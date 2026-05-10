"""StyledCheckbox — Unicode-based checkbox widget, consistent with ProjectWizard style."""
from __future__ import annotations
import tkinter as tk
from utils.ui_font import UI_FONT


class StyledCheckbox(tk.Frame):
    """A label-based checkbox using ☑/☐ glyphs.

    Works identically on Windows, macOS, and Linux — no native Checkbutton quirks.
    """

    def __init__(
        self,
        parent,
        text: str,
        variable: tk.BooleanVar,
        *,
        bg: str,
        fg: str = "#cccccc",
        dim: str = "#858585",
        checked_color: str = "#569cd6",
        font_size: int = 9,
        box_font_size: int = 11,
        disabled: bool = False,
        **kw,
    ) -> None:
        cursor = "" if disabled else "hand2"
        super().__init__(parent, bg=bg, cursor=cursor, **kw)

        self._var = variable
        self._disabled = disabled
        self._dim = dim
        self._checked_color = checked_color

        self._box = tk.Label(self, bg=bg, font=(UI_FONT, box_font_size), cursor=cursor)
        self._box.pack(side="left", padx=(0, 4))

        self._lbl = tk.Label(
            self, text=text, bg=bg,
            fg=dim if disabled else fg,
            font=(UI_FONT, font_size), cursor=cursor,
        )
        self._lbl.pack(side="left")

        self._refresh()
        if not disabled:
            for w in (self, self._box, self._lbl):
                w.bind("<Button-1>", self._toggle)

    def _refresh(self, *_) -> None:
        if self._disabled:
            self._box.config(text="☐", fg=self._dim)
        else:
            checked = self._var.get()
            self._box.config(
                text="☑" if checked else "☐",
                fg=self._checked_color if checked else self._dim,
            )

    def _toggle(self, _=None) -> None:
        self._var.set(not self._var.get())
        self._refresh()
