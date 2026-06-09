from __future__ import annotations
from utils.ui_font import UI_FONT

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
        self._snap_lbl:    tk.Label | None = None
        self._grid_lbl:    tk.Label | None = None
        self._autogen_lbl: tk.Label | None = None
        self._autogen_after_id: str | None = None

        # Button groups for bulk enable/disable
        self._align_btns: list[tk.Label] = []
        self._dist_btns:  list[tk.Label] = []
        self._size_btns:  list[tk.Label] = []
        self._undo_btn:   tk.Label | None = None
        self._redo_btn:   tk.Label | None = None
        self._copy_btn:   tk.Label | None = None
        self._paste_btn:  tk.Label | None = None

        self._build_ui()
        self.refresh()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        c = self._canvas

        # Alignment cluster
        self._align_btns = [
            self._btn("⬌L", c.align_left,    "Align left edges"),
            self._btn("⬌R", c.align_right,   "Align right edges"),
            self._btn("⬍T", c.align_top,     "Align top edges"),
            self._btn("⬍B", c.align_bottom,  "Align bottom edges"),
            self._btn("⟺H", c.align_center_h, "Center horizontally"),
            self._btn("⟺V", c.align_center_v, "Center vertically"),
        ]

        self._sep()

        # Distribute cluster
        self._dist_btns = [
            self._btn("⇔H", c.distribute_h, "Equal horizontal spacing (≥3)"),
            self._btn("⇕V", c.distribute_v, "Equal vertical spacing (≥3)"),
        ]
        self._grid_btn = self._btn("⊡", self._open_grid_panel, "Grid layout & spacing")

        self._sep()

        # Size cluster
        self._size_btns = [
            self._btn("↔W", c.same_width,  "Match width to primary"),
            self._btn("↕H", c.same_height, "Match height to primary"),
        ]

        self._sep()

        # Snap toggle — always enabled
        self._snap_lbl = self._btn(
            "⊞",
            self._toggle_snap,
            "Snap to grid",
            sticky=True,
        )
        self._refresh_snap()

        # Grid visibility toggle — always enabled
        self._grid_lbl = self._btn(
            "⋯",
            self._toggle_grid,
            "Show/hide grid",
            sticky=True,
        )
        self._refresh_grid()

        # Tab order badge toggle — always enabled
        self._taborder_btn = self._btn(
            "⇥",
            self._toggle_tab_order,
            "Show tab order numbers",
            sticky=True,
        )

        # ── Right-aligned: divider + Undo / Redo / Copy / Paste ──────────────
        self._paste_btn = self._btn("⎘", c.paste,         "Paste  (Ctrl+V)", side="right")
        self._copy_btn  = self._btn("⧉", c.copy_selected, "Copy   (Ctrl+C)", side="right")
        self._redo_btn  = self._btn("↷", c.redo,          "Redo   (Ctrl+Y)", side="right")
        self._undo_btn  = self._btn("↶", c.undo,          "Undo   (Ctrl+Z)", side="right")
        self._sep(side="right")

        # Auto-gen sync indicator — flashes "✓ synced" briefly after each auto-regen
        self._autogen_lbl = tk.Label(
            self, text="", bg=_BG, fg="#4ec9b0",
            font=(UI_FONT, 8), anchor="w",
        )
        self._autogen_lbl.pack(side="left", padx=(8, 2))

    def _btn(
        self,
        text: str,
        cmd: Callable,
        tooltip: str = "",
        sticky: bool = False,
        side: str = "left",
    ) -> tk.Label:
        lbl = tk.Label(
            self,
            text=text,
            bg=_BTN_BG,
            fg=_BTN_FG,
            font=(UI_FONT, 8),
            width=3,
            height=1,
            cursor="hand2",
            relief="flat",
        )
        lbl.pack(side=side, padx=_PAD_X, pady=_PAD_Y)
        lbl._enabled = True   # type: ignore[attr-defined]

        def _enter(_):
            if not lbl._enabled:  # type: ignore[attr-defined]
                return
            lbl.config(bg=_BTN_ACT, fg="#ffffff")

        def _leave(_):
            if not lbl._enabled:  # type: ignore[attr-defined]
                return
            if sticky and getattr(lbl, "_active", False):
                lbl.config(bg=_BTN_ACT, fg=_SNAP_ON)
            else:
                lbl.config(bg=_BTN_BG, fg=_BTN_FG)

        def _click(_):
            if not lbl._enabled:  # type: ignore[attr-defined]
                return
            cmd()
            self.after(10, self.refresh)

        lbl.bind("<Enter>",    _enter)
        lbl.bind("<Leave>",    _leave)
        lbl.bind("<Button-1>", _click)

        if tooltip:
            _add_tooltip(lbl, tooltip)

        return lbl

    def _sep(self, side: str = "left") -> None:
        tk.Frame(self, bg=_SEP_COLOR, width=1).pack(
            side=side, fill="y", padx=4, pady=4
        )

    def flash_autogen(self) -> None:
        """Briefly show a ✓ synced indicator after auto code-gen."""
        if self._autogen_lbl is None:
            return
        if self._autogen_after_id:
            self.after_cancel(self._autogen_after_id)
        self._autogen_lbl.config(text="✓ synced")
        self._autogen_after_id = self.after(
            2000, lambda: self._autogen_lbl.config(text="") if self._autogen_lbl else None
        )

    # ── Enable / disable ──────────────────────────────────────────────────────

    def _set_enabled(self, lbl: tk.Label, enabled: bool) -> None:
        if lbl._enabled == enabled:  # type: ignore[attr-defined]
            return
        lbl._enabled = enabled       # type: ignore[attr-defined]
        if enabled:
            lbl.config(fg=_BTN_FG, cursor="hand2")
        else:
            lbl.config(fg=_BTN_DIS, bg=_BTN_BG, cursor="")

    def refresh(self) -> None:
        """Update every button's enabled state based on current canvas state."""
        c   = self._canvas
        sel = len(c.selected_ids)

        for lbl in self._align_btns:
            self._set_enabled(lbl, sel >= 2)

        for lbl in self._dist_btns:
            self._set_enabled(lbl, sel >= 3)

        if self._canvas.ci_mode:
            ci_count = len(self._canvas.form.widgets) if self._canvas.form else 0
            self._set_enabled(self._grid_btn, ci_count >= 2)
        else:
            self._set_enabled(self._grid_btn, sel >= 2)

        for lbl in self._size_btns:
            self._set_enabled(lbl, sel >= 2)

        if self._undo_btn:
            self._set_enabled(self._undo_btn, c.can_undo)
        if self._redo_btn:
            self._set_enabled(self._redo_btn, c.can_redo)
        if self._copy_btn:
            self._set_enabled(self._copy_btn, sel >= 1)
        if self._paste_btn:
            self._set_enabled(self._paste_btn, c._clipboard is not None)

    # ── Snap toggle ───────────────────────────────────────────────────────────

    def refresh_snap(self) -> None:
        self._refresh_snap()

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

    def _toggle_grid(self) -> None:
        on = self._canvas.toggle_grid()
        if self._grid_lbl is None:
            return
        self._grid_lbl._active = on  # type: ignore[attr-defined]
        self._grid_lbl.config(
            bg=_BTN_ACT if on else _BTN_BG,
            fg=_SNAP_ON  if on else _BTN_FG,
        )

    def _refresh_grid(self) -> None:
        if self._grid_lbl is None:
            return
        on = self._canvas.grid_visible
        self._grid_lbl._active = on  # type: ignore[attr-defined]
        self._grid_lbl.config(
            bg=_BTN_ACT if on else _BTN_BG,
            fg=_SNAP_ON  if on else _BTN_FG,
        )

    def _toggle_tab_order(self) -> None:
        on = self._canvas.toggle_tab_order()
        self._taborder_btn._active = on  # type: ignore[attr-defined]
        self._taborder_btn.config(
            bg=_BTN_ACT if on else _BTN_BG,
            fg=_SNAP_ON  if on else _BTN_FG,
        )

    # ── Grid panel ────────────────────────────────────────────────────────────

    def _open_grid_panel(self) -> None:
        """Toggle the grid layout + spacing popup below the ⊡ button."""
        existing = getattr(self, "_grid_panel_win", None)
        if existing:
            try:
                existing.destroy()
            except Exception:
                pass
            self._grid_panel_win = None
            return

        btn = self._grid_btn
        bx  = btn.winfo_rootx()
        by  = btn.winfo_rooty() + btn.winfo_height() + 2
        c   = self._canvas
        _NUDGE = 8

        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        win.configure(bg=_SEP_COLOR)
        self._grid_panel_win = win

        inner = tk.Frame(win, bg=_BG)
        inner.pack(fill="both", expand=True, padx=1, pady=1)

        def _dismiss():
            try:
                win.destroy()
            except Exception:
                pass
            self._grid_panel_win = None

        def _full_btn(text, cmd):
            lbl = tk.Label(inner, text=text, bg=_BTN_BG, fg=_BTN_FG,
                           font=(UI_FONT, 8), cursor="hand2",
                           padx=6, pady=4, anchor="center")
            lbl.pack(fill="x", padx=4, pady=(4, 2))
            lbl.bind("<Enter>",    lambda e: lbl.config(bg=_BTN_ACT, fg="#ffffff"))
            lbl.bind("<Leave>",    lambda e: lbl.config(bg=_BTN_BG,  fg=_BTN_FG))
            lbl.bind("<Button-1>", lambda e: cmd())

        def _nudge_row(label, fn_minus, fn_plus):
            row = tk.Frame(inner, bg=_BG)
            row.pack(fill="x", padx=4, pady=2)
            tk.Label(row, text=label, bg=_BG, fg="#888888",
                     font=(UI_FONT, 8), width=2, anchor="w").pack(side="left")
            for sym, fn in (("−", fn_minus), ("+", fn_plus)):
                b = tk.Label(row, text=sym, bg=_BTN_BG, fg=_BTN_FG,
                             font=(UI_FONT, 9), width=3, cursor="hand2", relief="flat")
                b.pack(side="left", padx=2)
                b.bind("<Enter>",    lambda e, b=b: b.config(bg=_BTN_ACT, fg="#ffffff"))
                b.bind("<Leave>",    lambda e, b=b: b.config(bg=_BTN_BG,  fg=_BTN_FG))
                b.bind("<Button-1>", lambda e, fn=fn: fn(1 if e.state & 0x1 else _NUDGE))

        # Row / col fields
        rc_frame = tk.Frame(inner, bg=_BG)
        rc_frame.pack(fill="x", padx=4, pady=(4, 0))
        _entry_cfg = dict(bg="#3c3c3c", fg=_BTN_FG, insertbackground=_BTN_FG,
                          relief="flat", highlightthickness=1,
                          highlightbackground=_SEP_COLOR, width=3,
                          font=(UI_FONT, 8))
        tk.Label(rc_frame, text="Rows", bg=_BG, fg="#888888",
                 font=(UI_FONT, 8)).pack(side="left")
        rows_var = tk.StringVar()
        tk.Entry(rc_frame, textvariable=rows_var, **_entry_cfg).pack(
            side="left", padx=(2, 8), ipady=2)
        tk.Label(rc_frame, text="Cols", bg=_BG, fg="#888888",
                 font=(UI_FONT, 8)).pack(side="left")
        cols_var = tk.StringVar()
        tk.Entry(rc_frame, textvariable=cols_var, **_entry_cfg).pack(
            side="left", padx=(2, 0), ipady=2)

        def _do_grid():
            try:    r = int(rows_var.get())
            except: r = None
            try:    co = int(cols_var.get())
            except: co = None
            c.arrange_grid(rows=r, cols=co)
            _dismiss()

        _full_btn("⊡  Make Grid", _do_grid)
        tk.Frame(inner, bg=_SEP_COLOR, height=1).pack(fill="x", padx=4, pady=2)
        _nudge_row("H", lambda d: c.nudge_h(-d), lambda d: c.nudge_h(+d))
        _nudge_row("V", lambda d: c.nudge_v(-d), lambda d: c.nudge_v(+d))
        tk.Frame(inner, bg=_BG, height=4).pack()

        win.geometry(f"+{bx}+{by}")

        top  = self.winfo_toplevel()
        _bid: list = []
        _fid: list = []

        def _global_click(e):
            try:
                px, py = win.winfo_rootx(), win.winfo_rooty()
                pw, ph = win.winfo_width(), win.winfo_height()
                if not (px <= e.x_root < px + pw and py <= e.y_root < py + ph):
                    if _bid:
                        top.unbind("<Button-1>", _bid.pop())
                    if _fid:
                        top.unbind("<FocusOut>", _fid.pop())
                    _dismiss()
            except Exception:
                pass

        def _on_focus_out(e):
            if e.widget is top:
                def _check_dismiss():
                    try:
                        # If focus is now inside the popup, keep it open
                        if win.winfo_exists() and win.focus_get() is not None:
                            return
                    except Exception:
                        pass
                    if _bid:
                        try: top.unbind("<Button-1>", _bid.pop())
                        except Exception: pass
                    if _fid:
                        try: top.unbind("<FocusOut>", _fid.pop())
                        except Exception: pass
                    _dismiss()
                top.after(60, _check_dismiss)

        def _on_destroy(e):
            if _bid:
                try:
                    top.unbind("<Button-1>", _bid.pop())
                except Exception:
                    pass
            if _fid:
                try:
                    top.unbind("<FocusOut>", _fid.pop())
                except Exception:
                    pass

        _bid.append(top.bind("<Button-1>", _global_click, add=True))
        _fid.append(top.bind("<FocusOut>", _on_focus_out, add=True))
        win.bind("<Destroy>", _on_destroy)


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
                font=(UI_FONT, 8),
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
