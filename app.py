from __future__ import annotations

import builtins
import os
import re
from tkinter import BooleanVar, Button, StringVar, Tk, ttk
from tkinter.filedialog import askopenfilename, asksaveasfilename
from tkinter.messagebox import showinfo, showerror, askyesnocancel

import pygments.lexers
import pygments.util
from tkfontchooser import askfont
from tkcolorpicker import askcolor

from widgets.codeview import CodeView
from widgets.notebook import CustomNotebook
from widgets.sidebar import Sidebar
from widgets.output import OutputPanel
from widgets.find_replace import FindReplaceBar
from widgets.statusbar import StatusBar
from editor.bracket_matcher import BracketMatcher
from editor.key_handler import KeyHandler
from menus.menubar import build_menubar
from utils import session as session_utils

# Words that should NOT trigger word-highlight on click
_SKIP_HIGHLIGHT = (
    set(dir(builtins))
    | {
        "and", "as", "assert", "async", "await", "break", "case", "class",
        "continue", "def", "del", "elif", "else", "except", "finally", "for",
        "from", "global", "if", "import", "in", "is", "lambda", "match", "not",
        "or", "pass", "raise", "return", "try", "while", "with", "yield",
        "False", "None", "True",
    }
    | {str(i) for i in range(10)}
    | {"(", ")", "[", "]", "{", "}", ".", ",", ":", ";"}
)


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

        self._bracket_matcher = BracketMatcher()
        self._find_replace: FindReplaceBar | None = None

        # Settings
        self.theme_var = StringVar(value="monokai")
        self.highlight_line_var = BooleanVar(value=True)
        self.output_visible_var = BooleanVar(value=True)
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

        # Left panel – sidebar (outline + explorer)
        self._sidebar = Sidebar(
            self._h_pane,
            on_file_open=self._open_file,
            on_navigate=self._outline_navigate,
        )
        self._sidebar.configure(width=220)
        self._h_pane.add(self._sidebar, weight=0)
        self._outline = self._sidebar.outline  # keep existing references working

        # Right panel – vertical split: notebook (top) | output (bottom)
        self._v_pane = ttk.PanedWindow(self._h_pane, orient="vertical")
        self._h_pane.add(self._v_pane, weight=1)

        # Wrap notebook in a frame so the "+" button can sit as a sibling
        # on top of the tab bar without being clipped by the notebook renderer
        nb_frame = ttk.Frame(self._v_pane)
        self.notebook = CustomNotebook(nb_frame, on_close=self._close_tab)
        self.notebook.pack(fill="both", expand=True)
        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed, add=True)

        # Inline find/replace bar (lives inside nb_frame, hidden by default)
        self._find_replace = FindReplaceBar(nb_frame)

        _btn_kw = dict(
            font=("Segoe UI", 11, "bold"),
            bg="#2d2d30", activebackground="#2d2d30",
            cursor="hand2", padx=4, pady=0,
            relief="flat", bd=0,
            highlightthickness=1, highlightbackground="#454545",
        )

        self._prev_btn = Button(nb_frame, text=" ‹ ", fg="#858585",
                                activeforeground="#cccccc",
                                command=self.notebook.select_prev, **_btn_kw)
        self._prev_btn.bind("<Enter>", lambda _: self._prev_btn.config(fg="#cccccc", highlightbackground="#666666"))
        self._prev_btn.bind("<Leave>", lambda _: self._prev_btn.config(fg="#858585", highlightbackground="#454545"))

        self._next_btn = Button(nb_frame, text=" › ", fg="#858585",
                                activeforeground="#cccccc",
                                command=self.notebook.select_next, **_btn_kw)
        self._next_btn.bind("<Enter>", lambda _: self._next_btn.config(fg="#cccccc", highlightbackground="#666666"))
        self._next_btn.bind("<Leave>", lambda _: self._next_btn.config(fg="#858585", highlightbackground="#454545"))

        self._plus_btn = Button(nb_frame, text=" + ", fg="#858585",
                                activeforeground="#2ea043",
                                command=self.file_new, **_btn_kw)
        self._plus_btn.bind("<Enter>", lambda _: self._plus_btn.config(fg="#2ea043", highlightbackground="#2ea043"))
        self._plus_btn.bind("<Leave>", lambda _: self._plus_btn.config(fg="#858585", highlightbackground="#454545"))

        for btn in (self._prev_btn, self._next_btn, self._plus_btn):
            btn.lift()

        self._v_pane.add(nb_frame, weight=3)

        self._output = OutputPanel(self._v_pane, run_callback=self.run_file)
        self._v_pane.add(self._output, weight=1)

        # Snap the sash once the window is actually visible on screen
        self.bind("<Map>", self._init_sash_pos)

    def _init_sash_pos(self, _=None) -> None:
        """Set the output panel to a small strip on first launch."""
        self.unbind("<Map>")  # only run once
        self.update_idletasks()
        total = self._v_pane.winfo_height()
        if total > 200:
            self._v_pane.sashpos(0, total - 160)
        self._place_plus_btn()

    def _place_plus_btn(self) -> None:
        """Position the ‹ › + buttons directly above the vertical scrollbar."""
        cv = self._current_codeview
        if cv is None:
            return
        vs = cv._vs
        vs.update_idletasks()
        vs_x = vs.winfo_x() + cv._frame.winfo_x() + self.notebook.winfo_x()
        vs_w = vs.winfo_width()
        tab_h = self.notebook.winfo_height() - cv._frame.winfo_height()
        btn_h = max(tab_h - 6, 16)

        # Place ‹ › + side by side, each the same width as the scrollbar
        self._prev_btn.place(x=vs_x - vs_w * 2, y=3, width=vs_w, height=btn_h, anchor="nw")
        self._next_btn.place(x=vs_x - vs_w,     y=3, width=vs_w, height=btn_h, anchor="nw")
        self._plus_btn.place(x=vs_x,             y=3, width=vs_w, height=btn_h, anchor="nw")
        for btn in (self._prev_btn, self._next_btn, self._plus_btn):
            btn.lift()

        # Reserve space on the right of the tab bar so tabs never slide under the buttons
        btn_area = vs_w * 3 + 6
        if getattr(self, "_last_btn_area", None) != btn_area:
            self._last_btn_area = btn_area
            ttk.Style().configure("CustomNotebook", tabmargins=[2, 5, btn_area, 0])

    def _bind_shortcuts(self) -> None:
        self.bind("<Control-n>", lambda _: self.file_new())
        self.bind("<Control-o>", lambda _: self.file_open())
        self.bind("<Control-s>", lambda _: self.file_save())
        self.bind("<Control-S>", lambda _: self.file_save_as())
        self.bind("<Control-w>", lambda _: self.file_close())
        self.bind("<Control-q>", lambda _: self.file_exit())
        self.bind("<Control-f>", lambda _: self.edit_find_replace())
        self.bind("<Control-l>", lambda _: self.view_change_font())
        self.bind("<F5>",        lambda _: self.run_file())

    # ── Tab helpers ───────────────────────────────────────────────────────────

    @property
    def _current_tab_id(self) -> str | None:
        if not self.notebook.tabs():
            return None
        return self.notebook.select()

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

        handler = KeyHandler(tab_size=4)
        self._key_handlers[tab_id] = handler
        self._setup_codeview(codeview, handler)
        self._sidebar.apply_theme(
            bg=codeview.cget("bg"),
            fg=codeview.cget("fg"),
            select_bg=codeview.cget("selectbackground"),
        )

        self._update_title()
        self._outline.schedule_refresh(content)

    def _setup_codeview(self, codeview: CodeView, handler: KeyHandler) -> None:
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

        codeview.bind("<Key>",            lambda e: handler.handle(e, codeview))
        codeview.bind("<KeyRelease>",     self._bracket_matcher.match)
        codeview.bind("<ButtonRelease-1>", self._on_click_release)
        codeview.bind("<ButtonPress-3>",   self._on_editor_right_click)
        codeview.bind("<<ContentChanged>>", lambda _: self._on_content_changed())

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
        if answer is None:   # Cancel
            return False
        if answer:           # Yes — save first
            if tab_id != self._current_tab_id:
                self.notebook.select(tab_id)
            if not self.file_save():
                return False  # save failed or was cancelled
        return True

    def _close_tab(self, index: int) -> None:
        tabs = self.notebook.tabs()
        if index >= len(tabs):
            return
        tab_id = tabs[index]
        if not self._confirm_close_tab(tab_id):
            return
        self._files.pop(tab_id, None)
        self._titles.pop(tab_id, None)
        self._dirty.pop(tab_id, None)
        self._indent_sizes.pop(tab_id, None)
        self._codeviews.pop(tab_id, None)
        self._key_handlers.pop(tab_id, None)
        self.notebook.forget(index)
        if not self.notebook.tabs():
            self._new_tab("Untitled", "")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _on_tab_changed(self, *_) -> None:
        tab_id = self._current_tab_id
        if tab_id is None:
            return
        self._update_title()
        self._statusbar.set_indent(self._indent_sizes.get(tab_id, 4))
        cv = self._codeviews.get(tab_id)
        if cv:
            self._update_status_lexer(cv)
            self._outline.schedule_refresh(cv.get("1.0", "end-1c"))
            self.after(50, self._place_plus_btn)

    def _on_content_changed(self) -> None:
        tab_id = self._current_tab_id
        if tab_id and not self._dirty.get(tab_id):
            self._dirty[tab_id] = True
            self._refresh_tab_title(tab_id)
        cv = self._current_codeview
        if cv:
            self._outline.schedule_refresh(cv.get("1.0", "end-1c"))

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
                label="Find References",
                command=self._find_references,
            )
            self._editor_menu.add_command(
                label="Find & Replace",
                command=self.edit_find_replace,
            )

        # Enable/disable Find References based on whether there's a word
        state = "normal" if (word and word not in _SKIP_HIGHLIGHT and not word[0].isdigit()) else "disabled"
        self._editor_menu.entryconfigure("Find References", state=state)
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
        self.notebook.tab(tab_id, text=f"  {marker}{name}  ")

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

    # ── Active-line highlight loop ────────────────────────────────────────────

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
            self._statusbar.set_position(int(line), int(col))
        self.after(25, self._highlight_active_line)

    # ── File operations ───────────────────────────────────────────────────────

    def file_new(self) -> None:
        self._new_tab("Untitled", "")

    def file_open(self, *_) -> None:
        path = askopenfilename(filetypes=[
            ("Python Scripts", "*.py"),
            ("Text Documents", "*.txt"),
            ("All Files", "*.*"),
        ])
        if path:
            self._open_file(path)

    def _open_file(self, path: str) -> None:
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
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(cv.get("1.0", "end-1c"))
            # Update lexer if the filepath (and therefore extension) changed
            if self._files.get(tab_id) != filepath:
                try:
                    cv.configure(lexer=pygments.lexers.get_lexer_for_filename(filepath))
                except pygments.util.ClassNotFound:
                    pass
            self._files[tab_id] = filepath
            title = os.path.basename(filepath)
            self._titles[tab_id] = title
            self._dirty[tab_id] = False
            self._refresh_tab_title(tab_id)
            self._update_title()
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

    # ── Help ─────────────────────────────────────────────────────────────────

    def help_about(self) -> None:
        showinfo("Notepad", "A Python code editor built with tkinter.")
