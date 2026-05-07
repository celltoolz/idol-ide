from __future__ import annotations

"""
DesignerToolbar — horizontal strip above the design canvas.

Groups:
  Alignment  — Align Left/Right/Top/Bottom, Center H/V
  Distribute — Equal H/V spacing (requires ≥3 widgets)
  Size       — Same Width / Same Height
  Snap       — Snap-to-grid toggle
"""

import tkinter as tk
from typing import TYPE_CHECKING, Callable, Optional

if TYPE_CHECKING:
    from designer.canvas import DesignerCanvas


_BG        = "#2d2d2d"
_BTN_BG    = "#3c3c3c"
_BTN_ACT   = "#094771"
_BTN_FG    = "#cccccc"
_BTN_DIS   = "#555555"
_SEP_COLOR = "#555555"
_SNAP_ON   = "#569cd6"   # active snap indicator color
_BTN_W     = 24
_BTN_H     = 22
_PAD_X     = 2
_PAD_Y     = 3


class DesignerToolbar(tk.Frame):
    """Thin toolbar strip that wraps DesignerCanvas alignment/snap methods."""

    def __init__(
        self,
        master,
        canvas: "DesignerCanvas",
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, height=28, **kwargs)
        self.pack_propagate(False)
        self._canvas = canvas
        self._snap_lbl: tk.Label | None = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c = self._canvas

        # Alignment cluster
        self._btn("⬌L", c.align_left,    "Align left edges")
        self._btn("⬌R", c.align_right,   "Align right edges")
        self._btn("⬍T", c.align_top,     "Align top edges")
        self._btn("⬍B", c.align_bottom,  "Align bottom edges")
        self._btn("⟺H", c.align_center_h, "Center horizontally")
        self._btn("⟺V", c.align_center_v, "Center vertically")

        self._sep()

        # Distribute cluster
        self._btn("⇔H", c.distribute_h, "Equal horizontal spacing (≥3)")
        self._btn("⇕V", c.distribute_v, "Equal vertical spacing (≥3)")

        self._sep()

        # Size cluster
        self._btn("↔W", c.same_width,  "Match width to primary")
        self._btn("↕H", c.same_height, "Match height to primary")

        self._sep()

        # Snap toggle
        self._snap_lbl = self._btn(
            "⊞",
            self._toggle_snap,
            "Snap to grid",
            sticky=True,
        )
        self._refresh_snap()

    def _btn(
        self,
        text: str,
        cmd: Callable,
        tooltip: str = "",
        sticky: bool = False,
    ) -> tk.Label:
        lbl = tk.Label(
            self,
            text=text,
            bg=_BTN_BG,
            fg=_BTN_FG,
            font=("Segoe UI", 8),
            width=3,
            height=1,
            cursor="hand2",
            relief="flat",
        )
        lbl.pack(side="left", padx=_PAD_X, pady=_PAD_Y)

        def _enter(_):
            lbl.config(bg=_BTN_ACT, fg="#ffffff")

        def _leave(_):
            if sticky and getattr(lbl, "_active", False):
                lbl.config(bg=_BTN_ACT, fg=_SNAP_ON)
            else:
                lbl.config(bg=_BTN_BG, fg=_BTN_FG)

        def _click(_):
            cmd()

        lbl.bind("<Enter>",    _enter)
        lbl.bind("<Leave>",    _leave)
        lbl.bind("<Button-1>", _click)

        if tooltip:
            _add_tooltip(lbl, tooltip)

        return lbl

    def _sep(self) -> None:
        tk.Frame(self, bg=_SEP_COLOR, width=1).pack(
            side="left", fill="y", padx=4, pady=4
        )

    # ── Snap toggle ───────────────────────────────────────────────────────────

    def _toggle_snap(self) -> None:
        self._canvas.toggle_snap()
        self._refresh_snap()

    def _refresh_snap(self) -> None:
        if self._snap_lbl is None:
            return
        on = self._canvas.snap_enabled
        self._snap_lbl._active = on  # type: ignore[attr-defined]
        self._snap_lbl.config(
            bg=_BTN_ACT if on else _BTN_BG,
            fg=_SNAP_ON  if on else _BTN_FG,
        )


# ── Tooltip helper ────────────────────────────────────────────────────────────

def _add_tooltip(widget: tk.Widget, text: str, delay: int = 500) -> None:
    _after = [None]
    _win   = [None]

    def _show(_):
        if _win[0]:
            return
        def _create():
            _win[0] = None
            x = widget.winfo_rootx() + widget.winfo_width() // 2
            y = widget.winfo_rooty() + widget.winfo_height() + 4
            tip = tk.Toplevel(widget)
            tip.wm_overrideredirect(True)
            tip.wm_geometry(f"+{x}+{y}")
            tk.Label(
                tip, text=text,
                bg="#2d2d2d", fg="#cccccc",
                font=("Segoe UI", 8),
                relief="solid", bd=1, padx=4, pady=2,
            ).pack()
            _win[0] = tip
        _after[0] = widget.after(delay, _create)

    def _hide(_):
        if _after[0]:
            widget.after_cancel(_after[0])
            _after[0] = None
        if _win[0]:
            try:
                _win[0].destroy()
            except Exception:
                pass
            _win[0] = None

    widget.bind("<Enter>", _show, add=True)
    widget.bind("<Leave>", _hide, add=True)
