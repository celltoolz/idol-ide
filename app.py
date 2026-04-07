from __future__ import annotations

import builtins
import os
import re
from tkinter import BooleanVar, Button, StringVar, Tk, ttk
from tkinter.filedialog import askopenfilename, asksaveasfilename
from tkinter.messagebox import showinfo, showerror, askyesnocancel, askyesno

import pygments.lexers
import pygments.util
from tkfontchooser import askfont
from tkcolorpicker import askcolor
 
from widgets.codeview import CodeView
from widgets.notebook import CustomNotebook
from widgets.sidebar import Sidebar
from widgets.bottom_panel import BottomPanel
from widgets.find_replace import FindReplaceBar
from widgets.statusbar import StatusBar
from widgets.command_palette import CommandPalette
from editor.bracket_matcher import BracketMatcher
from editor.key_handler import KeyHandler
from editor.multi_cursor import MultiCursor
from editor.completion import CompletionPopup
from editor.lsp_manager import (
    LspManager,
    detect_server,
    uri_to_path,
    SEV_ERROR,
    SEV_WARNING,
)
from editor.git_manager import GitManager
from menus.menubar import build_menubar
from utils import session as session_utils

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


class Notepad(Tk):
    def __init__(self, initial_file: str | None = None) -> None:
        super().__init__()
        self.title("Notepad")
        self.geometry("1280x800")

        # Per-tab state  {tab_id -> value}
        self._files: dict[str, str | None] = {}
        self._titles: dict[str, str] = {}
        self._dirty: dict[str, bool] = {}
        self._indent_sizes: dict[str, int] = {}
        self._codeviews: dict[str, CodeView] = {}
        self._key_handlers: dict[str, KeyHandler] = {}
        self._multi_cursors: dict[str, MultiCursor] = {}

        self._bracket_matcher = BracketMatcher()
        self._find_replace: FindReplaceBar | None = None

        # LSP
        self._lsp: LspManager | None = None
        self._lsp_diagnostics: dict[str, list] = {}  # uri → diag list
        self._hover_after_id: str | None = None
        self._hover_popup = None
        self._lsp_change_after_id: str | None = None

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

        # Split editor
        self._split_active: bool = False
        self._active_pane: str = "left"  # "left" | "right"
        self._notebook_r: CustomNotebook | None = None
        self._nb_frame_r = None
        self._scroll_locked: bool = False
        self._lock_btn = None
        self._syncing_scroll: bool = False

        # Settings
        self.theme_var = StringVar(value="monokai")
        self.highlight_line_var = BooleanVar(value=True)
        self.output_visible_var = BooleanVar(value=True)
        self.minimap_visible_var = BooleanVar(value=True)
        self._active_line_color: str | None = None

        self._build_layout()
        build_menubar(self)
        self._bind_shortcuts()
        self._start_highlight_loop()

        if initial_file and os.path.isfile(initial_file):
            self._open_file(initial_file)
        elif not session_utils.restore(self):
            self._new_tab("Untitled", "")
            self._sidebar.explorer.set_root(os.getcwd())

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_layout(self) -> None:
        # Status bar at the very bottom
        self._statusbar = StatusBar(self, on_indent_change=self._on_indent_change)
        self._statusbar.pack(side="bottom", fill="x")

        # Horizontal split: outline (left) | editor+output (right)
        self._h_pane = ttk.PanedWindow(self, orient="horizontal")
        self._h_pane.pack(fill="both", expand=True)

        # Left panel – sidebar (outline + source control + explorer)
        self._sidebar = Sidebar(
            self._h_pane,
            on_file_open=self._open_file,
            on_navigate=self._outline_navigate,
            sc_callbacks={
                "stage":             self._sc_stage,
                "unstage":           self._sc_unstage,
                "discard":           self._sc_discard,
                "commit":            self._sc_commit,
                "push":              self._sc_push,
                "pull":              self._sc_pull,
                "diff":              self._sc_open_diff,
                "create_gitignore":  self._sc_create_gitignore,
                "gitignore_check":   self._sc_gitignore_exists,
                "repo_root":         lambda: self._git._root if self._git else "",
            },
        )
        self._sidebar.configure(width=220)
        self._h_pane.add(self._sidebar, weight=0)
        self._outline = self._sidebar.outline  # keep existing references working

        # Right panel – vertical split: notebook (top) | output (bottom)
        self._v_pane = ttk.PanedWindow(self._h_pane, orient="vertical")
        self._h_pane.add(self._v_pane, weight=1)

        # Horizontal split pane — holds left notebook (always) + right notebook (when split)
        self._split_pane = ttk.PanedWindow(self._v_pane, orient="horizontal")
        self._v_pane.add(self._split_pane, weight=3)

        # Left notebook frame (primary)
        nb_frame = ttk.Frame(self._split_pane)
        self._split_pane.add(nb_frame, weight=1)
        self._nb_frame_l = nb_frame

        self.notebook = CustomNotebook(
            nb_frame, on_close=self._close_tab, on_split=self._open_in_split
        )
        self.notebook._split_open_ref = lambda: self._split_active
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add=True)
        self.notebook.bind(
            "<ButtonPress-1>", lambda _: self._set_active_pane("left"), add=True
        )

        # Inline find/replace bar (lives inside nb_frame, hidden by default)
        self._find_replace = FindReplaceBar(nb_frame)

        _btn_kw = dict(
            font=("Segoe UI", 11, "bold"),
            bg="#2d2d30",
            activebackground="#2d2d30",
            cursor="hand2",
            padx=4,
            pady=0,
            relief="flat",
            bd=0,
            highlightthickness=1,
            highlightbackground="#454545",
        )

        self._prev_btn = Button(
            nb_frame,
            text=" ‹ ",
            fg="#858585",
            activeforeground="#cccccc",
            command=self.notebook.select_prev,
            **_btn_kw,
        )
        self._prev_btn.bind(
            "<Enter>",
            lambda _: self._prev_btn.config(
                fg="#cccccc", highlightbackground="#666666"
            ),
        )
        self._prev_btn.bind(
            "<Leave>",
            lambda _: self._prev_btn.config(
                fg="#858585", highlightbackground="#454545"
            ),
        )

        self._next_btn = Button(
            nb_frame,
            text=" › ",
            fg="#858585",
            activeforeground="#cccccc",
            command=self.notebook.select_next,
            **_btn_kw,
        )
        self._next_btn.bind(
            "<Enter>",
            lambda _: self._next_btn.config(
                fg="#cccccc", highlightbackground="#666666"
            ),
        )
        self._next_btn.bind(
            "<Leave>",
            lambda _: self._next_btn.config(
                fg="#858585", highlightbackground="#454545"
            ),
        )

        self._plus_btn = Button(
            nb_frame,
            text=" + ",
            fg="#858585",
            activeforeground="#2ea043",
            command=self.file_new,
            **_btn_kw,
        )
        self._plus_btn.bind(
            "<Enter>",
            lambda _: self._plus_btn.config(
                fg="#2ea043", highlightbackground="#2ea043"
            ),
        )
        self._plus_btn.bind(
            "<Leave>",
            lambda _: self._plus_btn.config(
                fg="#858585", highlightbackground="#454545"
            ),
        )

        self._output = BottomPanel(self._v_pane, run_callback=self.run_file)
        self._v_pane.add(self._output, weight=1)

        # Snap the sash once the window is actually visible on screen
        self.bind("<Map>", self._init_sash_pos)
        # Start LSP and Git after the UI is fully mapped
        self.after(500, self._start_lsp)
        self.after(700, self._start_git)
        # Re-position <> + buttons and completion popup whenever the window is moved/resized
        self.bind("<Configure>", self._on_window_configure)

    def _init_sash_pos(self, _=None) -> None:
        """Set the output panel to a small strip on first launch."""
        self.unbind("<Map>")  # only run once
        self.update_idletasks()
        total = self._v_pane.winfo_height()
        if total > 200:
            self._v_pane.sashpos(0, total - 160)
        self._place_plus_btn()

    def _on_window_configure(self, _=None) -> None:
        self.after(10, self._place_plus_btn)
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

    def _place_plus_btn(self) -> None:
        """Position the ‹ › + buttons directly above the vertical scrollbar."""
        nb = self.notebook  # buttons always live in the left notebook frame
        left_cv_id = nb.select() if nb.tabs() else None
        left_cv = self._codeviews.get(left_cv_id) if left_cv_id else None
        if left_cv is None:
            return
        vs = left_cv._vs
        vs.update_idletasks()
        vs_x = vs.winfo_x() + left_cv._frame.winfo_x() + nb.winfo_x()
        vs_w = vs.winfo_width()
        tab_h = nb.winfo_height() - left_cv._frame.winfo_height()
        btn_h = max(tab_h - 6, 16)

        # Account for minimap + border widths so buttons sit left of them
        mm = left_cv._minimap
        mm_w = (
            (mm.winfo_width() + mm._border.winfo_width()) if mm.winfo_ismapped() else 0
        )
        right_x = vs_x + vs_w + mm_w  # right edge of the minimap column

        # Place ‹ › + side by side, each the same width as the scrollbar
        self._prev_btn.place(
            x=right_x - vs_w * 3, y=3, width=vs_w, height=btn_h, anchor="nw"
        )
        self._next_btn.place(
            x=right_x - vs_w * 2, y=3, width=vs_w, height=btn_h, anchor="nw"
        )
        self._plus_btn.place(
            x=right_x - vs_w, y=3, width=vs_w, height=btn_h, anchor="nw"
        )

        # Keep find/replace bar above the buttons at all times
        if self._find_replace:
            self._find_replace.lift()

        # Reserve tab bar margin so tabs never slide under the buttons
        btn_area = vs_w * 3 + 6
        if getattr(self, "_last_btn_area", None) != btn_area:
            self._last_btn_area = btn_area
            ttk.Style().configure(
                "CustomNotebook", tabmargins=[2, 5, btn_area + mm_w, 0]
            )

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda _: self.file_new())
        self.bind("<Control-o>", lambda _: self.file_open())
        self.bind("<Control-s>", lambda _: self.file_save())
        self.bind("<Control-S>", lambda _: self.file_save_as())
        self.bind("<Control-w>", lambda _: self.file_close())
        self.bind("<Control-q>", lambda _: self.file_exit())
        self.bind("<Control-f>", lambda _: self.edit_find_replace())
        self.bind("<Control-l>", lambda _: self.view_change_font())
        self.bind("<F5>", lambda _: self.run_file())
        self.bind("<Control-grave>", lambda _: self.view_new_terminal())
        self.bind("<Control-G>", lambda _: self.view_source_control())
        self.bind("<Control-backslash>", lambda _: self.view_split_editor())
        self.bind("<Control-P>", lambda _: self.open_command_palette())

    # ── Tab helpers ───────────────────────────────────────────────────────────

    @property
    def _active_notebook(self) -> CustomNotebook:
        if self._split_active and self._active_pane == "right" and self._notebook_r:
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
    def _current_codeview(self) -> CodeView | None:
        tab_id = self._current_tab_id
        return self._codeviews.get(tab_id) if tab_id else None

    def _new_tab(self, title: str, content: str, filepath: str | None = None) -> None:
        # Pick lexer from filename; default to Python for new untitled tabs
        lexer = pygments.lexers.PythonLexer()
        if filepath:
            try:
                lexer = pygments.lexers.get_lexer_for_filename(filepath)
            except pygments.util.ClassNotFound:
                pass

        frame = ttk.Frame(self.notebook)
        codeview = CodeView(
            frame,
            lexer=lexer,
            color_scheme=self.theme_var.get(),
            tab_width=4,
            autohide_scrollbar=False,
            default_context_menu=True,
            undo=True,
            maxundo=-1,
        )
        codeview.pack(fill="both", expand=True)
        codeview.insert("1.0", content)
        codeview.edit_reset()  # clear undo history after initial load

        self.notebook.add(frame, text=f"  {title}  ")
        self.notebook.select(frame)

        tab_id = self.notebook.select()
        self._files[tab_id] = filepath
        self._titles[tab_id] = title
        self._dirty[tab_id] = False
        self._indent_sizes[tab_id] = 4
        self._codeviews[tab_id] = codeview

        is_code = not isinstance(lexer, (pygments.lexers.TextLexer,))
        handler = KeyHandler(tab_size=4, smart_pairs=is_code)
        mc = MultiCursor(codeview, tab_size=4)
        self._key_handlers[tab_id] = handler
        self._multi_cursors[tab_id] = mc
        self._setup_codeview(codeview, handler, mc)
        self._sidebar.apply_theme(
            bg=codeview.cget("bg"),
            fg=codeview.cget("fg"),
            select_bg=codeview.cget("selectbackground"),
            codeview=codeview,
        )

        if not self.minimap_visible_var.get():
            codeview.hide_minimap()

        self._update_title()
        if isinstance(
            lexer, (pygments.lexers.PythonLexer, pygments.lexers.Python3Lexer)
        ):
            self._outline.schedule_refresh(content)
            if filepath and self._lsp:
                self._lsp.open_file(filepath, content)
        else:
            self._outline.clear()

    def _setup_codeview(
        self, codeview: CodeView, handler: KeyHandler, mc: MultiCursor
    ) -> None:
        # Grab the active-line colour from the theme
        if self._active_line_color is None:
            self._active_line_color = codeview.cget("inactiveselectbackground")

        codeview.tag_configure("active_line", background=self._active_line_color)
        codeview.tag_configure(
            "matching_paren",
            background=codeview.tag_cget("sel", "background"),
            foreground=codeview.tag_cget("sel", "foreground"),
        )
        codeview.tag_lower("active_line")
        codeview.tag_raise("sel")

        def _on_key(e):
            # Completion popup navigation takes priority
            if self._completion.visible:
                if e.keysym == "Down":
                    self._completion.select_next()
                    return "break"
                if e.keysym == "Up":
                    self._completion.select_prev()
                    return "break"
                if e.keysym in ("Return", "Tab"):
                    self._accept_completion(codeview)
                    return "break"
                if e.keysym == "Escape":
                    self._completion.hide()
                    return "break"

            prev_ovr = handler.overwrite
            result = handler.handle(e, codeview)
            if mc.active:
                mc.apply_key(e)
            # Insert key toggled — update status bar and cursor shape
            if handler.overwrite != prev_ovr:
                self._statusbar.set_overwrite(handler.overwrite)
                codeview.config(
                    blockcursor=handler.overwrite,
                    insertwidth=0 if handler.overwrite else 2,
                )

            # Decide whether to (re-)trigger, narrow, or hide completion
            ch = e.char
            sym = e.keysym
            if ch and (ch.isalnum() or ch in ("_", ".")):
                self._schedule_completion(codeview)
            elif sym == "BackSpace":
                self._schedule_completion(codeview)
            elif sym not in (
                "Shift_L",
                "Shift_R",
                "Control_L",
                "Control_R",
                "Alt_L",
                "Alt_R",
                "Meta_L",
                "Meta_R",
                "Left",
                "Right",
            ):
                self._completion.hide()

            return result

        codeview.bind("<Key>", _on_key)
        codeview.bind("<KeyRelease>", self._bracket_matcher.match)
        codeview.bind("<ButtonRelease-1>", self._on_click_release)
        codeview.bind("<ButtonPress-3>", self._on_editor_right_click)
        codeview.bind("<<ContentChanged>>", lambda _: self._on_content_changed())

        # Alt+Click — add a secondary cursor; returns "break" so plain-click
        # handler below doesn't also fire and clear the new cursor.
        codeview.bind(
            "<Alt-ButtonPress-1>",
            lambda e, m=mc: (
                m.add(f"@{e.x},{e.y}"),
                self._update_cursor_status(),
                "break",
            )[2],
        )

        # Plain click — clear secondary cursors, dismiss completion, activate pane
        def _on_click(_, m=mc, cv=codeview):
            self._completion.hide()
            if m.active:
                m.clear()
                self._update_cursor_status()
            # Determine which pane this codeview belongs to and activate it
            pane = (
                "right"
                if (
                    self._notebook_r
                    and any(
                        self._codeviews.get(tid) is cv
                        for tid in self._notebook_r.tabs()
                    )
                )
                else "left"
            )
            self._set_active_pane(pane)

        codeview.bind("<ButtonPress-1>", _on_click)
        # Escape — also clears secondary cursors
        codeview.bind(
            "<Escape>",
            lambda _, m=mc: (
                (m.clear(), self._update_cursor_status()) if m.active else None
            ),
        )

        # LSP — diagnostics tags + hover + go-to-definition
        self._setup_lsp_tags(codeview)
        codeview.bind(
            "<Motion>",
            lambda e, cv=codeview: self._on_hover_motion(
                e, cv, self._files.get(self._current_tab_id, "")
            ),
        )
        codeview.bind("<Leave>", lambda _: self._cancel_hover())
        codeview.bind("<F12>", lambda _: self._goto_definition())

        codeview.mark_set("insert", "1.0")
        codeview.focus_set()

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
        if not self._confirm_close_tab(tab_id):
            return
        closed_path = self._files.pop(tab_id, None)
        self._titles.pop(tab_id, None)
        self._dirty.pop(tab_id, None)
        self._indent_sizes.pop(tab_id, None)
        self._codeviews.pop(tab_id, None)
        self._key_handlers.pop(tab_id, None)
        mc = self._multi_cursors.pop(tab_id, None)
        if mc:
            mc.clear()
        if closed_path and closed_path.endswith(".py") and self._lsp:
            self._lsp.close_file(closed_path)
        nb.forget(index)
        if nb is self._notebook_r and not nb.tabs():
            self._close_split()
        elif nb is self.notebook and not nb.tabs():
            self._new_tab("Untitled", "")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_tab_changed(self, *_) -> None:
        tab_id = self._current_tab_id
        if tab_id is None:
            return
        self._update_title()
        self._statusbar.set_indent(self._indent_sizes.get(tab_id, 4))
        # Reflect overwrite state of the new tab's handler
        handler = self._key_handlers.get(tab_id)
        ovr = handler.overwrite if handler else False
        self._statusbar.set_overwrite(ovr)
        cv = self._codeviews.get(tab_id)
        if cv:
            self._update_status_lexer(cv)
            if isinstance(
                cv._lexer, (pygments.lexers.PythonLexer, pygments.lexers.Python3Lexer)
            ):
                self._outline.schedule_refresh(cv.get("1.0", "end-1c"))
            else:
                self._outline.clear()
            self.after(50, self._place_plus_btn)
            # Apply cached git hunks for this tab; fetch fresh ones
            cv._line_numbers.set_git_hunks(self._git_hunks.get(tab_id, []))
            self._refresh_git_hunks()
            # Sync cursor shape to this tab's overwrite state
            cv.config(
                blockcursor=ovr,
                insertwidth=0 if ovr else 2,
            )

    def _on_content_changed(self) -> None:
        tab_id = self._current_tab_id
        if tab_id and not self._dirty.get(tab_id):
            self._dirty[tab_id] = True
            self._refresh_tab_title(tab_id)
        cv = self._current_codeview
        if cv and isinstance(
            cv._lexer, (pygments.lexers.PythonLexer, pygments.lexers.Python3Lexer)
        ):
            text = cv.get("1.0", "end-1c")
            self._outline.schedule_refresh(text)
            # LSP: debounced change notification
            path = self._files.get(tab_id)
            if path and self._lsp:
                if self._lsp_change_after_id:
                    self.after_cancel(self._lsp_change_after_id)
                self._lsp_change_after_id = self.after(
                    300,
                    lambda p=path, t=text: (
                        self._lsp.change_file(p, t) if self._lsp else None
                    ),
                )

    def _on_click_release(self, event) -> None:
        self._bracket_matcher.match(event)
        cv = self._current_codeview
        if cv is None:
            return
        cv.tag_remove("matching_word", "1.0", "end")

        word = cv.get("insert wordstart", "insert wordend").strip()
        if word and word not in _SKIP_HIGHLIGHT and not word[0].isdigit():
            pattern = re.compile(r"\b" + re.escape(word) + r"\b")
            for m in pattern.finditer(cv.get("1.0", "end-1c")):
                s = f"1.0 + {m.start()} chars"
                e = f"1.0 + {m.end()} chars"
                cv.tag_add("matching_word", s, e)
            cv.tag_configure("matching_word", background="#3d3f4a")
            cv.tag_raise("sel", "matching_word")

    def _on_editor_right_click(self, event) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        # Move insert cursor to click position
        cv.mark_set("insert", f"@{event.x},{event.y}")
        word = cv.get("insert wordstart", "insert wordend").strip()

        if not hasattr(self, "_editor_menu"):
            from tkinter import Menu

            self._editor_menu = Menu(self, tearoff=0)
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

        # Enable/disable word-sensitive items based on whether there's a word
        has_word = bool(word and word not in _SKIP_HIGHLIGHT and not word[0].isdigit())
        self._editor_menu.entryconfigure(
            "Go to Definition", state="normal" if has_word and self._lsp else "disabled"
        )
        self._editor_menu.entryconfigure(
            "Find References", state="normal" if has_word else "disabled"
        )
        self._editor_menu.tk_popup(event.x_root, event.y_root)

    def _find_references(self) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        word = cv.get("insert wordstart", "insert wordend").strip()
        if word:
            self._sidebar.show_references(word, cv)

    def _outline_navigate(self, lineno: int) -> None:
        cv = self._current_codeview
        if cv:
            cv.see(f"{lineno}.0")
            cv.mark_set("insert", f"{lineno}.0")
            cv.focus_set()

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
        self.title(f"{label} – Notepad")

    def _update_status_lexer(self, cv: CodeView) -> None:
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
            cv.configure(tabs=Font(font=cv.cget("font")).measure(" " * size))
        if handler:
            handler.tab_size = size
        self._indent_sizes[tab_id] = size

    # ── LSP ───────────────────────────────────────────────────────────────────

    def _start_lsp(self) -> None:
        cmd = detect_server()
        if not cmd:
            return
        root = self._sidebar.explorer._root or os.getcwd()
        self._lsp = LspManager(root, after_fn=self.after)
        self._lsp.on_diagnostics = self._on_lsp_diagnostics
        self._lsp.start(cmd)
        # Notify LSP of any already-open Python files
        self.after(800, self._lsp_open_all_tabs)

    def _lsp_open_all_tabs(self) -> None:
        for tab_id, cv in self._codeviews.items():
            if cv is None:
                continue
            path = self._files.get(tab_id)
            if path and path.endswith(".py"):
                self._lsp.open_file(path, cv.get("1.0", "end-1c"))

    def _setup_lsp_tags(self, codeview: CodeView) -> None:
        """Configure diagnostic highlight tags on a new codeview."""
        codeview.tag_configure("lsp_error", background="#3d0000", underline=True)
        codeview.tag_configure("lsp_warning", background="#2e2a00", underline=True)
        codeview.tag_configure("lsp_info", background="#002040")

    def _on_lsp_diagnostics(self, uri: str, diags: list) -> None:
        """Called by LspManager when diagnostics arrive for a file."""
        self._lsp_diagnostics[uri] = diags
        # Find the codeview for this URI
        norm_path = uri_to_path(uri).replace("/", os.sep).replace("\\", os.sep)
        for tab_id, path in self._files.items():
            if path and os.path.normcase(path) == os.path.normcase(norm_path):
                cv = self._codeviews.get(tab_id)
                if cv:
                    self._apply_diagnostics(cv, diags)
                break

    def _apply_diagnostics(self, codeview: CodeView, diags: list) -> None:
        """Paint diagnostic underlines onto *codeview*."""
        for tag in ("lsp_error", "lsp_warning", "lsp_info"):
            codeview.tag_remove(tag, "1.0", "end")

        for d in diags:
            sev = d.get("severity", SEV_WARNING)
            tag = (
                "lsp_error"
                if sev == SEV_ERROR
                else "lsp_warning"
                if sev == SEV_WARNING
                else "lsp_info"
            )
            start = d["range"]["start"]
            end = d["range"]["end"]
            s_idx = f"{start['line'] + 1}.{start['character']}"
            e_idx = f"{end['line'] + 1}.{end['character']}"
            codeview.tag_add(tag, s_idx, e_idx)
        for tag in ("lsp_info", "lsp_warning", "lsp_error"):
            codeview.tag_raise(tag)

    # ── LSP hover popup ───────────────────────────────────────────────────────

    def _on_hover_motion(self, event, cv: CodeView, path: str) -> None:
        """Debounce mouse motion; trigger hover request after 600 ms of stillness."""
        if self._completion.visible:
            return  # don't hover while the completion popup is open
        if self._hover_after_id:
            self.after_cancel(self._hover_after_id)
        self._dismiss_hover()
        self._hover_after_id = self.after(
            600, lambda: self._do_hover(event.x, event.y, cv, path)
        )

    def _do_hover(self, mx: int, my: int, cv: CodeView, path: str) -> None:
        if not self._lsp or not path:
            return
        idx = cv.index(f"@{mx},{my}")
        line, col = idx.split(".")
        self._lsp.hover(
            path,
            int(line) - 1,
            int(col),
            lambda result: self._show_hover(result, cv, mx, my),
        )

    def _show_hover(self, result, cv: CodeView, mx: int, my: int) -> None:
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
            self, text, cv.winfo_rootx() + mx, cv.winfo_rooty() + my
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
        self._git = GitManager(root, after_fn=self.after)
        if not self._git.is_repo():
            self._git = None
            return
        self._refresh_git()

    def _refresh_git(self) -> None:
        if not self._git:
            return
        self._git.get_branch(self._on_git_branch)
        self._git.get_status(self._on_git_status)
        # Poll every 30 s to catch external git operations
        self.after(30_000, self._refresh_git)

    def _on_git_branch(self, branch: str) -> None:
        self._statusbar.set_branch(branch)

    def _on_git_status(self, status_map: dict) -> None:
        self._git_status = status_map
        # Update file explorer colours
        self._sidebar.explorer.apply_git_status(status_map)
        # Update tab titles
        for tab_id, path in self._files.items():
            if path:
                norm = os.path.normcase(path)
                status = status_map.get(norm, "")
                self._git_tab_status[tab_id] = status
                self._refresh_tab_title(tab_id)
        # Fetch fresh diff hunks for whichever tab is active
        self._refresh_git_hunks()
        # Keep SC panel up to date if it's visible
        if self._sidebar._sc_visible:
            self._refresh_sc_panel()

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
            if cv:
                cv._line_numbers.set_git_hunks(hunks)

    def _refresh_sc_panel(self) -> None:
        """Re-fetch staged/unstaged status and push it to the Source Control panel."""
        if not self._git:
            return
        self._git.get_full_status(self._on_sc_status)

    def _on_sc_status(self, staged: dict, unstaged: dict) -> None:
        self._sidebar.source_control.refresh(staged, unstaged)

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
            self._output.output.write(f"[git commit]\n{output}\n", "stdout")
            self._refresh_git()
            self._refresh_sc_panel()

        self._git.commit(message, callback=_done)

    def _sc_push(self) -> None:
        if not self._git:
            return
        self._output.output.write("[git push] Running…\n", "stdout")

        def _done(output: str) -> None:
            self._output.output.write(f"{output}\n", "stdout")
            self._refresh_git()

        self._git.push(callback=_done)

    def _sc_pull(self) -> None:
        if not self._git:
            return
        self._output.output.write("[git pull] Running…\n", "stdout")

        def _done(output: str) -> None:
            self._output.output.write(f"{output}\n", "stdout")
            self._refresh_git()
            self._refresh_sc_panel()

        self._git.pull(callback=_done)

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

    def _sc_gitignore_exists(self) -> bool:
        if not self._git:
            return False
        return os.path.exists(os.path.join(self._git._root, ".gitignore"))

    def _sc_create_gitignore(self) -> None:
        """Create a standard Python .gitignore in the repo root if absent."""
        if not self._git:
            return
        dest = os.path.join(self._git._root, ".gitignore")
        if os.path.exists(dest):
            self._output.output.write("[.gitignore] File already exists.\n", "stderr")
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
        self._output.output.write("[.gitignore] Created.\n", "stdout")
        self._refresh_git()
        self._refresh_sc_panel()

    def _open_diff_tab(self, title: str, diff_text: str) -> None:
        """Create a read-only syntax-colored tab showing a unified diff."""
        import tkinter as tk
        from tkinter import ttk

        frame = ttk.Frame(self.notebook)
        txt = tk.Text(
            frame,
            bg="#1e1e1e",
            fg="#cccccc",
            font=self._codeviews[self._current_tab_id].cget("font")
            if self._current_tab_id and self._codeviews
            else ("Consolas", 11),
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

        sb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
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
        self._lsp.completion(
            path,
            int(line) - 1,
            int(col),
            lambda items, s=seq: self._show_completion(items, cv, s),
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
        if prefix:
            items = sorted(
                items,
                key=lambda it: (
                    not it.get("label", "").lower().startswith(prefix.lower()),
                    it.get("label", "").lower(),
                ),
            )
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

    # ── Go to definition ──────────────────────────────────────────────────────

    def _goto_definition(self) -> None:
        cv = self._current_codeview
        path = self._files.get(self._current_tab_id)
        if not cv or not path or not self._lsp:
            return
        line, col = cv.index("insert").split(".")
        self._lsp.definition(path, int(line) - 1, int(col), self._handle_definition)

    def _handle_definition(self, result) -> None:
        if not result:
            return
        # result may be a single Location or a list
        if isinstance(result, dict):
            result = [result]
        if not result:
            return
        loc = result[0]
        uri = loc.get("uri", "")
        path = uri_to_path(uri)
        # Normalise to OS path
        path = path.replace("/", os.sep)
        if os.name == "nt" and path.startswith("\\"):
            path = path[1:]  # strip leading backslash on Windows
        line = loc["range"]["start"]["line"] + 1
        col = loc["range"]["start"]["character"]
        self._open_file_at(path, line, col)

    def _open_file_at(self, path: str, line: int, col: int) -> None:
        """Open *path* and position cursor at *line*:*col*."""
        # If already open in a tab, just switch to it
        for tab_id, fp in self._files.items():
            if fp and os.path.normcase(fp) == os.path.normcase(path):
                self.notebook.select(tab_id)
                cv = self._codeviews.get(tab_id)
                if cv:
                    cv.mark_set("insert", f"{line}.{col}")
                    cv.see("insert")
                return
        # Otherwise open as a new tab
        if os.path.isfile(path):
            self._open_file(path)
            cv = self._current_codeview
            if cv:
                cv.mark_set("insert", f"{line}.{col}")
                cv.see("insert")

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
            cv.tag_remove("active_line", "1.0", "end")
            if self.highlight_line_var.get() and self._active_line_color:
                cv.tag_configure("active_line", background=self._active_line_color)
                cv.tag_add("active_line", "insert linestart", "insert lineend+1c")
            # Keep status bar position in sync
            line, col = cv.index("insert").split(".")
            mc = self._multi_cursors.get(self._current_tab_id)
            cursors = mc.count() if mc and mc.active else 1
            self._statusbar.set_position(int(line), int(col), cursors)
        self.after(25, self._highlight_active_line)

    # ── File operations ───────────────────────────────────────────────────────

    def file_new(self) -> None:
        self._new_tab("Untitled", "")

    def file_open(self, *_) -> None:
        path = askopenfilename(
            filetypes=[
                ("Python Scripts", "*.py"),
                ("Text Documents", "*.txt"),
                ("All Files", "*.*"),
            ]
        )
        if path:
            self._open_file(path)

    def _open_file(self, path: str, update_explorer: bool = True) -> None:
        try:
            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as exc:
            showerror("Open Error", str(exc))
            return

        # If the current tab is an empty unmodified Untitled, remember it so we
        # can close it after the new tab is open (closing first would trigger the
        # "no tabs left" fallback and spawn another Untitled).
        old_tab_id = self._current_tab_id
        replace = (
            old_tab_id is not None
            and self._titles.get(old_tab_id) == "Untitled"
            and not self._dirty.get(old_tab_id)
            and not self._codeviews[old_tab_id].get("1.0", "end-1c").strip()
        )

        self._new_tab(os.path.basename(path), content, filepath=path)
        # Only update the explorer root when opening externally (File > Open),
        # not when clicking a file inside the tree (would reset root unexpectedly)
        if update_explorer:
            self._sidebar.explorer.set_root(path)

        if replace:
            old_index = self.notebook.tabs().index(old_tab_id)
            self._close_tab(old_index)

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
        path = asksaveasfilename(
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
            text = cv.get("1.0", "end-1c")
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(text)
            old_path = self._files.get(tab_id)
            # Update lexer if the filepath (and therefore extension) changed
            if old_path != filepath:
                try:
                    new_lexer = pygments.lexers.get_lexer_for_filename(filepath)
                    cv.configure(lexer=new_lexer)
                    handler = self._key_handlers.get(tab_id)
                    if handler:
                        handler.smart_pairs = not isinstance(
                            new_lexer, pygments.lexers.TextLexer
                        )
                except pygments.util.ClassNotFound:
                    pass
                # LSP: close old file, open new one (Save As changed the path)
                if self._lsp:
                    if old_path and old_path.endswith(".py"):
                        self._lsp.close_file(old_path)
                    if filepath.endswith(".py"):
                        self._lsp.open_file(filepath, text)
            elif filepath.endswith(".py") and self._lsp:
                self._lsp.save_file(filepath)
            self._files[tab_id] = filepath
            title = os.path.basename(filepath)
            self._titles[tab_id] = title
            self._dirty[tab_id] = False
            self._refresh_tab_title(tab_id)
            self._update_title()
            # Refresh git status + hunks after saving
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
        # Prompt for each dirty tab before exiting
        for tab_id in list(self.notebook.tabs()):
            if not self._confirm_close_tab(tab_id):
                return  # user cancelled — abort exit
        session_utils.save(self)
        self.quit()

    def destroy(self) -> None:
        self.file_exit()

    def workspace_new(self, *_) -> None:
        """Close the current workspace (with save prompt) and open a fresh one."""
        answer = askyesnocancel(
            "New Workspace",
            "Creating a new workspace will close the current one.\n\nWould you like to save the current workspace before closing?",
        )
        if answer is None:
            return  # Cancel
        if answer:
            self.workspace_save()
        # Check for dirty tabs
        for tab_id in list(self.notebook.tabs()):
            if not self._confirm_close_tab(tab_id):
                return
        # Close all tabs without auto-opening Untitled yet
        for tab_id in list(self.notebook.tabs()):
            self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            self._key_handlers.pop(tab_id, None)
        mc = self._multi_cursors.pop(tab_id, None)
        if mc:
            mc.clear()
            self.notebook.forget(tab_id)
        self._new_tab("Untitled", "")
        self._sidebar.explorer.set_root(os.getcwd())

    def workspace_close(self, *_) -> None:
        """Close the current workspace (with save prompt) leaving a blank state."""
        answer = askyesnocancel(
            "Close Workspace",
            "You are about to close your current workspace.\n\nWould you like to save before closing?",
        )
        if answer is None:
            return  # Cancel
        if answer:
            self.workspace_save()
        # Check for dirty tabs
        for tab_id in list(self.notebook.tabs()):
            if not self._confirm_close_tab(tab_id):
                return
        for tab_id in list(self.notebook.tabs()):
            self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            self._key_handlers.pop(tab_id, None)
        mc = self._multi_cursors.pop(tab_id, None)
        if mc:
            mc.clear()
            self.notebook.forget(tab_id)
        self._new_tab("Untitled", "")

    def workspace_save(self, *_) -> None:
        path = asksaveasfilename(
            title="Save Workspace",
            defaultextension=".json",
            filetypes=[("Workspace files", "*.json"), ("All files", "*.*")],
        )
        if path:
            session_utils.save(self, path)

    def workspace_open(self, *_) -> None:
        path = askopenfilename(
            title="Open Workspace",
            filetypes=[("Workspace files", "*.json"), ("All files", "*.*")],
        )
        if not path or not os.path.isfile(path):
            return
        # Close all tabs cleanly (bypass the auto-Untitled fallback)
        for tab_id in list(self.notebook.tabs()):
            self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            self._key_handlers.pop(tab_id, None)
        mc = self._multi_cursors.pop(tab_id, None)
        if mc:
            mc.clear()
            self.notebook.forget(tab_id)
        if not session_utils.restore(self, path):
            self._new_tab("Untitled", "")

    # ── Edit operations ───────────────────────────────────────────────────────

    def edit_undo(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Undo>>")

    def edit_redo(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Redo>>")

    def edit_cut(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Cut>>")

    def edit_copy(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Copy>>")

    def edit_paste(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<<Paste>>")

    def edit_select_all(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.event_generate("<Control-a>")

    def edit_find_replace(self, *_) -> None:
        cv = self._current_codeview
        if cv is None:
            return
        self._find_replace.show(cv)

    # ── View operations ───────────────────────────────────────────────────────

    def view_change_theme(self) -> None:
        cv = self._current_codeview
        if cv:
            cv.set_color_scheme(self.theme_var.get())
            self._active_line_color = cv.cget("inactiveselectbackground")
            self._sidebar.apply_theme(
                bg=cv.cget("bg"),
                fg=cv.cget("fg"),
                select_bg=cv.cget("selectbackground"),
                codeview=cv,
            )
            self._update_status_lexer(cv)

    def view_change_font(self, *_) -> None:
        font = askfont(self)
        if not font:
            return
        font["family"] = font["family"].replace(" ", "\\ ")
        font_str = "%(family)s %(size)i %(weight)s %(slant)s" % font
        if font["underline"]:
            font_str += " underline"
        if font["overstrike"]:
            font_str += " overstrike"
        cv = self._current_codeview
        if cv:
            cv.configure(font=font_str)

    def view_toggle_highlight(self) -> None:
        pass  # BooleanVar already toggled; the poll loop picks it up automatically

    def view_active_line_color(self) -> None:
        color = askcolor(self._active_line_color or "#ffffff", self)[1]
        if color:
            self._active_line_color = color

    def view_toggle_output(self) -> None:
        if self.output_visible_var.get():
            self._v_pane.add(self._output, weight=1)
        else:
            self._v_pane.forget(self._output)

    def view_new_terminal(self) -> None:
        """Show the bottom panel and switch to the Terminal tab."""
        if not self.output_visible_var.get():
            self.output_visible_var.set(True)
            self.view_toggle_output()
        self._output._set_active("terminal")

    def view_toggle_minimap(self) -> None:
        show = self.minimap_visible_var.get()
        for cv in self._codeviews.values():
            if cv is None:
                continue
            if show:
                cv.show_minimap()
            else:
                cv.hide_minimap()

    def view_split_editor(self) -> None:
        """Toggle the split editor."""
        if self._split_active:
            self._close_split()
        else:
            self._open_in_split(self._current_tab_id)

    # ── Split editor ──────────────────────────────────────────────────────────

    def _open_in_split(self, tab_id: str | None) -> None:
        """Open the file from *tab_id* in the right split pane."""
        if not tab_id:
            return
        path = self._files.get(tab_id)
        title = self._titles.get(tab_id, "Untitled")
        cv = self._codeviews.get(tab_id)
        if cv is None:
            return
        content = cv.get("1.0", "end-1c")

        # Build the right pane on first use
        if not self._split_active:
            self._build_right_pane()

        # Open as a new tab in the right notebook
        self._new_tab_in(
            self._notebook_r,
            title,
            content,
            filepath=path,
        )
        self._split_active = True
        self._set_active_pane("right")
        # Patch scroll callbacks on all codeviews now that split is live
        self._patch_scroll_callbacks()

    def _build_right_pane(self) -> None:
        """Create the right notebook frame and wire it up."""
        import tkinter as tk

        self._nb_frame_r = ttk.Frame(self._split_pane)
        self._split_pane.add(self._nb_frame_r, weight=1)

        # Thin header with "SPLIT" label, lock button, and × close button
        hdr = tk.Frame(self._nb_frame_r, bg="#2d2d30", height=24)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr,
            text="  SPLIT",
            bg="#2d2d30",
            fg="#858585",
            font=("Segoe UI", 8, "bold"),
        ).pack(side="left")
        tk.Button(
            hdr,
            text="×",
            bg="#2d2d30",
            fg="#858585",
            activebackground="#2d2d30",
            activeforeground="#cccccc",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10, "bold"),
            cursor="hand2",
            command=self._close_split,
        ).pack(side="right", padx=4)

        self._scroll_locked = False
        self._lock_btn = tk.Button(
            hdr,
            text="⇕",
            bg="#2d2d30",
            fg="#555555",
            activebackground="#2d2d30",
            activeforeground="#cccccc",
            relief="flat",
            bd=0,
            font=("Segoe UI", 10),
            cursor="hand2",
            command=self._toggle_scroll_lock,
        )
        self._lock_btn.pack(side="right", padx=2)

        self._notebook_r = CustomNotebook(
            self._nb_frame_r,
            on_close=lambda idx: self._close_tab(idx, self._notebook_r),
        )
        self._notebook_r.pack(fill="both", expand=True)
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

    def _toggle_scroll_lock(self) -> None:
        self._scroll_locked = not self._scroll_locked
        if self._lock_btn:
            self._lock_btn.config(fg="#007acc" if self._scroll_locked else "#555555")
        if self._scroll_locked:
            # Snap right pane to match left pane immediately
            left_cv = self._get_left_cv()
            right_cv = self._get_right_cv()
            if left_cv and right_cv:
                right_cv.yview_moveto(left_cv.yview()[0])

    def _get_left_cv(self):
        tid = self.notebook.select() if self.notebook.tabs() else None
        return self._codeviews.get(tid) if tid else None

    def _get_right_cv(self):
        if not self._notebook_r or not self._notebook_r.tabs():
            return None
        tid = self._notebook_r.select()
        return self._codeviews.get(tid)

    def _on_scroll_locked(self, source: str, *args) -> None:
        """Called by the yscrollcommand of whichever pane scrolled."""
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
        """Wrap the yscrollcommand on both codeviews so scroll lock can sync them."""
        import tkinter as tk

        left_cv = self._get_left_cv()
        right_cv = self._get_right_cv()
        if not left_cv or not right_cv:
            return

        orig_left_vs = left_cv.vertical_scroll
        orig_right_vs = right_cv.vertical_scroll

        def left_scroll(first, last):
            orig_left_vs(first, last)
            if self._scroll_locked and not self._syncing_scroll:
                self._syncing_scroll = True
                try:
                    right_cv.yview_moveto(float(first))
                finally:
                    self._syncing_scroll = False

        def right_scroll(first, last):
            orig_right_vs(first, last)
            if self._scroll_locked and not self._syncing_scroll:
                self._syncing_scroll = True
                try:
                    left_cv.yview_moveto(float(first))
                finally:
                    self._syncing_scroll = False

        tk.Text.configure(left_cv, yscrollcommand=left_scroll)
        tk.Text.configure(right_cv, yscrollcommand=right_scroll)

    def _close_split(self) -> None:
        """Close the right split pane after checking for unsaved changes."""
        if not self._split_active or self._notebook_r is None:
            return
        # Check each right-pane tab for unsaved changes
        for tab_id in list(self._notebook_r.tabs()):
            if not self._confirm_close_tab(tab_id):
                return  # user cancelled
        # All confirmed — clean up
        for tab_id in list(self._notebook_r.tabs()):
            closed_path = self._files.pop(tab_id, None)
            self._titles.pop(tab_id, None)
            self._dirty.pop(tab_id, None)
            self._indent_sizes.pop(tab_id, None)
            self._codeviews.pop(tab_id, None)
            self._key_handlers.pop(tab_id, None)
            mc = self._multi_cursors.pop(tab_id, None)
            if mc:
                mc.clear()
            if closed_path and closed_path.endswith(".py") and self._lsp:
                self._lsp.close_file(closed_path)
        self._split_pane.forget(self._nb_frame_r)
        self._nb_frame_r.destroy()
        self._nb_frame_r = None
        self._notebook_r = None
        self._split_active = False
        self._set_active_pane("left")

    def _new_tab_in(
        self,
        notebook: CustomNotebook,
        title: str,
        content: str,
        filepath: str | None = None,
    ) -> None:
        """Like _new_tab but targets a specific notebook (used for right pane)."""
        import pygments.lexers
        import pygments.util

        lexer = pygments.lexers.PythonLexer()
        if filepath:
            try:
                lexer = pygments.lexers.get_lexer_for_filename(filepath)
            except pygments.util.ClassNotFound:
                pass

        frame = ttk.Frame(notebook)
        codeview = CodeView(
            frame,
            lexer=lexer,
            color_scheme=self.theme_var.get(),
            tab_width=4,
            autohide_scrollbar=False,
            default_context_menu=True,
            undo=True,
            maxundo=-1,
        )
        codeview.pack(fill="both", expand=True)
        codeview.insert("1.0", content)
        codeview.edit_reset()

        notebook.add(frame, text=f"  {title}  ")
        notebook.select(frame)

        tab_id = notebook.select()
        self._files[tab_id] = filepath
        self._titles[tab_id] = title
        self._dirty[tab_id] = False
        self._indent_sizes[tab_id] = 4
        self._codeviews[tab_id] = codeview

        is_code = not isinstance(lexer, pygments.lexers.TextLexer)
        handler = KeyHandler(tab_size=4, smart_pairs=is_code)
        mc = MultiCursor(codeview, tab_size=4)
        self._key_handlers[tab_id] = handler
        self._multi_cursors[tab_id] = mc
        self._setup_codeview(codeview, handler, mc)
        self._sidebar.apply_theme(
            bg=codeview.cget("bg"),
            fg=codeview.cget("fg"),
            select_bg=codeview.cget("selectbackground"),
            codeview=codeview,
        )
        if not self.minimap_visible_var.get():
            codeview.hide_minimap()

        if isinstance(
            lexer, (pygments.lexers.PythonLexer, pygments.lexers.Python3Lexer)
        ):
            if filepath and self._lsp:
                self._lsp.open_file(filepath, content)

    def view_source_control(self) -> None:
        """Toggle the Source Control sidebar panel."""
        if self._sidebar._sc_visible:
            self._sidebar.hide_source_control()
        else:
            self._sidebar.show_source_control()
            self._refresh_sc_panel()

    # ── Run operations ────────────────────────────────────────────────────────

    def run_file(self) -> None:
        if not self.file_save():
            return
        filepath = self._files.get(self._current_tab_id)
        if filepath:
            # Make output panel visible if hidden
            if not self.output_visible_var.get():
                self.output_visible_var.set(True)
                self.view_toggle_output()
            self._output.run(filepath)

    def run_stop(self) -> None:
        self._output.terminate()

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
            ("New Workspace", "", self.workspace_new),
            ("Close Workspace", "", self.workspace_close),
            ("Save Workspace...", "", self.workspace_save),
            ("Open Workspace...", "", self.workspace_open),
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
            # Run
            ("Run File", "F5", self.run_file),
            ("Stop", "", self.run_stop),
            ("Clear Output", "", self.run_clear),
            # Help
            ("About", "", self.help_about),
        ]
        CommandPalette(
            self,
            commands,
            symbol_fn=self._outline.get_symbols,
            navigate_fn=self._outline_navigate,
        )

    # ── Help ─────────────────────────────────────────────────────────────────

    def help_about(self) -> None:
        showinfo(
            "Notepad",
            "A Python code editor built with tkinter.\n\nCreated/Authored By:\nAlex Fero & Claude",
        )
