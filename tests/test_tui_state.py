import importlib.util
import unittest
from fetchit import config


class StateTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('fetchit.tui_state'), 'terminal state module missing')
        from fetchit.tui_state import AppState
        self.state = AppState({**config.DEFAULTS, 'quality': '720', 'format': 'mkv'})

    def test_tab_shift_tab_and_escape(self):
        s = self.state
        s.navigate('tab'); self.assertEqual(s.focus, 0)
        s.navigate('tab'); self.assertEqual(s.focus, 1)
        s.navigate('backtab'); self.assertEqual(s.focus, 0)
        s.navigate('escape'); self.assertEqual(s.focus, -1)

    def test_q_edits_field_and_quits_only_navigation(self):
        s = self.state
        s.navigate('tab'); self.assertIsNone(s.navigate('q'))
        self.assertEqual(s.fields[0].value, 'q')
        s.navigate('escape'); self.assertEqual(s.navigate('q'), 'quit')

    def test_choices_use_defaults_and_arrows(self):
        s = self.state
        s.navigate('tab'); s.navigate('tab')
        self.assertEqual(s.fields[1].value, '720')
        s.navigate('right'); self.assertEqual(s.fields[1].value, '480')
        self.assertEqual(s.download_args().format, 'mkv') if s.fields[0].value else None

    def test_url_editing_and_unicode_controls(self):
        s = self.state
        s.navigate('tab')
        for char in 'https://example.com/বাংলা': s.navigate(char)
        s.navigate('backspace'); s.navigate('x')
        self.assertTrue(s.fields[0].value.endswith('x'))
        s.navigate('\x1b'); self.assertNotIn('\x1b', s.fields[0].value)
        from fetchit.tui_state import safe_text
        self.assertEqual(safe_text('\x1b[31mবাংলা\nabc\x07'), 'বাংলা abc')

    def test_validation_retains_entered_value(self):
        s = self.state
        s.fields[0].value = 'not a URL'
        with self.assertRaises(ValueError): s.download_args()
        self.assertEqual(s.fields[0].value, 'not a URL')

    def test_download_uses_saved_defaults(self):
        s = self.state; s.fields[0].value = 'https://example.com/v'
        args = s.download_args()
        self.assertEqual(args.quality, '720'); self.assertEqual(args.format, 'mkv')

    def test_settings_reject_invalid_concurrency(self):
        s = self.state; s.select_screen('settings')
        next(f for f in s.fields if f.key == 'concurrent_fragments').value = '0'
        with self.assertRaises(ValueError): s.settings_values()

    def test_history_clear_requires_confirmation(self):
        s = self.state; s.select_screen('history'); s.focus = 0
        self.assertIsNone(s.navigate('enter')); self.assertTrue(s.confirm_clear)
        self.assertIsNone(s.navigate('n')); self.assertFalse(s.confirm_clear)
        s.navigate('enter'); self.assertEqual(s.navigate('y'), 'clear_history')

    def test_search_selection_prefills_video_form(self):
        s = self.state; s.select_screen('search')
        s.results = [{'title': 'test', 'url': 'https://example.com/v'}]; s.focus = 0
        self.assertIsNone(s.navigate('enter'))
        self.assertEqual(s.screen, 'video')
        self.assertEqual(s.fields[0].value, 'https://example.com/v')

    def test_switching_screens_retains_draft(self):
        s = self.state; s.fields[0].value = 'https://example.com/draft'
        s.select_screen('audio'); s.select_screen('video')
        self.assertEqual(s.fields[0].value, 'https://example.com/draft')
