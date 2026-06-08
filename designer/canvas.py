from __future__ import annotations
from utils.ui_font import UI_FONT

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

import sys
import tkinter as tk
from typing import Callable, Optional

from .model import CanvasItemDescriptor, FormModel, WidgetDescriptor
from .registry import REGISTRY

# ── Constants ─────────────────────────────────────────────────────────────────

GRID         = 8     # snap grid (px)
_snap_enabled  = True  # module-level flag toggled by DesignerCanvas.toggle_snap()
_grid_visible  = True  # module-level flag toggled by DesignerCanvas.toggle_grid()
_MARGIN = 50        # space around the form on the canvas
_BG     = "#1e1e1e" # canvas background
_FORM   = "#f5f5f5" # default form fill
_DOT    = "#3a3a3a" # grid dot color
_SEL     = "#007acc" # secondary selection color
_PRIMARY = "#e8a844" # primary selection color (amber)
_HIT    = "#1a9fd4" # hover highlight
_HW     = 7         # handle width/height (px)
_TITLE      = 24    # form title bar height (px)
_MENUBAR    = 20    # menu bar strip height (px)
_SHADOW     = 4     # form drop-shadow offset (px)
_LF_LABEL_H = 17    # LabelFrame label area height — measured: child y=0 appears 17px below outer top
_NB_TAB_H   = 26    # Notebook tab-strip height — content area starts this many px below the widget top
_CI_BORDER  = "#007acc"  # active canvas-item-edit mode border
_CI_SEL     = "#e8a844"  # selected canvas item handle/highlight color


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
    if sys.platform == "win32":
        return {
            "NW": "size_nw_se", "SE": "size_nw_se",
            "NE": "size_ne_sw", "SW": "size_ne_sw",
            "N":  "size_ns",    "S":  "size_ns",
            "E":  "size_we",    "W":  "size_we",
        }.get(name, "arrow")
    return {
        "NW": "top_left_corner",     "SE": "bottom_right_corner",
        "NE": "top_right_corner",    "SW": "bottom_left_corner",
        "N":  "sb_v_double_arrow",   "S":  "sb_v_double_arrow",
        "E":  "sb_h_double_arrow",   "W":  "sb_h_double_arrow",
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
        on_menu_navigate:         Optional[Callable[[str],               None]] = None,
        on_menu_item_no_command:  Optional[Callable[[int],               None]] = None,
        on_tool_cancel:           Optional[Callable[[],                  None]] = None,
        on_snap_state_changed:    Optional[Callable[[],                  None]] = None,
        on_canvas_item_mode:      Optional[Callable[[str | None],        None]] = None,
        on_ci_select:             Optional[Callable[["CanvasItemDescriptor | None"], None]] = None,
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
        self._on_menu_item_no_command = on_menu_item_no_command
        self._on_tool_cancel       = on_tool_cancel
        self._on_snap_state_changed = on_snap_state_changed
        self._on_canvas_item_mode  = on_canvas_item_mode
        self._on_ci_select         = on_ci_select
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
        self._shift_snap_override: bool = False

        self._undo_stack: list[dict] = []
        self._redo_stack: list[dict] = []
        self._tab_order_visible: bool = False
        self._active_nb_tabs: dict[str, str] = {}  # nb_id → active tab name
        self._img_cache: dict[str, object] = {}  # "{path}:{w}:{h}" → ImageTk.PhotoImage
        self._project_dir: str = __import__("os").getcwd()

        # Canvas item edit mode state
        self._ci_mode:        bool          = False   # in canvas item edit mode?
        self._ci_widget_id:   str | None    = None    # which Canvas widget we're editing
        self._ci_selected_id: str | None    = None    # selected CanvasItemDescriptor id
        self._ci_drag:        dict | None   = None    # drag state
        self._ci_arm_kind:    str | None    = None    # armed item type for placement
        self._ci_arm_props:   dict         = {}      # extra props pre-set on placement (e.g. image_path)

        self.bind("<Button-1>",        self._on_click)
        self.bind("<Double-Button-1>", self._on_double_click_evt)
        self.bind("<B1-Motion>",       self._on_motion)
        self.bind("<ButtonRelease-1>", self._on_release)
        self.bind("<Motion>",          self._on_hover)
        self.bind("<Button-3>",        self._on_right_click)
        self.bind("<KeyPress-Shift_L>",   self._on_shift_press)
        self.bind("<KeyPress-Shift_R>",   self._on_shift_press)
        self.bind("<KeyRelease-Shift_L>", self._on_shift_release)
        self.bind("<KeyRelease-Shift_R>", self._on_shift_release)
        self.bind("<Delete>",          lambda _: self.remove_selected())
        self.bind("<Control-c>",       lambda _: self.copy_selected())
        self.bind("<Control-v>",       lambda _: self.paste())
        self.bind("<Control-a>",       lambda _: self.select_all())
        self.bind("<Control-z>",       lambda _: self.undo())
        self.bind("<Control-y>",       lambda _: self.redo())
        self.bind("<Control-Z>",       lambda _: self.redo())
        self.bind("<Configure>",       lambda _: self._reposition())
        self.bind("<Left>",            lambda _: self._nudge(-(GRID if self.snap_enabled else 1),    0))
        self.bind("<Right>",           lambda _: self._nudge( (GRID if self.snap_enabled else 1),    0))
        self.bind("<Up>",              lambda _: self._nudge(    0, -(GRID if self.snap_enabled else 1)))
        self.bind("<Down>",            lambda _: self._nudge(    0,  (GRID if self.snap_enabled else 1)))
        self.bind("<Shift-Left>",      lambda _: self._nudge(-(GRID if self.snap_enabled else 1),    0))
        self.bind("<Shift-Right>",     lambda _: self._nudge( (GRID if self.snap_enabled else 1),    0))
        self.bind("<Shift-Up>",        lambda _: self._nudge(    0, -(GRID if self.snap_enabled else 1)))
        self.bind("<Shift-Down>",      lambda _: self._nudge(    0,  (GRID if self.snap_enabled else 1)))
        self.bind("<MouseWheel>",       self._on_mousewheel)
        self.bind("<Button-4>",         self._on_mousewheel)
        self.bind("<Button-5>",         self._on_mousewheel)
        self.bind("<Shift-MouseWheel>", self._on_mousewheel_h)
        self.bind("<Shift-Button-4>",   self._on_mousewheel_h)
        self.bind("<Shift-Button-5>",   self._on_mousewheel_h)
        self.bind("<Escape>",          self._on_escape)

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

    def cancel_tool(self) -> None:
        """Exit placement mode and return to pointer."""
        if self._ci_mode:
            if self._ci_arm_kind:
                self.arm_item_tool(None)
                if self._on_tool_cancel:
                    self._on_tool_cancel()
            else:
                self.exit_canvas_item_mode()
            return
        if self._active_tool is None:
            return
        self._active_tool = None
        self.config(cursor="arrow")
        if self._on_tool_cancel:
            self._on_tool_cancel()

    def _on_escape(self, event) -> None:
        self.cancel_tool()

    # ── Canvas item edit mode (public API) ────────────────────────────────────

    @property
    def ci_mode(self) -> bool:
        return self._ci_mode

    @property
    def ci_widget_id(self) -> str | None:
        return self._ci_widget_id

    @property
    def ci_selected_id(self) -> str | None:
        return self._ci_selected_id

    def enter_canvas_item_mode(self, widget_id: str) -> None:
        if self._form is None:
            return
        w = self._form.get_widget(widget_id)
        if w is None or w.type != "Canvas":
            return
        self._ci_mode = True
        self._ci_widget_id = widget_id
        self._ci_selected_id = None
        self._ci_drag = None
        self._ci_arm_kind = None
        self.deselect()
        self.config(cursor="arrow")
        self._ci_redraw()
        if self._on_canvas_item_mode:
            self._on_canvas_item_mode(widget_id)

    def exit_canvas_item_mode(self) -> None:
        self._ci_mode = False
        self._ci_widget_id = None
        self._ci_selected_id = None
        self._ci_drag = None
        self._ci_arm_kind = None
        self.config(cursor="arrow")
        self._redraw()
        if self._on_canvas_item_mode:
            self._on_canvas_item_mode(None)
        if self._on_ci_select:
            self._on_ci_select(None)

    def arm_item_tool(self, kind: str | None, props: dict | None = None) -> None:
        self._ci_arm_kind  = kind
        self._ci_arm_props = props or {}
        self.config(cursor="crosshair" if kind else "arrow")

    def add_canvas_item(self, kind: str, x: int = 0, y: int = 0,
                        props: dict | None = None) -> CanvasItemDescriptor | None:
        """Create a new canvas item on the active CI widget and select it."""
        if not self._ci_mode or not self._ci_widget_id or not self._form:
            return None
        w = self._form.get_widget(self._ci_widget_id)
        if w is None:
            return None
        defaults: dict = {"image": {}, "rectangle": {"fill": "#4a4a4a", "outline": "#888888"},
                          "oval": {"fill": "#4a4a4a", "outline": "#888888"},
                          "text": {"text": "Text", "fill": "#ffffff"},
                          "line": {"fill": "#888888", "linewidth": 1}}
        base_props = dict(defaults.get(kind, {}))
        base_props.update(self._ci_arm_props)
        if props:
            base_props.update(props)
        if kind == "image":
            iw, ih = self._get_image_size(base_props.get("image_path", ""))
            item_w, item_h = iw, ih
        elif kind == "line":
            item_w, item_h = 50, 0
        elif kind == "text":
            item_w, item_h = 64, 20
        else:
            item_w, item_h = 64, 64
        item = CanvasItemDescriptor(
            id=w.next_item_id(kind), kind=kind,
            x=max(0, min(x, w.width - 32)),
            y=max(0, min(y, w.height - 32)),
            width=item_w, height=item_h,
            props=base_props,
        )
        w.canvas_items.append(item)
        self._ci_selected_id = item.id
        self._ci_redraw()
        self._notify_ci_select()
        if self._on_structure_changed:
            self._on_structure_changed()
        return item

    def _get_image_size(self, rel_path: str) -> tuple[int, int]:
        import os
        if not rel_path:
            return 64, 64
        full = rel_path if os.path.isabs(rel_path) else os.path.join(
            self._project_dir, rel_path.replace("/", os.sep))
        try:
            from PIL import Image
            with Image.open(full) as img:
                return img.size
        except Exception:
            return 64, 64

    def drop_ci_item(self, kind: str, local_x: int, local_y: int,
                     props: dict | None = None) -> None:
        """Place a CI item at local pixel coords within the designer canvas widget."""
        if not self._ci_mode or not self._ci_widget_id or not self._form:
            return
        w = self._form.get_widget(self._ci_widget_id)
        if w is None:
            return
        cx = int(self.canvasx(local_x))
        cy = int(self.canvasy(local_y))
        wx, wy = self._abs_xy(w)
        self.add_canvas_item(kind, cx - wx, cy - wy, props=props)
        self.arm_item_tool(None)

    def remove_canvas_item(self, item_id: str) -> None:
        if not self._ci_widget_id or not self._form:
            return
        w = self._form.get_widget(self._ci_widget_id)
        if w is None:
            return
        w.canvas_items = [ci for ci in w.canvas_items if ci.id != item_id]
        if self._ci_selected_id == item_id:
            self._ci_selected_id = None
        self._ci_redraw()
        self._notify_ci_select()
        if self._on_structure_changed:
            self._on_structure_changed()

    def update_canvas_item(self, item: CanvasItemDescriptor) -> None:
        """Re-render after an external property change to a canvas item."""
        if self._ci_mode:
            self._ci_redraw()

    def get_ci_widget(self) -> WidgetDescriptor | None:
        if self._ci_widget_id and self._form:
            return self._form.get_widget(self._ci_widget_id)
        return None

    def get_ci_selected(self) -> CanvasItemDescriptor | None:
        w = self.get_ci_widget()
        if w and self._ci_selected_id:
            return next((ci for ci in w.canvas_items if ci.id == self._ci_selected_id), None)
        return None

    def select_ci_item(self, item_id: str) -> None:
        """Select a canvas item by id (called from Order tab row click)."""
        if not self._ci_mode:
            return
        self._ci_selected_id = item_id
        self._ci_redraw()
        self._notify_ci_select()

    def _notify_ci_select(self) -> None:
        if self._on_ci_select:
            self._on_ci_select(self.get_ci_selected())

    def place_at_default(self, type_key: str) -> None:
        """Place *type_key* widget at the centre of the form and select it."""
        if self._form is None:
            return
        reg = REGISTRY.get(type_key)
        if not reg:
            return
        w, h   = reg["default_size"]
        usable = self._form.height - self._min_y
        fx = max(0, min(self._form.width  // 2 - w // 2, self._form.width  - w))
        fy = max(self._min_y, min(self._min_y + usable // 2 - h // 2, self._form.height - h))
        wid  = self._form.next_id(type_key)
        desc = WidgetDescriptor(
            id=wid, type=type_key,
            x=fx, y=fy, width=w, height=h,
            props=dict(reg["default_props"]),
        )
        self.add_widget(desc)
        if REGISTRY.get(type_key, {}).get("is_notebook"):
            tabs = desc.props.get("tabs", [])
            if tabs:
                self._active_nb_tabs[wid] = tabs[0]
        self._active_tool = None
        self.config(cursor="arrow")

    def drop_widget(self, type_key: str, cx: int, cy: int) -> None:
        """Place *type_key* at canvas coord (cx, cy) with default size (palette drag-drop)."""
        if self._form is None:
            return
        reg = REGISTRY.get(type_key)
        if not reg:
            return
        w, h = reg["default_size"]
        container = self._container_at(cx, cy)
        tab_name = ""
        if container:
            ax, ay = self._abs_xy(container)
            if REGISTRY.get(container.type, {}).get("is_notebook"):
                label_h = _NB_TAB_H
                tabs = container.props.get("tabs", [])
                tab_name = self._active_nb_tabs.get(container.id, tabs[0] if tabs else "")
            elif container.type == "LabelFrame":
                label_h = _LF_LABEL_H
            else:
                label_h = 0
            fx = _snap(cx - ax)
            fy = _snap(cy - ay - label_h)
            fx = max(0, min(fx, container.width  - w))
            fy = max(0, min(fy, container.height - label_h - h))
            parent_id = container.id
        else:
            fx = _snap(cx - self._ox)
            fy = _snap(cy - self._oy)
            fx = max(0,           min(fx, self._form.width  - w))
            fy = max(self._min_y, min(fy, self._form.height - h))
            parent_id = None
        wid = self._form.next_id(type_key)
        desc = WidgetDescriptor(
            id=wid, type=type_key,
            x=fx, y=fy, width=w, height=h,
            props=dict(reg["default_props"]),
            parent_id=parent_id,
            tab=tab_name,
        )
        self.add_widget(desc)
        if parent_id:
            self._reorder_after_parent(wid, parent_id)

    def load_form(self, form: FormModel) -> None:
        self._form = form
        self._selected_ids.clear()
        self._primary_id = None
        self._hover_id = None
        self._drag = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._active_nb_tabs.clear()
        self._img_cache.clear()
        self._reposition()

    def set_project_dir(self, path: str) -> None:
        self._project_dir = path
        self._img_cache.clear()
        self._reposition()

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    _MAX_UNDO = 50

    def push_undo(self) -> None:
        """Snapshot the current form state; call this BEFORE any mutation."""
        if self._form is None:
            return
        self._undo_stack.append(self._form.to_dict())
        if len(self._undo_stack) > self._MAX_UNDO:
            self._undo_stack.pop(0)
        self._redo_stack.clear()

    def undo(self) -> None:
        if not self._undo_stack or self._form is None:
            return
        self._redo_stack.append(self._form.to_dict())
        self._restore_state(self._undo_stack.pop())

    def redo(self) -> None:
        if not self._redo_stack or self._form is None:
            return
        self._undo_stack.append(self._form.to_dict())
        self._restore_state(self._redo_stack.pop())

    def _restore_state(self, state: dict) -> None:
        self._form = FormModel.from_dict(state)
        self._selected_ids.clear()
        self._primary_id = None
        self._form_selected = False
        self._drag = None
        self._reposition()
        if self._on_structure_changed:
            self._on_structure_changed()
        if self._on_deselect:
            self._on_deselect()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def add_widget(self, descriptor: WidgetDescriptor) -> None:
        if self._form is None:
            return
        self.push_undo()
        self._form.add_widget(descriptor)
        self._render_widget(descriptor)
        self.select(descriptor.id)
        if self._on_structure_changed:
            self._on_structure_changed()

    def remove_selected(self) -> None:
        if not self._selected_ids or self._form is None:
            return
        self.push_undo()
        # Expand selection to include all descendants of any container being deleted
        to_delete: set[str] = set(self._selected_ids)
        for wid in list(self._selected_ids):
            for desc in self._descendants_of(wid):
                to_delete.add(desc.id)
        for wid in to_delete:
            self._disconnect_widget(wid)
            self._form.remove_widget(wid)
            self.delete(f"widget:{wid}")
        self.delete("handle")
        self.delete("fhandle")
        if self._tab_order_visible:
            self.delete("tab_badge")
            self._draw_tab_badges()
        self._selected_ids.clear()
        self._primary_id = None
        if self._on_deselect:
            self._on_deselect()
        if self._on_structure_changed:
            self._on_structure_changed()

    def _disconnect_widget(self, wid: str) -> None:
        """Strip all component/handler connections that reference this widget before deletion."""
        if self._form is None:
            return
        # Remove canvas_button entries in Image components that target this widget
        for comp in self._form.components:
            if comp.type == "Image":
                buttons = comp.props.get("canvas_buttons") or []
                comp.props["canvas_buttons"] = [
                    b for b in buttons if b.get("canvas_id") != wid
                ]
        # Remove orphaned handler wires that target this widget
        self._form.handler_wires = [
            w for w in self._form.handler_wires if w.widget_id != wid
        ]

    def _nudge(self, dx: int, dy: int) -> None:
        """Move all selected widgets by (dx, dy) pixels, clamped to form bounds."""
        if not self._selected_ids or self._form is None:
            return
        for wid in self._selected_ids:
            w = self._form.get_widget(wid)
            if w is None:
                continue
            if w.parent_id:
                par = self._form.get_widget(w.parent_id)
                if par:
                    lh = _LF_LABEL_H if par.type == "LabelFrame" else 0
                    w.x = max(0, min(w.x + dx, par.width  - w.width))
                    w.y = max(0, min(w.y + dy, par.height - lh - w.height))
                else:
                    w.x = max(0,            min(w.x + dx, self._form.width  - w.width))
                    w.y = max(self._min_y, min(w.y + dy, self._form.height - w.height))
            else:
                w.x = max(0,            min(w.x + dx, self._form.width  - w.width))
                w.y = max(self._min_y, min(w.y + dy, self._form.height - w.height))
            self.delete(f"widget:{wid}")
            self._render_widget(w)
            self._restore_z_order(wid)
            for child in self._children_of(wid):
                self.delete(f"widget:{child.id}")
                self._render_widget(child)
                self._restore_z_order(child.id)
        if self._tab_order_visible:
            self.delete("tab_badge")
            self._draw_tab_badges()
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
        for child in self._descendants_of(descriptor.id):
            self.delete(f"widget:{child.id}")
            if self._should_render(child):
                self._render_widget(child)
                self._restore_z_order(child.id)
        if self._tab_order_visible:
            self.delete("tab_badge")
            self._draw_tab_badges()
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
        # Iterate form.widgets (ordered list) so clipboard preserves creation order,
        # giving paste a deterministic ID sequence instead of random set iteration.
        for w in self._form.widgets:
            if w.id not in self._selected_ids:
                continue
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
        self.push_undo()

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
        if self._tab_order_visible:
            self.delete("tab_badge")
            self._draw_tab_badges()
            self.tag_raise("handle")
        self._notify_selection()
        if self._on_structure_changed:
            self._on_structure_changed()

    def select_form(self) -> None:
        if self._form is None:
            return
        was_selected = self._form_selected
        self._selected_ids.clear()
        self._primary_id = None
        self._form_selected = True
        self.delete("handle")
        self.delete("fhandle")
        self._draw_form_handles()
        self.tag_raise("fhandle")
        if not was_selected and self._on_deselect:
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
            self.push_undo()
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
            self.push_undo()
            self._form.widgets.remove(w)
            self._form.widgets.insert(0, w)
            self.redraw()
            if self._on_structure_changed:
                self._on_structure_changed()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _on_mousewheel(self, event: tk.Event) -> None:
        if event.num == 4:
            self.yview_scroll(-1, "units")
        elif event.num == 5:
            self.yview_scroll(1, "units")
        else:
            self.yview_scroll(-1 if event.delta > 0 else 1, "units")

    def _on_mousewheel_h(self, event: tk.Event) -> None:
        if event.num == 4:
            self.xview_scroll(-1, "units")
        elif event.num == 5:
            self.xview_scroll(1, "units")
        else:
            self.xview_scroll(-1 if event.delta > 0 else 1, "units")

    def _reposition(self) -> None:
        """Center the form on the canvas (when it fits) and update scrollregion."""
        if self._form is None:
            self.delete("all")
            cw = max(self.winfo_width(), 1)
            ch = max(self.winfo_height(), 1)
            self.configure(scrollregion=(0, 0, cw, ch))
            return
        cw = max(self.winfo_width(),  1)
        ch = max(self.winfo_height(), 1)
        self._ox = max(_MARGIN, (cw - self._form.width)  // 2)
        self._oy = max(_MARGIN + _TITLE, (ch - self._form.height) // 2)
        sr_w = self._ox + self._form.width  + _MARGIN
        sr_h = self._oy + self._form.height + _MARGIN
        self.configure(scrollregion=(0, 0, max(cw, sr_w), max(ch, sr_h)))
        self.redraw()

    def _should_render(self, w: WidgetDescriptor) -> bool:
        """Return False for children of a Notebook that belong to an inactive tab."""
        if not w.parent_id or not self._form:
            return True
        par = self._form.get_widget(w.parent_id)
        if par and REGISTRY.get(par.type, {}).get("is_notebook"):
            tabs = par.props.get("tabs", [])
            active = self._active_nb_tabs.get(par.id, tabs[0] if tabs else "")
            return w.tab == active
        return True

    def redraw(self) -> None:
        self.delete("all")
        if self._form is None:
            return
        self._draw_form()
        for w in self._form.widgets:
            if self._should_render(w):
                self._render_widget(w)
        if self._tab_order_visible:
            self._draw_tab_badges()
        if self._selected_ids:
            self._draw_all_handles()
            self.tag_raise("handle")
        elif self._form_selected:
            self._draw_form_handles()
            self.tag_raise("fhandle")

    # ── Tab order ─────────────────────────────────────────────────────────────

    def toggle_tab_order(self) -> bool:
        self._tab_order_visible = not self._tab_order_visible
        self.redraw()
        return self._tab_order_visible

    def _draw_tab_badges(self) -> None:
        if not self._form:
            return
        r = 9
        form_idx = 0
        # Cache per-notebook-tab sibling lists for scoped numbering
        _nb_tab_counts: dict[tuple, int] = {}

        for w in self._form.widgets:
            if not self._should_render(w):
                continue
            x, y = self._abs_xy(w)
            cx, cy = x + r + 2, y + r + 2

            par = self._form.get_widget(w.parent_id) if w.parent_id else None
            if par and REGISTRY.get(par.type, {}).get("is_notebook"):
                # Scoped within this notebook tab — number independently, teal badge
                key = (par.id, w.tab)
                _nb_tab_counts[key] = _nb_tab_counts.get(key, 0) + 1
                badge_num = _nb_tab_counts[key]
                fill = "#4ec9b0"
            else:
                form_idx += 1
                badge_num = form_idx
                fill = "#007acc"

            self.create_oval(cx - r, cy - r, cx + r, cy + r,
                             fill=fill, outline="#ffffff", width=1,
                             tags="tab_badge")
            self.create_text(cx, cy, text=str(badge_num), fill="#ffffff",
                             font=(UI_FONT, 7, "bold"), tags="tab_badge")
        self.tag_raise("tab_badge")

    def move_widget_to(self, widget_id: str, new_idx: int) -> None:
        """Move widget_id to new_idx in form order (tab + z order)."""
        if self._form is None:
            return
        self.push_undo()
        if not self._form.move_widget(widget_id, new_idx):
            self._undo_stack.pop()
            return
        self.redraw()
        if self._on_structure_changed:
            self._on_structure_changed()

    # ── Snap toggle ───────────────────────────────────────────────────────────

    def toggle_snap(self) -> bool:
        global _snap_enabled
        _snap_enabled = not _snap_enabled
        return _snap_enabled

    @property
    def snap_enabled(self) -> bool:
        return (not _snap_enabled) if self._shift_snap_override else _snap_enabled

    def toggle_grid(self) -> bool:
        global _grid_visible
        _grid_visible = not _grid_visible
        self.redraw()
        return _grid_visible

    @property
    def grid_visible(self) -> bool:
        return _grid_visible

    # ── Alignment / distribution / sizing (multi-select operations) ───────────

    def _selected_widgets(self) -> list[WidgetDescriptor]:
        if not self._form:
            return []
        return [w for wid in self._selected_ids
                if (w := self._form.get_widget(wid)) is not None]

    def _primary_widget(self) -> "WidgetDescriptor | None":
        if not self._form or not self._primary_id:
            return None
        return self._form.get_widget(self._primary_id)

    def _commit_alignment(self) -> None:
        self.push_undo()
        self.redraw()
        for w in self._selected_widgets():
            if self._on_widget_changed:
                self._on_widget_changed(w)

    def align_left(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        for w in self._selected_widgets():
            w.x = ref.x
        self._commit_alignment()

    def align_right(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        target = ref.x + ref.width
        for w in self._selected_widgets():
            w.x = target - w.width
        self._commit_alignment()

    def align_top(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        for w in self._selected_widgets():
            w.y = ref.y
        self._commit_alignment()

    def align_bottom(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        target = ref.y + ref.height
        for w in self._selected_widgets():
            w.y = target - w.height
        self._commit_alignment()

    def align_center_h(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        cx = ref.x + ref.width // 2
        for w in self._selected_widgets():
            w.x = cx - w.width // 2
        self._commit_alignment()

    def align_center_v(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        cy = ref.y + ref.height // 2
        for w in self._selected_widgets():
            w.y = cy - w.height // 2
        self._commit_alignment()

    def distribute_h(self) -> None:
        widgets = self._selected_widgets()
        if len(widgets) < 3:
            return
        # Cluster by center-x into column groups; all widgets in the same column
        # get the same x so rows with different spans don't produce uneven gaps.
        avg_w = sum(w.width for w in widgets) / len(widgets)
        by_cx = sorted(widgets, key=lambda w: w.x + w.width / 2)
        cols: list[list] = []
        for w in by_cx:
            cx = w.x + w.width / 2
            if cols and cx - (cols[-1][-1].x + cols[-1][-1].width / 2) < avg_w:
                cols[-1].append(w)
            else:
                cols.append([w])
        if len(cols) < 2:
            return
        cols = sorted(cols, key=lambda c: sum(w.x + w.width / 2 for w in c) / len(c))
        left  = min(w.x for w in widgets)
        right = max(w.x + w.width for w in widgets)
        col_widths = [sum(w.width for w in c) / len(c) for c in cols]
        gap = (right - left - sum(col_widths)) / max(1, len(cols) - 1)
        x = float(left)
        for col, cw in zip(cols, col_widths):
            for w in col:
                w.x = round(x)
            x += cw + gap
        self._commit_alignment()

    def distribute_v(self) -> None:
        widgets = self._selected_widgets()
        if len(widgets) < 3:
            return
        # Cluster by center-y into row groups; all widgets in the same row
        # get the same y so columns with different spans don't produce uneven gaps.
        avg_h = sum(w.height for w in widgets) / len(widgets)
        by_cy = sorted(widgets, key=lambda w: w.y + w.height / 2)
        rows: list[list] = []
        for w in by_cy:
            cy = w.y + w.height / 2
            if rows and cy - (rows[-1][-1].y + rows[-1][-1].height / 2) < avg_h:
                rows[-1].append(w)
            else:
                rows.append([w])
        if len(rows) < 2:
            return
        rows = sorted(rows, key=lambda r: sum(w.y + w.height / 2 for w in r) / len(r))
        top    = min(w.y for w in widgets)
        bottom = max(w.y + w.height for w in widgets)
        row_heights = [sum(w.height for w in r) / len(r) for r in rows]
        gap = (bottom - top - sum(row_heights)) / max(1, len(rows) - 1)
        y = float(top)
        for row, rh in zip(rows, row_heights):
            for w in row:
                w.y = round(y)
            y += rh + gap
        self._commit_alignment()

    def arrange_grid(self) -> None:
        """Snap selected widgets into a uniform grid using their existing layout."""
        widgets = self._selected_widgets()
        n = len(widgets)
        if n < 2:
            return
        self.push_undo()
        avg_w = sum(w.width  for w in widgets) / n
        avg_h = sum(w.height for w in widgets) / n

        # Detect column count from existing x-clustering
        by_cx = sorted(widgets, key=lambda w: w.x + w.width / 2)
        cols: list[list] = []
        for w in by_cx:
            cx = w.x + w.width / 2
            if cols and cx - (cols[-1][-1].x + cols[-1][-1].width / 2) < avg_w:
                cols[-1].append(w)
            else:
                cols.append([w])
        n_cols = max(1, len(cols))
        n_rows = (n + n_cols - 1) // n_cols

        # Sort in reading order (row clusters then left-to-right within each row)
        by_cy = sorted(widgets, key=lambda w: w.y + w.height / 2)
        rows: list[list] = []
        for w in by_cy:
            cy = w.y + w.height / 2
            if rows and cy - (rows[-1][-1].y + rows[-1][-1].height / 2) < avg_h:
                rows[-1].append(w)
            else:
                rows.append([w])
        ordered: list = []
        for row in rows:
            ordered.extend(sorted(row, key=lambda w: w.x + w.width / 2))

        start_x = min(w.x for w in widgets)
        start_y = min(w.y for w in widgets)

        col_widths = [
            max((ordered[r * n_cols + c].width for r in range(n_rows)
                 if r * n_cols + c < len(ordered)), default=int(avg_w))
            for c in range(n_cols)
        ]
        row_heights = [
            max((ordered[r * n_cols + c].height for c in range(n_cols)
                 if r * n_cols + c < len(ordered)), default=int(avg_h))
            for r in range(n_rows)
        ]

        for i, w in enumerate(ordered):
            row = i // n_cols
            col = i % n_cols
            w.x = start_x + sum(col_widths[:col])  + col  * GRID
            w.y = start_y + sum(row_heights[:row]) + row * GRID
        self._commit_alignment()

    def nudge_h(self, delta: int) -> None:
        """Shift each column right (+) or left (−) by delta per column index."""
        widgets = self._selected_widgets()
        if len(widgets) < 2:
            return
        avg_w = sum(w.width for w in widgets) / len(widgets)
        by_cx = sorted(widgets, key=lambda w: w.x + w.width / 2)
        cols: list[list] = []
        for w in by_cx:
            cx = w.x + w.width / 2
            if cols and cx - (cols[-1][-1].x + cols[-1][-1].width / 2) < avg_w:
                cols[-1].append(w)
            else:
                cols.append([w])
        if len(cols) < 2:
            return
        self.push_undo()
        cols = sorted(cols, key=lambda c: sum(w.x + w.width / 2 for w in c) / len(c))
        for i, col in enumerate(cols[1:], 1):
            for w in col:
                w.x = max(0, w.x + delta * i)
        self._commit_alignment()

    def nudge_v(self, delta: int) -> None:
        """Shift each row down (+) or up (−) by delta per row index."""
        widgets = self._selected_widgets()
        if len(widgets) < 2:
            return
        avg_h = sum(w.height for w in widgets) / len(widgets)
        by_cy = sorted(widgets, key=lambda w: w.y + w.height / 2)
        rows: list[list] = []
        for w in by_cy:
            cy = w.y + w.height / 2
            if rows and cy - (rows[-1][-1].y + rows[-1][-1].height / 2) < avg_h:
                rows[-1].append(w)
            else:
                rows.append([w])
        if len(rows) < 2:
            return
        self.push_undo()
        rows = sorted(rows, key=lambda r: sum(w.y + w.height / 2 for w in r) / len(r))
        for i, row in enumerate(rows[1:], 1):
            for w in row:
                w.y = max(0, w.y + delta * i)
        self._commit_alignment()

    def same_width(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        for w in self._selected_widgets():
            w.width = ref.width
        self._commit_alignment()

    def same_height(self) -> None:
        ref = self._primary_widget()
        if ref is None:
            return
        for w in self._selected_widgets():
            w.height = ref.height
        self._commit_alignment()

    def set_selection_anchor(self, anchor: str) -> None:
        self.push_undo()
        for w in self._selected_widgets():
            w.anchor = anchor
        if self._on_widget_changed:
            for w in self._selected_widgets():
                self._on_widget_changed(w)

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
                         fill="#ffffff", font=(UI_FONT, 9), tags="titlebar")

        # Form body
        bg = f.bg or _FORM
        self.create_rectangle(ox, oy, x2, y2,
                               fill=bg, outline="#aaaaaa", tags="form_bg")

        # Background image (natural size, below grid)
        if f.image:
            photo = _load_natural_image(self, f.image)
            if photo:
                self.create_image(ox, oy, anchor="nw", image=photo, tags="form_bg")
            else:
                self.create_text(ox + 4, oy + 4, text="[bg image]", anchor="nw",
                                 fill="#ce9178", font=(UI_FONT, 7), tags="form_bg")

        # Dot grid
        if _grid_visible:
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
                                 font=(UI_FONT, 9), tags="menu_bar")
                self._menu_hitboxes.append((mx, oy, mx + tw, oy + _MENUBAR, idx))
                mx += tw + 4

    # ── Container helpers ─────────────────────────────────────────────────────

    def _abs_xy(self, w: WidgetDescriptor) -> tuple[int, int]:
        """Absolute canvas (x, y) for a widget's top-left, honouring parent offset.

        LabelFrame children are offset by _LF_LABEL_H so the designer matches
        the actual tkinter placement (children are measured from the content area,
        not the widget's outer top-left).
        """
        if w.parent_id and self._form:
            p = self._form.get_widget(w.parent_id)
            if p:
                px, py = self._abs_xy(p)
                if p.type == "LabelFrame":
                    label_h = _LF_LABEL_H
                elif REGISTRY.get(p.type, {}).get("is_notebook"):
                    label_h = _NB_TAB_H
                else:
                    label_h = 0
                return px + w.x, py + label_h + w.y
        return self._ox + w.x, self._oy + w.y

    def _children_of(self, parent_id: str) -> list[WidgetDescriptor]:
        if not self._form:
            return []
        return [w for w in self._form.widgets if w.parent_id == parent_id]

    def _descendants_of(self, parent_id: str) -> list[WidgetDescriptor]:
        result = []
        for child in self._children_of(parent_id):
            result.append(child)
            result.extend(self._descendants_of(child.id))
        return result

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
            content_y = ay + _NB_TAB_H if REGISTRY.get(w.type, {}).get("is_notebook") else ay
            if ax <= cx < ax + w.width and content_y <= cy < ay + w.height:
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

    def _switch_nb_tab(self, nb_id: str, tab_name: str) -> None:
        """Make tab_name the active tab for notebook nb_id and redraw."""
        self._active_nb_tabs[nb_id] = tab_name
        self.select(nb_id)
        self._redraw()

    def _redraw(self) -> None:
        """Full redraw keeping selection and handle state."""
        self.redraw()
        if self._selected_ids:
            self._draw_all_handles()
            self.tag_raise("handle")
        elif self._form_selected:
            self._draw_form_handles()
            self.tag_raise("fhandle")

    # ── Canvas item edit mode rendering ───────────────────────────────────────

    def _ci_redraw(self) -> None:
        """Full redraw in canvas item edit mode."""
        self.delete("all")
        if self._form is None or self._ci_widget_id is None:
            return
        self._draw_form()
        for widget in self._form.widgets:
            if self._should_render(widget):
                self._render_widget(widget)
        w = self._form.get_widget(self._ci_widget_id)
        if w:
            self._ci_draw_overlay(w)
            self._ci_draw_items(w)
            if self._ci_selected_id:
                item = next((ci for ci in w.canvas_items if ci.id == self._ci_selected_id), None)
                if item:
                    wx, wy = self._abs_xy(w)
                    self._ci_draw_handles(item, wx, wy)

    def _ci_draw_overlay(self, w: WidgetDescriptor) -> None:
        """Draw dim overlay over all widgets except the CI canvas, plus mode indicator."""
        wx, wy = self._abs_xy(w)
        ox, oy = self._ox, self._oy
        fw, fh = self._form.width, self._form.height
        x2, y2 = wx + w.width, wy + w.height

        # Four dim strips framing the canvas widget within the form
        if wy > oy:
            self.create_rectangle(ox, oy, ox + fw, wy,
                                  fill="#000000", outline="", stipple="gray25", tags="ci_overlay")
        if y2 < oy + fh:
            self.create_rectangle(ox, y2, ox + fw, oy + fh,
                                  fill="#000000", outline="", stipple="gray25", tags="ci_overlay")
        if wx > ox:
            self.create_rectangle(ox, wy, wx, y2,
                                  fill="#000000", outline="", stipple="gray25", tags="ci_overlay")
        if x2 < ox + fw:
            self.create_rectangle(x2, wy, ox + fw, y2,
                                  fill="#000000", outline="", stipple="gray25", tags="ci_overlay")

        # Blue border + mode label
        self.create_rectangle(wx - 2, wy - 2, x2 + 2, y2 + 2,
                               outline=_CI_BORDER, width=2, fill="", tags="ci_overlay")
        self.create_text(wx, wy - 4, anchor="sw",
                         text=f"Canvas Items: {w.id}  (Esc to exit)",
                         fill=_CI_BORDER, font=(UI_FONT, 8), tags="ci_overlay")

    def _ci_draw_items(self, w: WidgetDescriptor) -> None:
        """Draw all canvas items belonging to widget w."""
        wx, wy = self._abs_xy(w)
        for item in w.canvas_items:
            self._ci_draw_item(item, wx, wy)

    def _ci_draw_item(self, item: CanvasItemDescriptor, wx: int, wy: int) -> None:
        """Draw one canvas item at its absolute designer-canvas position."""
        ix  = wx + item.x
        iy  = wy + item.y
        ix2 = ix + item.width
        iy2 = iy + item.height
        tags = ("ci_item", f"ci_item:{item.id}")
        is_sel = item.id == self._ci_selected_id

        if item.kind == "image":
            img_path = item.props.get("image_path", "")
            if img_path and item.width > 0 and item.height > 0:
                photo = _load_preview_image(self, img_path, item.width, item.height)
                if photo:
                    self.create_image(ix, iy, anchor="nw", image=photo, tags=tags)
                    if is_sel:
                        self.create_rectangle(ix - 1, iy - 1, ix2 + 1, iy2 + 1,
                                              outline=_CI_SEL, width=2, fill="", tags=tags)
                else:
                    self._ci_draw_placeholder(ix, iy, ix2, iy2, "[img]", "#ce9178", is_sel, tags)
            else:
                self._ci_draw_placeholder(ix, iy, ix2, iy2, "image", "#569cd6", is_sel, tags)

        elif item.kind == "rectangle":
            fill    = item.props.get("fill", "#4a4a4a")
            outline = item.props.get("outline", "#888888")
            self.create_rectangle(ix, iy, ix2, iy2, fill=fill, outline=outline, tags=tags)
            if is_sel:
                self.create_rectangle(ix - 1, iy - 1, ix2 + 1, iy2 + 1,
                                      outline=_CI_SEL, width=2, fill="", tags=tags)

        elif item.kind == "oval":
            fill    = item.props.get("fill", "#4a4a4a")
            outline = item.props.get("outline", "#888888")
            self.create_oval(ix, iy, ix2, iy2, fill=fill, outline=outline, tags=tags)
            if is_sel:
                self.create_rectangle(ix - 1, iy - 1, ix2 + 1, iy2 + 1,
                                      outline=_CI_SEL, width=2, fill="", tags=tags)

        elif item.kind == "text":
            text = item.props.get("text", "Text")
            fill = item.props.get("fill", "#ffffff")
            fnt  = item.props.get("font", "")
            self.create_text(ix, iy, anchor="nw", text=text, fill=fill,
                             font=fnt if fnt else (UI_FONT, 9), tags=tags)
            if is_sel:
                self.create_rectangle(ix - 2, iy - 2, ix + max(item.width, 30), iy + item.height + 2,
                                      outline=_CI_SEL, width=1, fill="", dash=(4, 2), tags=tags)

        elif item.kind == "line":
            fill  = item.props.get("fill", "#888888")
            lw    = item.props.get("linewidth", 1)
            x2pt  = ix + item.width
            y2pt  = iy + item.height
            self.create_line(ix, iy, x2pt, y2pt, fill=fill, width=lw, tags=tags)
            if is_sel:
                h = _HW // 2
                self.create_oval(ix - h, iy - h, ix + h, iy + h,
                                 fill=_CI_SEL, outline="", tags=tags)
                self.create_oval(x2pt - h, y2pt - h, x2pt + h, y2pt + h,
                                 fill=_CI_SEL, outline="", tags=tags)

        # Tag name label(s)
        if item.tags:
            label = ", ".join(item.tags[:2]) + ("…" if len(item.tags) > 2 else "")
            self.create_text(ix + 2, iy + 2, anchor="nw", text=label,
                             fill="#858585", font=(UI_FONT, 6), tags=tags)

    def _ci_draw_placeholder(self, ix, iy, ix2, iy2, label, fg, is_sel, tags) -> None:
        sel_out = _CI_SEL if is_sel else "#555555"
        self.create_rectangle(ix, iy, ix2, iy2,
                              fill="#2a3a4a", outline=sel_out,
                              dash=(4, 2) if not is_sel else (), tags=tags)
        self.create_text((ix + ix2) // 2, (iy + iy2) // 2,
                         text=label, fill=fg, font=(UI_FONT, 7), tags=tags)

    def _ci_draw_handles(self, item: CanvasItemDescriptor, wx: int, wy: int) -> None:
        """Draw resize handles around the selected canvas item."""
        ix, iy = wx + item.x, wy + item.y
        h = _HW // 2
        for name in _HANDLES:
            hcx, hcy = _handle_center(ix, iy, item.width, item.height, name)
            self.create_rectangle(hcx - h, hcy - h, hcx + h, hcy + h,
                                  fill=_CI_SEL, outline="#ffffff", width=1,
                                  tags=("ci_handle", f"ci_handle:{name}"))
            self.tag_bind(f"ci_handle:{name}", "<Enter>",
                          lambda e, n=name: self.config(cursor=_handle_cursor(n)))
            self.tag_bind(f"ci_handle:{name}", "<Leave>",
                          lambda e: self.config(
                              cursor="crosshair" if self._ci_arm_kind else "arrow"))

    # ── Canvas item hit testing ────────────────────────────────────────────────

    def _ci_handle_at(self, cx: int, cy: int) -> str | None:
        """Return handle name (e.g. 'NW') if a CI handle is at (cx, cy)."""
        for item in self.find_overlapping(cx - 1, cy - 1, cx + 1, cy + 1):
            for t in self.gettags(item):
                if t.startswith("ci_handle:"):
                    return t.split(":", 1)[1]
        return None

    def _ci_item_at(self, cx: int, cy: int, w: WidgetDescriptor) -> CanvasItemDescriptor | None:
        """Return topmost canvas item under (cx, cy) (coords relative to designer canvas)."""
        wx, wy = self._abs_xy(w)
        for item in reversed(w.canvas_items):
            ix = wx + item.x
            iy = wy + item.y
            if item.kind == "line":
                # Widen hit area for lines
                x2pt = ix + item.width
                y2pt = iy + item.height
                if min(ix, x2pt) - 4 <= cx <= max(ix, x2pt) + 4 and \
                   min(iy, y2pt) - 4 <= cy <= max(iy, y2pt) + 4:
                    return item
            else:
                if ix <= cx <= ix + max(item.width, 8) and iy <= cy <= iy + max(item.height, 8):
                    return item
        return None

    # ── Canvas item mouse handlers ─────────────────────────────────────────────

    def _ci_on_click(self, cx: float, cy: float, event: tk.Event) -> None:
        if self._form is None or self._ci_widget_id is None:
            return
        w = self._form.get_widget(self._ci_widget_id)
        if w is None:
            return
        wx, wy = self._abs_xy(w)
        inside = (wx <= cx <= wx + w.width and wy <= cy <= wy + w.height)

        # Handle resize
        if self._ci_selected_id:
            handle = self._ci_handle_at(int(cx), int(cy))
            if handle:
                item = self.get_ci_selected()
                if item:
                    self._ci_drag = {
                        "mode": "resize", "handle": handle,
                        "orig_x": item.x, "orig_y": item.y,
                        "orig_w": item.width, "orig_h": item.height,
                        "start_cx": cx, "start_cy": cy,
                    }
                return

        if not inside:
            return

        # Armed placement
        if self._ci_arm_kind:
            rel_x = max(0, int(cx - wx))
            rel_y = max(0, int(cy - wy))
            self.add_canvas_item(self._ci_arm_kind, rel_x, rel_y)
            return

        # Hit an existing item?
        item = self._ci_item_at(cx, cy, w)
        if item:
            if item.id != self._ci_selected_id:
                self._ci_selected_id = item.id
                self._ci_redraw()
                self._notify_ci_select()
            self._ci_drag = {
                "mode": "move", "start_cx": cx, "start_cy": cy,
                "orig_x": item.x, "orig_y": item.y,
            }
        else:
            self._ci_selected_id = None
            self._ci_redraw()
            self._notify_ci_select()

    def _ci_on_motion(self, cx: float, cy: float, event: tk.Event) -> None:
        d = self._ci_drag
        if d is None or not self._ci_selected_id:
            return
        w = self.get_ci_widget()
        if w is None:
            return
        item = self.get_ci_selected()
        if item is None:
            return

        dx = int(cx - d["start_cx"])
        dy = int(cy - d["start_cy"])

        if d["mode"] == "move":
            item.x = max(0, min(_snap(d["orig_x"] + dx), w.width  - max(item.width,  1)))
            item.y = max(0, min(_snap(d["orig_y"] + dy), w.height - max(item.height, 1)))

        elif d["mode"] == "resize":
            handle = d["handle"]
            ox, oy_ = d["orig_x"], d["orig_y"]
            ow, oh  = d["orig_w"], d["orig_h"]
            nx, ny_, nw, nh = ox, oy_, ow, oh
            if "W" in handle:
                raw = ox + dx
                nx  = _snap(raw)
                nw  = max(GRID, ow - (nx - ox))
            if "E" in handle:
                nw = max(GRID, _snap(ow + dx))
            if "N" in handle:
                raw = oy_ + dy
                ny_ = _snap(raw)
                nh  = max(GRID, oh - (ny_ - oy_))
            if "S" in handle:
                nh = max(GRID, _snap(oh + dy))
            item.x, item.y = max(0, nx), max(0, ny_)
            item.width, item.height = nw, nh

        self._ci_redraw()

    def _ci_on_release(self, cx: float, cy: float, event: tk.Event) -> None:
        if self._ci_drag and self._ci_drag.get("mode") in ("move", "resize"):
            self._ci_drag = None
            if self._on_widget_changed and self._ci_widget_id and self._form:
                wgt = self._form.get_widget(self._ci_widget_id)
                if wgt:
                    self._on_widget_changed(wgt)

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
        # Walk forward to the first widget that has canvas items (inactive notebook
        # tab children are absent from the canvas, so skip them).
        for next_id in ids[idx + 1:]:
            if self.find_withtag(f"widget:{next_id}"):
                self.tag_lower(f"widget:{widget_id}", f"widget:{next_id}")
                return

    def _render_widget(self, w: WidgetDescriptor) -> None:
        tag   = f"widget:{w.id}"
        x, y  = self._abs_xy(w)
        x2    = x + w.width
        y2    = y + w.height
        props = w.props
        text  = str(props.get("text", w.id))

        if REGISTRY.get(w.type, {}).get("is_notebook"):
            tabs   = w.props.get("tabs") or ["Tab 1"]
            active = self._active_nb_tabs.get(w.id, tabs[0])
            _draw_notebook_canvas(self, x, y, x2, y2, props, tag, w.id, active)
        else:
            _DRAW.get(w.type, _draw_generic)(self, x, y, x2, y2, text, props, tag)

        # Ghost previews of Image component canvas buttons targeting this widget
        if w.type == "Canvas" and self._form:
            self._draw_canvas_btn_ghosts(w, x, y, tag)
            if w.canvas_items:
                self._draw_ci_items_preview(w, x, y, tag)

        # Bind click → select on every newly created item
        for item in self.find_withtag(tag):
            self.tag_bind(item, "<Button-1>",
                          lambda e, wid=w.id: self._widget_clicked(e, wid))
            item_tags = self.gettags(item)
            if any(t.startswith("nbtab:") for t in item_tags):
                # Tab strip headers: pointer cursor regardless of armed state
                self.tag_bind(item, "<Enter>",
                              lambda e: self.config(cursor="hand2"))
                self.tag_bind(item, "<Leave>",
                              lambda e: self.config(
                                  cursor="crosshair" if self._active_tool else "arrow"))
            else:
                self.tag_bind(item, "<Enter>",
                              lambda e, wid=w.id: self._widget_enter(e, wid))
                self.tag_bind(item, "<Leave>",
                              lambda e, wid=w.id: self._widget_leave(e, wid))

    def _draw_ci_items_preview(self, w: "WidgetDescriptor", wx: int, wy: int, tag: str) -> None:
        """Draw canvas items on a Canvas widget in normal (non-CI-edit) designer view."""
        for item in w.canvas_items:
            ix  = wx + item.x
            iy  = wy + item.y
            ix2 = ix + item.width
            iy2 = iy + item.height
            ptag = (tag, f"ci_preview:{item.id}")
            if item.kind == "image":
                img_path = item.props.get("image_path", "")
                if img_path and item.width > 0 and item.height > 0:
                    photo = _load_preview_image(self, img_path, item.width, item.height)
                    if photo:
                        self.create_image(ix, iy, anchor="nw", image=photo, tags=ptag)
                        continue
                self.create_rectangle(ix, iy, ix2, iy2, fill="#2a3a4a",
                                      outline="#444444", tags=ptag)
                self.create_text((ix + ix2) // 2, (iy + iy2) // 2,
                                 text="[img]", fill="#ce9178",
                                 font=(UI_FONT, 7), tags=ptag)
            elif item.kind == "rectangle":
                self.create_rectangle(ix, iy, ix2, iy2,
                                      fill=item.props.get("fill", "#4a4a4a"),
                                      outline=item.props.get("outline", "#888888"),
                                      tags=ptag)
            elif item.kind == "oval":
                self.create_oval(ix, iy, ix2, iy2,
                                 fill=item.props.get("fill", "#4a4a4a"),
                                 outline=item.props.get("outline", "#888888"),
                                 tags=ptag)
            elif item.kind == "text":
                fnt = item.props.get("font", "")
                self.create_text(ix, iy, anchor="nw",
                                 text=item.props.get("text", "Text"),
                                 fill=item.props.get("fill", "#ffffff"),
                                 font=fnt if fnt else (UI_FONT, 9), tags=ptag)
            elif item.kind == "line":
                self.create_line(ix, iy, ix + item.width, iy + item.height,
                                 fill=item.props.get("fill", "#888888"),
                                 width=item.props.get("linewidth", 1), tags=ptag)

    def _draw_canvas_btn_ghosts(self, w: "WidgetDescriptor", wx: int, wy: int, tag: str) -> None:
        """Draw ghost images of canvas_button placements from Image components."""
        if not self._form:
            return
        for comp in self._form.components:
            if comp.type != "Image":
                continue
            paths = comp.props.get("paths") or []
            stems = [__import__("os").path.splitext(__import__("os").path.basename(p))[0]
                     for p in paths]
            is_multi = len(paths) > 1
            for btn in (comp.props.get("canvas_buttons") or []):
                if btn.get("canvas_id") != w.id:
                    continue
                nk = btn.get("normal_key", "")
                bx, by = btn.get("x", 0), btn.get("y", 0)
                btn_tag = btn.get("tag", "")
                # Resolve path for normal image
                if is_multi and nk:
                    idx = next((i for i, s in enumerate(stems) if s == nk), 0)
                    path = paths[idx] if idx < len(paths) else ""
                elif paths:
                    path = paths[0]
                else:
                    path = ""
                if not path:
                    continue
                photo = _load_natural_image(self, path)
                if photo:
                    self.create_image(wx + bx, wy + by, anchor="nw", image=photo, tags=tag)
                    # Dim label showing tag name
                    self.create_text(wx + bx + 2, wy + by + 2,
                                     text=btn_tag, anchor="nw",
                                     fill="#ce9178", font=(UI_FONT, 7), tags=tag)

    # ── Selection handles ─────────────────────────────────────────────────────

    def _draw_handles(self, w: WidgetDescriptor, color: str = _PRIMARY) -> None:
        x, y = self._abs_xy(w)
        hw = w.width
        hh = w.height
        h  = _HW // 2

        # Selection dashed border
        self.create_rectangle(x - 1, y - 1, x + hw + 1, y + hh + 1,
                               outline=color, width=1, dash=(4, 3),
                               fill="", tags="handle")

        for name in _HANDLES:
            cx, cy = _handle_center(x, y, hw, hh, name)
            self.create_rectangle(cx - h, cy - h, cx + h + 1, cy + h + 1,
                                   fill="#ffffff", outline=color, width=1,
                                   tags=("handle", f"handle:{name}"))
            self.tag_bind(f"handle:{name}", "<Enter>",
                          lambda e, n=name: None if self._active_tool else self.config(cursor=_handle_cursor(n)))
            self.tag_bind(f"handle:{name}", "<Leave>",
                          lambda e: None if self._active_tool else self.config(cursor="arrow"))

    def _draw_all_handles(self) -> None:
        """Draw selection handles for all selected widgets.

        Primary widget: full resize handles in amber (_PRIMARY).
        Secondary widgets: dashed border only in blue (_SEL).
        """
        self.delete("handle")
        if not self._form:
            return
        # Secondaries first (drawn below primary handles in z-order)
        for wid in self._selected_ids:
            if wid == self._primary_id:
                continue
            w = self._form.get_widget(wid)
            if w is None:
                continue
            x, y = self._abs_xy(w)
            self.create_rectangle(x - 1, y - 1, x + w.width + 1, y + w.height + 1,
                                   outline=_SEL, width=1, dash=(4, 3),
                                   fill="", tags="handle")
        # Primary: full handles on top
        if self._primary_id:
            w = self._form.get_widget(self._primary_id)
            if w:
                self._draw_handles(w)

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
            cx, cy = _handle_center(ox, ty, f.width, f.height + _TITLE, name)
            self.create_rectangle(cx - h, cy - h, cx + h + 1, cy + h + 1,
                                   fill="#ffffff", outline=_SEL, width=1,
                                   tags=("fhandle", f"fhandle:{name}"))
            self.tag_bind(f"fhandle:{name}", "<Enter>",
                          lambda e, n=name: None if self._active_tool else self.config(cursor=_handle_cursor(n)))
            self.tag_bind(f"fhandle:{name}", "<Leave>",
                          lambda e: None if self._active_tool else self.config(cursor="arrow"))

    # ── Mouse events ──────────────────────────────────────────────────────────

    def _on_click(self, event: tk.Event) -> None:
        self.focus_set()
        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        if self._ci_mode:
            self._ci_on_click(cx, cy, event)
            return

        # Notebook tab-strip click — always intercept before any tool logic
        item = self._topmost_at(cx, cy)
        if item is not None:
            for t in self.gettags(item):
                if t.startswith("nbtab:"):
                    _, nb_id, tab_name = t.split(":", 2)
                    self._switch_nb_tab(nb_id, tab_name)
                    return

        # Placement mode: drop a new widget at the click position
        if self._active_tool and self._form:
            # If clicking a non-container widget, de-arm so the user can drag it
            # immediately. Clicking a Frame/LabelFrame keeps the tool armed — the
            # draw begins inside the container.
            if item is not None:
                tags = self.gettags(item)
                if any(t.startswith("widget:") for t in tags):
                    wid_under = next((t.split(":", 1)[1] for t in tags if t.startswith("widget:")), None)
                    w_under = self._form.get_widget(wid_under) if wid_under else None
                    if not (w_under and REGISTRY.get(w_under.type, {}).get("is_container")):
                        self.cancel_tool()
                        # fall through to normal hit-testing below
            if self._active_tool:  # still armed → begin draw drag
                self._drag = {
                    "mode":      "draw_widget",
                    "start_cx":  cx,
                    "start_cy":  cy,
                    "container": self._container_at(cx, cy),
                }
                return
            # Tool was cancelled (clicked on widget) → fall through to normal handling

        # Menu bar hitbox check (before regular hit testing)
        for (hx1, hy1, hx2, hy2, item_idx) in self._menu_hitboxes:
            if hx1 <= cx <= hx2 and hy1 <= cy <= hy2:
                self._show_menu_popup(event, item_idx)
                return

        if item is None:
            self.deselect()
            return

        tags = self.gettags(item)

        # Form handle click → start form resize
        fhandle_tag = next((t for t in tags if t.startswith("fhandle:")), None)
        if fhandle_tag:
            handle_name = fhandle_tag.split(":", 1)[1]
            if self._form:
                self.push_undo()
                self._drag = {
                    "mode":     "form_resize",
                    "handle":   handle_name,
                    "start_cx": cx, "start_cy": cy,
                    "orig_w":   self._form.width,
                    "orig_h":   self._form.height,
                    "orig_ox":  self._ox,
                    "orig_oy":  self._oy,
                    "orig_widget_geoms": {
                        w.id: (w.x, w.y, w.width, w.height)
                        for w in self._form.widgets
                        if w.anchor and w.anchor not in ("", "top_left")
                    },
                    "orig_parent_sizes": {
                        w.id: (p.width, p.height)
                        for w in self._form.widgets
                        if w.anchor and w.anchor not in ("", "top_left") and w.parent_id
                        if (p := self._form.get_widget(w.parent_id)) is not None
                    },
                }
            return

        # Widget handle click → start resize (primary widget; delta propagates to secondaries)
        handle_tag = next((t for t in tags if t.startswith("handle:")), None)
        if handle_tag:
            handle_name = handle_tag.split(":", 1)[1]
            if self._primary_id and self._form:
                w = self._form.get_widget(self._primary_id)
                if w:
                    self.push_undo()
                    orig_others = {
                        sid: (sw.x, sw.y, sw.width, sw.height)
                        for sid in self._selected_ids
                        if sid != self._primary_id
                        and (sw := self._form.get_widget(sid)) is not None
                    }
                    self._drag = {
                        "mode":    "resize",
                        "handle":  handle_name,
                        "id":      w.id,
                        "start_cx": cx, "start_cy": cy,
                        "orig_x": w.x, "orig_y": w.y,
                        "orig_w": w.width, "orig_h": w.height,
                        "orig_others": orig_others,
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
                    self.push_undo()
                    orig_positions = {
                        sid: (sw.x, sw.y)
                        for sid in self._selected_ids
                        if (sw := self._form.get_widget(sid))
                    }
                    self._drag = {
                        "mode":          "move",
                        "id":            wid,
                        "start_cx":      cx, "start_cy": cy,
                        "orig_x":        w.x, "orig_y":  w.y,
                        "orig_positions": orig_positions,
                        "parent_locked": bool(w.parent_id),
                    }
            return

        # Title bar click → select form and show resize handles
        if "titlebar" in tags:
            self.select_form()
            return

        # Clicked form body, grid, or menu bar background → rubber-band select
        if any(t in ("form_bg", "grid", "menu_bar") for t in tags):
            if not ctrl:
                self._selected_ids.clear()
                self._primary_id = None
                self.delete("handle")
                self.delete("fhandle")
            self._drag = {
                "mode":     "rubber_band",
                "start_cx": cx, "start_cy": cy,
                "ctrl":     ctrl,
                "prev_ids": set(self._selected_ids),
            }
            return

        self.deselect()

    def _on_double_click_evt(self, event: tk.Event) -> None:
        if self._ci_mode:
            return
        if self._primary_id and self._form:
            w = self._form.get_widget(self._primary_id)
            if w and w.type == "Canvas":
                self.enter_canvas_item_mode(self._primary_id)
                return
        if self._on_double_click and self._primary_id:
            self._on_double_click(self._primary_id)

    def _on_motion(self, event: tk.Event) -> None:
        if self._ci_mode:
            self._ci_on_motion(self.canvasx(event.x), self.canvasy(event.y), event)
            return
        d = self._drag
        if d is None or self._form is None:
            return

        cx, cy = self.canvasx(event.x), self.canvasy(event.y)
        dx = cx - d["start_cx"]
        dy = cy - d["start_cy"]

        if d["mode"] == "form_resize":
            f      = self._form
            handle = d["handle"]
            ow, oh = d["orig_w"], d["orig_h"]
            oox, ooy = d["orig_ox"], d["orig_oy"]
            nw, nh   = ow, oh
            nox, noy = oox, ooy

            shift_held = bool(event.state & 0x0001)
            _s = (lambda v: int(v)) if shift_held else _snap

            if "E" in handle:
                nw = _s(ow + dx)
            if "W" in handle:
                nw  = _s(ow - dx)
                nox = oox + (ow - nw)
            if "S" in handle:
                nh = _s(oh + dy)
            if "N" in handle:
                nh  = _s(oh - dy)
                noy = ooy + (oh - nh)

            f.width  = max(GRID * 8, nw)
            f.height = max(GRID * 8, nh)
            self._ox = nox
            self._oy = noy

            # Reposition anchored widgets unless Shift is held (suppress anchors)
            if not shift_held:
                orig_fw = d["orig_w"]
                orig_fh = d["orig_h"]
                orig_par_sizes = d.get("orig_parent_sizes", {})
                for widget in f.widgets:
                    geom = d["orig_widget_geoms"].get(widget.id)
                    if geom:
                        if widget.parent_id:
                            # Anchor is relative to parent, not the form.
                            # Parents appear before children in form.widgets
                            # (via _reorder_after_parent), so par.width/height
                            # already reflects any anchor the parent itself had.
                            par = f.get_widget(widget.parent_id)
                            if par:
                                orig_pw, orig_ph = orig_par_sizes.get(widget.id, (par.width, par.height))
                                lh = _LF_LABEL_H if par.type == "LabelFrame" else 0
                                nx, ny, nww, nwh = _anchor_geom(
                                    geom, widget.anchor,
                                    orig_pw, orig_ph - lh,
                                    par.width, par.height - lh,
                                )
                            else:
                                nx, ny, nww, nwh = _anchor_geom(
                                    geom, widget.anchor, orig_fw, orig_fh, f.width, f.height)
                        else:
                            nx, ny, nww, nwh = _anchor_geom(
                                geom, widget.anchor, orig_fw, orig_fh, f.width, f.height)
                        widget.x, widget.y = nx, ny
                        widget.width, widget.height = max(GRID, nww), max(GRID, nwh)

            self.delete("all")
            self._draw_form()
            for widget in f.widgets:
                if self._should_render(widget):
                    self._render_widget(widget)
            self._draw_form_handles()
            self.tag_raise("fhandle")
            return

        if d["mode"] == "rubber_band":
            x0, y0 = d["start_cx"], d["start_cy"]
            # Delete old rubber-band rect if any
            self.delete("rubber_band")
            self.create_rectangle(min(x0, cx), min(y0, cy),
                                   max(x0, cx), max(y0, cy),
                                   outline=_SEL, dash=(4, 3), fill="",
                                   width=1, tags="rubber_band")
            return

        if d["mode"] == "draw_widget" and self._form:
            self.delete("draw_preview")
            x0 = min(d["start_cx"], cx)
            y0 = min(d["start_cy"], cy)
            x1 = max(d["start_cx"], cx)
            y1 = max(d["start_cy"], cy)
            # Clamp preview rect to container bounds (if draw started inside one)
            # or form bounds otherwise.
            container = d.get("container")
            if container:
                ax, ay = self._abs_xy(container)
                if REGISTRY.get(container.type, {}).get("is_notebook"):
                    lh = _NB_TAB_H
                elif container.type == "LabelFrame":
                    lh = _LF_LABEL_H
                else:
                    lh = 0
                x0 = max(ax, x0)
                y0 = max(ay + lh, y0)
                x1 = min(ax + container.width, x1)
                y1 = min(ay + container.height, y1)
            else:
                x0 = max(self._ox, x0)
                y0 = max(self._oy + self._min_y, y0)
                x1 = min(self._ox + self._form.width, x1)
                y1 = min(self._oy + self._form.height, y1)
            if x1 > x0 and y1 > y0:
                self.create_rectangle(x0, y0, x1, y1,
                                      outline=_SEL, dash=(4, 3), fill="",
                                      width=1, tags="draw_preview")
            return

        w = self._form.get_widget(d["id"])
        if w is None:
            return

        if d["mode"] == "move":
            _s = (lambda v: int(v)) if (event.state & 0x0001) else _snap
            new_x = _s(d["orig_x"] + dx)
            new_y = _s(d["orig_y"] + dy)
            # Parented widgets move freely during drag so they can escape the
            # container — _try_reparent on release handles final clamping.
            if not w.parent_id:
                new_x = max(0,            min(new_x, self._form.width  - w.width))
                new_y = max(self._min_y, min(new_y, self._form.height - w.height))
            # Actual snapped delta (may differ from raw dx/dy due to clamping)
            actual_dx = new_x - d["orig_x"]
            actual_dy = new_y - d["orig_y"]
            # Move all selected widgets by the same delta
            selected_ids = set(d["orig_positions"].keys())
            rendered: set[str] = set()
            for sid, (ox, oy) in d["orig_positions"].items():
                sw = self._form.get_widget(sid)
                if sw is None:
                    continue
                # If this widget's parent is also selected, skip the delta update —
                # the parent's movement already carries it.  It will be re-rendered
                # by the parent's _children_of loop below.
                if sw.parent_id and sw.parent_id in selected_ids:
                    continue
                if sw.parent_id:
                    par = self._form.get_widget(sw.parent_id)
                    # Single-widget drag: lock to parent until mouse exits parent bounds
                    if par and d.get("parent_locked") and len(d["orig_positions"]) == 1:
                        par_ax, par_ay = self._abs_xy(par)
                        if not (par_ax <= cx <= par_ax + par.width and
                                par_ay <= cy <= par_ay + par.height):
                            d["parent_locked"] = False
                    if par and d.get("parent_locked"):
                        if REGISTRY.get(par.type, {}).get("is_notebook"):
                            lh = _NB_TAB_H
                        elif par.type == "LabelFrame":
                            lh = _LF_LABEL_H
                        else:
                            lh = 0
                        sw.x = max(0, min(ox + actual_dx, par.width  - sw.width))
                        sw.y = max(0, min(oy + actual_dy, par.height - lh - sw.height))
                    else:
                        sw.x = ox + actual_dx
                        sw.y = oy + actual_dy
                else:
                    sw.x = max(0,            min(ox + actual_dx, self._form.width  - sw.width))
                    sw.y = max(self._min_y, min(oy + actual_dy, self._form.height - sw.height))
                self.delete(f"widget:{sid}")
                self._render_widget(sw)
                self._restore_z_order(sid)
                rendered.add(sid)
                # If moving a container, visually update its children too
                for child in self._descendants_of(sid):
                    if child.id not in rendered:
                        self.delete(f"widget:{child.id}")
                        if self._should_render(child):
                            self._render_widget(child)
                            self._restore_z_order(child.id)
                        rendered.add(child.id)

        elif d["mode"] == "resize":
            handle = d["handle"]
            ox, oy = d["orig_x"], d["orig_y"]
            ow, oh = d["orig_w"], d["orig_h"]

            nx, ny, nw, nh = ox, oy, ow, oh

            shift_held = bool(event.state & 0x0001)
            _s = (lambda v: int(v)) if shift_held else _snap

            if "W" in handle:
                nw = _s(ow - dx)
                nx = _s(ox + dx)
            if "E" in handle:
                nw = _s(ow + dx)
            if "N" in handle:
                nh = _s(oh - dy)
                ny = max(self._min_y, _s(oy + dy))
                nh = oy + oh - ny  # recalculate height after ny clamp
                nh = max(GRID * 2, nh)
            if "S" in handle:
                nh = _s(oh + dy)

            nw = max(GRID * 2, nw)
            nh = max(GRID * 2, nh)

            # Clamp resize within parent container if widget has one
            if w.parent_id:
                par = self._form.get_widget(w.parent_id)
                if par:
                    if REGISTRY.get(par.type, {}).get("is_notebook"):
                        lh = _NB_TAB_H
                    elif par.type == "LabelFrame":
                        lh = _LF_LABEL_H
                    else:
                        lh = 0
                    nx = max(0, min(nx, par.width  - GRID * 2))
                    ny = max(0, min(ny, par.height - lh - GRID * 2))
                    nw = max(GRID * 2, min(nw, par.width  - nx))
                    nh = max(GRID * 2, min(nh, par.height - lh - ny))

            # Deltas to propagate to secondaries
            ddx = nx - ox
            ddy = ny - oy
            ddw = nw - ow
            ddh = nh - oh

            w.x, w.y, w.width, w.height = nx, ny, nw, nh
            self.delete(f"widget:{w.id}")
            self._render_widget(w)
            self._restore_z_order(w.id)

            # Apply same delta to all other selected widgets
            for sid, (sox, soy, sow, soh) in d.get("orig_others", {}).items():
                sw = self._form.get_widget(sid)
                if sw is None:
                    continue
                sw.x      = sox + ddx
                sw.y      = max(self._min_y, soy + ddy)
                sw.width  = max(GRID * 2, sow + ddw)
                sw.height = max(GRID * 2, soh + ddh)
                self.delete(f"widget:{sw.id}")
                self._render_widget(sw)
                self._restore_z_order(sw.id)

        if self._tab_order_visible:
            self.delete("tab_badge")
            self._draw_tab_badges()
        self.delete("handle")
        self._draw_all_handles()
        self.tag_raise("handle")

    def _on_release(self, event: tk.Event) -> None:
        if self._ci_mode:
            self._ci_on_release(self.canvasx(event.x), self.canvasy(event.y), event)
            return
        d = self._drag
        self._drag = None
        if self._shift_snap_override:
            self._shift_snap_override = False
            if self._on_snap_state_changed:
                self._on_snap_state_changed()
        if not self._active_tool:
            # If the pointer is still over a resize handle, restore that cursor
            # (handle <Enter> won't re-fire since the pointer never left)
            _cx = self.canvasx(event.x)
            _cy = self.canvasy(event.y)
            _hc = next(
                (_handle_cursor(t.split(":", 1)[1])
                 for item in self.find_overlapping(_cx - 2, _cy - 2, _cx + 2, _cy + 2)
                 for t in self.gettags(item)
                 if t.startswith("handle:") or t.startswith("fhandle:")),
                None,
            )
            self.config(cursor=_hc or "arrow")
        if d is None or self._form is None:
            return

        cx, cy = self.canvasx(event.x), self.canvasy(event.y)

        if d["mode"] == "draw_widget":
            self.delete("draw_preview")
            if not self._active_tool:
                return
            reg = REGISTRY.get(self._active_tool)
            if not reg:
                return
            shift_held = bool(event.state & 0x0001)
            _s = (lambda v: int(v)) if shift_held else _snap
            _min_sz = 1 if shift_held else GRID * 2
            dx = abs(cx - d["start_cx"])
            dy = abs(cy - d["start_cy"])
            tab_name = ""
            if dx > 5 or dy > 5:
                # Drawn: use the dragged rectangle as the widget bounds
                cx1 = min(d["start_cx"], cx)
                cy1 = min(d["start_cy"], cy)
                cx2 = max(d["start_cx"], cx)
                cy2 = max(d["start_cy"], cy)
                container = self._container_at((cx1 + cx2) // 2, (cy1 + cy2) // 2)
                if container:
                    ax, ay = self._abs_xy(container)
                    if REGISTRY.get(container.type, {}).get("is_notebook"):
                        label_h = _NB_TAB_H
                        tabs = container.props.get("tabs", [])
                        tab_name = self._active_nb_tabs.get(container.id, tabs[0] if tabs else "")
                    elif container.type == "LabelFrame":
                        label_h = _LF_LABEL_H
                    else:
                        label_h = 0
                    fw = max(_min_sz, _s(cx2 - cx1))
                    fh = max(_min_sz, _s(cy2 - cy1))
                    fx = _s(cx1 - ax)
                    fy = _s(cy1 - ay - label_h)
                    fx = max(0, min(fx, container.width  - fw))
                    fy = max(0, min(fy, container.height - label_h - fh))
                    parent_id = container.id
                else:
                    fw = max(_min_sz, _s(cx2 - cx1))
                    fh = max(_min_sz, _s(cy2 - cy1))
                    fx = _s(cx1 - self._ox)
                    fy = _s(cy1 - self._oy)
                    fx = max(0,           min(fx, self._form.width  - fw))
                    fy = max(self._min_y, min(fy, self._form.height - fh))
                    parent_id = None
            else:
                # Click: drop at default size centered on click point
                fw, fh = reg["default_size"]
                container = self._container_at(d["start_cx"], d["start_cy"])
                if container:
                    ax, ay = self._abs_xy(container)
                    if REGISTRY.get(container.type, {}).get("is_notebook"):
                        label_h = _NB_TAB_H
                        tabs = container.props.get("tabs", [])
                        tab_name = self._active_nb_tabs.get(container.id, tabs[0] if tabs else "")
                    elif container.type == "LabelFrame":
                        label_h = _LF_LABEL_H
                    else:
                        label_h = 0
                    fx = _s(d["start_cx"] - ax)
                    fy = _s(d["start_cy"] - ay - label_h)
                    fx = max(0, min(fx, container.width  - fw))
                    fy = max(0, min(fy, container.height - label_h - fh))
                    parent_id = container.id
                else:
                    fx = _s(d["start_cx"] - self._ox)
                    fy = _s(d["start_cy"] - self._oy)
                    fx = max(0,           min(fx, self._form.width  - fw))
                    fy = max(self._min_y, min(fy, self._form.height - fh))
                    parent_id = None
            wid = self._form.next_id(self._active_tool)
            desc = WidgetDescriptor(
                id=wid, type=self._active_tool,
                x=fx, y=fy, width=fw, height=fh,
                props=dict(reg["default_props"]),
                parent_id=parent_id,
                tab=tab_name,
            )
            self.add_widget(desc)
            if parent_id:
                self._reorder_after_parent(wid, parent_id)
            # If a Notebook was just placed, initialise its active tab
            if REGISTRY.get(self._active_tool, {}).get("is_notebook"):
                tabs = desc.props.get("tabs", [])
                if tabs:
                    self._active_nb_tabs[wid] = tabs[0]
            # Stay in placement mode
            return

        if d["mode"] == "rubber_band":
            self.delete("rubber_band")
            x0 = min(d["start_cx"], cx)
            y0 = min(d["start_cy"], cy)
            x1 = max(d["start_cx"], cx)
            y1 = max(d["start_cy"], cy)
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
            self._reposition()
            if self._on_form_changed:
                self._on_form_changed(self._form)
        elif d["mode"] in ("move", "resize"):
            w = self._form.get_widget(d["id"])
            if w:
                if d["mode"] == "move":
                    self._try_reparent(w)
                    self._paste_offset = 0   # repositioning signals a new paste cycle
                if self._on_widget_changed:
                    self._on_widget_changed(w)
            if d["mode"] == "resize" and self._on_widget_changed:
                for sid in d.get("orig_others", {}):
                    sw = self._form.get_widget(sid)
                    if sw:
                        self._on_widget_changed(sw)

    def _on_shift_press(self, event: tk.Event) -> None:
        if not self._shift_snap_override:
            self._shift_snap_override = True
            if self._on_snap_state_changed:
                self._on_snap_state_changed()

    def _on_shift_release(self, event: tk.Event) -> None:
        if self._shift_snap_override:
            self._shift_snap_override = False
            if self._on_snap_state_changed:
                self._on_snap_state_changed()

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
            # Moving into a container: make coords relative to its content area
            p = self._form.get_widget(new_pid)
            label_h = _LF_LABEL_H if p.type == "LabelFrame" else 0
            p_abs_x, p_abs_y = self._abs_xy(p)
            w.x = max(0, min(abs_x - (p_abs_x - self._ox), p.width  - w.width))
            w.y = max(0, min(abs_y - (p_abs_y - self._oy) - label_h, p.height - label_h - w.height))
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
        item = self._topmost_at(self.canvasx(event.x), self.canvasy(event.y))
        if item is None:
            if self._hover_id:
                self._clear_hover()
            return
        tags = self.gettags(item)
        # nbtab items: always pointer (tab switching, not widget placement)
        if any(t.startswith("nbtab:") for t in tags):
            if self._hover_id:
                self._clear_hover()
            self.config(cursor="hand2")
            return

        widget_tag = next((t for t in tags if t.startswith("widget:")), None)
        if widget_tag:
            wid = widget_tag.split(":", 1)[1]
            if wid != self._hover_id:
                self._clear_hover()
                self._hover_id = wid
                if self._active_tool:
                    w_h = self._form.get_widget(wid) if self._form else None
                    if w_h and REGISTRY.get(w_h.type, {}).get("is_container"):
                        self.config(cursor="crosshair")
                    else:
                        self.config(cursor="hand2")
                else:
                    self.config(cursor="fleur")
        elif not any(t.startswith("handle:") or t.startswith("fhandle:") for t in tags):
            self._clear_hover()

    def _widget_clicked(self, event: tk.Event, wid: str) -> None:
        pass  # handled by _on_click via tag binding

    def _widget_enter(self, event: tk.Event, wid: str) -> None:
        if self._active_tool:
            w = self._form.get_widget(wid) if self._form else None
            if w and REGISTRY.get(w.type, {}).get("is_container"):
                self.config(cursor="crosshair")
            else:
                self.config(cursor="hand2")
        else:
            self.config(cursor="fleur")

    def _widget_leave(self, event: tk.Event, wid: str) -> None:
        if self._drag is None:
            self.config(cursor="crosshair" if self._active_tool else "arrow")

    def _clear_hover(self) -> None:
        self._hover_id = None
        self.config(cursor="crosshair" if self._active_tool else "arrow")

    def _show_menu_popup(self, event: tk.Event, top_idx: int) -> None:
        """Show a dropdown for the top-level menu item at top_idx."""
        items = self._form.menu_items
        menu = tk.Menu(self, tearoff=0,
                       bg="#ffffff", fg="#111111",
                       activebackground="#0078d4", activeforeground="#ffffff",
                       relief="flat", bd=1, font=(UI_FONT, 9))

        def _ul(item):
            u = item.underline_index
            return {"underline": u} if u >= 0 else {}

        def _sc(item):
            return {"accelerator": item.shortcut} if item.shortcut else {}

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
                                  relief="flat", bd=1, font=(UI_FONT, 9))
                    j = i + 1
                    while j < len(items) and items[j].indent > 1:
                        si = items[j]
                        if si.caption == "-":
                            sub.add_separator()
                        elif si.kind == "checkbutton":
                            if si.command_handler:
                                sub.add_checkbutton(label=si.display_caption,
                                                    command=lambda m=f"_{si.command_handler}_click": self._navigate_menu(m),
                                                    **_ul(si), **_sc(si))
                            else:
                                sub.add_checkbutton(label=si.display_caption,
                                                    foreground="#888888", activeforeground="#cccccc",
                                                    command=lambda idx=j: self._navigate_menu_no_command(idx),
                                                    **_ul(si), **_sc(si))
                        elif si.kind == "radiobutton":
                            if si.command_handler:
                                sub.add_radiobutton(label=si.display_caption,
                                                    command=lambda m=f"_{si.command_handler}_click": self._navigate_menu(m),
                                                    **_ul(si), **_sc(si))
                            else:
                                sub.add_radiobutton(label=si.display_caption,
                                                    foreground="#888888", activeforeground="#cccccc",
                                                    command=lambda idx=j: self._navigate_menu_no_command(idx),
                                                    **_ul(si), **_sc(si))
                        elif si.name:
                            sub.add_command(label=si.display_caption,
                                            command=lambda m=f"_{si.name}_click": self._navigate_menu(m),
                                            **_ul(si), **_sc(si))
                        else:
                            sub.add_command(label=si.display_caption, state="disabled", **_ul(si))
                        j += 1
                    menu.add_cascade(label=item.display_caption, menu=sub, **_ul(item))
                    i = j
                    continue
                elif item.kind == "checkbutton":
                    if item.command_handler:
                        menu.add_checkbutton(label=item.display_caption,
                                             command=lambda m=f"_{item.command_handler}_click": self._navigate_menu(m),
                                             **_ul(item), **_sc(item))
                    else:
                        menu.add_checkbutton(label=item.display_caption,
                                             foreground="#888888", activeforeground="#cccccc",
                                             command=lambda idx=i: self._navigate_menu_no_command(idx),
                                             **_ul(item), **_sc(item))
                elif item.kind == "radiobutton":
                    if item.command_handler:
                        menu.add_radiobutton(label=item.display_caption,
                                             command=lambda m=f"_{item.command_handler}_click": self._navigate_menu(m),
                                             **_ul(item), **_sc(item))
                    else:
                        menu.add_radiobutton(label=item.display_caption,
                                             foreground="#888888", activeforeground="#cccccc",
                                             command=lambda idx=i: self._navigate_menu_no_command(idx),
                                             **_ul(item), **_sc(item))
                elif item.name:
                    menu.add_command(label=item.display_caption,
                                     command=lambda m=f"_{item.name}_click": self._navigate_menu(m),
                                     **_ul(item), **_sc(item))
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

    def _navigate_menu_no_command(self, item_idx: int) -> None:
        if self._on_menu_item_no_command:
            self._on_menu_item_no_command(item_idx)

    def _on_right_click(self, event: tk.Event) -> None:
        import tkinter as _tk
        _rcx, _rcy = self.canvasx(event.x), self.canvasy(event.y)
        menu = _tk.Menu(self, tearoff=0)

        # ── Canvas item edit mode context menu ────────────────────────────────
        if self._ci_mode:
            w = self.get_ci_widget()
            has_item = bool(self._ci_selected_id)
            cx_inside = bool(w and self._abs_xy(w)[0] <= _rcx <= self._abs_xy(w)[0] + w.width and
                             self._abs_xy(w)[1] <= _rcy <= self._abs_xy(w)[1] + w.height)
            rel_x = max(0, int(_rcx - (self._abs_xy(w)[0] if w else 0)))
            rel_y = max(0, int(_rcy - (self._abs_xy(w)[1] if w else 0)))

            add_sub = _tk.Menu(menu, tearoff=0)
            for kind, label in [("image", "Image"), ("rectangle", "Rectangle"),
                                 ("oval", "Oval"), ("text", "Text"), ("line", "Line")]:
                add_sub.add_command(
                    label=label,
                    state="normal" if cx_inside else "disabled",
                    command=lambda k=kind, rx=rel_x, ry=rel_y: self.add_canvas_item(k, rx, ry),
                )
            menu.add_cascade(label="Add Item", menu=add_sub)
            menu.add_separator()
            menu.add_command(label="Delete Item",
                             state="normal" if has_item else "disabled",
                             command=lambda: self.remove_canvas_item(self._ci_selected_id))
            menu.add_separator()
            menu.add_command(label="Exit Canvas Edit  (Esc)",
                             command=self.exit_canvas_item_mode)
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
            return

        # ── Normal designer context menu ──────────────────────────────────────
        item = self._topmost_at(_rcx, _rcy)
        if item:
            tags = self.gettags(item)
            widget_tag = next((t for t in tags if t.startswith("widget:")), None)
            if widget_tag:
                wid = widget_tag.split(":", 1)[1]
                if wid not in self._selected_ids:
                    self.select(wid)

        has_sel  = bool(self._selected_ids)
        has_clip = self._clipboard is not None

        # "Edit Canvas Items" at top when a single Canvas widget is selected
        if self._primary_id and self._form and not self._selected_ids - {self._primary_id}:
            pw = self._form.get_widget(self._primary_id)
            if pw and pw.type == "Canvas":
                menu.add_command(label="Edit Canvas Items",
                                 command=lambda: self.enter_canvas_item_mode(self._primary_id))
                menu.add_separator()

        menu.add_command(
            label="Undo",
            state="normal" if self.can_undo else "disabled",
            command=self.undo,
            accelerator="Ctrl+Z",
        )
        menu.add_command(
            label="Redo",
            state="normal" if self.can_redo else "disabled",
            command=self.redo,
            accelerator="Ctrl+Y",
        )
        menu.add_separator()
        menu.add_command(
            label="Copy",
            state="normal" if has_sel else "disabled",
            command=self.copy_selected,
            accelerator="Ctrl+C",
        )
        menu.add_command(
            label="Paste",
            state="normal" if has_clip else "disabled",
            command=lambda: self.paste(_rcx, _rcy),
            accelerator="Ctrl+V",
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
            if any(t in ("grid", "shadow") for t in tags):
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
    font = (UI_FONT, 9, "bold") if bold else (UI_FONT, 9)
    cx = (x + x2) // 2 if anchor == "center" else x + 6
    cy = (y + y2) // 2
    c.create_text(cx, cy, text=txt, fill=color, font=font, anchor=anchor)


def _relief_border(c, x, y, x2, y2, relief, bd=2):
    """Draw a tkinter-style relief border. Does nothing for flat/empty."""
    light, mid, dark = "#ffffff", "#c0c0c0", "#808080"
    if not relief or relief == "flat":
        return
    if relief == "solid":
        c.create_rectangle(x, y, x2, y2, outline="#000000", fill="")
        return
    if relief == "raised":
        tl, br, tl2, br2 = light, dark,  light, mid
    elif relief == "sunken":
        tl, br, tl2, br2 = dark,  light, mid,   light
    elif relief == "groove":
        tl, br, tl2, br2 = dark,  light, light, dark
    elif relief == "ridge":
        tl, br, tl2, br2 = light, dark,  dark,  light
    else:
        return
    c.create_line(x,    y,    x2,   y,    fill=tl)
    c.create_line(x,    y,    x,    y2,   fill=tl)
    c.create_line(x,    y2,   x2,   y2,   fill=br)
    c.create_line(x2,   y,    x2,   y2,   fill=br)
    if bd >= 2:
        c.create_line(x+1,  y+1,  x2-1, y+1,  fill=tl2)
        c.create_line(x+1,  y+1,  x+1,  y2-1, fill=tl2)
        c.create_line(x+1,  y2-1, x2-1, y2-1, fill=br2)
        c.create_line(x2-1, y+1,  x2-1, y2-1, fill=br2)


def _get_bd(props, default=2):
    try:
        return max(0, int(props.get("borderwidth", "") or default))
    except (ValueError, TypeError):
        return default


def _resolve_image_path(rel_path: str, project_dir: str) -> str:
    """Resolve a relative-or-absolute image path against the project directory."""
    from pathlib import Path
    p = Path(rel_path)
    if p.is_absolute():
        return str(p)
    return str(Path(project_dir) / p)


def _load_natural_image(canvas, rel_path: str):
    """Return a cached ImageTk.PhotoImage at natural size, or None on any failure."""
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None
    try:
        resolved = _resolve_image_path(rel_path, canvas._project_dir)
        key = f"natural:{resolved}"
        cached = canvas._img_cache.get(key)
        if cached is not None:
            return cached
        photo = ImageTk.PhotoImage(Image.open(resolved))
        canvas._img_cache[key] = photo
        return photo
    except Exception:
        return None


def _load_preview_image(canvas, rel_path: str, max_w: int, max_h: int):
    """Return a cached ImageTk.PhotoImage thumbnail, or None on any failure."""
    try:
        from PIL import Image, ImageTk
    except ImportError:
        return None
    try:
        resolved = _resolve_image_path(rel_path, canvas._project_dir)
        key = f"{resolved}:{max_w}:{max_h}"
        cached = canvas._img_cache.get(key)
        if cached is not None:
            return cached
        img = Image.open(resolved).resize((max_w, max_h), Image.LANCZOS)
        photo = ImageTk.PhotoImage(img)
        canvas._img_cache[key] = photo
        return photo
    except Exception:
        return None


@_tag
def _draw_button(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#e1e1e1") or "#e1e1e1"
    fg = props.get("fg", "#111111") or "#111111"
    disabled = (props.get("state", "normal") == "disabled")
    if disabled:
        fg = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    relief = props.get("relief", "") or "raised"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    img_path = props.get("image", "")
    if img_path:
        photo = _load_preview_image(c, img_path, x2 - x - 4, y2 - y - 4)
        if photo:
            c.create_image(x + 2, y + 2, anchor="nw", image=photo)
        else:
            c.create_text(x2 - 4, y + 4, text="[img]", anchor="ne",
                          fill="#ce9178", font=("TkDefaultFont", 6))
            _text(c, x, y, x2, y2, text or "Button", color=fg)
    else:
        _text(c, x, y, x2, y2, text or "Button", color=fg)


@_tag
def _draw_label(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    if props.get("state", "normal") == "disabled":
        fg = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    relief = props.get("relief", "") or "flat"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    img_path = props.get("image", "")
    if img_path:
        photo = _load_preview_image(c, img_path, x2 - x, y2 - y)
        if photo:
            c.create_image(x, y, anchor="nw", image=photo)
        else:
            c.create_text(x2 - 4, y + 4, text="[img]", anchor="ne",
                          fill="#ce9178", font=("TkDefaultFont", 6))
            _text(c, x, y, x2, y2, text or "Label", anchor="w", color=fg)
    else:
        _text(c, x, y, x2, y2, text or "Label", anchor="w", color=fg)


@_tag
def _draw_entry(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#ffffff") or "#ffffff"
    fg = props.get("fg", "#111111") or "#111111"
    state = props.get("state", "normal")
    if state == "disabled":
        bg = props.get("disabledbackground", bg) or bg
        fg = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    relief = props.get("relief", "") or "sunken"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    show = props.get("show", "")
    placeholder = props.get("placeholder", "")
    if show:
        _text(c, x, y, x2, y2, "•" * 6, anchor="w", color=fg)
    elif placeholder:
        _text(c, x, y, x2, y2, placeholder, anchor="w", color="#aaaaaa")
    if state != "disabled":
        c.create_line(x+6, y+4, x+6, y2-4, fill=fg, width=1)


@_tag
def _draw_text(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#ffffff") or "#ffffff"
    state = props.get("state", "normal")
    relief = props.get("relief", "") or "sunken"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    fg = "#cccccc" if state == "disabled" else "#aaaaaa"
    _text(c, x, y, x2, y2, "Text", anchor="w", color=fg)


@_tag
def _draw_checkbutton(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    disabled = (props.get("state", "normal") == "disabled")
    if disabled:
        fg = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    bx, by = x + 2, (y + y2) // 2 - 6
    c.create_rectangle(bx, by, bx + 12, by + 12, fill="#ffffff", outline="#abadb3")
    check_color = "#abadb3" if disabled else "#0078d4"
    c.create_line(bx+2, by+6, bx+5, by+10, fill=check_color, width=2)
    c.create_line(bx+5, by+10, bx+11, by+2, fill=check_color, width=2)
    _text(c, bx + 18, y, x2, y2, text or "Check", anchor="w", color=fg)


@_tag
def _draw_radiobutton(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f5f5f5") or "#f5f5f5"
    fg = props.get("fg", "#111111") or "#111111"
    disabled = (props.get("state", "normal") == "disabled")
    if disabled:
        fg = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    cx2, cy2 = x + 8, (y + y2) // 2
    c.create_oval(cx2-6, cy2-6, cx2+6, cy2+6, fill="#ffffff", outline="#abadb3")
    dot_color = "#abadb3" if disabled else "#0078d4"
    c.create_oval(cx2-3, cy2-3, cx2+3, cy2+3, fill=dot_color, outline="")
    _text(c, cx2 + 12, y, x2, y2, text or "Radio", anchor="w", color=fg)


@_tag
def _draw_combobox(c, x, y, x2, y2, text, props):
    state = props.get("state", "normal")
    if state == "disabled":
        bg = props.get("disabledbackground", "#f0f0f0") or "#f0f0f0"
        fg = "#aaaaaa"
    elif state == "readonly":
        bg = props.get("readonlybackground", "#e8e8e8") or "#e8e8e8"
        fg = "#333333"
    else:
        bg, fg = "#ffffff", "#444444"
    c.create_rectangle(x, y, x2, y2,     fill=bg,      outline="#abadb3")
    c.create_rectangle(x2-20, y, x2, y2, fill="#e1e1e1", outline="#abadb3")
    c.create_text(x2-10, (y+y2)//2,      text="▾",     fill="#444444", font=(UI_FONT, 8))
    vals = props.get("values", [])
    if vals:
        _text(c, x, y, x2-20, y2, str(vals[0]), anchor="w", color=fg)


@_tag
def _draw_listbox(c, x, y, x2, y2, text, props):
    bg     = props.get("bg", "#ffffff") or "#ffffff"
    fg     = props.get("fg", "#555555") or "#555555"
    sbg    = props.get("selectbackground", "#0078d4") or "#0078d4"
    sfg    = props.get("selectforeground", "#ffffff")  or "#ffffff"
    alt_bg = props.get("colorize_altbg", "") if props.get("colorize") else ""
    relief = props.get("relief", "") or "sunken"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    row_h = 18
    items = props.get("values", [])
    display = [str(v) for v in items] if items else [f"Item {i+1}" for i in range(3)]
    for i, label in enumerate(display):
        ry = y + i * row_h
        if ry + row_h > y2:
            break
        if i == 0:
            c.create_rectangle(x+1, ry+1, x2-1, ry+row_h, fill=sbg, outline="")
            c.create_text(x+5, ry+row_h//2, text=label, anchor="w",
                          fill=sfg, font=(UI_FONT, 8))
        else:
            row_bg = (alt_bg if (i % 2 == 0 and alt_bg) else bg)
            if row_bg != bg:
                c.create_rectangle(x+1, ry+1, x2-1, ry+row_h, fill=row_bg, outline="")
            c.create_text(x+5, ry+row_h//2, text=label, anchor="w",
                          fill=fg, font=(UI_FONT, 8))


def _draw_notebook_canvas(c, x, y, x2, y2, props, tag, nb_id, active_tab):
    """Draw a Notebook on the designer canvas (not @_tag — needs nb_id/active_tab)."""
    tabs  = props.get("tabs") or ["Tab 1"]
    _BORDER   = "#adadad"
    _STRIP    = "#f0f0f0"
    _ACT_BG   = _STRIP
    _INACT_BG = "#e1e1e1"
    bg    = props.get("bg", "") or _STRIP
    sep_y = y + _NB_TAB_H   # y-coord of strip / content boundary

    tab_w = max(48, min(80, (x2 - x - 4) // max(len(tabs), 1)))

    # Locate the active tab's x extents so we can leave a gap in the separator
    act_x1 = act_x2 = None
    tx = x + 2
    for tab in tabs:
        if tab == active_tab:
            act_x1, act_x2 = tx, tx + tab_w
        tx += tab_w + 2

    # ── Content area (fill + 3-sided border, top left open for active tab) ─
    c.create_rectangle(x, sep_y, x2, y2, fill=bg, outline="",
                       tags=(tag, "widget"))
    c.create_line(x,  sep_y, x,  y2, fill=_BORDER, tags=(tag, "widget"))
    c.create_line(x,  y2,    x2, y2, fill=_BORDER, tags=(tag, "widget"))
    c.create_line(x2, sep_y, x2, y2, fill=_BORDER, tags=(tag, "widget"))

    # Separator line — drawn with a gap under the active tab
    if act_x1 is not None:
        if act_x1 > x:
            c.create_line(x, sep_y, act_x1, sep_y,
                          fill=_BORDER, tags=(tag, "widget"))
        if act_x2 < x2:
            c.create_line(act_x2, sep_y, x2, sep_y,
                          fill=_BORDER, tags=(tag, "widget"))
    else:
        c.create_line(x, sep_y, x2, sep_y, fill=_BORDER, tags=(tag, "widget"))

    # ── Tab strip background + outer border ───────────────────────────────
    c.create_rectangle(x, y, x2, sep_y, fill=_STRIP, outline="",
                       tags=(tag, "widget"))
    c.create_line(x,  y, x,  sep_y, fill=_BORDER, tags=(tag, "widget"))
    c.create_line(x,  y, x2, y,     fill=_BORDER, tags=(tag, "widget"))
    c.create_line(x2, y, x2, sep_y, fill=_BORDER, tags=(tag, "widget"))

    # ── Tabs ──────────────────────────────────────────────────────────────
    tab_x = x + 2
    for tab in tabs:
        is_active = (tab == active_tab)
        nb_tag = f"nbtab:{nb_id}:{tab}"

        if is_active:
            ty1, ty2 = y + 2, sep_y
            # White fill — covers the strip bg and bridges into the content area
            c.create_rectangle(tab_x, ty1, tab_x + tab_w, ty2,
                               fill=_ACT_BG, outline="",
                               tags=(tag, "widget", nb_tag))
            # 3-sided border (no bottom — the gap in the separator handles that)
            c.create_line(tab_x,         ty1, tab_x + tab_w, ty1,
                          fill=_BORDER, tags=(tag, "widget", nb_tag))
            c.create_line(tab_x,         ty1, tab_x,         ty2,
                          fill=_BORDER, tags=(tag, "widget", nb_tag))
            c.create_line(tab_x + tab_w, ty1, tab_x + tab_w, ty2,
                          fill=_BORDER, tags=(tag, "widget", nb_tag))
            text_y = (ty1 + sep_y) // 2
        else:
            ty1, ty2 = y + 4, sep_y - 2
            c.create_rectangle(tab_x, ty1, tab_x + tab_w, ty2,
                               fill=_INACT_BG, outline=_BORDER,
                               tags=(tag, "widget", nb_tag))
            text_y = (ty1 + ty2) // 2

        c.create_text(tab_x + tab_w // 2, text_y,
                      text=tab, fill="#111111",
                      font=(UI_FONT, 8),
                      tags=(tag, "widget", nb_tag))
        tab_x += tab_w + 2


@_tag
def _draw_frame(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#f0f0f0") or "#f0f0f0"
    relief = props.get("relief", "") or "flat"
    c.create_rectangle(x, y, x2, y2, fill=bg, outline="")
    if not relief or relief == "flat":
        c.create_rectangle(x, y, x2, y2, outline="#abadb3", fill="", dash=(4, 4))
    else:
        _relief_border(c, x, y, x2, y2, relief, _get_bd(props))


@_tag
def _draw_labelframe(c, x, y, x2, y2, text, props):
    bg    = props.get("bg",  "#f0f0f0") or "#f0f0f0"
    fg    = props.get("fg",  "#333333") or "#333333"
    label = text or "Group"
    relief = props.get("relief", "") or "groove"
    bd = _get_bd(props)
    anchor = props.get("labelanchor", "nw") or "nw"
    lw = len(label) * 6 + 8
    lh = 16
    edge = anchor[0]
    align = anchor[1] if len(anchor) > 1 else ""
    if edge == "s":
        bx, by, bx2, by2 = x, y, x2, y2-8
        lx = x+8 if align == "w" else (x2-8-lw if align == "e" else (x+x2)//2-lw//2)
        notch = (lx, y2-lh, lx+lw, y2)
    elif edge == "w":
        bx, by, bx2, by2 = x+8, y, x2, y2
        ly = y+8 if align == "n" else (y2-lh-8 if align == "s" else (y+y2)//2-lh//2)
        notch = (x, ly, x+lw, ly+lh)
    elif edge == "e":
        bx, by, bx2, by2 = x, y, x2-8, y2
        ly = y+8 if align == "n" else (y2-lh-8 if align == "s" else (y+y2)//2-lh//2)
        notch = (x2-lw, ly, x2, ly+lh)
    else:  # n (default)
        bx, by, bx2, by2 = x, y+8, x2, y2
        lx = x+8 if align in ("w", "") else (x2-8-lw if align == "e" else (x+x2)//2-lw//2)
        notch = (lx, y, lx+lw, y+lh)
    c.create_rectangle(bx, by, bx2, by2, fill=bg, outline="")
    _relief_border(c, bx, by, bx2, by2, relief, bd)
    # Erase the border at the label position to create the notch
    c.create_rectangle(notch[0], notch[1], notch[2], notch[3], fill=bg, outline="")
    if edge == "s":
        c.create_text(notch[0]+4, y2-8, text=label, anchor="w", fill=fg, font=(UI_FONT, 8))
    elif edge in ("w", "e"):
        c.create_text(notch[0]+4, notch[1]+8, text=label, anchor="w", fill=fg, font=(UI_FONT, 8))
    else:
        c.create_text(notch[0]+4, by, text=label, anchor="w", fill=fg, font=(UI_FONT, 8))


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
    bg    = props.get("bg", "#ffffff") or "#ffffff"
    fg    = props.get("fg", "#333333") or "#333333"
    state = props.get("state", "normal")
    if state == "disabled":
        bg  = props.get("disabledbackground", bg) or bg
        fg  = props.get("disabledforeground", "#aaaaaa") or "#aaaaaa"
    elif state == "readonly":
        bg  = props.get("readonlybackground", "#e8e8e8") or "#e8e8e8"
    btn_bg = "#cccccc" if state in ("disabled", "readonly") else "#e1e1e1"
    btn_fg = "#aaaaaa" if state == "disabled" else "#555555"
    relief = props.get("relief", "") or "sunken"
    c.create_rectangle(x, y, x2, y2,      fill=bg,     outline="")
    c.create_rectangle(x2-16, y, x2, y2,  fill=btn_bg, outline="")
    _relief_border(c, x, y, x2, y2, relief, _get_bd(props))
    mid = (y + y2) // 2
    c.create_text(x2-8, mid-4, text="▲", fill=btn_fg, font=(UI_FONT, 6))
    c.create_text(x2-8, mid+4, text="▼", fill=btn_fg, font=(UI_FONT, 6))
    values = props.get("values", [])
    val = str(values[0]) if values else str(props.get("from_", "0"))
    _text(c, x, y, x2-16, y2, val, anchor="w", color=fg)


@_tag
def _draw_progressbar(c, x, y, x2, y2, text, props):
    c.create_rectangle(x, y, x2, y2, fill="#e1e1e1", outline="#abadb3")
    mode = props.get("mode", "determinate") or "determinate"
    if mode == "indeterminate":
        bw = (x2 - x) // 3
        bx = (x + x2) // 2 - bw // 2
        c.create_rectangle(bx, y+1, bx+bw, y2-1, fill="#0078d4", outline="")
        for sx in range(bx + 6, bx + bw, 8):
            c.create_line(sx, y+1, sx-6, y2-1, fill="#006ac1", width=1)
    else:
        fill_w = int((x2 - x - 2) * 0.6)
        c.create_rectangle(x+1, y+1, x+1+fill_w, y2-1, fill="#0078d4", outline="")


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


@_tag
def _draw_canvas_widget(c, x, y, x2, y2, text, props):
    bg = props.get("bg", "#e8e8e8") or "#e8e8e8"
    show_border = str(props.get("border", True)).lower() not in ("false", "0")
    outline = "#808080" if show_border else ""
    c.create_rectangle(x, y, x2, y2, fill=bg, outline=outline)
    img_path = props.get("image", "")
    if img_path:
        photo = _load_preview_image(c, img_path, x2 - x, y2 - y)
        if photo:
            c.create_image(x, y, anchor="nw", image=photo)
        else:
            c.create_text(x2 - 4, y + 4, text="[img]", anchor="ne",
                          fill="#ce9178", font=("TkDefaultFont", 6))
            _text(c, x, y, x2, y2, "Canvas", color="#666666")
    else:
        _text(c, x, y, x2, y2, "Canvas", color="#666666")


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
    "Canvas":      _draw_canvas_widget,
}


# ── Utility ───────────────────────────────────────────────────────────────────

def _snap(v: int) -> int:
    return round(v / GRID) * GRID if _snap_enabled else v


def _anchor_geom(
    geom: tuple[int, int, int, int],
    anchor: str,
    orig_fw: int, orig_fh: int,
    new_fw: int,  new_fh: int,
) -> tuple[int, int, int, int]:
    """Return (x, y, w, h) for a widget after form resize, matching codegen formulas."""
    x, y, ww, wh = geom
    rm = orig_fw - (x + ww)
    bm = orig_fh - (y + wh)
    if anchor == "all":
        return (
            round(x  * new_fw / orig_fw),
            round(y  * new_fh / orig_fh),
            round(ww * new_fw / orig_fw),
            round(wh * new_fh / orig_fh),
        )
    if anchor == "top":
        return (x, y, new_fw - x - rm, wh)
    if anchor == "bottom":
        return (x, new_fh - bm - wh, new_fw - x - rm, wh)
    if anchor == "left":
        return (x, y, ww, new_fh - y - bm)
    if anchor == "right":
        return (new_fw - rm - ww, y, ww, new_fh - y - bm)
    if anchor == "top_right":
        return (new_fw - rm - ww, y, ww, wh)
    if anchor == "bottom_left":
        return (x, new_fh - bm - wh, ww, wh)
    if anchor == "bottom_right":
        return (new_fw - rm - ww, new_fh - bm - wh, ww, wh)
    return (x, y, ww, wh)  # top_left / none — no change
