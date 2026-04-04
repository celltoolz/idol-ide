from __future__ import annotations

from tkinter import ttk
from typing import Callable, Optional


class StatusBar(ttk.Frame):
    """VS Code-style status bar: Ln/Col | Lexer | Encoding | Spaces.

    The indent indicator is clickable — it cycles through 2 / 4 / 8 spaces
    and fires *on_indent_change(size)* so the app can update the active editor.
    """

    _INDENT_CYCLE = [2, 4, 8]

    def __init__(
        self,
        master,
        on_indent_change: Optional[Callable[[int], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_indent_change = on_indent_change
        self._indent_size = 4
        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("SB.TFrame",        background="#1e1e1e")
        style.configure("SB.TLabel",        background="#1e1e1e", foreground="#858585",
                        font=("TkDefaultFont", 8))
        style.configure("SB.Hi.TLabel",     background="#1e1e1e", foreground="#cccccc",
                        font=("TkDefaultFont", 8))

        self.configure(style="SB.TFrame")

        # Top border
        ttk.Separator(self, orient="horizontal").pack(fill="x", side="top")

        # ── Right side (packed right-to-left) ─────────────────────────────────
        self._indent_lbl = ttk.Label(self, style="SB.Hi.TLabel", cursor="hand2")
        self._indent_lbl.pack(side="right", padx=(2, 10), pady=2)
        self._indent_lbl.bind("<Button-1>", self._on_indent_click)
        self._vsep()

        self._encoding_lbl = ttk.Label(self, text="UTF-8", style="SB.TLabel")
        self._encoding_lbl.pack(side="right", padx=(2, 8), pady=2)
        self._vsep()

        self._lexer_lbl = ttk.Label(self, text="", style="SB.Hi.TLabel")
        self._lexer_lbl.pack(side="right", padx=(2, 8), pady=2)
        self._vsep()

        # ── Left side ─────────────────────────────────────────────────────────
        self._pos_lbl = ttk.Label(self, text="Ln 1, Col 1", style="SB.TLabel")
        self._pos_lbl.pack(side="left", padx=(10, 2), pady=2)

        self._refresh_indent_label()

    def _vsep(self) -> None:
        ttk.Separator(self, orient="vertical").pack(side="right", fill="y", padx=4, pady=3)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_position(self, line: int, col: int, cursors: int = 1) -> None:
        pos = f"Ln {line}, Col {col + 1}"
        if cursors > 1:
            pos += f"  |  {cursors} cursors"
        self._pos_lbl.config(text=pos)

    def set_lexer(self, name: str) -> None:
        self._lexer_lbl.config(text=name)

    def set_indent(self, size: int) -> None:
        self._indent_size = size
        self._refresh_indent_label()

    @property
    def indent_size(self) -> int:
        return self._indent_size

    # ── Internals ─────────────────────────────────────────────────────────────

    def _refresh_indent_label(self) -> None:
        self._indent_lbl.config(text=f"Spaces: {self._indent_size}")

    def _on_indent_click(self, _) -> None:
        try:
            idx = self._INDENT_CYCLE.index(self._indent_size)
        except ValueError:
            idx = 0
        self._indent_size = self._INDENT_CYCLE[(idx + 1) % len(self._INDENT_CYCLE)]
        self._refresh_indent_label()
        if self._on_indent_change:
            self._on_indent_change(self._indent_size)
