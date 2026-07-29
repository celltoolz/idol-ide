"""User preferences — the store behind the Settings panel.

**Scope is the rule this module exists to enforce.** IDOL keeps state in three
places and they answer different questions:

* **Preference** — "how do I like my IDE?" Lives here, follows the *user*
  across every project.
* **Workspace state** — "what was I doing here?" Lives in `.idol-project` /
  `session.json` (see `utils/session.py`), follows the *project*: open tabs,
  sash positions, the run configuration, designer state.
* **Project config** — "how is this codebase built?" Lives in files in the repo
  (`ruff.toml`, `environment.yml`), follows the *code* into git. Settings must
  **edit** those files, never mirror them here — two sources of truth for lint
  config is how the same rule ends up meaning two things.

Preferences used to be filed as workspace state, which had a real consequence:
`session.restore()` applies `appearance.theme` and `appearance.font` from
whichever file it reads, so opening a project silently changed the user's theme
and editor font to whatever that project last had. `migrate_from_session`
moves them out, once.

The schema is the single source of truth. Add a `Setting` and it gets a
default, a type, a home in the panel, and a place in the file — the same way a
`HandlerDef` is all the designer needs to gain a handler.
"""
from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

SETTINGS_FILE = Path.home() / ".idol" / "settings.json"

#: Bumped only when a migration needs to run. Stored under `_version`.
_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Setting:
    """One preference: what it is, what it defaults to, where it belongs."""

    key: str                      # dotted, e.g. "editor.font"
    default: Any
    kind: str                     # bool | int | str | choice | color | font
    section: str                  # panel category, e.g. "Editor"
    label: str                    # row label in the panel
    description: str = ""         # one line under the label
    #: kind="choice" — a tuple, or a zero-arg callable for options that are
    #: only known at runtime. Themes are files in `themes/`, so hardcoding
    #: them here would mean dropping in a JSON no longer being enough.
    choices: tuple | Callable[[], tuple] = ()
    minimum: int | None = None    # kind="int"
    maximum: int | None = None
    #: Restart needed for this to take effect. Nothing sets it yet; the panel
    #: will show a hint rather than pretending a change applied.
    needs_restart: bool = False


#: Declared order is the order the panel renders.
SCHEMA: tuple[Setting, ...] = (
    Setting(
        key="appearance.theme", default="monokai-bright", kind="choice",
        section="Appearance", label="Theme",
        description="Editor and sidebar colour scheme.",
        choices=lambda: tuple(_theme_ids()),
    ),
    Setting(
        key="editor.font", default=None, kind="font",
        section="Editor", label="Font",
        description="Family, size and style for every editor tab. "
                    "Unset uses the editor's built-in default.",
    ),
    Setting(
        key="editor.minimap_visible", default=True, kind="bool",
        section="Editor", label="Show minimap",
        description="The scaled overview down the right edge of the editor.",
    ),
    Setting(
        key="ai.ollama_url", default="http://localhost:11434", kind="str",
        section="AI", label="Ollama server URL",
        description="Where the AI chat panel looks for a local Ollama server.",
    ),
)

_BY_KEY: dict[str, Setting] = {s.key: s for s in SCHEMA}


def _theme_ids() -> list[str]:
    """Bundled theme ids. Imported lazily — `theme_loader` reads the themes
    directory, and this module is imported long before that matters."""
    try:
        from utils.theme_loader import list_themes
        return list(list_themes())
    except Exception:
        return ["monokai-bright"]


def choices_for(setting: Setting) -> tuple:
    """Resolve a Setting's choices, calling the provider when it has one."""
    raw = setting.choices
    if callable(raw):
        try:
            return tuple(raw())
        except Exception:
            return ()
    return tuple(raw)


def get_setting(key: str) -> Setting | None:
    return _BY_KEY.get(key)


def schema() -> tuple[Setting, ...]:
    return SCHEMA


def sections() -> list[str]:
    """Panel categories, in declared order, de-duplicated."""
    out: list[str] = []
    for s in SCHEMA:
        if s.section not in out:
            out.append(s.section)
    return out


def settings_in(section: str) -> list[Setting]:
    return [s for s in SCHEMA if s.section == section]


def default_for(key: str) -> Any:
    s = _BY_KEY.get(key)
    return s.default if s else None


# ── Storage ───────────────────────────────────────────────────────────────────

_lock = threading.RLock()
_cache: dict | None = None


def _load() -> dict:
    global _cache
    with _lock:
        if _cache is None:
            try:
                data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
                _cache = data if isinstance(data, dict) else {}
            except Exception:
                _cache = {}
        return _cache


def _flush() -> None:
    with _lock:
        data = _cache or {}
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            SETTINGS_FILE.write_text(json.dumps(data, indent=2, sort_keys=True),
                                     encoding="utf-8")
        except Exception:
            pass


def reload() -> None:
    """Drop the cache so the next read comes from disk. For tests."""
    global _cache
    with _lock:
        _cache = None


# ── Change notification ───────────────────────────────────────────────────────

_listeners: list[Callable[[str, Any], None]] = []


def subscribe(callback: Callable[[str, Any], None]) -> Callable[[], None]:
    """Call *callback(key, value)* after any change. Returns an unsubscribe.

    This is what makes "apply live" possible without every consumer polling
    the file or the panel knowing who cares about which key.
    """
    _listeners.append(callback)

    def _unsubscribe() -> None:
        try:
            _listeners.remove(callback)
        except ValueError:
            pass

    return _unsubscribe


def _notify(key: str, value: Any) -> None:
    for cb in list(_listeners):
        try:
            cb(key, value)
        except Exception:
            pass        # a broken listener must not break the write


# ── Public API ────────────────────────────────────────────────────────────────

def get(key: str, default=None):
    """Read *key*.

    Falls back to the schema default, then to *default*. Keys outside the
    schema are allowed and simply have no default — `interpreter:<root>` and
    friends predate the schema and are still stored here.
    """
    data = _load()
    if key in data:
        return data[key]
    if key in _BY_KEY:
        return _BY_KEY[key].default
    return default


def set(key: str, value) -> None:
    """Write *key* and notify listeners. No-op when the value is unchanged."""
    with _lock:
        data = _load()
        if key in data and data[key] == value:
            return
        data[key] = value
        _flush()
    _notify(key, value)


def reset(key: str) -> None:
    """Remove any stored value so *key* falls back to its schema default."""
    with _lock:
        data = _load()
        if key not in data:
            return
        del data[key]
        _flush()
    _notify(key, default_for(key))


def is_default(key: str) -> bool:
    return key not in _load()


# ── Migration ─────────────────────────────────────────────────────────────────

#: (settings key, where it used to live in a session file)
_SESSION_MIGRATIONS = (
    ("appearance.theme",          ("appearance", "theme")),
    ("editor.font",               ("appearance", "font")),
    ("editor.minimap_visible",    ("appearance", "minimap_visible")),
    ("ai.ollama_url",             ("layout", "ollama_url")),
)


def migrate_from_session(session_path: Path | None = None) -> bool:
    """Move preferences out of the auto-session into this store, once.

    Reads the *auto-session* only (`~/.idol/session.json`), never a project
    file — a project's copy is exactly the leak being fixed, and picking a
    project's theme as the user's would just make the last-opened project win
    permanently.

    Runs once, guarded by `_version`. Already-set keys are never overwritten,
    so a user who has configured something new keeps it.

    Returns True when it did something, for logging and tests.
    """
    with _lock:
        data = _load()
        if data.get("_version", 0) >= _SCHEMA_VERSION:
            return False

    path = session_path or (Path.home() / ".idol" / "session.json")
    try:
        session = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        session = {}

    moved = False
    for key, (block, field_name) in _SESSION_MIGRATIONS:
        if not is_default(key):
            continue                    # user already set it here; leave alone
        value = (session.get(block) or {}).get(field_name)
        if value is None:
            continue
        set(key, value)
        moved = True

    with _lock:
        _load()["_version"] = _SCHEMA_VERSION
        _flush()
    return moved


# ── Convenience for the editor font ───────────────────────────────────────────

def get_editor_font() -> tuple[str, int, str, str] | None:
    """`editor.font` as a 4-tuple, or None when unset/malformed.

    Stored as a JSON list; callers want `(family, size, weight, slant)` and
    should not each re-validate a hand-edited file.
    """
    raw = get("editor.font")
    if not isinstance(raw, (list, tuple)) or len(raw) < 2:
        return None
    try:
        family = str(raw[0])
        size = int(raw[1])
    except (TypeError, ValueError):
        return None
    weight = str(raw[2]) if len(raw) > 2 else "normal"
    slant = str(raw[3]) if len(raw) > 3 else "roman"
    return family, size, weight, slant


def set_editor_font(family: str, size: int, weight: str = "normal",
                    slant: str = "roman") -> None:
    set("editor.font", [family, int(size), weight, slant])


__all__ = [
    "SETTINGS_FILE", "Setting", "SCHEMA",
    "schema", "sections", "settings_in", "default_for", "choices_for",
    "get_setting",
    "get", "set", "reset", "is_default", "reload", "subscribe",
    "migrate_from_session", "get_editor_font", "set_editor_font",
]
