from __future__ import annotations

import tkinter as tk
from typing import Callable

from utils.ui_font import UI_FONT

_BG   = "#252526"
_ROW  = "#2d2d30"
_HOV  = "#3e3e42"
_SEL  = "#094771"
_FG   = "#cccccc"
_DIM  = "#858585"
_CODE = "#ce9178"   # warm orange for code previews

_ROW_H = 38


class HandlerOptionsEditor(tk.Toplevel):
    """Pick one named option for a handler stub or connected-wire body.

    is_wire=False → edits form.handler_options (controls the handler stub body).
    is_wire=True  → edits a HandlerWire.option (controls the widget-event body).
    """

    def __init__(
        self,
        parent: tk.Misc,
        handler_id: str,
        hdef,
        is_wire: bool,
        current_option: str,
        on_apply: Callable[[str], None],
    ) -> None:
        super().__init__(parent)
        self._on_apply   = on_apply
        self._options    = list(hdef.options)
        bodies           = hdef.wire_option_bodies if is_wire else hdef.stub_option_bodies
        self._bodies     = list(bodies)
        self._selected   = (current_option if current_option in self._options
                            else (self._options[0] if self._options else ""))
        self._hov_idx:   int | None = None

        self.title(f"Options — {handler_id}")
        self.resizable(False, False)
        self.configure(bg=_BG)
        self.transient(parent)
        self.grab_set()

        target_label = "widget event body" if is_wire else "stub body"
        tk.Label(
            self, text=f"Choose {target_label}:",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8), anchor="w",
        ).pack(padx=12, pady=(10, 4), fill="x")

        # Option rows on a canvas so we get full-row hit areas
        total_h = len(self._options) * _ROW_H
        self._cv = tk.Canvas(
            self, bg=_BG, highlightthickness=0,
            width=400, height=max(total_h, _ROW_H),
        )
        self._cv.pack(fill="x", padx=8)
        self._cv.bind("<Configure>",       lambda _: self._draw())
        self._cv.bind("<ButtonRelease-1>", self._on_click)
        self._cv.bind("<Motion>",          self._on_motion)
        self._cv.bind("<Leave>",           self._on_leave)

        # Separator
        tk.Frame(self, bg="#3a3a3a", height=1).pack(fill="x", padx=8, pady=(6, 0))

        # Button row
        btn_row = tk.Frame(self, bg=_BG)
        btn_row.pack(fill="x", padx=12, pady=(8, 10))
        for text, cmd in [("Apply", self._commit), ("Cancel", self.destroy)]:
            is_primary = text == "Apply"
            lbl = tk.Label(
                btn_row, text=text,
                bg="#094771" if is_primary else "#3c3c3c",
                fg="#ffffff",
                font=(UI_FONT, 9), padx=10, pady=3, cursor="hand2",
            )
            lbl.pack(side="right", padx=(6, 0))
            on_bg  = "#0e6898" if is_primary else "#4c4c4c"
            off_bg = "#094771" if is_primary else "#3c3c3c"
            lbl.bind("<ButtonRelease-1>", lambda e, c=cmd: c())
            lbl.bind("<Enter>", lambda e, l=lbl, b=on_bg:  l.config(bg=b))
            lbl.bind("<Leave>", lambda e, l=lbl, b=off_bg: l.config(bg=b))

        self.update_idletasks()
        self._draw()
        self.wait_window()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _draw(self) -> None:
        cv = self._cv
        cv.delete("all")
        w = max(cv.winfo_width(), 400)
        for i, (opt, body) in enumerate(zip(self._options, self._bodies)):
            y0  = i * _ROW_H
            y1  = y0 + _ROW_H
            mid = (y0 + y1) // 2
            sel = opt == self._selected
            hov = i == self._hov_idx

            bg = _SEL if sel else (_HOV if hov else _ROW)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")

            # Radio circle
            rx, ry = 16, mid
            cv.create_oval(rx - 6, ry - 6, rx + 6, ry + 6,
                           fill=bg, outline="#555555")
            if sel:
                cv.create_oval(rx - 3, ry - 3, rx + 3, ry + 3,
                               fill="#007acc", outline="")

            # Option name
            cv.create_text(rx + 14, mid, text=opt,
                           fill=_FG, font=(UI_FONT, 9, "bold"), anchor="w")

            # Code body preview (truncated)
            preview = (body[:52] + "…") if len(body) > 53 else body
            cv.create_text(rx + 80, mid, text=preview,
                           fill=_CODE, font=("Consolas", 8), anchor="w")

    # ── Interaction ───────────────────────────────────────────────────────────

    def _row_at(self, y: int) -> int | None:
        idx = y // _ROW_H
        return idx if 0 <= idx < len(self._options) else None

    def _on_click(self, e: tk.Event) -> None:
        idx = self._row_at(e.y)
        if idx is not None:
            self._selected = self._options[idx]
            self._draw()

    def _on_motion(self, e: tk.Event) -> None:
        idx = self._row_at(e.y)
        if idx != self._hov_idx:
            self._hov_idx = idx
            self._draw()

    def _on_leave(self, _e: tk.Event) -> None:
        if self._hov_idx is not None:
            self._hov_idx = None
            self._draw()

    def _commit(self) -> None:
        self.result = self._selected
        self._on_apply(self._selected)
        self.destroy()
