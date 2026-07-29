"""Recent projects and files — read/write helpers."""
from __future__ import annotations

import json
import time
from pathlib import Path

RECENT_FILE = Path.home() / ".idol" / "recent.json"
_MAX = 10


def _load() -> dict:
    try:
        return json.loads(RECENT_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save(data: dict) -> None:
    try:
        RECENT_FILE.parent.mkdir(parents=True, exist_ok=True)
        RECENT_FILE.write_text(json.dumps(data, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_projects() -> list[dict]:
    return _load().get("projects", [])


def get_files() -> list[dict]:
    return _load().get("files", [])


def get_show_on_startup() -> bool:
    """Deprecated — the value moved to `utils.settings`.

    Kept as a delegating shim so no caller reads a stale copy out of
    `recent.json` after the migration. New code should read
    `settings.get("general.show_welcome_on_startup")` directly.
    """
    from utils import settings
    return bool(settings.get("general.show_welcome_on_startup"))


def set_show_on_startup(value: bool) -> None:
    """Deprecated — see `get_show_on_startup`."""
    from utils import settings
    settings.set("general.show_welcome_on_startup", bool(value))


def add_project(path: str) -> None:
    data = _load()
    projects = [p for p in data.get("projects", []) if p.get("path") != path]
    projects.insert(0, {
        "path": path,
        "name": Path(path).name,
        "ts": int(time.time()),
    })
    data["projects"] = projects[:_MAX]
    _save(data)


def add_file(path: str) -> None:
    data = _load()
    files = [f for f in data.get("files", []) if f.get("path") != path]
    files.insert(0, {
        "path": path,
        "name": Path(path).name,
        "ts": int(time.time()),
    })
    data["files"] = files[:_MAX]
    _save(data)


def remove_project(path: str) -> None:
    data = _load()
    data["projects"] = [p for p in data.get("projects", []) if p.get("path") != path]
    _save(data)


def remove_file(path: str) -> None:
    data = _load()
    data["files"] = [f for f in data.get("files", []) if f.get("path") != path]
    _save(data)
