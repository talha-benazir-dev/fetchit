import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import sys
import time
import unittest
from fetchit import core, jobs


class AnonymousRecoveryTests(unittest.TestCase):
    def test_bot_failure_gets_one_anonymous_alternative(self):
        self.assertTrue(hasattr(core, 'anonymous_retry_command'), 'anonymous recovery missing')
        cmd = ['yt-dlp', '-q', '720', '--', 'https://youtu.be/example']
        retry = core.anonymous_retry_command(cmd, 'ERROR: Sign in to confirm you are not a bot')
        self.assertIsNotNone(retry)
        i = retry.index('--extractor-args')
        self.assertEqual(retry[i + 1], 'youtube:player_client=web_embedded,tv_downgraded')
        self.assertLess(i, retry.index('--'))
        self.assertEqual(retry[-1], 'https://youtu.be/example')
        self.assertIsNone(core.anonymous_retry_command(retry, 'ERROR: Sign in to confirm you are not a bot'))
        self.assertFalse(any('cookie' in arg for arg in retry))

    def test_no_recovery_for_other_errors_sites_or_explicit_auth(self):
        self.assertTrue(hasattr(core, 'anonymous_retry_command'), 'anonymous recovery missing')
        for cmd, error in [
            (['yt-dlp', '--', 'https://example.com/v'], 'HTTP Error 429'),
            (['yt-dlp', '--', 'https://youtu.be/v'], 'ERROR: Video is private'),
            (['yt-dlp', '--cookies', 'cookies.txt', '--', 'https://youtu.be/v'], 'not a bot'),
            (['yt-dlp', '--extractor-args=youtube:player_client=web', '--', 'https://youtu.be/v'], 'not a bot'),
        ]:
            self.assertIsNone(core.anonymous_retry_command(cmd, error))

    def test_managed_job_retries_before_emitting_one_completion(self):
        with TemporaryDirectory() as directory:
            marker = Path(directory) / 'attempts'
            script = Path(directory) / 'fake.py'
            script.write_text('''import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text() + 'x' if p.exists() else 'x')
if '--extractor-args' not in sys.argv:
    print('ERROR: Sign in to confirm you are not a bot', file=sys.stderr, flush=True)
    raise SystemExit(1)
print('anonymous extraction succeeded', flush=True)
''')
            cmd = [sys.executable, str(script), str(marker), '--', 'https://youtu.be/example']
            job = jobs.ManagedJob(cmd); self.addCleanup(job.close); job.start()
            events = []; deadline = time.monotonic() + 4
            while not job.finished and time.monotonic() < deadline:
                events.extend(job.poll()); time.sleep(.01)
            events.extend(job.poll())
            self.assertTrue(job.finished)
            self.assertEqual(marker.read_text(), 'xx')
            completed = [e for e in events if e.kind == 'complete']
            self.assertEqual(len(completed), 1)
            self.assertEqual(completed[0].data['returncode'], 0)
            self.assertTrue(any('anonymous extraction succeeded' in e.data.get('text', '') for e in events))

    def test_foreground_download_uses_same_recovery(self):
        with TemporaryDirectory() as directory:
            script = Path(directory) / 'fake.py'
            script.write_text('''import sys
if '--extractor-args' not in sys.argv:
    print('ERROR: Sign in to confirm you are not a bot', file=sys.stderr)
    raise SystemExit(1)
print('anonymous extraction succeeded')
''')
            out = io.StringIO()
            with redirect_stdout(out), redirect_stderr(io.StringIO()):
                rc = core.run([sys.executable, str(script), '--', 'https://youtu.be/example'])
            self.assertEqual(rc, 0)
            self.assertIn('anonymous extraction succeeded', out.getvalue())

    def test_no_alternate_player_after_media_download_has_started(self):
        with TemporaryDirectory() as directory:
            marker = Path(directory) / 'attempts'
            script = Path(directory) / 'fake.py'
            script.write_text('''import pathlib, sys
p = pathlib.Path(sys.argv[1])
p.write_text(p.read_text() + 'x' if p.exists() else 'x')
print('[download] Destination: example.mp4')
print('ERROR: HTTP Error 429: Too Many Requests')
raise SystemExit(1)
''')
            job = jobs.ManagedJob([sys.executable, str(script), str(marker), '--', 'https://youtu.be/example'])
            self.addCleanup(job.close); job.start()
            deadline = time.monotonic() + 4
            while not job.finished and time.monotonic() < deadline: time.sleep(.01)
            self.assertTrue(job.finished)
            self.assertEqual(marker.read_text(), 'x', 'switching formats after partial media can corrupt resume')

    def test_foreground_preserves_long_json_output(self):
        import json, subprocess
        payload = json.dumps({'title': 'x' * 12000}) + '\n'
        child = [sys.executable, '-c', f'import sys; sys.stdout.write({payload!r})']
        result = subprocess.run([sys.executable, '-c', f'from fetchit.core import run; raise SystemExit(run({child!r}))'], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, payload.encode())

    def test_foreground_preserves_binary_stdout_separate_from_diagnostics(self):
        import subprocess
        child = [sys.executable, '-c', "import sys; sys.stderr.write('diagnostic\\n'); sys.stdout.buffer.write(bytes(range(256)) * 5000)"]
        result = subprocess.run([sys.executable, '-c', f'from fetchit.core import run; raise SystemExit(run({child!r}))'], capture_output=True)
        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout, bytes(range(256)) * 5000)
        self.assertIn(b'diagnostic', result.stderr)
