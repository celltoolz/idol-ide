from __future__ import annotations

import builtins
import os
import re
import sys
import threading
import zlib
import tkinter as tk
from pathlib import Path
from tkinter import BooleanVar, Label, StringVar, Tk, ttk
from tkinter.filedialog import askopenfilename, asksaveasfilename
from tkinter.messagebox import showinfo, showerror, askyesnocancel, askyesno

from tkfontchooser import askfont
from tkinter.colorchooser import askcolor

from widgets.canvas_codeview import CanvasCodeView
from widgets.scrollbar import HorizontalScrollbar, VerticalScrollbar
from widgets.notebook import CustomNotebook
from widgets.sidebar import Sidebar
from widgets.bottom_panel import BottomPanel
from widgets.find_replace import FindReplaceBar
from widgets.statusbar import StatusBar
from widgets.command_palette import CommandPalette
from widgets.breadcrumb_bar import BreadcrumbBar
from editor.bracket_matcher import BracketMatcher
from editor.key_handler import KeyHandler
from editor.multi_cursor import MultiCursor
from widgets.completion_popup import CompletionPopup
from editor.lsp_manager import (
    LspManager,
    detect_server,
    uri_to_path,
    path_to_uri,
    SEV_ERROR,
    SEV_WARNING,
)
from editor.pyflakes_linter import PyflakesLinter
from editor.debug_manager import DebugManager
from editor.git_manager import GitManager, get_global_identity
from menus.menubar import build_menubar
from utils import session as session_utils
from utils import recent as recent_utils
from utils.thread_safe_after import make_thread_safe_after
from widgets.learning_manager import LearningManager
from utils.custom_cursor import get_learn_cursor
from utils.ui_font import UI_FONT
from utils.theme_loader import theme_kind as _theme_kind
from widgets.learning_panel import LearningPanel
from widgets.ai_chat_panel import AiChatPanel
from widgets.package_manager import PackageManagerPanel
from widgets.welcome import WelcomePanel
from widgets.clipboard_history import ClipboardHistoryPanel
from widgets.designer_properties import DesignerProperties
from widgets.designer_palette import DesignerPalette
from widgets.designer_component_tray import ComponentTray
from widgets.designer_connector import ComponentConnector
from widgets.form_list_panel import FormListPanel
from designer.canvas import DesignerCanvas
from designer.component_registry import (
    COMPONENT_REGISTRY,
    get_component_def,
    default_props,
)
from designer.model import ComponentDescriptor
from designer.registry import REGISTRY as _DESIGNER_REGISTRY
from designer.toolbar import DesignerToolbar


def _add_tooltip(widget, text: str, delay: int = 500) -> None:
    """Attach a hover tooltip that appears *delay* ms after entering *widget*."""
    _after = [None]
    _win = [None]

    def _show():
        if _win[0]:
            return
        x = widget.winfo_rootx() + widget.winfo_width() // 2
        y = widget.winfo_rooty() + widget.winfo_height() + 4
        win = tk.Toplevel(widget)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        tk.Label(
            win,
            text=text,
            bg="#252526",
            fg="#cccccc",
            font=(UI_FONT, 8),
            padx=6,
            pady=3,
            relief="flat",
        ).pack()
        win.update_idletasks()
        w = win.winfo_width()
        win.geometry(f"+{x - w // 2}+{y}")
        _win[0] = win

    def _enter(_):
        _after[0] = widget.after(delay, _show)

    def _leave(_):
        if _after[0]:
            widget.after_cancel(_after[0])
            _after[0] = None
        if _win[0]:
            _win[0].destroy()
            _win[0] = None

    widget.bind("<Enter>", _enter, add=True)
    widget.bind("<Leave>", _leave, add=True)


# Cross-platform sash helpers — sashpos() is missing on some macOS Tk builds
def _sash_get(pane: tk.PanedWindow, index: int) -> int:
    """Return sash position for a horizontal PanedWindow."""
    try:
        return pane.sashpos(index)
    except AttributeError:
        return pane.sash_coord(index)[0]


def _sash_set(pane: tk.PanedWindow, index: int, pos: int) -> None:
    """Set sash position for a horizontal PanedWindow."""
    try:
        pane.sashpos(index, pos)
    except AttributeError:
        pane.sash_place(index, pos, 0)


def _offset_to_tk(text: str, offset: int) -> str:
    """Convert a flat character offset into a Tk 'line.col' index string."""
    before = text[:offset]
    line = before.count("\n") + 1
    col = len(before) - before.rfind("\n") - 1
    return f"{line}.{col}"


# Words that should NOT trigger word-highlight on click
_SKIP_HIGHLIGHT = (
    set(dir(builtins))
    | {
        "and",
        "as",
        "assert",
        "async",
        "await",
        "break",
        "case",
        "class",
        "continue",
        "def",
        "del",
        "elif",
        "else",
        "except",
        "finally",
        "for",
        "from",
        "global",
        "if",
        "import",
        "in",
        "is",
        "lambda",
        "match",
        "not",
        "or",
        "pass",
        "raise",
        "return",
        "try",
        "while",
        "with",
        "yield",
        "False",
        "None",
        "True",
    }
    | {str(i) for i in range(10)}
    | {"(", ")", "[", "]", "{", "}", ".", ",", ":", ";"}
)


class _HoverPopup:
    """Lightweight borderless popup for LSP hover documentation."""

    def __init__(self, master, text: str, root_x: int, root_y: int) -> None:
        import tkinter as tk

        self._win = tk.Toplevel(master)
        self._win.overrideredirect(True)
        self._win.wm_attributes("-topmost", True)

        # Clamp text length
        lines = text.splitlines()
        if len(lines) > 20:
            lines = lines[:20] + ["…"]
        display = "\n".join(lines)

        lbl = tk.Label(
            self._win,
            text=display,
            bg="#252526",
            fg="#cccccc",
            font=("Consolas", 9),
            justify="left",
            anchor="w",
            padx=8,
            pady=5,
            wraplength=480,
        )
        lbl.pack()

        # Position just below and to the right of the cursor
        self._win.geometry(f"+{root_x + 16}+{root_y + 8}")

    def destroy(self) -> None:
        try:
            self._win.destroy()
        except Exception:
            pass


# ── Editor accessors ──────────────────────────────────────────────────────────
# Small wrappers that read commonly-needed pieces of the editor's
# state. Phase-(e) cleanup leaves only `CanvasCodeView` so these are
# straight passthroughs to the engine's explicit API now; they stay
# as named helpers because the call sites read more clearly with
# `_cv_text(cv)` than with the bare `.get_text()`.


def _cv_language(cv) -> str:
    """Return the canonical language id for *cv* ("python", "text", ...)."""
    return (cv.language or "text") if cv is not None else "text"


def _cv_is_python(cv) -> bool:
    return _cv_language(cv) == "python"


def _cv_is_code(cv) -> bool:
    return _cv_language(cv) != "text"


def _cv_text(cv) -> str:
    """Return the full buffer text."""
    return cv.get_text() if cv is not None else ""


def _cv_cursor_word(cv) -> str:
    """Return the identifier under the cursor (or empty string)."""
    if cv is None:
        return ""
    return cv._cursor_word() or ""


def _cv_cursor_line_text(cv) -> str:
    """Return the text of the line the cursor is on (no trailing newline)."""
    return cv.get_line(cv.cur_line) if cv is not None else ""


def _cv_selected_text(cv) -> str:
    """Return the currently-selected text (empty if no selection)."""
    return cv.selected_text() if cv is not None else ""


def _cv_cursor_lc(cv) -> tuple[int, int]:
    """Return the cursor position as (line_0_indexed, col)."""
    return cv.get_cursor() if cv is not None else (0, 0)


def _diags_to_entries(diags: list, filepath: str, filename: str) -> list[dict]:
    """Convert LSP diagnostic dicts to ProblemsPanel entries.

    Suppresses cascade noise: when a syntax error exists on line N, ALL
    diagnostics on lines N+1..N+3 that are not themselves root syntax errors
    are dropped — they're parser fallout, not real bugs.
    """
    # Collect 1-based line numbers of root syntax errors
    syntax_error_lines: set[int] = {
        d["range"]["start"]["line"] + 1
        for d in diags
        if d.get("severity") == 1  # SEV_ERROR
    }

    entries = []
    for d in diags:
        line = d["range"]["start"]["line"] + 1
        col = d["range"]["start"]["character"]
        sev = d.get("severity", 2)
        # Drop anything within 3 lines of a syntax error that isn't itself a root
        if line not in syntax_error_lines and any(
            0 < line - root <= 3 for root in syntax_error_lines
        ):
            continue
        entries.append(
            {
                "filepath": filepath,
                "filename": filename,
                "line": line,
                "col": col,
                "severity": sev,
                "message": d.get("message", ""),
            }
        )
    return entries


def _breadcrumb_highlight(cv_ref: list, text: str) -> list[tuple[str, str]]:
    """Tokenize *text* with the active editor's tokenizer and return
    (token_text, color) pairs. The canvas engine exposes `_tokenize`
    (regex-based, returns `(text, category_or_None)`) plus
    `_token_style` (category → `(color, italic)`)."""
    cv = cv_ref[0]
    _FALLBACK = "#cccccc"
    if cv is None:
        return [(text, _FALLBACK)]
    fg = cv._palette.get("fg", _FALLBACK)
    style = cv._token_style
    result: list[tuple[str, str]] = []
    for tok_text, cat in cv._tokenize(text):
        if not tok_text:
            continue
        if cat is None:
            color = fg
        else:
            spec = style.get(cat)
            color = spec[0] if spec else fg
        result.append((tok_text, color))
    return result


class IDOL(Tk):
    def __init__(self, initial_file: str | None = None) -> None:
        super().__init__()
        self.title("IDOL")
        self.geometry("1280x800")

        # On Linux/X11 the classic Tk file dialog (tk_getOpenFile etc.) uses
        # a Motif-style widget whose Listbox defaults to invisible selection
        # colors — the user can't see which file they just clicked. Set
        # readable defaults via Tk's option database. Every IDOL tk.Listbox
        # already passes its own bg/fg/selectbackground/selectforeground in
        # its constructor, which overrides option_add — so these defaults
        # only land on listboxes that don't specify their own (i.e. the
        # file dialog's). Entry/Text are NOT included here because some
        # IDOL widgets (designer properties, etc.) build dark-themed
        # entries without explicit bg.
        import platform as _pl_init

        if _pl_init.system() == "Linux":
            self.option_add("*Listbox.background", "#ffffff")
            self.option_add("*Listbox.foreground", "#000000")
            self.option_add("*Listbox.selectBackground", "#0078d4")
            self.option_add("*Listbox.selectForeground", "#ffffff")

        self._safe_after = make_thread_safe_after(self)

        # Per-tab state  {tab_id -> value}
        self._files: dict[str, str | None] = {}
        self._titles: dict[str, str] = {}
        self._dirty: dict[str, bool] = {}
        self._clean_crcs: dict[str, int] = {}  # CRC32 of last saved/loaded content
        self._temp_files: dict[str, str] = {}  # tab_id → temp file path
        self._indent_sizes: dict[str, int] = {}
        self._codeviews: dict[str, CanvasCodeView] = {}
        self._key_handlers: dict[str, KeyHandler] = {}
        self._multi_cursors: dict[str, MultiCursor] = {}
        self._breadcrumbs: dict[str, BreadcrumbBar] = {}

        self._editor_font: tuple | None = None  # (family, size, weight, slant)

        self._bracket_matcher = BracketMatcher()
        self._find_replace: FindReplaceBar | None = None

        # LSP
        self._lsp: LspManager | None = (
            None  # intelligence (hover/completion/definition)
        )
        self._lsp_diag: PyflakesLinter | None = None  # diagnostics (ruff subprocess)
        self._runtime_error_tab_id: str | None = (
            None  # tab showing last crash indicator
        )
        self._lsp_diagnostics: dict[str, list] = {}  # uri → diag list
        self._hover_after_id: str | None = None
        self._hover_popup = None
        self._lsp_change_after_id: str | None = None

        # Debugger
        self._debugger: DebugManager | None = None
        self._breakpoints: dict[str, set[int]] = {}  # filepath → line numbers
        self._debug_current_tab: str | None = None  # tab_id with debug highlight

        # Interpreter
        self._active_python: str = sys.executable
        self._active_python_label: str = ""

        # Completion
        self._completion = CompletionPopup(
            self, on_accept=self._completion_click_accept
        )
        self._completion_after_id: str | None = None
        self._completion_seq: int = 0  # stale-callback guard

        # Git
        self._git: GitManager | None = None
        self._git_status: dict[str, str] = {}  # normcase_path → M/A/U/D
        self._git_tab_status: dict[str, str] = {}  # tab_id → status char
        self._git_hunks: dict[str, list] = {}  # tab_id → hunk list

        # AI Chat panel (right-side panel, not a tab)
        self._ai_panel_visible: bool = False
        self._ai_panel_width: int = 350  # restored width in px
        self._ai_chat_panel: AiChatPanel | None = None  # set in _build_layout
        self._last_editor_tab: str | None = None  # last tab with a real codeview

        # Welcome tab
        self._welcome_tab: str | None = None
        self._welcome_panel: WelcomePanel | None = None

        # Package Manager
        self._pkg_tab: str | None = None
        self._pkg_panel: PackageManagerPanel | None = None

        # Learning Mode
        self._learning_tab: str | None = None
        self._learning_panel: LearningPanel | None = None
        self._learning_active_lid: str = ""
        self._learning_reg_map: dict = {}  # widget → lid, built on activate

        # Clipboard History
        self._clip_top: tk.Toplevel | None = None
        self._clip_panel: ClipboardHistoryPanel | None = None

        # Canvas Editor sandbox — preview of the canvas-rendered editor

        # Split editor
        self._split_active: bool = False  # right pane has been built and has tabs
        self._split_shown: bool = False  # right pane is currently visible
        self._split_was_shown: bool = False  # was visible before designer hid it
        self._split_sash_pos: int | None = None
        self._active_pane: str = "left"  # "left" | "right"
        self._notebook_r: CustomNotebook | None = None
        self._nb_frame_r = None
        self._scroll_locked: bool = False
        self._lock_btn = None
        self._syncing_scroll: bool = False

        # Settings
        # Default theme aligned with the canvas engine's own default
        # so the View → Theme submenu shows the right radio-checked
        # entry on first launch. Legacy CodeView ignores canvas-only
        # ids — switching to "monokai" / "dracula" / etc. in the menu
        # routes via view_change_theme's engine-aware branch.
        self.theme_var = StringVar(value="monokai-bright")
        self.highlight_line_var = BooleanVar(value=True)
        self.output_visible_var = BooleanVar(value=True)
        self.panel_tab_var = StringVar(value="output")
        self.minimap_visible_var = BooleanVar(value=True)
        self.sidebar_visible_var = BooleanVar(value=True)
        self.zen_mode_var = BooleanVar(value=False)
        self._run_target_var = tk.StringVar(value="output")
        self._run_action_var = tk.StringVar(value="run")
        self._run_entry_file: str | None = None
        self._running_file: str | None = None  # transient label while a run is active
        self._sidebar_shown = True  # tracks actual pane membership
        self._active_line_color: str | None = None

        # Zen mode
        self._zen_mode: bool = False

        # Designer
        self._designer_mode: bool = False
        self._designer_dirty: bool = (
            False  # True when model changed since last Generate Code
        )
        self._designer_forms_dirty: bool = False  # True when JSON not yet saved
        self._autogen_after_id: str | None = None  # pending debounced auto-gen timer
        self._pending_body_resets: set[str] = (
            set()
        )  # method names to drop before next gen
        self._designer_project_type: str = "cli"  # "cli" | "gui"
        self._designer_menu_had_items: bool = (
            False  # tracks prev menu_bar state for shift logic
        )
        self._designer_forms: dict = {}  # {name: FormModel} for all open forms
        self._designer_form_names: list = []  # explicit project form list ([] = use glob)
        self._designer_missing_dialogs: set = (
            set()
        )  # linked dialog names whose files were not found
        self._designer_main_form: str | None = (
            None  # form set as the project entry point
        )
        self._zen_pill: object = None  # floating toast Toplevel

        # Peek at the saved layout before building so panes can be pre-sized
        # to their saved dimensions — eliminates the visible sash jump on startup.
        _saved = session_utils.peek_layout()
        self._startup_h_sash: int = int(_saved.get("h_sash") or 0) or 220
        self._startup_v_sash: int = int(_saved.get("v_sash") or 0)

        # On Linux, wm_attributes("-zoomed") may not reflect the true state at
        # close time due to X11 event queuing.  Track it continuously instead.
        self._window_maximized: bool = False
        if sys.platform.startswith("linux"):

            def _track_maximize(event):
                if event.widget is not self:
                    return
                try:
                    raw = self.attributes("-zoomed")
                    zoomed = bool(int(raw))
                    if zoomed != self._window_maximized:
                        print(
                            f"[maximize] <Configure> zoomed changed: {self._window_maximized} → {zoomed}  (raw={raw!r})"
                        )
                    self._window_maximized = zoomed
                except Exception as e:
                    print(f"[maximize] <Configure> attributes('-zoomed') error: {e}")

            self.bind("<Configure>", _track_maximize, add=True)

        self._build_layout()
        build_menubar(self)
        self._bind_shortcuts()
        self._start_highlight_loop()

        if initial_file and os.path.isfile(initial_file):
            self._open_file(initial_file)
        elif not session_utils.restore(self):
            if recent_utils.get_show_on_startup():
                self.after_idle(self.view_welcome)
            else:
                self._new_tab("Untitled", "")
            self._set_explorer_root(str(Path.home()))
            # No session file — trigger sidebar relayout once the window has
            # real pixel dimensions (250 ms is enough for all platforms).
            self.after(250, self._sidebar._relayout)

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # Status bar at the very bottom
        self._statusbar = StatusBar(
            self,
            on_indent_change=self._on_indent_change,
            on_diagnostics_click=lambda: self._output._set_active("problems"),
            on_interpreter_click=self._open_interpreter_picker,
            on_run_entry_click=self._open_run_entry_picker,
        )
        self._statusbar.pack(side="bottom", fill="x")
        self._statusbar.set_run_entry("Active Tab")  # show segment immediately
        LearningManager.register(self._statusbar._run_entry_lbl, "run_entry_selector")

        # Horizontal split: outline (left) | editor+output (right)
        self._h_pane = tk.PanedWindow(
            self, orient="horizontal", sashwidth=4, bd=0, bg="#3c3c3c"
        )
        self._h_pane.pack(fill="both", expand=True)

        # Left panel – sidebar (outline + source control + explorer)
        self._sidebar = Sidebar(
            self._h_pane,
            on_file_open=self._open_file,
            on_navigate=self._outline_navigate,
            sc_callbacks={
                "stage": self._sc_stage,
                "unstage": self._sc_unstage,
                "discard": self._sc_discard,
                "commit": self._sc_commit,
                "push": self._sc_push,
                "pull": self._sc_pull,
                "diff": self._sc_open_diff,
                "create_gitignore": self._sc_create_gitignore,
                "add_to_gitignore": self._sc_add_to_gitignore,
                "untrack_venv": self._sc_untrack_venv,
                "gitignore_check": self._sc_gitignore_exists,
                "repo_root": lambda: self._git._root if self._git else "",
                "history_diff": self._sc_history_diff,
                "expand_commit": self._sc_expand_commit,
            },
            on_file_move=self._on_explorer_file_move,
            on_root_change=self._on_explorer_root_change,
            on_file_delete=self._on_explorer_file_delete,
            on_ref_navigate=self._ref_navigate,
            on_open_in_designer=self._open_form_json_in_designer,
        )
        self._sidebar.configure(width=self._startup_h_sash)
        self._h_pane.add(self._sidebar, minsize=220, stretch="never")
        self._outline = self._sidebar.outline  # keep existing references working

        # Check git identity immediately — no repo needed, reads global config
        get_global_identity(self._safe_after, self._on_sc_identity)

        # Detect active interpreter and show in statusbar
        self._init_interpreter()

        # Right panel – vertical split: notebook (top) | output (bottom)
        self._v_pane = ttk.PanedWindow(self._h_pane, orient="vertical")
        self._h_pane.add(self._v_pane, stretch="always")

        # Horizontal split pane — holds left notebook (always) + right notebook (when split)
        self._split_pane = ttk.PanedWindow(self._v_pane, orient="horizontal")
        self._v_pane.add(self._split_pane, weight=3)

        # Left notebook frame (primary)
        nb_frame = ttk.Frame(self._split_pane)
        self._split_pane.add(nb_frame, weight=1)
        self._nb_frame_l = nb_frame

        # ── Nav toolbar strip ─────────────────────────────────────────────────
        # Thin strip above the tab bar: left cluster (‹ › +) and right cluster
        # of view toggles that highlight blue when active.
        _NAV_BG = "#2d2d30"
        _nav_bar = tk.Frame(nb_frame, bg=_NAV_BG, height=24)
        _nav_bar.pack(fill="x", side="top")
        _nav_bar.pack_propagate(False)

        def _nav_btn(
            parent, text, cmd, side="left", padx=5, active_fn=None, passthrough=False
        ):
            fg0 = "#007acc" if active_fn and active_fn() else "#858585"
            lbl = Label(
                parent,
                text=text,
                bg=_NAV_BG,
                fg=fg0,
                font=(UI_FONT, 9),
                cursor="hand2",
                padx=padx,
                pady=0,
            )

            def _enter(_):
                lbl.config(fg="#1a9fd4" if active_fn and active_fn() else "#cccccc")

            def _leave(_):
                lbl.config(fg="#007acc" if active_fn and active_fn() else "#858585")

            def _click():
                if (
                    self._learning_tab
                    and cmd is not self.view_learning_mode
                    and not passthrough
                ):
                    lid = self._learning_reg_map.get(lbl)
                    if lid:
                        self._on_learning_click(lbl, lid)
                    return
                cmd()
                self._refresh_nav_bar()

            lbl.bind("<Button-1>", lambda _: _click())
            lbl.bind("<Enter>", _enter)
            lbl.bind("<Leave>", _leave)
            lbl.pack(side=side)
            return lbl

        # Left cluster — lambdas defer notebook lookup until after assignment
        self._prev_btn = _nav_btn(
            _nav_bar, " ‹ ", lambda: self.notebook.select_prev(), passthrough=True
        )
        self._next_btn = _nav_btn(
            _nav_bar, " › ", lambda: self.notebook.select_next(), passthrough=True
        )
        tk.Frame(_nav_bar, bg="#555555", width=1).pack(side="left", fill="y", pady=4)
        self._plus_btn = _nav_btn(_nav_bar, " + ", self.file_new, passthrough=True)
        self._plus_btn.bind("<Enter>", lambda _: self._plus_btn.config(fg="#2ea043"))
        self._plus_btn.bind("<Leave>", lambda _: self._plus_btn.config(fg="#858585"))

        # Encoding fix pill — hidden until a bad paste is detected
        self._encoding_pill = Label(
            _nav_bar,
            text=" ⚠ Fix Encoding ",
            bg=_NAV_BG,
            fg="#e8a844",
            font=(UI_FONT, 9),
            cursor="hand2",
            padx=2,
            pady=0,
        )
        self._encoding_pill.bind("<Button-1>", lambda _: self._fix_encoding())
        self._encoding_pill.bind(
            "<Enter>", lambda _: self._encoding_pill.config(fg="#ffd080")
        )
        self._encoding_pill.bind(
            "<Leave>", lambda _: self._encoding_pill.config(fg="#e8a844")
        )

        # Debug controls — hidden until a session is active
        self._debug_bar = tk.Frame(_nav_bar, bg="#1e1e1e")
        # (packed dynamically by _show_debug_bar / _hide_debug_bar)
        _DBG_BTN_STYLE = dict(
            bg="#1e1e1e",
            fg="#858585",
            font=(UI_FONT, 10),
            relief="flat",
            bd=0,
            cursor="hand2",
            padx=6,
            pady=2,
            activebackground="#2a2d2e",
            activeforeground="#ffffff",
        )
        self._dbg_continue_btn = tk.Label(
            self._debug_bar, text="▶", **{**_DBG_BTN_STYLE, "fg": "#4ec94e"}
        )
        self._dbg_over_btn = tk.Label(self._debug_bar, text="↷", **_DBG_BTN_STYLE)
        self._dbg_in_btn = tk.Label(self._debug_bar, text="↓", **_DBG_BTN_STYLE)
        self._dbg_out_btn = tk.Label(self._debug_bar, text="↑", **_DBG_BTN_STYLE)
        self._dbg_stop_btn = tk.Label(
            self._debug_bar, text="■", **{**_DBG_BTN_STYLE, "fg": "#f44747"}
        )
        for btn, cmd in (
            (self._dbg_continue_btn, self._debug_continue),
            (self._dbg_over_btn, self._debug_step_over),
            (self._dbg_in_btn, self._debug_step_in),
            (self._dbg_out_btn, self._debug_step_out),
            (self._dbg_stop_btn, self._debug_stop),
        ):
            btn.pack(side="left")
            btn.bind("<Button-1>", lambda _, fn=cmd: fn())
            btn.bind("<Enter>", lambda e, b=btn: b.config(fg="#ffffff"))
            btn.bind(
                "<Leave>",
                lambda e, b=btn: b.config(
                    fg="#4ec94e"
                    if b is self._dbg_continue_btn
                    else "#f44747"
                    if b is self._dbg_stop_btn
                    else "#858585"
                ),
            )
        for btn, tip in (
            (self._dbg_continue_btn, "Continue (F5)"),
            (self._dbg_over_btn, "Step Over (F10)"),
            (self._dbg_in_btn, "Step Into (F11)"),
            (self._dbg_out_btn, "Step Out (Shift+F11)"),
            (self._dbg_stop_btn, "Stop (Shift+F5)"),
        ):
            _add_tooltip(btn, tip)
        tk.Frame(self._debug_bar, bg="#555555", width=1).pack(
            side="left", fill="y", pady=4, padx=2
        )

        # Right cluster — packed side="right" so leftmost button is packed last.
        # MAP needs to pre-toggle minimap_visible_var since view_toggle_minimap
        # reads it expecting the checkbutton to have already flipped it.
        def _nav_map_cmd():
            self.minimap_visible_var.set(not self.minimap_visible_var.get())
            self.view_toggle_minimap()

        tk.Frame(_nav_bar, bg="#555555", width=1).pack(side="right", fill="y", pady=4)

        # ── Run / Stop cluster (rightmost) ────────────────────────────────────
        # Layout (left→right): [ ▶/⬡ action ][ ▾ chevron ]  [ ■ stop ]
        # Packed side="right" so rightmost item is packed first.
        self._nav_stop_btn = Label(
            _nav_bar,
            text=" ■ ",
            bg=_NAV_BG,
            fg="#555555",
            font=(UI_FONT, 9),
            cursor="hand2",
            padx=3,
            pady=0,
        )
        self._nav_stop_btn.pack(side="right")
        self._nav_chevron_btn = Label(
            _nav_bar,
            text="▾",
            bg=_NAV_BG,
            fg="#858585",
            font=(UI_FONT, 8),
            cursor="hand2",
            padx=1,
            pady=0,
        )
        self._nav_chevron_btn.pack(side="right")
        self._nav_run_btn = Label(
            _nav_bar,
            text=" ▶ ",
            bg=_NAV_BG,
            fg="#4ec94e",
            font=(UI_FONT, 9),
            cursor="hand2",
            padx=3,
            pady=0,
        )
        self._nav_run_btn.pack(side="right")

        def _run_btn_enter(_):
            if not self._is_anything_running() and self._has_runnable_target():
                is_dbg = self._run_action_var.get() == "debug"
                self._nav_run_btn.config(fg="#f0d880" if is_dbg else "#6fe06f")

        def _run_btn_leave(_):
            self._refresh_run_buttons()

        def _chevron_enter(_):
            if not self._is_anything_running():
                self._nav_chevron_btn.config(fg="#cccccc")

        def _chevron_leave(_):
            self._nav_chevron_btn.config(
                fg="#555555" if self._is_anything_running() else "#858585"
            )

        def _stop_btn_enter(_):
            if self._is_anything_running():
                self._nav_stop_btn.config(fg="#ff6b6b")

        def _stop_btn_leave(_):
            self._nav_stop_btn.config(
                fg="#f44747" if self._is_anything_running() else "#555555"
            )

        self._nav_run_btn.bind("<Button-1>", lambda _: self._nav_execute())
        self._nav_run_btn.bind("<Enter>", _run_btn_enter)
        self._nav_run_btn.bind("<Leave>", _run_btn_leave)
        self._nav_chevron_btn.bind("<Button-1>", lambda _: self._show_run_menu())
        self._nav_chevron_btn.bind("<Enter>", _chevron_enter)
        self._nav_chevron_btn.bind("<Leave>", _chevron_leave)
        self._nav_stop_btn.bind("<Button-1>", lambda _: self.run_stop())
        self._nav_stop_btn.bind("<Enter>", _stop_btn_enter)
        self._nav_stop_btn.bind("<Leave>", _stop_btn_leave)

        _add_tooltip(self._nav_run_btn, "Run or Debug")
        _add_tooltip(self._nav_chevron_btn, "Select run mode")
        _add_tooltip(self._nav_stop_btn, "Stop (Shift+F5)")

        # Build the run dropdown menu (posted on ▾ click)
        self._run_menu = tk.Menu(
            _nav_bar,
            tearoff=0,
            bg="#252526",
            fg="#cccccc",
            activebackground="#094771",
            activeforeground="#ffffff",
            font=(UI_FONT, 9),
        )
        self._run_menu.add_radiobutton(
            label="\u25b6  Run",
            variable=self._run_action_var,
            value="run",
            command=lambda: (self._refresh_run_buttons(), self._nav_execute()),
        )
        self._run_menu.add_radiobutton(
            label="\u2b21  Debug",
            variable=self._run_action_var,
            value="debug",
            command=lambda: (self._refresh_run_buttons(), self._nav_execute()),
        )
        self._run_menu.add_separator()
        self._run_menu.add_radiobutton(
            label="  \u2192 Output", variable=self._run_target_var, value="output"
        )
        self._run_menu.add_radiobutton(
            label="  \u2192 Terminal", variable=self._run_target_var, value="terminal"
        )
        self._run_menu.add_separator()
        self._run_menu.add_command(label="Run Line", command=self._run_current_line)
        self._run_menu.add_command(label="Run Selection", command=self._run_selection)

        tk.Frame(_nav_bar, bg="#555555", width=1).pack(side="right", fill="y", pady=4)

        self._nav_learn_btn = _nav_btn(
            _nav_bar,
            " 📖 ",
            self.view_learning_mode,
            side="right",
            active_fn=lambda: bool(self._learning_tab),
        )
        self._nav_learn_btn.config(cursor=get_learn_cursor())
        self._nav_pkg_btn = _nav_btn(
            _nav_bar,
            " 📦 ",
            self.view_package_manager,
            side="right",
            active_fn=lambda: bool(self._pkg_tab),
        )
        self._nav_ai_btn = _nav_btn(
            _nav_bar,
            " AI ",
            self.view_ai_chat,
            side="right",
            active_fn=lambda: self._ai_panel_visible,
        )
        tk.Frame(_nav_bar, bg="#555555", width=1).pack(side="right", fill="y", pady=4)
        self._nav_zen_btn = _nav_btn(
            _nav_bar,
            " ZEN ",
            self.view_zen_mode,
            side="right",
            active_fn=lambda: self._zen_mode,
        )
        self._nav_sidebar_btn = _nav_btn(
            _nav_bar,
            " ☰ ",
            self.view_toggle_sidebar,
            side="right",
            active_fn=lambda: self._sidebar_shown,
        )
        self._nav_map_btn = _nav_btn(
            _nav_bar,
            " MAP ",
            _nav_map_cmd,
            side="right",
            active_fn=lambda: self.minimap_visible_var.get(),
        )
        self._nav_split_btn = _nav_btn(
            _nav_bar,
            " SPLIT ",
            self.view_split_editor,
            side="right",
            active_fn=lambda: self._split_active and self._split_shown,
        )
        self._nav_term_btn = _nav_btn(
            _nav_bar, " >_ ", self.view_new_terminal, side="right"
        )

        # Register nav buttons with Learning Mode
        LearningManager.register(self._nav_run_btn, "nav_run")
        LearningManager.register(self._nav_chevron_btn, "nav_chevron")
        LearningManager.register(self._nav_stop_btn, "nav_stop")
        LearningManager.register(self._nav_split_btn, "nav_split")
        LearningManager.register(self._nav_map_btn, "nav_map")
        LearningManager.register(self._nav_sidebar_btn, "nav_sidebar")
        LearningManager.register(self._nav_zen_btn, "nav_zen")
        LearningManager.register(self._nav_ai_btn, "nav_ai")
        LearningManager.register(self._nav_pkg_btn, "nav_pkg")
        LearningManager.register(self._nav_learn_btn, "nav_learn")
        LearningManager.register(self._nav_term_btn, "nav_terminal")

        # ── Mode bar — [Editor] | [Designer] ─────────────────────────────────
        # Hidden until a Tkinter GUI project is active (_show_mode_bar).
        _MB_BG = "#1e1e1e"
        _MB_ACT = "#ffffff"
        _MB_DIM = "#6a6a6a"
        _MB_HL = "#007acc"

        self._mode_bar = tk.Frame(nb_frame, bg=_MB_BG, height=28)
        self._mode_bar.pack_propagate(False)

        def _mode_btn(text: str, cmd) -> tk.Label:
            lbl = tk.Label(
                self._mode_bar,
                text=text,
                bg=_MB_BG,
                fg=_MB_DIM,
                font=(UI_FONT, 9),
                cursor="hand2",
                padx=12,
                pady=0,
            )
            lbl.bind("<Button-1>", lambda _: cmd())
            lbl.bind("<Enter>", lambda _: lbl.config(fg=_MB_ACT))
            lbl.bind("<Leave>", lambda _: self._refresh_mode_bar())
            lbl.pack(side="left")
            return lbl

        self._mode_btn_editor = _mode_btn("Editor", self._enter_editor_mode)
        self._mode_btn_designer = _mode_btn("Designer", self._enter_designer_mode)

        # ── Designer surface (pre-built, swapped in by _enter_designer_mode) ──
        self._designer_frame = tk.Frame(nb_frame, bg="#1e1e1e")

        _canvas_area = tk.Frame(self._designer_frame, bg="#1e1e1e")
        _vbar = VerticalScrollbar(_canvas_area)
        _hbar = HorizontalScrollbar(_canvas_area)

        self._design_canvas = DesignerCanvas(
            _canvas_area,
            on_select=self._on_designer_select,
            on_deselect=self._on_designer_deselect,
            on_widget_changed=self._on_designer_widget_changed,
            on_form_changed=self._on_designer_form_changed,
            on_multi_select=self._on_designer_multi_select,
            on_structure_changed=self._on_designer_structure_changed,
            on_double_click=self._on_designer_double_click,
            on_menu_navigate=self._on_designer_menu_navigate,
            on_menu_item_no_command=self._on_designer_menu_item_no_command,
            on_tool_cancel=self._on_designer_tool_cancel,
            on_snap_state_changed=self._on_designer_snap_state_changed,
            xscrollcommand=_hbar.set,
            yscrollcommand=_vbar.set,
        )
        _vbar.config(command=self._design_canvas.yview)
        _hbar.config(command=self._design_canvas.xview)

        self._designer_toolbar = DesignerToolbar(
            self._designer_frame, self._design_canvas
        )
        self._designer_toolbar.pack(fill="x", side="top")

        _vbar.pack(side="right", fill="y")
        _hbar.pack(side="bottom", fill="x")
        self._design_canvas.pack(fill="both", expand=True)

        self._comp_tray = ComponentTray(
            self._designer_frame,
            on_select=self._on_comp_select,
            on_deselect=self._on_comp_deselect,
            on_delete=self._on_comp_delete,
            on_rename=self._on_comp_rename,
        )
        self._comp_tray.pack(fill="x", side="bottom")

        _canvas_area.pack(fill="both", expand=True)

        # ── Properties panel (right pane, added to _h_pane in designer mode) ──
        self._props_panel = DesignerProperties(
            self._h_pane,
            on_prop_change=self._on_designer_prop_change,
            on_event_change=self._on_designer_event_change,
            on_select_widget=self._on_designer_selector_pick,
            on_navigate_handler=self._on_designer_event_navigate,
            on_reorder_widget=self._on_designer_reorder_widget,
            on_handler_toggle=self._on_designer_handler_toggle,
            on_handler_connect=self._on_designer_handler_connect,
            on_handler_disconnect=self._on_designer_handler_disconnect,
            on_handler_edit=self._on_designer_handler_edit,
            on_component_prop_change=self._on_comp_prop_change,
            on_component_connect=self._on_comp_connect,
            on_component_disconnect=self._on_comp_disconnect,
            on_component_edit=self._on_comp_edit,
            on_select_component=self._on_comp_select,
            on_install_pillow=self._on_designer_install_pillow,
        )
        self._props_panel.configure(width=230)

        # ── Left designer pane: form list (top) + palette (bottom) ──────────────
        self._designer_left_pane = tk.Frame(self._h_pane, bg="#252526")

        self._form_list_panel = FormListPanel(
            self._designer_left_pane,
            on_select=self._on_form_list_select,
            on_new=self.designer_new_form,
            on_link=self._on_form_link,
            on_unlink=self._on_form_unlink,
            on_remove=self._on_designer_form_remove,
            on_context_menu=self._on_form_list_context_menu,
            on_set_main=self._on_form_set_as_main,
        )
        self._form_list_panel.pack(fill="x")

        self._designer_palette = DesignerPalette(
            self._designer_left_pane,
            on_tool_select=self._on_palette_tool_select,
            on_place=self._on_palette_place,
            on_drag_drop=self._on_palette_drag_drop,
            on_component_add=self._on_comp_add,
        )
        self._designer_palette.pack(fill="both", expand=True)
        self._designer_left_pane.configure(width=180)

        # Last-used designer pane widths (persisted in session.json)
        self._designer_palette_width: int = 180
        self._designer_props_width: int = 230

        self.notebook = CustomNotebook(
            nb_frame,
            on_close=self._close_tab,
            on_split=self._copy_to_split,
            on_drag_split=self._move_to_split,
        )
        self.notebook._split_open_ref = lambda: self._split_active and self._split_shown
        self.notebook._get_tab_path = lambda tab_id: self._files.get(tab_id)
        self.notebook._can_drag_out = lambda tab_id: tab_id != self._welcome_tab
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add=True)
        self.notebook.bind(
            "<ButtonPress-1>", lambda _: self._set_active_pane("left"), add=True
        )

        # Inline find/replace bar (lives inside nb_frame, hidden by default)
        self._find_replace = FindReplaceBar(nb_frame)

        self._output = BottomPanel(
            self._v_pane,
            on_run_start=self._refresh_run_buttons,
            on_run_done=self._refresh_run_buttons,
            cwd=os.getcwd(),
            on_navigate=self._open_file_at,
            on_bp_click=lambda fp, ln: self._open_file_at(fp, ln, 0),
        )
        # Wrap on_run_done to also restore the status-bar run-entry label
        _orig_run_done = self._output.output._on_run_done

        def _run_done_hook(_orig=_orig_run_done):
            self._set_running_file(None)
            if _orig:
                _orig()

        self._output.output._on_run_done = _run_done_hook

        # Terminal shell integration: OSC 133;D fires when the prompt appears
        self._output.terminal.on_command_done = lambda exit_code=None: (
            self._running_file and self._set_running_file(None)
        )

        # Keep panel_tab_var in sync whenever the bottom panel switches tabs
        _orig_set_active = self._output._set_active

        def _synced_set_active(key, _orig=_orig_set_active):
            _orig(key)
            self.panel_tab_var.set(key)

        self._output._set_active = _synced_set_active

        self._output.output.on_runtime_error = self._on_runtime_error
        self._output.on_ask_ai_problems = self._ask_ai_about_problems
        self._output.problems.on_ask_ai_entry = self._ask_ai_about_entry
        self._v_pane.add(self._output, weight=1)

        # AI Chat right panel — created here but not added to _h_pane until F2
        self._ai_panel_frame = tk.Frame(self._h_pane, bg="#1e1e1e")
        self._ai_chat_panel = AiChatPanel(
            self._ai_panel_frame,
            get_file_content=self._ai_get_file_content,
            get_selection=self._ai_get_selection,
        )
        self._ai_chat_panel.pack(fill="both", expand=True)

        # Snap the sash once the window is actually visible on screen
        self.bind("<Map>", self._init_sash_pos)
        # Start LSP and Git after the UI is fully mapped
        self.after(500, self._start_lsp)
        self.after(700, self._start_git)
        self.after(1500, self._prewarm_terminal)
        # Reposition autocomplete popup on window move/resize
        self.bind("<Configure>", self._on_window_configure)

        # Ghost-sash: show drag line during drag, resize only on mouse-up
        self._install_ghost_sash(self._h_pane,     "horizontal")
        self._install_ghost_sash(self._v_pane,     "vertical",   min_second=80)
        self._install_ghost_sash(self._split_pane, "horizontal")

    def _init_sash_pos(self, _=None) -> None:
        """Set default sash positions once the window has real pixel dimensions."""
        self.unbind("<Map>")  # only run once
        self.update_idletasks()

        # Guarantee the sidebar has a sensible width.  On Linux the h_pane sash
        # defaults to 0 (collapsing the sidebar entirely) when no session exists
        # or when the async session restore hasn't fired yet.  Set it here while
        # we're in the Map handler so the window is definitely visible.
        try:
            if _sash_get(self._h_pane, 0) < 50:
                _sash_set(self._h_pane, 0, 220)
        except Exception:
            pass

        total = self._v_pane.winfo_height()
        if total > 200:
            v_target = (
                self._startup_v_sash if self._startup_v_sash > 0 else (total - 160)
            )
            self._v_pane.sashpos(0, v_target)

    def _install_ghost_sash(self, pane: tk.Widget, orient: str,
                            min_second: int = 0) -> None:
        """Replace live sash drag with a ghost line + deferred resize.

        A 2px #007acc line tracks the mouse during the drag; the panes only
        resize on mouse-up — eliminates continuous redraws while dragging.
        min_second: minimum pixels the second (bottom/right) pane must keep.
        """
        is_ttk = isinstance(pane, ttk.PanedWindow)
        ghost = tk.Frame(self, bg="#007acc")
        _drag: dict = {"active": False, "sash": 0}

        def _clamp(pos: int) -> int:
            if min_second <= 0:
                return max(0, pos)
            total = pane.winfo_height() if orient == "vertical" else pane.winfo_width()
            return max(0, min(pos, total - min_second))

        def _sash_hit(x: int, y: int) -> tuple[bool, int]:
            try:
                if is_ttk:
                    # identify() is unreliable on Windows (theme-dependent), so
                    # just check proximity to each sash position directly.
                    coord = y if orient == "vertical" else x
                    for i in range(len(pane.panes()) - 1):
                        if abs(coord - pane.sashpos(i)) <= 6:
                            return True, i
                    return False, 0
                else:
                    r = pane.identify(x, y)
                    if not r:
                        return False, 0
                    parts = list(r) if isinstance(r, (list, tuple)) else str(r).split()
                    if len(parts) >= 2 and parts[1] in ("sash", "handle"):
                        return True, int(parts[0])
                    return False, 0
            except Exception:
                return False, 0

        def _show_ghost(ex: int, ey: int) -> None:
            bx = pane.winfo_rootx() - self.winfo_rootx()
            by = pane.winfo_rooty() - self.winfo_rooty()
            pw, ph = pane.winfo_width(), pane.winfo_height()
            if orient == "vertical":
                ghost.place(x=bx, y=by + _clamp(ey) - 1, width=pw, height=2)
            else:
                ghost.place(x=bx + ex - 1, y=by, width=2, height=ph)
            ghost.lift()

        def _apply_release(event):
            if not _drag["active"]:
                return
            _drag["active"] = False
            ghost.place_forget()
            pos = (
                (event.y_root - pane.winfo_rooty())
                if orient == "vertical"
                else (event.x_root - pane.winfo_rootx())
            )
            try:
                _sash_set(pane, _drag["sash"], _clamp(pos))
            except Exception:
                pass
            if pane is self._h_pane and self._ai_panel_visible and self._ai_chat_panel:
                self.after(50, self._ai_chat_panel._on_ai_panel_sash_done)

        def _on_press(event):
            hit, idx = _sash_hit(event.x, event.y)
            if not hit:
                return
            _drag["active"] = True
            _drag["sash"] = idx
            _show_ghost(event.x, event.y)
            return "break"

        def _on_motion(event):
            if not _drag["active"]:
                return
            _show_ghost(event.x, event.y)

        pane.bind("<ButtonPress-1>", _on_press)
        pane.bind("<B1-Motion>", _on_motion)
        # Pane-instance binding fires before class handlers (covers SetCapture case).
        # Toplevel binding fires when mouse is released over a child widget.
        # Both are idempotent — the second caller hits `if not _drag["active"]: return`.
        pane.bind("<ButtonRelease-1>", _apply_release)
        self.bind("<ButtonRelease-1>", _apply_release, add=True)

    def _prewarm_terminal(self) -> None:
        """Start the terminal shell in the background so it's ready on first open."""
        self._output.terminal.on_venv_activate = self._on_venv_activated
        self._output.terminal.on_venv_deactivate = self._on_venv_deactivated
        if not self._output.terminal._running:
            cwd = self._output._cwd or os.getcwd()
            self._output.terminal._new_session(cwd=cwd)
        # If session restore flagged a venv to activate, schedule it 1500 ms after
        # the terminal starts — by then the shell hooks are injected and ready.
        # Guard: skip if the terminal's own _auto_activate_venv already ran (it sets
        # _venv_auto_activated=True).  On Windows _send_silently falls back to the
        # visible send(), so without this guard both paths fire and the user sees the
        # activate command printed twice.
        pending = getattr(self, "_pending_venv_activate", None)
        if pending and os.path.isfile(pending):
            self._pending_venv_activate = None
            term = self._output.terminal

            def _activate_if_needed(p=pending, t=term):
                if not getattr(t, "_venv_auto_activated", False):
                    self._auto_activate_venv(p)

            self.after(1500, _activate_if_needed)

    def _on_venv_deactivated(self) -> None:
        """Called when the user clicks Deactivate — fall back to first system Python."""
        from editor.project_manager import ProjectManager, categorize_interpreter

        def _on_pythons(results: list[tuple[str, str]]) -> None:
            for label, exe in results:
                if categorize_interpreter(exe) == "system" and os.path.isfile(exe):
                    self._set_active_interpreter(
                        exe, self._get_short_interp_label(label)
                    )
                    return
            # Last resort: IDOL's own interpreter
            self._set_active_interpreter(sys.executable, "Python")

        ProjectManager(self._safe_after).discover_interpreters(_on_pythons)

    def _on_venv_activated(self, python_exe: str) -> None:
        """Called when the user clicks Activate venv in the terminal toolbar."""
        from editor.project_manager import ProjectManager

        def _on_pythons(results: list[tuple[str, str]]) -> None:
            for label, exe in results:
                if os.path.normcase(exe) == os.path.normcase(python_exe):
                    short = self._get_short_interp_label(label)
                    self._set_active_interpreter(exe, f"(.venv) {short}")
                    return
            # Not in detected list — set with generic venv label
            self._set_active_interpreter(python_exe, "(.venv) Python")

        ProjectManager(self._safe_after).discover_interpreters(_on_pythons)

    def _schedule_venv_activation_if_needed(self, activate_path: str = "") -> None:
        """Schedule terminal venv activation after session restore.

        At startup the terminal isn't running yet — store as _pending_venv_activate
        so _prewarm_terminal picks it up 1500 ms after the shell starts.
        When called from workspace_open the terminal is already running — schedule
        _auto_activate_venv directly with a short delay.
        """
        import platform as _pl

        if not activate_path:
            path = getattr(self, "_active_python", "")
            if not path:
                return
            parent = os.path.dirname(path)
            activate_path = os.path.join(
                parent, "Activate.ps1" if _pl.system() == "Windows" else "activate"
            )
        if not os.path.isfile(activate_path):
            return
        if getattr(self._output, "terminal", None) and self._output.terminal._running:
            # Terminal already up — fire directly after a short settle delay.
            self.after(500, lambda: self._auto_activate_venv(activate_path))
        else:
            # Startup path — _prewarm_terminal will pick this up.
            self._pending_venv_activate = activate_path

    def _auto_activate_venv(self, activate_path: str) -> None:
        """Send the venv activate command to the terminal (used on session restore)."""
        import platform as _pl

        term = self._output.terminal
        if not term._running:
            return
        if _pl.system() == "Windows":
            term.send(f'& "{activate_path}"\r')
        else:
            term.send(f'source "{activate_path}"\r')

    def _on_window_configure(self, event=None) -> None:
        if event is not None and event.widget is not self:
            return
        if self._completion.visible:
            cv = self._current_codeview
            if cv is None:
                return
            bbox = cv.bbox("insert")
            if not bbox:
                return
            bx, by, _, bh = bbox
            self._completion.reposition(
                cv.winfo_rootx() + bx,
                cv.winfo_rooty() + by + bh + 2,
            )

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda _: self.file_new())
        self.bind("<Control-o>", lambda _: self.file_open())
        self.bind("<Control-s>", lambda _: self.file_save())
        self.bind("<Control-S>", lambda _: self.file_save_as())
        self.bind("<Control-w>", lambda _: self.file_close())
        if sys.platform == "darwin":
            self.bind("<Command-w>", lambda _: self.file_close())
        self.bind("<Control-q>", lambda _: self.file_exit())
        self.bind("<Control-f>", lambda _: self.edit_find_replace())
        self.bind("<Control-l>", lambda _: self.view_change_font())
        self.bind("<F5>", lambda _: self.debug_file())
        self.bind("<Control-F5>", lambda _: self._nav_run())
        self.bind("<F10>", lambda _: self._debug_step_over())
        self.bind("<F11>", lambda _: self._debug_step_in())
        self.bind("<Shift-F11>", lambda _: self._debug_step_out())
        self.bind("<Shift-F5>", lambda _: self.run_stop())
        self.bind("<Control-grave>", lambda _: self.view_show_panel("terminal"))
        self.bind("<Control-U>", lambda _: self.view_show_panel("output"))
        self.bind("<Control-M>", lambda _: self.view_show_panel("problems"))
        self.bind("<Control-Y>", lambda _: self.view_show_panel("debug"))
        self.bind("<Control-G>", lambda _: self.view_source_control())
        self.bind("<Control-backslash>", lambda _: self.view_split_editor())
        self.bind("<Control-P>", lambda _: self.open_command_palette())
        self.bind("<Control-Shift-G>", lambda _: self.designer_generate_code())
        self.bind("<Control-b>", lambda _: self.view_toggle_sidebar())
        self.bind("<F12>", lambda _: self._goto_definition())
        self.bind("<F10>", lambda _: self.view_zen_mode())
        self.bind("<F1>", lambda _: self.view_learning_mode())
        self.bind("<F2>", lambda _: self.view_ai_chat())
        self.bind("<F3>", lambda _: self.view_package_manager())
        self.bind(
            "<Control-H>", lambda _: self.view_clipboard_history()
        )  # Ctrl+Shift+H
        self.bind("<Scroll_Lock>", lambda _: self._toggle_scroll_lock())
        self.bind("<Escape>", self._on_escape)

        # Cancel designer placement mode when clicking outside canvas/palette.
        self.bind_all("<Button-1>", self._on_global_click_designer, add=True)

        # Dismiss floating popups when the application loses OS-level focus.
        # bind_all fires on every widget's FocusOut; the deferred check via
        # focus_displayof() distinguishes internal focus changes (ignored) from
        # the whole app losing focus (dismiss).
        self.bind_all("<FocusOut>", self._on_any_focus_out, add=True)

        self._register_learning_widgets()

    def _on_any_focus_out(self, _event) -> None:
        self.after(50, self._dismiss_on_focus_loss)

    def _dismiss_on_focus_loss(self) -> None:
        """Hide floating popups if the whole application has lost OS focus."""
        try:
            focused = self.focus_displayof()
        except KeyError:
            return  # focus is on a transient tkinter surface (dialog, menu) — keep popups
        if focused is not None:
            return
        try:
            self._run_menu.unpost()
        except Exception:
            pass
        try:
            self._completion.hide()
        except Exception:
            pass

    # ── Tab helpers ───────────────────────────────────────────────────────────

    @property
    def _active_notebook(self) -> CustomNotebook:
        if (
            self._split_active
            and self._split_shown
            and self._active_pane == "right"
            and self._notebook_r
        ):
            return self._notebook_r
        return self.notebook

    def _set_active_pane(self, pane: str) -> None:
        if self._active_pane == pane:
            return
        self._active_pane = pane
        self._on_tab_changed()

    @property
    def _current_tab_id(self) -> str | None:
        nb = self._active_notebook
        if not nb.tabs():
            return None
        try:
            return nb.select()
        except Exception:
            return None

    @property
    def _current_codeview(self) -> CanvasCodeView | None:
        tab_id = self._current_tab_id
        return self._codeviews.get(tab_id) if tab_id else None

    def _new_tab(self, title: str, content: str, filepath: str | None = None) -> None:
        """Build a new editor tab.

        Adds the tab to the notebook, seeds the standard bookkeeping
        (`_files`, `_titles`, `_dirty`, `_codeviews`, `_breadcrumbs`),
        wires the engine's host hooks (on_change for dirty tracking +
        LSP didChange, on_copy for the clipboard ring, on_breakpoint_
        toggle for debug gutter, on_request_* for the right-click
        menu), and schedules the initial outline refresh + LSP
        didOpen for Python files.
        """
        frame = ttk.Frame(self.notebook)
        cv = CanvasCodeView(frame)
        if self._editor_font:
            cv.set_font(*self._editor_font)
        # The sandbox already builds its own breadcrumb internally —
        # no separate widget needed at the tab-frame level for now.
        cv.pack(fill="both", expand=True)
        # Fire `_on_content_changed` whenever the buffer mutates so
        # dirty tracking, LSP didChange, outline refresh, and the
        # statusbar diagnostic count all stay current. Same hook the
        # legacy CodeView fires via its `<<ContentChanged>>` virtual
        # event — canvas engine routes through `on_change` instead.
        cv.on_change = self._on_content_changed
        cv.on_bad_paste = self._show_encoding_pill

        # Copy → ClipboardHistory ring. Mirrors the legacy
        # `_setup_codeview` wiring: when the user hits Ctrl+C, push
        # the selected text to the clipboard panel tagged with the
        # tab's filename for the ring's source label.
        def _on_cv_copy(text: str, _cv=cv) -> None:
            tid = self._current_tab_id
            source = os.path.basename(self._files.get(tid, "") or "")
            if self._clip_panel is None:
                self._ensure_clip_panel()
            self._clip_panel.push(text, source=source)

        cv.on_copy = _on_cv_copy
        if content:
            cv.set_text(content)
        cv.set_filepath(filepath)

        self.notebook.add(frame, text=f"  {title}  ")
        self.notebook.select(frame)

        tab_id = self.notebook.select()
        self._files[tab_id] = filepath
        self._titles[tab_id] = title
        self._dirty[tab_id] = False
        self._indent_sizes[tab_id] = 4
        self._codeviews[tab_id] = cv
        # Reuse the canvas editor's internal breadcrumb as this tab's
        # "breadcrumb widget" for the existing breadcrumb registry —
        # app.py uses _breadcrumbs[tab_id] for outline / path crumbs.
        self._breadcrumbs[tab_id] = cv.breadcrumb

        # Mark clean once the after-idle setup settles, so the initial
        # load doesn't show as a dirty buffer.
        self.after_idle(lambda tid=tab_id: self._reset_dirty_after_load(tid))

        # Outline + LSP open — mirror the legacy `_new_tab` post-build
        # for Python files. Canvas engine derives language from the
        # filepath (.py extension) via `cv.language == "python"`.
        if cv.language == "python":
            self._outline.schedule_refresh(content)
            if filepath:
                for srv in self._each_lsp():
                    srv.open_file(filepath, content)

        # Push canvas palette to the sidebar so outline / references /
        # source control / explorer match the editor's theme. Mirrors
        # the legacy `_new_tab` apply_theme call at the same spot but
        # pulls colors from the canvas engine's palette dict instead
        # of the tk.Text widget options.
        pal = cv._palette
        self._sidebar.apply_theme(
            bg=pal["bg"],
            fg=pal["fg"],
            select_bg=pal.get("select_bg", "#264f78"),
            codeview=cv,
            kind=_theme_kind(self.theme_var.get()),
        )

        # Ctrl+F → IDOL's FindReplaceBar (the sandbox's own internal
        # find bar was deliberately disabled — the user prefers the
        # IDOL one). Bound on the canvas widget that captures key
        # events for the sandbox.
        cv.canvas.bind(
            "<Control-f>",
            lambda _e: (self.edit_find_replace(), "break")[1],
            add="+",
        )

        # Wire LSP completion through the engine's `on_completion_request`
        # hook — same async-callback signature `_sync_canvas_ed_panel_
        # with_active_tab` uses for the preview window. The sandbox's
        # internal autocomplete popup pops on identifier-y keystrokes
        # (alnum / `_` / `.`) and delivers labels back via the callback.
        def _on_completion(prefix, trigger_char, callback, _cv=cv):
            if not (self._lsp and self._lsp.ready and _cv.filepath):
                callback([])
                return

            def _items_cb(items):
                labels = [
                    it.get("label", "") for it in (items or []) if it.get("label")
                ]
                callback(labels)

            # For dot triggers, flush the debounced didChange immediately so
            # pyls sees the "." in the file before it processes the completion
            # request (LSP messages are ordered; this guarantees correct content).
            if trigger_char == ".":
                for _srv in self._each_lsp():
                    _srv.change_file(_cv.filepath, _cv.get_text())
            # For member access with a partial prefix (e.g. self._c), pyls
            # needs triggerKind=2 at the position right after "." — if we
            # send the current cursor (past the prefix) it returns empty.
            # Walk the column back by len(prefix) so pyls sees the dot trigger.
            lsp_col = (
                _cv.cur_col - len(prefix)
                if trigger_char == "." and prefix
                else _cv.cur_col
            )
            self._lsp.completion(
                _cv.filepath,
                _cv.cur_line,
                lsp_col,
                _items_cb,
                trigger_char=trigger_char,
            )

        cv.on_completion_request = _on_completion

        # ── Debug breakpoint gutter ─────────────────────────────────
        # Click on the canvas's debug column → fires `on_breakpoint_
        # toggle(line_0)`. We convert to the 1-indexed convention the
        # host's breakpoint store uses, call `_on_breakpoint_toggle`,
        # and push the resulting set back to the engine for the dot
        # rendering. Mirrors the legacy `_line_numbers.on_breakpoint_
        # toggle = _make_bp_toggle(tab_id)` flow but routed through
        # the canvas engine's own gutter painter.
        def _canvas_bp_toggle(line_0: int, _tid=tab_id, _cv=cv):
            fp = self._files.get(_tid) or ""
            if not fp:
                # Unsaved tab — create a temp file eagerly so the
                # breakpoint has a stable path. Same as legacy
                # `_make_bp_toggle` does for tk.Text-backed tabs.
                import uuid
                from utils.session import TMP_DIR

                tmp = self._temp_files.get(_tid)
                if not tmp:
                    TMP_DIR.mkdir(parents=True, exist_ok=True)
                    tmp = str(TMP_DIR / f"idol_tmp_{uuid.uuid4().hex[:12]}.py")
                    self._temp_files[_tid] = tmp
                try:
                    Path(tmp).write_text(_cv_text(_cv), encoding="utf-8")
                except Exception:
                    pass
                fp = tmp
            lineno_1 = line_0 + 1
            self._on_breakpoint_toggle(fp, lineno_1)
            # Convert host's 1-indexed set back to 0-indexed for the
            # engine.
            _cv.set_breakpoints({ln - 1 for ln in self._breakpoints.get(fp, set())})

        cv.on_breakpoint_toggle = _canvas_bp_toggle

        # Apply any existing breakpoints for this file (session
        # restore, debugger attach) — convert host's 1-indexed set
        # to the engine's 0-indexed convention.
        if filepath:
            cv.set_breakpoints(
                {ln - 1 for ln in self._breakpoints.get(filepath, set())}
            )

        # ── Right-click menu IDE actions ────────────────────────────
        # Mirror the legacy `_on_editor_right_click` (app.py:2234).
        # Each hook is set to the same app.py method the legacy
        # CodeView menu invokes via virtual events; the engine
        # decides when to include them based on selection + cursor
        # word state.
        cv.on_request_goto_definition = self._goto_definition
        cv.on_can_goto_definition = lambda: bool(self._lsp and self._lsp.ready)
        cv.on_request_find_references = self._find_references
        cv.on_request_find_replace = self.edit_find_replace
        cv.on_request_run_line = self._run_current_line
        cv.on_request_run_selection = self._run_selection

        # Line-shift handler for breakpoints — DORMANT for now. The
        # callback (same shift math as the legacy `_make_lines_changed`
        # path) is wired so it's ready when the engine starts firing
        # `on_lines_changed(from_line_1, delta)` from its mutation
        # methods. Until then, canvas-tab breakpoints stay put when
        # lines are inserted/deleted above them — set them again
        # after big edits. Tracked as a follow-up to the breakpoint
        # wiring above.
        def _canvas_lines_changed(from_line_1: int, delta: int, _tid=tab_id, _cv=cv):
            fp = self._files.get(_tid)
            if not fp or fp not in self._breakpoints:
                return
            bp_set = self._breakpoints[fp]
            new_bp: set[int] = set()
            for ln in bp_set:
                if delta > 0:
                    new_bp.add(ln + delta if ln > from_line_1 else ln)
                else:
                    deleted_end = from_line_1 - delta
                    if ln <= from_line_1:
                        new_bp.add(ln)
                    elif ln <= deleted_end:
                        pass  # deleted along with the lines
                    else:
                        new_bp.add(ln + delta)
            self._breakpoints[fp] = new_bp
            _cv.set_breakpoints({ln - 1 for ln in new_bp})
            self._refresh_debug_breakpoints()

        cv.on_lines_changed = _canvas_lines_changed

        # ── LSP hover ───────────────────────────────────────────────
        cv.canvas.bind(
            "<Motion>",
            lambda e, _cv=cv, _tid=tab_id: self._on_hover_motion(
                e, _cv, self._files.get(_tid) or ""
            ),
            add="+",
        )
        cv.canvas.bind("<Leave>", lambda _: self._cancel_hover(), add="+")
        cv.canvas.bind("<FocusIn>", lambda _: self._set_active_pane("left"), add="+")

    def _confirm_close_tab(self, tab_id: str) -> bool:
        """Return True if the tab can be closed (not dirty, or user confirmed)."""
        if not self._dirty.get(tab_id):
            return True
        title = self._titles.get(tab_id, "Untitled")
        answer = askyesnocancel(
            "Unsaved Changes",
            f'"{title}" has unsaved changes.\n\nSave before closing?',
        )
        if answer is None:  # Cancel
            return False
        if answer:  # Yes — save first
            if tab_id != self._current_tab_id:
                self.notebook.select(tab_id)
            if not self.file_save():
                return False  # save failed or was cancelled
        return True

    def _which_notebook(self, tab_id: str) -> CustomNotebook:
        """Return the notebook that owns *tab_id*."""
        if self._notebook_r and tab_id in self._notebook_r.tabs():
            return self._notebook_r
        return self.notebook

    def _close_tab(self, index: int, notebook: CustomNotebook | None = None) -> None:
        nb = notebook or self.notebook
        tabs = nb.tabs()
        if index >= len(tabs):
            return
        tab_id = tabs[index]
        closing_welcome = tab_id == self._welcome_tab
        if closing_welcome:
            # Welcome tab has no dirty state — just close it
            nb.forget(index)
            self._welcome_tab = None
            self._welcome_panel = None
            if nb is self.notebook and not nb.tabs():
                self._new_tab("Untitled", "")
            return
        if not self._confirm_close_tab(tab_id):
            return
        closed_path = self._files.pop(tab_id, None)
        self._titles.pop(tab_id, None)
        self._dirty.pop(tab_id, None)
        self._clean_crcs.pop(tab_id, None)
        self._indent_sizes.pop(tab_id, None)
        self._codeviews.pop(tab_id, None)
        self._key_handlers.pop(tab_id, None)
        self._breadcrumbs.pop(tab_id, None)
        mc = self._multi_cursors.pop(tab_id, None)
        # Delete any temp file for this tab — user explicitly chose to close it
        _tmp = self._temp_files.pop(tab_id, None)
        if _tmp:
            try:
                Path(_tmp).unlink(missing_ok=True)
            except Exception:
                pass
        if mc:
            mc.clear()
        if closed_path and closed_path.endswith(".py"):
            for srv in self._each_lsp():
                srv.close_file(closed_path)
            # Drop diagnostics for this file so problems panel stays clean.
            # Match by normalized path because the LSP server may echo back a URI
            # with different drive-letter case or encoding than Path.as_uri() produces.
            closed_norm = os.path.normcase(os.path.normpath(closed_path))
            stale_uris = [
                u
                for u in self._lsp_diagnostics
                if os.path.normcase(os.path.normpath(uri_to_path(u))) == closed_norm
            ]
            if stale_uris:
                for u in stale_uris:
                    del self._lsp_diagnostics[u]
                entries = self._build_problem_entries()
                self._output.update_problems(entries)
                errors = sum(1 for e in entries if e.get("severity") == SEV_ERROR)
                warnings = sum(1 for e in entries if e.get("severity") == SEV_WARNING)
                self._statusbar.set_diagnostics(errors, warnings)
        nb.forget(index)
        if nb is self._notebook_r and not nb.tabs():
            # Last split tab gone — nothing to preserve, fully close the pane
            self._close_split()
        elif nb is self.notebook and not nb.tabs():
            self.view_welcome()

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_tab_changed(self, *_) -> None:
        tab_id = self._current_tab_id
        if tab_id is None:
            return
        self._encoding_pill.pack_forget()
        self._update_title()
        self._statusbar.set_indent(self._indent_sizes.get(tab_id, 4))
        # Reflect overwrite state of the new tab's handler
        handler = self._key_handlers.get(tab_id)
        ovr = handler.overwrite if handler else False
        self._statusbar.set_overwrite(ovr)
        cv = self._codeviews.get(tab_id)
        if cv is None:
            # Non-editor tab (Welcome, Package Manager, etc.) — theme sidebar from loader
            self._apply_theme_to_sidebar_no_cv()
            self._outline.clear()
            self._refresh_run_buttons()
        if cv:
            self._update_status_lexer(cv)
            if _cv_is_python(cv):
                self._outline.schedule_refresh(cv.get_text())
            else:
                self._outline.clear()
            # Invalidate breadcrumb so it re-renders for the new tab immediately
            crumb = self._breadcrumbs.get(tab_id)
            if crumb:
                crumb.invalidate()
            # Apply cached git hunks + breakpoints to this tab's gutter.
            cv.set_git_hunks(self._git_hunks.get(tab_id, []))
            self._refresh_git_hunks()
            fp = self._files.get(tab_id) or ""
            cv.set_breakpoints({ln - 1 for ln in self._breakpoints.get(fp, set())})

        # Sync run button — may need to go green when switching from a non-editor tab
        if cv is not None:
            self._refresh_run_buttons()

        # Track last real editor tab (used by AI Send File / Selection)
        if tab_id and tab_id in self._codeviews:
            self._last_editor_tab = tab_id

        # Learning Mode overlay sync — show when on learning tab, hide otherwise
        # Keep _pkg_tab in sync when the tab is closed via the × button
        if self._pkg_tab:
            try:
                tabs = self.notebook.tabs()
            except Exception:
                tabs = []
            if self._pkg_tab not in tabs:
                self._pkg_tab = None
                self._pkg_panel = None
                self._refresh_nav_bar()

        if self._learning_tab:
            try:
                tabs = self.notebook.tabs()
            except Exception:
                tabs = []
            if self._learning_tab not in tabs:
                # Tab was closed via the × button
                self._close_learning_mode()

        if self._split_active and self._split_shown:
            self._patch_scroll_callbacks()

        # Update form selector ▶ indicator when in Active Tab entry mode
        if self._designer_mode and not self._run_entry_file:
            self._refresh_form_list()

    def _reset_dirty_after_load(self, tab_id: str) -> None:
        """Clear the dirty flag after all deferred events from file load have fired.

        codeview.insert() during load fires <<ContentChanged>> with when="tail",
        which is processed after the synchronous dirty=False assignment.  A second
        after_idle pass ensures the flag is cleared even if the LSP or linter fires
        a late ContentChanged after the first pass.
        """
        if tab_id in self._dirty:
            self._dirty[tab_id] = False
            self._refresh_tab_title(tab_id)
        # Snapshot the clean CRC so subsequent identical-content edits don't dirty the tab.
        cv = self._codeviews.get(tab_id)
        if cv:
            try:
                self._clean_crcs[tab_id] = zlib.crc32(_cv_text(cv).encode())
            except Exception:
                pass
        self.after_idle(lambda tid=tab_id: self._reset_dirty_final(tid))

    def _reset_dirty_final(self, tab_id: str) -> None:
        if tab_id not in self._dirty or not self._dirty[tab_id]:
            return
        fp = self._files.get(tab_id)
        if not fp:
            return  # unsaved tab — may have been intentionally marked dirty
        cv = self._codeviews.get(tab_id)
        if cv is None:
            return
        try:
            text = _cv_text(cv)
            if text == Path(fp).read_text(encoding="utf-8"):
                self._dirty[tab_id] = False
                self._clean_crcs[tab_id] = zlib.crc32(text.encode())
                self._refresh_tab_title(tab_id)
        except Exception:
            pass

    def _on_content_changed(self) -> None:
        self._clear_runtime_error()
        if getattr(self, "_restoring", False):
            return
        tab_id = self._current_tab_id
        cv = self._current_codeview
        text: str | None = None

        if tab_id:
            clean_crc = self._clean_crcs.get(tab_id)
            if clean_crc is not None and cv:
                # Fetch text once — reused below for outline/LSP too.
                text = _cv_text(cv)
                current_crc = zlib.crc32(text.encode())
                if current_crc == clean_crc:
                    # Content matches the saved baseline — revert dirty flag if set.
                    if self._dirty.get(tab_id):
                        self._dirty[tab_id] = False
                        self._refresh_tab_title(tab_id)
                else:
                    if not self._dirty.get(tab_id):
                        self._dirty[tab_id] = True
                        self._refresh_tab_title(tab_id)
            elif not self._dirty.get(tab_id):
                self._dirty[tab_id] = True
                self._refresh_tab_title(tab_id)

        if cv and _cv_is_python(cv):
            if text is None:
                text = cv.get_text()
            self._outline.schedule_refresh(text)
            # LSP: debounced change notification
            path = self._files.get(tab_id)
            if path and (self._lsp or self._lsp_diag):
                if self._lsp_change_after_id:
                    self.after_cancel(self._lsp_change_after_id)
                self._lsp_change_after_id = self.after(
                    300,
                    lambda p=path, t=text: [
                        srv.change_file(p, t) for srv in self._each_lsp()
                    ],
                )

    # _highlight_matching_words / _on_click_release / _on_arrow_key
    # removed — canvas engine paints word-occurrence highlights and
    # bracket matches internally; no Text-tag plumbing needed.

    def _on_editor_right_click(self, event) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        # Move insert cursor to click position
        cv.mark_set("insert", f"@{event.x},{event.y}")
        word = cv.get("insert wordstart", "insert wordend").strip()

        if not hasattr(self, "_editor_menu"):
            from tkinter import Menu
            import platform as _platform

            mod = "⌘" if _platform.system() == "Darwin" else "Ctrl"

            self._editor_menu = Menu(self, tearoff=0)
            self._editor_menu.add_command(
                label="Undo",
                accelerator=f"{mod}+Z",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<Undo>>")
                ),
            )
            self._editor_menu.add_command(
                label="Redo",
                accelerator=f"{mod}+Y",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<Redo>>")
                ),
            )
            self._editor_menu.add_separator()
            self._editor_menu.add_command(
                label="Cut",
                accelerator=f"{mod}+X",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<Cut>>")
                ),
            )
            self._editor_menu.add_command(
                label="Copy",
                accelerator=f"{mod}+C",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<Copy>>")
                ),
            )
            self._editor_menu.add_command(
                label="Paste",
                accelerator=f"{mod}+V",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<Paste>>")
                ),
            )
            self._editor_menu.add_command(
                label="Select All",
                accelerator=f"{mod}+A",
                command=lambda: (
                    self._current_codeview
                    and self._current_codeview.event_generate("<<SelectAll>>")
                ),
            )
            self._editor_menu.add_separator()
            self._editor_menu.add_command(
                label="Go to Definition",
                command=self._goto_definition,
            )
            self._editor_menu.add_command(
                label="Find References",
                command=self._find_references,
            )
            self._editor_menu.add_separator()
            self._editor_menu.add_command(
                label="Find & Replace",
                command=self.edit_find_replace,
            )
            self._editor_menu.add_separator()
            self._editor_menu.add_command(
                label="Run Line",
                command=self._run_current_line,
            )
            self._editor_menu.add_command(
                label="Run Selection",
                command=self._run_selection,
            )

        # Enable/disable word-sensitive items based on whether there's a word
        has_word = bool(word and word not in _SKIP_HIGHLIGHT and not word[0].isdigit())
        self._editor_menu.entryconfigure(
            "Go to Definition", state="normal" if has_word and self._lsp else "disabled"
        )
        self._editor_menu.entryconfigure(
            "Find References", state="normal" if has_word else "disabled"
        )
        # Enable Run Selection only when there's an actual selection
        has_sel = False
        try:
            has_sel = bool(cv.tag_ranges("sel"))
        except Exception:
            pass
        self._editor_menu.entryconfigure(
            "Run Selection", state="normal" if has_sel else "disabled"
        )
        self._editor_menu.tk_popup(event.x_root, event.y_root)

    def _find_references(self) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        word = _cv_cursor_word(cv)
        if word:
            self._sidebar.show_references(word, cv)

    def _outline_navigate(self, lineno: int) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        cv.set_cursor(max(0, lineno - 1), 0)
        cv.scroll_to_line(max(0, lineno - 1))

    def _ref_navigate(self, filepath: str | None, lineno: int, col: int) -> None:
        """Tab-aware references navigation — switches to the right tab and
        positions the caret at the start of the matched word."""
        if filepath:
            self._open_file_at(filepath, lineno, col)
        else:
            self._outline_navigate(lineno)

    def _refresh_tab_title(self, tab_id: str) -> None:
        name = self._titles.get(tab_id, "Untitled")
        marker = "● " if self._dirty.get(tab_id) else ""
        git_st = self._git_tab_status.get(tab_id, "")
        suffix = f" {git_st}" if git_st else ""
        text = f"  {marker}{name}{suffix}  "
        nb = self._which_notebook(tab_id)
        try:
            nb.tab(tab_id, text=text)
        except Exception:
            pass

    def _update_title(self) -> None:
        tab_id = self._current_tab_id
        if not tab_id:
            return
        label = self._titles.get(tab_id, "Untitled")
        self.title(f"{label} – IDOL")

    def _update_status_lexer(self, cv) -> None:
        # Canvas editor exposes `language` directly; legacy CodeView
        # exposes `_lexer` (a pygments Lexer instance). Either path
        # produces the same status-bar string.
        if hasattr(cv, "language"):
            name = (cv.language or "text").title()
        else:
            name = type(cv._lexer).__name__.replace("Lexer", "") or "Text"
        self._statusbar.set_lexer(name)

    def _on_indent_change(self, size: int) -> None:
        from tkinter.font import Font

        tab_id = self._current_tab_id
        if tab_id is None:
            return
        cv = self._codeviews.get(tab_id)
        handler = self._key_handlers.get(tab_id)
        if cv:
            if hasattr(cv, "tab_size"):
                cv.tab_size = size
            else:
                cv.configure(tabs=Font(font=cv.cget("font")).measure(" " * size))
        if handler:
            handler.tab_size = size
        self._indent_sizes[tab_id] = size

    # ── LSP ───────────────────────────────────────────────────────────────────

    def _start_lsp(self) -> None:
        root = self._sidebar.explorer._root or os.getcwd()

        # Intelligence server (hover, completion, go-to-definition)
        cmd = detect_server()
        if cmd:
            self._lsp = LspManager(root, after_fn=self._safe_after)
            self._lsp.on_ready = lambda srv=self._lsp: self._lsp_open_tabs_for(srv)
            self._lsp.start(cmd)

        # Diagnostics — always PyflakesLinter (uses ruff subprocess internally)
        self._lsp_diag = PyflakesLinter(after_fn=self._safe_after)
        self._lsp_diag.on_diagnostics = self._on_lsp_diagnostics
        self._lsp_open_tabs_for(self._lsp_diag)

    def _each_lsp(self):
        """Yield each distinct active LSP/linter instance (deduped)."""
        seen: set[int] = set()
        for srv in (self._lsp, self._lsp_diag):
            if srv is not None and id(srv) not in seen:
                seen.add(id(srv))
                yield srv

    def _lsp_open_tabs_for(self, srv) -> None:
        """Open all currently loaded Python tabs in a specific LSP server."""
        for tab_id, cv in self._codeviews.items():
            if cv is None:
                continue
            path = self._files.get(tab_id)
            if path and path.endswith(".py"):
                srv.open_file(path, cv.get_text())

    def _on_lsp_diagnostics(self, uri: str, diags: list) -> None:
        """Called by LspManager when diagnostics arrive for a file."""
        # Guard against the race where a background lint thread finishes *after*
        # the tab has already been closed and its entry removed from _lsp_diagnostics.
        # Without this, the thread re-inserts stale diagnostics and they never clear.
        norm_path = uri_to_path(uri).replace("/", os.sep).replace("\\", os.sep)
        if not any(
            p and os.path.normcase(p) == os.path.normcase(norm_path)
            for p in self._files.values()
        ):
            return

        self._lsp_diagnostics[uri] = diags
        # Paint underlines on the relevant codeview
        for tab_id, path in self._files.items():
            if path and os.path.normcase(path) == os.path.normcase(norm_path):
                cv = self._codeviews.get(tab_id)
                if cv:
                    self._apply_diagnostics(cv, diags)
                break
        # Rebuild the full problems list and push to the panel
        entries = self._build_problem_entries()
        self._output.update_problems(entries)
        errors = sum(1 for e in entries if e.get("severity") == SEV_ERROR)
        warnings = sum(1 for e in entries if e.get("severity") == SEV_WARNING)
        self._statusbar.set_diagnostics(errors, warnings)

    def _build_problem_entries(self) -> list[dict]:
        """Flatten _lsp_diagnostics into a list of dicts for ProblemsPanel."""
        entries = []
        for uri, diags in self._lsp_diagnostics.items():
            filepath = uri_to_path(uri).replace("/", os.sep)
            if os.name == "nt" and filepath.startswith("\\"):
                filepath = filepath[1:]
            filename = os.path.basename(filepath)
            entries.extend(_diags_to_entries(diags, filepath, filename))
        return entries

    def _apply_diagnostics(self, codeview, diags: list) -> None:
        """Push LSP diagnostics to the editor. Canvas engine renders
        squigglies from its own diagnostic list using palette colors."""
        codeview.set_diagnostics([self._lsp_diag_to_sandbox(d) for d in diags])

    # ── Runtime error indicator ───────────────────────────────────────────────

    def _on_runtime_error(self, filepath: str, lineno: int) -> None:
        """Jump to crashed line, apply amber highlight and gutter triangle."""
        self._clear_runtime_error()
        self._open_file_at(filepath, lineno, 0)
        norm = os.path.normcase(filepath)
        for tab_id, fp in self._files.items():
            if fp and os.path.normcase(fp) == norm:
                self._runtime_error_tab_id = tab_id
                cv = self._codeviews.get(tab_id)
                if cv:
                    cv.set_runtime_error_line(lineno)
                break
        if self._output._active != "problems":
            self._output.flash_problems_tab()

    def _clear_runtime_error(self) -> None:
        """Remove the amber line highlight and gutter triangle."""
        self._output.stop_flash_problems_tab()
        if self._runtime_error_tab_id is None:
            return
        cv = self._codeviews.get(self._runtime_error_tab_id)
        if cv:
            cv.set_runtime_error_line(None)
        self._runtime_error_tab_id = None

    # ── LSP hover popup ───────────────────────────────────────────────────────

    def _on_hover_motion(self, event, cv: CanvasCodeView, path: str) -> None:
        """Debounce mouse motion; trigger hover request after 600 ms of stillness."""
        if self._completion.visible:
            return  # don't hover while the completion popup is open
        if self._hover_after_id:
            self.after_cancel(self._hover_after_id)
        self._dismiss_hover()
        self._hover_after_id = self.after(
            600, lambda: self._do_hover(event.x, event.y, cv, path)
        )

    def _do_hover(self, mx: int, my: int, cv: CanvasCodeView, path: str) -> None:
        if not self._lsp or not path:
            return
        line, col = cv._coords_from_pixel(mx, my)
        self._lsp.hover(
            path,
            line,
            col,
            lambda result: self._show_hover(result, cv, mx, my),
        )

    def _show_hover(self, result, cv: CanvasCodeView, mx: int, my: int) -> None:
        if not result:
            return
        # Extract plain text from hover result
        contents = result.get("contents", "")
        if isinstance(contents, dict):
            text = contents.get("value", "")
        elif isinstance(contents, list):
            parts = [c.get("value", c) if isinstance(c, dict) else c for c in contents]
            text = "\n".join(parts)
        else:
            text = str(contents)
        text = text.strip()
        if not text:
            return
        self._dismiss_hover()
        self._hover_popup = _HoverPopup(
            self, text, cv.canvas.winfo_rootx() + mx, cv.canvas.winfo_rooty() + my
        )

    def _cancel_hover(self) -> None:
        """Cancel any pending hover timer AND dismiss the popup."""
        if self._hover_after_id:
            self.after_cancel(self._hover_after_id)
            self._hover_after_id = None
        self._dismiss_hover()

    def _dismiss_hover(self) -> None:
        if self._hover_popup:
            try:
                self._hover_popup.destroy()
            except Exception:
                pass
            self._hover_popup = None

    # ── Git ───────────────────────────────────────────────────────────────────

    def _start_git(self) -> None:
        root = str(self._sidebar.explorer._root or os.getcwd())
        git = GitManager(root, after_fn=self._safe_after)
        self._git = git

        def _on_is_repo(ok: bool) -> None:
            if self._git is not git:
                return  # superseded by a later _start_git call — discard
            if not ok:
                self._git = None
                self._on_git_branch("")
                if self._sidebar._sc_visible:
                    self._sidebar.source_control.refresh({}, {})
                return
            self._refresh_git()

        git.is_repo(_on_is_repo)

    def _refresh_git(self) -> None:
        if not self._git:
            return
        self._git.get_branch(self._on_git_branch)
        self._git.get_status(self._on_git_status)
        self._git.get_ahead_behind(self._on_git_ahead_behind)
        # Poll every 30 s to catch external git operations
        self.after(30_000, self._refresh_git)

    def _on_git_branch(self, branch: str) -> None:
        self._statusbar.set_branch(branch)

    def _on_git_ahead_behind(self, ahead: int, behind: int) -> None:
        self._statusbar.set_ahead_behind(ahead, behind)

    def _on_git_status(self, status_map: dict) -> None:
        self._git_status = status_map
        # Update file explorer colours
        self._sidebar.explorer.apply_git_status(status_map)
        # Update tab titles
        norm_status = {os.path.normcase(k): v for k, v in status_map.items()}
        for tab_id, path in self._files.items():
            if path:
                status = norm_status.get(os.path.normcase(path), "")
                self._git_tab_status[tab_id] = status
                self._refresh_tab_title(tab_id)
        # Fetch fresh diff hunks for whichever tab is active
        self._refresh_git_hunks()
        # Keep SC panel up to date if it's visible
        if self._sidebar._sc_visible:
            self._refresh_sc_panel()
        else:
            # History refreshes independently (no file-list cost when SC hidden)
            self._refresh_history()

    def _refresh_git_hunks(self) -> None:
        tab_id = self._current_tab_id
        if not tab_id or not self._git:
            return
        path = self._files.get(tab_id)
        if not path:
            return
        self._git.get_diff_hunks(path, lambda h, tid=tab_id: self._on_git_hunks(tid, h))

    def _on_git_hunks(self, tab_id: str, hunks: list) -> None:
        self._git_hunks[tab_id] = hunks
        if tab_id == self._current_tab_id:
            cv = self._codeviews.get(tab_id)
            if cv is not None:
                cv.set_git_hunks(hunks)

    def _refresh_sc_panel(self) -> None:
        """Re-fetch staged/unstaged status and push it to the Source Control panel."""
        if not self._git:
            return
        self._git.get_full_status(self._on_sc_status)
        self._git.get_identity(self._on_sc_identity)
        self._refresh_history()

    def _on_sc_status(self, staged: dict, unstaged: dict) -> None:
        self._sidebar.source_control.refresh(staged, unstaged)

    def _on_sc_identity(self, name: str, email: str) -> None:
        self._sidebar.source_control.set_git_identity(name, email)

    # ── Source Control actions ─────────────────────────────────────────────────

    def _sc_stage(self, path: str) -> None:
        if self._git:
            self._git.stage(path, callback=self._refresh_sc_panel)

    def _sc_unstage(self, path: str) -> None:
        if self._git:
            self._git.unstage(path, callback=self._refresh_sc_panel)

    def _sc_discard(self, path: str) -> None:
        name = os.path.basename(path)
        if not askyesno(
            "Discard Changes",
            f"Discard all changes to '{name}'? This cannot be undone.",
        ):
            return
        if self._git:
            self._git.discard(path, callback=self._refresh_sc_panel)

    def _sc_commit(self, message: str) -> None:
        if not self._git:
            return

        def _done(output: str) -> None:
            self._output.output.write(f"[git commit]\n{output}\n", "info")
            self._refresh_git()
            self._refresh_sc_panel()

        self._git.commit(message, callback=_done)

    def _sc_push(self) -> None:
        if not self._git:
            return
        self._output.output.write("[git push] Running…\n", "info")

        def _done(output: str) -> None:
            self._output.output.write(f"{output}\n", "info")
            if "no configured push destination" in output or (
                "fatal" in output.lower() and "remote" in output.lower()
            ):
                self._show_remote_guide()
            self._refresh_git()

        self._git.push(callback=_done)

    def _show_remote_guide(self) -> None:
        from widgets.guide_window import GuideWindow
        import utils.git_remote_guide as git_remote_guide

        GuideWindow(
            self._sidebar, "Setting Up a Git Remote", git_remote_guide.get_pages()
        )

    def _sc_pull(self) -> None:
        if not self._git:
            return
        self._output.output.write("[git pull] Running…\n", "info")

        def _done(output: str) -> None:
            self._output.output.write(f"{output}\n", "info")
            self._refresh_git()
            self._refresh_sc_panel()

        self._git.pull(callback=_done)

    # ── Encoding fix ──────────────────────────────────────────────────────────

    def _show_encoding_pill(self) -> None:
        if not self._encoding_pill.winfo_ismapped():
            self._encoding_pill.pack(side="left", padx=(6, 0))

    def _fix_encoding(self) -> None:
        # Non-ASCII whitespace chars that look like spaces but silently
        # break Python source. Inlined from the old `widgets.codeview`.
        _BAD_PASTE_CHARS = frozenset("\xa0​      ")
        _REMOVE = frozenset(
            [0x200B]
        )  # zero-width — removing is safer than replacing with space
        cv = self._current_codeview
        if cv is None:
            return
        content = _cv_text(cv)
        fixed = "".join(
            ("" if ord(c) in _REMOVE else " ") if c in _BAD_PASTE_CHARS else c
            for c in content
        )
        if fixed != content:
            saved = cv.get_cursor()
            cv.set_text(fixed)
            cv.set_cursor(*saved)
        self._encoding_pill.pack_forget()

    # ── Clipboard History ─────────────────────────────────────────────────────

    def _capture_clipboard(self) -> None:
        """Called 50 ms after <<Copy>> / <<Cut>> to grab the clipboard content."""
        try:
            text = self.clipboard_get()
        except Exception:
            return
        if not text.strip():
            return
        tab_id = self._current_tab_id
        source = os.path.basename(self._files.get(tab_id, "") or "")
        if self._clip_panel is None:
            self._ensure_clip_panel()
        self._clip_panel.push(text, source=source)

    def _ensure_clip_panel(self) -> None:
        """Create the persistent clipboard history Toplevel on first use."""
        if self._clip_top is not None:
            return
        top = tk.Toplevel(self)
        top.withdraw()
        top.title("Clipboard History")
        top.resizable(True, True)
        top.protocol("WM_DELETE_WINDOW", top.withdraw)
        top.bind("<Escape>", lambda _: top.withdraw())

        def _paste(text: str) -> None:
            top.withdraw()
            cv = self._current_codeview
            if cv:
                cv.insert("insert", text)
                cv.focus_set()

        panel = ClipboardHistoryPanel(top, on_paste=_paste)
        panel.set_window(top)
        panel.pack(fill="both", expand=True)
        self._clip_top = top
        self._clip_panel = panel

    def view_clipboard_history(self) -> None:
        """Toggle the Clipboard History overlay (Ctrl+H)."""
        self._ensure_clip_panel()
        top = self._clip_top
        if top.state() != "withdrawn":
            top.withdraw()
            return
        # Center over the editor area
        ew = self.winfo_width()
        ex = self.winfo_rootx()
        ey = self.winfo_rooty()
        w, h = 460, 520
        x = ex + (ew - w) // 2
        y = ey + 60
        top.geometry(f"{w}x{h}+{x}+{y}")
        top.deiconify()
        top.lift()
        top.focus_force()
        self._clip_panel.focus_search()

    @staticmethod
    def _lsp_diag_to_sandbox(d: dict) -> dict:
        sev_int = d.get("severity", SEV_WARNING)
        sev = (
            "error"
            if sev_int == SEV_ERROR
            else "warning"
            if sev_int == SEV_WARNING
            else "info"
        )
        rng = d.get("range") or {}
        s = rng.get("start") or {}
        e = rng.get("end") or {}
        s_line = s.get("line", 0)
        s_col = s.get("character", 0)
        e_line = e.get("line", s_line)
        e_col = e.get("character", s_col + 1)
        # Sandbox paints one line at a time — clamp to start-line range
        return {
            "line": s_line,
            "col_start": s_col,
            "col_end": e_col if e_line == s_line else max(s_col + 1, 9999),
            "severity": sev,
            "message": d.get("message", ""),
        }

    def _sc_open_diff(self, path: str) -> None:
        """Open a read-only diff tab for *path*."""
        if not self._git:
            return

        def _show(diff_text: str) -> None:
            if not diff_text:
                return
            name = f"Δ {os.path.basename(path)}"
            self._open_diff_tab(name, diff_text)

        self._git.get_file_diff(path, _show)

    def _sc_history_diff(self, commit_hash: str, filepath: str) -> None:
        """Open a diff tab for *filepath* as changed in *commit_hash*."""
        if not self._git:
            return

        def _show(diff_text: str) -> None:
            if not diff_text:
                return
            name = f"Δ {os.path.basename(filepath)} @ {commit_hash[:7]}"
            self._open_diff_tab(name, diff_text)

        self._git.get_commit_diff(commit_hash, filepath, _show)

    def _sc_expand_commit(self, token: str) -> None:
        """Fetch file list for a commit, or load more history (load-more token)."""
        if not self._git:
            return
        if token.startswith("__load_more__:"):
            offset = int(token.split(":")[1])
            n = offset + 50

            def _on_more(commits):
                self._sidebar.source_control.refresh_history(commits)

            self._git.get_log(n, _on_more)
        else:

            def _on_files(files, h=token):
                self._sidebar.source_control.commit_files_ready(h, files)

            self._git.get_commit_files(token, _on_files)

    def _refresh_history(self) -> None:
        """Fetch the latest 50 commits and push them to the HISTORY section."""
        if not self._git or not self._sidebar._sc_visible:
            return
        git_snap = self._git
        self._git.get_log(
            50,
            lambda commits: (
                self._sidebar.source_control.refresh_history(commits)
                if self._git is git_snap
                else None
            ),
        )

    def _sc_gitignore_exists(self) -> bool:
        if not self._git:
            return False
        return os.path.exists(os.path.join(self._git._root, ".gitignore"))

    def _sc_add_to_gitignore(self, path: str) -> None:
        """Append *path* (relative to repo root) to .gitignore, creating it if needed."""
        if not self._git:
            return
        root = self._git._root
        gitignore_path = os.path.join(root, ".gitignore")
        try:
            rel = os.path.relpath(path, root).replace("\\", "/")
        except ValueError:
            rel = os.path.basename(path)

        def _run() -> None:
            # Don't add a duplicate entry
            if os.path.exists(gitignore_path):
                with open(gitignore_path, "r", encoding="utf-8") as f:
                    existing = f.read()
                if rel in existing.splitlines():
                    self.after(
                        0,
                        lambda: self._output.output.write(
                            f"[.gitignore] {rel} is already listed.\n", "info"
                        ),
                    )
                    return
                with open(gitignore_path, "a", encoding="utf-8") as f:
                    if not existing.endswith("\n"):
                        f.write("\n")
                    f.write(f"{rel}\n")
            else:
                with open(gitignore_path, "w", encoding="utf-8") as f:
                    f.write(f"{rel}\n")
            self.after(
                0,
                lambda: (
                    self._output.output.write(f"[.gitignore] Added: {rel}\n", "info"),
                    self._refresh_git(),
                    self._refresh_sc_panel(),
                ),
            )

        threading.Thread(target=_run, daemon=True).start()

    def _sc_create_gitignore(self) -> None:
        """Create a standard Python .gitignore in the repo root if absent."""
        if not self._git:
            return
        dest = os.path.join(self._git._root, ".gitignore")

        def _run() -> None:
            if os.path.exists(dest):
                self.after(
                    0,
                    lambda: self._output.output.write(
                        "[.gitignore] File already exists.\n", "stderr"
                    ),
                )
                return
            template = (
                "# Byte-compiled / optimized / DLL files\n"
                "__pycache__/\n"
                "*.py[cod]\n"
                "*$py.class\n\n"
                "# Distribution / packaging\n"
                "dist/\n"
                "build/\n"
                "*.egg-info/\n"
                ".eggs/\n\n"
                "# Virtual environments (named folders)\n"
                ".venv/\n"
                "venv/\n"
                "env/\n"
                "# Virtual environment files at repo root (macOS/Linux venv created in-place)\n"
                "bin/\n"
                "include/\n"
                "lib/\n"
                "lib64\n"
                "pyvenv.cfg\n"
                "share/\n\n"
                "# Unit test / coverage\n"
                ".pytest_cache/\n"
                ".coverage\n"
                "htmlcov/\n\n"
                "# IDEs / editors\n"
                ".vscode/\n"
                ".idea/\n"
                "*.swp\n\n"
                "# OS\n"
                ".DS_Store\n"
                "Thumbs.db\n"
            )
            with open(dest, "w", encoding="utf-8") as f:
                f.write(template)
            self.after(
                0,
                lambda: (
                    self._output.output.write("[.gitignore] Created.\n", "info"),
                    self._refresh_git(),
                    self._refresh_sc_panel(),
                ),
            )

        threading.Thread(target=_run, daemon=True).start()

    def _sc_untrack_venv(self) -> None:
        """Fix venv git tracking: add patterns to .gitignore (untracked) or git rm --cached (tracked)."""
        if not self._git:
            return
        root = self._git._root
        venv_candidates = [
            ".venv",
            "venv",
            "env",
            "bin",
            "lib",
            "lib64",
            "include",
            "share",
        ]
        import subprocess

        def _run() -> None:
            # Get current git status to distinguish untracked (??) vs tracked files
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=root,
                capture_output=True,
                text=True,
            )
            untracked_folders: list[str] = []
            tracked_folders: list[str] = []

            for name in venv_candidates:
                folder = os.path.join(root, name)
                if not os.path.isdir(folder):
                    continue
                # Check if any files from this folder appear as untracked (??) or tracked
                folder_prefix = name + "/"
                has_untracked = any(
                    line[3:].startswith(folder_prefix) or line[3:].strip() == name
                    for line in status_result.stdout.splitlines()
                    if line.startswith("??")
                )
                has_tracked = any(
                    line[3:].startswith(folder_prefix) or line[3:].strip() == name
                    for line in status_result.stdout.splitlines()
                    if not line.startswith("??")
                )
                if has_untracked:
                    untracked_folders.append(name)
                elif has_tracked:
                    tracked_folders.append(name)
                else:
                    # Folder exists but nothing shows in status — could be fully tracked
                    tracked_folders.append(name)

            did_something = False

            # Untracked venv folders → add patterns to .gitignore
            if untracked_folders:
                gitignore_path = os.path.join(root, ".gitignore")
                existing = ""
                if os.path.exists(gitignore_path):
                    with open(gitignore_path, "r", encoding="utf-8") as f:
                        existing = f.read()

                lines_to_add: list[str] = []
                for name in untracked_folders:
                    pattern = name + "/"
                    if pattern not in existing and name not in existing:
                        lines_to_add.append(pattern)

                if lines_to_add:
                    addition = (
                        "\n# Virtual Environment\n" + "\n".join(lines_to_add) + "\n"
                    )
                    with open(gitignore_path, "a", encoding="utf-8") as f:
                        f.write(addition)
                    added = ", ".join(lines_to_add)
                    self.after(
                        0,
                        lambda a=added: self._output.output.write(
                            f"[.gitignore] Added: {a}\n", "info"
                        ),
                    )
                    did_something = True
                else:
                    self.after(
                        0,
                        lambda: self._output.output.write(
                            "[.gitignore] Venv patterns already present.\n", "info"
                        ),
                    )
                    did_something = True

            # Tracked venv folders → remove from git index
            for name in tracked_folders:
                result = subprocess.run(
                    ["git", "rm", "-r", "--cached", "--ignore-unmatch", name],
                    cwd=root,
                    capture_output=True,
                    text=True,
                )
                if result.stdout.strip():
                    did_something = True
                    self.after(
                        0,
                        lambda o=result.stdout.strip(): self._output.output.write(
                            f"{o}\n", "info"
                        ),
                    )

            if did_something:
                self.after(
                    0,
                    lambda: (
                        self._output.output.write(
                            "\n[git] Venv cleanup complete. "
                            "Commit any staged removals to finish.\n",
                            "success",
                        ),
                        self._refresh_git(),
                        self._refresh_sc_panel(),
                    ),
                )
            else:
                self.after(
                    0,
                    lambda: self._output.output.write(
                        "[git] No venv folders found to fix.\n", "warning"
                    ),
                )

        if not self.output_visible_var.get():
            self.output_visible_var.set(True)
            self.view_toggle_output()
        threading.Thread(target=_run, daemon=True).start()

    def _open_diff_tab(self, title: str, diff_text: str) -> None:
        """Create a read-only syntax-colored tab showing a unified diff."""
        import tkinter as tk
        from tkinter import ttk

        frame = ttk.Frame(self.notebook)
        _cv = (
            self._codeviews.get(self._current_tab_id) if self._current_tab_id else None
        )
        _font = (
            (_cv._font.actual("family"), _cv._font.actual("size"))
            if _cv
            else ("Consolas", 11)
        )
        txt = tk.Text(
            frame,
            bg="#1e1e1e",
            fg="#cccccc",
            font=_font,
            insertwidth=0,
            relief="flat",
            padx=8,
            pady=4,
            wrap="none",
            state="normal",
        )
        txt.tag_configure("add", foreground="#4ec994")
        txt.tag_configure("remove", foreground="#f14c4c")
        txt.tag_configure("hunk", foreground="#569cd6")
        txt.tag_configure("meta", foreground="#858585")

        for line in diff_text.splitlines(keepends=True):
            if line.startswith("+++") or line.startswith("---"):
                txt.insert("end", line, "meta")
            elif line.startswith("+"):
                txt.insert("end", line, "add")
            elif line.startswith("-"):
                txt.insert("end", line, "remove")
            elif line.startswith("@@"):
                txt.insert("end", line, "hunk")
            else:
                txt.insert("end", line)

        txt.config(state="disabled")

        sb = VerticalScrollbar(frame, command=txt.yview)
        txt.configure(yscrollcommand=sb.set)
        txt.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        self.notebook.add(frame, text=f"  {title}  ")
        self.notebook.select(frame)
        tab_id = self.notebook.select()
        self._files[tab_id] = None
        self._titles[tab_id] = title
        self._dirty[tab_id] = False
        self._indent_sizes[tab_id] = 4
        self._codeviews[tab_id] = None  # not a real codeview

    # ── Completion ────────────────────────────────────────────────────────────

    def _dismiss_completion(self) -> None:
        """Hide the completion popup and cancel any pending request."""
        if self._completion_after_id:
            self.after_cancel(self._completion_after_id)
            self._completion_after_id = None
        self._completion_seq += 1
        self._completion.hide()

    def _schedule_completion(self, cv) -> None:
        if self._completion_after_id:
            self.after_cancel(self._completion_after_id)
        self._completion_seq += 1  # invalidate any in-flight callbacks
        self._completion_after_id = self.after(
            350, lambda: self._do_completion(cv, self._completion_seq)
        )

    def _do_completion(self, cv, seq: int) -> None:
        if not self._lsp or seq != self._completion_seq:
            return
        path = None
        for tid, c in self._codeviews.items():
            if c is cv:
                path = self._files.get(tid)
                break
        if not path or not path.endswith(".py"):
            return
        idx = cv.index("insert")
        line, col = idx.split(".")
        char_before = cv.get("insert-1c", "insert")
        trigger_char = char_before if char_before == "." else None
        self._lsp.completion(
            path,
            int(line) - 1,
            int(col),
            lambda items, s=seq: self._show_completion(items, cv, s),
            trigger_char=trigger_char,
        )

    def _show_completion(self, items: list, cv, seq: int) -> None:
        if seq != self._completion_seq:
            return  # stale — a newer request supersedes this one
        if not items:
            self._completion.hide()
            return
        # Sort: prefix matches first, then alphabetical
        try:
            cursor = cv.index("insert")
            line, _ = cursor.split(".")
            line_text = cv.get(f"{line}.0", cursor)
            prefix = ""
            for ch in reversed(line_text):
                if ch.isalnum() or ch == "_":
                    prefix = ch + prefix
                else:
                    break
        except Exception:
            prefix = ""
            line_text = ""
        if prefix:
            items = [
                it
                for it in items
                if it.get("label", "").lower().startswith(prefix.lower())
            ]
            if not items:
                self._completion.hide()
                return
            items = sorted(items, key=lambda it: it.get("label", "").lower())
        elif line_text[-1:] != ".":
            # No prefix and not a member-access dot — word was erased, hide
            self._completion.hide()
            return
        items = items[:20]
        bbox = cv.bbox("insert")
        if not bbox:
            return
        bx, by, _, bh = bbox
        root_x = cv.winfo_rootx() + bx
        root_y = cv.winfo_rooty() + by + bh + 2
        self._completion.show(items, root_x, root_y)

    def _accept_completion(self, cv) -> None:
        # Cancel any pending re-trigger so the popup doesn't reappear
        if self._completion_after_id:
            self.after_cancel(self._completion_after_id)
            self._completion_after_id = None
        self._completion_seq += 1
        item = self._completion.get_selected()
        self._completion.hide()
        if not item:
            return
        insert_text = item.get("insertText") or item.get("label", "")
        # Scan backwards from cursor to find the typed prefix length
        cursor = cv.index("insert")
        line, col = cursor.split(".")
        line_text = cv.get(f"{line}.0", cursor)
        prefix_len = 0
        for ch in reversed(line_text):
            if ch.isalnum() or ch == "_":
                prefix_len += 1
            else:
                break
        if prefix_len:
            cv.delete(f"{line}.{int(col) - prefix_len}", cursor)
        cv.insert("insert", insert_text)

    def _completion_click_accept(self) -> None:
        """Called when the user double-clicks an item in the popup."""
        cv = self._current_codeview
        if cv:
            self._accept_completion(cv)

    # ── Comment toggle (Ctrl+/) ───────────────────────────────────────────────

    def _toggle_comment(self, cv) -> None:
        sel = cv.tag_ranges("sel")
        if sel:
            start_line = int(cv.index(sel[0]).split(".")[0])
            end_idx = cv.index(sel[1])
            end_line = int(end_idx.split(".")[0])
            if end_idx.endswith(".0"):
                end_line -= 1
        else:
            start_line = end_line = int(cv.index("insert").split(".")[0])

        lines = [
            cv.get(f"{ln}.0", f"{ln}.end") for ln in range(start_line, end_line + 1)
        ]
        non_empty = [l for l in lines if l.strip()]
        all_commented = bool(non_empty) and all(
            l.lstrip().startswith("#") for l in non_empty
        )

        for ln in range(start_line, end_line + 1):
            text = cv.get(f"{ln}.0", f"{ln}.end")
            indent = len(text) - len(text.lstrip())
            body = text[indent:]
            if all_commented:
                if body.startswith("# "):
                    new = text[:indent] + body[2:]
                elif body.startswith("#"):
                    new = text[:indent] + body[1:]
                else:
                    continue
            else:
                if not body:
                    continue  # skip blank lines
                new = text[:indent] + "# " + body
            cv.delete(f"{ln}.0", f"{ln}.end")
            cv.insert(f"{ln}.0", new)

    # ── Go to definition ──────────────────────────────────────────────────────

    def _goto_definition(self) -> None:
        cv = self._current_codeview
        if not cv:
            return
        line_0, col = _cv_cursor_lc(cv)
        # Local search first: finds `def word` / `class word` in the current
        # buffer without any LSP round-trip.  Covers self.xxx method refs that
        # pylsp/jedi sometimes fails to resolve.
        word = self._word_at_cursor(cv)
        if word and self._goto_definition_local(cv, word):
            return
        # Fall back to LSP for cross-file / stdlib navigation.
        path = self._files.get(self._current_tab_id)
        if path and (self._lsp and self._lsp.ready):
            self._lsp.definition(path, line_0, col, self._handle_definition)

    def _word_at_cursor(self, cv) -> str:
        """Return the Python identifier token touching the cursor, or ''."""
        line_text = cv.get_line(cv.cur_line)
        col = cv.cur_col
        start = col
        while start > 0 and (
            line_text[start - 1].isalnum() or line_text[start - 1] == "_"
        ):
            start -= 1
        end = col
        while end < len(line_text) and (
            line_text[end].isalnum() or line_text[end] == "_"
        ):
            end += 1
        return line_text[start:end]

    def _goto_definition_local(self, cv, word: str) -> bool:
        """Scan the current buffer for `def word` or `class word`.

        Navigates there and returns True if found; returns False otherwise so
        the caller can fall back to the LSP.
        """
        import re

        pat = re.compile(r"^\s*(def|class)\s+" + re.escape(word) + r"\b")
        for i, line in enumerate(cv.lines):
            if pat.match(line):
                col = line.index(word)
                cv.set_cursor(i, col)
                cv.scroll_to_line(i)
                cv.canvas.focus_set()
                return True
        return False

    def _handle_definition(self, result) -> None:
        if not result:
            return
        # result may be a single Location or a list; also accept LocationLink
        # (targetUri/targetRange) for forward-compat with servers that prefer it.
        if isinstance(result, dict):
            result = [result]
        if not result:
            return
        loc = result[0]
        uri = loc.get("targetUri") or loc.get("uri", "")
        if not uri:
            return
        path = uri_to_path(uri)
        path = path.replace("/", os.sep)
        if os.name == "nt" and path.startswith("\\"):
            path = path[1:]
        rng = (
            loc.get("targetSelectionRange")
            or loc.get("targetRange")
            or loc.get("range", {})
        )
        start = rng.get("start", {})
        line = start.get("line", 0) + 1
        col = start.get("character", 0)
        self._open_file_at(path, line, col)

    def _open_file_at(self, path: str, line: int, col: int) -> None:
        """Open *path* and position cursor at *line*:*col*."""

        def _seek(cv) -> None:
            if cv is None:
                return
            cv.set_cursor(max(0, line - 1), col)
            cv.scroll_to_line(max(0, line - 1))
            cv.canvas.focus_set()

        # If already open in a tab, just switch to it
        for tab_id, fp in self._files.items():
            if fp and os.path.normcase(fp) == os.path.normcase(path):
                self.notebook.select(tab_id)
                _seek(self._codeviews.get(tab_id))
                return
        # Otherwise open as a new tab — navigation must not reset the explorer root
        if os.path.isfile(path):
            self._open_file(path, update_explorer=False)
            _seek(self._current_codeview)

    # ── Active-line highlight loop ────────────────────────────────────────────

    def _update_cursor_status(self) -> None:
        """Immediately refresh the status bar cursor count."""
        cv = self._current_codeview
        if cv is None:
            return
        line, col = cv.index("insert").split(".")
        mc = self._multi_cursors.get(self._current_tab_id)
        cursors = mc.count() if mc and mc.active else 1
        self._statusbar.set_position(int(line), int(col), cursors)

    def _start_highlight_loop(self) -> None:
        self._highlight_active_line()

    def _highlight_active_line(self) -> None:
        cv = self._current_codeview
        if cv is not None:
            # Canvas engine paints its current-line band from the
            # palette — no Text tags involved. Just read the cursor
            # for the status bar / breadcrumb sync below.
            cline, ccol = cv.get_cursor()
            line, col = cline + 1, ccol
            mc = self._multi_cursors.get(self._current_tab_id)
            cursors = mc.count() if mc and mc.active else 1
            self._statusbar.set_position(int(line), int(col), cursors)
            # Update breadcrumb (re-renders only when line changes)
            tab_id = self._current_tab_id
            crumb = self._breadcrumbs.get(tab_id)
            if crumb:
                crumb.update_crumbs(
                    filepath=self._files.get(tab_id),
                    explorer_root=str(self._sidebar.explorer._root)
                    if self._sidebar.explorer._root
                    else None,
                    cursor_line=int(line),
                    outline=self._outline,
                    is_python=_cv_is_python(cv),
                )
        self.after(25, self._highlight_active_line)

    # ── File operations ───────────────────────────────────────────────────────

    def file_new(self) -> None:
        if (
            self._split_active
            and self._split_shown
            and self._active_pane == "right"
            and self._notebook_r
        ):
            self._new_tab_in(self._notebook_r, "Untitled", "")
        else:
            self._new_tab("Untitled", "")

    def file_new_project(self) -> None:
        from widgets.project_wizard import ProjectWizard

        # Only consider tabs that have a real codeview — excludes Welcome,
        # Package Manager, Learning Mode, and any other special tabs.
        editor_tabs = [t for t in self.notebook.tabs() if self._codeviews.get(t) is not None]
        has_editor_content = any(
            self._titles.get(t) != "Untitled"
            or self._dirty.get(t)
            or bool(self._codeviews[t].get_text().strip())
            for t in editor_tabs
        )
        # Designer counts if a form is loaded AND has unsaved changes.
        # An empty canvas or a freshly-saved form doesn't trigger the prompt.
        has_designer_content = (
            getattr(self._design_canvas, "form", None) is not None
            and (self._designer_dirty or self._designer_forms_dirty)
        )
        has_project = has_editor_content or has_designer_content
        if has_project:
            answer = askyesnocancel(
                "New Project",
                "Would you like to save your current project before creating a new one?",
            )
            if answer is None:
                return  # Cancel — keep current project open
            if answer:
                self.workspace_save()
            else:
                session_utils.save(self)
            self._teardown_project()

        ProjectWizard(self, on_complete=self._on_project_created)

    def _set_explorer_root(self, path: str) -> None:
        """Set explorer root and sync terminal cwd."""
        self._sidebar.explorer.set_root(path)
        # set_root fires on_root_change which calls _on_explorer_root_change,
        # so set_cwd is already handled there — nothing else needed here.

    def _on_explorer_root_change(self, root: str) -> None:
        """Called whenever the explorer navigates to a new root directory."""
        self._output.set_cwd(root)
        self._git = None
        self._start_git()
        if hasattr(self, "_props_panel") and self._props_panel:
            self._props_panel.set_project_dir(root)
        if hasattr(self, "_design_canvas") and self._design_canvas:
            self._design_canvas.set_project_dir(root)
        if hasattr(self, "_comp_tray") and self._comp_tray:
            self._comp_tray.set_project_dir(root)
        # If the designer is open, silently drop back to editor mode so the
        # now-stale form state (from the old project root) doesn't persist into
        # the session.  Without this, closing IDOL after a root change would
        # save designer_mode_active=True with the new root, causing the new
        # project's forms to load in the designer on next launch.
        if getattr(self, "_designer_mode", False):
            self._enter_editor_mode()

    def _on_project_created(
        self,
        project_path: str,
        python_exe: str = "",
        python_label: str = "",
        venv_activate_path: str | None = None,
        project_type: str = "cli",
    ) -> None:
        """Called when the project wizard finishes — open the new project."""
        self._designer_project_type = project_type
        if project_type == "gui":
            self._show_mode_bar()
            from designer.persistence import load as designer_load
            from pathlib import Path as _Path

            json_files = sorted(_Path(project_path).glob("*.form.json"))
            if json_files:
                form, _ = designer_load(json_files[0])
                self._designer_forms[form.name] = form
                if form.name not in self._designer_form_names:
                    self._designer_form_names.append(form.name)
                self._designer_main_form = form.name
                self._design_canvas.load_form(form)
                self._props_panel.set_form(form)
                self._props_panel.load_form(form)
                self._comp_tray.refresh(form.components)
                self._comp_tray.deselect()
                self._refresh_form_list(active=form.name)
            self._refresh_generate_code_state()
        else:
            self._hide_mode_bar()
        self._set_explorer_root(project_path)
        self._git = None
        self._start_git()
        if venv_activate_path and os.path.isfile(venv_activate_path):
            import platform as _pl

            _base = os.path.dirname(venv_activate_path)
            _venv_py = os.path.join(
                _base, "python.exe" if _pl.system() == "Windows" else "python"
            )
            _activate_exe = _venv_py if os.path.isfile(_venv_py) else python_exe
            # Set interpreter synchronously so workspace_save (500 ms below) captures
            # the venv Python path before the async label refinement completes.
            self._set_active_interpreter(_activate_exe, "(.venv) Python")
            # Background thread refines the label with the exact version string.
            self._on_venv_activated(_activate_exe)
            term = self._output.terminal
            if _pl.system() == "Windows":
                term.send(f'& "{venv_activate_path}"\r')
            else:
                term.send(f'source "{venv_activate_path}"\r')
            # Ensure panel is visible without toggling (view_show_panel would
            # hide the panel if terminal was already the active tab)
            if not self.output_visible_var.get():
                self.output_visible_var.set(True)
                self.view_toggle_output()
            self._output._set_active("terminal")
        elif python_exe and os.path.isfile(python_exe):
            self._set_active_interpreter(python_exe, python_label or "Python")
        # Open the project entry point
        entry = os.path.join(project_path, "main.py")
        if os.path.isfile(entry):
            self._open_file(entry, update_explorer=False)
            self._set_run_entry(entry)
        # For GUI projects, also open the generated form file as the active tab
        if project_type == "gui":
            _active_form = self._design_canvas.form
            if _active_form:
                self.designer_generate_code()
                _form_py = os.path.join(project_path, f"{_active_form.name}.py")
                if os.path.isfile(_form_py):
                    self._open_file(_form_py, update_explorer=False)
            self._enter_designer_mode()
        recent_utils.add_project(project_path)
        # Auto-create the project file so "Open Project" works immediately
        self.after(500, self.workspace_save)

    def file_open(self, *_) -> None:
        root = str(self._sidebar.explorer._root or os.getcwd())
        path = askopenfilename(
            initialdir=root,
            filetypes=[
                ("Python Scripts", "*.py"),
                ("Text Documents", "*.txt"),
                ("All Files", "*.*"),
            ],
        )
        if path:
            self._open_file(path)

    def _open_file(
        self, path: str, update_explorer: bool = True, select: bool = True
    ) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            showerror("Open Error", str(exc))
            return

        # Remember the currently active tab so we can restore it when select=False.
        prev_tab_id = self._current_tab_id

        # If the current tab is an empty unmodified Untitled, remember it so we
        # can close it after the new tab is open (closing first would trigger the
        # "no tabs left" fallback and spawn another Untitled).
        # Only replace if prev_tab_id is actually in the main notebook (not split).
        replace = (
            select
            and prev_tab_id is not None
            and prev_tab_id in self.notebook.tabs()
            and self._titles.get(prev_tab_id) == "Untitled"
            and not self._dirty.get(prev_tab_id)
            and self._codeviews.get(prev_tab_id) is not None
            and not _cv_text(self._codeviews[prev_tab_id]).strip()
        )

        self._new_tab(os.path.basename(path), content, filepath=path)
        recent_utils.add_file(path)
        if self._welcome_panel:
            self._welcome_panel.refresh()
        # Only update the explorer root when opening externally (File > Open),
        # not when clicking a file inside the tree (would reset root unexpectedly)
        if update_explorer:
            self._set_explorer_root(path)

        if replace:
            tabs = self.notebook.tabs()
            if prev_tab_id in tabs:
                self._close_tab(tabs.index(prev_tab_id))
        elif not select and prev_tab_id and prev_tab_id in self.notebook.tabs():
            self.notebook.select(prev_tab_id)

    def _on_explorer_file_delete(self, path: str) -> None:
        """Called by the explorer after a file is deleted from disk.

        Clears the path reference on any open tab so the tooltip, title, and
        breadcrumb no longer point to the now-deleted location.
        """
        norm = os.path.normcase(path)
        for tab_id, tab_path in list(self._files.items()):
            if tab_path and os.path.normcase(tab_path) == norm:
                self._files[tab_id] = None  # no saved location
                self._dirty[tab_id] = True
                self._refresh_tab_title(tab_id)

    def _on_explorer_file_move(self, old_path: str, new_path: str) -> bool:
        """Called by the explorer before a drag/drop move.

        Checks whether the file is open and has unsaved changes; prompts the
        user if so.  Updates the open tab's path after a successful move.
        Returns True to proceed, False to cancel.
        """
        norm_old = os.path.normcase(old_path)
        open_tab_id: str | None = None
        for tab_id, path in self._files.items():
            if path and os.path.normcase(path) == norm_old:
                open_tab_id = tab_id
                break

        saved = False
        if open_tab_id and self._dirty.get(open_tab_id):
            from tkinter.messagebox import askyesnocancel

            answer = askyesnocancel(
                "Unsaved Changes",
                f'"{self._titles.get(open_tab_id, "Untitled")}" has unsaved changes.\n\n'
                "Save before moving?",
            )
            if answer is None:  # Cancel
                return False
            if answer:  # Yes — save first
                self._write_file(open_tab_id, old_path)
                saved = True

        # After the physical move succeeds (caller does shutil.move), update the tab
        if open_tab_id:
            new_title = os.path.basename(new_path)
            self._files[open_tab_id] = new_path
            self._titles[open_tab_id] = new_title
            if saved:
                self._dirty[open_tab_id] = False
            self._refresh_tab_title(open_tab_id)
            self._update_title()

        return True

    def file_save(self, *_) -> bool:
        tab_id = self._current_tab_id
        if tab_id is None:
            return False
        filepath = self._files.get(tab_id)
        if filepath is None:
            return self.file_save_as()
        return self._write_file(tab_id, filepath)

    def file_save_as(self, *_) -> bool:
        tab_id = self._current_tab_id
        if tab_id is None:
            return False
        root = str(self._sidebar.explorer._root or os.getcwd())
        path = asksaveasfilename(
            initialdir=root,
            initialfile="Untitled.py",
            defaultextension=".py",
            filetypes=[
                ("Python Scripts", "*.py"),
                ("Text Documents", "*.txt"),
                ("All Files", "*.*"),
            ],
        )
        if not path:
            return False
        return self._write_file(tab_id, path)

    def _write_file(self, tab_id: str, filepath: str) -> bool:
        cv = self._codeviews.get(tab_id)
        if cv is None:
            return False
        try:
            text = _cv_text(cv)
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            old_path = self._files.get(tab_id)
            # Update language if the filepath (and therefore extension)
            # changed — canvas engine derives it from `filepath` via
            # `set_filepath`, which also reroutes LSP / lint targeting.
            if old_path != filepath:
                cv.set_filepath(filepath)
                # LSP: close old file, open new one (Save As changed the path)
                for srv in self._each_lsp():
                    if old_path and old_path.endswith(".py"):
                        srv.close_file(old_path)
                    if filepath.endswith(".py"):
                        srv.open_file(filepath, text)
            elif filepath.endswith(".py"):
                for srv in self._each_lsp():
                    srv.save_file(filepath)
            self._files[tab_id] = filepath
            title = os.path.basename(filepath)
            self._titles[tab_id] = title
            self._dirty[tab_id] = False
            self._clean_crcs[tab_id] = zlib.crc32(text.encode())
            _tmp = self._temp_files.pop(tab_id, None)
            if _tmp:
                # Transfer any breakpoints registered against the temp path
                # to the real saved path, then clean up the temp file.
                if _tmp in self._breakpoints:
                    self._breakpoints[filepath] = self._breakpoints.pop(_tmp)
                    self._refresh_debug_breakpoints()
                    cv = self._codeviews.get(tab_id)
                    if cv:
                        cv.set_breakpoints(
                            {ln - 1 for ln in self._breakpoints.get(filepath, set())}
                        )
                # If the run entry was pinned to the temp file, redirect it to the real path
                if self._run_entry_file == _tmp:
                    self._set_run_entry(filepath)
                try:
                    Path(_tmp).unlink(missing_ok=True)
                except Exception:
                    pass
            self._refresh_tab_title(tab_id)
            self._update_title()
            # Refresh explorer (soft — preserves expanded folders) and git
            self.after(100, self._sidebar.explorer.soft_refresh)
            if self._git:
                self.after(400, self._refresh_git)
            return True
        except Exception as exc:
            showerror("Save Error", str(exc))
            return False

    def file_close(self) -> None:
        if self.notebook.tabs():
            self._close_tab(self.notebook.index("current"))

    def file_exit(self, *_) -> None:
        # No prompts on exit — dirty tabs are auto-saved to temp files by
        # session.save() so nothing is lost. Prompts only happen on tab close.
        self._do_exit()

    def _set_designer_dirty(self) -> None:
        self._designer_dirty = True
        self._designer_forms_dirty = True
        self._schedule_autogen()

    def _schedule_autogen(self) -> None:
        """Debounced auto code-gen: resets the 1.5s timer on every change."""
        if self._autogen_after_id:
            self.after_cancel(self._autogen_after_id)
        self._autogen_after_id = self.after(1500, self._run_autogen)

    def _run_autogen(self) -> None:
        """Timer callback — silently regenerate code for the active form."""
        self._autogen_after_id = None
        if not self._designer_mode:
            return
        if self._design_canvas.form is None:
            return
        self.designer_generate_code()
        self._designer_toolbar.flash_autogen()

    def designer_save_form(self) -> None:
        """Save all .form.json files (File → Designer → Save Form)."""
        self._designer_autosave()

    def _designer_autosave(self) -> None:
        """Silently save all .form.json files without regenerating Python code."""
        from pathlib import Path as _Path
        from designer.persistence import save as _save, load as _load

        root = getattr(self._sidebar.explorer, "_root", None)
        if not root:
            return
        # Sync current canvas model back into the dict before saving
        active = self._design_canvas.form
        if active and active.name in self._designer_forms:
            self._designer_forms[active.name] = active
        for form in self._designer_forms.values():
            try:
                json_path = _Path(root) / f"{form.name}.form.json"
                try:
                    _, existing_checksum = _load(json_path)
                except Exception:
                    existing_checksum = ""
                _save(form, json_path, py_checksum=existing_checksum)
            except Exception:
                pass
        self._designer_forms_dirty = False

    def _do_exit(self) -> None:
        """Save session and quit — called exactly once."""
        if getattr(self, "_exiting", False):
            return
        if self._designer_forms_dirty and self._designer_forms:
            from tkinter.messagebox import askyesnocancel

            result = askyesnocancel(
                "Unsaved Designer Changes",
                "Designer forms have unsaved changes. Save before exiting?",
                parent=self,
            )
            if result is None:  # Cancel
                return
            if result:  # Yes
                self._designer_autosave()
        self._exiting = True
        session_utils.save(self)
        if self._ai_chat_panel:
            self._ai_chat_panel.auto_save_history()
        self.quit()

    def destroy(self) -> None:
        # destroy() is called by the WM close button; route through file_exit
        # so dirty-tab prompts run.  _do_exit guards against double-save if
        # quit() triggers another destroy() before the process exits.
        self.file_exit()

    def _has_dirty_tabs(self) -> bool:
        """Return True if any open tab has unsaved changes."""
        return any(self._dirty.get(tid) for tid in self.notebook.tabs())

    def workspace_new(self, *_) -> None:
        """Close the current workspace and open a fresh one."""
        if self._has_dirty_tabs():
            answer = askyesnocancel(
                "New Workspace",
                "You have unsaved changes.\n\nSave before creating a new workspace?",
            )
            if answer is None:
                return
            if answer:
                self.workspace_save()
        session_utils.save(self)
        self._teardown_project()

    def _teardown_project(self, add_untitled: bool = True) -> None:
        """Close all tabs and reset to a clean blank state (no save prompt)."""
        for tab_id in list(self.notebook.tabs()):
            closed_path = self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._clean_crcs.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            self._key_handlers.pop(tab_id, None)
            self._breadcrumbs.pop(tab_id, None)
            self._temp_files.pop(tab_id, None)
            mc = self._multi_cursors.pop(tab_id, None)
            if mc:
                mc.clear()
            if closed_path and closed_path.endswith(".py"):
                for srv in self._each_lsp():
                    srv.close_file(closed_path)
            self.notebook.forget(tab_id)
        # Clear LSP diagnostics and breakpoints from the old project
        self._lsp_diagnostics.clear()
        self._output.update_problems([])
        self._breakpoints.clear()
        self._refresh_debug_breakpoints()
        self._welcome_tab = None
        self._welcome_panel = None
        if add_untitled:
            self.view_welcome()
        if "(.venv)" in getattr(self, "_active_python_label", ""):
            term = self._output.terminal
            if term._running and term._venv_active:
                term.send("deactivate\r")
            import sys as _sys

            self._set_active_interpreter(_sys.executable, "Python")
            self._on_venv_deactivated()
        self._set_run_entry(None)
        self._set_explorer_root(str(Path.home()))
        self._sidebar.source_control.refresh({}, {})
        self._sidebar.source_control.refresh_history([])
        # Reset designer state
        if self._autogen_after_id:
            self.after_cancel(self._autogen_after_id)
            self._autogen_after_id = None
        self.designer_close_form()
        if self._designer_mode:
            self._enter_editor_mode()
        self._hide_mode_bar()
        self._designer_project_type = "cli"

    def workspace_close(self, *_) -> None:
        """Close the current project, prompting only when there are unsaved changes."""
        if self._has_dirty_tabs():
            answer = askyesnocancel(
                "Close Project",
                "You have unsaved changes.\n\nSave before closing?",
            )
            if answer is None:
                return
            if answer:
                self.workspace_save()
        session_utils.save(self)
        self._teardown_project()

    def workspace_save(self, *_) -> None:
        """Save project to <name>.idol-project in the explorer root (no dialog needed)."""
        root = getattr(self, "_explorer_root", None) or str(
            self._sidebar.explorer._root or os.getcwd()
        )
        project_name = os.path.basename(root) or "project"
        path = os.path.join(root, f"{project_name}.idol-project")
        session_utils.save(self, path)

    def workspace_open(self, *_) -> None:
        initial = str(self._sidebar.explorer._root or os.getcwd())
        path = askopenfilename(
            title="Open Project",
            initialdir=initial,
            filetypes=[("IDOL Project files", "*.idol-project"), ("All files", "*.*")],
        )
        if not path or not os.path.isfile(path):
            return
        if self._has_dirty_tabs():
            answer = askyesnocancel(
                "Open Project",
                "You have unsaved changes.\n\nSave before opening a new project?",
            )
            if answer is None:
                return
            if answer:
                self.workspace_save()
        # Full teardown of the current project (designer, LSP diags, tabs, etc.)
        self._teardown_project(add_untitled=False)
        if session_utils.restore(self, path):
            project_dir = os.path.dirname(path)
            recent_utils.add_project(project_dir)
        else:
            self.view_welcome()

    # ── Edit operations ───────────────────────────────────────────────────────

    def _update_edit_menu_state(self) -> None:
        """Called via postcommand every time the Edit menu opens."""
        m = self._edit_menu
        if self._designer_mode:
            canvas = self._design_canvas
            has_sel = bool(canvas.selected_ids)
            has_clip = canvas._clipboard is not None
            can_undo = canvas.can_undo
            can_redo = canvas.can_redo
            has_form = canvas.form is not None
            m.entryconfigure("Undo", state="normal" if can_undo else "disabled")
            m.entryconfigure("Redo", state="normal" if can_redo else "disabled")
            m.entryconfigure("Cut", state="normal" if has_sel else "disabled")
            m.entryconfigure("Copy", state="normal" if has_sel else "disabled")
            m.entryconfigure("Paste", state="normal" if has_clip else "disabled")
            m.entryconfigure("Select All", state="normal" if has_form else "disabled")
            m.entryconfigure("Find & Replace...", state="disabled")
        else:
            cv = self._current_codeview
            try:
                has_clip = bool(self.clipboard_get())
            except Exception:
                has_clip = False
            has_sel = False
            if cv:
                try:
                    cv.get("sel.first", "sel.last")
                    has_sel = True
                except Exception:
                    pass
            can_undo = bool(cv and getattr(cv, "can_undo", True))
            can_redo = bool(cv and getattr(cv, "can_redo", True))
            m.entryconfigure("Undo", state="normal" if can_undo else "disabled")
            m.entryconfigure("Redo", state="normal" if can_redo else "disabled")
            m.entryconfigure("Cut", state="normal" if has_sel else "disabled")
            m.entryconfigure("Copy", state="normal" if has_sel else "disabled")
            m.entryconfigure("Paste", state="normal" if has_clip else "disabled")
            m.entryconfigure("Select All", state="normal" if cv else "disabled")
            m.entryconfigure("Find & Replace...", state="normal" if cv else "disabled")

    def edit_undo(self) -> None:
        if self._designer_mode:
            self._design_canvas.undo()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Undo>>")

    def edit_redo(self) -> None:
        if self._designer_mode:
            self._design_canvas.redo()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Redo>>")

    def edit_cut(self) -> None:
        if self._designer_mode:
            self._design_canvas.copy_selected()
            self._design_canvas.remove_selected()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Cut>>")

    def edit_copy(self) -> None:
        if self._designer_mode:
            self._design_canvas.copy_selected()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Copy>>")

    def edit_paste(self) -> None:
        if self._designer_mode:
            self._design_canvas.paste()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Paste>>")

    def edit_select_all(self) -> None:
        if self._designer_mode:
            self._design_canvas.select_all()
            return
        cv = self._current_codeview
        if cv:
            cv.event_generate("<Control-a>")

    def edit_find_replace(self, *_) -> None:
        if self._designer_mode:
            return
        cv = self._current_codeview
        if cv is None:
            return
        self._find_replace.show(cv)

    # ── View operations ───────────────────────────────────────────────────────

    def view_change_theme(self) -> None:
        """Apply the selected theme to every canvas tab + the sidebar."""
        scheme = self.theme_var.get()
        for cv in self._codeviews.values():
            if cv is not None:
                cv.set_theme(scheme)
        cv = self._current_codeview
        if cv is None:
            self._apply_theme_to_sidebar_no_cv()
            return
        pal = cv._palette
        self._active_line_color = pal.get("current_line_bg")
        self._sidebar.apply_theme(
            bg=pal["bg"],
            fg=pal["fg"],
            select_bg=pal.get("select_bg", "#264f78"),
            codeview=cv,
            kind=_theme_kind(scheme),
        )
        self._update_status_lexer(cv)

    def _apply_theme_to_sidebar_no_cv(self) -> None:
        """Apply theme palette to the sidebar when no codeview is active (e.g. Welcome tab)."""
        from utils.theme_loader import load_theme

        try:
            theme = load_theme(self.theme_var.get())
            pal = theme["palette"]
            self._sidebar.apply_theme(
                bg=pal.get("bg", "#1e1e1e"),
                fg=pal.get("fg", "#cccccc"),
                select_bg=pal.get("select_bg", "#264f78"),
                codeview=None,
                kind=_theme_kind(self.theme_var.get()),
            )
        except Exception:
            pass

    def view_change_font(self, *_) -> None:
        font = askfont(self)
        if not font:
            return
        family = font["family"]
        size = int(font["size"])
        weight = font.get("weight", "normal") or "normal"
        slant = font.get("slant", "roman") or "roman"
        self._editor_font = (family, size, weight, slant)
        for cv in self._codeviews.values():
            if cv is not None:
                cv.set_font(family, size, weight, slant)

    def view_toggle_highlight(self) -> None:
        enabled = self.highlight_line_var.get()
        for cv in self._codeviews.values():
            if cv is not None:
                cv.highlight_active_line = enabled
                cv.render()

    def view_active_line_color(self) -> None:
        result = askcolor(self._active_line_color or "#ffffff", parent=self)
        color = result[1] if result else None
        if color:
            self._active_line_color = color
            for cv in self._codeviews.values():
                if cv is not None:
                    cv._active_line_color = color
                    cv.render()

    def view_toggle_output(self) -> None:
        if self.output_visible_var.get():
            self._v_pane.add(self._output, weight=1)
        else:
            self._v_pane.forget(self._output)

    def view_show_panel(self, tab: str) -> None:
        """Show the panel area and switch to *tab*, or hide if already active."""
        if self.output_visible_var.get() and self._output._active == tab:
            self.output_visible_var.set(False)
            self.view_toggle_output()
        else:
            if not self.output_visible_var.get():
                self.output_visible_var.set(True)
                self.view_toggle_output()
            self._output._set_active(tab)

    def view_new_terminal(self) -> None:
        self.view_show_panel("terminal")

    def view_toggle_minimap(self) -> None:
        show = self.minimap_visible_var.get()
        for cv in self._codeviews.values():
            if cv is None:
                continue
            if show:
                cv.show_minimap()
            else:
                cv.hide_minimap()
        self._refresh_nav_bar()

    def view_split_editor(self) -> None:
        """Toggle split editor visibility (never destroys tabs)."""
        if self._split_active:
            if self._split_shown:
                self._hide_split()
            else:
                self._show_split()
            return

        # First open: move current tab if there are multiple, otherwise open fresh Untitled
        tab_id = self._current_tab_id
        if tab_id and tab_id != self._welcome_tab and len(self.notebook.tabs()) > 1:
            self._move_to_split(tab_id)
        else:
            self._ensure_split_shown()
            self._new_tab_in(self._notebook_r, "Untitled", "")

    def view_fold_all(self) -> None:
        cv = self._current_codeview
        if not cv:
            return
        for i in range(len(cv.lines)):
            if cv._line_is_foldable(i):
                cv.folded.add(i)
        cv.render()

    def view_unfold_all(self) -> None:
        cv = self._current_codeview
        if not cv:
            return
        cv.folded.clear()
        cv.render()

    def _refresh_nav_bar(self) -> None:
        """Sync nav bar toggle button colors with current view state."""
        pairs = [
            (
                getattr(self, "_nav_split_btn", None),
                lambda: self._split_active and self._split_shown,
            ),
            (
                getattr(self, "_nav_map_btn", None),
                lambda: self.minimap_visible_var.get(),
            ),
            (getattr(self, "_nav_sidebar_btn", None), lambda: self._sidebar_shown),
            (getattr(self, "_nav_zen_btn", None), lambda: self._zen_mode),
            (getattr(self, "_nav_ai_btn", None), lambda: self._ai_panel_visible),
            (getattr(self, "_nav_pkg_btn", None), lambda: bool(self._pkg_tab)),
            (getattr(self, "_nav_learn_btn", None), lambda: bool(self._learning_tab)),
        ]
        for btn, active_fn in pairs:
            if btn is not None:
                try:
                    btn.config(fg="#007acc" if active_fn() else "#858585")
                except Exception:
                    pass

    # ── Welcome tab ───────────────────────────────────────────────────────────

    def view_welcome(self) -> None:
        """Open (or focus) the Welcome tab."""
        if self._welcome_tab:
            try:
                if self._welcome_tab not in self.notebook.tabs():
                    raise ValueError
                if self.notebook.select() == self._welcome_tab:
                    # Already focused — do nothing (don't close on second press)
                    return
                self.notebook.select(self._welcome_tab)
                if self._welcome_panel:
                    self._welcome_panel.refresh()
                return
            except Exception:
                self._welcome_tab = None
                self._welcome_panel = None

        frame = ttk.Frame(self.notebook)
        panel = WelcomePanel(
            frame,
            on_new_file=self.file_new,
            on_open_file=self._welcome_open_file,
            on_open_folder=self.workspace_open,
            on_new_project=self.file_new_project,
            on_open_project=self._welcome_open_project,
            on_learning=self.view_learning_mode,
            on_designer=self._enter_designer_mode,
            on_packages=self.view_package_manager,
        )
        panel.pack(fill="both", expand=True)
        self.notebook.add(frame, text="  Welcome  ")
        self.notebook.select(frame)
        self._welcome_tab = self.notebook.select()
        self._welcome_panel = panel
        self._apply_theme_to_sidebar_no_cv()

    def _welcome_open_file(self, path: str | None = None) -> None:
        if path:
            self._open_file(path)
        else:
            self.file_open()

    def _welcome_open_project(self, path: str | None = None) -> None:
        """Open a project — from a direct path (recent) or via dialog."""
        if not path:
            self.workspace_open()
            return
        # Find the .idol-project file inside the project directory
        from pathlib import Path as _P

        proj_dir = _P(path)
        candidate = proj_dir / f"{proj_dir.name}.idol-project"
        if not candidate.is_file():
            candidates = list(proj_dir.glob("*.idol-project"))
            candidate = candidates[0] if candidates else None
        if candidate and candidate.is_file():
            # Reuse workspace_open flow without the file dialog
            if self._has_dirty_tabs():
                from tkinter.messagebox import askyesnocancel as _aync

                answer = _aync(
                    "Open Project", "You have unsaved changes.\n\nSave before opening?"
                )
                if answer is None:
                    return
                if answer:
                    self.workspace_save()
            self._teardown_project(add_untitled=False)
            if not session_utils.restore(self, str(candidate)):
                self.view_welcome()
        else:
            showerror("Open Project", f"Could not find a project file in:\n{path}")
            recent_utils.remove_project(path)
            if self._welcome_panel:
                self._welcome_panel.refresh()

    # ── Package Manager ───────────────────────────────────────────────────────

    def view_package_manager(self) -> None:
        """Toggle the Package Manager tab (F3)."""
        if self._pkg_tab:
            try:
                tabs = self.notebook.tabs()
                if self._pkg_tab not in tabs:
                    raise ValueError
                if self.notebook.select() == self._pkg_tab:
                    # Already focused — close it
                    idx = list(tabs).index(self._pkg_tab)
                    self.notebook.forget(idx)
                    self._pkg_tab = None
                    self._pkg_panel = None
                    self._refresh_nav_bar()
                    return
                else:
                    self.notebook.select(self._pkg_tab)
                    self._refresh_nav_bar()
                    return
            except Exception:
                self._pkg_tab = None
                self._pkg_panel = None

        frame = ttk.Frame(self.notebook)
        panel = PackageManagerPanel(
            frame,
            get_output_panel=lambda: self._output.output,
            get_ai_panel=lambda: self._ai_chat_panel,
            open_ai_panel=self._ensure_ai_panel_open,
        )
        panel.pack(fill="both", expand=True)
        panel.set_python(self._active_python)
        self.notebook.add(frame, text="📦 Packages")
        self.notebook.select(frame)
        self._pkg_tab = self.notebook.select()
        self._pkg_panel = panel
        self._refresh_nav_bar()

    # ── Learning Mode ─────────────────────────────────────────────────────────

    def _close_learning_mode(self) -> None:
        """Unconditionally close the learning tab and restore all widget state."""
        if not self._learning_tab:
            return
        try:
            idx = list(self.notebook.tabs()).index(self._learning_tab)
            self.notebook.forget(idx)
        except Exception:
            pass
        self._learning_tab = None
        self._learning_panel = None
        self._learning_deactivate_cursors()
        self._refresh_nav_bar()

    def view_learning_mode(self) -> None:
        """Toggle the Learning Mode tab (F1)."""
        if self._learning_tab:
            try:
                if self._learning_tab not in self.notebook.tabs():
                    raise ValueError
                if self.notebook.select() == self._learning_tab:
                    self._close_learning_mode()
                    return
                else:
                    self.notebook.select(self._learning_tab)
                    self._refresh_nav_bar()
                    return
            except Exception:
                self._close_learning_mode()
                return

        frame = ttk.Frame(self.notebook)
        panel = LearningPanel(frame)
        panel.pack(fill="both", expand=True)

        self.notebook.add(frame, text="  📖 Learning  ")
        self.notebook.select(frame)

        self._learning_tab = self.notebook.select()
        self._learning_panel = panel
        self._learning_active_lid = ""

        self._learning_activate_cursors()
        self._refresh_nav_bar()

    def view_ai_chat(self) -> None:
        """Toggle the AI Chat right panel (F2)."""
        if self._ai_panel_visible:
            # Save current width before hiding — measure the frame directly
            # because sashpos() returns unreliable values on macOS.
            try:
                w = self._ai_panel_frame.winfo_width()
                if w > 50:
                    self._ai_panel_width = max(280, w)
            except Exception:
                pass
            self._h_pane.forget(self._ai_panel_frame)
            self._ai_panel_visible = False
        else:
            self._ai_panel_frame.configure(width=self._ai_panel_width)
            self._h_pane.add(self._ai_panel_frame, minsize=280, stretch="never")
            self._ai_panel_visible = True
            self.after(100, self._apply_ai_panel_sash)
            if self._ai_chat_panel:
                self.after(200, self._ai_chat_panel.recheck_ollama)
        self._refresh_nav_bar()

    def _ensure_ai_panel_open(self) -> None:
        """Open the AI Chat panel if it isn't already visible."""
        if not self._ai_panel_visible:
            self._ai_panel_frame.configure(width=self._ai_panel_width)
            self._h_pane.add(self._ai_panel_frame, minsize=280, stretch="never")
            self._ai_panel_visible = True
            self.after(100, self._apply_ai_panel_sash)
            if self._ai_chat_panel:
                self.after(200, self._ai_chat_panel.recheck_ollama)

    def _apply_ai_panel_sash(self) -> None:
        """Position the sash so the AI panel has its saved width.

        Always uses a <Configure> binding instead of calling sashpos()
        immediately, because any sashpos() call made synchronously after
        add() gets overridden by tkinter's geometry pass — especially on
        macOS where the pane already has a real width before add().
        """
        _cbid: list = []

        def _set_sash(event=None):
            w = self._h_pane.winfo_width()
            if w < 10:
                return
            try:
                self._h_pane.unbind("<Configure>", _cbid[0])
            except Exception:
                pass
            try:
                target = max(200, w - self._ai_panel_width)
                current = _sash_get(self._h_pane, 1)
                if abs(current - target) > 4:
                    _sash_set(self._h_pane, 1, target)
            except Exception:
                pass
            # Notify AI chat so it can re-snap to bottom after this resize
            if self._ai_chat_panel:
                self.after(50, self._ai_chat_panel._on_ai_panel_sash_done)

        _cbid.append(self._h_pane.bind("<Configure>", _set_sash))
        # Fallback: also fire after 500ms in case <Configure> doesn't trigger
        self.after(500, lambda: _set_sash() if _cbid else None)

    def _ai_get_file_content(self) -> tuple[str, str]:
        """Return (filename, content) of the last active editor tab."""
        tab_id = self._last_editor_tab or self._current_tab_id
        cv = self._codeviews.get(tab_id) if tab_id else None
        if not cv or not tab_id:
            return ("", "")
        filepath = self._files.get(tab_id, "")
        filename = os.path.basename(filepath) if filepath else "Untitled"
        return (filename, _cv_text(cv))

    def _ai_get_selection(self) -> str:
        """Return selected text from the last active editor."""
        tab_id = self._last_editor_tab or self._current_tab_id
        cv = self._codeviews.get(tab_id) if tab_id else None
        if not cv:
            return ""
        try:
            return cv.selected_text()
        except Exception:
            return ""

    def _ask_ai_about_problems(self) -> None:
        """Build a beginner-friendly prompt from current diagnostics and send to AI Chat."""
        filename, source = self._ai_get_file_content()
        if not source:
            return
        entries = self._build_problem_entries()
        # Only errors and warnings — skip pure style info
        actionable = [
            e for e in entries if e.get("severity") in (SEV_ERROR, SEV_WARNING)
        ]
        if not actionable:
            return

        sev_label = {SEV_ERROR: "Error", SEV_WARNING: "Warning"}
        error_lines = "\n".join(
            f"  • Line {e['line']} — {sev_label.get(e['severity'], 'Issue')}: {e['message']}"
            for e in actionable
        )
        ctx = f"# File: {filename}\n\n{source}"
        user_text = (
            f"I have some problems in my Python file '{filename}'.\n\n"
            f"Problems found:\n{error_lines}\n\n"
            f"Please help me fix them:\n"
            f"1. Explain each problem in plain English (one sentence each)\n"
            f"2. Show exactly what lines need to change\n"
            f"3. Show the complete corrected file"
        )
        self._ensure_ai_panel_open()
        if self._ai_chat_panel:
            self._ai_chat_panel.ask_with_context(user_text, ctx)

    def _ask_ai_about_entry(self, entry: dict) -> None:
        """Double-click on a single problem — ask AI for explanation + example + fix."""
        sev_label = {SEV_ERROR: "error", SEV_WARNING: "warning"}.get(
            entry.get("severity"), "issue"
        )
        msg = entry.get("message", "")
        filename = entry.get("filename", "")
        line = entry.get("line", 0)
        user_text = (
            f"I have a Python {sev_label} on line {line} of '{filename}':\n\n"
            f"  {msg}\n\n"
            f"Please:\n"
            f"1. Explain what this {sev_label} means in plain English\n"
            f"2. Show a simple example of code that causes this same problem\n"
            f"3. Show the fixed version of that example"
        )
        self._ensure_ai_panel_open()
        if self._ai_chat_panel:
            self._ai_chat_panel.ask_with_context(user_text, "")

    def _register_learning_widgets(self) -> None:
        """Tag all known IDE widgets with their learning IDs."""
        LM = LearningManager

        # Sidebar section headers — overlay on header only, not the large body panel
        LM.register(self._sidebar._outline_hdr, "outline_panel")
        LM.register(self._sidebar.outline, "outline_panel", overlay=False)
        LM.register(self._sidebar._refs_hdr, "references_panel")
        LM.register(self._sidebar.references, "references_panel", overlay=False)
        LM.register(self._sidebar._sc_hdr, "source_control_panel")
        LM.register(self._sidebar.source_control, "source_control_panel", overlay=False)
        LM.register(self._sidebar.source_control._health_hdr, "git_health_panel")
        LM.register(
            self._sidebar.source_control._staged_sec._hdr, "source_control_panel"
        )
        LM.register(
            self._sidebar.source_control._unstaged_sec._hdr, "source_control_panel"
        )
        LM.register(self._sidebar.source_control._history_sec._hdr, "commit_history")
        LM.register(self._sidebar._explorer_hdr, "explorer_panel")

        # Source control action buttons
        sc = self._sidebar.source_control
        LM.register(sc._commit_btn, "sc_commit_btn")
        LM.register(sc._push_btn, "sc_push_btn")
        LM.register(sc._pull_btn, "sc_pull_btn")

        # Status bar segments
        LM.register(self._statusbar._pos_lbl, "statusbar_position")
        LM.register(self._statusbar._branch_lbl, "statusbar_branch")
        LM.register(self._statusbar._lexer_lbl, "statusbar_lexer")
        LM.register(self._statusbar._indent_lbl, "statusbar_indent")

        # Find & Replace bar
        LM.register(self._find_replace, "find_replace_bar")

        # Output / Terminal / Problems / Debug — tab buttons get overlays, large panels don't
        LM.register(self._output.output_tab_btn, "output_panel")
        LM.register(self._output.output_tab_lbl, "output_panel")
        LM.register(self._output.terminal_tab_btn, "terminal_panel")
        LM.register(self._output.terminal_tab_lbl, "terminal_panel")
        LM.register(self._output.problems_tab_btn, "problems_panel")
        LM.register(self._output.problems_tab_lbl, "problems_panel")
        LM.register(self._output.debug_tab_btn, "debug_panel")
        LM.register(self._output.debug_tab_lbl, "debug_panel")
        LM.register(self._output.output, "output_panel", overlay=False)
        LM.register(self._output.terminal, "terminal_panel", overlay=False)
        LM.register(self._output.problems, "problems_panel", overlay=False)
        LM.register(self._output.debug, "debug_panel", overlay=False)

        # Tab bar slot controls
        LM.register(self._output.output._guide_btn, "output_panel")
        LM.register(self._output.output._clear_btn, "output_panel")
        LM.register(self._output.terminal._restart_btn, "terminal_panel")
        LM.register(self._output.terminal._term_clear_btn, "terminal_panel")
        LM.register(self._output.terminal._venv_btn, "terminal_panel")
        LM.register(self._output._popout_lbl, "debug_panel")

        # Debug toolbar buttons
        LM.register(self._dbg_continue_btn, "dbg_continue")
        LM.register(self._dbg_over_btn, "dbg_step_over")
        LM.register(self._dbg_in_btn, "dbg_step_in")
        LM.register(self._dbg_out_btn, "dbg_step_out")
        LM.register(self._dbg_stop_btn, "dbg_stop")

        # AI Chat input box
        LM.register(self._ai_chat_panel._input, "ai_chat")

    # Tkinter bindtag used to intercept all clicks while learning mode is active
    _LM_TAG = "LearningMode"

    def _learning_activate_cursors(self) -> None:
        """Enter learning mode: set cursors on registered widgets + intercept all clicks."""
        # Show debug bar so users can learn the controls even without a live session
        self._show_debug_bar()
        self._learning_reg_map = {w: l for w, l in LearningManager.all_registrations()}
        LearningManager.set_active(True)
        LearningManager.set_click_handler(self._on_learning_click)
        for widget in self._learning_reg_map:
            try:
                widget.config(cursor=get_learn_cursor())
            except Exception:
                pass
        self._nav_learn_btn.config(cursor="hand2")
        self._learning_install_bindtag()

    def _learning_adopt_widgets(self, *widgets) -> None:
        """Add newly created widgets into an already-active learning mode session."""
        if not self._learning_tab:
            return
        for w in widgets:
            lid = LearningManager._widget_lid.get(w)
            if lid:
                self._learning_reg_map[w] = lid
            try:
                w.config(cursor=get_learn_cursor())
            except Exception:
                pass
            for child in self._iter_all_widgets(w):
                try:
                    tags = child.bindtags()
                    if self._LM_TAG not in tags:
                        child.bindtags((self._LM_TAG,) + tags)
                except Exception:
                    pass

    def _learning_deactivate_cursors(self) -> None:
        """Leave learning mode: remove bindtag intercept + restore cursors."""
        # Hide debug bar again unless a real session is active
        if not self._debugger:
            self._hide_debug_bar()
        LearningManager.set_active(False)
        self._learning_remove_bindtag()
        for widget, _lid in LearningManager.all_registrations():
            orig = LearningManager.get_widget_originals(widget)
            try:
                widget.config(cursor=orig.get("cursor", ""))
            except Exception:
                pass
        self._learning_reg_map = {}
        self._nav_learn_btn.config(cursor=get_learn_cursor())

    def _iter_all_widgets(self, widget=None):
        """Yield every widget in this window recursively, skipping other Toplevels."""
        root = widget if widget is not None else self
        if root is not self and isinstance(root, tk.Toplevel):
            return
        yield root
        try:
            children = root.winfo_children()
        except Exception:
            return
        for child in children:
            try:
                yield from self._iter_all_widgets(child)
            except Exception:
                pass

    def _learning_install_bindtag(self) -> None:
        """Prepend LearningMode bindtag to every widget so clicks are intercepted first."""
        self.bind_class(self._LM_TAG, "<Button-1>", self._learning_click_intercept)
        for w in self._iter_all_widgets():
            try:
                tags = w.bindtags()
                if self._LM_TAG not in tags:
                    w.bindtags((self._LM_TAG,) + tags)
            except Exception:
                pass

    def _learning_remove_bindtag(self) -> None:
        """Remove the LearningMode bindtag from every widget."""
        for w in self._iter_all_widgets():
            try:
                tags = w.bindtags()
                if self._LM_TAG in tags:
                    w.bindtags(tuple(t for t in tags if t != self._LM_TAG))
            except Exception:
                pass

    def _learning_click_intercept(self, event) -> str:
        """Bindtag handler — fires before any widget binding on every click."""
        if not self._learning_tab:
            return
        # Let the Learning nav button always close learning mode
        if event.widget is getattr(self, "_nav_learn_btn", None):
            self._close_learning_mode()
            return "break"
        # Let < > + nav buttons keep working during learning mode
        if event.widget in (
            getattr(self, "_prev_btn", None),
            getattr(self, "_next_btn", None),
            getattr(self, "_plus_btn", None),
        ):
            return
        # Let notebook tab bar clicks (tab switching, X close) fall through
        nb_r = getattr(self, "_notebook_r", None)
        if event.widget is self.notebook or (nb_r and event.widget is nb_r):
            return
        if event.widget is getattr(self.notebook, "_hover_btn", None):
            return
        if nb_r and event.widget is getattr(nb_r, "_hover_btn", None):
            return
        # Let clicks inside the learning panel itself fall through untouched
        try:
            lf = self.nametowidget(self._learning_tab)
            w = event.widget
            while w is not None:
                if w is lf:
                    return
                w = getattr(w, "master", None)
        except Exception:
            pass
        # Route to content if the click lands on or inside a registered widget
        widget, lid = self._find_learning_registration(event.widget)
        if widget is not None:
            self._on_learning_click(widget, lid)
        return "break"

    def _find_learning_registration(self, widget):
        """Walk up the parent chain to find the nearest registered ancestor."""
        w = widget
        while w is not None:
            if w in self._learning_reg_map:
                return w, self._learning_reg_map[w]
            w = getattr(w, "master", None)
        return None, None

    def _on_learning_click(self, widget, lid: str) -> None:
        """Show guide content and flash the clicked widget."""
        self._learning_active_lid = lid
        try:
            self.notebook.select(self._learning_tab)
        except Exception:
            pass
        if self._learning_panel:
            self._learning_panel.show(lid)
        self._learning_flash(widget)

    def _learning_flash(self, widget) -> None:
        """Flash *widget* with a blue highlight for 400 ms."""
        from tkinter import ttk as _ttk

        if isinstance(widget, _ttk.Treeview):
            return
        orig = LearningManager.get_widget_originals(widget)
        try:
            widget.config(highlightbackground="#007acc", highlightthickness=2)
            self.after(
                400,
                lambda: self._learning_flash_restore(
                    widget,
                    orig.get("highlightbackground", ""),
                    orig.get("highlightthickness", 0),
                ),
            )
        except Exception:
            pass

    def _learning_flash_restore(self, widget, hbg: str, ht: int) -> None:
        try:
            widget.config(highlightbackground=hbg, highlightthickness=ht)
        except Exception:
            pass

    # ── Zen mode ──────────────────────────────────────────────────────────────

    def view_zen_mode(self) -> None:
        """Toggle Zen mode — full-screen editor, no distractions."""
        if self._zen_mode:
            self._exit_zen()
        else:
            self._enter_zen()

    def _enter_zen(self) -> None:
        self._zen_mode = True
        self.zen_mode_var.set(True)
        # If the Designer is active, normalise to editor layout first so the
        # Zen entry logic always operates on the same [sidebar | v_pane] shape.
        self._zen_was_designer = self._designer_mode
        if self._designer_mode:
            self._enter_editor_mode()
        self._zen_sidebar_was_visible = self._sidebar_shown
        if self._sidebar_shown:
            self._h_pane.forget(self._sidebar)
            self._sidebar_shown = False
        if self._ai_panel_visible:
            self._h_pane.forget(self._ai_panel_frame)
        if self.output_visible_var.get():
            self._v_pane.forget(self._output)
        self._statusbar.pack_forget()
        self.title("IDOL  [Zen]")
        self._refresh_nav_bar()
        self._show_zen_pill()

    def _exit_zen(self) -> None:
        self._zen_mode = False
        self.zen_mode_var.set(False)
        self._statusbar.pack(side="bottom", fill="x", before=self._h_pane)
        # tk.PanedWindow has no insert() — rebuild the pane order so sidebar
        # goes back at position 0: forget v_pane, add sidebar, re-add v_pane.
        restore_sidebar = getattr(self, "_zen_sidebar_was_visible", True)
        self._h_pane.forget(self._v_pane)
        if restore_sidebar:
            self._h_pane.add(self._sidebar, minsize=220, stretch="never")
            self._sidebar_shown = True
        self._h_pane.add(self._v_pane, stretch="always")

        if self._ai_panel_visible:
            self._h_pane.add(self._ai_panel_frame, minsize=280, stretch="never")
            self.after(100, self._apply_ai_panel_sash)
        if self.output_visible_var.get():
            self._v_pane.add(self._output, weight=1)
        self.title("IDOL")
        self._refresh_nav_bar()
        self._dismiss_zen_pill()
        # Restore Designer if that's where we came from.
        if getattr(self, "_zen_was_designer", False):
            self._enter_designer_mode()

    def _on_escape(self, _=None) -> None:
        if self._zen_mode:
            self._exit_zen()

    def _show_zen_pill(self) -> None:
        """Show a floating 'Esc — Exit Zen' pill that fades away after 2s."""
        import tkinter as tk

        self._dismiss_zen_pill()
        pill = tk.Toplevel(self)
        pill.overrideredirect(True)
        pill.attributes("-topmost", True)
        pill.configure(bg="#3c3c3c")

        lbl = tk.Label(
            pill,
            text="  Esc — Exit Zen  ",
            bg="#3c3c3c",
            fg="#cccccc",
            font=(UI_FONT, 9),
            pady=6,
            padx=4,
        )
        lbl.pack()

        # Centre the pill at the bottom of the editor area
        self.update_idletasks()
        w = lbl.winfo_reqwidth() + 8
        h = lbl.winfo_reqheight() + 4
        sx = self.winfo_rootx() + (self.winfo_width() - w) // 2
        sy = self.winfo_rooty() + self.winfo_height() - h - 48
        pill.geometry(f"{w}x{h}+{sx}+{sy}")
        self._zen_pill = pill

        # Fade out over ~1s starting after 2s
        self.after(2000, lambda: self._fade_pill(pill, 1.0))

    def _fade_pill(self, pill, alpha: float) -> None:
        if pill is None or not self._zen_pill:
            return
        try:
            if alpha <= 0.0:
                pill.destroy()
                self._zen_pill = None
                return
            pill.attributes("-alpha", alpha)
            self.after(40, lambda: self._fade_pill(pill, round(alpha - 0.05, 2)))
        except Exception:
            self._zen_pill = None

    def _dismiss_zen_pill(self) -> None:
        if self._zen_pill:
            try:
                self._zen_pill.destroy()
            except Exception:
                pass
            self._zen_pill = None

    # ── Designer mode ─────────────────────────────────────────────────────────

    def _refresh_generate_code_state(self) -> None:
        menu = getattr(self, "_designer_menu", None)
        if menu is None:
            return
        form_loaded = getattr(self._design_canvas, "_form", None) is not None
        state = "normal" if form_loaded else "disabled"
        menu.entryconfigure("Generate Code", state=state)
        menu.entryconfigure("Save Form", state=state)

    def _show_mode_bar(self) -> None:
        """Pack the [Editor] | [Designer] strip above the notebook."""
        before = self._designer_frame if self._designer_mode else self.notebook
        self._mode_bar.pack(fill="x", side="top", before=before)
        self._refresh_mode_bar()
        if self._split_active and hasattr(self, "_split_mode_bar_spacer"):
            self._split_mode_bar_spacer.pack(fill="x", before=self._notebook_r)

    def _hide_mode_bar(self) -> None:
        """Remove the mode bar and force editor mode."""
        self._enter_editor_mode()
        self._mode_bar.pack_forget()
        if hasattr(self, "_split_mode_bar_spacer"):
            self._split_mode_bar_spacer.pack_forget()

    def _refresh_mode_bar(self) -> None:
        """Sync button colours to the active mode."""
        act, dim = "#ffffff", "#6a6a6a"
        if self._designer_mode:
            self._mode_btn_editor.config(fg=dim)
            self._mode_btn_designer.config(fg=act)
        else:
            self._mode_btn_editor.config(fg=act)
            self._mode_btn_designer.config(fg=dim)
        self._refresh_generate_code_state()

    def _enter_designer_mode(self) -> None:
        """Switch the main content area to the designer canvas."""
        if self._designer_mode:
            return
        if self._split_active and self._split_shown:
            self._split_was_shown = True
            self._hide_split()
        else:
            self._split_was_shown = False
        self._designer_mode = True
        self._designer_project_type = "gui"
        self.notebook.pack_forget()
        self._designer_frame.pack(fill="both", expand=True)

        # Swap left pane: sidebar → palette
        # Rebuild h_pane order: palette | v_pane | props
        self._h_pane.forget(self._v_pane)
        if self._sidebar_shown:
            self._h_pane.forget(self._sidebar)
        if getattr(self, "_ai_panel_visible", False):
            try:
                self._h_pane.forget(self._ai_panel_frame)
            except Exception:
                pass
        # Apply stored widths before add() — PanedWindow uses the widget's
        # requested width as the initial sash position, no timing tricks needed.
        self._designer_left_pane.configure(width=self._designer_palette_width)
        self._props_panel.configure(width=self._designer_props_width)
        self._h_pane.add(self._designer_left_pane, minsize=160, stretch="never")
        self._h_pane.add(self._v_pane, stretch="always")
        self._h_pane.add(self._props_panel, minsize=200, stretch="never")

        self._designer_palette.reset_to_pointer()
        self._show_mode_bar()
        # Hide autocomplete before the canvas unmaps — pack_forget() doesn't
        # reliably trigger FocusOut on the inner canvas widget.
        cv = self._current_codeview
        if cv and hasattr(cv, "_hide_autocomplete"):
            cv._hide_autocomplete()

        # Auto-load form if canvas is empty (e.g. after session restore)
        if self._design_canvas.form is None:
            self._load_designer_form_from_project()

        # Sync ▶ indicator — tab may have changed while editor had focus
        if not self._run_entry_file:
            self._refresh_form_list()

        # Grab focus so keyboard shortcuts (Delete, arrows, Ctrl+Z) go to the
        # canvas immediately without requiring a click first
        self._design_canvas.focus_set()

    def _load_designer_form_from_project(self) -> None:
        """Load form JSON files into the designer.

        When _designer_form_names is populated (saved project), only those
        forms are loaded.  When empty (first open, migration), all *.form.json
        files in the root are loaded and _designer_form_names is seeded from
        whatever is found — establishing the explicit list for future saves.
        """
        from pathlib import Path as _Path
        from designer.persistence import load as _load

        root = getattr(self._sidebar.explorer, "_root", None)
        if not root:
            return

        if self._designer_form_names:
            # Explicit list — only load tracked forms
            json_files = []
            for name in self._designer_form_names:
                jf = _Path(root) / f"{name}.form.json"
                if jf.exists():
                    json_files.append(jf)
        else:
            # Migration / first open — glob all and seed the explicit list
            try:
                json_files = sorted(_Path(root).glob("*.form.json"))
            except Exception:
                return

        if not json_files:
            return

        self._designer_forms.clear()
        self._designer_missing_dialogs.clear()
        primary: object = None
        for jf in json_files:
            try:
                form, _ = _load(jf)
                self._designer_forms[form.name] = form
                if primary is None or form.form_type == "main":
                    primary = form
            except Exception:
                pass

        # Seed explicit list from whatever was actually loaded (migration path)
        if not self._designer_form_names:
            self._designer_form_names = list(self._designer_forms.keys())

        # Load linked dialogs for every main form; track any that are missing
        for form in list(self._designer_forms.values()):
            if form.form_type == "main":
                self._load_linked_dialogs(form)

        if primary is None:
            return
        self._design_canvas.load_form(primary)
        self._props_panel.set_form(primary)
        self._props_panel.load_form(primary)
        self._comp_tray.refresh(primary.components)
        self._comp_tray.deselect()
        self._designer_menu_had_items = bool(primary.menu_items)
        self._refresh_form_list(active=primary.name)
        self._refresh_generate_code_state()

    def _enter_editor_mode(self) -> None:
        """Switch the main content area back to the code editor."""
        if not self._designer_mode:
            return
        self._designer_autosave()
        self._designer_mode = False
        self._designer_frame.pack_forget()
        self.notebook.pack(fill="both", expand=True)

        # Snapshot pane widths before removing them from the layout.
        try:
            w = self._designer_left_pane.winfo_width()
            if w > 50:
                self._designer_palette_width = w
        except Exception:
            pass
        try:
            w = self._props_panel.winfo_width()
            if w > 50:
                self._designer_props_width = w
        except Exception:
            pass

        # Rebuild h_pane order: sidebar | v_pane  (remove left pane + props)
        try:
            self._h_pane.forget(self._designer_left_pane)
        except Exception:
            pass
        try:
            self._h_pane.forget(self._props_panel)
        except Exception:
            pass
        self._h_pane.forget(self._v_pane)
        if self._sidebar_shown:
            self._h_pane.add(self._sidebar, minsize=220, stretch="never")
        self._h_pane.add(self._v_pane, stretch="always")
        if getattr(self, "_ai_panel_visible", False):
            try:
                self._h_pane.add(self._ai_panel_frame, minsize=280, stretch="never")
            except Exception:
                pass

        self._refresh_mode_bar()

        # Restore split if it was visible before entering designer mode
        if self._split_was_shown and self._split_active and not self._split_shown:
            self._split_was_shown = False
            self.after(50, self._show_split)

        def _restore_editor_focus():
            cv = self._current_codeview
            if cv:
                inner = getattr(cv, "canvas", cv)
                inner.focus_set()
                cv.scroll_to_line(cv.get_cursor()[0])

        self.after_idle(_restore_editor_focus)

    def _on_designer_prop_change(self, widget_id: str, key: str, value) -> None:
        """Property panel edit → update canvas rendering."""
        form = self._design_canvas.form
        if form is None:
            return
        self._design_canvas.push_undo()
        self._set_designer_dirty()
        if widget_id == "__multi__":
            self._design_canvas.redraw()
            return
        if key == "__name__":
            new_name = value
            self._design_canvas.rename_widget(widget_id, new_name)
            self._props_panel.set_form(form)
            if form.get_widget(new_name):
                self._props_panel.load_widget(form.get_widget(new_name))
            return
        if widget_id == "__form__":
            if key == "image":
                form.image = value
                self._design_canvas._img_cache.clear()
                self._design_canvas.redraw()
            elif key == "bg":
                form.bg = value
                self._design_canvas.redraw()
            elif key == "title":
                form.title = value
                self._design_canvas.redraw()
            elif key in ("width", "height"):
                try:
                    v = int(value)
                    if key == "height" and form.menu_items:
                        v += 20
                    setattr(form, key, v)
                    self._design_canvas._reposition()
                except ValueError:
                    pass
            elif key == "border_style":
                form.border_style = str(value).lower().strip()
            elif key == "maximize_box":
                form.maximize_box = str(value).lower() in ("true", "1", "yes")
            elif key == "always_on_top":
                form.always_on_top = str(value).lower() in ("true", "1", "yes")
            elif key == "menu_bar":
                has_menu = bool(form.menu_items)
                if has_menu != self._designer_menu_had_items:
                    dy = 20 if has_menu else -20
                    form.height += dy  # canvas grows by 20 when menu bar added, shrinks when removed
                    self._design_canvas._reposition()
                    for w in form.widgets:
                        if w.parent_id is None:
                            w.y = max(
                                20 if has_menu else 0,
                                min(w.y + dy, form.height - w.height),
                            )
                self._designer_menu_had_items = has_menu
                self._design_canvas.redraw()
                self._props_panel.load_form(form)
            return
        if key in ("__variable__", "__anchor__"):
            return  # model already mutated by properties panel; no canvas redraw needed
        if key == "__tab__":
            self._design_canvas.redraw()
            sel = next(iter(self._design_canvas.selected_ids), None)
            self._props_panel.refresh_order(form, sel)
            return
        w = form.get_widget(widget_id)
        if w:
            if key == "tabs" and _DESIGNER_REGISTRY.get(w.type, {}).get("is_notebook"):
                # Ensure active tab is still valid after add/rename/remove
                tabs = w.props.get("tabs") or []
                active = self._design_canvas._active_nb_tabs.get(w.id, "")
                if active not in tabs:
                    self._design_canvas._active_nb_tabs[w.id] = tabs[0] if tabs else ""
                self._design_canvas.redraw()
            else:
                if w.type == "Canvas":
                    if key == "image" and value:
                        # Auto-fit canvas to the image's natural size
                        self._canvas_fit_to_image(w, value)
                    elif key == "sizing" and value == "fit image":
                        img = w.props.get("image", "")
                        if img:
                            self._canvas_fit_to_image(w, img)
                self._design_canvas.update_widget(w)
                if w.type == "Canvas" and key in ("image", "sizing"):
                    self._props_panel.load_widget(w)

    def _canvas_fit_to_image(self, widget, rel_path: str) -> None:
        """Resize a Canvas widget to its image's natural pixel dimensions."""
        project_dir = self._design_canvas._project_dir
        img_path = os.path.join(project_dir, rel_path.replace("/", os.sep))
        try:
            from PIL import Image as _PIL_Image
            with _PIL_Image.open(img_path) as img:
                widget.width  = img.width
                widget.height = img.height
            widget.props["sizing"] = "fit image"
        except Exception:
            pass

    def _on_designer_event_change(
        self, widget_id: str, event_key: str, handler: str
    ) -> None:
        """Event panel edit — model already mutated by properties panel."""
        self._set_designer_dirty()

    def _on_global_click_designer(self, event: tk.Event) -> None:
        """Cancel placement mode when user clicks outside the canvas or palette."""
        if not self._designer_mode:
            return
        if not self._design_canvas._active_tool:
            return
        w = event.widget
        while w is not None:
            if w is self._design_canvas or w is self._designer_left_pane:
                return
            try:
                w = w.master
            except Exception:
                break
        self._design_canvas.cancel_tool()
        self._designer_palette.reset_to_pointer()

    def _on_designer_tool_cancel(self) -> None:
        """Canvas cancelled placement tool → reset palette to pointer."""
        self._designer_palette.reset_to_pointer()

    def _on_designer_snap_state_changed(self) -> None:
        self._designer_toolbar.refresh_snap()

    def _on_palette_tool_select(self, type_key: str | None) -> None:
        """Palette click → arm canvas with placement tool."""
        self._design_canvas.set_tool(type_key)

    def _on_palette_place(self, type_key: str) -> None:
        """Palette double-click → place widget at form centre immediately."""
        self._design_canvas.place_at_default(type_key)
        self._designer_palette.reset_to_pointer()

    def _on_palette_drag_drop(self, type_key: str, x_root: int, y_root: int) -> None:
        """Palette drag-drop → place widget at the drop position on the canvas."""
        canvas = self._design_canvas
        cx = canvas.winfo_rootx()
        cy = canvas.winfo_rooty()
        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
        if cx <= x_root <= cx + cw and cy <= y_root <= cy + ch:
            canvas.drop_widget(type_key, x_root - cx, y_root - cy)
        self._designer_palette.reset_to_pointer()

    def _on_designer_select(self, widget_id: str) -> None:
        """Canvas selection → populate properties panel; reset palette only when not placing."""
        if not self._design_canvas._active_tool:
            self._designer_palette.reset_to_pointer()
        self._comp_tray.deselect()
        self._designer_toolbar.refresh()
        form = self._design_canvas.form
        if form is None:
            return
        w = form.get_widget(widget_id)
        if w:
            self._props_panel.load_widget(w)
        self._props_panel.refresh_order(form, widget_id)

    def _on_designer_deselect(self) -> None:
        """Canvas deselect → show form-level properties."""
        if getattr(self, "_comp_selecting", False):
            return
        self._comp_tray.deselect()
        self._designer_toolbar.refresh()
        form = self._design_canvas.form
        if form:
            self._props_panel.load_form(form)
            self._props_panel.refresh_order(form, None)
        else:
            self._props_panel.clear()

    def _on_designer_multi_select(self, widget_ids: list) -> None:
        self._designer_toolbar.refresh()
        form = self._design_canvas.form
        if form is None:
            return
        descriptors = [
            form.get_widget(wid) for wid in widget_ids if form.get_widget(wid)
        ]
        if descriptors:
            self._props_panel.load_multi(descriptors)

    def _on_designer_widget_changed(self, descriptor) -> None:
        self._set_designer_dirty()
        if len(self._design_canvas.selected_ids) > 1:
            form = self._design_canvas.form
            descriptors = [
                form.get_widget(wid)
                for wid in self._design_canvas.selected_ids
                if form and form.get_widget(wid)
            ]
            self._props_panel.load_multi(descriptors)
        else:
            self._props_panel.refresh_widget(descriptor)

    def _on_designer_form_changed(self, form) -> None:
        """Form resize finished → refresh form-level properties panel."""
        self._set_designer_dirty()
        self._props_panel.set_form(form)
        self._props_panel.load_form(form)

    def _on_designer_structure_changed(self) -> None:
        """Widget added/removed/reordered → dirty flag + rebuild selector."""
        self._set_designer_dirty()
        self._designer_toolbar.refresh()
        form = self._design_canvas.form
        if form:
            self._props_panel.set_form(form)
            sel = next(iter(self._design_canvas.selected_ids), None)
            self._props_panel.refresh_order(form, sel)

    def _on_designer_reorder_widget(self, widget_id: str, new_idx: int) -> None:
        """Order tab drag-drop → move widget in model."""
        self._design_canvas.move_widget_to(widget_id, new_idx)

    def _on_designer_handler_toggle(self, handler_id: str, enabled: bool) -> None:
        """Handlers tab checkbox → update form.enabled_handlers."""
        form = self._design_canvas.form
        if form is None:
            return
        if enabled and handler_id not in form.enabled_handlers:
            form.enabled_handlers.append(handler_id)
        elif not enabled:
            form.enabled_handlers = [
                h for h in form.enabled_handlers if h != handler_id
            ]
        self._set_designer_dirty()

    def _on_designer_handler_connect(
        self, handler_id: str, preselect_widget_id: str | None = None
    ) -> None:
        """⚡ button on an Available handler row — enable or wire the handler."""
        from designer.handlers import HANDLER_CATALOG
        from designer.model import HandlerWire
        from widgets.designer_connector import ComponentConnector

        form = self._design_canvas.form
        if form is None:
            return
        hdef = next((h for h in HANDLER_CATALOG if h.id == handler_id), None)
        if hdef is None:
            return

        if hdef.connectable:
            # Resolve primary connector options (static tuple or dynamic source)
            if hdef.connector_options_source == "linked_dialogs":
                if not form.linked_dialogs:
                    self._props_panel.show_hint(
                        "No linked dialogs. Link a dialog to this form first "
                        "via the Forms panel."
                    )
                    return
                connector_options = tuple(form.linked_dialogs)
            else:
                connector_options = hdef.options

            # Open connector so the user picks a widget + event + option
            def _on_wire(widget_id: str, event_key: str, option: str) -> None:
                if widget_id == "__form__":
                    # Wire body goes into a form-event stub (_on_load, _on_activate, …)
                    # Reuse existing method name if the event is already wired, else default.
                    method_name = form.form_events.get(event_key) or f"_on_{event_key}"
                    form.form_events[event_key] = method_name
                    # Don't add to enabled_handlers — the wire body is injected
                    # directly into the form event stub via _wire_default_bodies in codegen.
                else:
                    # Auto-create a named event stub on the widget if none exists
                    widget = form.get_widget(widget_id)
                    if widget is not None and not widget.events.get(event_key):
                        widget.events[event_key] = f"_{widget_id}_{event_key}"

                self._apply_wire_side_effects(form, hdef, option)

                wire = HandlerWire(
                    handler_id=handler_id,
                    widget_id=widget_id,
                    event_key=event_key,
                    option=option,
                )
                form.handler_wires.append(wire)
                # generates_stub=False handlers (e.g. _open_dialog) don't emit a stub.
                if hdef.generates_stub and handler_id not in form.enabled_handlers:
                    form.enabled_handlers.append(handler_id)
                # Store chosen option so the handler stub body reflects selection.
                if option and hdef.stub_option_bodies:
                    form.handler_options[handler_id] = option
                self._set_designer_dirty()
                self._props_panel.load_handlers(form)

            # Pass a resolver so the connector preview shows the actual generated call.
            resolver = (
                (lambda opt: hdef.wire_body_for(opt, handler_id))
                if hdef.dynamic_wire_body
                else None
            )
            ComponentConnector(
                self,
                form,
                component_id="",
                handler_id=handler_id,
                handler_label="",
                on_wire=_on_wire,
                options=connector_options,
                preselect_widget_id=preselect_widget_id,
                wire_body_resolver=resolver,
                secondary_options=hdef.secondary_options,
                form_event_keys=("load", "activate", "deactivate", "unload", "resize"),
            )
        else:
            # Non-connectable handler — just enable it
            if handler_id not in form.enabled_handlers:
                form.enabled_handlers.append(handler_id)
            self._set_designer_dirty()
            self._props_panel.load_handlers(form)

    def _on_designer_handler_disconnect(self, handler_id: str, wire) -> None:
        """× button on a Connected handler row — disable the handler or remove a wire."""
        from designer.model import HandlerWire

        form = self._design_canvas.form
        if form is None:
            return
        if wire is not None and isinstance(wire, HandlerWire):
            # Remove specific widget-event wire for connectable handlers
            form.handler_wires = [
                w
                for w in form.handler_wires
                if not (
                    w.handler_id == wire.handler_id
                    and w.widget_id == wire.widget_id
                    and w.event_key == wire.event_key
                )
            ]
            # Clear the event binding on the widget or form
            if wire.widget_id == "__form__":
                form.form_events.pop(wire.event_key, None)
            else:
                widget = form.get_widget(wire.widget_id)
                if widget is not None:
                    widget.events.pop(wire.event_key, None)
            # If no wires remain for this handler, clean up enabled_handlers + options
            still_wired = any(w.handler_id == handler_id for w in form.handler_wires)
            if not still_wired:
                form.enabled_handlers = [
                    h for h in form.enabled_handlers if h != handler_id
                ]
                form.handler_options.pop(handler_id, None)
        else:
            # Remove from enabled_handlers (built-in wired handler)
            form.enabled_handlers = [
                h for h in form.enabled_handlers if h != handler_id
            ]
            form.handler_options.pop(handler_id, None)
        self._set_designer_dirty()
        self._props_panel.load_handlers(form)

    def _on_designer_handler_edit(self, handler_id: str, wire) -> None:
        """… button on a Connected handler row — open the options editor."""
        from designer.handlers import HANDLER_CATALOG
        from designer.model import HandlerWire
        from widgets.handler_options_editor import HandlerOptionsEditor

        form = self._design_canvas.form
        if form is None:
            return
        hdef = next((h for h in HANDLER_CATALOG if h.id == handler_id), None)
        if hdef is None or not (hdef.options or hdef.secondary_options):
            return
        is_wire = isinstance(wire, HandlerWire)

        # Multi-wire handlers: edit the secondary option (mode)
        if is_wire and hdef.multi_wire and hdef.secondary_options:
            opt_parts = wire.option.partition(":")
            primary_part = opt_parts[0]
            current_mode = opt_parts[2] if opt_parts[1] else hdef.secondary_options[0]

            def on_mode_apply(new_mode: str) -> None:
                new_combined = f"{primary_part}:{new_mode}"
                form.handler_wires = [
                    HandlerWire(
                        w.handler_id,
                        w.widget_id,
                        w.event_key,
                        new_combined
                        if (
                            w.handler_id == wire.handler_id
                            and w.widget_id == wire.widget_id
                            and w.event_key == wire.event_key
                        )
                        else w.option,
                    )
                    for w in form.handler_wires
                ]
                self._apply_wire_side_effects(form, hdef, new_combined)
                self._set_designer_dirty()
                self._props_panel.load_handlers(form)

            HandlerOptionsEditor(
                self,
                handler_id,
                hdef,
                is_wire=True,
                current_option=current_mode,
                on_apply=on_mode_apply,
                override_options=list(hdef.secondary_options),
                override_bodies=list(hdef.edit_bodies) if hdef.edit_bodies else None,
            )
            return

        current = wire.option if is_wire else form.handler_options.get(handler_id, "")

        def on_apply(option: str) -> None:
            if is_wire:
                # Try to refresh the widget event stub when the option changes
                self._reset_wire_stub_if_auto(form, wire, hdef, option)
                form.handler_wires = [
                    HandlerWire(
                        w.handler_id,
                        w.widget_id,
                        w.event_key,
                        option
                        if (
                            w.handler_id == wire.handler_id
                            and w.widget_id == wire.widget_id
                            and w.event_key == wire.event_key
                        )
                        else w.option,
                    )
                    for w in form.handler_wires
                ]
                # Sync handler_options so stub body reflects the new option
                if option and hdef.stub_option_bodies:
                    form.handler_options[handler_id] = option
            else:
                if option:
                    form.handler_options[handler_id] = option
                else:
                    form.handler_options.pop(handler_id, None)
            self._set_designer_dirty()
            self._props_panel.load_handlers(form)

        HandlerOptionsEditor(self, handler_id, hdef, is_wire, current, on_apply)

    def _apply_wire_side_effects(self, form, hdef, option: str) -> None:
        """Dispatch post-wire side effects declared in hdef.wire_side_effects."""
        if hdef.wire_side_effects == "sync_dialog_close_mode" and ":" in option:
            dlg_name, _, mode_str = option.partition(":")
            # mode_str is already the full secondary option string e.g. "destroy (exit)";
            # store it directly so HandlerOptionsEditor can match it exactly.
            dlg_form = self._designer_forms.get(dlg_name)
            if dlg_form:
                dlg_form.handler_options["_on_close"] = mode_str
                if "_on_close" not in dlg_form.enabled_handlers:
                    dlg_form.enabled_handlers.append("_on_close")

    def _reset_wire_stub_if_auto(self, form, wire, hdef, new_option: str) -> None:
        """Queue a body reset for the wire's target method if the body is still auto-generated.

        Compares the current saved body against all known wire_option_bodies.
        If it matches any (i.e. the user hasn't customised it), drop it from
        persistence so the next codegen writes the new option's wire body.
        If the body has been edited, leave it and flash a hint instead.
        """
        from pathlib import Path as _Path
        from designer.persistence import extract_event_bodies as _bodies

        widget = form.get_widget(wire.widget_id)
        if widget is None:
            return
        method = widget.events.get(wire.event_key)
        if not method:
            return

        root = getattr(getattr(self, "_sidebar", None), "explorer", None)
        root = getattr(root, "_root", None)
        if not root:
            return
        py_path = _Path(root) / f"{form.name}.py"
        if not py_path.exists():
            return

        saved_bodies = _bodies(py_path)
        current_body = saved_bodies.get(method, "").strip()
        known_bodies = {b.strip() for b in hdef.wire_option_bodies}

        if not current_body or current_body in known_bodies:
            # Auto-generated (or no saved body yet) — safe to reset
            self._pending_body_resets.add(method)
        else:
            # User has customised the stub — don't overwrite, flash a hint
            self._props_panel._show_status(
                f"Stub for {method} was edited — update manually.", duration_ms=4000
            )

    # ── Component tray handlers ───────────────────────────────────────────────

    def _on_comp_add(self, type_key: str) -> None:
        form = self._design_canvas.form
        if form is None:
            return
        cdef = get_component_def(type_key)
        if cdef is None:
            return
        if type_key == "Socket":
            self._open_socket_setup_dialog(form, cdef)
            return
        comp_id = form.next_component_id(cdef.default_name)
        comp = ComponentDescriptor(
            id=comp_id, type=type_key, props=default_props(type_key)
        )
        form.components.append(comp)
        self._comp_tray.refresh(form.components)
        self._comp_tray.select(comp_id)
        self._comp_selecting = True
        try:
            self._design_canvas.deselect()
        finally:
            self._comp_selecting = False
        self._props_panel.load_component(comp, cdef)
        self._set_designer_dirty()

    def _open_socket_setup_dialog(self, form, cdef) -> None:
        from designer.model import WidgetDescriptor
        from designer.component_registry import default_props as comp_default_props

        win = tk.Toplevel(self)
        win.withdraw()
        win.title("New Socket Component")
        win.resizable(False, False)
        win.configure(bg="#2d2d2d")
        win.transient(self)

        _BG = "#2d2d2d"
        _FG = "#cccccc"
        _FG2 = "#888888"
        _ENT = "#3c3c3c"
        _SEP = "#3a3a3a"
        _FONT = (UI_FONT, 9)

        # ── Type row ──────────────────────────────────────────────────────────
        type_var = tk.StringVar(value="server")
        tk.Label(win, text="Type:", bg=_BG, fg=_FG, font=_FONT).grid(
            row=0, column=0, padx=12, pady=(14, 4), sticky="w"
        )
        type_frame = tk.Frame(win, bg=_BG)
        type_frame.grid(
            row=0, column=1, columnspan=3, padx=(0, 12), pady=(14, 4), sticky="w"
        )
        for lbl, val in [
            ("Server  (listen)", "server"),
            ("Client  (connect)", "client"),
        ]:
            tk.Radiobutton(
                type_frame,
                text=lbl,
                variable=type_var,
                value=val,
                bg=_BG,
                fg=_FG,
                selectcolor="#094771",
                activebackground=_BG,
                font=_FONT,
                highlightthickness=0,
                relief="flat",
            ).pack(side="left", padx=(0, 12))

        # ── Host / Port row ───────────────────────────────────────────────────
        tk.Label(win, text="Host:", bg=_BG, fg=_FG, font=_FONT).grid(
            row=1, column=0, padx=12, pady=4, sticky="w"
        )
        host_var = tk.StringVar(value="localhost")
        tk.Entry(
            win,
            textvariable=host_var,
            bg=_ENT,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            font=_FONT,
            width=16,
        ).grid(row=1, column=1, padx=(0, 8), pady=4, sticky="w")
        tk.Label(win, text="Port:", bg=_BG, fg=_FG, font=_FONT).grid(
            row=1, column=2, pady=4, sticky="w"
        )
        port_var = tk.StringVar(value="8080")
        tk.Entry(
            win,
            textvariable=port_var,
            bg=_ENT,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            font=_FONT,
            width=6,
        ).grid(row=1, column=3, padx=(4, 12), pady=4, sticky="w")

        # ── Separator + scaffold section ──────────────────────────────────────
        tk.Frame(win, bg=_SEP, height=1).grid(
            row=2, column=0, columnspan=4, sticky="ew", padx=8, pady=(10, 2)
        )
        tk.Label(
            win,
            text="Scaffold starter widgets (optional):",
            bg=_BG,
            fg=_FG2,
            font=_FONT,
        ).grid(row=3, column=0, columnspan=4, padx=12, pady=(4, 2), sticky="w")

        # ── 3 grouped checkboxes ──────────────────────────────────────────────
        chk_connect = tk.BooleanVar(value=False)
        chk_chat = tk.BooleanVar(value=False)
        chk_file = tk.BooleanVar(value=False)

        def _chk(row_i, var, title, detail):
            f = tk.Frame(win, bg=_BG)
            f.grid(row=row_i, column=0, columnspan=4, padx=16, pady=(3, 0), sticky="w")
            tk.Checkbutton(
                f,
                text=title,
                variable=var,
                bg=_BG,
                fg=_FG,
                selectcolor="#094771",
                activebackground=_BG,
                font=_FONT,
                highlightthickness=0,
                relief="flat",
            ).pack(side="left")
            tk.Label(f, text=detail, bg=_BG, fg=_FG2, font=(UI_FONT, 8)).pack(
                side="left", padx=(4, 0)
            )

        _chk(
            4,
            chk_connect,
            "Connect / Disconnect",
            "— toggle button + status label, auto-wired",
        )
        _chk(5, chk_chat, "Chat", "— text log, message entry + Send button, auto-wired")
        _chk(
            6,
            chk_file,
            "File Transfer",
            "— progressbar, file label + Send File button, framed protocol",
        )

        # ── Button row ────────────────────────────────────────────────────────
        tk.Frame(win, bg=_SEP, height=1).grid(
            row=7, column=0, columnspan=4, sticky="ew", padx=8, pady=(10, 0)
        )
        btn_frame = tk.Frame(win, bg=_BG)
        btn_frame.grid(row=8, column=0, columnspan=4, padx=12, pady=(6, 12), sticky="e")

        def _make_btn(parent, text, cmd):
            b = tk.Label(
                parent,
                text=text,
                bg="#3c3c3c",
                fg=_FG,
                font=_FONT,
                padx=10,
                pady=4,
                cursor="hand2",
                relief="flat",
            )
            b.pack(side="left", padx=(6, 0))
            b.bind("<ButtonRelease-1>", lambda _: cmd())
            b.bind("<Enter>", lambda _: b.configure(bg="#505050"))
            b.bind("<Leave>", lambda _: b.configure(bg="#3c3c3c"))
            return b

        def _on_confirm():
            stype = type_var.get()
            host = host_var.get().strip() or "localhost"
            try:
                port = int(port_var.get())
            except ValueError:
                port = 8080

            # ── Create component ──────────────────────────────────────────────
            comp_id = form.next_component_id(cdef.default_name)
            props = comp_default_props("Socket")
            props["socket_type"] = stype
            props["host"] = host
            props["port"] = port
            if stype == "server":
                props["bind_address"] = "0.0.0.0"

            # ── Scaffold ──────────────────────────────────────────────────────
            fw = form.width
            mx = 16  # margin x
            inner_w = fw - mx * 2
            cur_y = 16
            gap = 8

            existing_ids = {wd.id for wd in form.widgets}

            def _named_id(base):
                if base not in existing_ids:
                    existing_ids.add(base)
                    return base
                n = 2
                while f"{base}_{n}" in existing_ids:
                    n += 1
                nid = f"{base}_{n}"
                existing_ids.add(nid)
                return nid

            def _btn_props(text):
                return {
                    "text": text,
                    "bg": "",
                    "fg": "#000000",
                    "font": "",
                    "justify": "",
                    "relief": "",
                    "borderwidth": "",
                    "wraplength": "",
                    "image": "",
                    "compound": "",
                }

            def _lbl_props(text, fg="#cccccc"):
                return {
                    "text": text,
                    "bg": "",
                    "fg": fg,
                    "font": "",
                    "justify": "left",
                    "relief": "",
                    "borderwidth": "",
                    "wraplength": "",
                    "image": "",
                    "compound": "",
                }

            def _add(w):
                form.widgets.append(w)

            # ── Group 1: Connect / Disconnect ─────────────────────────────────
            if chk_connect.get():
                btn_lbl = "Listen" if stype == "server" else "Connect"
                btn_id = _named_id("btn_connect")
                lbl_id = _named_id("lbl_status")
                _add(
                    WidgetDescriptor(
                        id=btn_id,
                        type="Button",
                        x=mx,
                        y=cur_y,
                        width=130,
                        height=28,
                        props=_btn_props(btn_lbl),
                        events={"command": f"_{comp_id}_toggle_connect"},
                    )
                )
                _add(
                    WidgetDescriptor(
                        id=lbl_id,
                        type="Label",
                        x=mx + 138,
                        y=cur_y + 4,
                        width=inner_w - 138,
                        height=20,
                        props=_lbl_props("Disconnected", "#888888"),
                        events={},
                    )
                )
                props["_scaffold_btn_connect"] = btn_id
                props["_scaffold_lbl_status"] = lbl_id
                cur_y += 28 + gap

            # ── Group 2: Chat ─────────────────────────────────────────────────
            if chk_chat.get():
                txt_id = _named_id("txt_chat")
                ent_id = _named_id("ent_message")
                send_id = _named_id("btn_send")
                send_w = 70
                ent_w = inner_w - send_w - gap
                _add(
                    WidgetDescriptor(
                        id=txt_id,
                        type="Text",
                        x=mx,
                        y=cur_y,
                        width=inner_w,
                        height=200,
                        props={
                            "wrap": "word",
                            "bg": "#1e1e1e",
                            "fg": "#cccccc",
                            "font": "",
                            "relief": "flat",
                            "insertbackground": "",
                            "borderwidth": "0",
                            "scrollbar": "Vertical",
                            "selectbackground": "",
                            "selectforeground": "",
                            "exportselection": "",
                            "char_width": "",
                            "char_height": "",
                        },
                        events={},
                    )
                )
                cur_y += 200 + gap
                _add(
                    WidgetDescriptor(
                        id=ent_id,
                        type="Entry",
                        x=mx,
                        y=cur_y,
                        width=ent_w,
                        height=28,
                        props={
                            "text": "",
                            "bg": "#3c3c3c",
                            "fg": "#cccccc",
                            "show": "",
                            "font": "",
                            "justify": "",
                            "relief": "flat",
                            "insertbackground": "#cccccc",
                            "borderwidth": "0",
                            "selectbackground": "",
                            "selectforeground": "",
                            "exportselection": "",
                            "char_width": "",
                        },
                        events={},
                    )
                )
                _add(
                    WidgetDescriptor(
                        id=send_id,
                        type="Button",
                        x=mx + ent_w + gap,
                        y=cur_y,
                        width=send_w,
                        height=28,
                        props=_btn_props("Send"),
                        events={"command": f"_{comp_id}_quick_send"},
                    )
                )
                props["_scaffold_txt_chat"] = txt_id
                props["_scaffold_ent_message"] = ent_id
                cur_y += 28 + gap

            # ── Group 3: File Transfer ────────────────────────────────────────
            if chk_file.get():
                pb_id = _named_id("pb_transfer")
                lbl_id = _named_id("lbl_file")
                file_id = _named_id("btn_send_file")
                file_w = 100
                lbl_w = inner_w - file_w - gap
                _add(
                    WidgetDescriptor(
                        id=pb_id,
                        type="Progressbar",
                        x=mx,
                        y=cur_y,
                        width=inner_w,
                        height=18,
                        props={
                            "orient": "horizontal",
                            "mode": "determinate",
                            "maximum": "",
                        },
                        events={},
                    )
                )
                cur_y += 18 + gap
                _add(
                    WidgetDescriptor(
                        id=lbl_id,
                        type="Label",
                        x=mx,
                        y=cur_y,
                        width=lbl_w,
                        height=24,
                        props=_lbl_props("No file selected", "#888888"),
                        events={},
                    )
                )
                _add(
                    WidgetDescriptor(
                        id=file_id,
                        type="Button",
                        x=mx + lbl_w + gap,
                        y=cur_y - 2,
                        width=file_w,
                        height=28,
                        props=_btn_props("Send File…"),
                        events={"command": f"_{comp_id}_pick_and_send_file"},
                    )
                )
                props["_scaffold_pb_transfer"] = pb_id
                props["_scaffold_lbl_file"] = lbl_id
                cur_y += 28 + gap

            # ── Finalise ──────────────────────────────────────────────────────
            comp = ComponentDescriptor(id=comp_id, type="Socket", props=props)
            form.components.append(comp)
            win.destroy()

            self._design_canvas.load_form(form)
            self._comp_tray.refresh(form.components)
            self._comp_tray.select(comp_id)
            self._comp_selecting = True
            try:
                self._design_canvas.deselect()
            finally:
                self._comp_selecting = False
            self._props_panel.load_component(comp, cdef)
            self._set_designer_dirty()

        def _on_cancel():
            win.destroy()

        _make_btn(btn_frame, "Cancel", _on_cancel)
        _make_btn(btn_frame, "Add Socket", _on_confirm)

        win.bind("<Return>", lambda _: _on_confirm())
        win.bind("<Escape>", lambda _: _on_cancel())

        self.update_idletasks()
        pw = self.winfo_rootx() + self.winfo_width() // 2
        ph = self.winfo_rooty() + self.winfo_height() // 2
        win.update_idletasks()
        win.geometry(f"+{pw - win.winfo_width() // 2}+{ph - win.winfo_height() // 2}")
        win.deiconify()
        win.grab_set()

    def _on_comp_select(self, comp_id: str) -> None:
        form = self._design_canvas.form
        if form is None:
            return
        comp = form.get_component(comp_id)
        if comp is None:
            return
        cdef = get_component_def(comp.type)
        if cdef is None:
            return
        self._comp_selecting = True
        try:
            self._design_canvas.deselect()
        finally:
            self._comp_selecting = False
        self._comp_tray.select(comp_id)
        self._props_panel.load_component(comp, cdef)

    def _on_comp_deselect(self) -> None:
        form = self._design_canvas.form
        if form:
            self._props_panel.load_form(form)

    def _on_comp_delete(self, comp_id: str) -> None:
        form = self._design_canvas.form
        if form is None:
            return
        form.components = [c for c in form.components if c.id != comp_id]
        self._comp_tray.refresh(form.components)
        self._props_panel.load_form(form)
        self._set_designer_dirty()

    def _on_comp_rename(self, comp_id: str, new_name: str) -> None:
        from pathlib import Path as _Path

        form = self._design_canvas.form
        if form is None:
            return
        if not new_name.isidentifier():
            return
        if any(c.id == new_name for c in form.components if c.id != comp_id):
            return
        comp = form.get_component(comp_id)
        if comp is None:
            return

        old_prefix = f"_{comp_id}_"
        new_prefix = f"_{new_name}_"

        # Update widget.events values that reference old handler names
        for widget in form.widgets:
            widget.events = {
                ev: (
                    v.replace(old_prefix, new_prefix, 1)
                    if v.startswith(old_prefix)
                    else v
                )
                for ev, v in widget.events.items()
            }

        # Rename in the generated .py file before codegen re-runs
        root = getattr(self._sidebar.explorer, "_root", None)
        if root:
            py_path = _Path(root) / f"{form.name}.py"
            if py_path.exists():
                src = py_path.read_text(encoding="utf-8")
                py_path.write_text(
                    src.replace(old_prefix, new_prefix), encoding="utf-8"
                )

        comp.id = new_name
        self._comp_tray.refresh(form.components)
        self._comp_tray.select(new_name)
        self._props_panel.set_form(form)
        cdef = get_component_def(comp.type)
        if cdef:
            self._props_panel.load_component(comp, cdef)
        self._set_designer_dirty()

    def _on_comp_prop_change(self, comp_id: str, prop_key: str, value) -> None:
        if prop_key == "__name__":
            self._on_comp_rename(comp_id, value)
            return
        form = self._design_canvas.form
        if form is None:
            return
        comp = form.get_component(comp_id)
        if comp is None:
            return
        comp.props[prop_key] = value
        if prop_key == "paths":
            self._comp_tray.refresh(form.components)
        self._set_designer_dirty()

    def _on_comp_connect(self, comp_id: str, handler_id: str) -> None:
        form = self._design_canvas.form
        if form is None:
            return
        comp = form.get_component(comp_id)
        if comp is None:
            return
        cdef = get_component_def(comp.type)
        if cdef is None:
            return
        hdef = next((h for h in cdef.handler_defs if h.id == handler_id), None)
        if hdef is None:
            return

        # canvas_button opens the Image Button Builder instead of the standard connector
        if handler_id == "canvas_button":
            self._open_img_button_builder(comp_id, comp, form)
            return

        # For file-object handlers, build a dynamic "Populate" widget list
        _FILE_OBJ_HANDLERS = ("ask_open_file", "ask_save_file")
        _POPULATE_TYPES = ("Entry", "Text", "Listbox")
        _INPUT_TYPES = ("string", "integer", "float")
        _MB_TYPES = ("askyesno", "askokcancel", "askretrycancel", "askquestion")
        if handler_id in _FILE_OBJ_HANDLERS:
            _targets = [w.id for w in form.widgets if w.type in _POPULATE_TYPES]
            _primary_opts = ()
            _secondary_opts = tuple(_targets) + ("(none)",)
            _secondary_label = "Populate"
            _secondary_warn = (
                ""
                if _targets
                else "⚠  No Entry, Text, or Listbox on form — add one or choose (none)"
            )
        elif handler_id == "ask_input":
            _primary_opts = _INPUT_TYPES
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""
        elif handler_id == "messagebox":
            _primary_opts = _MB_TYPES
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""
        else:
            _primary_opts = ()
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""

        _show_title = comp.type == "CommonDialog"
        _title_entry_label = "Message" if handler_id == "messagebox" else "Title"
        _show_extra = handler_id == "messagebox"
        if handler_id == "messagebox":
            _init_title = comp.props.get("messagebox_message", "")
            _init_extra = comp.props.get("messagebox_title", "")
        else:
            _init_title = (
                comp.props.get(f"{handler_id}_title", "") if _show_title else ""
            )
            _init_extra = ""

        # Connectable menu items (non-cascade command items at indent > 0)
        _all_mi = form.menu_items
        _conn_mi = [
            mi
            for i, mi in enumerate(_all_mi)
            if mi.indent > 0
            and mi.caption != "-"
            and mi.name
            and mi.kind not in ("checkbutton", "radiobutton")
            and not any(
                _all_mi[j].indent == mi.indent + 1
                for j in range(i + 1, len(_all_mi))
                if _all_mi[j].indent <= mi.indent + 1
            )
        ]

        def _is_stub(method_name: str) -> bool:
            import re as _re

            root = getattr(self._sidebar.explorer, "_root", None)
            if not root:
                return True
            from pathlib import Path as _Path

            py_path = _Path(root) / f"{form.name}.py"
            if not py_path.exists():
                return True
            try:
                src = py_path.read_text(encoding="utf-8")
            except Exception:
                return False
            m = _re.search(
                rf"def {_re.escape(method_name)}\(self[^)]*\):\s*\n[ \t]+(pass\b)",
                src,
                _re.MULTILINE,
            )
            return bool(m)

        def _on_wire(widget_id: str, event_key: str, option: str = "") -> None:
            method = f"_{comp_id}{hdef.label}"
            # Menu item target
            mi = next((m for m in _conn_mi if m.name == widget_id), None)
            if mi is not None:
                mi.command_handler = method
                self._set_designer_dirty()
                self._props_panel.refresh_comp_connections()
                return
            w = form.get_widget(widget_id)
            if w is None:
                return
            w.events[event_key] = method
            if handler_id == "messagebox":
                _parts = option.split("|", 2)
                main_opt = _parts[0]
                msg_text = _parts[1] if len(_parts) > 1 else ""
                dlg_title = _parts[2] if len(_parts) > 2 else ""
                comp.props["messagebox_type"] = main_opt or "askyesno"
                if msg_text:
                    comp.props["messagebox_message"] = msg_text
                elif "messagebox_message" in comp.props:
                    del comp.props["messagebox_message"]
                if dlg_title:
                    comp.props["messagebox_title"] = dlg_title
                elif "messagebox_title" in comp.props:
                    del comp.props["messagebox_title"]
            else:
                if _show_title and "|" in option:
                    main_opt, title_val = option.rsplit("|", 1)
                else:
                    main_opt, title_val = option, ""
                if _show_title:
                    if title_val:
                        comp.props[f"{handler_id}_title"] = title_val
                    elif f"{handler_id}_title" in comp.props:
                        del comp.props[f"{handler_id}_title"]
                if handler_id in _FILE_OBJ_HANDLERS:
                    comp.props[f"{handler_id}_target"] = main_opt
                elif handler_id == "ask_input":
                    comp.props["ask_input_type"] = main_opt or "string"
            self._set_designer_dirty()
            self._props_panel.refresh_comp_connections()

        ComponentConnector(
            self,
            form,
            comp_id,
            handler_id,
            hdef.label,
            _on_wire,
            options=_primary_opts,
            secondary_options=_secondary_opts,
            secondary_label=_secondary_label,
            initial_warning=_secondary_warn,
            preselect_widget_id=self._design_canvas.selected_id,
            show_title_entry=_show_title,
            initial_title=_init_title,
            title_entry_label=_title_entry_label,
            show_extra_entry=_show_extra,
            initial_extra=_init_extra,
            extra_entry_label="Title",
            menu_items=_conn_mi,
            stub_checker=_is_stub,
        )

    def _open_img_button_builder(self, comp_id: str, comp, form, edit_tag: str = "") -> None:
        """Open the Image Button Builder dialog for an Image component."""
        from widgets.designer_img_button_builder import ImageButtonBuilder
        paths      = comp.props.get("paths") or []
        canvas_ids = [w.id for w in form.widgets if w.type == "Canvas"]
        preset_canvas = ""
        # Pre-select current widget if it's a Canvas
        cur = self._props_panel._current_widget
        if cur and cur.type == "Canvas":
            preset_canvas = cur.id
        # Find existing config if editing
        edit_config = None
        if edit_tag:
            edit_config = next(
                (b for b in (comp.props.get("canvas_buttons") or []) if b.get("tag") == edit_tag),
                None
            )

        def _on_create_canvas() -> str:
            """Add a new Canvas widget to the form and return its ID."""
            from designer.model import WidgetDescriptor
            new_id = form.next_id("Canvas")
            w = WidgetDescriptor(
                id=new_id, type="Canvas",
                x=20, y=20, width=200, height=150,
                props={"bg": "", "image": "", "sizing": "sizable"},
            )
            form.add_widget(w)
            self._design_canvas.redraw()
            self._set_designer_dirty()
            return new_id

        def _on_confirm(config: dict) -> None:
            buttons = list(comp.props.get("canvas_buttons") or [])
            if edit_tag:
                buttons = [b for b in buttons if b.get("tag") != edit_tag]
            buttons.append(config)
            comp.props["canvas_buttons"] = buttons
            # Auto-size the canvas widget to the largest image dimensions
            aw = config.get("auto_size_w", 0)
            ah = config.get("auto_size_h", 0)
            if aw > 0 and ah > 0:
                cw = form.get_widget(config["canvas_id"])
                if cw:
                    cw.width  = aw
                    cw.height = ah
            self._comp_tray.refresh(form.components)
            self._design_canvas.redraw()
            self._set_designer_dirty()
            self._props_panel.refresh_comp_connections()

        ImageButtonBuilder(
            self,
            comp_id=comp_id,
            paths=paths,
            canvas_ids=canvas_ids,
            project_dir=self._design_canvas._project_dir,
            on_confirm=_on_confirm,
            on_create_canvas=_on_create_canvas,
            preset_canvas_id=preset_canvas,
            edit_config=edit_config,
        )

    def _on_comp_disconnect(self, comp_id: str, widget_id: str, event_key: str) -> None:
        form = self._design_canvas.form
        if form is None:
            return
        # canvas_button deletion — event_key is the tag name
        if widget_id == "__canvas_btn__":
            comp = form.get_component(comp_id)
            if comp:
                buttons = comp.props.get("canvas_buttons") or []
                comp.props["canvas_buttons"] = [b for b in buttons if b.get("tag") != event_key]
                self._design_canvas.redraw()
                self._set_designer_dirty()
                self._props_panel.refresh_comp_connections()
            return
        if widget_id.startswith("__mi__"):
            mi = form.get_menu_item(widget_id[6:])
            if mi:
                mi.command_handler = ""
            self._set_designer_dirty()
            self._props_panel.refresh_comp_connections()
            return
        w = form.get_widget(widget_id)
        if w is None:
            return
        w.events.pop(event_key, None)
        self._set_designer_dirty()
        self._props_panel.refresh_comp_connections()

    def _on_comp_edit(self, comp_id: str, widget_id: str, event_key: str) -> None:
        """Open the Connector dialog pre-populated for an existing component wire."""
        form = self._design_canvas.form
        if form is None:
            return
        comp = form.get_component(comp_id)
        if comp is None:
            return
        # canvas_button edit — open builder pre-filled
        if widget_id == "__canvas_btn__":
            self._open_img_button_builder(comp_id, comp, form, edit_tag=event_key)
            return
        cdef = get_component_def(comp.type)
        if cdef is None:
            return
        # Find the handler_id — from widget event or menu item command_handler
        if widget_id.startswith("__mi__"):
            mi = form.get_menu_item(widget_id[6:])
            method = mi.command_handler if mi else ""
        else:
            w = form.get_widget(widget_id)
            if w is None:
                return
            method = w.events.get(event_key, "")
        hdef = next(
            (h for h in cdef.handler_defs if f"_{comp_id}{h.label}" == method),
            None,
        )
        if hdef is None:
            return
        handler_id = hdef.id

        _FILE_OBJ_HANDLERS = ("ask_open_file", "ask_save_file")
        _POPULATE_TYPES = ("Entry", "Text", "Listbox")
        _INPUT_TYPES = ("string", "integer", "float")
        _MB_TYPES = ("askyesno", "askokcancel", "askretrycancel", "askquestion")
        if handler_id in _FILE_OBJ_HANDLERS:
            _targets = [wd.id for wd in form.widgets if wd.type in _POPULATE_TYPES]
            _primary_opts = ()
            _secondary_opts = tuple(_targets) + ("(none)",)
            _secondary_label = "Populate"
            _secondary_warn = (
                ""
                if _targets
                else "⚠  No Entry, Text, or Listbox on form — add one or choose (none)"
            )
        elif handler_id == "ask_input":
            _primary_opts = _INPUT_TYPES
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""
        elif handler_id == "messagebox":
            _primary_opts = _MB_TYPES
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""
        else:
            _primary_opts = ()
            _secondary_opts = ()
            _secondary_label = "Mode"
            _secondary_warn = ""

        _show_title = comp.type == "CommonDialog"
        _title_entry_label = "Message" if handler_id == "messagebox" else "Title"
        _show_extra = handler_id == "messagebox"
        if handler_id == "messagebox":
            _init_title = comp.props.get("messagebox_message", "")
            _init_extra = comp.props.get("messagebox_title", "")
        else:
            _init_title = (
                comp.props.get(f"{handler_id}_title", "") if _show_title else ""
            )
            _init_extra = ""

        # Connectable menu items (non-cascade command items at indent > 0)
        _all_mi = form.menu_items
        _conn_mi = [
            mi
            for i, mi in enumerate(_all_mi)
            if mi.indent > 0
            and mi.caption != "-"
            and mi.name
            and mi.kind not in ("checkbutton", "radiobutton")
            and not any(
                _all_mi[j].indent == mi.indent + 1
                for j in range(i + 1, len(_all_mi))
                if _all_mi[j].indent <= mi.indent + 1
            )
        ]

        # Resolve widget_id for menu items (strip __mi__ prefix for connector)
        _preselect_wid = widget_id[6:] if widget_id.startswith("__mi__") else widget_id

        def _is_stub(method_name: str) -> bool:
            import re as _re

            root = getattr(self._sidebar.explorer, "_root", None)
            if not root:
                return True
            from pathlib import Path as _Path

            py_path = _Path(root) / f"{form.name}.py"
            if not py_path.exists():
                return True
            try:
                src = py_path.read_text(encoding="utf-8")
            except Exception:
                return False
            m = _re.search(
                rf"def {_re.escape(method_name)}\(self[^)]*\):\s*\n[ \t]+(pass\b)",
                src,
                _re.MULTILINE,
            )
            return bool(m)

        def _on_wire(new_widget_id: str, new_event_key: str, option: str = "") -> None:
            # Remove old binding
            if new_widget_id != _preselect_wid or new_event_key != event_key:
                if widget_id.startswith("__mi__"):
                    old_mi = form.get_menu_item(widget_id[6:])
                    if old_mi:
                        old_mi.command_handler = ""
                else:
                    old_w = form.get_widget(widget_id)
                    if old_w:
                        old_w.events.pop(event_key, None)
            # Set new binding
            new_mi = next((m for m in _conn_mi if m.name == new_widget_id), None)
            if new_mi is not None:
                new_mi.command_handler = method
                self._set_designer_dirty()
                self._props_panel.refresh_comp_connections()
                return
            new_w = form.get_widget(new_widget_id)
            if new_w is None:
                return
            new_w.events[new_event_key] = method
            if handler_id == "messagebox":
                _parts = option.split("|", 2)
                main_opt = _parts[0]
                msg_text = _parts[1] if len(_parts) > 1 else ""
                dlg_title = _parts[2] if len(_parts) > 2 else ""
                comp.props["messagebox_type"] = main_opt or "askyesno"
                if msg_text:
                    comp.props["messagebox_message"] = msg_text
                elif "messagebox_message" in comp.props:
                    del comp.props["messagebox_message"]
                if dlg_title:
                    comp.props["messagebox_title"] = dlg_title
                elif "messagebox_title" in comp.props:
                    del comp.props["messagebox_title"]
            else:
                if _show_title and "|" in option:
                    main_opt, title_val = option.rsplit("|", 1)
                else:
                    main_opt, title_val = option, ""
                if _show_title:
                    if title_val:
                        comp.props[f"{handler_id}_title"] = title_val
                    elif f"{handler_id}_title" in comp.props:
                        del comp.props[f"{handler_id}_title"]
                if handler_id in _FILE_OBJ_HANDLERS:
                    comp.props[f"{handler_id}_target"] = main_opt
                elif handler_id == "ask_input":
                    comp.props["ask_input_type"] = main_opt or "string"
            self._set_designer_dirty()
            self._props_panel.refresh_comp_connections()

        ComponentConnector(
            self,
            form,
            comp_id,
            handler_id,
            hdef.label,
            _on_wire,
            options=_primary_opts,
            secondary_options=_secondary_opts,
            secondary_label=_secondary_label,
            initial_warning=_secondary_warn,
            preselect_widget_id=_preselect_wid,
            preselect_event_key=event_key,
            show_title_entry=_show_title,
            initial_title=_init_title,
            title_entry_label=_title_entry_label,
            show_extra_entry=_show_extra,
            initial_extra=_init_extra,
            extra_entry_label="Title",
            wire_label="Update",
            menu_items=_conn_mi,
            stub_checker=_is_stub,
        )

    def _on_designer_double_click(self, widget_id: str) -> None:
        """Double-click on canvas widget → jump to first event handler or flash Events tab."""
        from pathlib import Path as _Path

        form = self._design_canvas.form
        if form is None:
            return
        w = form.get_widget(widget_id)
        if w is None:
            return
        if not w.events:
            self._props_panel.flash_events_tab()
            return

        root = getattr(self._sidebar.explorer, "_root", None)
        if root:
            py_path = _Path(root) / f"{form.name}.py"
            if self._designer_dirty or not py_path.exists():
                self.designer_generate_code()

        first_handler = next(iter(w.events.values()))
        self._designer_jump_to_handler(first_handler)

    def _on_designer_event_navigate(self, method_name: str) -> None:
        """Double-click on a wired event row → jump to that handler in the editor."""
        from pathlib import Path as _Path

        form = self._design_canvas.form
        if not form:
            return
        root = getattr(self._sidebar.explorer, "_root", None)
        if root:
            py_path = _Path(root) / f"{form.name}.py"
            if self._designer_dirty or not py_path.exists():
                self.designer_generate_code()
        self._designer_jump_to_handler(method_name)

    def _on_designer_menu_item_no_command(self, item_idx: int) -> None:
        """Click on a no-command check/radio menu item → open editor and flash Command field."""
        self._props_panel.open_menu_editor(flash_item_idx=item_idx)

    def _on_designer_menu_navigate(self, method_name: str) -> None:
        """Click on a menu item in the designer → jump to its event handler."""
        form = self._design_canvas.form
        if form is None:
            return
        root = getattr(self._sidebar.explorer, "_root", None)
        if root:
            from pathlib import Path as _Path

            py_path = _Path(root) / f"{form.name}.py"
            if self._designer_dirty or not py_path.exists():
                self.designer_generate_code()
        self._designer_jump_to_handler(method_name)

    def _designer_jump_to_handler(self, method_name: str) -> None:
        """Switch to editor mode and navigate to the named method in the generated .py."""
        from pathlib import Path as _Path

        form = self._design_canvas.form
        root = getattr(self._sidebar.explorer, "_root", None)
        if not form or not root:
            return
        py_path = _Path(root) / f"{form.name}.py"
        self._enter_editor_mode()

        def _navigate():
            # Find or open the generated .py tab
            target_tab = None
            for tab_id, fp in self._files.items():
                if fp and _Path(fp) == py_path:
                    target_tab = tab_id
                    break
            if target_tab is None:
                if py_path.exists():
                    self._open_file(str(py_path))
                    for tab_id, fp in self._files.items():
                        if fp and _Path(fp) == py_path:
                            target_tab = tab_id
                            break
            if target_tab is None:
                return
            # Switch to the tab
            for i, tid in enumerate(self.notebook.tabs()):
                if tid == target_tab:
                    self.notebook.select(i)
                    break
            cv = self._codeviews.get(target_tab)
            if cv is None:
                return
            # Find `def method_name` and navigate
            search = f"def {method_name}"
            for lineno, line in enumerate(cv.get_text().splitlines(), 1):
                if search in line:
                    self._outline_navigate(lineno)
                    return

        self.after(50, _navigate)

    def _on_designer_selector_pick(self, widget_id: str | None) -> None:
        """User picks a control from the selector dropdown → select on canvas."""
        if widget_id is None:
            self._design_canvas.select_form()
        else:
            self._design_canvas.select(widget_id)

    # ── Form list helpers ─────────────────────────────────────────────────────

    def _links_dict(self) -> dict:
        """Build {form_name: [dialog_names]} from current _designer_forms."""
        return {
            f.name: list(f.linked_dialogs)
            for f in self._designer_forms.values()
            if f.form_type == "main"
        }

    def _load_linked_dialogs(self, form, source_dir=None) -> None:
        """Load linked dialog .form.json files for *form*.

        source_dir — directory to search first (e.g. dir of the form file the
                     user just opened via the file picker). When omitted, only
                     the project root is searched.

        Dialogs found in source_dir that are not already in the project root are
        copied there (new files silently; overwrites with a single confirmation
        prompt). Updates _designer_forms, _designer_form_names, and
        _designer_missing_dialogs.
        """
        import shutil as _shutil
        from pathlib import Path as _Path
        from designer.persistence import load as _load

        root = getattr(self._sidebar.explorer, "_root", None)
        root_path = _Path(root) if root else None
        src_path = _Path(source_dir) if source_dir else None

        # Search order: source_dir first (when it differs from root), then root
        search_dirs: list[_Path] = []
        if src_path and (not root_path or src_path.resolve() != root_path.resolve()):
            search_dirs.append(src_path)
        if root_path:
            search_dirs.append(root_path)

        # Accumulate files to copy so we can batch the overwrite prompt
        new_copies: list[tuple[_Path, _Path]] = []  # copies that don't overwrite
        overwrites: list[tuple[_Path, _Path]] = []  # copies that would overwrite

        for dlg_name in list(getattr(form, "linked_dialogs", [])):
            if dlg_name in self._designer_forms:
                self._designer_missing_dialogs.discard(dlg_name)
                continue

            found = False
            for sdir in search_dirs:
                jf = sdir / f"{dlg_name}.form.json"
                if not jf.exists():
                    continue
                try:
                    dlg_form, _ = _load(jf)
                    self._designer_forms[dlg_form.name] = dlg_form
                    if dlg_form.name not in self._designer_form_names:
                        self._designer_form_names.append(dlg_form.name)
                    self._designer_missing_dialogs.discard(dlg_form.name)
                    found = True

                    # Plan file copies when source dir differs from root
                    if root_path and sdir.resolve() != root_path.resolve():
                        for ext in (".form.json", ".py"):
                            src_file = sdir / f"{dlg_name}{ext}"
                            if not src_file.exists():
                                continue
                            dst_file = root_path / f"{dlg_name}{ext}"
                            (overwrites if dst_file.exists() else new_copies).append(
                                (src_file, dst_file)
                            )
                    break
                except Exception:
                    pass  # try next search dir

            if not found:
                self._designer_missing_dialogs.add(dlg_name)

        # Copy new files silently
        for src, dst in new_copies:
            try:
                _shutil.copy2(str(src), str(dst))
            except Exception:
                pass

        # Ask once for any overwrites
        if overwrites:
            from tkinter.messagebox import askyesno as _ask

            bullet = "\n  • ".join(dst.name for _, dst in overwrites)
            if _ask(
                "Overwrite Dialog Files",
                f"These files already exist in the current project:\n  • {bullet}"
                f"\n\nOverwrite them with versions from the source directory?",
                parent=self,
            ):
                for src, dst in overwrites:
                    try:
                        _shutil.copy2(str(src), str(dst))
                    except Exception:
                        pass

        if new_copies or overwrites:
            self._sidebar.explorer.refresh()

    def _form_name_for_file(self, path: str) -> str | None:
        """Return the designer form name whose .py file matches path, or None."""
        from pathlib import Path as _Path

        p = _Path(path)
        if p.stem in self._designer_forms:
            return p.stem
        if p.name == "main.py":
            try:
                import re as _re

                content = p.read_text(encoding="utf-8")
                if self._is_idol_main_py(content):
                    m = _re.search(
                        r"^from\s+(\w+)\s+import\s+\1", content, _re.MULTILINE
                    )
                    if m and m.group(1) in self._designer_forms:
                        return m.group(1)
            except Exception:
                pass
        return None

    def _effective_designer_main(self) -> str | None:
        """Compute which form should show ▶ based on the current run entry."""
        if not self._designer_forms:
            return self._designer_main_form
        if self._run_entry_file and os.path.isfile(self._run_entry_file):
            name = self._form_name_for_file(self._run_entry_file)
            if name:
                return name
        else:
            candidate = self._files.get(self._current_tab_id)
            if candidate:
                name = self._form_name_for_file(candidate)
                if name:
                    return name
        return self._designer_main_form

    def _refresh_form_list(self, active: str | None = None) -> None:
        """Re-render the FormListPanel with current state."""
        if active is None:
            active_form = self._design_canvas.form
            active = active_form.name if active_form else None
        self._form_list_panel.set_forms(
            [(f.name, f.form_type) for f in self._designer_forms.values()],
            links=self._links_dict(),
            active=active,
            missing=self._designer_missing_dialogs,
            main_form=self._effective_designer_main(),
        )

    def _on_form_list_select(self, form_name: str) -> None:
        """FormListPanel click — switch canvas to the named form."""
        if form_name in self._designer_missing_dialogs:
            self.designer_open_form()
            return
        if self._design_canvas.form and self._design_canvas.form.name == form_name:
            return
        self._designer_autosave()
        form = self._designer_forms.get(form_name)
        if form is None:
            return
        self._design_canvas.load_form(form)
        self._props_panel.set_form(form)
        self._props_panel.load_form(form)
        self._comp_tray.refresh(form.components)
        self._comp_tray.deselect()
        self._designer_menu_had_items = bool(form.menu_items)
        self._form_list_panel.set_active(form_name)
        self._refresh_generate_code_state()

    def _on_form_link(self, dialog_name: str, form_name: str) -> None:
        """Tree drag-drop — link a dialog to a form."""
        form = self._designer_forms.get(form_name)
        if form is None or dialog_name in form.linked_dialogs:
            return
        form.linked_dialogs.append(dialog_name)
        self._set_designer_dirty()
        self._refresh_form_list()

    def _on_form_unlink(self, dialog_name: str, form_name: str) -> None:
        """Tree × click — unlink a dialog from a form."""
        form = self._designer_forms.get(form_name)
        if form is None or dialog_name not in form.linked_dialogs:
            return
        form.linked_dialogs.remove(dialog_name)
        self._set_designer_dirty()
        self._refresh_form_list()

    def _on_designer_form_remove(self, name: str) -> None:
        """Remove a form from the designer view without deleting files.

        For main forms, also removes all of their linked dialogs.
        Removes from _designer_forms and _designer_form_names so nothing
        is re-loaded on the next session restore.  Files on disk are untouched.
        """
        # Collect dialogs owned by this form before we remove it
        form_obj = self._designer_forms.get(name)
        linked = list(form_obj.linked_dialogs) if form_obj else []

        def _drop(n: str) -> None:
            self._designer_forms.pop(n, None)
            self._designer_missing_dialogs.discard(n)
            if n == self._designer_main_form:
                self._designer_main_form = None
            if n in self._designer_form_names:
                self._designer_form_names.remove(n)

        # Remove the form itself and, for main forms, cascade to linked dialogs
        _drop(name)
        for dlg in linked:
            # Also strip the dialog from any other parent's linked_dialogs list
            for f in self._designer_forms.values():
                if dlg in f.linked_dialogs:
                    f.linked_dialogs.remove(dlg)
            _drop(dlg)

        # For dialogs being removed standalone, strip from any parent list
        for form in self._designer_forms.values():
            if name in form.linked_dialogs:
                form.linked_dialogs.remove(name)

        dropped_names = {name} | set(linked)
        current = self._design_canvas.form
        if current is None or current.name in dropped_names:
            remaining = list(self._designer_forms.values())
            if remaining:
                nxt = remaining[0]
                self._design_canvas.load_form(nxt)
                self._props_panel.set_form(nxt)
                self._props_panel.load_form(nxt)
                self._comp_tray.refresh(nxt.components)
                self._comp_tray.deselect()
            else:
                self._design_canvas.load_form(None)
                self._props_panel.clear()
                self._comp_tray.refresh([])

        self._refresh_form_list()
        self._set_designer_dirty()
        self._refresh_generate_code_state()

    def _idol_main_py_content(self, form_name: str) -> str:
        return (
            f"# Generated by IDOL Designer\n"
            f"from {form_name} import {form_name}\n"
            f"\n"
            f'if __name__ == "__main__":\n'
            f"    app = {form_name}()\n"
            f"    app.mainloop()\n"
        )

    def _is_idol_main_py(self, content: str) -> bool:
        return "# Generated by IDOL Designer" in content

    def _on_form_set_as_main(self, name: str) -> None:
        from pathlib import Path as _Path

        root = getattr(self._sidebar.explorer, "_root", None)
        if not root:
            return
        main_path = _Path(root) / "main.py"
        if main_path.exists():
            try:
                existing = main_path.read_text(encoding="utf-8")
            except Exception:
                existing = ""
            if not self._is_idol_main_py(existing):
                from tkinter.messagebox import askyesno as _ask

                if not _ask(
                    "Overwrite main.py",
                    f"main.py already exists and was not generated by IDOL Designer.\n\n"
                    f"Overwrite it to launch '{name}'?",
                    parent=self,
                ):
                    return
        try:
            main_path.write_text(self._idol_main_py_content(name), encoding="utf-8")
        except Exception as exc:
            from tkinter.messagebox import showerror

            showerror("Error", f"Could not write main.py:\n{exc}", parent=self)
            return
        self._designer_main_form = name
        self._set_run_entry(str(main_path))
        self._refresh_form_list()
        self._sidebar.explorer.refresh()

    def _on_form_list_context_menu(
        self, name: str, kind: str, parent: str | None, x_root: int, y_root: int
    ) -> None:
        """Show the FORMS tree right-click context menu."""
        menu = tk.Menu(
            self,
            tearoff=0,
            bg="#2d2d2d",
            fg="#cccccc",
            activebackground="#094771",
            activeforeground="#ffffff",
            relief="flat",
            bd=0,
        )

        if kind == "form":
            already_main = name == self._designer_main_form
            menu.add_command(
                label="Set as Main" + (" ✓" if already_main else ""),
                state="disabled" if already_main else "normal",
                command=lambda: self._on_form_set_as_main(name),
            )
            menu.add_separator()

        menu.add_command(
            label="Remove from Designer",
            command=lambda: self._on_designer_form_remove(name),
        )

        # Unlink — only meaningful for linked dialogs
        if kind == "linked" and parent:
            menu.add_command(
                label="Unlink",
                command=lambda: self._on_form_unlink(name, parent),
            )
        else:
            menu.add_command(label="Unlink", state="disabled")

        menu.add_separator()

        menu.add_command(
            label="Delete",
            foreground="#f14c4c",
            activeforeground="#ff6b6b",
            command=lambda: self._on_designer_form_delete(name),
        )

        try:
            menu.tk_popup(x_root, y_root)
        finally:
            menu.grab_release()

    def _on_designer_form_delete(self, name: str) -> None:
        """Permanently delete a form — removes files from disk."""
        from tkinter.messagebox import askyesno
        from pathlib import Path as _Path

        confirmed = askyesno(
            "Delete Form",
            f'Permanently delete "{name}"?\n\n'
            "This will remove its .py and .form.json files and cannot be undone.",
            icon="warning",
            parent=self,
        )
        if not confirmed:
            return

        root = getattr(self._sidebar.explorer, "_root", None)

        # Close any open editor tabs that point to this form's .py file
        if root:
            py_norm = os.path.normcase(str(_Path(root) / f"{name}.py"))
            for tab_id, tab_path in list(self._files.items()):
                if tab_path and os.path.normcase(tab_path) == py_norm:
                    idx = self.notebook.tabs().index(tab_id)
                    self._close_tab(idx)
                    break

        # Remove from linked_dialogs of any parent form
        for form in self._designer_forms.values():
            if name in form.linked_dialogs:
                form.linked_dialogs.remove(name)

        # Remove from in-memory dict and explicit tracking list
        self._designer_forms.pop(name, None)
        self._designer_missing_dialogs.discard(name)
        if name == self._designer_main_form:
            self._designer_main_form = None
        if name in self._designer_form_names:
            self._designer_form_names.remove(name)

        # If this was the active canvas form, switch to the first remaining form
        current = self._design_canvas.form
        if current and current.name == name:
            remaining = list(self._designer_forms.values())
            if remaining:
                next_form = remaining[0]
                self._design_canvas.load_form(next_form)
                self._props_panel.set_form(next_form)
                self._props_panel.load_form(next_form)
                self._comp_tray.refresh(next_form.components)
                self._comp_tray.deselect()
            else:
                self._design_canvas.load_form(None)
                self._props_panel.clear()
                self._comp_tray.refresh([])

        # Delete files from disk
        if root:
            for ext in (".py", ".form.json"):
                fp = _Path(root) / f"{name}{ext}"
                try:
                    fp.unlink(missing_ok=True)
                except Exception:
                    pass

        self._refresh_form_list()
        self._set_designer_dirty()
        self._sidebar.explorer.refresh()
        self._refresh_generate_code_state()

    def designer_new_form(self) -> None:
        """Open a small dialog to create a new form or dialog."""
        from designer.model import FormModel as _FormModel

        win = tk.Toplevel(self)
        win.withdraw()
        win.title("New Form")
        win.resizable(False, False)
        win.configure(bg="#2d2d2d")
        win.transient(self)

        tk.Label(
            win, text="Form Name:", bg="#2d2d2d", fg="#cccccc", font=(UI_FONT, 9)
        ).grid(row=0, column=0, padx=12, pady=(14, 4), sticky="w")

        default_type = "dialog" if self._designer_forms else "main"
        type_var = tk.StringVar(value=default_type)

        name_var = tk.StringVar(value=self._next_form_name(default_type))
        name_entry = tk.Entry(
            win,
            textvariable=name_var,
            bg="#3c3c3c",
            fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat",
            font=(UI_FONT, 9),
            width=22,
        )
        name_entry.grid(row=0, column=1, padx=(0, 12), pady=(14, 4))
        name_entry.select_range(0, "end")
        name_entry.focus_set()

        tk.Label(win, text="Type:", bg="#2d2d2d", fg="#cccccc", font=(UI_FONT, 9)).grid(
            row=1, column=0, padx=12, pady=4, sticky="w"
        )

        type_frame = tk.Frame(win, bg="#2d2d2d")
        type_frame.grid(row=1, column=1, padx=(0, 12), pady=4, sticky="w")
        for lbl, val in [("Main Window", "main"), ("Dialog Window", "dialog")]:
            tk.Radiobutton(
                type_frame,
                text=lbl,
                variable=type_var,
                value=val,
                bg="#2d2d2d",
                fg="#cccccc",
                selectcolor="#094771",
                activebackground="#2d2d2d",
                font=(UI_FONT, 9),
                highlightthickness=0,
                relief="flat",
            ).pack(side="left", padx=(0, 8))

        tk.Label(
            win, text="Link to:", bg="#2d2d2d", fg="#cccccc", font=(UI_FONT, 9)
        ).grid(row=2, column=0, padx=12, pady=4, sticky="w")

        main_forms = [
            f.name for f in self._designer_forms.values() if f.form_type == "main"
        ]
        link_options = ["None (unlinked)"] + main_forms
        link_var = tk.StringVar(
            value=main_forms[0] if main_forms else "None (unlinked)"
        )
        link_cb = ttk.Combobox(
            win,
            textvariable=link_var,
            values=link_options,
            state="readonly",
            font=(UI_FONT, 9),
            width=20,
        )
        link_cb.grid(row=2, column=1, padx=(0, 12), pady=4, sticky="w")

        def _on_type_change(*_):
            ft = type_var.get()
            # Auto-update name only when it still matches the previous auto-name
            old_auto = self._next_form_name("main" if ft == "dialog" else "dialog")
            if name_var.get() == old_auto:
                name_var.set(self._next_form_name(ft))
            if ft == "main":
                link_cb.config(state="disabled")
                link_var.set("None (unlinked)")
            else:
                link_cb.config(state="readonly")

        type_var.trace_add("write", _on_type_change)

        btn_frame = tk.Frame(win, bg="#2d2d2d")
        btn_frame.grid(row=3, column=0, columnspan=2, pady=(8, 12))

        def _create():
            name = name_var.get().strip()
            if not name or not name.isidentifier():
                name_entry.config(bg="#5a1a1a")
                return
            if name in self._designer_forms:
                name_entry.config(bg="#5a1a1a")
                return
            # Warn if files would be overwritten in the project root
            _root = getattr(self._sidebar.explorer, "_root", None)
            if _root:
                from pathlib import Path as _Path

                _existing = [
                    f"{name}.form.json"
                    for f in [_Path(_root) / f"{name}.form.json"]
                    if f.exists()
                ] + [f"{name}.py" for f in [_Path(_root) / f"{name}.py"] if f.exists()]
                if _existing:
                    from tkinter.messagebox import askyesno as _ask

                    bullet = "\n  • ".join(_existing)
                    if not _ask(
                        "Existing Files",
                        f"These files already exist in the project:\n  • {bullet}"
                        f"\n\nCreating '{name}' will overwrite them. Continue?",
                        parent=win,
                    ):
                        return
            link_to = link_var.get()
            form_type = type_var.get()
            win.destroy()
            from designer.handlers import default_enabled_for as _def_handlers

            form = _FormModel(
                name=name,
                title=name,
                width=400,
                height=300,
                form_type=form_type,
                enabled_handlers=_def_handlers(form_type),
            )
            self._designer_forms[name] = form
            if name not in self._designer_form_names:
                self._designer_form_names.append(name)
            if form_type == "dialog" and link_to != "None (unlinked)":
                parent = self._designer_forms.get(link_to)
                if parent and name not in parent.linked_dialogs:
                    parent.linked_dialogs.append(name)
            self._designer_autosave()
            self._design_canvas.load_form(form)
            self._props_panel.set_form(form)
            self._props_panel.load_form(form)
            self._comp_tray.refresh(form.components)
            self._comp_tray.deselect()
            self._designer_menu_had_items = False
            self._set_designer_dirty()
            self._refresh_form_list(active=name)
            self._show_mode_bar()
            if not self._designer_mode:
                self._enter_designer_mode()
            self._refresh_generate_code_state()
            # Generate code immediately so the .py exists, then open it
            root = getattr(self._sidebar.explorer, "_root", None)
            if root:
                if self._autogen_after_id:
                    self.after_cancel(self._autogen_after_id)
                    self._autogen_after_id = None
                self.designer_generate_code()
                from pathlib import Path as _Path

                py_path = str(_Path(root) / f"{name}.py")
                if _Path(py_path).exists():
                    self._open_file(py_path, update_explorer=False, select=False)
                # Refresh explorer so new files appear without triggering a terminal cd
                self._sidebar.explorer.refresh()

        def _lbtn(parent, text, cmd, bg, fg, hover, bold=False):
            font = (UI_FONT, 9, "bold") if bold else (UI_FONT, 9)
            b = tk.Label(
                parent,
                text=text,
                bg=bg,
                fg=fg,
                font=font,
                cursor="hand2",
                padx=14,
                pady=4,
            )
            b.bind("<Button-1>", lambda _: cmd())
            b.bind("<Enter>", lambda _: b.config(bg=hover))
            b.bind("<Leave>", lambda _: b.config(bg=bg))
            return b

        _lbtn(
            btn_frame,
            "Create",
            _create,
            bg="#0e639c",
            fg="#ffffff",
            hover="#1177bb",
            bold=True,
        ).pack(side="left", padx=(0, 4))
        _lbtn(
            btn_frame,
            "Cancel",
            win.destroy,
            bg="#3c3c3c",
            fg="#cccccc",
            hover="#4a4a4a",
        ).pack(side="left", padx=(0, 4))

        win.bind("<Return>", lambda _: _create())
        win.bind("<Escape>", lambda _: win.destroy())

        # Centre on parent, then reveal
        self.update_idletasks()
        px = self.winfo_rootx() + self.winfo_width() // 2
        py = self.winfo_rooty() + self.winfo_height() // 2
        win.update_idletasks()
        win.geometry(f"+{px - win.winfo_width() // 2}+{py - win.winfo_height() // 2}")
        win.deiconify()
        win.grab_set()

    def _next_form_name(self, form_type: str = "dialog") -> str:
        """Return the next available Form{n} or Dialog{n} name."""
        existing = set(self._designer_forms)
        prefix = "Form" if form_type == "main" else "Dialog"
        n = 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

    def designer_close_form(self) -> None:
        """Unload the current form from the designer canvas."""
        if self._autogen_after_id:
            self.after_cancel(self._autogen_after_id)
            self._autogen_after_id = None
        self._design_canvas._form = None
        self._design_canvas.delete("all")
        self._props_panel.clear()
        self._designer_forms.clear()
        self._designer_form_names.clear()
        self._designer_missing_dialogs.clear()
        self._designer_main_form = None
        self._form_list_panel.set_forms([])
        self._refresh_generate_code_state()

    def designer_open_form(self) -> None:
        """Open a .form.json file and load it into the designer canvas."""
        from pathlib import Path as _Path
        from tkinter.filedialog import askopenfilename
        from designer.persistence import load as _load

        initial_dir = str(self._sidebar.explorer._root or os.getcwd())
        path = askopenfilename(
            filetypes=[("Designer Form", "*.form.json"), ("All Files", "*.*")],
            title="Open Form",
            initialdir=initial_dir,
            parent=self,
        )
        if not path:
            return
        try:
            form, _ = _load(_Path(path))
            self._designer_forms[form.name] = form
            self._designer_missing_dialogs.discard(form.name)
            if form.name not in self._designer_form_names:
                self._designer_form_names.append(form.name)
            self._load_linked_dialogs(form, source_dir=_Path(path).parent)
            self._design_canvas.load_form(form)
            self._props_panel.set_form(form)
            self._props_panel.load_form(form)
            self._comp_tray.refresh(form.components)
            self._comp_tray.deselect()
            self._designer_menu_had_items = bool(form.menu_items)
            self._designer_dirty = False
            self._refresh_form_list(active=form.name)
            self._show_mode_bar()
            self._refresh_generate_code_state()
            if not self._designer_mode:
                self._enter_designer_mode()
            # Copy the companion .py to CWD if the source is from a different dir
            import shutil as _shutil

            src_dir = _Path(path).parent
            root_dir = _Path(getattr(self._sidebar.explorer, "_root", None) or ".")
            src_py = src_dir / f"{form.name}.py"
            dst_py = root_dir / f"{form.name}.py"
            py_to_open = None
            if src_py.exists():
                if src_dir.resolve() == root_dir.resolve():
                    py_to_open = src_py  # already in CWD, just open it
                else:
                    do_copy = True
                    if dst_py.exists():
                        from tkinter.messagebox import askyesno as _ask

                        do_copy = _ask(
                            "Copy Python File",
                            f"'{form.name}.py' already exists in the current project.\n\n"
                            f"Overwrite it with the version from:\n{src_dir}?",
                            parent=self,
                        )
                    if do_copy:
                        _shutil.copy2(str(src_py), str(dst_py))
                        self._sidebar.explorer.refresh()
                    py_to_open = dst_py if dst_py.exists() else src_py
            elif dst_py.exists():
                py_to_open = dst_py  # .py already in project, open it
            if py_to_open:
                py_str = str(py_to_open)
                existing_tab = next(
                    (tid for tid, fp in self._files.items() if fp == py_str), None
                )
                if existing_tab:
                    self.notebook.select(existing_tab)
                else:
                    self._open_file(py_str, update_explorer=False)
        except Exception as exc:
            from tkinter.messagebox import showerror

            showerror("Open Form", f"Could not load form:\n{exc}", parent=self)

    def _open_form_json_in_designer(self, path: str) -> None:
        """Open a .form.json from the explorer right-click menu into the designer."""
        from pathlib import Path as _Path
        from designer.persistence import load as _load

        try:
            form, _ = _load(_Path(path))
            self._designer_forms[form.name] = form
            self._designer_missing_dialogs.discard(form.name)
            if form.name not in self._designer_form_names:
                self._designer_form_names.append(form.name)
            self._load_linked_dialogs(form, source_dir=_Path(path).parent)
            self._design_canvas.load_form(form)
            self._props_panel.set_form(form)
            self._props_panel.load_form(form)
            self._comp_tray.refresh(form.components)
            self._comp_tray.deselect()
            self._designer_menu_had_items = bool(form.menu_items)
            self._designer_dirty = False
            self._refresh_form_list(active=form.name)
            self._show_mode_bar()
            self._refresh_generate_code_state()
            if not self._designer_mode:
                self._enter_designer_mode()
            # Open companion .py in the editor (prefer CWD copy)
            root_dir = _Path(getattr(self._sidebar.explorer, "_root", None) or ".")
            src_dir = _Path(path).parent
            dst_py = root_dir / f"{form.name}.py"
            src_py = src_dir / f"{form.name}.py"
            py_to_open = (
                dst_py if dst_py.exists() else (src_py if src_py.exists() else None)
            )
            if py_to_open:
                py_str = str(py_to_open)
                existing_tab = next(
                    (tid for tid, fp in self._files.items() if fp == py_str), None
                )
                if existing_tab:
                    self.notebook.select(existing_tab)
                else:
                    self._open_file(py_str, update_explorer=False)
        except Exception as exc:
            from tkinter.messagebox import showerror

            showerror("Open in Designer", f"Could not load form:\n{exc}", parent=self)

    def designer_generate_code(self) -> None:
        """Regenerate .py for all forms in the project and save checksums."""
        root = getattr(self._sidebar.explorer, "_root", None)
        active_form = self._design_canvas.form
        if active_form is None or not root:
            return

        # Sync active canvas model into the dict before generating
        self._designer_forms[active_form.name] = active_form

        # Generate dialogs first so imports resolve when main form is generated
        for form in self._designer_forms.values():
            if form.form_type != "main":
                self._generate_one_form(form, root)

        for form in self._designer_forms.values():
            if form.form_type == "main":
                self._generate_one_form(form, root)

        self._designer_dirty = False
        self._designer_forms_dirty = False

    def _generate_one_form(self, form, root: str) -> None:
        from pathlib import Path as _Path
        from designer.codegen import generate as _gen
        from designer.persistence import (
            save as _save,
            compute_checksum as _cs,
            extract_event_bodies as _bodies,
            extract_event_signatures as _sigs,
            extract_init_user_zones as _init_zones,
            extract_helper_methods as _helpers,
            extract_user_imports as _user_imports,
            load as _load,
            was_modified as _modified,
        )

        json_path = _Path(root) / f"{form.name}.form.json"
        py_path = _Path(root) / f"{form.name}.py"

        # Manual edits are always preserved (event bodies, helpers, init zones)
        # so no confirmation is needed before regenerating.

        if py_path.exists():
            event_bodies = _bodies(py_path)
            event_sigs = _sigs(py_path)
            pre_init, post_init = _init_zones(py_path)
            helpers = _helpers(py_path)
            user_imports = _user_imports(py_path)
            # Drop stale auto-bodies so the new wire body becomes the default
            for _m in self._pending_body_resets:
                event_bodies.pop(_m, None)
            self._pending_body_resets.clear()
        else:
            event_bodies, event_sigs, pre_init, post_init, helpers, user_imports = (
                {},
                {},
                "",
                "",
                "",
                "",
            )

        # Determine each linked dialog's close mode for opener body generation.
        # Uses destroy mode if _on_close OR _on_escape is set to "destroy".
        # Read from the in-memory model so the value is always current.
        dialog_modes: dict[str, str] = {}
        if form.form_type == "main":
            for dlg_name in form.linked_dialogs:
                dlg_mem = self._designer_forms.get(dlg_name)
                if dlg_mem is not None:
                    opts = dlg_mem.handler_options
                    is_destroy = opts.get("_on_close", "").startswith(
                        "destroy"
                    ) or opts.get("_on_escape", "").startswith("destroy")
                    dialog_modes[dlg_name] = "destroy" if is_destroy else "hide"

        code = _gen(
            form,
            event_bodies=event_bodies,
            event_signatures=event_sigs,
            pre_init=pre_init,
            post_init=post_init,
            helpers=helpers,
            user_imports=user_imports,
            linked_dialogs=list(form.linked_dialogs)
            if form.form_type == "main"
            else None,
            dialog_modes=dialog_modes or None,
        )
        py_path.write_text(code, encoding="utf-8")
        checksum = _cs(py_path)
        _save(form, json_path, py_checksum=checksum)

        # If the generated file is open in a tab, refresh it in place
        for tab_id, fp in list(self._files.items()):
            if fp and _Path(fp) == py_path:
                cv = self._codeviews.get(tab_id)
                if cv:
                    scroll = cv.scroll_y
                    saved_cursor = cv.get_cursor()
                    cv.set_text(code)
                    cv.scroll_y = scroll
                    cv.set_cursor(*saved_cursor)
                    self._dirty[tab_id] = False
                    self._refresh_tab_title(tab_id)
                break

    # ── Split editor ──────────────────────────────────────────────────────────

    def _ensure_split_shown(self, open_tab_id: str | None = None) -> None:
        """Build + show the split pane if needed, optionally opening a tab."""
        if not self._split_active:
            self._build_right_pane()
            if open_tab_id:
                self._add_tab_to_split(open_tab_id)
            self._split_active = True
            self._split_shown = True
            self._set_active_pane("right")
            self._patch_scroll_callbacks()
            self._refresh_nav_bar()
        elif not self._split_shown:
            self._show_split()

    def _hide_split(self) -> None:
        """Hide the split pane without destroying it or its tabs."""
        if not self._split_active or not self._split_shown:
            return
        self._patched_scroll_pair = None
        for cv in (self._get_left_cv(), self._get_right_cv()):
            if cv is not None:
                cv.on_scroll = None
        try:
            self._split_sash_pos = self._split_pane.sashpos(0)
        except Exception:
            pass
        self._split_pane.forget(self._nb_frame_r)
        self._split_shown = False
        self._refresh_nav_bar()

    def _show_split(self) -> None:
        """Re-show a hidden split pane, restoring the sash position."""
        if not self._split_active or self._split_shown:
            return
        # Guard: tabs were all closed somehow — destroy cleanly instead of showing empty pane
        if not self._notebook_r or not self._notebook_r.tabs():
            self._close_split()
            return
        self._split_pane.add(self._nb_frame_r, weight=1)
        if self._split_sash_pos and self._split_sash_pos > 10:
            pos = self._split_sash_pos
            self.after(10, lambda: self._split_pane.sashpos(0, pos))
        else:
            # No saved position — default to midpoint
            def _set_mid():
                w = self._split_pane.winfo_width()
                if w > 10:
                    self._split_pane.sashpos(0, w // 2)

            self.after(50, _set_mid)
        self._split_shown = True
        self._set_active_pane("right")
        self._patch_scroll_callbacks()
        self._refresh_nav_bar()

    def _copy_to_split(self, tab_id: str | None) -> None:
        """Right-click: open a copy of tab_id in the split, keep it in main too."""
        if not tab_id:
            return
        self._ensure_split_shown()
        self._add_tab_to_split(tab_id)
        self._set_active_pane("right")
        self._patch_scroll_callbacks()

    def _move_to_split(self, tab_id: str | None) -> None:
        """Drag main→split: move the tab (remove from main, open in split)."""
        if not tab_id or tab_id == self._welcome_tab:
            return
        path = self._files.get(tab_id)
        title = self._titles.get(tab_id, "Untitled")
        cv = self._codeviews.get(tab_id)
        content = _cv_text(cv) if cv else ""
        dirty = self._dirty.get(tab_id, False)
        tmp = self._temp_files.pop(tab_id, None)

        self._ensure_split_shown()
        self._new_tab_in(self._notebook_r, title, content, filepath=path)
        new_tid = self._notebook_r.tabs()[-1]
        if dirty:
            self._dirty[new_tid] = True
            self._refresh_tab_title(new_tid)
            if tmp:
                self._temp_files[new_tid] = tmp
        self._remove_tab_silent(tab_id, self.notebook)
        # If main notebook is now empty, show Welcome so it's never blank
        if not self.notebook.tabs():
            self.view_welcome()
        self._set_active_pane("right")
        self._patch_scroll_callbacks()

    def _copy_to_main(self, tab_id: str | None) -> None:
        """Right-click on split tab: open a copy in main, keep it in split too."""
        if not tab_id:
            return
        path = self._files.get(tab_id)
        title = self._titles.get(tab_id, "Untitled")
        cv = self._codeviews.get(tab_id)
        content = _cv_text(cv) if cv else ""
        self._new_tab(title, content, filepath=path)
        self._set_active_pane("left")

    def _move_to_main(self, tab_id: str | None) -> None:
        """Drag split→main: move the tab (remove from split, open in main)."""
        if not tab_id:
            return
        path = self._files.get(tab_id)
        title = self._titles.get(tab_id, "Untitled")
        cv = self._codeviews.get(tab_id)
        content = _cv_text(cv) if cv else ""
        dirty = self._dirty.get(tab_id, False)
        tmp = self._temp_files.pop(tab_id, None)

        self._new_tab(title, content, filepath=path)
        new_tid = self.notebook.tabs()[-1]
        if dirty:
            self._dirty[new_tid] = True
            self._refresh_tab_title(new_tid)
            if tmp:
                self._temp_files[new_tid] = tmp
        self._remove_tab_silent(tab_id, self._notebook_r)
        self._set_active_pane("left")
        # If split is now empty, hide it (don't destroy — X button does that)
        if self._notebook_r and not self._notebook_r.tabs():
            self._hide_split()

    def _add_tab_to_split(self, tab_id: str) -> None:
        """Open a copy of main-pane tab_id in the split notebook."""
        path = self._files.get(tab_id)
        title = self._titles.get(tab_id, "Untitled")
        cv = self._codeviews.get(tab_id)
        content = _cv_text(cv) if cv else ""
        self._new_tab_in(self._notebook_r, title, content, filepath=path)

    def _remove_tab_silent(self, tab_id: str, nb: "CustomNotebook") -> None:
        """Remove a tab from notebook without unsaved-changes prompt."""
        closed_path = self._files.pop(tab_id, None)
        self._titles.pop(tab_id, None)
        self._dirty.pop(tab_id, None)
        self._clean_crcs.pop(tab_id, None)
        self._indent_sizes.pop(tab_id, None)
        self._breadcrumbs.pop(tab_id, None)
        self._codeviews.pop(tab_id, None)
        kh = self._key_handlers.pop(tab_id, None)
        if kh:
            kh.detach()
        mc = self._multi_cursors.pop(tab_id, None)
        if mc:
            mc.clear()
        # Don't close LSP file — it may still be open in the other pane
        try:
            idx = list(nb.tabs()).index(tab_id)
            nb.forget(idx)
        except Exception:
            pass

    def _build_right_pane(self) -> None:
        """Create the right notebook frame and wire it up."""
        import tkinter as tk

        self._nb_frame_r = ttk.Frame(self._split_pane)
        self._split_pane.add(self._nb_frame_r, weight=1)

        # Set sash to midpoint after geometry settles.
        _mid_set = [False]

        def _on_split_configured(event):
            if _mid_set[0]:
                return
            w = event.width
            if w > 10:
                _mid_set[0] = True
                self._split_pane.unbind("<Configure>")
                self._split_pane.sashpos(0, w // 2)

        self._split_pane.bind("<Configure>", _on_split_configured)

        # Thin header with "SPLIT" label, lock button, and × close button
        hdr = tk.Frame(self._nb_frame_r, bg="#2d2d30", height=24)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr,
            text="  SPLIT",
            bg="#2d2d30",
            fg="#858585",
            font=(UI_FONT, 8, "bold"),
        ).pack(side="left")
        close_lbl = tk.Label(
            hdr,
            text="✕",
            bg="#2d2d30",
            fg="#858585",
            font=(UI_FONT, 9),
            cursor="hand2",
            padx=6,
        )
        close_lbl.pack(side="right")
        close_lbl.bind("<Enter>", lambda _: close_lbl.config(fg="#cccccc"))
        close_lbl.bind("<Leave>", lambda _: close_lbl.config(fg="#858585"))
        close_lbl.bind("<ButtonRelease-1>", lambda _: self._close_split())

        self._scroll_locked = self._get_system_scroll_lock()
        self._lock_btn = tk.Label(
            hdr,
            text="⇕",
            bg="#2d2d30",
            fg="#007acc" if self._scroll_locked else "#555555",
            font=(UI_FONT, 10),
            cursor="hand2",
            padx=4,
        )
        self._lock_btn.pack(side="right")
        self._lock_btn.bind("<Button-1>", lambda _: self._toggle_scroll_lock())
        self._lock_btn.bind(
            "<Enter>",
            lambda _: self._lock_btn.config(
                fg="#1a9fd4" if self._scroll_locked else "#cccccc"
            ),
        )
        self._lock_btn.bind(
            "<Leave>",
            lambda _: self._lock_btn.config(
                fg="#007acc" if self._scroll_locked else "#555555"
            ),
        )

        # Blank spacer matching the [Editor|Designer] mode bar height.
        # Shown when the mode bar is visible so both panes align.
        self._split_mode_bar_spacer = tk.Frame(
            self._nb_frame_r, bg="#1e1e1e", height=28
        )
        self._split_mode_bar_spacer.pack_propagate(False)
        if self._mode_bar.winfo_ismapped():
            self._split_mode_bar_spacer.pack(fill="x")

        self._notebook_r = CustomNotebook(
            self._nb_frame_r,
            on_close=lambda idx: self._close_tab(idx, self._notebook_r),
            on_split=self._copy_to_main,
            on_drag_main=self._move_to_main,
            split_label="Open in Main Editor",
        )
        self._notebook_r.pack(fill="both", expand=True)
        self._notebook_r._left_pane_ref = lambda: self._nb_frame_l
        self._notebook_r.bind(
            "<<NotebookTabChanged>>",
            lambda _: self._on_tab_changed_r(),
            add=True,
        )
        self._notebook_r.bind(
            "<ButtonPress-1>",
            lambda _: self._set_active_pane("right"),
            add=True,
        )

    def _on_tab_changed_r(self) -> None:
        """Tab changed in the right notebook — set it active and refresh outline."""
        self._active_pane = "right"
        self._on_tab_changed()
        if self._split_active and self._split_shown:
            self._patch_scroll_callbacks()

    @staticmethod
    def _get_system_scroll_lock() -> bool:
        """Return the current hardware Scroll Lock key state."""
        import platform

        try:
            if platform.system() == "Windows":
                import ctypes

                return bool(ctypes.windll.user32.GetKeyState(0x91) & 1)
            elif platform.system() == "Linux":
                import subprocess

                out = subprocess.check_output(
                    ["xset", "q"], stderr=subprocess.DEVNULL, text=True
                )
                for line in out.splitlines():
                    if "Scroll Lock" in line:
                        return "on" in line.lower().split("Scroll Lock")[1][:10]
            # macOS has no accessible Scroll Lock state — default to off
        except Exception:
            pass
        return False

    def _toggle_scroll_lock(self) -> None:
        self._scroll_locked = not self._scroll_locked
        if self._lock_btn:
            self._lock_btn.config(fg="#007acc" if self._scroll_locked else "#555555")
        if self._scroll_locked:
            # Snap right pane to match left pane immediately
            left_cv = self._get_left_cv()
            right_cv = self._get_right_cv()
            if left_cv and right_cv:
                right_cv.yview_moveto(
                    left_cv.yview()[0]
                )  # yview_moveto on CanvasCodeView

    def _get_left_cv(self):
        tid = self.notebook.select() if self.notebook.tabs() else None
        return self._codeviews.get(tid) if tid else None

    def _get_right_cv(self):
        if not self._notebook_r or not self._notebook_r.tabs():
            return None
        tid = self._notebook_r.select()
        return self._codeviews.get(tid)

    def _on_scroll_locked(self, source: str, *args) -> None:
        """Kept for compatibility; scroll sync is now handled via on_scroll hooks."""
        if not self._scroll_locked:
            return
        left_cv = self._get_left_cv()
        right_cv = self._get_right_cv()
        if not left_cv or not right_cv:
            return
        fraction = float(args[0])
        if source == "left":
            right_cv.yview_moveto(fraction)
        else:
            left_cv.yview_moveto(fraction)

    def _patch_scroll_callbacks(self) -> None:
        """Wire on_scroll hooks on both codeviews so scroll lock can sync them.

        Safe to call repeatedly — skips if the same pair is already patched.
        """
        left_cv = self._get_left_cv()
        right_cv = self._get_right_cv()
        if not left_cv or not right_cv:
            return

        # Skip if already patched with this exact pair (avoid chaining wrappers)
        if getattr(self, "_patched_scroll_pair", None) == (id(left_cv), id(right_cv)):
            return
        self._patched_scroll_pair = (id(left_cv), id(right_cv))

        # Clear any hooks left over from a previous split pair
        for cv in (left_cv, right_cv):
            cv.on_scroll = None

        def _sync_to(target_cv, first: float) -> None:
            if self._scroll_locked and not self._syncing_scroll:
                self._syncing_scroll = True
                try:
                    if target_cv.winfo_exists():
                        target_cv.yview_moveto(float(first))
                finally:
                    self._syncing_scroll = False

        left_cv.on_scroll = lambda first, last: _sync_to(right_cv, first)
        right_cv.on_scroll = lambda first, last: _sync_to(left_cv, first)

    def _close_split(self) -> None:
        """X button: close all split tabs (with unsaved-changes prompts) and destroy pane."""
        if not self._split_active or self._notebook_r is None:
            return
        self._patched_scroll_pair = None
        for cv in (self._get_left_cv(), self._get_right_cv()):
            if cv is not None:
                cv.on_scroll = None
        # Prompt for each dirty tab
        for tab_id in list(self._notebook_r.tabs()):
            if not self._confirm_close_tab(tab_id):
                return  # user cancelled
        # All confirmed — clean up state
        for tab_id in list(self._notebook_r.tabs()):
            closed_path = self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._clean_crcs.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._breadcrumbs.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            kh = self._key_handlers.pop(tab_id, None)
            if kh:
                kh.detach()
            mc = self._multi_cursors.pop(tab_id, None)
            if mc:
                mc.clear()
            _tmp = self._temp_files.pop(tab_id, None)
            if _tmp:
                try:
                    Path(_tmp).unlink(missing_ok=True)
                except Exception:
                    pass
            if closed_path and closed_path.endswith(".py"):
                for srv in self._each_lsp():
                    srv.close_file(closed_path)
        if self._split_shown:
            self._split_pane.forget(self._nb_frame_r)
        self._nb_frame_r.destroy()
        self._nb_frame_r = None
        self._notebook_r = None
        self._split_active = False
        self._split_shown = False
        self._split_was_shown = False
        self._set_active_pane("left")
        self._refresh_nav_bar()

    def _new_tab_in(
        self,
        notebook: CustomNotebook,
        title: str,
        content: str,
        filepath: str | None = None,
    ) -> None:
        """Like _new_tab but targets a specific notebook (used for right pane).

        Mirrors _new_tab's canvas-engine setup against the supplied
        notebook so the split-pane tab gets the same hook wiring
        (on_change, on_copy, breakpoint toggle, right-click hooks,
        LSP open, sidebar palette).
        """
        cv = CanvasCodeView(ttk.Frame(notebook))
        if self._editor_font:
            cv.set_font(*self._editor_font)
        frame = cv.master  # the Frame we just constructed
        cv.pack(fill="both", expand=True)
        cv.on_change = self._on_content_changed
        cv.on_bad_paste = self._show_encoding_pill
        if content:
            cv.set_text(content)
        cv.set_filepath(filepath)

        notebook.add(frame, text=f"  {title}  ")
        notebook.select(frame)

        tab_id = notebook.select()
        self._files[tab_id] = filepath
        self._titles[tab_id] = title
        self._dirty[tab_id] = False
        self._indent_sizes[tab_id] = 4
        self._codeviews[tab_id] = cv
        self._breadcrumbs[tab_id] = cv.breadcrumb
        self.after_idle(lambda tid=tab_id: self._reset_dirty_after_load(tid))

        pal = cv._palette
        self._sidebar.apply_theme(
            bg=pal["bg"],
            fg=pal["fg"],
            select_bg=pal.get("select_bg", "#264f78"),
            codeview=cv,
            kind=_theme_kind(self.theme_var.get()),
        )
        if not self.minimap_visible_var.get():
            cv.hide_minimap()

        if cv.language == "python":
            if filepath:
                for srv in self._each_lsp():
                    srv.open_file(filepath, content)

        cv.canvas.bind(
            "<Motion>",
            lambda e, _cv=cv, _tid=tab_id: self._on_hover_motion(
                e, _cv, self._files.get(_tid) or ""
            ),
            add="+",
        )
        cv.canvas.bind("<Leave>", lambda _: self._cancel_hover(), add="+")
        cv.canvas.bind("<FocusIn>", lambda _: self._set_active_pane("right"), add="+")

    def view_toggle_sidebar(self) -> None:
        """Show or hide the entire left sidebar (Ctrl+B)."""
        if self._sidebar_shown:
            self._h_pane.forget(self._sidebar)
            self._sidebar_shown = False
            self.sidebar_visible_var.set(False)
        else:
            # Tk PanedWindow has no insert — rebuild order in one synchronous
            # batch (all forget/add calls complete before Tk redraws, so no flash).
            self._h_pane.forget(self._v_pane)
            if self._ai_panel_visible:
                try:
                    self._h_pane.forget(self._ai_panel_frame)
                except Exception:
                    pass
            self._h_pane.add(self._sidebar, minsize=220, stretch="never")
            self._h_pane.add(self._v_pane, stretch="always")
            if self._ai_panel_visible:
                self._h_pane.add(self._ai_panel_frame, minsize=280, stretch="never")
                self.after(100, self._apply_ai_panel_sash)
            self._sidebar_shown = True
            self.sidebar_visible_var.set(True)
        self._refresh_nav_bar()

    def view_source_control(self) -> None:
        """Toggle the Source Control sidebar panel."""
        if self._sidebar._sc_visible:
            self._sidebar.hide_source_control()
        else:
            self._sidebar.show_source_control()
            self._refresh_sc_panel()

    # ── Run operations ────────────────────────────────────────────────────────

    def _is_anything_running(self) -> bool:
        """True while a debug session, output-panel run, or terminal run is active."""
        return (
            (self._debugger is not None)
            or getattr(self._output.output, "_is_running", False)
            or bool(self._running_file)
        )

    def _has_runnable_target(self) -> bool:
        """True when there is something the run button can actually execute."""
        return bool(self._run_entry_file) or (self._current_codeview is not None)

    def _refresh_run_buttons(self) -> None:
        """Sync ▶/⬡ action button icon+colour and ■ stop button with run state."""
        running = self._is_anything_running()
        no_target = not self._has_runnable_target()
        is_debug = (
            getattr(self, "_run_action_var", None)
            and self._run_action_var.get() == "debug"
        )

        run_btn = getattr(self, "_nav_run_btn", None)
        chevron_btn = getattr(self, "_nav_chevron_btn", None)
        stop_btn = getattr(self, "_nav_stop_btn", None)

        if run_btn:
            try:
                icon = " \u2b21 " if is_debug else " \u25b6 "
                color = (
                    "#555555"
                    if (running or no_target)
                    else ("#e5c07b" if is_debug else "#4ec94e")
                )
                run_btn.config(text=icon, fg=color)
            except Exception:
                pass
        if chevron_btn:
            try:
                chevron_btn.config(fg="#555555" if running else "#858585")
            except Exception:
                pass
        if stop_btn:
            try:
                stop_btn.config(fg="#f44747" if running else "#555555")
            except Exception:
                pass

    def _show_run_menu(self) -> None:
        """Post the run dropdown menu below the ▶▾ nav button pair."""
        if self._is_anything_running():
            return
        btn = self._nav_run_btn
        x = btn.winfo_rootx()
        y = btn.winfo_rooty() + btn.winfo_height()
        self._run_menu.tk_popup(x, y)

    def _nav_execute(self) -> None:
        """One-click execute using the mode selected in the run menu."""
        if not self._has_runnable_target():
            return
        if self._designer_mode and self._designer_dirty:
            self.designer_generate_code()

        if self._run_action_var.get() == "debug":
            self.debug_file()
        else:
            self._nav_run()

    def _nav_run(self) -> None:
        """Run the current file in the panel selected by _run_target_var."""
        if self._learning_tab:
            self.view_learning_mode()
        if self._run_target_var.get() == "terminal":
            self.run_file_in_terminal()
        else:
            self.run_file()

    def run_stop(self) -> None:
        """Stop the active debug session, output run, or terminal run (Shift+F5)."""
        if self._debugger:
            self._debug_stop()
        elif self._running_file:
            self._output.terminal.send_to_run_session("\x03")  # Ctrl+C
            self._set_running_file(None)
        else:
            self._output.terminate()

    def run_line(self) -> None:
        self._run_current_line()

    def run_selection(self) -> None:
        self._run_selection()

    def run_file(self) -> None:
        """Run the current file (or pinned entry) in the output panel."""
        saved = self.file_save()
        if not saved and not self._run_entry_file:
            return
        filepath = self._get_run_filepath()
        if filepath:
            if not self.output_visible_var.get():
                self.output_visible_var.set(True)
                self.view_toggle_output()
            self._set_running_file(filepath)
            self._output.run(filepath, self._active_python)

    def run_file_in_terminal(self) -> None:
        """Ctrl+F5 — save and run the current file (or pinned entry) in the terminal."""
        saved = self.file_save()
        if not saved and not self._run_entry_file:
            return
        filepath = self._get_run_filepath()
        if not filepath:
            return
        if not self.output_visible_var.get():
            self.output_visible_var.set(True)
            self.view_toggle_output()
        self._output._set_active("terminal")
        if not self._output.terminal._running:
            self._output.terminal._new_session(
                cwd=os.path.dirname(filepath) or os.getcwd()
            )
        self._set_running_file(filepath)
        term = self._output.terminal
        import platform as _pl

        prefix = "& " if _pl.system() == "Windows" else ""
        cmd = f'{prefix}"{self._active_python}" "{filepath}"\r'

        def _send_when_ready(retries: int = 40) -> None:
            if term.winfo_ismapped() and not term._resize_job:
                term.after(200, lambda: term.send_to_run_session(cmd))
            elif retries > 0:
                term.after(50, lambda: _send_when_ready(retries - 1))

        _send_when_ready()

    # ── Debugger ──────────────────────────────────────────────────────────────

    def _find_project_python(self, filepath: str) -> str:
        """Return the venv Python for *filepath*'s project tree, or sys.executable."""
        is_win = sys.platform == "win32"
        subpath = os.path.join(
            "Scripts" if is_win else "bin", "python.exe" if is_win else "python"
        )
        directory = os.path.dirname(os.path.abspath(filepath))
        while True:
            for name in (".venv", "venv", "env", ".env"):
                candidate = os.path.join(directory, name, subpath)
                if os.path.isfile(candidate):
                    return candidate
            parent = os.path.dirname(directory)
            if parent == directory:
                break
            directory = parent
        return sys.executable

    # ── Interpreter management ────────────────────────────────────────────────

    def _get_short_interp_label(self, label: str) -> str:
        """Extract 'Python X.Y.Z' from a full interpreter label string."""
        import re

        m = re.match(r"(Python\s+\S+)", label)
        return m.group(1) if m else label.split("(")[0].strip()

    def _init_interpreter(self) -> None:
        """Load saved interpreter from settings (or auto-detect) and show in statusbar."""
        from editor.project_manager import ProjectManager
        from utils import settings as _settings

        root = getattr(self, "_explorer_root", None) or os.path.expanduser("~")
        saved = _settings.get(f"interpreter:{root}")
        # Snapshot the current value — if session restore sets a different interpreter
        # before the background thread returns, don't override it.
        _snapshot = self._active_python

        def _on_pythons(results: list[tuple[str, str]]) -> None:
            if self._active_python != _snapshot:
                # session.restore (or wizard) already set a more authoritative
                # interpreter after we launched — leave it alone.
                return
            path, label = sys.executable, "Python"
            if saved:
                for lbl, exe in results:
                    if exe == saved and os.path.isfile(exe):
                        path, label = exe, self._get_short_interp_label(lbl)
                        break
            if not label or label == "Python":
                # Fall back to auto-detect via venv walk, then first result
                fp = next(iter(self._files.values()), None)
                detected = self._find_project_python(fp) if fp else sys.executable
                for lbl, exe in results:
                    if exe == detected:
                        path, label = exe, self._get_short_interp_label(lbl)
                        break
                else:
                    if results:
                        path, label = (
                            results[0][1],
                            self._get_short_interp_label(results[0][0]),
                        )
            self._active_python = path
            self._active_python_label = label
            self._statusbar.set_interpreter(label)

        ProjectManager(self._safe_after).discover_interpreters(_on_pythons)

    def _set_active_interpreter(self, path: str, label: str) -> None:
        """Update the active interpreter, refresh the statusbar, and persist the choice."""
        from utils import settings as _settings

        self._active_python = path
        self._active_python_label = label
        self._statusbar.set_interpreter(label)
        if hasattr(self._statusbar, "_interp_lbl") and not getattr(
            self._statusbar._interp_lbl, "_learning_registered", False
        ):
            LearningManager.register(
                self._statusbar._interp_lbl, "interpreter_selector"
            )
            self._statusbar._interp_lbl._learning_registered = True
        root = getattr(self, "_explorer_root", None) or os.path.expanduser("~")
        _settings.set(f"interpreter:{root}", path)
        if self._pkg_panel:
            self._pkg_panel.set_python(path)
        if hasattr(self, "_props_panel") and self._props_panel:
            self._props_panel.set_active_python(path)

    def _on_designer_install_pillow(self) -> None:
        pip = getattr(self._pkg_panel, "_pip", None)
        if pip is None:
            from editor.pip_manager import PipManager

            pip = PipManager(self._safe_after)
        pip.set_python(self._active_python)
        output = self._output.output
        try:
            self._output._set_active("output")
        except Exception:
            pass
        output.write("\n$ pip install pillow\n", tag="cmd")

        def _on_line(line):
            output.write(line)

        def _on_done():
            output.write("✓ Pillow installed.\n", tag="info")
            self._props_panel._pil_available = True
            self._props_panel._update_pil_warning_row("prop__image", True)
            self._add_to_requirements("Pillow")

        pip.run_operation(
            ["install", "pillow"],
            on_line=_on_line,
            on_done=_on_done,
            on_error=lambda e: output.write(e + "\n", tag="err"),
        )

    def _add_to_requirements(self, package: str) -> None:
        """Append *package* to the project's requirements.txt if not already listed."""
        import re as _re
        root = str(getattr(self._sidebar.explorer, "_root", "") or "")
        if not root:
            return
        req = Path(root) / "requirements.txt"
        if not req.is_file():
            return
        try:
            text = req.read_text(encoding="utf-8")
            existing = {
                _re.split(r"[=<>!~;\s]", ln.strip())[0].lower()
                for ln in text.splitlines()
                if ln.strip() and not ln.startswith("#")
            }
            if package.lower() in existing:
                return
            if text and not text.endswith("\n"):
                text += "\n"
            req.write_text(text + f"{package}\n", encoding="utf-8")
        except Exception:
            pass

    # ── Run entry file ────────────────────────────────────────────────────────

    def _get_run_filepath(self) -> str | None:
        """Return the pinned entry file path, or the current tab's file."""
        if self._run_entry_file and os.path.isfile(self._run_entry_file):
            return self._run_entry_file
        return self._files.get(self._current_tab_id)

    def _set_run_entry(self, path: str | None) -> None:
        self._run_entry_file = path or None
        self._running_file = None
        label = os.path.basename(path) if path else "Active Tab"
        self._statusbar.set_run_entry(label)
        if self._designer_mode:
            self._refresh_form_list()

    def _set_running_file(self, path: str | None) -> None:
        """Temporarily show a filename in the run-entry label while a run is active."""
        self._running_file = path
        if path:
            self._statusbar.set_run_entry(os.path.basename(path))
        else:
            label = (
                os.path.basename(self._run_entry_file)
                if self._run_entry_file
                else "Active Tab"
            )
            self._statusbar.set_run_entry(label)
        self._refresh_run_buttons()

    def _open_run_entry_picker(self) -> None:
        """Popup above the statusbar to pin a specific entry file for Run/Debug."""
        import tkinter as tk
        import glob as _glob

        if hasattr(self, "_run_entry_picker") and self._run_entry_picker.winfo_exists():
            self._run_entry_picker.destroy()
            return

        picker = tk.Toplevel(self)
        self._run_entry_picker = picker
        picker.overrideredirect(True)
        picker.configure(bg="#252526")

        tk.Label(
            picker,
            text="Select Entry File",
            bg="#252526",
            fg="#cccccc",
            font=(UI_FONT, 9, "bold"),
            pady=6,
            padx=10,
            anchor="w",
        ).pack(fill="x")
        ttk.Separator(picker, orient="horizontal").pack(fill="x")

        lb = tk.Listbox(
            picker,
            bg="#1e1e1e",
            fg="#cccccc",
            selectbackground="#094771",
            selectforeground="#ffffff",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            relief="flat",
            activestyle="none",
        )
        lb.pack(fill="both", expand=True, padx=1, pady=1)

        # Build file list: "Active Tab" + project .py files + Browse
        root = str(self._sidebar.explorer._root or os.getcwd())
        _SKIP = {
            "__pycache__",
            ".venv",
            "venv",
            "env",
            ".git",
            "node_modules",
            "dist",
            "build",
        }

        py_files: list[str] = []
        for pattern in ("*.py", "*/*.py"):
            for f in _glob.glob(os.path.join(root, pattern)):
                parts = Path(f).relative_to(root).parts
                if not any(p in _SKIP for p in parts):
                    py_files.append(f)
        py_files.sort(
            key=lambda f: (os.path.dirname(f) != root, os.path.basename(f).lower())
        )
        # Also include any open .py tabs that weren't caught by the glob
        # (e.g. files saved outside the project root)
        _py_norm = {os.path.normcase(os.path.normpath(f)) for f in py_files}
        open_py = [
            fp
            for fp in self._files.values()
            if fp
            and fp.endswith(".py")
            and os.path.normcase(os.path.normpath(fp)) not in _py_norm
        ]
        py_files.extend(sorted(open_py, key=lambda f: os.path.basename(f).lower()))

        entries: list[str | None] = [None] + py_files + ["__browse__"]

        def _display(entry) -> str:
            if entry is None:
                marker = "● " if not self._run_entry_file else "  "
                return f"{marker}Active Tab"
            if entry == "__browse__":
                return "  Browse..."
            marker = "● " if entry == self._run_entry_file else "  "
            try:
                rel = os.path.relpath(entry, root)
            except ValueError:
                rel = os.path.basename(entry)
            return f"{marker}{rel}"

        for e in entries:
            lb.insert("end", _display(e))

        # Select current
        for i, e in enumerate(entries):
            if e == self._run_entry_file:
                lb.selection_set(i)
                lb.see(i)
                break
        else:
            lb.selection_set(0)

        rows = min(len(entries), 12)
        lb.config(height=rows)

        def _reposition() -> None:
            ax, ay = self._statusbar.get_run_entry_anchor()
            pw = max(picker.winfo_reqwidth(), 340)
            ph = picker.winfo_reqheight()
            sw = self.winfo_screenwidth()
            x = min(ax, sw - pw - 4)
            y = ay - ph - 2
            picker.geometry(f"{pw}x{ph}+{x}+{y}")

        picker.update_idletasks()
        _reposition()

        def _select(event=None) -> None:
            sel = lb.curselection()
            if not sel:
                return
            entry = entries[sel[0]]
            picker.destroy()
            if entry == "__browse__":
                from tkinter.filedialog import askopenfilename

                path = askopenfilename(
                    title="Select Entry File",
                    filetypes=[("Python files", "*.py"), ("All files", "*.*")],
                    initialdir=root,
                )
                if path:
                    self._set_run_entry(path)
            else:
                self._set_run_entry(entry)

        lb.bind("<Double-Button-1>", _select)
        lb.bind("<Return>", _select)
        picker.bind("<Escape>", lambda _: picker.destroy())
        picker.bind("<FocusOut>", lambda _: picker.destroy())
        picker.focus_set()
        lb.focus_set()

    def _open_interpreter_picker(self) -> None:
        """Show a popup above the statusbar to select the active Python interpreter."""
        import tkinter as tk
        from editor.project_manager import ProjectManager

        # Toggle — click again to close
        if hasattr(self, "_interp_picker") and self._interp_picker.winfo_exists():
            self._interp_picker.destroy()
            return

        picker = tk.Toplevel(self)
        self._interp_picker = picker
        picker.overrideredirect(True)
        picker.configure(bg="#252526")

        # Header
        tk.Label(
            picker,
            text="Select Python Interpreter",
            bg="#252526",
            fg="#cccccc",
            font=(UI_FONT, 9, "bold"),
            pady=6,
            padx=10,
            anchor="w",
        ).pack(fill="x")
        ttk.Separator(picker, orient="horizontal").pack(fill="x")

        lb = tk.Listbox(
            picker,
            bg="#1e1e1e",
            fg="#cccccc",
            selectbackground="#094771",
            selectforeground="#ffffff",
            borderwidth=0,
            highlightthickness=0,
            font=("Consolas", 9),
            relief="flat",
            activestyle="none",
        )
        lb.pack(fill="both", expand=True, padx=1, pady=(1, 1))
        lb.insert("end", "  Detecting interpreters…")

        pythons: list[tuple[str, str]] = []

        def _on_pythons(results: list[tuple[str, str]]) -> None:
            nonlocal pythons
            pythons = results
            lb.delete(0, "end")
            for lbl, exe in results:
                prefix = "● " if exe == self._active_python else "  "
                lb.insert("end", f"{prefix}{lbl}")
            for i, (_, exe) in enumerate(results):
                if exe == self._active_python:
                    lb.selection_set(i)
                    lb.see(i)
                    break
            # Resize to content (cap at 10 rows)
            rows = min(len(results), 10)
            lb.config(height=rows)
            picker.update_idletasks()
            _reposition()

        def _reposition() -> None:
            ax, ay = self._statusbar.get_interp_anchor()
            pw = max(picker.winfo_reqwidth(), 420)
            ph = picker.winfo_reqheight()
            # Keep within screen bounds
            sw = self.winfo_screenwidth()
            x = min(ax, sw - pw - 4)
            y = ay - ph - 2
            picker.geometry(f"{pw}x{ph}+{x}+{y}")

        def _select(event=None) -> None:
            sel = lb.curselection()
            if not sel or not pythons:
                return
            idx = sel[0]
            if idx < len(pythons):
                lbl, exe = pythons[idx]
                self._set_active_interpreter(exe, self._get_short_interp_label(lbl))
            picker.destroy()

        lb.bind("<Return>", _select)
        lb.bind("<Double-Button-1>", _select)
        lb.bind("<Button-1>", lambda e: lb.after(10, _select))
        lb.bind("<Escape>", lambda _: picker.destroy())
        picker.bind(
            "<FocusOut>",
            lambda e: picker.after(
                100, lambda: picker.destroy() if picker.winfo_exists() else None
            ),
        )

        # Initial position before data loads
        ax, ay = self._statusbar.get_interp_anchor()
        picker.geometry(f"420x60+{ax}+{ay - 62}")
        picker.lift()
        lb.focus_set()

        ProjectManager(self._safe_after).discover_interpreters(_on_pythons)

    def _get_debugpy_site(self) -> str | None:
        """Return the site-packages dir containing IDOL's bundled debugpy, or None."""
        try:
            import importlib.util

            spec = importlib.util.find_spec("debugpy")
            if spec and spec.origin:
                return os.path.dirname(os.path.dirname(spec.origin))
        except Exception:
            pass
        return None

    def debug_file(self) -> None:
        """F5 — save and launch a debug session for the current file."""
        if self._learning_tab:
            self.view_learning_mode()
        if self._debugger and self._debugger.active:
            # Already paused — treat F5 as Continue
            self._debug_continue()
            return
        saved = self.file_save()
        if not saved and not self._run_entry_file:
            return
        filepath = self._get_run_filepath()
        if not filepath or not filepath.endswith(".py"):
            return

        python_exe = self._active_python
        debugpy_site = self._get_debugpy_site()

        self._set_running_file(filepath)
        self._debugger = DebugManager(after_fn=self._safe_after)
        self._debugger.on_stopped = self._on_debug_stopped
        self._debugger.on_continued = self._on_debug_continued
        self._debugger.on_terminated = self._on_debug_terminated
        self._debugger.on_output = self._on_debug_output

        # Collect breakpoints for all files
        bp_dict = {
            fp: sorted(lines) for fp, lines in self._breakpoints.items() if lines
        }

        if not self.output_visible_var.get():
            self.output_visible_var.set(True)
            self.view_toggle_output()

        if self._run_target_var.get() == "terminal":
            self._debug_in_terminal(filepath, python_exe, bp_dict, debugpy_site)
        else:
            self._output._set_active("debug")
            self._output.output.clear()
            self._output.output.write(
                f"$ Debugging {os.path.basename(filepath)}\n\n", "info"
            )
            self._debugger.launch(filepath, python_exe, bp_dict, debugpy_site)
            self._show_debug_bar()
            if self._file_uses_input(filepath):
                self._output.output.show_debug_input_guide_btn(
                    self._switch_to_terminal_debug
                )

    def _debug_in_terminal(
        self,
        filepath: str,
        python_exe: str,
        bp_dict: dict,
        debugpy_site: str | None = None,
    ) -> None:
        """Launch debugpy in the terminal and attach our DAP client to it."""
        from editor.debug_manager import _find_free_port

        port = _find_free_port()

        self._output._set_active("terminal")
        if not self._output.terminal._running:
            self._output.terminal._new_session(
                cwd=os.path.dirname(filepath) or os.getcwd()
            )

        import platform as _pl

        is_win = _pl.system() == "Windows"
        prefix = "& " if is_win else ""
        base = f'{prefix}"{python_exe}" -Xfrozen_modules=off -m debugpy --listen 127.0.0.1:{port} --wait-for-client "{filepath}"'
        if debugpy_site:
            if is_win:
                safe = debugpy_site.replace("'", "''")
                cmd = f"$env:PYTHONPATH='{safe}' + [IO.Path]::PathSeparator + $env:PYTHONPATH; {base}\r"
            else:
                cmd = f'PYTHONPATH="{debugpy_site}:$PYTHONPATH" {base}\r'
        else:
            cmd = base + "\r"

        # Poll until the terminal is mapped AND its resize debounce has settled.
        # On first show the widget gets real pixel dimensions, firing <Configure>
        # → _on_resize → setwinsize → SIGWINCH → shell repaint. Sending before
        # that repaint finishes wipes the output. On subsequent runs the widget
        # is already the right size so _resize_job is None and this fires immediately.
        term = self._output.terminal

        def _send_when_ready(retries: int = 40) -> None:
            if term.winfo_ismapped() and not term._resize_job:
                term.after(200, lambda: term.send_to_run_session(cmd))
            elif retries > 0:
                term.after(50, lambda: _send_when_ready(retries - 1))

        _send_when_ready()

        self._debugger.attach_to_port(port, filepath, bp_dict)
        self._show_debug_bar()

    def _show_debug_bar(self) -> None:
        self._debug_bar.pack(side="left", padx=(4, 0))
        self._refresh_nav_bar()
        self._refresh_run_buttons()

    def _hide_debug_bar(self) -> None:
        self._debug_bar.pack_forget()
        self._refresh_nav_bar()

    def _debug_continue(self) -> None:
        if self._debugger:
            self._debugger.continue_()

    def _debug_step_over(self) -> None:
        if self._debugger:
            self._debugger.next_()

    def _debug_step_in(self) -> None:
        if self._debugger:
            self._debugger.step_in()

    def _debug_step_out(self) -> None:
        if self._debugger:
            self._debugger.step_out()

    def _debug_stop(self) -> None:
        if self._debugger:
            in_terminal = self._run_target_var.get() == "terminal"
            self._debugger.disconnect()
            if in_terminal:
                self._output.terminal.send_text("\x03")
            self._on_debug_terminated()

    def _on_debug_stopped(
        self, frame_id: int, filepath: str, line: int, reason: str
    ) -> None:
        """Called when the debugger pauses (breakpoint hit, step complete, etc.)."""
        # Clear old highlight
        self._clear_debug_highlight()
        # Navigate to the paused location
        if filepath and line:
            self._open_file_at(filepath, line, 0)
            # Highlight the current line in the editor + gutter
            cv = self._current_codeview
            if cv:
                cv.set_debug_line(line)
                self._debug_current_tab = self._current_tab_id
        # Fetch locals and update debug panel
        self._output._set_active("debug")
        if frame_id:
            self._debugger.get_locals(
                frame_id,
                lambda variables: self._output.debug.update_locals(variables),
            )
        # Update breakpoints list
        self._refresh_debug_breakpoints()

    def _on_debug_continued(self) -> None:
        self._clear_debug_highlight()

    def _on_debug_terminated(self) -> None:
        self._clear_debug_highlight()
        self._output.debug.clear_session()
        self._hide_debug_bar()
        self._debugger = None
        self._debug_current_tab = None
        self._output.output.write("\nProcess finished.\n", "info")
        self._output.output.hide_debug_input_guide_btn()
        self._set_running_file(None)
        self._refresh_run_buttons()

    def _file_uses_input(self, filepath: str) -> bool:
        try:
            with open(filepath, encoding="utf-8", errors="ignore") as f:
                return "input(" in f.read()
        except OSError:
            return False

    def _switch_to_terminal_debug(self) -> None:
        self._debug_stop()
        self._run_target_var.set("terminal")
        self.after(150, self.debug_file)

    def _on_debug_output(self, category: str, text: str) -> None:
        tag = "stderr" if category == "stderr" else ""
        self._output.output.write(text, tag)

    def _clear_debug_highlight(self) -> None:
        """Remove current-line highlight and gutter arrow."""
        if self._debug_current_tab:
            cv = self._codeviews.get(self._debug_current_tab)
            if cv:
                cv.set_debug_line(None)

    def _on_breakpoint_toggle(self, filepath: str, lineno: int) -> None:
        """Toggle a breakpoint for *filepath*:*lineno* and sync panels."""
        if filepath not in self._breakpoints:
            self._breakpoints[filepath] = set()
        bp_set = self._breakpoints[filepath]
        if lineno in bp_set:
            bp_set.discard(lineno)
        else:
            bp_set.add(lineno)
        self._refresh_debug_breakpoints()
        # Live-update breakpoints in an active session
        if self._debugger and self._debugger.active:
            self._debugger._pending_breakpoints = {
                fp: sorted(lines) for fp, lines in self._breakpoints.items() if lines
            }

    def _refresh_debug_breakpoints(self) -> None:
        """Push the current breakpoint list to the debug panel."""
        from utils.session import TMP_DIR

        tmp_root = str(TMP_DIR)
        entries = []
        has_unsaved = False
        for fp, lines in self._breakpoints.items():
            if not lines:
                continue
            if fp.startswith(tmp_root):
                has_unsaved = True
            fname = os.path.basename(fp)
            for ln in sorted(lines):
                entries.append({"filepath": fp, "filename": fname, "line": ln})
        self._output.debug.update_breakpoints(entries)
        if has_unsaved:
            self._output.debug.show_unsaved_warning()
        else:
            self._output.debug.hide_unsaved_warning()

    def _run_snippet(self, code: str, label: str) -> None:
        """Send *code* to the output panel for execution."""
        if not code.strip():
            return
        if not self.output_visible_var.get():
            self.output_visible_var.set(True)
            self.view_toggle_output()
        self._output.run_code(code, label, self._active_python)

    def _run_current_line(self) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        line = _cv_cursor_line_text(cv).lstrip()
        self._run_snippet(line, "line")

    def _run_selection(self) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        code = _cv_selected_text(cv)
        if not code:
            return
        import textwrap

        self._run_snippet(textwrap.dedent(code), "selection")

    def run_clear(self) -> None:
        self._output.clear()

    # ── Command palette ───────────────────────────────────────────────────────

    def open_command_palette(self) -> None:
        commands = [
            # File
            ("New File", "Ctrl+N", self.file_new),
            ("Open File...", "Ctrl+O", self.file_open),
            ("Save", "Ctrl+S", self.file_save),
            ("Save As...", "Ctrl+Shift+S", self.file_save_as),
            ("Close Tab", "Ctrl+W", self.file_close),
            ("New Project...", "", self.file_new_project),
            ("Open Project...", "", self.workspace_open),
            ("Save Project", "", self.workspace_save),
            ("Close Project", "", self.workspace_close),
            ("Exit", "Ctrl+Q", self.file_exit),
            # Edit
            ("Undo", "Ctrl+Z", self.edit_undo),
            ("Redo", "Ctrl+Y", self.edit_redo),
            ("Cut", "Ctrl+X", self.edit_cut),
            ("Copy", "Ctrl+C", self.edit_copy),
            ("Paste", "Ctrl+V", self.edit_paste),
            ("Select All", "Ctrl+A", self.edit_select_all),
            ("Find & Replace", "Ctrl+F", self.edit_find_replace),
            # View
            ("Change Font...", "Ctrl+L", self.view_change_font),
            ("Toggle Highlight Active Line", "", self.view_toggle_highlight),
            ("Active Line Color...", "", self.view_active_line_color),
            ("Show/Hide Output Panel", "", self.view_toggle_output),
            ("New Terminal", "Ctrl+`", self.view_new_terminal),
            ("Show/Hide Minimap", "", self.view_toggle_minimap),
            ("Split Editor", "Ctrl+\\", self.view_split_editor),
            ("Source Control", "Ctrl+Shift+G", self.view_source_control),
            # Themes
            *[
                (
                    f"Theme: {t}",
                    "",
                    lambda t=t: (self.theme_var.set(t), self.view_change_theme()),
                )
                for t in [
                    "ayu-dark",
                    "ayu-light",
                    "dracula",
                    "mariana",
                    "material",
                    "monokai",
                    "rrt",
                ]
            ],
            # Designer
            ("Generate Code", "Ctrl+Shift+G", self.designer_generate_code),
            # Editor
            ("Fold All", "", self.view_fold_all),
            ("Unfold All", "", self.view_unfold_all),
            # Run
            ("Debug", "F5", self.debug_file),
            ("Run", "Ctrl+F5", self._nav_run),
            ("Run Line", "", self.run_line),
            ("Run Selection", "", self.run_selection),
            ("Stop", "Shift+F5", self.run_stop),
            ("Clear Output", "", self.run_clear),
            # Help
            ("About", "", self.help_about),
        ]
        from widgets.package_manager import _BUILTIN_LOOKUP

        CommandPalette(
            self,
            commands,
            symbol_fn=self._outline.get_symbols,
            navigate_fn=self._outline_navigate,
            run_pip_fn=self._palette_run_pip,
            installed_fn=lambda: self._pkg_panel._installed if self._pkg_panel else {},
            pkg_lookup=_BUILTIN_LOOKUP,
        )

    def _palette_run_pip(self, args: list[str]) -> None:
        """Run a pip command from the command palette, streaming to the Output panel."""
        import subprocess, threading as _threading

        output = self._output.output
        try:
            output.master._set_active("output")
        except Exception:
            pass
        output.write(f"\n$ pip {' '.join(args)}\n", tag="cmd")

        def _run():
            try:
                proc = subprocess.Popen(
                    [self._active_python, "-m", "pip"] + args,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    self.after(0, lambda l=line: output.write(l))
                proc.wait()
                # Refresh pkg panel installed list if it's open
                if self._pkg_panel:
                    self.after(0, self._pkg_panel._load_installed)
            except Exception as e:
                self.after(0, lambda: output.write(str(e) + "\n", tag="err"))

        _threading.Thread(target=_run, daemon=True).start()

    # ── Help ─────────────────────────────────────────────────────────────────

    def help_about(self) -> None:
        from pathlib import Path as _Path

        dlg = tk.Toplevel(self)
        dlg.title("About IDOL")
        dlg.resizable(False, False)
        dlg.configure(bg="#0d1117")
        dlg.attributes("-topmost", True)

        # Logo
        logo_path = _Path(__file__).parent / "images" / "IDOL.png"
        try:
            from PIL import Image, ImageTk

            img = Image.open(logo_path)
            ratio = 420 / img.width
            img = img.resize((420, int(img.height * ratio)), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            dlg._photo = photo
            tk.Label(dlg, image=photo, bg="#0d1117", bd=0).pack(pady=(0, 8))
        except Exception:
            tk.Label(
                dlg,
                text="IDOL",
                bg="#0d1117",
                fg="#cccccc",
                font=(UI_FONT, 28, "bold"),
            ).pack(pady=(24, 8))

        # Info
        tk.Label(
            dlg,
            text="Integrated Development and Objective Learning",
            bg="#0d1117",
            fg="#858585",
            font=(UI_FONT, 9),
        ).pack()

        tk.Label(
            dlg,
            text="Alex Fero & Claude Sonnet",
            bg="#0d1117",
            fg="#858585",
            font=(UI_FONT, 8),
        ).pack(pady=(10, 4))

        tk.Frame(dlg, bg="#2a2a2a", height=1).pack(fill="x", padx=32)

        import platform as _platform

        try:
            from importlib.metadata import version as _pkg_ver

            pip_ver = _pkg_ver("pip")
        except Exception:
            pip_ver = "unknown"
        _sys = _platform.system()
        if _sys == "Windows":
            os_str = f"Windows {_platform.release()}"
        elif _sys == "Darwin":
            os_str = f"macOS {_platform.mac_ver()[0]}"
        else:
            os_str = f"{_sys} {_platform.release()}"

        tk.Label(
            dlg,
            text=f"Python {sys.version.split()[0]}   •   pip {pip_ver}   •   {os_str}",
            bg="#0d1117",
            fg="#555555",
            font=(UI_FONT, 8),
        ).pack(pady=(4, 10))

        # Close button
        btn = tk.Label(
            dlg,
            text="Close",
            bg="#0e639c",
            fg="white",
            font=(UI_FONT, 9),
            cursor="hand2",
            padx=20,
            pady=5,
        )
        btn.pack(pady=(10, 20))
        btn.bind("<Button-1>", lambda _: dlg.destroy())
        btn.bind("<Enter>", lambda _: btn.config(bg="#1177bb"))
        btn.bind("<Leave>", lambda _: btn.config(bg="#0e639c"))

        # Center over main window
        dlg.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dlg.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dlg.winfo_height()) // 2
        dlg.geometry(f"+{x}+{y}")
