"""Clipboard history persistence — one history per project, plus a scratch one.

Histories live under `~/.idol/clipboard/`, never inside the user's project
folder.  Clipboard text is whatever happened to be copied — snippets, tokens,
connection strings — and a file in the project root is a file that gets
committed.  Keeping it machine-local means a shared repo can't leak one
developer's clipboard.  The trade is that copying a project folder to another
machine doesn't bring its history along, which is the right way round.

Each project root gets its own file, named for a hash of the root path (paths
contain separators and casing that don't survive as filenames).  The root is
stored inside the file too, so the directory stays readable by hand.

Entries are plain dicts — `{text, source, ts, pinned}` — so the on-disk format
doesn't depend on the panel's dataclass.  Unknown keys are dropped on load and
a malformed file reads as empty rather than raising; a corrupt history is worth
losing silently, never worth blocking startup over.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

CLIP_DIR = Path.home() / ".idol" / "clipboard"

#: Ring depth for a project history.
PROJECT_MAX = 50
#: Ring depth with no project open.  Deliberately shallower — the scratch
#: history is a catch-all shared by every project-less session, so a smaller
#: window keeps it from filling with context the user has moved on from.
SCRATCH_MAX = 20

_SCRATCH_NAME = "_scratch.json"
_KEYS = ("text", "source", "ts", "pinned")


def max_for(root: str | None) -> int:
    """Ring depth for *root*'s history (None = the scratch history)."""
    return PROJECT_MAX if root else SCRATCH_MAX


def _key(root: str) -> str:
    """Stable filename stem for a project root.

    normcase + abspath so `C:\\Dev\\App`, `c:/dev/app`, and a trailing-slash
    variant all resolve to one history instead of three.
    """
    norm = os.path.normcase(os.path.abspath(root))
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]


def path_for(root: str | None) -> Path:
    """The history file backing *root*, or the scratch file when None."""
    return CLIP_DIR / (_SCRATCH_NAME if not root else f"{_key(root)}.json")


def _clean(raw) -> list[dict]:
    """Coerce loaded JSON into well-formed entries, dropping anything odd."""
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        text = item.get("text")
        if not isinstance(text, str) or not text.strip():
            continue
        out.append({
            "text":   text,
            "source": str(item.get("source") or ""),
            "ts":     str(item.get("ts") or ""),
            "pinned": bool(item.get("pinned")),
        })
    return out


def load(root: str | None) -> list[dict]:
    """Read *root*'s history, newest first.  Missing or broken file → []."""
    try:
        data = json.loads(path_for(root).read_text(encoding="utf-8"))
    except Exception:
        return []
    entries = _clean(data.get("entries") if isinstance(data, dict) else data)
    return entries[:max_for(root)]


def save(root: str | None, entries: list[dict]) -> None:
    """Write *entries* as *root*'s history, trimmed to the ring depth.

    Writing an empty history removes the file instead of leaving an empty one
    behind, so clearing a project's history doesn't leave a permanent entry in
    the directory for a project the user may never open again.
    """
    entries = _clean(entries)[:max_for(root)]
    target = path_for(root)
    try:
        if not entries:
            target.unlink(missing_ok=True)
            return
        CLIP_DIR.mkdir(parents=True, exist_ok=True)
        payload = {"root": str(root) if root else "", "entries": entries}
        target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    except Exception:
        pass


__all__ = [
    "CLIP_DIR", "PROJECT_MAX", "SCRATCH_MAX",
    "max_for", "path_for", "load", "save",
]
