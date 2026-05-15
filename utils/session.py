"""Session and workspace persistence helpers."""
from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from app import IDOL

# Auto-session lives in ~/.idol/session.json
SESSION_FILE = Path.home() / ".idol" / "session.json"
# Unsaved content is written here so it survives across restarts
TMP_DIR = Path.home() / ".idol" / "tmp"


def peek_layout(filepath: str | Path | None = None) -> dict:
    """Read just the layout block from a session file without any side effects.

    Used at startup to pre-size panes before the layout is built so there is
    no visible sash jump when the full restore fires 50 ms later.
    """
    path = Path(filepath) if filepath else SESSION_FILE
    try:
        return json.loads(path.read_text(encoding="utf-8")).get("layout", {})
    except Exception:
        return {}


def save(app: "IDOL", filepath: str | Path | None = None) -> None:
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

        if dirty and fp and Path(fp).is_file():
            # Verify the dirty flag isn't spurious — if content matches disk,
            # treat the tab as clean so it doesn't come back as unsaved on restore.
            try:
                cur = (cv.get_text() if hasattr(cv, "get_text")
                       else cv.get("1.0", "end-1c"))
                if cur == Path(fp).read_text(encoding="utf-8"):
                    dirty = False
            except Exception:
                pass

        if dirty:
            # Write unsaved content to a temp file so the session JSON stays
            # small and the content survives restarts without a save prompt.
            # Duck-type the editor so both `CodeView` (tk.Text) and the
            # canvas-rendered `CanvasCodeView` (explicit `get_text`)
            # work — utils/ can't import from widgets/ per project rules.
            content = (cv.get_text() if hasattr(cv, "get_text")
                       else cv.get("1.0", "end-1c"))
            existing = app._temp_files.get(tab_id)
            if existing:
                tmp_path = Path(existing)
            else:
                ext = Path(fp).suffix if fp else ".py"
                TMP_DIR.mkdir(parents=True, exist_ok=True)
                tmp_path = TMP_DIR / f"idol_tmp_{uuid.uuid4().hex[:12]}{ext}"
                app._temp_files[tab_id] = str(tmp_path)
            try:
                tmp_path.write_text(content, encoding="utf-8")
                entry["temp_file"] = str(tmp_path)
            except Exception:
                entry["content"] = content  # fallback if write fails
        elif fp is None:
            # New empty tab — embed the (likely empty) content directly
            entry["content"] = (cv.get_text() if hasattr(cv, "get_text")
                                else cv.get("1.0", "end-1c"))

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
    # Persist the editor font (family, size, weight, slant) set via View > Change Font.
    if getattr(app, "_editor_font", None):
        appearance["font"] = list(app._editor_font)

    # ── Layout ────────────────────────────────────────────────────────────────
    layout: dict = {}

    # ── Window state (maximize/fullscreen — position is not restored) ────────
    try:
        if sys.platform.startswith("linux"):
            # Use the continuously-tracked flag — reading attributes("-zoomed")
            # at close time is unreliable on X11 due to event-queue lag.
            layout["window_maximized"] = bool(getattr(app, "_window_maximized", False))
        else:
            state = app.wm_state()
            is_maximized = (state == "zoomed")
            try:
                is_maximized = is_maximized or bool(int(app.attributes("-zoomed")))
            except Exception:
                pass
            layout["window_maximized"] = is_maximized
    except Exception:
        pass
    # macOS: green button enters native fullscreen, not "zoomed" state
    if sys.platform == "darwin":
        try:
            layout["window_fullscreen"] = bool(app.wm_attributes("-fullscreen"))
        except Exception:
            pass
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

    # Run preferences (target: output/terminal; action: run/debug; entry file)
    layout["run_target"] = app._run_target_var.get()
    layout["run_action"] = app._run_action_var.get()
    layout["run_entry"] = getattr(app, "_run_entry_file", "") or ""

    # Designer
    layout["designer_project_type"] = getattr(app, "_designer_project_type", "cli")
    layout["designer_mode_active"]  = getattr(app, "_designer_mode", False)
    # Save live sash widths if in designer mode, otherwise use the stored values.
    if getattr(app, "_designer_mode", False):
        try:
            w = app._designer_left_pane.winfo_width()
            if w > 50:
                layout["designer_palette_width"] = w
        except Exception:
            pass
        try:
            w = app._props_panel.winfo_width()
            if w > 50:
                layout["designer_props_width"] = w
        except Exception:
            pass
    else:
        pw = getattr(app, "_designer_palette_width", 0)
        if pw > 50:
            layout["designer_palette_width"] = pw
        prw = getattr(app, "_designer_props_width", 0)
        if prw > 50:
            layout["designer_props_width"] = prw

    # Debug float window
    fw = app._output._debug_float_win
    layout["debug_floating"] = fw is not None
    if fw is not None:
        try:
            layout["debug_float_geom"]    = fw.geometry()
            layout["debug_float_topmost"] = fw._topmost
        except Exception:
            pass

    # AI panel
    from utils import ollama_client
    layout["ollama_url"] = ollama_client.get_base_url()
    layout["ai_panel_visible"] = app._ai_panel_visible
    if app._ai_panel_visible:
        try:
            # Measure the frame directly — sashpos() is unreliable on macOS.
            w = app._ai_panel_frame.winfo_width()
            layout["ai_panel_width"] = max(280, w) if w > 50 else app._ai_panel_width
        except Exception:
            layout["ai_panel_width"] = app._ai_panel_width
    else:
        layout["ai_panel_width"] = app._ai_panel_width

    explorer_root = str(app._sidebar.explorer._root or os.getcwd())

    breakpoints = {
        fp: sorted(lines)
        for fp, lines in app._breakpoints.items()
        if lines
    }

    _interp_path = getattr(app, "_active_python", "")
    # Derive the venv activate script from the interpreter path so it can be
    # used to auto-activate the terminal on the next session restore.
    import platform as _pl
    _venv_activate = ""
    if _interp_path:
        _parent = Path(_interp_path).parent  # Scripts/ or bin/
        _act = _parent / ("Activate.ps1" if _pl.system() == "Windows" else "activate")
        if _act.exists():
            _venv_activate = str(_act)
    interpreter = {
        "path":          _interp_path,
        "label":         getattr(app, "_active_python_label", ""),
        "venv_activate": _venv_activate,
    }

    try:
        target.write_text(
            json.dumps(
                {
                    "tabs":          tabs_data,
                    "active_index":  active_index,
                    "explorer_root": explorer_root,
                    "layout":        layout,
                    "appearance":    appearance,
                    "breakpoints":   breakpoints,
                    "interpreter":   interpreter,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
    except Exception:
        pass


def restore(app: "IDOL", filepath: str | Path | None = None) -> bool:
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

    # ── Breakpoints — restore before tabs so _new_tab() applies gutter dots ──
    saved_bp = data.get("breakpoints", {})
    for fp, lines in saved_bp.items():
        if lines:
            app._breakpoints[fp] = set(lines)
    if saved_bp:
        app.after_idle(app._refresh_debug_breakpoints)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    app._restoring = True
    for entry in tabs:
        fp       = entry.get("filepath")
        title    = entry.get("title", "Untitled")
        content  = entry.get("content")
        tmp_file = entry.get("temp_file")

        if tmp_file and os.path.isfile(tmp_file):
            # Restore from temp file — tab was unsaved when the app last exited
            try:
                tmp_content = Path(tmp_file).read_text(encoding="utf-8")
                app._new_tab(title, tmp_content, filepath=fp if fp else None)
                tab_id = app.notebook.tabs()[-1]
                app._temp_files[tab_id] = tmp_file
                # Schedule dirty=True via after_idle so it fires after _new_tab's
                # own _reset_dirty_after_load callback (after_idle is FIFO).
                def _mark_restored(tid=tab_id):
                    app._dirty[tid] = True
                    app._refresh_tab_title(tid)
                app.after_idle(_mark_restored)
            except Exception:
                continue
        elif fp and os.path.isfile(fp):
            try:
                file_content = Path(fp).read_text(encoding="utf-8")
                app._new_tab(title, file_content, filepath=fp)
            except Exception:
                continue
        elif content is not None:
            app._new_tab(title, content, filepath=fp if fp else None)

    # Keep _restoring True past all layout callbacks (50ms, 250ms) so any
    # ContentChanged events they generate are suppressed before the user
    # can interact with the editor.  The 350ms cleanup still runs first.
    app.after(400, lambda: setattr(app, '_restoring', False))

    tabs_list = app.notebook.tabs()
    active = data.get("active_index", 0)
    if 0 <= active < len(tabs_list):
        app.notebook.select(tabs_list[active])

    # ── Explorer root ─────────────────────────────────────────────────────────
    root = data.get("explorer_root")
    if root and not os.path.isdir(root):
        root = str(Path.home())
    if root:
        app._set_explorer_root(root)

    # ── Interpreter ───────────────────────────────────────────────────────────
    interp = data.get("interpreter", {})
    interp_path  = interp.get("path", "")
    interp_label    = interp.get("label", "")
    venv_activate   = interp.get("venv_activate", "")
    if interp_path and os.path.isfile(interp_path) and hasattr(app, "_set_active_interpreter"):
        app._set_active_interpreter(interp_path, interp_label or "Python")
    if venv_activate and os.path.isfile(venv_activate) and hasattr(app, "_schedule_venv_activation_if_needed"):
        app._schedule_venv_activation_if_needed(venv_activate)

    # ── Appearance ────────────────────────────────────────────────────────────
    appearance = data.get("appearance", {})
    theme = appearance.get("theme")
    if theme:
        # Coerce legacy pygments theme names (saved before the canvas
        # editor migration) to the bundled default so the View → Theme
        # menu has a valid radio-checked entry on launch.
        from utils.theme_loader import list_themes as _canvas_ids
        if theme not in _canvas_ids():
            theme = "monokai-bright"
        app.theme_var.set(theme)
        app.view_change_theme()
    font = appearance.get("font")
    if font:
        try:
            if isinstance(font, (list, tuple)) and len(font) >= 2:
                family = str(font[0])
                size   = int(font[1])
                weight = str(font[2]) if len(font) > 2 else "normal"
                slant  = str(font[3]) if len(font) > 3 else "roman"
                app._editor_font = (family, size, weight, slant)
                for cv in app._codeviews.values():
                    if cv is not None:
                        cv.set_font(family, size, weight, slant)
        except Exception:
            pass

    minimap = appearance.get("minimap_visible", True)
    app.minimap_visible_var.set(minimap)
    app.view_toggle_minimap()

    # ── Layout — two-stage to let pane geometry settle before sidebar measures ──
    layout = data.get("layout")
    if layout:
        # Restore maximize / fullscreen state — position is not persisted
        maximized  = layout.get("window_maximized", False)
        fullscreen = sys.platform == "darwin" and layout.get("window_fullscreen", False)
        if fullscreen:
            # macOS native fullscreen — enter it now; sash restore needs a longer
            # delay because the fullscreen animation takes ~400 ms to settle.
            try:
                app.wm_attributes("-fullscreen", True)
            except Exception:
                pass
        elif maximized:
            try:
                app.wm_state("zoomed")      # Windows
            except Exception:
                pass
            try:
                app.attributes("-zoomed", True)  # Linux
            except Exception:
                pass
        elif sys.platform.startswith("linux"):
            # KDE/GNOME session management re-maximizes windows independently of
            # IDOL's saved state.  We fight it with a delayed retry, but there is
            # a visible flash (normal → maximize → normal) that we cannot fully
            # eliminate without fighting the WM further — not worth it.
            # DO NOT try withdraw()/deiconify() here; it makes the flash worse.
            def _force_normal(attempt: int = 0):
                try:
                    if bool(int(app.attributes("-zoomed"))):
                        app.attributes("-zoomed", False)
                        if attempt < 4:
                            app.after(150, lambda: _force_normal(attempt + 1))
                except Exception:
                    pass
            app.after(300, _force_normal)
        # Stage 1: set h_pane / v_pane sash positions.
        # Use a longer delay when entering macOS fullscreen so the animation
        # completes before we try to measure pane geometry.
        stage1_delay = 500 if fullscreen else 50
        stage2_delay = 700 if fullscreen else 250
        app.after(stage1_delay, lambda: _apply_pane_sashes(app, layout))
        app.after(stage2_delay, lambda: _apply_sidebar_layout(app, layout))

    # Stage 3 (350 ms): final dirty-flag cleanup — any ContentChanged events
    # that fired after _restoring was cleared (layout redraws, LSP) may have
    # spuriously marked tabs dirty.  Clear tabs whose content matches disk.
    app.after(350, lambda: _cleanup_dirty_flags(app))

    return True


def _cleanup_dirty_flags(app: "IDOL") -> None:
    """Clear dirty on tabs whose in-editor content matches what's on disk."""
    for tab_id in app.notebook.tabs():
        if not app._dirty.get(tab_id):
            continue
        fp = app._files.get(tab_id)
        if not fp:
            continue
        cv = app._codeviews.get(tab_id)
        if cv is None:
            continue
        try:
            cur = (cv.get_text() if hasattr(cv, "get_text")
                   else cv.get("1.0", "end-1c"))
            if cur == Path(fp).read_text(encoding="utf-8"):
                app._dirty[tab_id] = False
                app._refresh_tab_title(tab_id)
        except Exception:
            pass


_MIN_SASH = 40   # px — below this a saved sash value is considered corrupt


def _apply_pane_sashes(app: "IDOL", layout: dict) -> None:
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

    # Restore run preferences
    run_target = layout.get("run_target")
    if run_target in ("output", "terminal"):
        app._run_target_var.set(run_target)
    run_action = layout.get("run_action")
    if run_action in ("run", "debug"):
        app._run_action_var.set(run_action)
        app.after_idle(app._refresh_run_buttons)
    run_entry = layout.get("run_entry", "")
    if run_entry and os.path.isfile(run_entry) and hasattr(app, "_set_run_entry"):
        app._set_run_entry(run_entry)

    # Designer — restore project type, sash widths, and mode bar visibility
    project_type = layout.get("designer_project_type", "cli")
    if project_type == "gui" and hasattr(app, "_show_mode_bar"):
        app._designer_project_type = "gui"
        pw = layout.get("designer_palette_width", 0)
        if pw > 50:
            app._designer_palette_width = pw
            try:
                app._designer_palette.configure(width=pw)
            except Exception:
                pass
        prw = layout.get("designer_props_width", 0)
        if prw > 50:
            app._designer_props_width = prw
            try:
                app._props_panel.configure(width=prw)
            except Exception:
                pass
        app.after_idle(app._show_mode_bar)
        if layout.get("designer_mode_active") and hasattr(app, "_enter_designer_mode"):
            app.after(300, app._enter_designer_mode)

    # Restore Ollama URL if customized
    if layout.get("ollama_url"):
        from utils import ollama_client
        ollama_client.set_base_url(layout["ollama_url"])
        if hasattr(app, "_ai_chat_panel"):
            app._ai_chat_panel._url_var.set(ollama_client.get_base_url())

    # Debug float window
    if layout.get("debug_floating"):
        try:
            app._output._pop_debug_out()
            fw = app._output._debug_float_win
            if fw:
                geom = layout.get("debug_float_geom")
                if geom:
                    fw.geometry(geom)
                if layout.get("debug_float_topmost"):
                    fw._toggle_topmost()
        except Exception:
            pass

    # AI panel — show it if it was visible; sash follows via _apply_ai_panel_sash
    if layout.get("ai_panel_visible"):
        w = layout.get("ai_panel_width", 350)
        app._ai_panel_width = max(280, w)
        if not app._ai_panel_visible:
            app.view_ai_chat()


def _apply_sidebar_layout(app: "IDOL", layout: dict) -> None:
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
def _apply_layout(app: "IDOL", layout: dict) -> None:
    _apply_pane_sashes(app, layout)
    _apply_sidebar_layout(app, layout)
