import importlib.util
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fetchit import config, history


class FakeWindow:
    def __init__(self, h, w):
        self.h, self.w = h, w
        self.writes = []
    def getmaxyx(self): return self.h, self.w
    def erase(self): self.writes.clear()
    def addstr(self, y, x, value, attr=0):
        from fetchit.tui import cell_width
        if not (0 <= y < self.h and 0 <= x < self.w and x + cell_width(value) <= self.w):
            raise AssertionError(f'drawing outside window: {y},{x},{value!r}')
        self.writes.append((y, x, value, attr))
    def refresh(self): pass
    def bkgd(self, *args): pass
    def move(self, y, x):
        if not (0 <= y < self.h and 0 <= x < self.w): raise AssertionError('cursor outside window')


class TerminalTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('fetchit.tui'), 'full-screen module missing')
        from fetchit import tui
        from fetchit.tui_state import AppState
        self.tui = tui
        self.state = AppState(config.DEFAULTS)

    def test_draw_clips_at_all_terminal_sizes(self):
        self.state.fields[0].value = 'https://example.com/' + '界' * 500
        for h, w in ((1, 1), (8, 15), (19, 59), (24, 60), (30, 80), (42, 140)):
            for screen in ('video', 'audio', 'playlist', 'search', 'batch', 'history', 'settings'):
                self.state.select_screen(screen)
                window = FakeWindow(h, w)
                self.tui.draw(window, self.state)
                self.assertTrue(window.writes or w == 1)

    def test_resize_keeps_form_value(self):
        self.state.fields[0].value = 'https://example.com/draft'
        for h, w in ((40, 120), (24, 60), (4, 10), (40, 120)):
            self.tui.draw(FakeWindow(h, w), self.state)
            self.assertEqual(self.state.fields[0].value, 'https://example.com/draft')

    def test_active_and_finished_job_have_different_status(self):
        self.state.busy = True
        self.tui.handle_event(self.state, 'progress', {'percent': 100, 'speed': '2MiB/s', 'eta': '0'})
        self.assertTrue(self.state.busy)
        self.tui.handle_event(self.state, 'complete', {'returncode': 130, 'cancelled': True, 'error': '', 'results': []})
        self.assertFalse(self.state.busy)
        self.assertIn('cancel', self.state.status.lower())
        self.tui.handle_event(self.state, 'complete', {'returncode': 0, 'cancelled': False, 'error': '', 'results': []})
        self.assertIn('complete', self.state.status.lower())

    def test_missing_tools_are_displayed(self):
        with patch('shutil.which', return_value=None):
            state = self.state
            state.dependencies = self.tui.dependency_status()
            w = FakeWindow(35, 120); self.tui.draw(w, state)
        text = '\n'.join(row[2] for row in w.writes)
        self.assertIn('missing', text)

    def test_history_clear_requires_confirmation_then_clears(self):
        with TemporaryDirectory() as d, patch.object(history, 'HISTORY_FILE', Path(d) / 'history.json'):
            history.HISTORY_FILE.write_text('[{"url":"example"}]')
            self.state.select_screen('history')
            self.state.history_entries = history._load()
            self.state.focus = 1
            self.state.navigate('enter')
            self.tui.draw(FakeWindow(35, 120), self.state)
            self.assertTrue(history.HISTORY_FILE.exists())
            action = self.state.navigate('y')
            self.tui.perform_action(self.state, action)
            self.assertFalse(history.HISTORY_FILE.exists())

    def test_failed_search_does_not_offer_partial_results(self):
        self.state.job_kind = 'search'; self.state.busy = True
        self.tui.handle_event(self.state, 'complete', {'returncode': 1, 'cancelled': False,
              'error': 'Search failed', 'results': []})
        self.assertEqual(self.state.results, [])
        self.assertTrue(self.state.error)

    def test_minimum_size_reserves_separate_field_and_action_rows(self):
        self.state.focus = 0
        self.state.fields[0].value = 'https://example.com/v'
        win = FakeWindow(20, 60); self.tui.draw(win, self.state)
        action_rows = {y for y, x, text, attr in win.writes if 'Start download' in text}
        field_rows = {y for y, x, text, attr in win.writes if 'https://example.com/v' in text}
        self.assertTrue(action_rows); self.assertTrue(field_rows)
        self.assertFalse(action_rows & field_rows)

    def test_invalid_terminal_type_uses_prompt_fallback(self):
        import curses
        with patch('sys.stdin.isatty', return_value=True), patch('sys.stdout.isatty', return_value=True), \
             patch.dict('os.environ', {'TERM': 'unknown-fetchit-terminal'}), \
             patch.object(curses, 'setupterm', side_effect=curses.error('unknown terminal')):
            self.assertFalse(self.tui.available())

    def test_youtube_failure_is_visible_instead_of_player_chatter(self):
        error = ('[youtube] Downloading visionos player API JSON\n'
                 '[youtube] Downloading iframe API JS\n'
                 '[youtube] Downloading player 21090930-main\n'
                 'ERROR: [youtube] video: Sign in to confirm you’re not a bot. Use --cookies for authentication.')
        self.tui.handle_event(self.state, 'complete', {'returncode': 1, 'cancelled': False, 'error': error, 'results': []})
        window = FakeWindow(24, 80); self.tui.draw(window, self.state)
        rendered = '\n'.join(text for y, x, text, attr in window.writes if y == 21)
        self.assertIn('sign-in', rendered.lower())
        self.assertNotIn('Downloading player', self.state.status)
        self.assertTrue(any('ERROR:' in line for line in self.state.logs))
        self.assertTrue(all('\n' not in line for line in self.state.logs))

    def test_rate_limit_error_has_actionable_message(self):
        self.tui.handle_event(self.state, 'complete', {'returncode': 1, 'cancelled': False,
            'error': '[youtube] Downloading webpage\nERROR: HTTP Error 429: Too Many Requests', 'results': []})
        self.assertIn('429', self.state.status)
        self.assertIn('later', self.state.status.lower())
