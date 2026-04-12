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
        h = app._h_pane.sashpos(0)
        if h > 50:  # only save valid non-collapsed positions
            layout["h_sash"] = h
    except Exception:
        pass
    try:
        v = app._v_pane.sashpos(0)
        if v > 0:  # skip if widget is being torn down
            layout["v_sash"] = v
    except Exception:
        pass
    sb = app._sidebar
    # Only save sash heights that are large enough to be meaningful — zero or
    # near-zero values (from a race-condition layout) must not be persisted or
    # they will override the seeding logic on the next launch.
    _MS = 40   # mirrors _MIN_SASH used in restore
    if sb._sash1_y >= _MS: layout["sidebar_sash1"] = sb._sash1_y
    if sb._sash2_y >= _MS: layout["sidebar_sash2"] = sb._sash2_y
    if sb._sash3_y >= _MS: layout["sidebar_sash3"] = sb._sash3_y
    if sb._sash4_y >= _MS: layout["sidebar_sash4"] = sb._sash4_y
    layout["outline_collapsed"]   = sb._outline_collapsed
    layout["refs_collapsed"]      = sb._refs_collapsed
    layout["refs_visible"]        = sb._refs_visible
    layout["sc_collapsed"]        = sb._sc_collapsed
    layout["sc_visible"]          = sb._sc_visible
    layout["explorer_collapsed"]  = sb._explorer_collapsed

    # AI panel
    from utils import ollama_client
    layout["ollama_url"] = ollama_client.get_base_url()
    layout["ai_panel_visible"] = app._ai_panel_visible
    if app._ai_panel_visible:
        try:
            total = app._h_pane.winfo_width()
            sash  = app._h_pane.sashpos(1)
            layout["ai_panel_width"] = max(280, total - sash)
        except Exception:
            layout["ai_panel_width"] = app._ai_panel_width
    else:
        layout["ai_panel_width"] = app._ai_panel_width

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
        app._set_explorer_root(root)

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

    # ── Layout — two-stage to let pane geometry settle before sidebar measures ──
    layout = data.get("layout")
    if layout:
        # Stage 1 (50 ms): set h_pane / v_pane sash positions so the sidebar
        # and editor panels get their correct pixel dimensions.
        app.after(50,  lambda: _apply_pane_sashes(app, layout))
        # Stage 2 (250 ms): by now the pane geometry has propagated; apply the
        # sidebar collapse states, sash heights, and relayout.
        app.after(250, lambda: _apply_sidebar_layout(app, layout))

    return True


_MIN_SASH = 40   # px — below this a saved sash value is considered corrupt


def _apply_pane_sashes(app: "Notepad", layout: dict) -> None:
    """Stage 1 — restore h_pane and v_pane sash positions only."""
    h = layout.get("h_sash")
    if h and h > 50:
        try:
            app._h_pane.sashpos(0, h)
        except Exception:
            pass

    v = layout.get("v_sash")
    if v is not None and v > 0:
        try:
            app._v_pane.sashpos(0, v)
        except Exception:
            pass

    # Restore Ollama URL if customized
    if layout.get("ollama_url"):
        from utils import ollama_client
        ollama_client.set_base_url(layout["ollama_url"])
        if hasattr(app, "_ai_chat_panel"):
            app._ai_chat_panel._url_var.set(ollama_client.get_base_url())

    # AI panel — show it if it was visible; sash follows via _apply_ai_panel_sash
    if layout.get("ai_panel_visible"):
        w = layout.get("ai_panel_width", 350)
        app._ai_panel_width = max(280, w)
        if not app._ai_panel_visible:
            app.view_ai_chat()


def _apply_sidebar_layout(app: "Notepad", layout: dict) -> None:
    """Stage 2 — restore sidebar collapse states, panel heights, and relayout.

    Called 250 ms after restore so the pane geometry from stage 1 has had
    time to propagate; winfo_height() will now return real pixel dimensions.
    """
    sb = app._sidebar

    # Restore collapse states before sash heights so _relayout sees them
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

    # Validate sash heights — corrupt/cross-platform values are discarded so
    # the seeding logic in _do_relayout fills them with sensible defaults.
    s1 = layout.get("sidebar_sash1", 0)
    s2 = layout.get("sidebar_sash2", 0)
    s3 = layout.get("sidebar_sash3", 0)
    s4 = layout.get("sidebar_sash4", 0)
    if s1 >= _MIN_SASH:
        sb._sash1_y = s1
    if s2 >= _MIN_SASH:
        sb._sash2_y = s2
    if s3 >= _MIN_SASH:
        sb._sash3_y = s3
    if s4 >= _MIN_SASH:
        sb._sash4_y = s4

    sb._relayout()


# keep the old name alive so any external callers aren't broken
def _apply_layout(app: "Notepad", layout: dict) -> None:
    _apply_pane_sashes(app, layout)
    _apply_sidebar_layout(app, layout)
