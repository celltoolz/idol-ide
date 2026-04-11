"""Learning Mode panel — displays contextual help for hovered IDE elements."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from utils.learning_registry import REGISTRY


_BG        = "#1e1e1e"
_HEADER_BG = "#252526"
_TITLE_FG  = "#569cd6"   # blue — matches function color in most themes
_SECTION_FG = "#c586c0"  # purple — stands out as a label
_BODY_FG   = "#cccccc"
_DIM_FG    = "#858585"
_ACCENT    = "#4ec9b0"   # teal for example block

_WELCOME_ID = "__welcome__"

REGISTRY[_WELCOME_ID] = {
    "title": "IDOL Learning Mode",
    "what": (
        "Learning Mode is active. Hover over any part of the IDE — "
        "panels, buttons, the editor, status bar — and this panel will explain what it does."
    ),
    "how": (
        "Each explanation has three sections:\n"
        "  WHAT IT IS — a plain-English description\n"
        "  HOW IT WORKS — the mechanics behind it\n"
        "  REAL-WORLD EXAMPLE — how you'd actually use it"
    ),
    "example": (
        "Try hovering the Outline panel on the left, the Commit button, "
        "or the branch name in the status bar."
    ),
}


class LearningPanel(tk.Frame):
    """Scrollable panel that displays what/how/example for a hovered widget."""

    def __init__(self, parent, **kwargs) -> None:
        super().__init__(parent, bg=_BG, **kwargs)
        self._build()
        self.show(_WELCOME_ID)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build(self) -> None:
        # Scrollable canvas
        self._canvas = tk.Canvas(self, bg=_BG, highlightthickness=0, bd=0)
        self._sb = ttk.Scrollbar(self, orient="vertical", command=self._canvas.yview)
        self._canvas.configure(yscrollcommand=self._sb.set)

        self._sb.pack(side="right", fill="y")
        self._canvas.pack(side="left", fill="both", expand=True)

        self._inner = tk.Frame(self._canvas, bg=_BG)
        self._win = self._canvas.create_window((0, 0), window=self._inner,
                                               anchor="nw")

        self._inner.bind("<Configure>", self._on_inner_configure)
        self._canvas.bind("<Configure>", self._on_canvas_configure)
        self._canvas.bind("<MouseWheel>", self._on_mousewheel)
        self._canvas.bind("<Button-4>",   self._on_mousewheel)
        self._canvas.bind("<Button-5>",   self._on_mousewheel)

    def _on_inner_configure(self, _=None) -> None:
        self._canvas.configure(scrollregion=self._canvas.bbox("all"))

    def _on_canvas_configure(self, event) -> None:
        self._canvas.itemconfig(self._win, width=event.width)

    def _on_mousewheel(self, event) -> None:
        if event.num == 4:
            self._canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self._canvas.yview_scroll(1, "units")
        else:
            self._canvas.yview_scroll(int(-event.delta / 120), "units")

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, lid: str) -> None:
        """Populate the panel with content for *lid*."""
        payload = REGISTRY.get(lid) or REGISTRY.get(_WELCOME_ID)
        self._render(payload)

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, payload: dict) -> None:
        # Clear previous content
        for child in self._inner.winfo_children():
            child.destroy()

        pad = {"padx": 14, "pady": 0}

        # ── Title ─────────────────────────────────────────────────────────────
        tk.Frame(self._inner, bg=_BG, height=12).pack(fill="x")

        tk.Label(
            self._inner,
            text=f"📖  {payload['title']}",
            bg=_BG, fg=_TITLE_FG,
            font=("Segoe UI", 11, "bold"),
            anchor="w", wraplength=0,
            justify="left",
        ).pack(fill="x", **pad)

        tk.Frame(self._inner, bg="#3c3c3c", height=1).pack(fill="x", padx=14, pady=(8, 0))

        # ── Sections ──────────────────────────────────────────────────────────
        sections = [
            ("WHAT IT IS",         payload.get("what", ""),    _BODY_FG,  _HEADER_BG),
            ("HOW IT WORKS",       payload.get("how", ""),     _BODY_FG,  _HEADER_BG),
            ("REAL-WORLD EXAMPLE", payload.get("example", ""), _ACCENT,   "#1a2a2a"),
        ]

        for header, body, fg, bg_block in sections:
            if not body:
                continue

            tk.Frame(self._inner, bg=_BG, height=10).pack(fill="x")

            # Section header
            tk.Label(
                self._inner,
                text=header,
                bg=_BG, fg=_SECTION_FG,
                font=("Segoe UI", 8, "bold"),
                anchor="w",
            ).pack(fill="x", **pad)

            tk.Frame(self._inner, bg=_BG, height=4).pack(fill="x")

            # Body block
            block = tk.Frame(self._inner, bg=bg_block, padx=10, pady=8)
            block.pack(fill="x", padx=14)

            tk.Label(
                block,
                text=body,
                bg=bg_block, fg=fg,
                font=("Segoe UI", 9),
                anchor="nw",
                justify="left",
                wraplength=220,
            ).pack(fill="x", anchor="w")

        tk.Frame(self._inner, bg=_BG, height=16).pack(fill="x")

        # Reset scroll to top
        self._canvas.yview_moveto(0)

    def apply_theme(self, bg: str, fg: str, _select_bg: str) -> None:
        """Minimal theme hook — panel uses fixed dark colors by design."""
        pass
