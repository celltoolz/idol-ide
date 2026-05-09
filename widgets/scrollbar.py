from __future__ import annotations

import tkinter as tk

# ── Dark-theme palette ────────────────────────────────────────────────────────
_BAR_W      = 12
_ARROW_H    = 14
_PANEL_BG   = "#1e1e1e"
_TRACK_BG   = "#252526"
_THUMB_NOM  = "#4a4a4c"
_THUMB_HOV  = "#686869"
_THUMB_ACT  = "#868687"
_ARROW_NOM  = "#525254"
_ARROW_HOV  = "#939395"


class VerticalScrollbar(tk.Canvas):
    """Custom canvas-rendered vertical scrollbar for dark-theme panels.

    Drop-in replacement for ttk.Scrollbar — same yscrollcommand/command protocol.

    Usage:
        sb = VerticalScrollbar(parent)
        sb.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=sb.set)
        sb.configure(command=canvas.yview)
    """

    def __init__(self, parent, **kwargs):
        kwargs.setdefault("width",              _BAR_W)
        kwargs.setdefault("bg",                 _PANEL_BG)
        kwargs.setdefault("highlightthickness", 0)
        kwargs.setdefault("cursor",             "arrow")
        super().__init__(parent, **kwargs)

        self._cmd:        object      = None
        self._first:      float       = 0.0
        self._last:       float       = 1.0
        self._drag_y:     int | None  = None
        self._drag_f0:    float       = 0.0
        self._hov_thumb:  bool        = False
        self._hov_up:     bool        = False
        self._hov_dn:     bool        = False

        self.bind("<Configure>",       lambda _: self._redraw())
        self.bind("<Motion>",          self._on_motion)
        self.bind("<Leave>",           self._on_leave)
        self.bind("<ButtonPress-1>",   self._on_press)
        self.bind("<B1-Motion>",       self._on_drag)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<MouseWheel>",      self._on_wheel)

    # ── Public API ────────────────────────────────────────────────────────────

    def configure(self, **kwargs):
        cmd = kwargs.pop("command", None)
        if cmd is not None:
            self._cmd = cmd
        if kwargs:
            super().configure(**kwargs)

    config = configure

    def set(self, first, last) -> None:
        """yscrollcommand target — called by the target widget on every scroll."""
        self._first = float(first)
        self._last  = float(last)
        self._redraw()

    # ── Geometry helpers ──────────────────────────────────────────────────────

    def _track_bounds(self) -> tuple[int, int]:
        """(track_y0, track_y1) — the scrollable region between the two arrows."""
        return _ARROW_H, max(_ARROW_H + 1, self.winfo_height() - _ARROW_H)

    def _thumb_bounds(self) -> tuple[int, int]:
        """(y0, y1) of the thumb in canvas coords."""
        tr_y0, tr_y1 = self._track_bounds()
        track_h = max(1, tr_y1 - tr_y0)
        span    = max(0.0, self._last - self._first)
        thumb_h = max(20, int(track_h * span))
        y0      = tr_y0 + int(self._first * track_h)
        y1      = y0 + thumb_h
        if y1 > tr_y1:
            y1 = tr_y1
            y0 = y1 - thumb_h
        return max(tr_y0, y0), max(tr_y0, y1)

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _redraw(self) -> None:
        self.delete("all")
        w = self.winfo_width()
        h = self.winfo_height()
        if w <= 1 or h <= 1:
            return

        ah = _ARROW_H
        cx = w // 2
        tr_y0, tr_y1 = self._track_bounds()

        # Track background
        self.create_rectangle(0, tr_y0, w, tr_y1,
                              fill=_TRACK_BG, outline="")

        # Thumb — only when content overflows
        if self._last - self._first < 0.999:
            y0, y1 = self._thumb_bounds()
            tc = (_THUMB_ACT  if self._drag_y  is not None else
                  _THUMB_HOV  if self._hov_thumb else _THUMB_NOM)
            self.create_rectangle(3, y0 + 1, w - 3, y1 - 1,
                                  fill=tc, outline="", tags="thumb")

        # Up arrow ▲
        ac_up = _ARROW_HOV if self._hov_up else _ARROW_NOM
        self.create_polygon(cx, 3, cx - 4, ah - 3, cx + 4, ah - 3,
                            fill=ac_up, outline="", tags="up")

        # Down arrow ▼
        ac_dn = _ARROW_HOV if self._hov_dn else _ARROW_NOM
        self.create_polygon(cx, h - 3, cx - 4, h - ah + 3, cx + 4, h - ah + 3,
                            fill=ac_dn, outline="", tags="dn")

    # ── Event routing ─────────────────────────────────────────────────────────

    def _hit(self, x: int, y: int) -> str:
        items = self.find_closest(x, y)
        if items:
            for t in ("thumb", "up", "dn"):
                if t in self.gettags(items[0]):
                    return t
        h = self.winfo_height()
        if y < _ARROW_H:
            return "up"
        if y > h - _ARROW_H:
            return "dn"
        return "track"

    def _on_motion(self, event: tk.Event) -> None:
        hit = self._hit(event.x, event.y)
        prev = (self._hov_thumb, self._hov_up, self._hov_dn)
        self._hov_thumb = hit == "thumb"
        self._hov_up    = hit == "up"
        self._hov_dn    = hit == "dn"
        if (self._hov_thumb, self._hov_up, self._hov_dn) != prev:
            self._redraw()

    def _on_leave(self, _event: tk.Event) -> None:
        if any((self._hov_thumb, self._hov_up, self._hov_dn)):
            self._hov_thumb = self._hov_up = self._hov_dn = False
            self._redraw()

    def _on_press(self, event: tk.Event) -> None:
        hit = self._hit(event.x, event.y)
        if hit == "thumb":
            self._drag_y  = event.y
            self._drag_f0 = self._first
            self._redraw()
        elif hit == "up":
            if self._cmd:
                self._cmd("scroll", -1, "units")
        elif hit == "dn":
            if self._cmd:
                self._cmd("scroll", 1, "units")
        elif hit == "track":
            y0, y1 = self._thumb_bounds()
            if event.y < y0 and self._cmd:
                self._cmd("scroll", -1, "pages")
            elif event.y > y1 and self._cmd:
                self._cmd("scroll", 1, "pages")

    def _on_drag(self, event: tk.Event) -> None:
        if self._drag_y is None:
            return
        tr_y0, tr_y1 = self._track_bounds()
        track_h = max(1, tr_y1 - tr_y0)
        delta   = (event.y - self._drag_y) / track_h
        span    = max(0.0, self._last - self._first)
        new_f   = max(0.0, min(1.0 - span, self._drag_f0 + delta))
        if self._cmd:
            self._cmd("moveto", new_f)

    def _on_release(self, _event: tk.Event) -> None:
        if self._drag_y is not None:
            self._drag_y = None
            self._redraw()

    def _on_wheel(self, event: tk.Event) -> None:
        if self._cmd:
            self._cmd("scroll", -1 * (event.delta // 120), "units")
