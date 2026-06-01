"""Welcome tab panel."""
from __future__ import annotations

import itertools
import os
import tkinter as tk
from pathlib import Path
from tkinter import ttk
from typing import Callable

from utils import recent as _recent
from utils.ui_font import UI_FONT

_BG       = "#1e1e1e"
_BG2      = "#252526"
_BG3      = "#2d2d30"
_FG       = "#cccccc"
_DIM      = "#858585"
_BLUE     = "#007acc"
_BLUE_H   = "#1a9fd4"
_GREEN    = "#4ec9b0"
_SECTION  = "#569cd6"
_SEP      = "#3c3c3c"

_TIPS = [
    "Drag a tab past the right edge to open the Split Editor",
    "Ctrl+\\ toggles the Split Editor",
    "Ctrl+P opens the Command Palette — search anything",
    "F1 activates Learning Mode — hover any element for an explanation",
    "Right-click a tab to copy it to the Split Editor",
    "Drag from the Split Editor back to the main pane to move a tab",
    "F3 opens the Package Manager — pip installs without a terminal",
    "Reopen this tab anytime via Help → Welcome",
    "Ctrl+Shift+G generates Python code from the GUI Designer form",
]


class WelcomePanel(tk.Frame):
    """Scrollable welcome / home tab."""

    def __init__(
        self,
        parent,
        on_new_file: Callable,
        on_open_file: Callable,
        on_open_folder: Callable,
        on_new_project: Callable,
        on_open_project: Callable,
        on_learning: Callable,
        on_designer: Callable,
        on_packages: Callable,
        **kwargs,
    ):
        super().__init__(parent, bg=_BG, **kwargs)
        self._cbs = {
            "new_file":     on_new_file,
            "open_file":    on_open_file,
            "open_folder":  on_open_folder,
            "new_project":  on_new_project,
            "open_project": on_open_project,
            "learning":     on_learning,
            "designer":     on_designer,
            "packages":     on_packages,
        }
        self._tip_cycle = itertools.cycle(_TIPS)
        self._tip_after_id = None

        self._canvas = tk.Canvas(self, bg=_BG, highlightthickness=0)
        self._scroll = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._scroll.set)
        self._scroll.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=_BG)
        self._win_id = self._canvas.create_window((0, 0), window=self._inner, anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)

        self._build()
        self._start_tip_rotation()

    # ── Scrolling ─────────────────────────────────────────────────────────────

    def _on_inner_configure(self, _event) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._win_id, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.num == 4 or (hasattr(event, "delta") and event.delta > 0):
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        for w in self._inner.winfo_children():
            w.destroy()

        outer = tk.Frame(self._inner, bg=_BG)
        outer.pack(fill="both", expand=True, padx=0, pady=0)

        self._build_header(outer)
        self._build_body(outer)
        self._build_footer(outer)

    def _build_header(self, parent: tk.Frame) -> None:
        hdr = tk.Frame(parent, bg=_BG2)
        hdr.pack(fill="x")

        # Logo image (if Pillow available) — fallback to text block
        logo_path = Path(__file__).parent.parent / "images" / "IDOL.png"
        logo_shown = False
        try:
            from PIL import Image, ImageTk  # type: ignore
            img = Image.open(logo_path)
            h = 48
            w = int(img.width * h / img.height)
            img = img.resize((w, h), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            lbl = tk.Label(hdr, image=photo, bg=_BG2, bd=0)
            lbl._photo = photo
            lbl.pack(side="left", padx=(32, 12), pady=20)
            logo_shown = True
        except Exception:
            pass

        if not logo_shown:
            tk.Label(
                hdr, text="⬛", bg=_BG2, fg=_BLUE,
                font=(UI_FONT, 28), padx=32, pady=16,
            ).pack(side="left")

        title_col = tk.Frame(hdr, bg=_BG2)
        title_col.pack(side="left", pady=16)
        tk.Label(
            title_col, text="IDOL", bg=_BG2, fg="#ffffff",
            font=(UI_FONT, 20, "bold"), anchor="w",
        ).pack(anchor="w")
        tk.Label(
            title_col, text="Integrated Development & Objective Learning",
            bg=_BG2, fg=_DIM, font=(UI_FONT, 9), anchor="w",
        ).pack(anchor="w")

        # Separator
        tk.Frame(parent, bg=_SEP, height=1).pack(fill="x")

    def _build_body(self, parent: tk.Frame) -> None:
        body = tk.Frame(parent, bg=_BG)
        body.pack(fill="both", expand=True, padx=32, pady=24)
        body.columnconfigure(0, weight=1, uniform="col")
        body.columnconfigure(1, weight=1, uniform="col")

        # ── Left column ───────────────────────────────────────────────────────
        left = tk.Frame(body, bg=_BG)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 24))

        self._section(left, "START")
        self._action(left, "+ New File",          self._cbs["new_file"])
        self._action(left, "⊘ Open File...",      self._cbs["open_file"])
        self._action(left, "⊡ Open Folder...",    self._cbs["open_folder"])
        self._action(left, "✦ New Project...",     self._cbs["new_project"])
        self._action(left, "⊞ Open Project...",   self._cbs["open_project"])

        tk.Frame(left, bg=_BG, height=16).pack()

        self._section(left, "EXPLORE")
        self._action(left, "📖 Learning Mode",    self._cbs["learning"])
        self._action(left, "🎨 GUI Designer",     self._cbs["designer"])
        self._action(left, "📦 Package Manager",  self._cbs["packages"])

        tk.Frame(left, bg=_BG, height=16).pack()

        self._section(left, "WHAT'S NEW")
        self._whats_new(left)

        # ── Right column ──────────────────────────────────────────────────────
        right = tk.Frame(body, bg=_BG)
        right.grid(row=0, column=1, sticky="nsew")

        self._section(right, "RECENT PROJECTS")
        self._recent_projects_list = tk.Frame(right, bg=_BG)
        self._recent_projects_list.pack(fill="x")
        self._populate_recent_projects()

        tk.Frame(right, bg=_BG, height=16).pack()

        self._section(right, "RECENT FILES")
        self._recent_files_list = tk.Frame(right, bg=_BG)
        self._recent_files_list.pack(fill="x")
        self._populate_recent_files()

    def _build_footer(self, parent: tk.Frame) -> None:
        tk.Frame(parent, bg=_SEP, height=1).pack(fill="x")
        footer = tk.Frame(parent, bg=_BG2)
        footer.pack(fill="x")

        # Tips row
        tip_row = tk.Frame(footer, bg=_BG2)
        tip_row.pack(fill="x", padx=32, pady=(10, 4))
        tk.Label(tip_row, text="💡", bg=_BG2, fg=_GREEN,
                 font=(UI_FONT, 9)).pack(side="left")
        self._tip_lbl = tk.Label(
            tip_row, text="", bg=_BG2, fg=_DIM,
            font=(UI_FONT, 9), anchor="w",
        )
        self._tip_lbl.pack(side="left", padx=(4, 0))

        # Startup checkbox row
        ck_row = tk.Frame(footer, bg=_BG2)
        ck_row.pack(fill="x", padx=32, pady=(0, 10))
        self._startup_var = tk.BooleanVar(value=_recent.get_show_on_startup())
        ck = tk.Checkbutton(
            ck_row,
            text="Show Welcome tab on startup",
            variable=self._startup_var,
            bg=_BG2, fg=_DIM, selectcolor=_BG3,
            activebackground=_BG2, activeforeground=_FG,
            font=(UI_FONT, 9),
            command=self._on_startup_toggle,
            relief="flat", bd=0,
        )
        ck.pack(side="left")
        tk.Label(
            ck_row, text="Help → Welcome",
            bg=_BG2, fg=_DIM, font=(UI_FONT, 8),
        ).pack(side="right", padx=(0, 0))

    # ── Section helpers ───────────────────────────────────────────────────────

    def _section(self, parent: tk.Frame, title: str) -> None:
        row = tk.Frame(parent, bg=_BG)
        row.pack(fill="x", pady=(0, 4))
        tk.Label(row, text=title, bg=_BG, fg=_SECTION,
                 font=(UI_FONT, 8, "bold")).pack(side="left")
        tk.Frame(row, bg=_SEP, height=1).pack(side="left", fill="x", expand=True, padx=(8, 0), pady=6)

    def _action(self, parent: tk.Frame, label: str, cmd: Callable) -> None:
        lbl = tk.Label(
            parent, text=f"  {label}",
            bg=_BG, fg=_BLUE,
            font=(UI_FONT, 10), anchor="w", cursor="hand2",
        )
        lbl.pack(fill="x", pady=1)
        lbl.bind("<Enter>",    lambda _: lbl.config(fg=_BLUE_H, bg=_BG3))
        lbl.bind("<Leave>",    lambda _: lbl.config(fg=_BLUE,   bg=_BG))
        lbl.bind("<ButtonRelease-1>", lambda _: cmd())

    def _whats_new(self, parent: tk.Frame) -> None:
        box = tk.Frame(parent, bg=_BG3, padx=10, pady=8)
        box.pack(fill="x")
        tk.Label(
            box,
            text="Changelog coming soon.\nCheck back after the next update.",
            bg=_BG3, fg=_DIM, font=(UI_FONT, 9),
            justify="left", anchor="w",
        ).pack(anchor="w")

    # ── Recent lists ──────────────────────────────────────────────────────────

    def _populate_recent_projects(self) -> None:
        for w in self._recent_projects_list.winfo_children():
            w.destroy()
        projects = _recent.get_projects()
        if not projects:
            tk.Label(
                self._recent_projects_list,
                text="  No recent projects",
                bg=_BG, fg=_DIM, font=(UI_FONT, 9), anchor="w",
            ).pack(fill="x")
            return
        for proj in projects:
            self._recent_row(
                self._recent_projects_list,
                proj["name"], proj.get("path", ""),
                lambda p=proj["path"]: self._open_recent_project(p),
                lambda p=proj["path"]: self._remove_recent_project(p),
            )

    def _populate_recent_files(self) -> None:
        for w in self._recent_files_list.winfo_children():
            w.destroy()
        files = _recent.get_files()
        if not files:
            tk.Label(
                self._recent_files_list,
                text="  No recent files",
                bg=_BG, fg=_DIM, font=(UI_FONT, 9), anchor="w",
            ).pack(fill="x")
            return
        for f in files:
            self._recent_row(
                self._recent_files_list,
                f["name"], f.get("path", ""),
                lambda p=f["path"]: self._open_recent_file(p),
                lambda p=f["path"]: self._remove_recent_file(p),
            )

    def _recent_row(
        self,
        parent: tk.Frame,
        name: str,
        path: str,
        on_open: Callable,
        on_remove: Callable,
    ) -> None:
        row = tk.Frame(parent, bg=_BG, cursor="hand2")
        row.pack(fill="x", pady=1)

        # Name + path stacked
        text_col = tk.Frame(row, bg=_BG)
        text_col.pack(side="left", fill="x", expand=True)

        name_lbl = tk.Label(
            text_col, text=f"  {name}",
            bg=_BG, fg=_BLUE, font=(UI_FONT, 10), anchor="w",
        )
        name_lbl.pack(fill="x")

        short_path = _shorten_path(path)
        path_lbl = tk.Label(
            text_col, text=f"    {short_path}",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w",
        )
        path_lbl.pack(fill="x")

        # × remove button
        x_lbl = tk.Label(
            row, text="×", bg=_BG, fg=_DIM,
            font=(UI_FONT, 11), cursor="hand2", padx=6,
        )
        x_lbl.pack(side="right")

        # Hover / click bindings
        for widget in (row, text_col, name_lbl, path_lbl):
            widget.bind("<Enter>",    lambda _, r=row, n=name_lbl, pl=path_lbl: _hover_row(r, n, pl, True))
            widget.bind("<Leave>",    lambda _, r=row, n=name_lbl, pl=path_lbl: _hover_row(r, n, pl, False))
            widget.bind("<ButtonRelease-1>", lambda _, fn=on_open: fn())
        x_lbl.bind("<Enter>",    lambda _: x_lbl.config(fg="#e8e8e8"))
        x_lbl.bind("<Leave>",    lambda _: x_lbl.config(fg=_DIM))
        x_lbl.bind("<ButtonRelease-1>", lambda _, fn=on_remove: fn())

    # ── Actions ───────────────────────────────────────────────────────────────

    def _open_recent_project(self, path: str) -> None:
        if not os.path.isdir(path):
            _recent.remove_project(path)
            self.refresh()
            return
        self._cbs["open_project"](path)

    def _remove_recent_project(self, path: str) -> None:
        _recent.remove_project(path)
        self._populate_recent_projects()

    def _open_recent_file(self, path: str) -> None:
        if not os.path.isfile(path):
            _recent.remove_file(path)
            self.refresh()
            return
        self._cbs["open_file"](path)

    def _remove_recent_file(self, path: str) -> None:
        _recent.remove_file(path)
        self._populate_recent_files()

    def _on_startup_toggle(self) -> None:
        _recent.set_show_on_startup(self._startup_var.get())

    # ── Tips rotation ─────────────────────────────────────────────────────────

    def _start_tip_rotation(self) -> None:
        self._show_next_tip()

    def _show_next_tip(self) -> None:
        try:
            self._tip_lbl.config(text=next(self._tip_cycle))
        except Exception:
            pass
        self._tip_after_id = self.after(8000, self._show_next_tip)

    def destroy(self) -> None:
        if self._tip_after_id:
            try:
                self.after_cancel(self._tip_after_id)
            except Exception:
                pass
        super().destroy()

    # ── Public ────────────────────────────────────────────────────────────────

    def refresh(self) -> None:
        """Rebuild the recent lists (call when a project/file is opened)."""
        self._populate_recent_projects()
        self._populate_recent_files()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _shorten_path(path: str, max_len: int = 50) -> str:
    try:
        p = Path(path)
        home = Path.home()
        try:
            rel = "~/" + str(p.relative_to(home))
        except ValueError:
            rel = str(p)
        if len(rel) > max_len:
            parts = p.parts
            if len(parts) > 3:
                rel = str(Path(parts[0]) / "..." / parts[-2] / parts[-1])
        return rel
    except Exception:
        return path


def _hover_row(row: tk.Frame, name_lbl: tk.Label, path_lbl: tk.Label, enter: bool) -> None:
    bg = "#2a2d2e" if enter else _BG
    fg = _BLUE_H if enter else _BLUE
    row.config(bg=bg)
    name_lbl.config(bg=bg, fg=fg)
    path_lbl.config(bg=bg)
