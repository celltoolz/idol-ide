"""Persistent IDE settings — small key/value store independent of sessions."""
from __future__ import annotations

import json
from pathlib import Path

_SETTINGS_FILE = Path.home() / ".idol" / "settings.json"


def _load() -> dict:
    try:
        return json.loads(_SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def get(key: str, default=None):
    return _load().get(key, default)


def set(key: str, value) -> None:
    data = _load()
    data[key] = value
    _SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    try:
        _SETTINGS_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass
