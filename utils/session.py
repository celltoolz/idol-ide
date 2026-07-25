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


# ── Portable paths ────────────────────────────────────────────────────────────
# A named `.idol-project` save stores every path that lives inside the project
# folder as a POSIX path relative to that folder, so the whole directory can be
# copied or moved and still open.  Paths outside it (a system interpreter, the
# ~/.idol/tmp scratch files, a tab opened from elsewhere) stay absolute — they
# are not part of the project and there is nothing meaningful to relativize
# against.  The auto-session (~/.idol/session.json) passes base=None and keeps
# everything absolute: it is machine-global and has no base directory.
#
# No format version is needed.  os.path.isabs() is the discriminator, so
# project files written by older versions — which are absolute throughout —
# load unchanged.


def _rel(path: str | None, base: str | None) -> str | None:
    """Return *path* relative to *base* when it lives inside it, else absolute.

    Only true descendants are relativized: a `../..` chain would break the
    moment the project folder moved to a different depth, which is exactly
    what this is meant to survive.

    An already-relative path is returned untouched — it is already portable,
    and `abspath()` would otherwise resolve it against the process CWD, which
    has nothing to do with the project.  That makes this idempotent.
    """
    if not path or not base or not os.path.isabs(path):
        return path
    ap = os.path.abspath(path)
    ab = os.path.abspath(base)
    if os.path.normcase(ap) == os.path.normcase(ab):
        return "."
    if os.path.normcase(ap).startswith(os.path.normcase(ab) + os.sep):
        return Path(os.path.relpath(ap, ab)).as_posix()
    return ap


def _abs(path: str | None, base: str | None) -> str | None:
    """Resolve *path* against *base* when it is relative. Inverse of `_rel`."""
    if not path or not base or os.path.isabs(path):
        return path
    return os.path.normpath(os.path.join(base, path))


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


def _under(path: str | None, root: str) -> bool:
    """True when *path* is *root* itself or lives inside it.

    A relative path is never "under" anything here — it is already portable,
    and resolving it would pull in the process CWD.
    """
    if not path or not os.path.isabs(path):
        return False
    ap, ar = os.path.normcase(os.path.abspath(path)), os.path.normcase(os.path.abspath(root))
    return ap == ar or ap.startswith(ar + os.sep)


def _remap_moved_project(data: dict, old_root: str, new_root: str) -> None:
    """Re-point every stored path that lived under *old_root* at *new_root*.

    Only needed for project files written before paths went relative — a
    portable file needs no remapping, because nothing in it names the old
    location in the first place.  Paths outside *old_root* are left alone:
    they were never project content, so a move says nothing about them.

    `temp_file` is deliberately skipped — those live in ~/.idol/tmp and belong
    to this machine, not to the project folder that moved.
    """
    def remap(p: str | None) -> str | None:
        if not _under(p, old_root):
            return p
        rel = os.path.relpath(os.path.abspath(p), os.path.abspath(old_root))
        return os.path.normpath(os.path.join(new_root, rel))

    for key in ("tabs", "split_tabs"):
        for entry in data.get(key, []) or []:
            if entry.get("filepath"):
                entry["filepath"] = remap(entry["filepath"])

    bps = data.get("breakpoints")
    if isinstance(bps, dict):
        data["breakpoints"] = {remap(fp): lines for fp, lines in bps.items()}

    interp = data.get("interpreter")
    if isinstance(interp, dict):
        for key in ("path", "venv_activate", "conda_prefix"):
            if interp.get(key):
                interp[key] = remap(interp[key])

    layout = data.get("layout")
    if isinstance(layout, dict) and layout.get("run_entry"):
        layout["run_entry"] = remap(layout["run_entry"])

    data["explorer_root"] = new_root


def _portable_copy(data: dict, base: str) -> dict:
    """Return *data* with every project-internal path relativized against *base*.

    A pure JSON transform: used to rewrite a legacy project file at open time
    without re-serialising live app state, which at that moment is still
    settling (layout stages, designer load) and would capture a half-restored
    session.
    """
    out = json.loads(json.dumps(data))  # deep copy — never mutate the caller's

    for key in ("tabs", "split_tabs"):
        for entry in out.get(key, []) or []:
            if entry.get("filepath"):
                entry["filepath"] = _rel(entry["filepath"], base)

    bps = out.get("breakpoints")
    if isinstance(bps, dict):
        out["breakpoints"] = {_rel(fp, base): lines for fp, lines in bps.items()}

    interp = out.get("interpreter")
    if isinstance(interp, dict):
        for key in ("path", "venv_activate", "conda_prefix"):
            if interp.get(key):
                interp[key] = _rel(interp[key], base)

    layout = out.get("layout")
    if isinstance(layout, dict) and layout.get("run_entry"):
        layout["run_entry"] = _rel(layout["run_entry"], base)

    out["explorer_root"] = "."
    return out


def _tab_entry(app: "IDOL", tab_id: str, cv, base: str | None) -> dict:
    """Serialise one editor tab.

    For files that exist on disk only the path is stored; unsaved / dirty tabs
    get their content written to ~/.idol/tmp so the session JSON stays small
    and the work survives a restart.  Shared by the main and split notebooks —
    they serialise identically, and a second copy of this is how a path would
    end up relativized in one pane but not the other.
    """
    fp    = app._files.get(tab_id)
    title = app._titles.get(tab_id, "Untitled")
    dirty = app._dirty.get(tab_id, False)

    entry: dict = {"title": title, "filepath": _rel(fp, base)}

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
        # Duck-type the editor so both `CodeView` (tk.Text) and the
        # canvas-rendered `CanvasCodeView` (explicit `get_text`) work —
        # utils/ can't import from widgets/ per project rules.
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
            # Absolute by design — machine-local scratch, not project content.
            tmp_path.write_text(content, encoding="utf-8")
            entry["temp_file"] = str(tmp_path)
        except Exception:
            entry["content"] = content  # fallback if write fails
    elif fp is None:
        # New empty tab — embed the (likely empty) content directly
        entry["content"] = (cv.get_text() if hasattr(cv, "get_text")
                            else cv.get("1.0", "end-1c"))

    return entry


def save(app: "IDOL", filepath: str | Path | None = None) -> None:
    """Serialise open tabs, explorer root, and sash layout to *filepath*.

    Saves to SESSION_FILE when no path is given (auto-session).
    For files that exist on disk, only the path is stored. For unsaved / dirty
    tabs the content is embedded directly so no work is lost.

    A named `.idol-project` save is **portable**: paths inside the project
    folder are stored relative to it, so the folder can be moved or copied and
    still open.  See the `_rel` / `_abs` block above.
    """
    target = Path(filepath) if filepath else SESSION_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    # A named project save relativizes against its own folder; the auto-session
    # has no base directory and stays absolute.
    base = str(target.parent) if filepath else None

    # ── Tabs ─────────────────────────────────────────────────────────────────
    tabs_data = []
    for tab_id in app.notebook.tabs():
        cv = app._codeviews.get(tab_id)
        if cv is None:
            continue
        tabs_data.append(_tab_entry(app, tab_id, cv, base))

    active_index = 0
    try:
        active_index = list(app.notebook.tabs()).index(app.notebook.select())
    except (ValueError, Exception):
        pass

    # ── Split tabs ────────────────────────────────────────────────────────────
    split_tabs_data = []
    split_active_index = 0
    if getattr(app, "_split_active", False) and getattr(app, "_notebook_r", None):
        for tab_id in app._notebook_r.tabs():
            cv = app._codeviews.get(tab_id)
            if cv is None:
                continue
            split_tabs_data.append(_tab_entry(app, tab_id, cv, base))
        try:
            split_active_index = list(app._notebook_r.tabs()).index(
                app._notebook_r.select()
            )
        except Exception:
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
        total = app._v_pane.winfo_height()
        # Only save if the bottom panel would still have at least 80px
        if v > 0 and (total <= 0 or (total - v) >= 80):
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

    # Run preferences (target: output/terminal; action: run/debug; entry file;
    # cwd mode: project/script)
    layout["run_target"] = app._run_target_var.get()
    layout["run_action"] = app._run_action_var.get()
    layout["run_cwd_mode"] = app._run_cwd_mode_var.get()
    layout["run_entry"] = _rel(getattr(app, "_run_entry_file", "") or "", base)

    # Split editor
    layout["split_active"] = getattr(app, "_split_active", False)
    layout["split_shown"]  = getattr(app, "_split_shown", False)
    layout["split_active_index"] = split_active_index

    # Designer
    layout["designer_project_type"] = getattr(app, "_designer_project_type", "cli")
    layout["designer_mode_active"]  = getattr(app, "_designer_mode", False)
    layout["designer_form_names"]   = list(getattr(app, "_designer_form_names", []))
    layout["designer_main_form"]    = getattr(app, "_designer_main_form", None)
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

    # In a project file this is always the file's own folder, so it is written
    # as "." and ignored on restore — deriving it from where the file actually
    # lives is what makes a copied project correct before any repair runs.
    explorer_root = _rel(str(app._sidebar.explorer._root or os.getcwd()), base)

    breakpoints = {
        _rel(fp, base): sorted(lines)
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
    # Conda envs have no activate script — persist the env prefix directory
    # instead (restore re-activates via the terminal's conda activation).
    from utils.conda_env import conda_prefix_for
    _conda_prefix = (conda_prefix_for(_interp_path) or "") if _interp_path else ""
    # A project-local .venv / .conda relativizes; a system or global-conda
    # interpreter is outside the project and stays absolute.
    interpreter = {
        "path":          _rel(_interp_path, base),
        "label":         getattr(app, "_active_python_label", ""),
        "venv_activate": _rel(_venv_activate, base),
        "conda_prefix":  _rel(_conda_prefix, base),
    }

    try:
        target.write_text(
            json.dumps(
                {
                    "tabs":          tabs_data,
                    "active_index":  active_index,
                    "split_tabs":    split_tabs_data,
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

    # Paths in a project file are relative to the file's own folder; the
    # auto-session stores everything absolute and passes base=None.
    base = str(target.parent) if filepath else None

    # ── Legacy project files ──────────────────────────────────────────────────
    # An absolute `explorer_root` means the file predates portable paths.  If it
    # also disagrees with where the file actually sits, the folder was moved or
    # copied, so every path under the old root is re-pointed at the new one.
    # Either way the file is rewritten in the portable format, so this runs once
    # per project rather than on every open.
    migrated_from = ""
    if base:
        stored_root = data.get("explorer_root") or ""
        if stored_root and os.path.isabs(stored_root):
            same = (os.path.normcase(os.path.abspath(stored_root))
                    == os.path.normcase(os.path.abspath(base)))
            if not same:
                _remap_moved_project(data, stored_root, base)
                migrated_from = stored_root
            try:
                target.write_text(
                    json.dumps(_portable_copy(data, base), indent=2),
                    encoding="utf-8",
                )
            except Exception:
                pass  # read-only location — the in-memory fix still applies

    # ── Breakpoints — restore before tabs so _new_tab() applies gutter dots ──
    saved_bp = data.get("breakpoints", {})
    for fp, lines in saved_bp.items():
        if lines:
            app._breakpoints[_abs(fp, base)] = set(lines)
    if saved_bp:
        app.after_idle(app._refresh_debug_breakpoints)

    # ── Tabs ─────────────────────────────────────────────────────────────────
    app._restoring = True
    for entry in tabs:
        fp       = _abs(entry.get("filepath"), base)
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

    # ── Split tabs ────────────────────────────────────────────────────────────
    split_tabs = data.get("split_tabs", [])
    layout_data = data.get("layout", {})
    split_was_active = layout_data.get("split_active", False)
    split_was_shown  = layout_data.get("split_shown", False)
    split_active_idx = layout_data.get("split_active_index", 0)
    if split_tabs and split_was_active and hasattr(app, "_build_right_pane"):
        app._build_right_pane()
        for entry in split_tabs:
            fp       = _abs(entry.get("filepath"), base)
            title    = entry.get("title", "Untitled")
            content  = entry.get("content")
            tmp_file = entry.get("temp_file")
            if tmp_file and os.path.isfile(tmp_file):
                try:
                    tmp_content = Path(tmp_file).read_text(encoding="utf-8")
                    app._new_tab_in(app._notebook_r, title, tmp_content, filepath=fp)
                    tab_id = app._notebook_r.tabs()[-1]
                    app._temp_files[tab_id] = tmp_file
                    def _mark_split_dirty(tid=tab_id):
                        app._dirty[tid] = True
                        app._refresh_tab_title(tid)
                    app.after_idle(_mark_split_dirty)
                except Exception:
                    continue
            elif fp and os.path.isfile(fp):
                try:
                    app._new_tab_in(app._notebook_r, title,
                                    Path(fp).read_text(encoding="utf-8"), filepath=fp)
                except Exception:
                    continue
            elif content is not None:
                app._new_tab_in(app._notebook_r, title, content, filepath=fp)
        split_list = app._notebook_r.tabs()
        if 0 <= split_active_idx < len(split_list):
            app._notebook_r.select(split_list[split_active_idx])
        app._split_active = True
        if split_was_shown:
            app._split_shown = True
            app._patch_scroll_callbacks()
        else:
            # Built but hidden — remove from paned window until user shows it
            app._split_pane.forget(app._nb_frame_r)
            app._split_shown = False

    # ── Explorer root ─────────────────────────────────────────────────────────
    if base:
        # A project file's root is wherever the file itself lives — never the
        # stored value.  This is what makes a copied or moved project folder
        # open correctly with no repair step at all.
        root = base
    else:
        root = data.get("explorer_root")
        if root and not os.path.isdir(root):
            root = str(Path.home())
    if root:
        # Project-level: the terminal follows the restored root too.
        app._set_project_root(root)

    # run_entry is consumed by the deferred _apply_pane_sashes below, so
    # normalise it in place rather than threading *base* through the callback.
    if base and layout_data.get("run_entry"):
        layout_data["run_entry"] = _abs(layout_data["run_entry"], base)

    # ── Interpreter ───────────────────────────────────────────────────────────
    interp = data.get("interpreter", {})
    interp_path  = _abs(interp.get("path", ""), base)
    interp_label    = interp.get("label", "")
    venv_activate   = _abs(interp.get("venv_activate", ""), base)
    if interp_path and os.path.isfile(interp_path) and hasattr(app, "_set_active_interpreter"):
        app._set_active_interpreter(interp_path, interp_label or "Python")
    if venv_activate and os.path.isfile(venv_activate) and hasattr(app, "_schedule_venv_activation_if_needed"):
        # Only auto-activate a saved venv if it lives inside the restored project
        # root.  A venv from a different project must not be injected into this
        # session's terminal — the user would have to manually deactivate it.
        _venv_under_root = bool(
            root and
            os.path.normcase(os.path.abspath(venv_activate)).startswith(
                os.path.normcase(os.path.abspath(root)) + os.sep
            )
        )
        if _venv_under_root:
            app._schedule_venv_activation_if_needed(venv_activate)

    conda_prefix = _abs(interp.get("conda_prefix", ""), base)
    if (conda_prefix and os.path.isdir(conda_prefix)
            and hasattr(app, "_schedule_conda_activation_if_needed")):
        # Same containment guard as venvs: only re-activate a project-local
        # conda env (e.g. <root>/.conda) — a base or named env from outside
        # the project must not be injected into this session's terminal.
        _conda_under_root = bool(
            root and
            os.path.normcase(os.path.abspath(conda_prefix)).startswith(
                os.path.normcase(os.path.abspath(root)) + os.sep
            )
        )
        if _conda_under_root:
            app._schedule_conda_activation_if_needed(conda_prefix)

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

    # ── Never hand back an empty notebook ─────────────────────────────────────
    # Every tab is skipped individually when its file is gone, so a session
    # whose files have all moved (a renamed project folder is the usual way)
    # restores zero tabs while still reporting success — and callers only run
    # their own fallback when this returns False.  The result was a bare grey
    # panel with no tabs at all.  Seed the same thing a cold start would.
    if not app.notebook.tabs():
        app.after_idle(lambda: _seed_empty_notebook(app))

    if migrated_from:
        # A note, not a question — the file the user opened is the ground truth
        # about where the project lives, so there was nothing to decide.
        app.after(600, lambda: _report_migration(app, migrated_from, base))

    return True


def _seed_empty_notebook(app: "IDOL") -> None:
    """Open Welcome (or a blank tab) when a restore produced no tabs at all."""
    if app.notebook.tabs():
        return  # something else filled it in the meantime
    try:
        from utils import recent as _recent

        if _recent.get_show_on_startup():
            app.view_welcome()
        else:
            app._new_tab("Untitled", "")
    except Exception:
        pass


def _report_migration(app: "IDOL", old_root: str, new_root: str) -> None:
    """Tell the user their project was relocated — in the Output panel, not a dialog."""
    try:
        app._output.output.write(
            f"This project was last opened at {old_root}\n"
            f"It now lives in {new_root} — paths have been updated and saved.\n",
            "info",
        )
    except Exception:
        pass


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
            # Clamp so the bottom panel is always at least 80px tall
            total = app._v_pane.winfo_height()
            if total > 160:
                v = min(v, total - 80)
            app._v_pane.sashpos(0, v)
        except Exception:
            pass

    # Refresh nav bar so SPLIT button reflects restored split state
    if layout.get("split_active") and hasattr(app, "_refresh_nav_bar"):
        app.after_idle(app._refresh_nav_bar)

    # Restore run preferences
    run_target = layout.get("run_target")
    if run_target in ("output", "terminal"):
        app._run_target_var.set(run_target)
    run_action = layout.get("run_action")
    if run_action in ("run", "debug"):
        app._run_action_var.set(run_action)
        app.after_idle(app._refresh_run_buttons)
    run_cwd_mode = layout.get("run_cwd_mode")
    if run_cwd_mode in ("project", "script"):
        app._run_cwd_mode_var.set(run_cwd_mode)
    run_entry = layout.get("run_entry", "")
    if run_entry and os.path.isfile(run_entry) and hasattr(app, "_set_run_entry"):
        app._set_run_entry(run_entry)

    # Designer — restore project type, sash widths, and mode bar visibility
    project_type = layout.get("designer_project_type", "cli")
    designer_was_active = layout.get("designer_mode_active", False)
    if (project_type == "gui" or designer_was_active) and hasattr(app, "_show_mode_bar"):
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
        # Only re-enter designer and reload forms if it was actually open at close time.
        # Restoring form names unconditionally caused stale names from old sessions to
        # load every form in the directory on next open.
        if designer_was_active and hasattr(app, "_enter_designer_mode"):
            saved_form_names = layout.get("designer_form_names", [])
            if saved_form_names and hasattr(app, "_designer_form_names"):
                app._designer_form_names = list(saved_form_names)
            saved_main_form = layout.get("designer_main_form")
            if saved_main_form and hasattr(app, "_designer_main_form"):
                app._designer_main_form = saved_main_form
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
