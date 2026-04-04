"""SourceControlPanel — Git Stage/Unstage/Commit/Push/Pull sidebar panel."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import Frame, Label, Button, Menu, ttk
from typing import Callable


_BG       = "#252526"
_ITEM_BG  = "#1e1e1e"
_HOV_BG   = "#2a2d2e"
_HDR_BG   = "#2d2d30"
_FG       = "#cccccc"
_DIM      = "#858585"
_BTN_BG   = "#0e639c"
_BTN_ACT  = "#1177bb"

STATUS_COLORS = {
    "M": "#e2c08d",
    "A": "#73c991",
    "U": "#cccccc",
    "D": "#f14c4c",
}
STATUS_LABELS = {"M": "M", "A": "A", "U": "U", "D": "D"}


class _FileRow(Frame):
    """A single file entry row with hover highlight."""

    def __init__(self, parent, path: str, status: str,
                 on_click: Callable, on_right_click: Callable,
                 bg: str = _ITEM_BG) -> None:
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg
        color = STATUS_COLORS.get(status, _FG)
        name = os.path.basename(path)

        lbl = Label(self, text=f"  {name}", bg=bg, fg=color,
                    font=("Segoe UI", 9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        Label(self, text=f" {status} ", bg=bg, fg=color,
              font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 4))

        for w in (self, lbl):
            w.bind("<Enter>",          lambda _: self._hover(True))
            w.bind("<Leave>",          lambda _: self._hover(False))
            w.bind("<Double-Button-1>",lambda _, p=path: on_click(p))
            w.bind("<Button-3>",       lambda e, p=path: on_right_click(e, p))

    def _hover(self, on: bool) -> None:
        c = _HOV_BG if on else self._bg
        self.config(bg=c)
        for w in self.winfo_children():
            w.config(bg=c)


class _Section(Frame):
    """Collapsible section header + file list."""

    def __init__(self, parent, title: str, bg: str = _BG) -> None:
        super().__init__(parent, bg=bg)
        self._collapsed = False
        self._bg = bg

        # Header
        hdr = Frame(self, bg=_HDR_BG, height=24)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._arrow = Label(hdr, text="▾", bg=_HDR_BG, fg=_FG,
                            font=("Segoe UI", 8))
        self._arrow.pack(side="left", padx=(4, 0))

        Label(hdr, text=title, bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)

        self._count_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_DIM,
                                font=("Segoe UI", 8), padx=6)
        self._count_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle())
        hdr.bind("<Button-1>", lambda _: self._toggle())

        # Body
        self._body = Frame(self, bg=_ITEM_BG)
        self._body.pack(fill="x")

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._arrow.config(text="▸" if self._collapsed else "▾")
        if self._collapsed:
            self._body.pack_forget()
        else:
            self._body.pack(fill="x")

    def set_count(self, n: int) -> None:
        self._count_lbl.config(text=f"({n})" if n else "")

    def populate(self, items: dict[str, str],
                 on_click: Callable, on_right_click: Callable) -> None:
        for w in self._body.winfo_children():
            w.destroy()
        for path, status in items.items():
            row = _FileRow(self._body, path, status, on_click, on_right_click,
                           bg=_ITEM_BG)
            row.pack(fill="x")
        self.set_count(len(items))

    def apply_theme(self, bg: str, fg: str) -> None:
        self._bg = bg
        self.config(bg=bg)
        self._body.config(bg=bg)


class SourceControlPanel(ttk.Frame):
    """Git source control panel: staged / unstaged file lists + commit UI."""

    def __init__(
        self,
        parent,
        on_stage:   Callable[[str], None],
        on_unstage: Callable[[str], None],
        on_discard: Callable[[str], None],
        on_commit:  Callable[[str], None],
        on_push:    Callable[[], None],
        on_pull:    Callable[[], None],
        on_diff:    Callable[[str], None],
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_stage   = on_stage
        self._on_unstage = on_unstage
        self._on_discard = on_discard
        self._on_commit  = on_commit
        self._on_push    = on_push
        self._on_pull    = on_pull
        self._on_diff    = on_diff
        self._ctx_path   = ""

        ttk.Style().configure("SC.TFrame", background=_BG)
        self.configure(style="SC.TFrame")

        self._build_commit_area()
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._staged_sec   = _Section(self, "STAGED CHANGES")
        self._staged_sec.pack(fill="x")
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._unstaged_sec = _Section(self, "CHANGES")
        self._unstaged_sec.pack(fill="x")

        # Context menus
        self._staged_menu = Menu(self, tearoff=0)
        self._staged_menu.add_command(label="Unstage Changes",
                                      command=self._ctx_do_unstage)
        self._staged_menu.add_command(label="Open Diff",
                                      command=self._ctx_do_diff)

        self._changes_menu = Menu(self, tearoff=0)
        self._changes_menu.add_command(label="Stage Changes",
                                       command=self._ctx_do_stage)
        self._changes_menu.add_command(label="Discard Changes",
                                       command=self._ctx_do_discard)
        self._changes_menu.add_command(label="Open Diff",
                                       command=self._ctx_do_diff)

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, staged: dict[str, str], unstaged: dict[str, str]) -> None:
        """Re-populate both file lists."""
        self._staged_sec.populate(
            staged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "staged"),
        )
        self._unstaged_sec.populate(
            unstaged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "changes"),
        )

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        ttk.Style().configure("SC.TFrame", background=bg)
        self._staged_sec.apply_theme(bg, fg)
        self._unstaged_sec.apply_theme(bg, fg)

    # ── Commit area ───────────────────────────────────────────────────────────

    def _build_commit_area(self) -> None:
        outer = Frame(self, bg=_BG, padx=6, pady=6)
        outer.pack(fill="x")

        # Placeholder-style Text widget for commit message
        self._msg = tk.Text(
            outer,
            height=3,
            bg="#3c3c3c",
            fg=_DIM,
            insertbackground=_FG,
            font=("Segoe UI", 9),
            relief="flat",
            padx=6,
            pady=4,
            wrap="word",
        )
        self._msg.insert("1.0", "Commit message…")
        self._msg.pack(fill="x")
        self._msg.bind("<FocusIn>",  self._msg_focus_in)
        self._msg.bind("<FocusOut>", self._msg_focus_out)
        self._placeholder_active = True

        # Buttons row
        btn_row = Frame(outer, bg=_BG)
        btn_row.pack(fill="x", pady=(5, 0))

        _kw = dict(
            bg=_BTN_BG, fg="white",
            activebackground=_BTN_ACT, activeforeground="white",
            relief="flat", font=("Segoe UI", 8, "bold"),
            cursor="hand2", padx=8, pady=3, bd=0,
        )
        Button(btn_row, text="✓ Commit",
               command=self._do_commit, **_kw).pack(side="left")
        Button(btn_row, text="↑ Push",
               command=self._on_push,  **_kw).pack(side="left", padx=(4, 0))
        Button(btn_row, text="↓ Pull",
               command=self._on_pull,  **_kw).pack(side="left", padx=(4, 0))

    def _msg_focus_in(self, _) -> None:
        if self._placeholder_active:
            self._msg.delete("1.0", "end")
            self._msg.config(fg=_FG)
            self._placeholder_active = False

    def _msg_focus_out(self, _) -> None:
        if not self._msg.get("1.0", "end-1c").strip():
            self._msg.delete("1.0", "end")
            self._msg.insert("1.0", "Commit message…")
            self._msg.config(fg=_DIM)
            self._placeholder_active = True

    def _do_commit(self) -> None:
        msg = self._msg.get("1.0", "end-1c").strip()
        if not msg or self._placeholder_active:
            return
        self._on_commit(msg)
        # Clear message field after commit
        self._msg.delete("1.0", "end")
        self._msg.insert("1.0", "Commit message…")
        self._msg.config(fg=_DIM)
        self._placeholder_active = True

    # ── Context menu helpers ──────────────────────────────────────────────────

    def _show_ctx(self, event, path: str, section: str) -> None:
        self._ctx_path = path
        menu = self._staged_menu if section == "staged" else self._changes_menu
        menu.tk_popup(event.x_root, event.y_root)

    def _ctx_do_stage(self)   -> None: self._on_stage(self._ctx_path)
    def _ctx_do_unstage(self) -> None: self._on_unstage(self._ctx_path)
    def _ctx_do_discard(self) -> None: self._on_discard(self._ctx_path)
    def _ctx_do_diff(self)    -> None: self._on_diff(self._ctx_path)
