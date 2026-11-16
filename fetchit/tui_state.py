"""Terminal-independent forms, editing, and navigation."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass
import re
import unicodedata
from urllib.parse import urlparse

from . import config, core
from .ui import make_args

SCREENS = ('video', 'audio', 'playlist', 'search', 'batch', 'history', 'settings')
LABELS = ('Video', 'Audio', 'Playlist', 'Search', 'Batch', 'History', 'Settings')
ESCAPES = re.compile(r'\x1b(?:\][^\x07\x1b]*(?:\x07|\x1b\\)|\[[0-?]*[ -/]*[@-~])')


def safe_text(value: str) -> str:
    value = ESCAPES.sub('', str(value))
    return ''.join(' ' if c in '\r\n\t' else c for c in value
                   if c in '\r\n\t' or not unicodedata.category(c).startswith('C'))


@dataclass
class Field:
    key: str
    label: str
    value: str
    choices: tuple[str, ...] = ()
    cursor: int = -1

    def __post_init__(self):
        if self.cursor < 0:
            self.cursor = len(self.value)

    def edit(self, key: str) -> None:
        if self.choices:
            if key in ('left', 'right', ' ', 'enter'):
                i = self.choices.index(self.value)
                self.value = self.choices[(i + (-1 if key == 'left' else 1)) % len(self.choices)]
            return
        self.cursor = min(self.cursor, len(self.value))
        if key == 'left': self.cursor = max(0, self.cursor - 1)
        elif key == 'right': self.cursor = min(len(self.value), self.cursor + 1)
        elif key == 'home': self.cursor = 0
        elif key == 'end': self.cursor = len(self.value)
        elif key == 'clear': self.value = ''; self.cursor = 0
        elif key == 'backspace' and self.cursor:
            self.value = self.value[:self.cursor - 1] + self.value[self.cursor:]
            self.cursor -= 1
        elif key == 'delete':
            self.value = self.value[:self.cursor] + self.value[self.cursor + 1:]
        elif len(key) == 1 and key.isprintable() and len(self.value) < 8192:
            self.value = self.value[:self.cursor] + key + self.value[self.cursor:]
            self.cursor += 1


class AppState:
    def __init__(self, cfg: dict, dry_run: bool = False):
        self.cfg = config.validate_config(cfg)
        self.dry_run = dry_run
        self.screen = 'video'
        self.focus = -1
        self.status = 'Paste a link to get started.'
        self.error = False
        self.busy = False
        self.confirm_clear = False
        self.results = []
        self.history_entries = []
        self.logs = deque(maxlen=80)
        self.progress = {'percent': None, 'speed': '', 'eta': ''}
        self.job_label = 'Ready for your next download'
        self.job_target = ''
        self.job_outcome = ''
        self._drafts = {}
        self.fields = self._fields('video')

    def _fields(self, screen: str) -> list[Field]:
        c = self.cfg
        url = Field('url', 'Video or playlist URL', '')
        quality = Field('quality', 'Video quality', c['quality'], config.QUALITIES)
        container = Field('format', 'Container', c['format'], config.CONTAINERS)
        folder = Field('output_dir', 'Save to', c['output_dir'])
        audio = Field('audio_format', 'Audio format', c['audio_format'], config.AUDIO_FORMATS)
        audio_quality = Field('audio_quality', 'Audio quality (0–10 or bitrate, e.g. 192K)', c['audio_quality'])
        if screen == 'video':
            return [url, quality, container, Field('subs', 'Download subtitles', 'off', ('off', 'on')),
                    Field('subs_lang', 'Subtitle languages', c['subs_lang']),
                    Field('sponsorblock', 'Remove sponsors', 'off', ('off', 'remove')), folder]
        if screen == 'audio': return [url, audio, audio_quality, folder]
        if screen == 'playlist': return [url, Field('playlist_items', 'Items (blank for all, e.g. 1-5)', ''), quality, container, folder]
        if screen == 'search': return [Field('query', 'Search YouTube', ''), Field('limit', 'Results (1–50)', '5')]
        if screen == 'batch':
            return [Field('batch_file', 'URL file path', ''), Field('mode', 'Download as', 'video', ('video', 'audio')),
                    quality, container, audio, audio_quality, folder]
        if screen == 'settings':
            return [folder, quality, container, audio, audio_quality, Field('subs_lang', 'Subtitle languages', c['subs_lang']),
                    Field('retries', 'Retries', str(c['retries'])),
                    Field('concurrent_fragments', 'Concurrent fragments', str(c['concurrent_fragments'])),
                    Field('embed_metadata', 'Embed metadata', 'on' if c['embed_metadata'] else 'off', ('off', 'on')),
                    Field('embed_thumbnail', 'Embed thumbnail', 'on' if c['embed_thumbnail'] else 'off', ('off', 'on'))]
        return []

    def select_screen(self, screen: str) -> None:
        self._drafts[self.screen] = self.fields
        self.screen = screen
        self.fields = self._drafts.get(screen) or self._fields(screen)
        self.focus = -1
        self.confirm_clear = False

    def refresh_defaults(self, cfg: dict) -> None:
        self.cfg = config.validate_config(cfg)
        self._drafts.clear()
        self.fields = self._fields(self.screen)
        self.focus = -1

    def navigate(self, key: str) -> str | None:
        if self.confirm_clear:
            if key in ('y', 'Y'):
                self.confirm_clear = False
                return 'clear_history'
            if key in ('n', 'N', 'escape'):
                self.confirm_clear = False
            return None
        if key == 'cancel': return 'cancel'
        if key == 'escape':
            if self.screen == 'search' and self.results and self.focus >= 0:
                self.results = []
            self.focus = -1
            return None
        results = self.screen == 'search' and bool(self.results)
        count = len(self.results) if results else len(self.history_entries) + 1 if self.screen == 'history' else len(self.fields) + 1
        if key in ('tab', 'backtab'):
            self.focus = (self.focus + (1 if key == 'tab' else -1) + 1) % (count + 1) - 1
            return None
        if self.focus == -1:
            if key in ('q', 'Q'): return 'quit'
            if key in ('up', 'down', 'left', 'right'):
                i = SCREENS.index(self.screen)
                self.select_screen(SCREENS[(i + (-1 if key in ('up', 'left') else 1)) % len(SCREENS)])
            elif key in '1234567' and len(key) == 1:
                self.select_screen(SCREENS[int(key) - 1])
            elif key == 'enter': self.focus = 0
            return None
        if key in ('up', 'down'):
            self.focus = (self.focus + (-1 if key == 'up' else 1)) % count
            return None
        if results:
            if key == 'enter':
                url = self.results[self.focus]['url']
                self.select_screen('video')
                self.fields[0].value = url; self.fields[0].cursor = len(url)
                self.focus = 1
                self.status = 'Choose quality, then start download.'
            return None
        if self.screen == 'history':
            if key == 'enter' and self.focus == len(self.history_entries):
                self.confirm_clear = True
            return None
        if self.focus == len(self.fields):
            if key == 'enter': return 'save' if self.screen == 'settings' else 'search' if self.screen == 'search' else 'download'
            return None
        if key == 'enter' and not self.fields[self.focus].choices:
            self.focus = min(len(self.fields), self.focus + 1)
        else:
            self.fields[self.focus].edit(key)
        return None

    def download_args(self):
        args = make_args(self.cfg)
        args.dry_run = self.dry_run
        for field in self.fields:
            value = field.value.strip()
            if field.key == 'url': args.url = [value] if value else []
            elif field.key == 'subs': args.subs = args.embed_subs = value == 'on'
            elif field.key == 'mode': args.audio_only = value == 'audio'
            elif field.key != 'query' and field.key != 'limit': setattr(args, field.key, value or None)
        if self.screen == 'audio': args.audio_only = True
        if args.url:
            url = urlparse(args.url[0])
            if url.scheme not in ('https', 'http') or not url.netloc or any(c.isspace() for c in args.url[0]):
                raise ValueError('Enter a complete http:// or https:// URL.')
        if not args.url and not args.batch_file:
            raise ValueError('Enter a URL or a batch file path.')
        core.validate_options(args, self.cfg)
        return args

    def settings_values(self) -> dict:
        cfg = dict(self.cfg)
        for field in self.fields:
            value = field.value.strip()
            if field.key in ('embed_metadata', 'embed_thumbnail'): value = value == 'on'
            elif field.key in ('retries', 'concurrent_fragments'):
                try: value = int(value)
                except ValueError: raise ValueError(f'{field.label} must be a number.') from None
            if not config.valid_value(field.key, value):
                raise ValueError(f'Invalid {field.label.lower()}.')
            cfg[field.key] = value
        return config.validate_config(cfg)
