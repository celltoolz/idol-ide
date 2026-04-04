"""Session and workspace persistence helpers."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import Notepad

# Auto-session lives in ~/.notepad_ide/session.json
SESSION_FILE = Path.home() / ".notepad_ide" / "session.json"


def save(app: "Notepad", filepath: str | Path | None = None) -> None:
    """Serialise open tabs, explorer root, and sash layout to *filepath*.

    Saves to SESSION_FILE when no path is given (auto-session).
    For files that exist on disk, only the path is stored. For unsaved / dirty
    tabs the content is embedded directly so no work is lost.
    """
    target = Path(filepath) if filepath else SESSION_FILE
    target.parent.mkdir(parents=True, exist_ok=True)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs_data = []
    for tab_id in app.notebook.tabs():
        cv = app._codeviews.get(tab_id)
        if cv is None:
            continue
        fp    = app._files.get(tab_id)
        title = app._titles.get(tab_id, "Untitled")
        dirty = app._dirty.get(tab_id, False)

        entry: dict = {"title": title, "filepath": fp}
        if fp is None or dirty:
            entry["content"] = cv.get("1.0", "end-1c")
        tabs_data.append(entry)

    active_index = 0
    try:
        active_index = list(app.notebook.tabs()).index(app.notebook.select())
    except (ValueError, Exception):
        pass

    # ── Appearance ────────────────────────────────────────────────────────────
    appearance: dict = {
        "theme":            app.theme_var.get(),
        "minimap_visible":  app.minimap_visible_var.get(),
    }
    # Grab the font from the active codeview (all tabs share the same font)
    cv_any = next((cv for cv in app._codeviews.values() if cv is not None), None)
    if cv_any is not None:
        try:
            appearance["font"] = cv_any.cget("font")
        except Exception:
            pass

    # ── Layout ────────────────────────────────────────────────────────────────
    layout: dict = {}
    try:
        layout["h_sash"] = app._h_pane.sashpos(0)
    except Exception:
        pass
    try:
        layout["v_sash"] = app._v_pane.sashpos(0)
    except Exception:
        pass
    sb = app._sidebar
    layout["sidebar_sash1"]       = sb._sash1_y
    layout["sidebar_sash2"]       = sb._sash2_y
    layout["sidebar_sash3"]       = sb._sash3_y
    layout["outline_collapsed"]   = sb._outline_collapsed
    layout["refs_collapsed"]      = sb._refs_collapsed
    layout["refs_visible"]        = sb._refs_visible
    layout["sc_collapsed"]        = sb._sc_collapsed
    layout["sc_visible"]          = sb._sc_visible
    layout["explorer_collapsed"]  = sb._explorer_collapsed

    explorer_root = str(app._sidebar.explorer._root or os.getcwd())

    try:
        target.write_text(
            json.dumps(
                {
                    "tabs":          tabs_data,
                    "active_index":  active_index,
                    "explorer_root": explorer_root,
                    "layout":        layout,
                    "appearance":    appearance,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def restore(app: "Notepad", filepath: str | Path | None = None) -> bool:
    """Restore tabs, layout, and explorer root from *filepath* (or SESSION_FILE).
    Returns True if anything was loaded.
    """
    target = Path(filepath) if filepath else SESSION_FILE
    if not target.exists():
        return False

    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except Exception:
        return False

    tabs = data.get("tabs", [])
    if not tabs:
        return False

    # ── Tabs ─────────────────────────────────────────────────────────────────
    for entry in tabs:
        fp      = entry.get("filepath")
        title   = entry.get("title", "Untitled")
        content = entry.get("content")

        if fp and os.path.isfile(fp):
            try:
                file_content = Path(fp).read_text(encoding="utf-8")
                app._new_tab(title, file_content, filepath=fp)
            except Exception:
                continue
        elif content is not None:
            app._new_tab(title, content, filepath=fp if fp else None)

    tabs_list = app.notebook.tabs()
    active = data.get("active_index", 0)
    if 0 <= active < len(tabs_list):
        app.notebook.select(tabs_list[active])

    # ── Explorer root ─────────────────────────────────────────────────────────
    root = data.get("explorer_root")
    if root and os.path.isdir(root):
        app._sidebar.explorer.set_root(root)

    # ── Appearance ────────────────────────────────────────────────────────────
    appearance = data.get("appearance", {})
    theme = appearance.get("theme")
    if theme:
        app.theme_var.set(theme)
        app.view_change_theme()
    font = appearance.get("font")
    if font:
        for cv in app._codeviews.values():
            if cv is None:
                continue
            try:
                cv.configure(font=font)
            except Exception:
                pass

    minimap = appearance.get("minimap_visible", True)
    app.minimap_visible_var.set(minimap)
    app.view_toggle_minimap()

    # ── Layout — must wait until widgets have real pixel dimensions ───────────
    layout = data.get("layout")
    if layout:
        app.after(50, lambda: _apply_layout(app, layout))

    return True


def _apply_layout(app: "Notepad", layout: dict) -> None:
    """Apply saved sash positions after the window is fully rendered."""
    app.update_idletasks()

    h = layout.get("h_sash")
    if h is not None:
        try:
            app._h_pane.sashpos(0, h)
        except Exception:
            pass

    v = layout.get("v_sash")
    if v is not None:
        try:
            app._v_pane.sashpos(0, v)
        except Exception:
            pass

    sb = app._sidebar
    if layout.get("outline_collapsed") and not sb._outline_collapsed:
        sb._toggle_outline()
    if layout.get("explorer_collapsed") and not sb._explorer_collapsed:
        sb._toggle_explorer()
    if layout.get("refs_collapsed") and not sb._refs_collapsed:
        sb._toggle_refs()
    if layout.get("refs_visible"):
        sb._refs_visible = True
    if layout.get("sc_visible"):
        sb._sc_visible = True
    if layout.get("sc_collapsed") and not sb._sc_collapsed:
        sb._toggle_sc()

    if layout.get("sidebar_sash1"):
        sb._sash1_y = layout["sidebar_sash1"]
    if layout.get("sidebar_sash2"):
        sb._sash2_y = layout["sidebar_sash2"]
    if layout.get("sidebar_sash3"):
        sb._sash3_y = layout["sidebar_sash3"]
    sb._relayout()
