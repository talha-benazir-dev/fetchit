"""Exercise the real curses entry point in an isolated POSIX terminal."""
import fcntl
import json
import os
from pathlib import Path
import pty
import select
import signal
import struct
import subprocess
import sys
import termios
import time
from tempfile import TemporaryDirectory
import unittest


@unittest.skipUnless(os.name == 'posix', 'POSIX terminal integration')
class TerminalSessionTests(unittest.TestCase):
    def test_navigation_resize_download_cancel_and_terminal_restore(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            fake = root / 'yt-dlp'
            fake.write_text('#!' + sys.executable + '\nimport time\nprint("FETCHIT_PROGRESS|50.0%|2MiB/s|00:04", flush=True)\ntime.sleep(30)\n')
            fake.chmod(0o755)
            cfg = root / 'config' / 'fetchit'; cfg.mkdir(parents=True)
            (cfg / 'config.json').write_text(json.dumps({'output_dir': str(root / 'downloads')}))
            master, slave = pty.openpty()
            before = termios.tcgetattr(slave)
            fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 38, 120, 0, 0))
            env = {**os.environ, 'TERM': 'xterm-256color', 'PATH': str(root) + ':' + os.environ['PATH'],
                   'XDG_CONFIG_HOME': str(root / 'config'), 'XDG_DATA_HOME': str(root / 'data')}
            proc = subprocess.Popen([sys.executable, '-m', 'fetchit'], stdin=slave, stdout=slave,
                                    stderr=slave, env=env, start_new_session=True)
            transcript = bytearray()
            def drain(seconds=.3):
                until = time.monotonic() + seconds
                while time.monotonic() < until:
                    if select.select([master], [], [], .05)[0]:
                        transcript.extend(os.read(master, 65536))
            try:
                drain(.5)
                self.assertIsNone(proc.poll(), bytes(transcript).decode(errors='replace'))
                self.assertIn(b'Download a video', transcript)
                os.write(master, b'2'); drain(.2)
                self.assertIn(b'Just the audio', transcript)
                os.write(master, b'1\thttps://example.com/video')
                drain(.2)
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 12, 40, 0, 0))
                os.kill(proc.pid, signal.SIGWINCH); drain(.2)
                self.assertIn(b'Resize to continue', transcript)
                fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 38, 120, 0, 0))
                os.kill(proc.pid, signal.SIGWINCH); drain(.2)
                os.write(master, b'\t' * 7 + b'\n'); drain(.6)
                self.assertIn(b'50.0%', transcript)
                os.write(master, b'\x18'); drain(.5)
                history_file = root / 'data' / 'fetchit' / 'history.json'
                deadline = time.monotonic() + 3
                while not history_file.exists() and time.monotonic() < deadline: drain(.1)
                entries = json.loads(history_file.read_text())
                self.assertEqual(entries[-1]['status'], 'cancelled')
                self.assertEqual(entries[-1]['url'], 'https://example.com/video')
                os.write(master, b'\x1b'); drain(.1); os.write(master, b'q')
                proc.wait(timeout=3); drain(.1)
                self.assertEqual(proc.returncode, 0)
                self.assertNotIn(b'Traceback', transcript)
                self.assertEqual(termios.tcgetattr(slave), before)
            finally:
                if proc.poll() is None:
                    proc.kill(); proc.wait()
                os.close(master); os.close(slave)
