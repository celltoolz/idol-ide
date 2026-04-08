"""GuideWindow — reusable paginated learning/guide Toplevel.

Content is provided as a list of GuidePage dataclasses. The window is
completely content-agnostic; callers own the page data.
"""
from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass, field
from tkinter import Frame, Label, ttk
from typing import Callable

_BG      = "#252526"
_HDR_BG  = "#2d2d30"
_FG      = "#cccccc"
_DIM     = "#858585"
_BTN_BG  = "#0e639c"
_BTN_ACT = "#1177bb"


@dataclass
class GuidePage:
    """One page of a GuideWindow.

    sections: list of (label, body, color) tuples — label is the section
    heading, body is the paragraph text, color is the heading foreground.
    action_label / action_fn: optional button shown at the bottom of the page;
    clicking it runs action_fn then closes the window.
    """
    title:        str
    subtitle:     str = ""
    sections:     list[tuple[str, str, str]] = field(default_factory=list)
    action_label: str = ""
    action_fn:    Callable | None = field(default=None, repr=False)


class GuideWindow(tk.Toplevel):
    """Paginated read-through guide window.

    Pass any list of GuidePage objects. Navigation is Previous / Next / Close.
    Works on Windows, Linux, and macOS (uses Labels instead of Buttons).
    """

    def __init__(self, parent, title: str, pages: list[GuidePage],
                 width: int = 380, height: int = 420) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.attributes("-topmost", True)

        # Position beside the parent widget
        parent.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() + 10
        py = parent.winfo_rooty()
        self.geometry(f"{width}x{height}+{px}+{py}")

        self._pages = pages
        self._idx   = 0

        # ── Header ────────────────────────────────────────────────────────────
        hdr = Frame(self, bg=_HDR_BG, pady=8)
        hdr.pack(fill="x")
        self._title_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_FG,
                                font=("Segoe UI", 10, "bold"), padx=12)
        self._title_lbl.pack(anchor="w")
        self._sub_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_DIM,
                              font=("Segoe UI", 8), padx=12)
        self._sub_lbl.pack(anchor="w")

        # ── Navigation bar — packed before content so it's always visible ─────
        nav = Frame(self, bg=_HDR_BG, pady=6)
        nav.pack(fill="x", side="bottom")

        self._prev_btn = self._make_nav_btn(nav, "← Previous", lambda: self._go(-1))
        self._prev_btn.pack(side="left", padx=6)
        self._next_btn = self._make_nav_btn(nav, "Next →", lambda: self._go(1))
        self._next_btn.pack(side="left")
        self._make_nav_btn(nav, "Close", self._on_close).pack(side="right", padx=6)

        # ── Scrollable content area ───────────────────────────────────────────
        scroll_outer = Frame(self, bg=_BG)
        scroll_outer.pack(fill="both", expand=True)

        # Scrollbar first so canvas doesn't overlap it
        self._vs = ttk.Scrollbar(scroll_outer, orient="vertical")
        self._vs.pack(side="right", fill="y")

        self._canvas = tk.Canvas(scroll_outer, bg=_BG, highlightthickness=0, bd=0,
                                 yscrollcommand=self._vs.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._vs.config(command=self._canvas.yview)

        self._content = Frame(self._canvas, bg=_BG, padx=12, pady=8)
        self._content_window = self._canvas.create_window(
            (0, 0), window=self._content, anchor="nw"
        )

        self._content.bind("<Configure>", self._on_content_configure)
        self._canvas.bind("<Configure>",  self._on_canvas_configure)

        # Wheel on every widget inside this window only
        self._wheel_binds: list[str] = []
        for seq in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            bid = self.bind(seq, self._on_wheel, add=True)
            self._wheel_binds.append((seq, bid))

        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self._load(0)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _make_nav_btn(self, parent, text: str, command: Callable) -> Label:
        lbl = Label(parent, text=text, bg=_HDR_BG, fg=_FG,
                    font=("Segoe UI", 9), cursor="hand2", padx=10, pady=2)
        lbl.bind("<Button-1>", lambda _: command())
        lbl.bind("<Enter>", lambda _: lbl.config(fg="#ffffff") if lbl["cursor"] == "hand2" else None)
        lbl.bind("<Leave>", lambda _: lbl.config(fg=_FG) if lbl["cursor"] == "hand2" else None)
        return lbl

    def _on_close(self) -> None:
        self.destroy()

    def _on_content_configure(self, _) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfigure(self._content_window, width=event.width)

    def _on_wheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")

    def _set_nav_enabled(self, lbl: Label, enabled: bool) -> None:
        lbl.config(fg=_FG if enabled else _DIM,
                   cursor="hand2" if enabled else "")

    def _go(self, delta: int) -> None:
        new = self._idx + delta
        if 0 <= new < len(self._pages):
            self._load(new)

    def _load(self, idx: int) -> None:
        self._idx = idx
        page      = self._pages[idx]
        n         = len(self._pages)

        self._title_lbl.config(text=page.title)
        step = f"Step {idx + 1} of {n}" if n > 1 else ""
        sub  = f"{page.subtitle}  ·  {step}" if page.subtitle and step else (page.subtitle or step)
        self._sub_lbl.config(text=sub)

        for w in self._content.winfo_children():
            w.destroy()
        self._canvas.yview_moveto(0)

        for label, body, color in page.sections:
            Label(self._content, text=label, bg=_BG, fg=color,
                  font=("Segoe UI", 8, "bold"), anchor="w").pack(fill="x", pady=(6, 0))
            Label(self._content, text=body, bg=_BG, fg=_FG,
                  font=("Segoe UI", 9), anchor="w", justify="left",
                  wraplength=340).pack(fill="x")

        if page.action_fn and page.action_label:
            def _do(fn=page.action_fn):
                fn()
                self._on_close()
            btn = Label(self._content, text=page.action_label,
                        bg=_BTN_BG, fg="white",
                        font=("Segoe UI", 9, "bold"),
                        cursor="hand2", padx=10, pady=4)
            btn.bind("<Button-1>", lambda _, f=_do: f())
            btn.bind("<Enter>", lambda _, b=btn: b.config(bg=_BTN_ACT))
            btn.bind("<Leave>", lambda _, b=btn: b.config(bg=_BTN_BG))
            btn.pack(anchor="w", pady=(12, 0))

        self._set_nav_enabled(self._prev_btn, idx > 0)
        self._set_nav_enabled(self._next_btn, idx < n - 1)

        # Bind wheel to all current children so it works over labels too
        for w in self._content.winfo_children():
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)
