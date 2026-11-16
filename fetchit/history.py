"""Download history: ~/.local/share/fetchit/history.json"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from .config import atomic_json

APP_NAME = "fetchit"
DATA_DIR = Path(
    os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share")
) / APP_NAME
HISTORY_FILE = DATA_DIR / "history.json"
LOG_FILE = DATA_DIR / "fetchit.log"


def _load() -> list:
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text())
        return [e for e in data if isinstance(e, dict)] if isinstance(data, list) else []
    except (ValueError, OSError):
        return []


def _save(entries: list) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    atomic_json(HISTORY_FILE, entries[-500:])


def add(url: str, title: str = "", status: str = "ok", extra: dict | None = None) -> None:
    entries = _load()
    entries.append(
        {
            "ts": datetime.now(timezone.utc).isoformat(),
            "url": url,
            "title": title,
            "status": status,
            **(extra or {}),
        }
    )
    _save(entries)


def show(limit: int = 20) -> str:
    if limit < 0:
        raise ValueError("history limit must be nonnegative")
    if limit == 0:
        return ""
    entries = _load()
    if not entries:
        return "no history yet."
    lines = []
    for e in entries[-limit:]:
        lines.append(f"{e.get('ts','?')}  [{e.get('status','?')}]  {e.get('title') or e.get('url')}")
        if e.get("title"):
            lines[-1] += f"\n    {e.get('url')}"
    return "\n".join(lines)


def clear() -> None:
    if HISTORY_FILE.exists():
        HISTORY_FILE.unlink()


def log(msg: str) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()
    with open(LOG_FILE, "a") as f:
        f.write(f"{ts} {msg}\n")
