"""Theme loader for the canvas-rendered editor.

Themes live as `.json` files in the project-root `themes/` directory.
Each file is `<theme-id>.json`; the filename stem is the id used in
`load_theme(id)` and shown in `list_themes()`.

JSON shape:
    {
      "name":        "Display Name",       (optional, defaults to id)
      "description": "...",                (optional, used in tooltips)
      "palette": {
          "bg":              "#272822",
          "fg":              "#f8f8f2",
          ...               (see _PALETTE_KEYS for the full surface)
      },
      "tokens": {
          "comment": {"color": "#75715e", "italic": true},
          "string":  {"color": "#e6db74"},
          ...
      }
    }

`italic` is optional and defaults to `false`. The loader returns the
engine's expected internal shape:

    {
      "palette": dict[str, str],
      "tokens":  dict[str, tuple[str, bool]],   # (color, italic)
      "name":    str,
    }

Drop a new `themes/foo.json` and `list_themes()` picks it up — no
code change needed to add a theme.
"""
from __future__ import annotations

import json
from pathlib import Path

# Project root is two parents up from this file (utils/ → root).
_THEMES_DIR = Path(__file__).resolve().parent.parent / "themes"

# Process-wide cache so set_theme()/list_themes() don't re-parse JSON
# every time. Keys = theme id; values = the internal-shape dict the
# engine consumes. Invalidate with `_cache.clear()` if you hot-edit
# theme files during development.
_cache: dict[str, dict] = {}
_ids_cache: list[str] | None = None


def list_themes() -> list[str]:
    """Return all theme ids (filename stems) sorted alphabetically.
    Cached after first scan. Cheap to call from menu builders."""
    global _ids_cache
    if _ids_cache is not None:
        return list(_ids_cache)
    if not _THEMES_DIR.is_dir():
        _ids_cache = []
        return []
    _ids_cache = sorted(p.stem for p in _THEMES_DIR.glob("*.json"))
    return list(_ids_cache)


def load_theme(theme_id: str) -> dict:
    """Return the theme dict for *theme_id* in the engine's internal
    shape. Raises `FileNotFoundError` if the theme doesn't exist."""
    if theme_id in _cache:
        return _cache[theme_id]
    path = _THEMES_DIR / f"{theme_id}.json"
    if not path.is_file():
        raise FileNotFoundError(
            f"theme '{theme_id}' not found at {path}"
        )
    raw = json.loads(path.read_text(encoding="utf-8"))
    palette = dict(raw.get("palette") or {})
    tokens_raw = raw.get("tokens") or {}
    # Normalize {"color":..., "italic":...} → (color, italic) tuple
    # so the engine doesn't have to branch on shape at draw time.
    tokens: dict[str, tuple[str, bool]] = {}
    for cat, spec in tokens_raw.items():
        if isinstance(spec, dict):
            tokens[cat] = (
                str(spec.get("color", "")),
                bool(spec.get("italic", False)),
            )
        elif isinstance(spec, (list, tuple)) and len(spec) >= 1:
            # Tolerate the older `[color, italic]` shape too.
            tokens[cat] = (str(spec[0]), bool(spec[1]) if len(spec) > 1 else False)
        elif isinstance(spec, str):
            tokens[cat] = (spec, False)
    theme = {
        "name":    raw.get("name") or theme_id,
        "palette": palette,
        "tokens":  tokens,
    }
    _cache[theme_id] = theme
    return theme


def theme_name(theme_id: str) -> str:
    """Display name for *theme_id* — defaults to the id when the
    file omits a `name` field. Returns the id verbatim on lookup
    failure so menu rendering doesn't crash on bad input."""
    try:
        return load_theme(theme_id)["name"]
    except Exception:
        return theme_id
