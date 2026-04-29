from __future__ import annotations

"""
DesignerCanvas — the drag-and-drop design surface for the GUI Designer.

Architecture:
  - Extends tk.Canvas directly.  No embedded windows.
  - Widgets are drawn as canvas-item groups (not real tkinter widgets).
    This gives complete control over selection handles, hover, and drag.
  - The FormModel is the source of truth; canvas items are always derived from it.
  - Snap grid is 8 px by default.

Public API:
  load_form(form)            — populate canvas from a FormModel
  add_widget(descriptor)     — add one widget and select it
  remove_selected()          — delete the currently selected widget
  update_widget(descriptor)  — re-render after a property change
  select(widget_id)          — programmatic selection
  deselect()                 — clear selection
  selected_id -> str | None  — currently selected widget id
  form -> FormModel | None   — live model (mutated in place on drag/resize)
"""

import tkinter as tk
from typing import Callable, Optional

from .model import FormModel, WidgetDescriptor
from .registry import REGISTRY

# ── Constants ─────────────────────────────────────────────────────────────────

GRID    = 8         # snap grid (px)
_MARGIN = 50        # space around the form on the canvas
_BG     = "#1e1e1e" # canvas background
_FORM   = "#f5f5f5" # default form fill
_DOT    = "#3a3a3a" # grid dot color
_SEL    = "#007acc" # selection / handle color
_HIT    = "#1a9fd4" # hover highlight
_HW     = 7         # handle width/height (px)
_TITLE  = 24        # form title bar height (px)
_SHADOW = 4         # form drop-shadow offset (px)


# ── Handle positions ──────────────────────────────────────────────────────────

_HANDLES = ("NW", "N", "NE", "E", "SE", "S", "SW", "W")

def _handle_center(hx: int, hy: int, hw: int, hh: int, name: str):
    """Canvas (cx, cy) for a handle given the widget's canvas bbox."""
    return {
        "NW": (hx,           hy),
        "N":  (hx + hw // 2, hy),
        "NE": (hx + hw,      hy),
        "E":  (hx + hw,      hy + hh // 2),
        "SE": (hx + hw,      hy + hh),
        "S":  (hx + hw // 2, hy + hh),
        "SW": (hx,           hy + hh),
        "W":  (hx,           hy + hh // 2),
    }[name]

def _handle_cursor(name: str) -> str:
    return {
        "NW": "size_nw_se", "SE": "size_nw_se",
        "NE": "size_ne_sw", "SW": "size_ne_sw",
        "N":  "size_ns",    "S":  "size_ns",
        "E":  "size_we",    "W":  "size_we",
    }.get(name, "arrow")


# ── Main widget ───────────────────────────────────────────────────────────────

class DesignerCanvas(tk.Canvas):
    def __init__(
        self,
        master,
        on_select:         Optional[Callable[[str],               None]] = None,
        on_deselect:       Optional[Callable[[],                  None]] = None,
        on_widget_changed: Optional[Callable[[WidgetDescriptor],  None]] = None,
        on_form_changed:   Optional[Callable[["FormModel"],       None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, highlightthickness=0, **kwargs)
        self._on_select         = on_select
        self._on_deselect       = on_deselect
        self._on_widget_changed = on_widget_changed
        self._on_form_changed   = on_form_changed

        self._form:          FormModel | None = None
        self._selected_id:   str | None       = None
        self._form_selected: bool             = False
        self._hover_id:      str | None       = None
        self._active_tool:   str | None       = None
        self._ox = _MARGIN
        self._oy = _MARGIN + _TITLE

        # Drag / resize state dict, set on ButtonPress and cleared on Release
        self._drag: dict | None = None

        self.bind("<Button-1>",        self._on_click)
        self.bind("<B1-Motion>",       self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<Delete>",          lambda _: self.remove_selected())
        self.bind("<Configure>",       lambda _: self._reposition())

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_id(self) -> str | None:
        return self._selected_id

    @property
    def form(self) -> FormModel | None:
        return self._form

    def set_tool(self, type_key: str | None) -> None:
        """Switch active tool. None = pointer/select; a registry key = place mode."""
        self._active_tool = type_key
        self.config(cursor="crosshair" if type_key else "arrow")

    def load_form(self, form: FormModel) -> None:
        self._form = form
        self._selected_id = None
        self._hover_id = None
        self._drag = None
        self._reposition()

    def add_widget(self, descriptor: WidgetDescriptor) -> None:
        if self._form is None:
            return
        self._form.add_widget(descriptor)
        self._render_widget(descriptor)
        self.select(descriptor.id)

    def remove_selected(self) -> WidgetDescriptor | None:
        if self._selected_id is None or self._form is None:
            return None
        w = self._form.get_widget(self._selected_id)
        self._form.remove_widget(self._selected_id)
        self.delete(f"widget:{self._selected_id}")
        self.delete("handle")
        self._selected_id = None
        if self._on_deselect:
            self._on_deselect()
        return w

    def update_widget(self, descriptor: WidgetDescriptor) -> None:
        """Re-render one widget after a property change from the properties panel."""
        was_selected = self._selected_id == descriptor.id
        self.delete(f"widget:{descriptor.id}")
        self._render_widget(descriptor)
        if was_selected:
            self._draw_handles(descriptor)
        self.tag_raise("handle")

    def select(self, widget_id: str) -> None:
        if self._form is None:
            return
        w = self._form.get_widget(widget_id)
        if w is None:
            return
        self._selected_id = widget_id
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        self._draw_handles(w)
        self.tag_raise("handle")
        if self._on_select:
            self._on_select(widget_id)

    def deselect(self) -> None:
        self._selected_id = None
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        if self._on_deselect:
            self._on_deselect()

    def select_form(self) -> None:
        """Select the form itself, showing resize handles around it."""
        if self._form is None:
            return
        self._selected_id = None
        self._form_selected = True
        self.delete("handle")
        self.delete("fhandle")
        self._draw_form_handles()
        self.tag_raise("fhandle")
        if self._on_deselect:
            self._on_deselect()  # shows form-level properties in panel

    def bring_to_front(self) -> None:
        if self._selected_id is None or self._form is None:
            return
        w = self._form.get_widget(self._selected_id)
        if w:
            self._form.widgets.remove(w)
            self._form.widgets.append(w)
            self.redraw()

    def send_to_back(self) -> None:
        if self._selected_id is None or self._form is None:
            return
        w = self._form.get_widget(self._selected_id)
        if w:
            self._form.widgets.remove(w)
            self._form.widgets.insert(0, w)
            self.redraw()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _reposition(self) -> None:
        """Center the form on the canvas and redraw everything."""
        if self._form is None:
            return
        cw = max(self.winfo_width(),  1)
        ch = max(self.winfo_height(), 1)
        self._ox = max(_MARGIN, (cw - self._form.width)  // 2)
        self._oy = max(_MARGIN + _TITLE, (ch - self._form.height) // 2)
        self.redraw()

    def redraw(self) -> None:
        self.delete("all")
        if self._form is None:
            return
        self._draw_form()
        for w in self._form.widgets:
            self._render_widget(w)
        if self._selected_id:
            sel = self._form.get_widget(self._selected_id)
            if sel:
                self._draw_handles(sel)
            self.tag_raise("handle")
        elif self._form_selected:
            self._draw_form_handles()
            self.tag_raise("fhandle")

    # ── Form background ───────────────────────────────────────────────────────

    def _draw_form(self) -> None:
        f   = self._form
        ox  = self._ox
        oy  = self._oy
        x2  = ox + f.width
        y2  = oy + f.height
        ty  = oy - _TITLE   # title bar top

        # Drop shadow
        self.create_rectangle(ox + _SHADOW, oy + _SHADOW,
                               x2 + _SHADOW, y2 + _SHADOW,
                               fill="#000000", outline="", tags="shadow")

        # Title bar
        self.create_rectangle(ox, ty, x2, oy,
                               fill="#0078d4", outline="", tags="titlebar")
        self.create_text(ox + 8, ty + _TITLE // 2, anchor="w",
                         text=f.title or f.name,
                         fill="#ffffff", font=("Segoe UI", 9), tags="titlebar")

        # Form body
        bg = f.bg or _FORM
        self.create_rectangle(ox, oy, x2, y2,
                               fill=bg, outline="#aaaaaa", tags="form_bg")

        # Dot grid (drawn over form body — canvas order keeps them behind widgets)
        for gx in range(0, f.width + 1, GRID):
            for gy in range(0, f.height + 1, GRID):
                px, py = ox + gx, oy + gy
                self.create_rectangle(px, py, px + 1, py + 1,
                                      fill=_DOT, outline="", tags="grid")

    # ── Widget rendering ──────────────────────────────────────────────────────

    def _render_widget(self, w: WidgetDescriptor) -> None:
        tag   = f"widget:{w.id}"
        x     = self._ox + w.x
        y     = self._oy + w.y
        x2    = x + w.width
        y2    = y + w.height
        props = w.props
        text  = str(props.get("text", w.id))

        _DRAW.get(w.type, _draw_generic)(self, x, y, x2, y2, text, props, tag)

        # Bind click → select on every newly created item
        for item in self.find_withtag(tag):
            self.tag_bind(item, "<Button-1>",
                          lambda e, wid=w.id: self._widget_clicked(e, wid))
            self.tag_bind(item, "<Enter>",
                          lambda e, wid=w.id: self._widget_enter(e, wid))
            self.tag_bind(item, "<Leave>",
                          lambda e, wid=w.id: self._widget_leave(e, wid))

    # ── Selection handles ─────────────────────────────────────────────────────

    def _draw_handles(self, w: WidgetDescriptor) -> None:
        self.delete("handle")
        x  = self._ox + w.x
        y  = self._oy + w.y
        hw = w.width
        hh = w.height
        h  = _HW // 2

        # Selection dashed border
        self.create_rectangle(x - 1, y - 1, x + hw + 1, y + hh + 1,
                               outline=_SEL, width=1, dash=(4, 3),
                               fill="", tags="handle")

        for name in _HANDLES:
            cx, cy = _handle_center(x, y, hw, hh, name)
            self.create_rectangle(cx - h, cy - h, cx + h + 1, cy + h + 1,
                                   fill="#ffffff", outline=_SEL, width=1,
                                   tags=("handle", f"handle:{name}"))
            self.tag_bind(f"handle:{name}", "<Enter>",
                          lambda e, n=name: self.config(cursor=_handle_cursor(n)))
            self.tag_bind(f"handle:{name}", "<Leave>",
                          lambda e: self.config(cursor="arrow"))

    def _draw_form_handles(self) -> None:
        f  = self._form
        ox, oy = self._ox, self._oy
        x2 = ox + f.width
        y2 = oy + f.height
        ty = oy - _TITLE
        h  = _HW // 2

        # Dashed selection border around the whole form (body + title bar)
        self.create_rectangle(ox - 1, ty - 1, x2 + 1, y2 + 1,
                               outline=_SEL, width=1, dash=(4, 3),
                               fill="", tags="fhandle")

        for name in _HANDLES:
            cx, cy = _handle_center(ox, oy, f.width, f.height, name)
            self.create_rectangle(cx - h, cy - h, cx + h + 1, cy + h + 1,
                                   fill="#ffffff", outline=_SEL, width=1,
                                   tags=("fhandle", f"fhandle:{name}"))
            self.tag_bind(f"fhandle:{name}", "<Enter>",
                          lambda e, n=name: self.config(cursor=_handle_cursor(n)))
            self.tag_bind(f"fhandle:{name}", "<Leave>",
                          lambda e: self.config(cursor="arrow"))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        self.focus_set()
        # Placement mode: drop a new widget at the click position
        if self._active_tool and self._form:
            reg = REGISTRY.get(self._active_tool)
            if reg:
                fx = _snap(event.x - self._ox)
                fy = _snap(event.y - self._oy)
                fx = max(0, min(fx, self._form.width  - reg["default_size"][0]))
                fy = max(0, min(fy, self._form.height - reg["default_size"][1]))
                w, h = reg["default_size"]
                wid  = self._form.next_id(self._active_tool)
                desc = WidgetDescriptor(
                    id=wid, type=self._active_tool,
                    x=fx, y=fy, width=w, height=h,
                    props=dict(reg["default_props"]),
                )
                self.add_widget(desc)
                self._active_tool = None
                self.config(cursor="arrow")
                if self._on_deselect:   # signal palette to reset to pointer
                    pass                # palette resets via app.py callback
            return

        item = self._topmost_at(event.x, event.y)
        if item is None:
            self.deselect()
            return

        tags = self.gettags(item)

        # Form handle click → start form resize
        fhandle_tag = next((t for t in tags if t.startswith("fhandle:")), None)
        if fhandle_tag:
            handle_name = fhandle_tag.split(":", 1)[1]
            if self._form:
                self._drag = {
                    "mode":     "form_resize",
                    "handle":   handle_name,
                    "start_cx": event.x, "start_cy": event.y,
                    "orig_w":   self._form.width,
                    "orig_h":   self._form.height,
                    "orig_ox":  self._ox,
                    "orig_oy":  self._oy,
                }
            return

        # Widget handle click → start widget resize
        handle_tag = next((t for t in tags if t.startswith("handle:")), None)
        if handle_tag:
            handle_name = handle_tag.split(":", 1)[1]
            if self._selected_id and self._form:
                w = self._form.get_widget(self._selected_id)
                if w:
                    self._drag = {
                        "mode":    "resize",
                        "handle":  handle_name,
                        "id":      w.id,
                        "start_cx": event.x, "start_cy": event.y,
                        "orig_x": w.x, "orig_y": w.y,
                        "orig_w": w.width, "orig_h": w.height,
                    }
            return

        # Widget click → select + prepare move
        widget_tag = next((t for t in tags if t.startswith("widget:")), None)
        if widget_tag:
            wid = widget_tag.split(":", 1)[1]
            self.select(wid)
            w = self._form.get_widget(wid) if self._form else None
            if w:
                self._drag = {
                    "mode":    "move",
                    "id":      wid,
                    "start_cx": event.x, "start_cy": event.y,
                    "orig_x": w.x, "orig_y": w.y,
                    "orig_w": w.width, "orig_h": w.height,
                }
            return

        # Clicked form body, title bar, or grid → select the form
        if any(t in ("form_bg", "titlebar", "grid") for t in tags):
            self.select_form()
            return

        self.deselect()

    def _on_motion(self, event: tk.Event) -> None:
        d = self._drag
        if d is None or self._form is None:
            return
        w = self._form.get_widget(d["id"])
        if w is None:
            return

        dx = event.x - d["start_cx"]
        dy = event.y - d["start_cy"]

        if d["mode"] == "form_resize":
            f      = self._form
            handle = d["handle"]
            ow, oh = d["orig_w"], d["orig_h"]
            oox, ooy = d["orig_ox"], d["orig_oy"]
            nw, nh   = ow, oh
            nox, noy = oox, ooy

            if "E" in handle:
                nw = _snap(ow + dx)
            if "W" in handle:
                nw  = _snap(ow - dx)
                nox = oox + (ow - nw)
            if "S" in handle:
                nh = _snap(oh + dy)
            if "N" in handle:
                nh  = _snap(oh - dy)
                noy = ooy + (oh - nh)

            f.width  = max(GRID * 8, nw)
            f.height = max(GRID * 8, nh)
            self._ox = nox
            self._oy = noy

            self.delete("all")
            self._draw_form()
            for widget in f.widgets:
                self._render_widget(widget)
            self._draw_form_handles()
            self.tag_raise("fhandle")
            return

        if d["mode"] == "move":
            new_x = _snap(d["orig_x"] + dx)
            new_y = _snap(d["orig_y"] + dy)
            new_x = max(0, min(new_x, self._form.width  - w.width))
            new_y = max(0, min(new_y, self._form.height - w.height))
            w.x, w.y = new_x, new_y

        elif d["mode"] == "resize":
            handle = d["handle"]
            ox, oy = d["orig_x"], d["orig_y"]
            ow, oh = d["orig_w"], d["orig_h"]

            nx, ny, nw, nh = ox, oy, ow, oh

            if "W" in handle:
                nw = _snap(ow - dx)
                nx = _snap(ox + dx)
            if "E" in handle:
                nw = _snap(ow + dx)
            if "N" in handle:
                nh = _snap(oh - dy)
                ny = _snap(oy + dy)
            if "S" in handle:
                nh = _snap(oh + dy)

            nw = max(GRID * 2, nw)
            nh = max(GRID * 2, nh)
            w.x, w.y, w.width, w.height = nx, ny, nw, nh

        # Live re-render
        self.delete(f"widget:{w.id}")
        self._render_widget(w)
        self.delete("handle")
        self._draw_handles(w)
        self.tag_raise("handle")

    def _on_release(self, event: tk.Event) -> None:
        if self._drag and self._form:
            if self._drag["mode"] == "form_resize":
                if self._on_form_changed:
                    self._on_form_changed(self._form)
            else:
                w = self._form.get_widget(self._drag["id"])
                if w and self._on_widget_changed:
                    self._on_widget_changed(w)
        self._drag = None
        self.config(cursor="arrow")

    def _on_hover(self, event: tk.Event) -> None:
        item = self._topmost_at(event.x, event.y)
        if item is None:
            if self._hover_id:
                self._clear_hover()
            return
        tags = self.gettags(item)
        widget_tag = next((t for t in tags if t.startswith("widget:")), None)
        if widget_tag:
            wid = widget_tag.split(":", 1)[1]
            if wid != self._hover_id:
                self._clear_hover()
                self._hover_id = wid
                self.config(cursor="fleur")
        elif not any(t.startswith("handle:") or t.startswith("fhandle:") for t in tags):
            self._clear_hover()

    def _widget_clicked(self, event: tk.Event, wid: str) -> None:
        pass  # handled by _on_click via tag binding

    def _widget_enter(self, event: tk.Event, wid: str) -> None:
        if wid != self._selected_id:
            self.config(cursor="fleur")

    def _widget_leave(self, event: tk.Event, wid: str) -> None:
        if self._drag is None:
            self.config(cursor="arrow")

    def _clear_hover(self) -> None:
        self._hover_id = None
        self.config(cursor="arrow")

    def _on_right_click(self, event: tk.Event) -> None:
        import tkinter as _tk
        # If there's a widget under the cursor, select it first
        item = self._topmost_at(event.x, event.y)
        if item:
            tags = self.gettags(item)
            widget_tag = next((t for t in tags if t.startswith("widget:")), None)
            if widget_tag:
                self.select(widget_tag.split(":", 1)[1])

        menu = _tk.Menu(self, tearoff=0)
        has_sel = self._selected_id is not None

        menu.add_command(
            label="Delete",
            state="normal" if has_sel else "disabled",
            command=self.remove_selected,
        )
        menu.add_separator()
        menu.add_command(
            label="Bring to Front",
            state="normal" if has_sel else "disabled",
            command=self.bring_to_front,
        )
        menu.add_command(
            label="Send to Back",
            state="normal" if has_sel else "disabled",
            command=self.send_to_back,
        )
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    # ── Hit testing ───────────────────────────────────────────────────────────

    def _topmost_at(self, cx: int, cy: int) -> int | None:
        """Return the topmost meaningful canvas item at (cx, cy)."""
        items = self.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1)
        # Reverse: canvas returns items in draw order (bottom to top),
        # but we want the topmost (last in list = drawn last = on top).
        for item in reversed(items):
            tags = self.gettags(item)
            if any(t in ("grid", "shadow", "titlebar") for t in tags):
                continue
            return item
        return None


# ── Per-widget-type draw functions ────────────────────────────────────────────
# Each receives (canvas, x1, y1, x2, y2, text, props, tag)

def _tag(fn):
    """Decorator: tag all canvas items created by *fn* with the given tag."""
    def wrapper(c, x, y, x2, y2, text, props, tag):
        before = set(c.find_all())
        fn(c, x, y, x2, y2, text, props)
        for item in set(c.find_all()) - before:
            c.addtag_withtag(tag, item)
            c.addtag_withtag("widget", item)
    return wrapper


def _text(c, x, y, x2, y2, txt, anchor="center", color="#111111", bold=False):
    font = ("Segoe UI", 9, "bold") if bold else ("Segoe UI", 9)
    cx = (x + x2) // 2 if anchor == "center" else x + 6
    cy = (y + y2) // 2
    c.create_text(cx, cy, text=txt, fill=color, font=font, anchor=anchor)


@_tag
def _draw_button(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2,     fill="#e1e1e1", outline="#adadad", width=1)
    c.create_rectangle(x+1, y+1, x2, y2, fill="",        outline="#ffffff", width=1)
    _text(c, x, y, x2, y2, text or "Button")


@_tag
def _draw_label(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#f5f5f5", outline="")
    _text(c, x, y, x2, y2, text or "Label", anchor="w", color="#111111")


@_tag
def _draw_entry(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#ffffff", outline="#abadb3", width=1)
    c.create_line(x+1, y+1, x2-1, y+1, fill="#c2c2c2")  # inner top shadow
    placeholder = props.get("placeholder", "")
    display = placeholder if placeholder else ""
    if display:
        _text(c, x, y, x2, y2, display, anchor="w", color="#aaaaaa")
    # cursor
    c.create_line(x+6, y+4, x+6, y2-4, fill="#111111", width=1)


@_tag
def _draw_text(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#ffffff", outline="#abadb3")
    c.create_line(x+1, y+1, x2-1, y+1, fill="#c2c2c2")
    _text(c, x, y, x2, y2, "Text", anchor="w", color="#aaaaaa")


@_tag
def _draw_checkbutton(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#f5f5f5", outline="")
    bx, by = x + 2, (y + y2) // 2 - 6
    c.create_rectangle(bx, by, bx + 12, by + 12, fill="#ffffff", outline="#abadb3")
    c.create_line(bx+2, by+6, bx+5, by+10, fill="#0078d4", width=2)
    c.create_line(bx+5, by+10, bx+11, by+2, fill="#0078d4", width=2)
    _text(c, bx + 18, y, x2, y2, text or "Check", anchor="w")


@_tag
def _draw_radiobutton(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#f5f5f5", outline="")
    cx2, cy2 = x + 8, (y + y2) // 2
    c.create_oval(cx2-6, cy2-6, cx2+6, cy2+6, fill="#ffffff", outline="#abadb3")
    c.create_oval(cx2-3, cy2-3, cx2+3, cy2+3, fill="#0078d4", outline="")
    _text(c, cx2 + 12, y, x2, y2, text or "Radio", anchor="w")


@_tag
def _draw_combobox(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2,           fill="#ffffff", outline="#abadb3")
    c.create_rectangle(x2-20, y, x2, y2,       fill="#e1e1e1", outline="#abadb3")
    c.create_text(x2-10, (y+y2)//2,            text="▾",       fill="#444444", font=("Segoe UI", 8))
    vals = props.get("values", [])
    if vals:
        _text(c, x, y, x2-20, y2, str(vals[0]), anchor="w", color="#444444")


@_tag
def _draw_listbox(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#ffffff", outline="#abadb3")
    row_h = 18
    for i in range(min(3, (y2 - y) // row_h)):
        ry = y + i * row_h
        if i == 0:
            c.create_rectangle(x+1, ry+1, x2-1, ry+row_h, fill="#0078d4", outline="")
            c.create_text(x+5, ry+row_h//2, text=f"Item {i+1}", anchor="w",
                          fill="#ffffff", font=("Segoe UI", 8))
        else:
            c.create_text(x+5, ry+row_h//2, text=f"Item {i+1}", anchor="w",
                          fill="#555555", font=("Segoe UI", 8))


@_tag
def _draw_frame(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#f0f0f0", outline="#abadb3",
                        dash=(4, 4), width=1)


@_tag
def _draw_labelframe(c, x, y, x2, y2, text, props):
    label = text or "Group"
    c.create_rectangle(x, y+8, x2, y2, fill="#f0f0f0", outline="#abadb3",
                        dash=(4, 4))
    lw = len(label) * 6 + 8
    c.create_rectangle(x+8, y, x+8+lw, y+16, fill="#f5f5f5", outline="")
    c.create_text(x+12, y+8, text=label, anchor="w",
                  fill="#333333", font=("Segoe UI", 8))


@_tag
def _draw_scale(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#f5f5f5", outline="")
    orient = props.get("orient", "horizontal")
    if orient == "horizontal":
        cy2 = (y + y2) // 2
        c.create_line(x+8, cy2, x2-8, cy2, fill="#abadb3", width=3, capstyle="round")
        mid = (x + x2) // 2
        c.create_rectangle(mid-5, cy2-8, mid+5, cy2+8, fill="#e1e1e1", outline="#abadb3")
    else:
        cx2 = (x + x2) // 2
        c.create_line(cx2, y+8, cx2, y2-8, fill="#abadb3", width=3, capstyle="round")
        mid = (y + y2) // 2
        c.create_rectangle(cx2-8, mid-5, cx2+8, mid+5, fill="#e1e1e1", outline="#abadb3")


@_tag
def _draw_spinbox(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2,      fill="#ffffff", outline="#abadb3")
    c.create_rectangle(x2-16, y, x2, y2,  fill="#e1e1e1", outline="#abadb3")
    mid = (y + y2) // 2
    c.create_text(x2-8, mid-4, text="▲", fill="#555555", font=("Segoe UI", 6))
    c.create_text(x2-8, mid+4, text="▼", fill="#555555", font=("Segoe UI", 6))
    val = str(props.get("from_", "0"))
    _text(c, x, y, x2-16, y2, val, anchor="w", color="#333333")


@_tag
def _draw_progressbar(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2,                    fill="#e1e1e1", outline="#abadb3")
    fill_w = int((x2 - x - 2) * 0.6)
    c.create_rectangle(x+1, y+1, x+1+fill_w, y2-1,      fill="#0078d4", outline="")


@_tag
def _draw_separator(c, x, y, x2, y2, text, props):
    orient = props.get("orient", "horizontal")
    if orient == "horizontal":
        mid = (y + y2) // 2
        c.create_line(x, mid, x2, mid, fill="#abadb3", width=1)
    else:
        mid = (x + x2) // 2
        c.create_line(mid, y, mid, y2, fill="#abadb3", width=1)


def _draw_generic(c, x, y, x2, y2, text, props, tag):
    before = set(c.find_all())
    c.create_rectangle(x, y, x2, y2, fill="#e8e8e8", outline="#abadb3")
    _text(c, x, y, x2, y2, text, color="#555555")
    for item in set(c.find_all()) - before:
        c.addtag_withtag(tag, item)
        c.addtag_withtag("widget", item)


# ── Registry map ──────────────────────────────────────────────────────────────

_DRAW: dict = {
    "Button":      _draw_button,
    "Label":       _draw_label,
    "Entry":       _draw_entry,
    "Text":        _draw_text,
    "Checkbutton": _draw_checkbutton,
    "Radiobutton": _draw_radiobutton,
    "Combobox":    _draw_combobox,
    "Listbox":     _draw_listbox,
    "Frame":       _draw_frame,
    "LabelFrame":  _draw_labelframe,
    "Scale":       _draw_scale,
    "Spinbox":     _draw_spinbox,
    "Progressbar": _draw_progressbar,
    "Separator":   _draw_separator,
}


# ── Utility ───────────────────────────────────────────────────────────────────

def _snap(v: int) -> int:
    return round(v / GRID) * GRID
