import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fetchit import cli, core, config, history


class CliTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.cfg = {**config.DEFAULTS, 'output_dir': str(root / 'output')}
        for mod, name, val in [(config, 'CONFIG_FILE', root / 'config.json'),
                               (history, 'HISTORY_FILE', root / 'history.json'),
                               (history, 'LOG_FILE', root / 'log'),
                               (history, 'DATA_DIR', root)]:
            p = patch.object(mod, name, val); p.start(); self.addCleanup(p.stop)
        p = patch.object(config, 'load_config', return_value=self.cfg)
        p.start(); self.addCleanup(p.stop)
        p = patch.object(core, 'find_ytdlp', return_value='yt-dlp')
        p.start(); self.addCleanup(p.stop)
        self.out = io.StringIO(); self.err = io.StringIO()

    def invoke(self, argv):
        with redirect_stdout(self.out), redirect_stderr(self.err):
            return cli.main(argv)

    def test_flags_after_url_are_effective(self):
        self.assertEqual(self.invoke(['https://example.com/v', '-q', '720', '--dry-run']), 0)
        self.assertIn('height<=720', self.out.getvalue())

    def test_interleaved_multiple_urls(self):
        self.assertEqual(self.invoke(['https://example.com/a', '-q', '720',
                                     'https://example.com/b', '--dry-run']), 0)
        self.assertIn('height<=720', self.out.getvalue())
        self.assertIn('https://example.com/b', self.out.getvalue())

    def test_explicit_passthrough_is_preserved(self):
        self.assertEqual(self.invoke(['--dry-run', 'url', '--', '--sleep-interval', '2']), 0)
        self.assertIn('--sleep-interval 2', self.out.getvalue())

    def test_dry_run_does_not_write_state(self):
        self.invoke(['--dry-run', 'url'])
        self.assertFalse(history.HISTORY_FILE.exists())
        self.assertFalse(history.LOG_FILE.exists())
        self.assertFalse(Path(self.cfg['output_dir']).exists())

    def test_save_defaults_includes_output_folder(self):
        self.invoke(['--save-as-default', '-o', self.tmp.name, '--dry-run', 'url'])
        self.assertIn(self.tmp.name, config.CONFIG_FILE.read_text())

    def test_missing_tool_error_is_handled(self):
        with patch.object(core, 'find_ytdlp', side_effect=SystemExit('missing yt-dlp')):
            self.assertEqual(self.invoke(['url']), 1)
        self.assertIn('missing', self.err.getvalue())

    def test_print_url_outputs_real_urls_only(self):
        import subprocess
        row = '{"id":"abc","title":"Example","url":"https://www.youtube.com/watch?v=abc"}\n'
        with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, row, '')):
            self.assertEqual(self.invoke(['--search', 'example', '--print-url']), 0)
        self.assertEqual(self.out.getvalue().strip(), 'https://www.youtube.com/watch?v=abc')

    def test_failed_search_with_partial_output_is_failure(self):
        import subprocess
        row = '{"id":"abc","title":"Example","url":"https://www.youtube.com/watch?v=abc"}\n'
        with patch.object(cli.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, row, 'search failed')):
            self.assertEqual(self.invoke(['--search', 'example']), 1)
        self.assertIn('search failed', self.err.getvalue())

    def test_noninteractive_no_target_shows_help(self):
        with patch('sys.stdin.isatty', return_value=False):
            self.assertEqual(self.invoke([]), 0)
        self.assertIn('usage:', self.out.getvalue())

    def test_prompt_batch_records_target(self):
        from fetchit import ui
        batch = Path(self.tmp.name) / 'urls.txt'; batch.write_text('https://example.com/v\n')
        args = ui.make_args(self.cfg); args.batch_file = str(batch); args.dry_run = False
        with patch.object(core, 'run', return_value=0), redirect_stdout(self.out):
            ui.run_download(args, self.cfg)
        self.assertIn('batch:', history.show())

    def test_prompt_video_uses_configured_defaults(self):
        from fetchit import ui
        cfg = {**self.cfg, 'quality': '720', 'format': 'mkv'}
        answers = iter(['https://example.com/v', '', '', 'n', 'n', ''])
        commands = []
        def run(cmd, dry_run=False): commands.append(cmd); return 0
        with patch('builtins.input', side_effect=lambda _: next(answers)), patch.object(ui, 'clear'), \
             patch.object(ui, 'banner'), patch.object(core, 'run', side_effect=run), redirect_stdout(self.out):
            ui.flow_video(cfg)
        self.assertIn('height<=720', commands[0][commands[0].index('-f') + 1])
        self.assertEqual(commands[0][commands[0].index('--merge-output-format') + 1], 'mkv')

    def test_prompt_video_accepts_low_resolution_defaults(self):
        from fetchit import ui
        for quality in ('144', '240'):
            cfg = {**self.cfg, 'quality': quality}
            answers = iter(['https://example.com/v', '', '', 'n', 'n', ''])
            commands = []
            def run(cmd, dry_run=False): commands.append(cmd); return 0
            with patch('builtins.input', side_effect=lambda _: next(answers)), patch.object(ui, 'clear'), \
                 patch.object(ui, 'banner'), patch.object(core, 'run', side_effect=run), redirect_stdout(self.out):
                ui.flow_video(cfg)
            self.assertIn('height<=' + quality, commands[0][commands[0].index('-f') + 1])

    def test_cancelled_cli_job_has_cancelled_history_status(self):
        with patch.object(core, 'run', return_value=130):
            self.assertEqual(self.invoke(['url']), 130)
        self.assertEqual(history._load()[-1]['status'], 'cancelled')
