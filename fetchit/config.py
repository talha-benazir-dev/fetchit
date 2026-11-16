"""Validated, atomic user settings (standard library only)."""
from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path

APP_NAME = 'fetchit'
CONFIG_DIR = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / APP_NAME
CONFIG_FILE = CONFIG_DIR / 'config.json'
QUALITIES = ('best', '2160', '1440', '1080', '720', '480', '360', '240', '144', 'worst')
CONTAINERS = ('mp4', 'mkv', 'webm', 'best')
AUDIO_FORMATS = ('mp3', 'm4a', 'opus', 'wav', 'flac', 'aac', 'vorbis', 'alac', 'best')
DEFAULTS = {
    'output_dir': str(Path.home() / 'Videos'), 'format': 'mp4', 'quality': 'best',
    'audio_format': 'mp3', 'audio_quality': '0', 'subs_lang': 'en',
    'concurrent_fragments': 4, 'retries': 10, 'embed_metadata': True,
    'embed_thumbnail': True,
}


def valid_value(key: str, value) -> bool:
    if key in ('embed_metadata', 'embed_thumbnail'):
        return type(value) is bool
    if key in ('concurrent_fragments', 'retries'):
        return type(value) is int and value >= (1 if key == 'concurrent_fragments' else 0)
    if not isinstance(value, str) or not value.strip() or any(ord(c) < 32 for c in value):
        return False
    if key == 'quality':
        return value.lower().removesuffix('p') in QUALITIES
    if key == 'format':
        return value.lower() in CONTAINERS
    if key == 'audio_format':
        return value.lower() in AUDIO_FORMATS
    if key == 'audio_quality':
        return bool(re.fullmatch(r'(?:10|[0-9]|[1-9][0-9]*[Kk])', value))
    return True


def validate_config(cfg: dict) -> dict:
    result = dict(cfg)
    for key, default in DEFAULTS.items():
        if not valid_value(key, result.get(key)):
            result[key] = default
    for key in ('quality', 'format', 'audio_format'):
        result[key] = result[key].lower().removesuffix('p') if key == 'quality' else result[key].lower()
    return result


def load_config() -> dict:
    try:
        user = json.loads(CONFIG_FILE.read_text(encoding='utf-8'))
    except (ValueError, OSError):
        user = {}
    return validate_config(user if isinstance(user, dict) else {})


def atomic_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    name = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         suffix='.tmp', delete=False) as file:
            name = file.name
            json.dump(data, file, indent=2, ensure_ascii=False)
            file.flush()
            os.fsync(file.fileno())
        os.replace(name, path)
    finally:
        if name and os.path.exists(name):
            os.unlink(name)


def save_config(cfg: dict) -> None:
    atomic_json(CONFIG_FILE, validate_config(cfg))


def show_config(cfg: dict) -> str:
    return '\n'.join([f'config file: {CONFIG_FILE}'] + [f'  {k} = {cfg[k]}' for k in sorted(cfg)])
