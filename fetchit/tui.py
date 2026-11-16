"""Fetchit's full-screen terminal workspace. No third-party Python packages."""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import shutil
import sys
import unicodedata

from . import config, core, history, jobs
from .tui_state import AppState, SCREENS, LABELS, safe_text

_THEME = {}
TITLES = {'video': ('Download a video', 'A link, your preferred quality, and a place to save it.'),
          'audio': ('Just the audio', 'Extract a soundtrack, podcast, or music collection.'),
          'playlist': ('Keep the whole collection', 'Download a playlist or channel. Choose a range if you need one.'),
          'search': ('Find your next download', 'Search YouTube, select a result, then choose how to save it.'),
          'batch': ('Bring your list', 'One URL per line. Download the list in a single job.'),
          'history': ('Your recent downloads', 'Command outcomes, newest first. Dry runs never change history.'),
          'settings': ('Make it yours', 'Defaults for new forms and command-line downloads.')}


def available() -> bool:
    if not (sys.stdin.isatty() and sys.stdout.isatty() and os.name == 'posix'
            and os.environ.get('TERM', '') not in ('', 'dumb')
            and importlib.util.find_spec('curses')):
        return False
    import curses
    try:
        curses.setupterm(term=os.environ['TERM'])
        return True
    except curses.error:
        return False


def dependency_status() -> str:
    return '  '.join(f'{name} {"ready" if shutil.which(name) else "missing"}' for name in ('yt-dlp', 'ffmpeg'))


def cell_width(value: str) -> int:
    return sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in ('W', 'F') else 1 for c in value)


def clip(value: str, width: int) -> str:
    result, used = [], 0
    for c in safe_text(value):
        size = cell_width(c)
        if used + size > width: break
        result.append(c); used += size
    return ''.join(result)


def _put(win, y: int, x: int, value: str, style: str = 'text', width: int | None = None) -> None:
    h, w = win.getmaxyx()
    if not (0 <= y < h and 0 <= x < w - 1): return
    max_width = min(w - x - 1, width if width is not None else w)
    text = clip(value, max_width)
    try:
        win.addstr(y, x, text, _THEME.get(style, 0))
    except Exception as exc:
        # Only curses' bottom-right and resize races are harmless here.
        if exc.__class__.__module__ != '_curses': raise


def _line(win, y, x, width):
    _put(win, y, x, '─' * max(0, width), 'muted', width)


def draw(stdscr, state: AppState) -> None:
    h, w = stdscr.getmaxyx()
    stdscr.erase()
    if w < 60 or h < 20:
        _put(stdscr, max(0, h // 2 - 1), 1, 'Fetchit needs 60 columns and 20 rows.', 'accent')
        _put(stdscr, max(0, h // 2 + 1), 1, 'Resize to continue. Your input is kept. q quits.', 'muted')
        stdscr.refresh()
        return
    wide = w >= 92
    left = 26 if wide else 3
    content_width = w - left - 3
    _put(stdscr, 1, 3, '↓  fetchit', 'brand')
    _put(stdscr, 1, 17, '/  your download workspace', 'muted', max(0, w - 57))
    deps = getattr(state, 'dependencies', '')
    _put(stdscr, 1, max(42, w - cell_width(deps) - 3), deps, 'muted')
    _line(stdscr, 3, 3, w - 6)
    if wide:
        if h >= 22: _put(stdscr, 5, 3, 'Workspace', 'muted')
        nav_top, nav_step = (7 if h >= 22 else 5), (2 if h >= 30 else 1)
        for i, name in enumerate(LABELS):
            selected = state.screen == SCREENS[i]
            style = 'focus' if selected and state.focus == -1 else 'accent' if selected else 'muted'
            _put(stdscr, nav_top + i * nav_step, 3, f'{">" if selected else " "} {i + 1}  {name}'.ljust(19), style, 19)
        if h >= 30:
            _put(stdscr, h - 12, 4, 'No pip required.', 'muted', 18)
            _put(stdscr, h - 11, 4, 'Files stay local.', 'muted', 18)
        for y in range(5, h - 9): _put(stdscr, y, 23, '│', 'muted')
    else:
        names = ('Video', 'Audio', 'Lists', 'Find', 'Batch', 'Log', 'Setup')
        x = 3
        for i, name in enumerate(names):
            token = f'{i + 1} {name} '
            _put(stdscr, 4, x, token, 'focus' if state.screen == SCREENS[i] and state.focus == -1 else 'muted')
            x += len(token)
    title, hint = TITLES[state.screen]
    _put(stdscr, 5 if wide else 6, left, title, 'brand')
    _put(stdscr, 6 if wide else 7, left, hint, 'muted', content_width)
    top, bottom = 9, h - 9
    rows = max(1, (bottom - top) // 2)
    show_results = state.screen == 'search' and bool(state.results)
    if show_results or state.screen == 'history':
        items = state.results if show_results else state.history_entries
        selected = max(0, state.focus)
        start = max(0, selected - rows + 1)
        for offset, entry in enumerate(items[start:start + rows]):
            i = start + offset
            y = top + offset * 2
            text = entry.get('title') or entry.get('url') or 'Unknown target'
            prefix = f'{i + 1}. ' if show_results else f'[{entry.get("status", "?")}] '
            _put(stdscr, y, left, f'{">" if state.focus == i else " "} {prefix}{text}',
                 'focus' if state.focus == i else 'text', content_width)
            _put(stdscr, y + 1, left + 3, entry.get('url', '') if show_results else str(entry.get('ts', '')), 'muted', content_width - 3)
        if not items:
            _put(stdscr, top, left, 'Nothing here yet. Start a download to build your history.', 'muted', content_width)
        label = 'Enter: choose video    Esc: new search' if show_results else '[ Clear history ]'
        _put(stdscr, bottom, left, label, 'focus' if not show_results and state.focus == len(items) else 'accent', content_width)
    else:
        selected = min(max(0, state.focus), max(0, len(state.fields) - 1))
        start = max(0, selected - rows + 1)
        for offset, field in enumerate(state.fields[start:start + rows]):
            i, y = start + offset, top + offset * 2
            focused = state.focus == i
            label_width = min(23, max(14, content_width // 3))
            _put(stdscr, y, left, field.label, 'accent' if focused else 'muted', label_width - 1)
            value_width = content_width - label_width
            value = field.value or ('Paste or type here' if field.key in ('url', 'query', 'batch_file') else 'All items')
            if focused and not field.choices:
                # Keep the editing point visible without relying on terminal cursor support.
                end = field.cursor
                before = field.value[:end]
                while cell_width(before) > max(1, value_width - 4): before = before[1:]
                value = before + '│' + field.value[end:]
            elif field.choices:
                value = f'‹ {value} ›'
            value = clip(' ' + value, value_width)
            value += ' ' * max(0, value_width - cell_width(value))
            _put(stdscr, y, left + label_width, value, 'focus' if focused else 'field', value_width)
        action = 'Save changes' if state.screen == 'settings' else 'Search YouTube' if state.screen == 'search' else 'Preview command' if state.dry_run else 'Start download'
        style = 'focus' if state.focus == len(state.fields) else 'accent'
        _put(stdscr, bottom, left, f'[ {action} ]', style, content_width)
        if len(state.fields) > rows:
            _put(stdscr, bottom, left + content_width - 15, f'{start + 1}–{min(len(state.fields), start + rows)} / {len(state.fields)} fields', 'muted', 15)
    _line(stdscr, h - 8, 3, w - 6)
    _put(stdscr, h - 7, 3, state.job_label, 'accent' if state.busy else 'text', w - 6)
    percent = state.progress.get('percent')
    bar_width = min(34, max(10, w // 3))
    filled = int(bar_width * (percent or 0) / 100)
    bar = '━' * filled + '─' * (bar_width - filled)
    suffix = f'{percent:5.1f}%' if percent is not None else ('working' if state.busy else 'ready')
    _put(stdscr, h - 6, 3, bar, 'accent')
    _put(stdscr, h - 6, bar_width + 5, f'{suffix}   {state.progress.get("speed", "")}   ETA {state.progress.get("eta") or "—"}', 'muted', w - bar_width - 8)
    _put(stdscr, h - 5, 3, state.job_target or f'Save to {state.cfg["output_dir"]}', 'muted', w - 6)
    if state.logs: _put(stdscr, h - 4, 3, state.logs[-1], 'muted', w - 6)
    status = 'Clear all download history? y: clear / n or Esc: keep it' if state.confirm_clear else state.status
    _put(stdscr, h - 3, 3, status, 'error' if state.error else 'accent', w - 6)
    help_text = 'Arrows: navigate   Tab: edit   Enter: open   q: quit' if state.focus == -1 else 'Tab / Shift-Tab: focus   Enter: next / activate   Esc: navigation   Ctrl-U: clear'
    if state.busy: help_text = 'Ctrl-X: cancel job   ' + help_text
    _put(stdscr, h - 1, 3, help_text, 'muted', w - 6)
    stdscr.refresh()


def summarize_error(text: str) -> str:
    """Put the failure reason before extractor chatter in the narrow status row."""
    lines = [safe_text(line).strip() for line in str(text).splitlines() if line.strip()]
    errors = [line for line in lines if line.startswith('ERROR:')]
    reason = errors[-1] if errors else (lines[-1] if lines else 'Download failed.')
    lower = reason.lower()
    if 'sign in to confirm' in lower and ('bot' in lower or 'authentication' in lower):
        return 'YouTube requires browser sign-in. Retry with browser cookies.'
    if '429' in lower and ('http' in lower or 'too many requests' in lower):
        return 'YouTube rate limit (HTTP 429). Try again later.'
    return reason


def handle_event(state: AppState, kind: str, data: dict) -> None:
    if kind == 'progress':
        state.progress = data
        state.job_label = 'Downloading · postprocessing finishes before completion'
    elif kind == 'log':
        state.logs.append(safe_text(data['text']))
    elif kind == 'complete':
        state.busy = False
        rc = data['returncode']
        cancelled = data.get('cancelled', False)
        outcome = 'cancelled' if cancelled else 'ok' if rc == 0 else f'exit-{rc}'
        state.job_outcome = outcome
        state.error = rc != 0 and not cancelled
        if cancelled:
            state.status = 'Cancelled. Partial files are kept for a later resume.'
            state.job_label = 'Job cancelled'
        elif rc:
            details = data.get('error') or f'Job failed (exit {rc}).'
            state.status = summarize_error(details)
            state.job_label = 'Job failed · review the message below'
            for line in str(details).splitlines():
                if line.strip():
                    state.logs.append(safe_text(line))
        elif getattr(state, 'job_kind', 'download') == 'search':
            state.results = data.get('results', [])
            if state.results and state.screen != 'search': state.select_screen('search')
            state.focus = 0 if state.results else -1
            state.status = f'{len(state.results)} results. Enter selects a video.' if state.results else 'No results. Try another query.'
            state.job_label = 'Search complete'
        else:
            state.status = 'Download complete. Your files are ready.'
            state.job_label = 'Download complete'
        for target in getattr(state, 'job_targets', []):
            try: history.add(target, status=outcome)
            except OSError as exc: state.status += f' History could not be saved: {exc}'
        state.job_targets = []
        state.history_entries = list(reversed(history._load()))
        if state.screen == 'history': state.focus = min(state.focus, len(state.history_entries))


def perform_action(state: AppState, action: str | None, job=None):
    if not action: return None
    try:
        if action == 'cancel':
            if job and not job.finished:
                job.cancel(); state.status = 'Cancelling…'
            return None
        if action == 'clear_history':
            history.clear(); state.history_entries = []; state.focus = 0
            state.status = 'History cleared.'; state.error = False
            return None
        if action == 'save':
            cfg = state.settings_values()
            config.save_config(cfg); state.refresh_defaults(cfg)
            state.status = 'Settings saved. New forms use these defaults.'; state.error = False
            return None
        if state.busy:
            state.status = 'A job is running. Cancel it with Ctrl-X before starting another.'
            return None
        if action == 'search':
            values = {f.key: f.value for f in state.fields}
            try: limit = int(values['limit'])
            except ValueError: raise ValueError('Results must be a number between 1 and 50.') from None
            cmd = jobs.search_command(values['query'], limit)
            targets = []; state.job_kind = 'search'
            state.job_target = values['query']; state.results = []
        elif action == 'download':
            args = state.download_args()
            cmd = core.build_command(args, state.cfg)
            targets = list(args.url)
            if args.batch_file: targets.append(f'batch:{args.batch_file}')
            state.job_kind = 'download'; state.job_target = ', '.join(targets)
        else: return None
        state.logs.clear(); state.progress = {'percent': None, 'speed': '', 'eta': ''}
        state.error = False
        if state.dry_run:
            state.logs.append(core.display_command(cmd))
            state.status = 'Dry run complete. No download, search, or state write was performed.'
            state.job_label = 'Command preview'; state.job_outcome = 'dry-run'
            return None
        if action == 'download':
            Path(cmd[cmd.index('-P') + 1]).mkdir(parents=True, exist_ok=True)
            cmd[1:1] = ['--newline', '--no-color', '--progress-template', jobs.PROGRESS_TEMPLATE]
        state.job_targets = targets
        state.busy = True; state.job_label = 'Searching YouTube…' if action == 'search' else 'Starting download…'
        state.status = 'Ctrl-X cancels the active job. You can still browse the workspace.'
        new_job = jobs.ManagedJob(cmd, search=action == 'search')
        new_job.start()
        return new_job
    except (ValueError, OSError, SystemExit) as exc:
        state.status = safe_text(str(exc)); state.error = True
        return None


def _setup_colors(curses) -> None:
    _THEME.clear()
    _THEME.update(brand=curses.A_BOLD, focus=curses.A_REVERSE, accent=curses.A_BOLD,
                  muted=0, field=0, error=curses.A_BOLD)
    if not curses.has_colors() or 'NO_COLOR' in os.environ: return
    curses.start_color()
    curses.use_default_colors()
    if curses.COLORS >= 256:
        palette = ((253, 234), (117, 234), (246, 234), (253, 236), (234, 117), (210, 234))
    else:
        palette = ((7, -1), (6, -1), (7, -1), (7, -1), (0, 6), (1, -1))
    for index, (fg, bg) in enumerate(palette, 1): curses.init_pair(index, fg, bg)
    _THEME.update(text=curses.color_pair(1), brand=curses.color_pair(2) | curses.A_BOLD,
                  accent=curses.color_pair(2), muted=curses.color_pair(3),
                  field=curses.color_pair(4), focus=curses.color_pair(5) | curses.A_BOLD,
                  error=curses.color_pair(6))


def _key(raw, curses) -> str:
    mapping = {curses.KEY_UP: 'up', curses.KEY_DOWN: 'down', curses.KEY_LEFT: 'left',
               curses.KEY_RIGHT: 'right', curses.KEY_BACKSPACE: 'backspace', curses.KEY_DC: 'delete',
               curses.KEY_HOME: 'home', curses.KEY_END: 'end', curses.KEY_BTAB: 'backtab',
               curses.KEY_ENTER: 'enter', curses.KEY_RESIZE: 'resize',
               '\t': 'tab', '\n': 'enter', '\r': 'enter', '\x1b': 'escape', '\x7f': 'backspace',
               '\b': 'backspace', '\x15': 'clear', '\x01': 'home', '\x05': 'end', '\x18': 'cancel'}
    return mapping.get(raw, raw if isinstance(raw, str) else '')


def _loop(stdscr, cfg: dict, dry_run: bool, curses) -> int:
    _setup_colors(curses)
    stdscr.bkgd(' ', _THEME.get('text', 0))
    stdscr.keypad(True); stdscr.timeout(80)
    curses.set_escdelay(25)
    try: curses.curs_set(0)
    except curses.error: pass
    state = AppState(cfg, dry_run)
    state.dependencies = dependency_status()
    state.history_entries = list(reversed(history._load()))
    job = None
    try:
        while True:
            if job:
                for event in job.poll(): handle_event(state, event.kind, event.data)
            draw(stdscr, state)
            try: key = _key(stdscr.get_wch(), curses)
            except curses.error: continue
            except KeyboardInterrupt:
                if state.busy: perform_action(state, 'cancel', job); continue
                return 130
            if key == 'resize': continue
            h, w = stdscr.getmaxyx()
            if w < 60 or h < 20:
                if key == 'q': return 0
                if key == 'cancel': perform_action(state, 'cancel', job)
                continue
            action = state.navigate(key)
            if action == 'quit': return 0
            new_job = perform_action(state, action, job)
            if new_job:
                if job: job.close()
                job = new_job
    finally:
        if job:
            job.close()
            for event in job.poll(): handle_event(state, event.kind, event.data)


def run(cfg: dict, dry_run: bool = False) -> int:
    import curses
    return curses.wrapper(lambda win: _loop(win, cfg, dry_run, curses))
