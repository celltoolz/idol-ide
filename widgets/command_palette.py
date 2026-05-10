"""CommandPalette — VS Code-style command palette popup (Ctrl+Shift+P).

Typing '@' switches to symbol-search mode (like VS Code's Go to Symbol).
Typing '!' switches to pip-command mode.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable
from utils.ui_font import UI_FONT


_BG       = "#252526"
_INPUT_BG = "#3c3c3c"
_HOV_BG   = "#094771"
_SEL_BG   = "#0e639c"
_FG       = "#cccccc"
_DIM      = "#858585"
_HINT_FG  = "#569cd6"   # blue hint text in the input when empty
_PIP_FG   = "#4ec9b0"   # teal for pip mode
_BORDER   = "#454545"

# pip command templates — (display_label, arg_list_template, needs_package)
# needs_package=True means the last token the user types becomes the package name
_PIP_COMMANDS: list[tuple[str, list[str], bool]] = [
    ("pip install <package>",              ["install"],          True),
    ("pip install --upgrade <package>",    ["install", "--upgrade"], True),
    ("pip uninstall <package>",            ["uninstall", "-y"],  True),
    ("pip show <package>",                 ["show"],             True),
    ("pip list",                           ["list"],             False),
    ("pip freeze > requirements.txt",      ["freeze"],           False),
    ("pip install -r requirements.txt",    ["install", "-r", "requirements.txt"], False),
    ("pip check",                          ["check"],            False),
]


class CommandPalette(tk.Toplevel):
    """Floating command palette overlay.

    Commands mode  — default; type to filter the command list.
    Symbol mode    — activated by typing '@'; shows symbols from the current
                     file using *symbol_fn()* → [(label, lineno), ...].
                     Executing a symbol calls *navigate_fn(lineno)*.
    Pip mode       — activated by typing '!'; shows pip command suggestions
                     with package name autocomplete from the builtin lookup.

    Args:
        commands:          [(label, accelerator, callback), ...]
        symbol_fn:         Optional callable returning [(label, lineno), ...]
        navigate_fn:       Optional callable(lineno: int) to jump to a line
        run_pip_fn:        Optional callable(args: list[str]) to run a pip command
        installed_fn:      Optional callable returning {name: version} of installed pkgs
        pkg_lookup:        Optional dict[str, str] — the 362K package name→category map
    """

    def __init__(
        self,
        parent: tk.Misc,
        commands: list[tuple[str, str, Callable]],
        symbol_fn: Callable[[], list[tuple[str, int]]] | None = None,
        navigate_fn: Callable[[int], None] | None = None,
        run_pip_fn: Callable[[list[str]], None] | None = None,
        installed_fn: Callable[[], dict[str, str]] | None = None,
        pkg_lookup: dict[str, str] | None = None,
    ) -> None:
        super().__init__(parent)
        self._parent      = parent
        self._commands    = commands
        self._symbol_fn   = symbol_fn
        self._navigate_fn = navigate_fn
        self._run_pip_fn  = run_pip_fn
        self._installed_fn = installed_fn
        self._pkg_lookup  = pkg_lookup or {}
        self._filtered: list[tuple[str, str, Callable]] = list(commands)
        self._selected      = 0
        self._symbol_mode   = False
        self._pip_mode      = False
        self._repositioning = False

        # ── Window chrome ──────────────────────────────────────────────────────
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=_BORDER)

        # ── Search input ───────────────────────────────────────────────────────
        input_frame = tk.Frame(self, bg=_INPUT_BG, padx=1, pady=1)
        input_frame.pack(fill="x")

        self._var = tk.StringVar()
        self._var.trace_add("write", self._on_type)

        self._entry = tk.Entry(
            input_frame,
            textvariable=self._var,
            bg=_INPUT_BG,
            fg=_FG,
            insertbackground=_FG,
            relief="flat",
            font=(UI_FONT, 12),
            bd=6,
        )
        self._entry.pack(fill="x")

        # Hint label (shown below input)
        self._hint = tk.Label(
            self, text="  Type @ for symbols  ·  ! for pip commands",
            bg=_INPUT_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w",
        )
        self._hint.pack(fill="x")

        # ── Results list ───────────────────────────────────────────────────────
        list_outer = tk.Frame(self, bg=_BG, pady=4)
        list_outer.pack(fill="both", expand=True)

        self._canvas = tk.Canvas(
            list_outer, bg=_BG, highlightthickness=0, bd=0,
        )
        self._scrollbar = ttk.Scrollbar(
            list_outer, orient="vertical", command=self._canvas.yview
        )
        self._canvas.configure(yscrollcommand=self._scrollbar.set)

        self._scrollbar.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._list_frame = tk.Frame(self._canvas, bg=_BG)
        self._canvas_win = self._canvas.create_window(
            (0, 0), window=self._list_frame, anchor="nw"
        )
        self._list_frame.bind("<Configure>", self._on_frame_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)
        self._list_frame.bind("<MouseWheel>", self._on_mousewheel)
        self._list_frame.bind("<Button-4>",   self._on_mousewheel)
        self._list_frame.bind("<Button-5>",   self._on_mousewheel)

        # ── Key bindings ───────────────────────────────────────────────────────
        self._entry.bind("<Up>",        self._on_up)
        self._entry.bind("<Down>",      self._on_down)
        self._entry.bind("<Return>",    self._on_enter)
        self._entry.bind("<Escape>",    lambda _: self.close())
        self._entry.bind("<MouseWheel>", self._on_mousewheel)

        self._entry.bind("<FocusOut>", self._on_focus_out)
        self._configure_bid = self._parent.bind("<Configure>", self._on_parent_configure, add=True)
        self.bind("<Destroy>", self._on_destroy)

        # ── Position and show ──────────────────────────────────────────────────
        self._build_list()
        self._position()
        self.deiconify()
        self._entry.focus_set()

    # ── Positioning ───────────────────────────────────────────────────────────

    def _position(self, n_results: int | None = None) -> None:
        self.update_idletasks()
        pw = self._parent.winfo_width()
        px = self._parent.winfo_rootx()
        py = self._parent.winfo_rooty()

        w = min(600, max(400, pw // 2))
        n = n_results if n_results is not None else len(self._filtered)
        hint_h = 22
        h = min(420, 54 + hint_h + n * 38)

        x = px + (pw - w) // 2
        y = py + 60

        self.geometry(f"{w}x{h}+{x}+{y}")

    # ── List rendering ────────────────────────────────────────────────────────

    def _build_list(self) -> None:
        for w in self._list_frame.winfo_children():
            w.destroy()
        self._rows: list[tk.Frame] = []

        for i, (label, accel, _) in enumerate(self._filtered):
            row = tk.Frame(self._list_frame, bg=_BG, cursor="hand2")
            row.pack(fill="x", padx=4, pady=1)
            self._rows.append(row)

            lbl = tk.Label(
                row, text=label, bg=_BG, fg=_FG,
                font=(UI_FONT, 10), anchor="w", padx=10, pady=6,
            )
            lbl.pack(side="left", fill="x", expand=True)

            if accel:
                fg = _HINT_FG if self._symbol_mode else _DIM
                tk.Label(
                    row, text=accel, bg=_BG, fg=fg,
                    font=(UI_FONT, 9), padx=10,
                ).pack(side="right")

            idx = i
            for widget in row.winfo_children() + [row]:
                widget.bind("<Enter>",      lambda _, r=idx: self._hover(r))
                widget.bind("<Leave>",      lambda _, r=idx: self._unhover(r))
                widget.bind("<Button-1>",   lambda _, r=idx: self._execute(r))
                widget.bind("<MouseWheel>", self._on_mousewheel)
                widget.bind("<Button-4>",   self._on_mousewheel)
                widget.bind("<Button-5>",   self._on_mousewheel)

        self._highlight(self._selected)

    def _highlight(self, idx: int) -> None:
        for i, row in enumerate(self._rows):
            bg = _SEL_BG if i == idx else _BG
            row.configure(bg=bg)
            for child in row.winfo_children():
                child.configure(bg=bg)

    def _hover(self, idx: int) -> None:
        if idx != self._selected:
            row = self._rows[idx]
            row.configure(bg=_HOV_BG)
            for child in row.winfo_children():
                child.configure(bg=_HOV_BG)

    def _unhover(self, idx: int) -> None:
        if idx != self._selected:
            row = self._rows[idx]
            row.configure(bg=_BG)
            for child in row.winfo_children():
                child.configure(bg=_BG)

    def _scroll_to(self, idx: int) -> None:
        if not self._rows or idx >= len(self._rows):
            return
        self.update_idletasks()
        row = self._rows[idx]
        canvas_h = self._canvas.winfo_height()
        frame_h  = self._list_frame.winfo_height()
        if frame_h <= canvas_h:
            return
        row_y = row.winfo_y()
        row_h = row.winfo_height()
        frac  = max(0.0, min(1.0, (row_y - canvas_h // 2 + row_h // 2) / frame_h))
        self._canvas.yview_moveto(frac)

    # ── Events ────────────────────────────────────────────────────────────────

    def _on_type(self, *_) -> None:
        raw   = self._var.get()
        query = raw.lower()

        if raw.startswith("@") and self._symbol_fn:
            # ── Symbol mode ───────────────────────────────────────────────────
            self._symbol_mode = True
            self._pip_mode    = False
            self._hint.config(
                text="  @ symbols — press Enter or click to navigate",
                fg=_HINT_FG,
            )
            sub = raw[1:].lower()
            symbols = self._symbol_fn()
            self._filtered = [
                (label, f"L{lineno}", lambda ln=lineno: self._nav(ln))
                for label, lineno in symbols
                if sub in label.lower()
            ]

        elif raw.startswith("!"):
            # ── Pip mode ──────────────────────────────────────────────────────
            self._symbol_mode = False
            self._pip_mode    = True
            self._hint.config(
                text="  ! pip — press Enter to run in Output panel",
                fg=_PIP_FG,
            )
            self._filtered = self._build_pip_suggestions(raw[1:].strip())

        else:
            # ── Command mode ─────────────────────────────────────────────────
            self._symbol_mode = False
            self._pip_mode    = False
            self._hint.config(
                text="  Type @ for symbols  ·  ! for pip commands",
                fg=_DIM,
            )
            self._filtered = [
                (lbl, accel, cb)
                for lbl, accel, cb in self._commands
                if query in lbl.lower()
            ]

        self._selected = 0
        self._build_list()
        self._position(len(self._filtered))

    def _build_pip_suggestions(self, after_bang: str) -> list[tuple[str, str, Callable]]:
        """Return filtered pip command rows based on what the user typed after '!'."""
        # Parse what the user has typed so far
        # e.g. "pip install req" → cmd_part="install", pkg_part="req"
        tokens = after_bang.lower().split()
        # Strip leading "pip" if typed
        if tokens and tokens[0] == "pip":
            tokens = tokens[1:]

        cmd_part = tokens[0] if tokens else ""
        pkg_part = tokens[1] if len(tokens) > 1 else ""

        installed = self._installed_fn() if self._installed_fn else {}
        results: list[tuple[str, str, Callable]] = []

        for label_tpl, args, needs_pkg in _PIP_COMMANDS:
            # Filter by command word
            subcmd = args[0]  # e.g. "install", "show", "list"
            if cmd_part and subcmd not in cmd_part and cmd_part not in subcmd:
                continue

            if needs_pkg and pkg_part:
                # Generate package-specific suggestions
                pkg_suggestions = self._pkg_suggestions(pkg_part, subcmd, installed)
                for pkg in pkg_suggestions:
                    final_args = args + [pkg]
                    display = f"pip {' '.join(args)} {pkg}"
                    hint = "installed" if pkg in installed else ""
                    results.append((display, hint, lambda a=final_args: self._run_pip(a)))
                if not pkg_suggestions:
                    # No matches yet — show the template as a placeholder
                    display = label_tpl.replace("<package>", pkg_part or "…")
                    final_args = args + ([pkg_part] if pkg_part else [])
                    results.append((display, "", lambda a=final_args: self._run_pip(a)))
            else:
                display = label_tpl.replace("<package>", pkg_part or "<package>")
                final_args = args + ([pkg_part] if needs_pkg and pkg_part else [])
                results.append((display, "", lambda a=final_args: self._run_pip(a)))

        return results[:20]

    def _pkg_suggestions(self, prefix: str, subcmd: str, installed: dict) -> list[str]:
        """Return up to 8 package name suggestions for the given prefix."""
        q = prefix.lower()
        # For uninstall/show/upgrade — only suggest installed packages
        if subcmd in ("uninstall", "show"):
            return sorted(
                (n for n in installed if q in n.lower()),
                key=lambda n: (not n.lower().startswith(q), len(n))
            )[:8]
        # For install — search the 362K lookup by prefix/contains
        exact, starts, contains = [], [], []
        for pkg in self._pkg_lookup:
            if pkg == q:
                exact.append(pkg)
            elif pkg.startswith(q):
                starts.append(pkg)
            elif q in pkg:
                contains.append(pkg)
        starts.sort(key=len)
        contains.sort(key=len)
        return (exact + starts + contains)[:8]

    def _run_pip(self, args: list[str]) -> None:
        if self._run_pip_fn and args:
            self._run_pip_fn(args)

    def _nav(self, lineno: int) -> None:
        if self._navigate_fn:
            self._navigate_fn(lineno)

    def _on_up(self, _) -> None:
        if not self._rows:
            return
        self._selected = max(0, self._selected - 1)
        self._highlight(self._selected)
        self._scroll_to(self._selected)

    def _on_down(self, _) -> None:
        if not self._rows:
            return
        self._selected = min(len(self._rows) - 1, self._selected + 1)
        self._highlight(self._selected)
        self._scroll_to(self._selected)

    def _on_enter(self, _) -> None:
        self._execute(self._selected)

    def _execute(self, idx: int) -> None:
        if 0 <= idx < len(self._filtered):
            _, _, cb = self._filtered[idx]
            self.close()
            cb()

    def _on_focus_out(self, _) -> None:
        # Small delay so clicks on rows (which briefly steal focus) don't close prematurely
        self.after(100, self._check_focus)

    def _check_focus(self) -> None:
        if self._repositioning:
            return
        try:
            focused = self.focus_get()
            # Keep open if focus is still inside this window
            if focused and str(focused).startswith(str(self)):
                return
        except Exception:
            pass
        self.close()

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_parent_configure(self, _) -> None:
        self._repositioning = True
        self._position(len(self._filtered))
        self.after(150, self._clear_repositioning)

    def _clear_repositioning(self) -> None:
        self._repositioning = False
        try:
            self._entry.focus_set()
        except Exception:
            pass

    def _on_destroy(self, _) -> None:
        try:
            self._parent.unbind("<Configure>", self._configure_bid)
        except Exception:
            pass

    def _on_frame_configure(self, _) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._canvas_win, width=event.width)

    def close(self) -> None:
        try:
            self.destroy()
        except Exception:
            pass
