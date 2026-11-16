"""Bounded subprocess events for responsive terminal downloads and search."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import json
import math
import os
import re
import selectors
import signal
import subprocess
import threading
import time
from urllib.parse import urlparse

from . import core

PROGRESS_TEMPLATE = 'download:FETCHIT_PROGRESS|%(progress._percent_str)s|%(progress._speed_str)s|%(progress._eta_str)s'


@dataclass(frozen=True)
class JobEvent:
    kind: str
    data: dict


def parse_progress(line: str) -> dict | None:
    if not line.startswith('FETCHIT_PROGRESS|'):
        return None
    fields = line.split('|')
    if len(fields) != 4:
        return None
    try:
        percent = float(fields[1].strip().rstrip('%'))
        percent = min(100., max(0., percent)) if math.isfinite(percent) else None
    except ValueError:
        percent = None
    return {'percent': percent, 'speed': fields[2].strip(), 'eta': fields[3].strip()}


def search_command(query: str, limit: int) -> list[str]:
    if not query.strip():
        raise ValueError('enter a search query')
    if not 1 <= limit <= 50:
        raise ValueError('search results must be between 1 and 50')
    return [core.find_ytdlp(), '--flat-playlist', '--dump-json', '--no-warnings',
            '--', f'ytsearch{limit}:{query.strip()}']


def parse_search(output: str) -> list[dict]:
    results = []
    for line in output.splitlines():
        try:
            item = json.loads(line)
        except ValueError:
            continue
        if not isinstance(item, dict):
            continue
        url = item.get('webpage_url') or item.get('url')
        if not isinstance(url, str):
            continue
        try:
            parsed = urlparse(url)
        except ValueError:
            continue
        if parsed.scheme not in ('http', 'https') or not parsed.netloc:
            continue
        if any(ord(c) < 32 for c in url):
            continue
        results.append({'title': str(item.get('title') or item.get('id') or url), 'url': url})
    return results


class ManagedJob:
    """Own one process; all drawing and persistence belong to the caller."""
    def __init__(self, cmd: list[str], search: bool = False, raw_output=None, raw_error=None):
        self.cmd = list(cmd)
        self.search = search
        self._raw_output = raw_output
        self._raw_error = raw_error
        self.finished = False
        self._cancel = threading.Event()
        self._events = deque(maxlen=256)
        self._lock = threading.Lock()
        self._thread = None
        self._proc = None

    def _emit(self, kind: str, **data) -> None:
        with self._lock:
            self._events.append(JobEvent(kind, data))

    def poll(self) -> list[JobEvent]:
        with self._lock:
            events = list(self._events)
            self._events.clear()
        return events

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError('job already started')
        self._thread = threading.Thread(target=self._work, name='fetchit-job', daemon=True)
        self._thread.start()

    def cancel(self) -> None:
        self._cancel.set()

    def _signal(self, sig) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if os.name == 'posix':
                os.killpg(proc.pid, sig)
            elif proc.poll() is None:
                proc.kill() if sig == signal.SIGKILL else proc.terminate()
        except ProcessLookupError:
            pass

    def close(self) -> None:
        if self._thread is not None:
            if not self.finished:
                self.cancel()
            self._thread.join(3)
            if self._thread.is_alive():
                self._signal(signal.SIGKILL)
                self._thread.join(2)

    def _work(self) -> None:
        result = {'returncode': 1, 'cancelled': False, 'error': '', 'results': []}
        try:
            if self._cancel.is_set():
                result.update(returncode=130, cancelled=True)
            else:
                result = self._attempt(self.cmd)
                retry = core.anonymous_retry_command(self.cmd, result.get('error', ''))
                if (retry and result['returncode'] and not result.get('media_started')
                        and not self._cancel.is_set() and not self.search):
                    self._emit('log', text='YouTube blocked the first attempt. Trying an anonymous alternative…', system=True)
                    result = self._attempt(retry)
        except (OSError, ValueError) as exc:
            result.update(returncode=1, error=str(exc))
        finally:
            if self._cancel.is_set():
                result.update(returncode=130, cancelled=True, error='', results=[])
            result.pop('media_started', None)
            self._emit('complete', **result)
            self.finished = True

    def _attempt(self, cmd: list[str]) -> dict:
        rc, error = 1, ''
        media_started = False
        search_lines = []
        search_bytes = 0
        tail = deque(maxlen=6)
        try:
            self._proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE if self._raw_output else subprocess.STDOUT,
                stdin=subprocess.DEVNULL, start_new_session=os.name == 'posix')
            buffer = b''
            terminate_at = None
            exit_at = None
            with selectors.DefaultSelector() as selector:
                selector.register(self._proc.stdout, selectors.EVENT_READ, 'stdout')
                if self._raw_output:
                    selector.register(self._proc.stderr, selectors.EVENT_READ, 'stderr')
                while selector.get_map():
                    now = time.monotonic()
                    if self._cancel.is_set():
                        if terminate_at is None:
                            self._signal(signal.SIGTERM)
                            terminate_at = now
                        elif now - terminate_at > .8:
                            self._signal(signal.SIGKILL)
                    if self._proc.poll() is not None:
                        exit_at = exit_at or now
                        # Do not hang if an orphan child inherited stdout.
                        if now - exit_at > 1:
                            self._signal(signal.SIGKILL)
                            break
                    ready = selector.select(.05)
                    if not ready:
                        continue
                    stream = ready[0][0]
                    chunk = os.read(stream.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(stream.fileobj)
                        continue
                    if self._raw_output and stream.data == 'stdout':
                        self._raw_output(chunk)
                        continue
                    if self._raw_error:
                        self._raw_error(chunk)
                    buffer += chunk
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        text = line.decode('utf-8', errors='replace').rstrip('\r')
                        if self.search:
                            search_bytes += len(line)
                            if search_bytes > 2 * 1024 * 1024:
                                raise ValueError('search output exceeded the safe buffer size')
                            search_lines.append(text)
                        else:
                            progress = parse_progress(text)
                            if (progress is not None or text.startswith(('[download] Destination:', '[Merger]', '[ExtractAudio]'))
                                    or re.match(r'\[download\]\s+[0-9.]+%', text)):
                                media_started = True
                            self._emit('progress', **progress) if progress else self._emit('log', text=text[:8192])
                        if text and not text.startswith('{'):
                            tail.append(text[:8192])
                    if len(buffer) > 1024 * 1024:
                        raise ValueError('subprocess output line is too large')
                if buffer:
                    text = buffer.decode('utf-8', errors='replace')
                    if self.search:
                        search_lines.append(text)
                    else:
                        self._emit('log', text=text[:8192])
                    if text and not text.startswith('{'):
                        tail.append(text[:8192])
            while self._proc.poll() is None:
                if self._cancel.is_set():
                    self._signal(signal.SIGTERM)
                    try:
                        self._proc.wait(.8)
                    except subprocess.TimeoutExpired:
                        self._signal(signal.SIGKILL)
                time.sleep(.02)
            rc = self._proc.wait()
            if rc != 0:
                error = '\n'.join(tail) or f'yt-dlp exited with status {rc}'
        except (OSError, ValueError) as exc:
            error = str(exc)
            self._signal(signal.SIGKILL)
        finally:
            # A reaped parent does not imply its process group is gone.
            if self._cancel.is_set():
                self._signal(signal.SIGKILL)
            if self._proc is not None:
                if self._proc.poll() is None:
                    self._signal(signal.SIGKILL)
                self._proc.wait()
                self._proc.stdout.close()
                if self._proc.stderr is not None:
                    self._proc.stderr.close()
            cancelled = self._cancel.is_set()
            results = []
            try:
                if self.search and rc == 0 and not cancelled:
                    results = parse_search('\n'.join(search_lines))
            except (ValueError, TypeError) as exc:
                rc, error = 1, f'Could not read search results: {exc}'
        return dict(returncode=130 if cancelled else rc, cancelled=cancelled,
                    error='' if cancelled else error, results=results, media_started=media_started)
