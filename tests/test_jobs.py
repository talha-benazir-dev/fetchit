import json
import os
from pathlib import Path
import sys
import time
import unittest
from unittest.mock import patch
import importlib.util


class JobTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('fetchit.jobs'), 'managed job module missing')
        from fetchit import jobs
        self.jobs = jobs

    def run_job(self, code, search=False):
        job = self.jobs.ManagedJob([sys.executable, '-u', '-c', code], search=search)
        self.addCleanup(job.close)
        job.start()
        return job

    def collect(self, job):
        events = []
        deadline = time.monotonic() + 5
        while not job.finished and time.monotonic() < deadline:
            events.extend(job.poll()); time.sleep(.01)
        self.assertTrue(job.finished, 'job did not finish')
        events.extend(job.poll())
        return events

    def test_progress_before_completion(self):
        job = self.run_job("import time; print('FETCHIT_PROGRESS|50.0%|2MiB/s|00:04'); time.sleep(.4)")
        deadline = time.monotonic() + 2
        events = []
        while not events and time.monotonic() < deadline:
            events.extend(job.poll()); time.sleep(.01)
        self.assertFalse(job.finished)
        self.assertEqual(events[0].kind, 'progress')
        self.assertEqual(events[0].data['percent'], 50.0)
        events.extend(self.collect(job))
        self.assertEqual(events[-1].data['returncode'], 0)

    def test_cancel_before_start(self):
        job = self.jobs.ManagedJob([sys.executable, '-c', 'raise SystemExit(9)'])
        self.addCleanup(job.close)
        job.cancel(); job.start()
        events = self.collect(job)
        self.assertTrue(events[-1].data['cancelled'])

    def test_cancel_reaps_running_process(self):
        job = self.run_job("import time; print('ready'); time.sleep(30)")
        deadline = time.monotonic() + 2
        while not job.poll() and time.monotonic() < deadline: time.sleep(.01)
        job.cancel()
        events = self.collect(job)
        self.assertTrue(events[-1].data['cancelled'])
        self.assertEqual(events[-1].data['returncode'], 130)

    def test_missing_executable_has_useful_error(self):
        job = self.jobs.ManagedJob(['/no/such/fetchit-test'])
        self.addCleanup(job.close); job.start()
        events = self.collect(job)
        self.assertEqual(events[-1].data['returncode'], 1)
        self.assertTrue(events[-1].data['error'])

    def test_output_buffer_is_bounded_and_keeps_completion(self):
        job = self.run_job("for i in range(30000): print('line', i)")
        deadline = time.monotonic() + 5
        while not job.finished and time.monotonic() < deadline: time.sleep(.01)
        events = job.poll()
        self.assertLessEqual(len(events), 256)
        self.assertEqual(events[-1].kind, 'complete')

    def test_failed_partial_search_is_not_success(self):
        data = json.dumps({'id': 'abc', 'title': 'Example', 'url': 'https://www.youtube.com/watch?v=abc'})
        job = self.run_job(f"print({data!r}); raise SystemExit(1)", search=True)
        events = self.collect(job)
        self.assertEqual(events[-1].data['returncode'], 1)
        self.assertEqual(events[-1].data.get('results', []), [])

    def test_search_titles_do_not_depend_on_line_pairs(self):
        line = json.dumps({'id': 'abc', 'title': 'A title\nwith another line', 'url': 'https://www.youtube.com/watch?v=abc'})
        rows = self.jobs.parse_search(line)
        self.assertEqual(rows[0]['url'], 'https://www.youtube.com/watch?v=abc')
        self.assertIn('another line', rows[0]['title'])
        self.assertEqual(self.jobs.parse_search('warning\nnull\n{"url":"file:///etc/passwd"}'), [])

    def test_unknown_progress_is_safe(self):
        result = self.jobs.parse_progress('FETCHIT_PROGRESS|NA|NA|NA')
        self.assertIsNone(result['percent'])
        self.assertIsNone(self.jobs.parse_progress('ordinary log'))

    def test_malformed_search_url_still_emits_completion(self):
        job = self.run_job('print(\'{"url":"https://[oops"}\')', search=True)
        events = self.collect(job)
        self.assertEqual(events[-1].kind, 'complete')
        self.assertEqual(events[-1].data['results'], [])

    @unittest.skipUnless(os.name == 'posix' and Path('/proc').exists(), 'Linux process group test')
    def test_cancel_kills_child_even_when_parent_exits_and_pipe_closes(self):
        from tempfile import TemporaryDirectory
        with TemporaryDirectory() as directory:
            pidfile = Path(directory) / 'child'
            code = f'''import os, signal, time
pid = os.fork()
if pid == 0:
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    fd = os.open('/dev/null', os.O_WRONLY)
    os.dup2(fd, 1); os.dup2(fd, 2)
    open({str(pidfile)!r}, 'w').write(str(os.getpid()))
    time.sleep(30)
else:
    while not os.path.exists({str(pidfile)!r}): time.sleep(.01)
    print('ready', flush=True)
    time.sleep(30)
'''
            job = self.run_job(code)
            deadline = time.monotonic() + 2
            while not pidfile.exists() and time.monotonic() < deadline: time.sleep(.01)
            pid = int(pidfile.read_text())
            def alive():
                try: return Path(f'/proc/{pid}/stat').read_text().split()[2] != 'Z'
                except FileNotFoundError: return False
            try:
                job.cancel(); self.collect(job)
                deadline = time.monotonic() + 1
                while alive() and time.monotonic() < deadline: time.sleep(.01)
                self.assertFalse(alive(), 'cancelled job left a live child process')
            finally:
                if alive(): os.kill(pid, 9)

    def test_failure_in_final_unterminated_line_is_preserved(self):
        job = self.run_job("import sys; print('[youtube] Downloading player'); sys.stdout.write('ERROR: Sign in to confirm you are not a bot'); sys.stdout.flush(); raise SystemExit(1)")
        events = self.collect(job)
        self.assertIn('ERROR: Sign in', events[-1].data['error'])
