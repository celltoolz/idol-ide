"""Canvas-drawn colour picker — an HSV square, a hue strip, and a hex field.

Two classes, deliberately split:

* ``ColorPicker`` is a plain ``tk.Frame`` that can be packed anywhere. It knows
  nothing about editors, documents, or hovering — it renders a colour and calls
  ``on_change`` when the user picks a new one.
* ``ColorPickerPopup`` wraps one in an ``overrideredirect`` ``Toplevel`` and adds
  the hover lifetime: stay open while the pointer is over the popup *or* over
  whatever opened it, and close after a grace delay once it is over neither.

The split is what makes the widget reusable. The editor mounts the popup on a
hex literal; the Designer's properties panel can mount the bare ``ColorPicker``
in a dialog and get the same picker without inheriting any hover behaviour.

No alpha channel — IDOL emits Tk colour strings, and Tk has no notion of one.

The gradients are PIL images generated small (``_GEN``px) and resized up.
A smooth gradient survives interpolation perfectly, so this costs a few hundred
pixels of work per hue change instead of tens of thousands, which is what keeps
dragging the hue strip smooth.
"""
from __future__ import annotations

import colorsys
import re
import tkinter as tk
from typing import Callable

from PIL import Image, ImageTk

from utils.ui_font import UI_FONT

# ── Geometry ──────────────────────────────────────────────────────────────────
_SV_W, _SV_H = 180, 132        # saturation/value square
_HUE_W       = 14              # hue strip width
_GAP         = 8
_PAD         = 8
_ROW_H       = 26              # hex field row
_GEN         = 64              # gradient generated at _GEN×_GEN, then resized

# ── Palette ───────────────────────────────────────────────────────────────────
_BG      = "#252526"
_BORDER  = "#454545"
_FG      = "#cccccc"
_ENTRY   = "#3c3c3c"
_MARKER  = "#ffffff"
_MARKER_ = "#000000"           # marker's contrasting outline

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3}|[0-9a-fA-F]{6})$")


def parse_hex(text: str) -> str | None:
    """Normalise ``#rgb`` / ``rrggbb`` / ``#RRGGBB`` to ``#rrggbb``, else None."""
    m = _HEX_RE.match((text or "").strip())
    if not m:
        return None
    digits = m.group(1)
    if len(digits) == 3:
        digits = "".join(c * 2 for c in digits)
    return "#" + digits.lower()


def hex_to_rgb(hex_color: str) -> tuple[int, int, int]:
    h = (parse_hex(hex_color) or "#000000")[1:]
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _chan(value: float) -> int:
    """Clamp a 0-255 channel to an int, rounding rather than truncating.

    Truncating loses a step on the HSV round trip — `colorsys` gives back
    31.999999999999996 for what went in as 32, so `int()` would turn every
    #10c020 into #10c01f each time the picker opened.
    """
    return max(0, min(255, int(round(value))))


def rgb_to_hex(r: float, g: float, b: float) -> str:
    return f"#{_chan(r):02x}{_chan(g):02x}{_chan(b):02x}"


class ColorPicker(tk.Frame):
    """HSV square + hue strip + hex entry. Fires ``on_change(hex)`` live."""

    def __init__(self, parent, color: str = "#000000",
                 on_change: Callable[[str], None] | None = None) -> None:
        super().__init__(parent, bg=_BG, highlightthickness=1,
                         highlightbackground=_BORDER, highlightcolor=_BORDER)
        self._on_change = on_change
        self._h, self._s, self._v = 0.0, 0.0, 0.0
        self._sv_img: ImageTk.PhotoImage | None = None
        self._hue_img: ImageTk.PhotoImage | None = None
        self._suppress = False          # guards the hex Entry against feedback

        cv_w = _PAD * 2 + _SV_W + _GAP + _HUE_W
        cv_h = _PAD + _SV_H
        self._cv = tk.Canvas(self, width=cv_w, height=cv_h, bg=_BG,
                             highlightthickness=0, cursor="crosshair")
        self._cv.pack(side="top")

        row = tk.Frame(self, bg=_BG)
        row.pack(side="top", fill="x", padx=_PAD, pady=(6, _PAD))
        self._swatch = tk.Canvas(row, width=18, height=18, bg=_BG,
                                 highlightthickness=1,
                                 highlightbackground=_BORDER)
        self._swatch.pack(side="left")
        self._entry_var = tk.StringVar()
        self._entry = tk.Entry(row, textvariable=self._entry_var, bg=_ENTRY,
                               fg=_FG, insertbackground=_FG, relief="flat",
                               font=(UI_FONT, 9), width=10, bd=0)
        self._entry.pack(side="left", padx=(8, 0), ipady=3)
        self._entry.bind("<Return>", self._commit_entry)
        self._entry.bind("<FocusOut>", self._commit_entry)

        self._sv_x0 = _PAD
        self._sv_y0 = _PAD
        self._hue_x0 = _PAD + _SV_W + _GAP

        for seq, handler in (
            ("<Button-1>", self._on_press),
            ("<B1-Motion>", self._on_drag),
            ("<ButtonRelease-1>", self._on_release),
        ):
            self._cv.bind(seq, handler)

        self._drag_target: str | None = None
        self.set_color(color)

    # ── Public API ────────────────────────────────────────────────────────────

    def get_color(self) -> str:
        r, g, b = colorsys.hsv_to_rgb(self._h, self._s, self._v)
        return rgb_to_hex(r * 255, g * 255, b * 255)

    def set_color(self, hex_color: str) -> None:
        """Set the displayed colour without firing ``on_change``."""
        r, g, b = hex_to_rgb(hex_color)
        h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
        # A greyscale colour has no meaningful hue; keep the current one so the
        # square does not snap to red when the user drags value down to black.
        self._h = h if s > 0 else self._h
        self._s, self._v = s, v
        self._render(regen_sv=True)

    def focus_entry(self) -> None:
        self._entry.focus_set()
        self._entry.select_range(0, "end")

    # ── Rendering ─────────────────────────────────────────────────────────────

    def _render(self, regen_sv: bool = False) -> None:
        if regen_sv or self._sv_img is None:
            self._sv_img = self._make_sv_image(self._h)
        if self._hue_img is None:
            self._hue_img = self._make_hue_image()

        c = self._cv
        c.delete("all")
        c.create_image(self._sv_x0, self._sv_y0, image=self._sv_img, anchor="nw")
        c.create_rectangle(self._sv_x0, self._sv_y0,
                           self._sv_x0 + _SV_W, self._sv_y0 + _SV_H,
                           outline=_BORDER)
        c.create_image(self._hue_x0, self._sv_y0, image=self._hue_img, anchor="nw")
        c.create_rectangle(self._hue_x0, self._sv_y0,
                           self._hue_x0 + _HUE_W, self._sv_y0 + _SV_H,
                           outline=_BORDER)

        # SV marker — white ring with a dark outline so it stays visible at both
        # ends of the gradient.
        mx = self._sv_x0 + self._s * _SV_W
        my = self._sv_y0 + (1.0 - self._v) * _SV_H
        for rad, col in ((5, _MARKER_), (4, _MARKER)):
            c.create_oval(mx - rad, my - rad, mx + rad, my + rad, outline=col)

        hy = self._sv_y0 + self._h * _SV_H
        c.create_rectangle(self._hue_x0 - 2, hy - 2,
                           self._hue_x0 + _HUE_W + 2, hy + 2,
                           outline=_MARKER_)
        c.create_rectangle(self._hue_x0 - 1, hy - 1,
                           self._hue_x0 + _HUE_W + 1, hy + 1,
                           outline=_MARKER)

        cur = self.get_color()
        self._swatch.configure(bg=cur)
        self._suppress = True
        self._entry_var.set(cur.upper())
        self._suppress = False

    def _make_sv_image(self, hue: float) -> ImageTk.PhotoImage:
        px = bytearray()
        for row in range(_GEN):
            v = 1.0 - row / (_GEN - 1)
            for col in range(_GEN):
                s = col / (_GEN - 1)
                r, g, b = colorsys.hsv_to_rgb(hue, s, v)
                px += bytes((int(r * 255), int(g * 255), int(b * 255)))
        img = Image.frombytes("RGB", (_GEN, _GEN), bytes(px))
        return ImageTk.PhotoImage(img.resize((_SV_W, _SV_H), Image.BILINEAR))

    def _make_hue_image(self) -> ImageTk.PhotoImage:
        px = bytearray()
        for row in range(_GEN):
            r, g, b = colorsys.hsv_to_rgb(row / (_GEN - 1), 1.0, 1.0)
            px += bytes((int(r * 255), int(g * 255), int(b * 255)))
        img = Image.frombytes("RGB", (1, _GEN), bytes(px))
        return ImageTk.PhotoImage(img.resize((_HUE_W, _SV_H), Image.BILINEAR))

    # ── Interaction ───────────────────────────────────────────────────────────

    def _zone(self, x: int, y: int) -> str | None:
        if (self._sv_x0 <= x <= self._sv_x0 + _SV_W
                and self._sv_y0 <= y <= self._sv_y0 + _SV_H):
            return "sv"
        if (self._hue_x0 - 3 <= x <= self._hue_x0 + _HUE_W + 3
                and self._sv_y0 <= y <= self._sv_y0 + _SV_H):
            return "hue"
        return None

    def _on_press(self, event) -> None:
        self._drag_target = self._zone(event.x, event.y)
        if self._drag_target:
            self._apply(event.x, event.y)

    def _on_drag(self, event) -> None:
        # Keep using the zone the drag *started* in — dragging out of the SV
        # square and over the hue strip must not start changing hue mid-stroke.
        if self._drag_target:
            self._apply(event.x, event.y)

    def _on_release(self, _event) -> None:
        self._drag_target = None

    def _apply(self, x: int, y: int) -> None:
        if self._drag_target == "sv":
            self._s = min(1.0, max(0.0, (x - self._sv_x0) / _SV_W))
            self._v = 1.0 - min(1.0, max(0.0, (y - self._sv_y0) / _SV_H))
            self._render()
        elif self._drag_target == "hue":
            self._h = min(1.0, max(0.0, (y - self._sv_y0) / _SV_H))
            self._render(regen_sv=True)
        else:
            return
        self._fire()

    def _commit_entry(self, _event=None) -> None:
        if self._suppress:
            return
        parsed = parse_hex(self._entry_var.get())
        if parsed is None:
            self._render()          # reject: snap the field back to the truth
            return
        if parsed == self.get_color():
            return
        self.set_color(parsed)
        self._fire()

    def _fire(self) -> None:
        if self._on_change is not None:
            try:
                self._on_change(self.get_color())
            except Exception:
                pass


class ColorPickerPopup(tk.Toplevel):
    """A ``ColorPicker`` in a borderless popup with hover-based lifetime.

    The caller reports pointer movement over the *anchor* (the swatch that
    opened this) via `keep_alive` / `schedule_close`; the popup watches itself.
    Either surface being hovered keeps it up, and the grace delay is what lets
    the pointer cross the gap between them without it vanishing mid-travel.
    """

    #: Grace period before closing once the pointer is over neither surface.
    CLOSE_DELAY_MS = 260

    def __init__(self, parent, color: str,
                 on_change: Callable[[str], None] | None = None,
                 on_close: Callable[[], None] | None = None) -> None:
        super().__init__(parent)
        self.withdraw()
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=_BG)
        self._on_close = on_close
        self._close_after: str | None = None
        self._closed = False

        self.picker = ColorPicker(self, color=color, on_change=on_change)
        self.picker.pack(fill="both", expand=True)

        # Bind on every descendant: <Enter>/<Leave> on a container do not fire
        # for motion between its children, so watching only the Toplevel would
        # read a move from the square to the hex field as "pointer left".
        self._bind_hover_recursive(self)
        self.bind("<Escape>", lambda _: self.close())

    def _bind_hover_recursive(self, widget) -> None:
        widget.bind("<Enter>", lambda _: self.keep_alive(), add=True)
        widget.bind("<Leave>", lambda _: self.schedule_close(), add=True)
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    # ── Lifetime ──────────────────────────────────────────────────────────────

    def show_at(self, x_root: int, y_root: int) -> None:
        """Place the popup near (x_root, y_root), nudged to stay on screen."""
        self.update_idletasks()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        x = max(0, min(x_root, sw - w))
        # Prefer below the anchor; flip above when that would go off-screen.
        y = y_root if y_root + h <= sh else max(0, y_root - h - 24)
        self.geometry(f"+{int(x)}+{int(y)}")
        self.deiconify()
        self.lift()

    def keep_alive(self) -> None:
        """Cancel a pending close — the pointer is over a live surface."""
        if self._close_after is not None:
            try:
                self.after_cancel(self._close_after)
            except Exception:
                pass
            self._close_after = None

    def schedule_close(self, delay_ms: int | None = None) -> None:
        if self._closed:
            return
        self.keep_alive()
        self._close_after = self.after(
            self.CLOSE_DELAY_MS if delay_ms is None else delay_ms, self.close)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        self.keep_alive()
        if self._on_close is not None:
            try:
                self._on_close()
            except Exception:
                pass
        try:
            self.destroy()
        except Exception:
            pass
