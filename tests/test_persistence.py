import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from fetchit import config, history


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        for mod, directory, file in ((config, 'CONFIG_DIR', 'CONFIG_FILE'),
                                     (history, 'DATA_DIR', 'HISTORY_FILE')):
            p = patch.object(mod, directory, root)
            p.start(); self.addCleanup(p.stop)
            p = patch.object(mod, file, root / (file + '.json'))
            p.start(); self.addCleanup(p.stop)

    def test_invalid_config_values_fall_back(self):
        config.CONFIG_FILE.write_text(json.dumps({'output_dir': None, 'quality': 42,
            'concurrent_fragments': -1, 'retries': -1, 'format': 'bad', 'embed_metadata': 'false'}))
        cfg = config.load_config()
        for key in config.DEFAULTS:
            self.assertEqual(cfg[key], config.DEFAULTS[key], key)

    def test_malformed_history_rows_are_skipped(self):
        history.HISTORY_FILE.write_text('[null, 3, "bad", {"url":"valid","status":"ok"}]')
        self.assertIn('valid', history.show())
        self.assertEqual(len(history._load()), 1)

    def test_zero_history_limit_is_empty(self):
        history.add('example')
        self.assertEqual(history.show(0), '')

    def test_negative_history_limit_rejected(self):
        with self.assertRaises(ValueError):
            history.show(-1)

    def test_atomic_write_preserves_existing_file(self):
        config.save_config(config.DEFAULTS)
        before = config.CONFIG_FILE.read_text()
        with patch('os.replace', side_effect=OSError('disk failure')):
            with self.assertRaises(OSError):
                config.save_config({**config.DEFAULTS, 'quality': '720'})
        self.assertEqual(config.CONFIG_FILE.read_text(), before)
        self.assertEqual(list(Path(self.tmp.name).glob('*.tmp')), [])

    def test_invalid_json_is_tolerated(self):
        config.CONFIG_FILE.write_text('{')
        history.HISTORY_FILE.write_text('{')
        self.assertEqual(config.load_config(), config.DEFAULTS)
        self.assertEqual(history._load(), [])

    def test_invalid_history_encoding_is_tolerated(self):
        history.HISTORY_FILE.write_bytes(b'\xff')
        self.assertEqual(history._load(), [])
