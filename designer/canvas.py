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
_TITLE   = 24       # form title bar height (px)
_MENUBAR = 20       # menu bar strip height (px)
_SHADOW  = 4        # form drop-shadow offset (px)


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
        on_select:            Optional[Callable[[str],               None]] = None,
        on_deselect:          Optional[Callable[[],                  None]] = None,
        on_widget_changed:    Optional[Callable[[WidgetDescriptor],  None]] = None,
        on_form_changed:      Optional[Callable[["FormModel"],       None]] = None,
        on_multi_select:      Optional[Callable[[list],              None]] = None,
        on_structure_changed: Optional[Callable[[],                  None]] = None,
        on_double_click:      Optional[Callable[[str],               None]] = None,
        on_menu_navigate:     Optional[Callable[[str],               None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, highlightthickness=0, **kwargs)
        self._on_select            = on_select
        self._on_deselect          = on_deselect
        self._on_widget_changed    = on_widget_changed
        self._on_form_changed      = on_form_changed
        self._on_multi_select      = on_multi_select
        self._on_structure_changed = on_structure_changed
        self._on_double_click      = on_double_click
        self._on_menu_navigate     = on_menu_navigate
        self._menu_hitboxes: list[tuple[int, int, int, int, int]] = []

        self._form:          FormModel | None        = None
        self._selected_ids:  set[str]                = set()
        self._primary_id:    str | None              = None
        self._form_selected: bool                    = False
        self._hover_id:      str | None              = None
        self._active_tool:   str | None              = None
        self._clipboard:     list[WidgetDescriptor] | None = None
        self._paste_offset:  int                     = 0
        self._ox = _MARGIN
        self._oy = _MARGIN + _TITLE

        self._drag: dict | None = None

        self.bind("<Button-1>",        self._on_click)
        self.bind("<Double-Button-1>", self._on_double_click_evt)
        self.bind("<B1-Motion>",       self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<Delete>",          lambda _: self.remove_selected())
        self.bind("<Control-c>",       lambda _: self.copy_selected())
        self.bind("<Control-v>",       lambda _: self.paste())
        self.bind("<Control-a>",       lambda _: self.select_all())
        self.bind("<Configure>",       lambda _: self._reposition())
        self.bind("<Left>",            lambda _: self._nudge(-1,  0))
        self.bind("<Right>",           lambda _: self._nudge( 1,  0))
        self.bind("<Up>",              lambda _: self._nudge( 0, -1))
        self.bind("<Down>",            lambda _: self._nudge( 0,  1))

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_id(self) -> str | None:
        return self._primary_id

    @property
    def selected_ids(self) -> set[str]:
        return self._selected_ids

    @property
    def form(self) -> FormModel | None:
        return self._form

    @property
    def _min_y(self) -> int:
        """Minimum widget y when a menu bar is present, so widgets can't cover it."""
        return _MENUBAR if (self._form and self._form.menu_items) else 0

    def set_tool(self, type_key: str | None) -> None:
        self._active_tool = type_key
        self.config(cursor="crosshair" if type_key else "arrow")

    def load_form(self, form: FormModel) -> None:
        self._form = form
        self._selected_ids.clear()
        self._primary_id = None
        self._hover_id = None
        self._drag = None
        self._reposition()

    def add_widget(self, descriptor: WidgetDescriptor) -> None:
        if self._form is None:
            return
        self._form.add_widget(descriptor)
        self._render_widget(descriptor)
        self.select(descriptor.id)
        if self._on_structure_changed:
            self._on_structure_changed()

    def remove_selected(self) -> None:
        if not self._selected_ids or self._form is None:
            return
        for wid in list(self._selected_ids):
            # Un-parent any children so they stay on the form
            for child in self._children_of(wid):
                p = self._form.get_widget(wid)
                if p:
                    child.x = max(0, child.x + p.x)
                    child.y = max(self._min_y, child.y + p.y)
                child.parent_id = None
            self._form.remove_widget(wid)
            self.delete(f"widget:{wid}")
        self.delete("handle")
        self.delete("fhandle")
        self._selected_ids.clear()
        self._primary_id = None
        if self._on_deselect:
            self._on_deselect()
        if self._on_structure_changed:
            self._on_structure_changed()

    def _nudge(self, dx: int, dy: int) -> None:
        """Move all selected widgets by (dx, dy) pixels, clamped to form bounds."""
        if not self._selected_ids or self._form is None:
            return
        for wid in self._selected_ids:
            w = self._form.get_widget(wid)
            if w is None:
                continue
            w.x = max(0,            min(w.x + dx, self._form.width  - w.width))
            w.y = max(self._min_y, min(w.y + dy, self._form.height - w.height))
            self.delete(f"widget:{wid}")
            self._render_widget(w)
            self._restore_z_order(wid)
        self.delete("handle")
        self.delete("fhandle")
        self._draw_all_handles()
        self.tag_raise("handle")
        # Notify properties panel via the primary widget
        if self._primary_id:
            w = self._form.get_widget(self._primary_id)
            if w and self._on_widget_changed:
                self._on_widget_changed(w)

    def update_widget(self, descriptor: WidgetDescriptor) -> None:
        was_selected = descriptor.id in self._selected_ids
        self.delete(f"widget:{descriptor.id}")
        self._render_widget(descriptor)
        self._restore_z_order(descriptor.id)
        if was_selected:
            self._draw_all_handles()
        self.tag_raise("handle")

    def select(self, widget_id: str) -> None:
        if self._form is None or self._form.get_widget(widget_id) is None:
            return
        self._paste_offset  = 0
        self._selected_ids  = {widget_id}
        self._primary_id    = widget_id
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        self._draw_all_handles()
        if self._on_select:
            self._on_select(widget_id)

    def select_toggle(self, widget_id: str) -> None:
        """Ctrl+Click: add to or remove from selection."""
        if self._form is None or self._form.get_widget(widget_id) is None:
            return
        if widget_id in self._selected_ids:
            self._selected_ids.discard(widget_id)
            if self._primary_id == widget_id:
                self._primary_id = next(iter(self._selected_ids), None)
        else:
            self._selected_ids.add(widget_id)
            self._primary_id = widget_id
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        self._draw_all_handles()
        self._notify_selection()

    def select_all(self) -> None:
        if not self._form or not self._form.widgets:
            return
        self._selected_ids = {w.id for w in self._form.widgets}
        self._primary_id = self._form.widgets[0].id
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        self._draw_all_handles()
        self._notify_selection()

    def deselect(self) -> None:
        self._selected_ids.clear()
        self._primary_id = None
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        if self._on_deselect:
            self._on_deselect()

    def copy_selected(self) -> None:
        if not self._selected_ids or self._form is None:
            return
        self._clipboard = []
        for wid in self._selected_ids:
            w = self._form.get_widget(wid)
            if w:
                self._clipboard.append(WidgetDescriptor(
                    id=w.id, type=w.type,
                    x=w.x, y=w.y, width=w.width, height=w.height,
                    props=dict(w.props),
                    events={},
                ))
        self._paste_offset = 0

    def _notify_selection(self) -> None:
        n = len(self._selected_ids)
        if n == 0:
            if self._on_deselect:
                self._on_deselect()
        elif n == 1:
            if self._on_select:
                self._on_select(self._primary_id)
        else:
            if self._on_multi_select:
                self._on_multi_select(list(self._selected_ids))

    def paste(self, canvas_x: int | None = None, canvas_y: int | None = None) -> None:
        if not self._clipboard or self._form is None:
            return

        if canvas_x is not None and canvas_y is not None:
            # Right-click paste: anchor the group's top-left corner to the mouse
            min_x = min(s.x for s in self._clipboard)
            min_y = min(s.y for s in self._clipboard)
            ox = _snap(canvas_x - self._ox) - min_x
            oy = _snap(canvas_y - self._oy) - min_y
        else:
            # Ctrl+V: nudge the group each time so repeated pastes don't stack
            self._paste_offset += GRID * 2
            ox = oy = self._paste_offset

        new_ids: list[str] = []
        for src in self._clipboard:
            new_id = self._form.next_id(src.type)
            fx = max(0,            min(src.x + ox, self._form.width  - src.width))
            fy = max(self._min_y, min(src.y + oy, self._form.height - src.height))
            desc = WidgetDescriptor(
                id=new_id, type=src.type,
                x=fx, y=fy, width=src.width, height=src.height,
                props=dict(src.props),
                events={},
            )
            self._form.add_widget(desc)
            self._render_widget(desc)
            new_ids.append(new_id)

        # Select all pasted widgets
        self._selected_ids  = set(new_ids)
        self._primary_id    = new_ids[0]
        self._form_selected = False
        self.delete("handle")
        self.delete("fhandle")
        self._draw_all_handles()
        self.tag_raise("handle")
        self._notify_selection()
        if self._on_structure_changed:
            self._on_structure_changed()

    def select_form(self) -> None:
        if self._form is None:
            return
        self._selected_ids.clear()
        self._primary_id = None
        self._form_selected = True
        self.delete("handle")
        self.delete("fhandle")
        self._draw_form_handles()
        self.tag_raise("fhandle")
        if self._on_deselect:
            self._on_deselect()

    def rename_widget(self, old_id: str, new_id: str) -> None:
        """Rename a widget ID in the model and re-tag canvas items."""
        if self._form is None:
            return
        w = self._form.get_widget(old_id)
        if w is None:
            return
        # Update canvas items tagged with the old id
        self.delete(f"widget:{old_id}")
        w.id = new_id
        self._render_widget(w)
        # Update selection state
        if old_id in self._selected_ids:
            self._selected_ids.discard(old_id)
            self._selected_ids.add(new_id)
        if self._primary_id == old_id:
            self._primary_id = new_id
        self.delete("handle")
        self._draw_all_handles()
        self.tag_raise("handle")

    def bring_to_front(self) -> None:
        if self._primary_id is None or self._form is None:
            return
        w = self._form.get_widget(self._primary_id)
        if w:
            self._form.widgets.remove(w)
            self._form.widgets.append(w)
            self.redraw()
            if self._on_structure_changed:
                self._on_structure_changed()

    def send_to_back(self) -> None:
        if self._primary_id is None or self._form is None:
            return
        w = self._form.get_widget(self._primary_id)
        if w:
            self._form.widgets.remove(w)
            self._form.widgets.insert(0, w)
            self.redraw()
            if self._on_structure_changed:
                self._on_structure_changed()

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
        if self._selected_ids:
            self._draw_all_handles()
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

        # Dot grid
        for gx in range(0, f.width + 1, GRID):
            for gy in range(0, f.height + 1, GRID):
                px, py = ox + gx, oy + gy
                self.create_rectangle(px, py, px + 1, py + 1,
                                      fill=_DOT, outline="", tags="grid")

        # Menu bar strip — drawn after form body so it sits on top
        self._menu_hitboxes = []
        top_items = [(i, item) for i, item in enumerate(f.menu_items) if item.indent == 0]
        if top_items:
            self.create_rectangle(ox, oy, x2, oy + _MENUBAR,
                                  fill="#f0f0f0", outline="", tags="menu_bar")
            self.create_line(ox, oy + _MENUBAR, x2, oy + _MENUBAR,
                             fill="#d0d0d0", tags="menu_bar")
            mx = ox + 4
            for idx, item in top_items:
                label = item.display_caption or "(menu)"
                tw = len(label) * 7 + 12
                self.create_rectangle(mx, oy + 2, mx + tw, oy + _MENUBAR - 2,
                                      fill="#f0f0f0", outline="", tags="menu_bar")
                self.create_text(mx + tw // 2, oy + _MENUBAR // 2,
                                 text=label, fill="#111111",
                                 font=("Segoe UI", 9), tags="menu_bar")
                self._menu_hitboxes.append((mx, oy, mx + tw, oy + _MENUBAR, idx))
                mx += tw + 4

    # ── Container helpers ─────────────────────────────────────────────────────

    def _abs_xy(self, w: WidgetDescriptor) -> tuple[int, int]:
        """Absolute canvas (x, y) for a widget's top-left, honouring parent offset."""
        if w.parent_id and self._form:
            p = self._form.get_widget(w.parent_id)
            if p:
                px, py = self._abs_xy(p)
                return px + w.x, py + w.y
        return self._ox + w.x, self._oy + w.y

    def _children_of(self, parent_id: str) -> list[WidgetDescriptor]:
        if not self._form:
            return []
        return [w for w in self._form.widgets if w.parent_id == parent_id]

    def _container_at(self, cx: int, cy: int,
                      exclude_id: str | None = None) -> WidgetDescriptor | None:
        """Return the innermost Frame/LabelFrame whose canvas rect contains (cx, cy)."""
        if not self._form:
            return None
        result = None
        for w in self._form.widgets:
            if w.id == exclude_id:
                continue
            if not REGISTRY.get(w.type, {}).get("is_container"):
                continue
            ax, ay = self._abs_xy(w)
            if ax <= cx < ax + w.width and ay <= cy < ay + w.height:
                result = w  # keep last match = topmost drawn
        return result

    def _reorder_after_parent(self, widget_id: str, parent_id: str) -> None:
        """Move widget to just after the last existing child of parent in form.widgets."""
        widgets = self._form.widgets
        w = self._form.get_widget(widget_id)
        if w is None:
            return
        widgets.remove(w)
        parent_idx = next((i for i, x in enumerate(widgets) if x.id == parent_id), -1)
        if parent_idx == -1:
            widgets.append(w)
            return
        insert_at = parent_idx
        for i, x in enumerate(widgets):
            if i > parent_idx and x.parent_id == parent_id:
                insert_at = i
        widgets.insert(insert_at + 1, w)

    # ── Widget rendering ──────────────────────────────────────────────────────

    def _restore_z_order(self, widget_id: str) -> None:
        """Lower a freshly re-rendered widget back to its correct z-position.

        Canvas items are drawn in creation order (later = on top). After a
        delete+re-render the new items land at the top of the stack. Lower
        them to just below the next widget in form.widgets so stacking order
        matches the model list.
        """
        if self._form is None:
            return
        ids = [w.id for w in self._form.widgets]
        try:
            idx = ids.index(widget_id)
        except ValueError:
            return
        if idx == len(ids) - 1:
            return  # already the topmost widget — correct
        next_id = ids[idx + 1]
        if self.find_withtag(f"widget:{next_id}"):
            self.tag_lower(f"widget:{widget_id}", f"widget:{next_id}")

    def _render_widget(self, w: WidgetDescriptor) -> None:
        tag   = f"widget:{w.id}"
        x, y  = self._abs_xy(w)
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
        x, y = self._abs_xy(w)
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

    def _draw_all_handles(self) -> None:
        """Draw selection handles for all selected widgets."""
        self.delete("handle")
        if not self._form:
            return
        single = len(self._selected_ids) == 1
        for wid in self._selected_ids:
            w = self._form.get_widget(wid)
            if w is None:
                continue
            if single:
                self._draw_handles(w)
            else:
                # Multi-select: dashed border only (no resize handles)
                x, y = self._abs_xy(w)
                self.create_rectangle(x - 1, y - 1, x + w.width + 1, y + w.height + 1,
                                       outline=_SEL, width=1, dash=(4, 3),
                                       fill="", tags="handle")

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
                w, h = reg["default_size"]
                wid  = self._form.next_id(self._active_tool)
                # Check if dropping onto a container
                container = self._container_at(event.x, event.y)
                if container:
                    ax, ay = self._abs_xy(container)
                    fx = _snap(event.x - ax)
                    fy = _snap(event.y - ay)
                    fx = max(0, min(fx, container.width  - w))
                    fy = max(0, min(fy, container.height - h))
                    parent_id = container.id
                else:
                    fx = _snap(event.x - self._ox)
                    fy = _snap(event.y - self._oy)
                    fx = max(0,            min(fx, self._form.width  - w))
                    fy = max(self._min_y, min(fy, self._form.height - h))
                    parent_id = None
                desc = WidgetDescriptor(
                    id=wid, type=self._active_tool,
                    x=fx, y=fy, width=w, height=h,
                    props=dict(reg["default_props"]),
                    parent_id=parent_id,
                )
                self.add_widget(desc)
                if parent_id:
                    self._reorder_after_parent(wid, parent_id)
                self._active_tool = None
                self.config(cursor="arrow")
                if self._on_deselect:   # signal palette to reset to pointer
                    pass                # palette resets via app.py callback
            return

        # Menu bar hitbox check (before regular hit testing)
        for (hx1, hy1, hx2, hy2, item_idx) in self._menu_hitboxes:
            if hx1 <= event.x <= hx2 and hy1 <= event.y <= hy2:
                self._show_menu_popup(event, item_idx)
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

        # Widget handle click → start resize (single-select only)
        handle_tag = next((t for t in tags if t.startswith("handle:")), None)
        if handle_tag:
            handle_name = handle_tag.split(":", 1)[1]
            if self._primary_id and self._form:
                w = self._form.get_widget(self._primary_id)
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

        # Widget click → Ctrl toggles; otherwise select + prepare move
        ctrl = bool(event.state & 0x0004)
        widget_tag = next((t for t in tags if t.startswith("widget:")), None)
        if widget_tag:
            wid = widget_tag.split(":", 1)[1]
            if ctrl:
                self.select_toggle(wid)
            else:
                # If clicking an already-selected widget keep the group; else replace
                if wid not in self._selected_ids:
                    self.select(wid)
                w = self._form.get_widget(wid) if self._form else None
                if w:
                    orig_positions = {
                        sid: (sw.x, sw.y)
                        for sid in self._selected_ids
                        if (sw := self._form.get_widget(sid))
                    }
                    self._drag = {
                        "mode":     "move",
                        "id":       wid,
                        "start_cx": event.x, "start_cy": event.y,
                        "orig_x":   w.x,     "orig_y":   w.y,
                        "orig_positions": orig_positions,
                    }
            return

        # Clicked form body, title bar, grid, or menu bar background → select form or rubber-band
        if any(t in ("form_bg", "titlebar", "grid", "menu_bar") for t in tags):
            if not ctrl:
                self._selected_ids.clear()
                self._primary_id = None
                self.delete("handle")
                self.delete("fhandle")
            self._drag = {
                "mode":     "rubber_band",
                "start_cx": event.x, "start_cy": event.y,
                "ctrl":     ctrl,
                "prev_ids": set(self._selected_ids),
            }
            return

        self.deselect()

    def _on_double_click_evt(self, event: tk.Event) -> None:
        if self._on_double_click and self._primary_id:
            self._on_double_click(self._primary_id)

    def _on_motion(self, event: tk.Event) -> None:
        d = self._drag
        if d is None or self._form is None:
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

        if d["mode"] == "rubber_band":
            x0, y0 = d["start_cx"], d["start_cy"]
            # Delete old rubber-band rect if any
            self.delete("rubber_band")
            self.create_rectangle(min(x0, event.x), min(y0, event.y),
                                   max(x0, event.x), max(y0, event.y),
                                   outline=_SEL, dash=(4, 3), fill="",
                                   width=1, tags="rubber_band")
            return

        w = self._form.get_widget(d["id"])
        if w is None:
            return

        if d["mode"] == "move":
            new_x = _snap(d["orig_x"] + dx)
            new_y = _snap(d["orig_y"] + dy)
            # Clamp primary widget based on its parent (or form)
            if w.parent_id:
                parent = self._form.get_widget(w.parent_id)
                if parent:
                    new_x = max(0, min(new_x, parent.width  - w.width))
                    new_y = max(0, min(new_y, parent.height - w.height))
                else:
                    new_x = max(0,            min(new_x, self._form.width  - w.width))
                    new_y = max(self._min_y, min(new_y, self._form.height - w.height))
            else:
                new_x = max(0,            min(new_x, self._form.width  - w.width))
                new_y = max(self._min_y, min(new_y, self._form.height - w.height))
            # Actual snapped delta (may differ from raw dx/dy due to clamping)
            actual_dx = new_x - d["orig_x"]
            actual_dy = new_y - d["orig_y"]
            # Move all selected widgets by the same delta
            rendered: set[str] = set()
            for sid, (ox, oy) in d["orig_positions"].items():
                sw = self._form.get_widget(sid)
                if sw is None:
                    continue
                if sw.parent_id:
                    par = self._form.get_widget(sw.parent_id)
                    if par:
                        sw.x = max(0, min(ox + actual_dx, par.width  - sw.width))
                        sw.y = max(0, min(oy + actual_dy, par.height - sw.height))
                    else:
                        sw.x = max(0,            min(ox + actual_dx, self._form.width  - sw.width))
                        sw.y = max(self._min_y, min(oy + actual_dy, self._form.height - sw.height))
                else:
                    sw.x = max(0,            min(ox + actual_dx, self._form.width  - sw.width))
                    sw.y = max(self._min_y, min(oy + actual_dy, self._form.height - sw.height))
                self.delete(f"widget:{sid}")
                self._render_widget(sw)
                self._restore_z_order(sid)
                rendered.add(sid)
                # If moving a container, visually update its children too
                for child in self._children_of(sid):
                    if child.id not in rendered:
                        self.delete(f"widget:{child.id}")
                        self._render_widget(child)
                        self._restore_z_order(child.id)
                        rendered.add(child.id)

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
                ny = max(self._min_y, _snap(oy + dy))
                nh = oy + oh - ny  # recalculate height after ny clamp
                nh = max(GRID * 2, nh)
            if "S" in handle:
                nh = _snap(oh + dy)

            nw = max(GRID * 2, nw)
            nh = max(GRID * 2, nh)
            w.x, w.y, w.width, w.height = nx, ny, nw, nh
            self.delete(f"widget:{w.id}")
            self._render_widget(w)
            self._restore_z_order(w.id)

        self.delete("handle")
        self._draw_all_handles()
        self.tag_raise("handle")

    def _on_release(self, event: tk.Event) -> None:
        d = self._drag
        self._drag = None
        self.config(cursor="arrow")
        if d is None or self._form is None:
            return

        if d["mode"] == "rubber_band":
            self.delete("rubber_band")
            x0 = min(d["start_cx"], event.x)
            y0 = min(d["start_cy"], event.y)
            x1 = max(d["start_cx"], event.x)
            y1 = max(d["start_cy"], event.y)
            if x1 - x0 > 4 or y1 - y0 > 4:
                # Select all widgets intersecting the band
                hit = set()
                for w in self._form.widgets:
                    ax, ay = self._abs_xy(w)
                    if ax < x1 and ax + w.width > x0 and ay < y1 and ay + w.height > y0:
                        hit.add(w.id)
                self._selected_ids = d["prev_ids"] | hit
                self._primary_id   = next(iter(self._selected_ids), None)
                self._form_selected = False
                self.delete("handle")
                self.delete("fhandle")
                self._draw_all_handles()
                self.tag_raise("handle")
                self._notify_selection()
            else:
                # Bare click on empty space → select form
                self.select_form()
            return

        if d["mode"] == "form_resize":
            if self._on_form_changed:
                self._on_form_changed(self._form)
        elif d["mode"] in ("move", "resize"):
            w = self._form.get_widget(d["id"])
            if w:
                if d["mode"] == "move":
                    self._try_reparent(w)
                if self._on_widget_changed:
                    self._on_widget_changed(w)

    def _try_reparent(self, w: WidgetDescriptor) -> None:
        """After a move drag, reparent w if it was dropped onto a different container."""
        ax, ay   = self._abs_xy(w)
        cx       = ax + w.width  // 2
        cy       = ay + w.height // 2
        container = self._container_at(cx, cy, exclude_id=w.id)
        new_pid   = container.id if container else None

        if new_pid == w.parent_id:
            return  # no change

        # Convert current position to form-relative absolute coords
        abs_x = ax - self._ox
        abs_y = ay - self._oy

        if new_pid:
            # Moving into a container: make coords relative to it
            p = self._form.get_widget(new_pid)
            w.x = max(0, min(abs_x - p.x, p.width  - w.width))
            w.y = max(0, min(abs_y - p.y, p.height - w.height))
        else:
            # Dropping onto the form
            w.x = max(0,            min(abs_x, self._form.width  - w.width))
            w.y = max(self._min_y, min(abs_y, self._form.height - w.height))

        w.parent_id = new_pid
        if new_pid:
            self._reorder_after_parent(w.id, new_pid)

        # Redraw to reflect new position / z-order
        self.delete(f"widget:{w.id}")
        self._render_widget(w)
        self._restore_z_order(w.id)
        self.delete("handle")
        self._draw_all_handles()
        self.tag_raise("handle")

        if self._on_structure_changed:
            self._on_structure_changed()

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
        if wid not in self._selected_ids:
            self.config(cursor="fleur")

    def _widget_leave(self, event: tk.Event, wid: str) -> None:
        if self._drag is None:
            self.config(cursor="arrow")

    def _clear_hover(self) -> None:
        self._hover_id = None
        self.config(cursor="arrow")

    def _show_menu_popup(self, event: tk.Event, top_idx: int) -> None:
        """Show a dropdown for the top-level menu item at top_idx."""
        items = self._form.menu_items
        menu = tk.Menu(self, tearoff=0,
                       bg="#ffffff", fg="#111111",
                       activebackground="#0078d4", activeforeground="#ffffff",
                       relief="flat", bd=1, font=("Segoe UI", 9))

        def _ul(item):
            u = item.underline_index
            return {"underline": u} if u >= 0 else {}

        i = top_idx + 1
        while i < len(items) and items[i].indent > 0:
            item = items[i]
            if item.indent == 1:
                if item.caption == "-":
                    menu.add_separator()
                elif i + 1 < len(items) and items[i + 1].indent > 1:
                    # Sub-cascade: collect indent=2 children
                    sub = tk.Menu(menu, tearoff=0,
                                  bg="#ffffff", fg="#111111",
                                  activebackground="#0078d4", activeforeground="#ffffff",
                                  relief="flat", bd=1, font=("Segoe UI", 9))
                    j = i + 1
                    while j < len(items) and items[j].indent > 1:
                        si = items[j]
                        if si.caption == "-":
                            sub.add_separator()
                        elif si.name:
                            sub.add_command(label=si.display_caption,
                                            command=lambda m=f"_{si.name}_click": self._navigate_menu(m),
                                            **_ul(si))
                        else:
                            sub.add_command(label=si.display_caption, state="disabled", **_ul(si))
                        j += 1
                    menu.add_cascade(label=item.display_caption, menu=sub, **_ul(item))
                    i = j
                    continue
                elif item.name:
                    menu.add_command(label=item.display_caption,
                                     command=lambda m=f"_{item.name}_click": self._navigate_menu(m),
                                     **_ul(item))
                else:
                    menu.add_command(label=item.display_caption, state="disabled", **_ul(item))
            i += 1

        # Position popup directly below the menu title button
        rx, ry = event.x_root, event.y_root
        for (hx1, hy1, hx2, hy2, idx) in self._menu_hitboxes:
            if idx == top_idx:
                rx = self.winfo_rootx() + hx1
                ry = self.winfo_rooty() + hy2
                break
        try:
            menu.tk_popup(rx, ry)
        finally:
            menu.grab_release()

    def _navigate_menu(self, method_name: str) -> None:
        if self._on_menu_navigate:
            self._on_menu_navigate(method_name)

    def _on_right_click(self, event: tk.Event) -> None:
        import tkinter as _tk
        # If widget under cursor isn't in selection, select just it
        item = self._topmost_at(event.x, event.y)
        if item:
            tags = self.gettags(item)
            widget_tag = next((t for t in tags if t.startswith("widget:")), None)
            if widget_tag:
                wid = widget_tag.split(":", 1)[1]
                if wid not in self._selected_ids:
                    self.select(wid)

        menu = _tk.Menu(self, tearoff=0)
        has_sel = bool(self._selected_ids)
        has_clip = self._clipboard is not None

        menu.add_command(
            label="Copy",
            state="normal" if has_sel else "disabled",
            command=self.copy_selected,
        )
        menu.add_command(
            label="Paste",
            state="normal" if has_clip else "disabled",
            command=lambda: self.paste(event.x, event.y),
        )
        menu.add_separator()
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
    bg = props.get("bg", "#e1e1e1") or "#e1e1e1"
    fg = props.get("fg", "#111111") or "#111111"
    c.create_rectangle(x, y, x2, y2,     fill=bg, outline="#adadad", width=1)
    c.create_rectangle(x+1, y+1, x2, y2, fill="", outline="#ffffff", width=1)
    _text(c, x, y, x2, y2, text or "Button", color=fg)


@_tag
def _draw_label(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _text(c, x, y, x2, y2, text or "Label", anchor="w", color=fg)


@_tag
def _draw_entry(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#ffffff") or "#ffffff"
    fg = props.get("fg", "#111111") or "#111111"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="#abadb3", width=1)
    c.create_line(x+1, y+1, x2-1, y+1, fill="#c2c2c2")
    placeholder = props.get("placeholder", "")
    if placeholder:
        _text(c, x, y, x2, y2, placeholder, anchor="w", color="#aaaaaa")
    c.create_line(x+6, y+4, x+6, y2-4, fill=fg, width=1)


@_tag
def _draw_text(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#ffffff") or "#ffffff"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="#abadb3")
    c.create_line(x+1, y+1, x2-1, y+1, fill="#c2c2c2")
    _text(c, x, y, x2, y2, "Text", anchor="w", color="#aaaaaa")


@_tag
def _draw_checkbutton(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    bx, by = x + 2, (y + y2) // 2 - 6
    c.create_rectangle(bx, by, bx + 12, by + 12, fill="#ffffff", outline="#abadb3")
    c.create_line(bx+2, by+6, bx+5, by+10, fill="#0078d4", width=2)
    c.create_line(bx+5, by+10, bx+11, by+2, fill="#0078d4", width=2)
    _text(c, bx + 18, y, x2, y2, text or "Check", anchor="w", color=fg)


@_tag
def _draw_radiobutton(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    cx2, cy2 = x + 8, (y + y2) // 2
    c.create_oval(cx2-6, cy2-6, cx2+6, cy2+6, fill="#ffffff", outline="#abadb3")
    c.create_oval(cx2-3, cy2-3, cx2+3, cy2+3, fill="#0078d4", outline="")
    _text(c, cx2 + 12, y, x2, y2, text or "Radio", anchor="w", color=fg)


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
    bg = props.get("bg", "#ffffff") or "#ffffff"
    fg = props.get("fg", "#555555") or "#555555"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="#abadb3")
    row_h = 18
    for i in range(min(3, (y2 - y) // row_h)):
        ry = y + i * row_h
        if i == 0:
            c.create_rectangle(x+1, ry+1, x2-1, ry+row_h, fill="#0078d4", outline="")
            c.create_text(x+5, ry+row_h//2, text=f"Item {i+1}", anchor="w",
                          fill="#ffffff", font=("Segoe UI", 8))
        else:
            c.create_text(x+5, ry+row_h//2, text=f"Item {i+1}", anchor="w",
                          fill=fg, font=("Segoe UI", 8))


@_tag
def _draw_frame(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f0f0f0") or "#f0f0f0"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="#abadb3",
                        dash=(4, 4), width=1)


@_tag
def _draw_labelframe(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f0f0f0") or "#f0f0f0"
    fg = props.get("fg", "#333333") or "#333333"
    label = text or "Group"
    c.create_rectangle(x, y+8, x2, y2, fill=bg, outline="#abadb3",
                        dash=(4, 4))
    lw = len(label) * 6 + 8
    c.create_rectangle(x+8, y, x+8+lw, y+16, fill=bg, outline="")
    c.create_text(x+12, y+8, text=label, anchor="w",
                  fill=fg, font=("Segoe UI", 8))


@_tag
def _draw_scale(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
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
    bg = props.get("bg", "#ffffff") or "#ffffff"
    fg = props.get("fg", "#333333") or "#333333"
    c.create_rectangle(x, y, x2, y2,      fill=bg, outline="#abadb3")
    c.create_rectangle(x2-16, y, x2, y2,  fill="#e1e1e1", outline="#abadb3")
    mid = (y + y2) // 2
    c.create_text(x2-8, mid-4, text="▲", fill="#555555", font=("Segoe UI", 6))
    c.create_text(x2-8, mid+4, text="▼", fill="#555555", font=("Segoe UI", 6))
    val = str(props.get("from_", "0"))
    _text(c, x, y, x2-16, y2, val, anchor="w", color=fg)


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
