import io
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fetchit import cli, core, config, history


class CommandTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.cfg = {**config.DEFAULTS, 'output_dir': self.tmp.name + '/new'}
        p = patch.object(core, 'find_ytdlp', return_value='yt-dlp')
        p.start(); self.addCleanup(p.stop)

    def command(self, argv):
        return core.build_command(cli.build_parser().parse_args(argv), self.cfg)

    def test_builder_has_no_directory_side_effect(self):
        self.command(['--dry-run', 'https://example.com/v'])
        self.assertFalse(Path(self.cfg['output_dir']).exists())

    def test_invalid_quality_rejected(self):
        with self.assertRaises(ValueError): self.command(['-q', 'nonsense', 'url'])

    def test_invalid_concurrency_rejected(self):
        with self.assertRaises(ValueError): self.command(['--concurrent', '0', 'url'])

    def test_invalid_playlist_bounds_rejected(self):
        with self.assertRaises(ValueError):
            self.command(['--playlist-start', '5', '--playlist-end', '2', 'url'])

    def test_audio_defaults_are_respected(self):
        self.cfg['audio_format'] = 'flac'
        cmd = self.command(['--audio-only', 'url'])
        self.assertEqual(cmd[cmd.index('--audio-format') + 1], 'flac')

    def test_force_overwrites_existing_media(self):
        self.assertIn('--force-overwrites', self.command(['--force', 'url']))

    def test_container_also_remuxes_single_stream(self):
        self.assertIn('--remux-video', self.command(['-f', 'mp4', 'url']))

    def test_manual_and_auto_subtitles_both_requested(self):
        cmd = self.command(['--subs', '--auto-subs', 'url'])
        self.assertIn('--write-subs', cmd)
        self.assertIn('--write-auto-subs', cmd)

    def test_spawn_failure_returns_code(self):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            self.assertEqual(core.run(['/definitely/missing/fetchit-test']), 1)

    def test_equals_form_credentials_are_redacted(self):
        text = core.display_command(['yt-dlp', '--proxy=https://user:secret@host', '--password=hidden'])
        self.assertNotIn('secret', text); self.assertNotIn('hidden', text)

    def test_explicit_playlist_is_forwarded(self):
        self.assertIn('--yes-playlist', self.command(['--playlist', 'url']))
