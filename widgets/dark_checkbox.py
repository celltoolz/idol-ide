"""Canvas-drawn checkbox for IDOL's dark dialogs.

`tk.Checkbutton` is not used anywhere in IDOL: it takes its colours from the
platform and renders as a light control sitting in a dark panel on Linux and
Windows alike, with no reliable way to restyle the indicator. Drawing the box
ourselves is the only way to get one appearance everywhere.

Promoted here from `designer/menu_editor.py`, which had the only copy. A second
copy in the font chooser would have been the third time in this codebase that
two versions of the same thing drifted apart.
"""
from __future__ import annotations

import tkinter as tk

from utils.ui_font import UI_FONT

_BOX = 12               # box side, px
_CHECK_BG = "#007acc"   # filled when checked
_CHECK_FG = "#ffffff"   # the tick
_EMPTY_OUTLINE = "#555555"


class DarkCheckbox(tk.Frame):
    """Drop-in for `tk.Checkbutton` — takes `variable`, `text`, `command`.

    Colours default to the dark-dialog palette; pass `bg`/`fg` to match a panel
    with a different background.
    """

    def __init__(self, master, text: str = "",
                 variable: tk.BooleanVar | None = None,
                 command=None, bg: str = "#252526", fg: str = "#cccccc",
                 fg_dim: str = "#5a5a5a", **kwargs) -> None:
        super().__init__(master, bg=bg, cursor="hand2", **kwargs)
        self._var = variable if variable is not None else tk.BooleanVar(value=False)
        self._cmd = command
        self._bg = bg
        self._fg = fg
        self._fg_dim = fg_dim
        self._enabled = True

        self._cv = tk.Canvas(self, width=_BOX, height=_BOX, bg=bg,
                             highlightthickness=0)
        self._cv.pack(side="left", padx=(0, 5))
        self._lbl = tk.Label(self, text=text, bg=bg, fg=fg,
                             font=(UI_FONT, 9), cursor="hand2")
        self._lbl.pack(side="left")

        self._draw()
        self._var.trace_add("write", lambda *_: self._draw())
        for w in (self, self._cv, self._lbl):
            w.bind("<Button-1>", self._toggle)

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def variable(self) -> tk.BooleanVar:
        return self._var

    def get(self) -> bool:
        return bool(self._var.get())

    def set(self, value: bool) -> None:
        self._var.set(bool(value))

    def set_enabled(self, enabled: bool) -> None:
        """Grey out and stop responding, without hiding the control."""
        self._enabled = enabled
        self._lbl.config(fg=self._fg if enabled else self._fg_dim,
                         cursor="hand2" if enabled else "")
        self.config(cursor="hand2" if enabled else "")
        self._draw()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        self._cv.delete("all")
        if self._var.get():
            fill = _CHECK_BG if self._enabled else "#3d3d3d"
            self._cv.create_rectangle(0, 0, _BOX, _BOX, fill=fill, outline=fill)
            self._cv.create_text(_BOX // 2, _BOX // 2, text="✓",
                                 fill=_CHECK_FG if self._enabled else "#7a7a7a",
                                 font=(UI_FONT, 7, "bold"))
        else:
            self._cv.create_rectangle(
                0, 0, _BOX, _BOX, fill="",
                outline=_EMPTY_OUTLINE if self._enabled else "#3d3d3d")

    def _toggle(self, _event=None) -> None:
        if not self._enabled:
            return
        self._var.set(not self._var.get())
        if self._cmd:
            self._cmd()
