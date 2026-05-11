from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from designer.model import FormModel, VariableBinding, WidgetDescriptor
from designer.registry import REGISTRY
from widgets.guide_window import GuideWindow, GuidePage
from widgets.scrollbar import VerticalScrollbar
from utils.ui_font import UI_FONT


# ── Order / Props canvas palette ─────────────────────────────────────────────
_ORD_ROW_H   = 28
_ORD_BG      = "#1e1e1e"
_ORD_EVEN    = "#252526"
_ORD_ODD     = "#2a2a2b"
_ORD_HOV     = "#2d2d30"
_ORD_SEL     = "#094771"
_ORD_FG      = "#cccccc"
_ORD_DIM     = "#636363"
_ORD_NUM     = "#007acc"
_PROPS_SPLIT = 0.44   # fraction of width for the label column


class DesignerProperties(tk.Frame):
    """Properties + Events panel for the GUI Designer.

    Displayed in the right pane of _h_pane while Designer mode is active.
    Exposes load_widget(), load_form(), set_form(), and clear() as the public API.
    Fires on_prop_change(widget_id, key, value),
         on_event_change(widget_id, event_key, handler_name), and
         on_select_widget(widget_id | None) on user edits.
    """

    def __init__(
        self,
        master,
        on_prop_change:      Optional[Callable[[str, str, Any],  None]] = None,
        on_event_change:     Optional[Callable[[str, str, str], None]] = None,
        on_select_widget:    Optional[Callable[[str | None],    None]] = None,
        on_navigate_handler: Optional[Callable[[str],           None]] = None,
        on_reorder_widget:   Optional[Callable[[str, int],      None]] = None,
        on_handler_toggle:   Optional[Callable[[str, bool],     None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg="#252526", **kwargs)
        self._on_prop_change      = on_prop_change
        self._on_event_change     = on_event_change
        self._on_select_widget    = on_select_widget
        self._on_navigate_handler = on_navigate_handler
        self._on_reorder_widget   = on_reorder_widget
        self._on_handler_toggle   = on_handler_toggle
        self._current_widget: WidgetDescriptor | None  = None
        self._multi_widgets:  list[WidgetDescriptor]    = []
        self._entry_editor:   tk.Widget | None          = None
        self._pending_commit: "Callable[[], None] | None" = None
        self._form:           FormModel | None          = None
        # (display_label, widget_id | None)  — None means the form itself
        self._selector_items: list[tuple[str, str | None]] = []
        self._status_after:   str | None                = None
        self._prop_clearing:  bool                      = False
        self._ev_clearing:    bool                      = False
        self._prop_clear_iid: str | None                = None
        self._ev_btn_iid:     str | None                = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        _apply_tree_style()

        # Control selector — dropdown that lists the form + all widgets
        sel_frame = tk.Frame(self, bg="#3c3c3c", relief="flat", bd=1)
        sel_frame.pack(fill="x", side="top", padx=4, pady=(6, 2))

        self._selector_label = tk.Label(
            sel_frame, text="Properties",
            bg="#3c3c3c", fg="#cccccc",
            font=(UI_FONT, 9), anchor="w", padx=6,
            cursor="hand2",
        )
        self._selector_label.pack(side="left", fill="x", expand=True)

        self._selector_arrow = tk.Label(
            sel_frame, text="▼",
            bg="#3c3c3c", fg="#858585",
            font=(UI_FONT, 7), padx=4,
            cursor="hand2",
        )
        self._selector_arrow.pack(side="right")

        for w in (sel_frame, self._selector_label, self._selector_arrow):
            w.bind("<Button-1>", self._open_selector_menu)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Notebook: Properties | Events
        nb_style = ttk.Style()
        nb_style.configure("Props.TNotebook",        background="#252526", borderwidth=0)
        nb_style.configure("Props.TNotebook.Tab",    background="#1e1e1e", foreground="#858585",
                           padding=(8, 3))
        nb_style.map("Props.TNotebook.Tab",
                     background=[("selected", "#252526")],
                     foreground=[("selected", "#cccccc")])

        # Status bar — fixed height so text changes never cause panel redraws
        _hint_frame = tk.Frame(self, bg="#252526", height=48)
        _hint_frame.pack(fill="x", side="bottom")
        _hint_frame.pack_propagate(False)
        self._status_label = tk.Label(
            _hint_frame, text="", bg="#252526", fg="#ff6b6b",
            font=(UI_FONT, 8), anchor="nw", padx=6, pady=4,
            justify="left", wraplength=200,
        )
        self._status_label.pack(fill="both", expand=True)
        self._status_label.bind(
            "<Configure>",
            lambda e: self._status_label.config(wraplength=max(1, e.width - 12)),
        )

        self._nb = ttk.Notebook(self, style="Props.TNotebook")
        self._nb.pack(fill="both", expand=True)

        # Properties tab — canvas-rendered rows
        self._props_frame = tk.Frame(self._nb, bg=_ORD_BG)
        self._nb.add(self._props_frame, text="  Properties  ")
        _pb = tk.Frame(self._props_frame, bg=_ORD_BG)
        _pb.pack(fill="both", expand=True)
        self._props_sb = VerticalScrollbar(_pb, bg=_ORD_BG)
        self._props_sb.pack(side="right", fill="y")
        self._props_cv = tk.Canvas(
            _pb, bg=_ORD_BG, highlightthickness=0,
            yscrollcommand=self._props_sb.set,
        )
        self._props_cv.pack(side="left", fill="both", expand=True)
        self._props_sb.configure(command=self._props_cv.yview)
        self._props_cv.bind("<Configure>",
            lambda _: self._props_redraw())
        self._props_cv.bind("<MouseWheel>",
            lambda e: self._props_cv.yview_scroll(-1 * (e.delta // 120), "units"))
        self._props_cv.bind("<Motion>",           self._on_prop_motion)
        self._props_cv.bind("<Leave>",            self._on_prop_canvas_leave)
        self._props_cv.bind("<ButtonRelease-1>",  self._on_prop_canvas_click)
        # Row data store
        self._props_rows:    list = []   # list of row dicts
        self._props_row_map: dict = {}   # iid → index
        self._props_hov_idx: int | None = None
        # Floating × clear button placed over canvas on hover
        self._prop_clear_btn = tk.Label(
            self._props_cv, text="×",
            bg="#3a3a3a", fg="#888888",
            font=(UI_FONT, 9), cursor="hand2", padx=2,
        )
        self._prop_clear_btn.bind("<Enter>",    lambda e: self._prop_clear_btn.config(fg="#ff6b6b"))
        self._prop_clear_btn.bind("<Leave>",    self._on_prop_btn_leave)
        self._prop_clear_btn.bind("<Button-1>", self._on_prop_clear_click)

        # Events tab — canvas-rendered rows
        self._events_frame = tk.Frame(self._nb, bg=_ORD_BG)
        self._nb.add(self._events_frame, text="  Events  ")
        _eb = tk.Frame(self._events_frame, bg=_ORD_BG)
        _eb.pack(fill="both", expand=True)
        self._events_sb = VerticalScrollbar(_eb, bg=_ORD_BG)
        self._events_sb.pack(side="right", fill="y")
        self._events_cv = tk.Canvas(
            _eb, bg=_ORD_BG, highlightthickness=0,
            yscrollcommand=self._events_sb.set,
        )
        self._events_cv.pack(side="left", fill="both", expand=True)
        self._events_sb.configure(command=self._events_cv.yview)
        self._events_cv.bind("<Configure>",
            lambda _: self._events_redraw())
        self._events_cv.bind("<MouseWheel>",
            lambda e: self._events_cv.yview_scroll(-1 * (e.delta // 120), "units"))
        self._events_cv.bind("<Motion>",           self._on_event_motion)
        self._events_cv.bind("<Leave>",            self._on_event_canvas_leave)
        self._events_cv.bind("<ButtonRelease-1>",  self._on_event_canvas_click)
        self._events_cv.bind("<Double-Button-1>",  self._on_event_canvas_dblclick)
        # Row data store
        self._events_rows:    list = []
        self._events_row_map: dict = {}
        self._events_hov_idx: int | None = None
        # Floating action buttons placed over canvas on hover
        self._ev_clear_btn = tk.Label(
            self._events_cv, text="×",
            bg="#3a3a3a", fg="#888888",
            font=(UI_FONT, 9), cursor="hand2", padx=2,
        )
        self._ev_clear_btn.bind("<Enter>",    lambda e: self._ev_clear_btn.config(fg="#ff6b6b"))
        self._ev_clear_btn.bind("<Leave>",    self._on_ev_btn_leave)
        self._ev_clear_btn.bind("<Button-1>", self._on_ev_clear_click)

        self._ev_wire_btn = tk.Label(
            self._events_cv, text="✦",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=2,
        )
        self._ev_wire_btn.bind("<Enter>",    lambda e: self._ev_wire_btn.config(fg="#569cd6"))
        self._ev_wire_btn.bind("<Leave>",    self._on_ev_btn_leave)
        self._ev_wire_btn.bind("<Button-1>", self._on_ev_wire_click)

        # ── Handlers tab ──────────────────────────────────────────────────────
        self._handlers_frame = tk.Frame(self._nb, bg=_ORD_BG)
        self._nb.add(self._handlers_frame, text="  Handlers  ")

        self._handlers_cv = tk.Canvas(
            self._handlers_frame, bg=_ORD_BG, highlightthickness=0,
        )
        self._handlers_cv.pack(fill="both", expand=True)
        self._handlers_cv.bind("<Configure>",  lambda _: self._handlers_redraw())
        self._handlers_cv.bind("<Motion>",     self._handlers_motion)
        self._handlers_cv.bind("<Leave>",      self._handlers_leave)
        self._handlers_cv.bind("<ButtonRelease-1>", self._handlers_click)
        self._handlers_cv.bind("<Double-Button-1>", self._handlers_dblclick)

        self._handlers_defs:    list = []   # HandlerDef list for current form
        self._handlers_enabled: set[str] = set()
        self._handlers_hov_idx: int | None = None
        self._handlers_dbl_pending: bool = False

        # ── Order tab ─────────────────────────────────────────────────────────
        self._order_frame = tk.Frame(self._nb, bg=_ORD_BG)
        self._nb.add(self._order_frame, text="  Order  ")

        _ob = tk.Frame(self._order_frame, bg=_ORD_BG)
        _ob.pack(fill="both", expand=True)

        # Keep hint bar in sync with the active tab
        self._nb.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self._order_sb = VerticalScrollbar(_ob, bg=_ORD_BG)
        self._order_sb.pack(side="right", fill="y")
        self._order_cv = tk.Canvas(
            _ob, bg=_ORD_BG, highlightthickness=0,
            yscrollcommand=self._order_sb.set,
        )
        self._order_cv.pack(side="left", fill="both", expand=True)
        self._order_sb.configure(command=self._order_cv.yview)
        self._order_cv.bind("<Configure>",  lambda _: self._order_redraw())
        self._order_cv.bind("<MouseWheel>",
            lambda e: self._order_cv.yview_scroll(-1 * (e.delta // 120), "units"))
        self._order_cv.bind("<ButtonPress-1>",   self._order_press)
        self._order_cv.bind("<B1-Motion>",        self._order_motion)
        self._order_cv.bind("<ButtonRelease-1>",  self._order_release)

        self._order_widgets: list[WidgetDescriptor] = []
        self._order_sel_id:  str | None = None
        self._order_bgs:     dict[int, int] = {}
        self._order_drag_idx:   int | None = None
        self._order_drag_ghost: int | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    def load_widget(self, descriptor: WidgetDescriptor) -> None:
        """Populate the panel from *descriptor*."""
        self._dismiss_editor()
        self._current_widget = descriptor
        self._multi_widgets  = []
        reg = REGISTRY.get(descriptor.type, {})
        self._set_selector(descriptor.id)
        self._populate_props(descriptor, reg)
        self._populate_events(descriptor, reg)
        if self._form:
            self.load_handlers(self._form)

    def load_form(self, form: FormModel) -> None:
        """Show form-level properties when the canvas background is selected."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._set_selector(None)

        self._props_clear()
        for key, label, val in [
            ("title",        "title",        form.title),
            ("width",        "width",        form.width),
            ("height",       "height",       form.height - (20 if form.menu_items else 0)),
            ("border_style",  "border style",   form.border_style),
            ("maximize_box",  "maximize",       form.maximize_box),
            ("always_on_top", "always on top",  form.always_on_top),
            ("bg",            "background",     form.bg),
        ]:
            self._props_insert(f"form__{key}", label, str(val))
        # Tint the background row only when a color is explicitly set
        self._apply_color_swatch("form__bg", form.bg.upper() if form.bg else None)
        # Menu bar row (blue link)
        n = len(form.menu_items)
        menu_val = f"{n} item{'s' if n != 1 else ''}" if n else "(none)"
        self._props_insert("form__menu_bar", "menu bar", menu_val)
        self._props_set_link("form__menu_bar", True)
        self._props_redraw()

        self._events_clear()
        for ev in ("load", "activate", "deactivate", "unload", "resize"):
            handler = form.form_events.get(ev, "")
            self._events_insert(f"form_ev__{ev}", ev, handler)
        self._events_insert("ev__learn_guide", "? Events", "", kind="guide")
        self._events_redraw()

        self.load_handlers(form)

    def load_handlers(self, form: FormModel) -> None:
        """Populate the Handlers tab from the form's enabled_handlers list."""
        from designer.handlers import handlers_for
        self._handlers_defs    = handlers_for(form.form_type)
        self._handlers_enabled = set(form.enabled_handlers)
        self._handlers_hov_idx = None
        self._handlers_redraw()

    def load_multi(self, descriptors: list[WidgetDescriptor]) -> None:
        """Show shared properties panel for a multi-widget selection."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = list(descriptors)
        self._selector_label.config(text=f"({len(descriptors)} widgets selected)")

        self._props_clear()
        self._events_clear()
        self._events_redraw()
        if self._form:
            self.load_handlers(self._form)

        if not descriptors:
            self._props_redraw()
            return

        primary = descriptors[0]

        # Geometry (delta-based on commit)
        for key in ("x", "y", "width", "height"):
            self._props_insert(f"geo__{key}", key, str(getattr(primary, key)))

        regs = [REGISTRY.get(d.type, {}) for d in descriptors]

        excluded: set[str] = {
            "state", "validate", "validatecommand", "vcmd_args",
            "invalidcommand", "colorize", "colorize_altbg",
        }
        for r in regs:
            for color_list in r.get("state_color_props", {}).values():
                excluded.update(color_list)

        all_key_sets = [set(r.get("default_props", {}).keys()) - excluded for r in regs]
        shared_keys  = set.intersection(*all_key_sets) if all_key_sets else set()

        first_defaults = regs[0].get("default_props", {})
        ordered_keys   = [k for k in first_defaults if k in shared_keys]
        for k in shared_keys:
            if k not in ordered_keys:
                ordered_keys.append(k)

        seen: set[str] = set()
        for key in ordered_keys:
            if key in seen:
                continue
            seen.add(key)
            vals = [str(d.props.get(key, regs[i].get("default_props", {}).get(key, "")))
                    for i, d in enumerate(descriptors)]
            display_val = _display(vals[0]) if len(set(vals)) == 1 else ""
            self._props_insert(f"prop__{key}", _PROP_LABELS.get(key, key), display_val)

        all_color_sets = [set(r.get("color_props", [])) for r in regs]
        shared_colors  = set.intersection(*all_color_sets) if all_color_sets else set()
        for key in shared_colors:
            if key in seen:
                continue
            seen.add(key)
            vals        = [d.props.get(key, "") for d in descriptors]
            display_val = vals[0] if len(set(vals)) == 1 else ""
            self._props_insert(f"prop__{key}", _PROP_LABELS.get(key, key), display_val)
            if display_val:
                self._props_set_swatch(f"prop__{key}", display_val.upper())

        # Layout / anchor section
        self._props_insert("anchor__section", "Layout", "", kind="header")
        anchor_vals = [d.anchor for d in descriptors]
        anchor_disp = (
            _ANCHOR_DISPLAY.get(anchor_vals[0], anchor_vals[0] or "(none)")
            if len(set(anchor_vals)) == 1 else ""
        )
        self._props_insert("anchor__value", "  anchor", anchor_disp)
        self._props_redraw()

    def clear(self) -> None:
        """Reset to the empty / no-selection state."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._selector_items = []
        self._selector_label.config(text="Properties")
        self._props_clear()
        self._props_redraw()
        self._events_clear()
        self._events_redraw()

    def set_form(self, form: FormModel) -> None:
        """Rebuild the control selector dropdown from the current form."""
        self._form = form
        kind = "TopLevel" if form.form_type == "dialog" else "Form"
        self._selector_items = [(f"{form.name}  ({kind})", None)]
        for w in form.widgets:
            self._selector_items.append((f"{w.id}  ({w.type})", w.id))

    def refresh_order(self, form: "FormModel | None", selected_id: str | None = None) -> None:
        """Refresh the Order tab list. Call on any structure change or selection change."""
        self._order_widgets = list(form.widgets) if form else []
        self._order_sel_id  = selected_id
        self._order_bgs.clear()
        self._order_redraw()

    # ── Events canvas helpers ─────────────────────────────────────────────────

    def _events_clear(self) -> None:
        self._events_rows.clear()
        self._events_row_map.clear()
        self._events_hov_idx = None

    def _events_insert(self, iid: str, label: str, value: str,
                       kind: str = "event") -> None:
        """kind: 'event' | 'guide'"""
        row: dict = {"iid": iid, "label": label, "value": value,
                     "kind": kind, "warn": False}
        self._events_row_map[iid] = len(self._events_rows)
        self._events_rows.append(row)

    def _events_set(self, iid: str, value: str) -> None:
        idx = self._events_row_map.get(iid)
        if idx is not None:
            self._events_rows[idx]["value"] = value
            self._events_redraw_row(idx)

    def _events_get(self, iid: str) -> str:
        idx = self._events_row_map.get(iid)
        return self._events_rows[idx]["value"] if idx is not None else ""

    def _events_exists(self, iid: str) -> bool:
        return iid in self._events_row_map

    def _events_set_warn(self, iid: str, warn: bool) -> None:
        idx = self._events_row_map.get(iid)
        if idx is not None:
            self._events_rows[idx]["warn"] = warn
            self._events_redraw_row(idx)

    def _events_bbox(self, iid: str) -> "tuple[int,int,int,int] | None":
        """Return (x, y, w, h) in canvas widget coords for the value column."""
        idx = self._events_row_map.get(iid)
        if idx is None:
            return None
        cv_w     = max(self._events_cv.winfo_width(), 160)
        split_x  = max(80, int(cv_w * _PROPS_SPLIT))
        canvas_y = idx * _ORD_ROW_H
        scroll_top = int(self._events_cv.canvasy(0))
        screen_y = canvas_y - scroll_top
        cv_h = self._events_cv.winfo_height()
        if screen_y < -_ORD_ROW_H or screen_y >= cv_h:
            return None
        return (split_x + 1, screen_y, cv_w - split_x - 1, _ORD_ROW_H)

    def _events_iid_at_y(self, widget_y: int) -> "str | None":
        canvas_y = int(self._events_cv.canvasy(widget_y))
        idx = canvas_y // _ORD_ROW_H
        return self._events_rows[idx]["iid"] if 0 <= idx < len(self._events_rows) else None

    def _events_idx_at_y(self, widget_y: int) -> "int | None":
        canvas_y = int(self._events_cv.canvasy(widget_y))
        idx = canvas_y // _ORD_ROW_H
        return idx if 0 <= idx < len(self._events_rows) else None

    def _events_redraw(self) -> None:
        cv = self._events_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 160)

        if not self._events_rows:
            cv.configure(scrollregion=(0, 0, w, 40))
            return

        split_x = max(80, int(w * _PROPS_SPLIT))
        total_h = len(self._events_rows) * _ORD_ROW_H
        cv.configure(scrollregion=(0, 0, w, total_h))

        for i, row in enumerate(self._events_rows):
            y0  = i * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            is_hov = (i == self._events_hov_idx)

            bg = _ORD_HOV if is_hov else (_ORD_EVEN if i % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"er{i}")

            if row["kind"] == "guide":
                cv.create_text(w // 2, mid, text=row["label"],
                               fill="#569cd6", font=(UI_FONT, 9),
                               anchor="center", tags=f"er{i}")
            else:
                cv.create_line(split_x, y0, split_x, y1,
                               fill="#333333", tags=f"er{i}")
                cv.create_text(8, mid, text=row["label"],
                               fill=_ORD_FG, font=(UI_FONT, 9),
                               anchor="w", tags=f"er{i}")
                val = row["value"]
                if val:
                    color = "#ff6b6b" if row["warn"] else _ORD_FG
                    cv.create_text(split_x + 8, mid, text=val,
                                   fill=color, font=("Consolas", 9),
                                   anchor="w", tags=f"er{i}")

    def _events_redraw_row(self, idx: int) -> None:
        cv = self._events_cv
        w  = max(cv.winfo_width(), 160)
        cv.delete(f"er{idx}")

        row     = self._events_rows[idx]
        y0      = idx * _ORD_ROW_H
        y1      = y0 + _ORD_ROW_H
        mid     = (y0 + y1) // 2
        split_x = max(80, int(w * _PROPS_SPLIT))
        is_hov  = (idx == self._events_hov_idx)

        bg = _ORD_HOV if is_hov else (_ORD_EVEN if idx % 2 == 0 else _ORD_ODD)
        cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"er{idx}")

        if row["kind"] == "guide":
            cv.create_text(w // 2, mid, text=row["label"],
                           fill="#569cd6", font=(UI_FONT, 9),
                           anchor="center", tags=f"er{idx}")
        else:
            cv.create_line(split_x, y0, split_x, y1,
                           fill="#333333", tags=f"er{idx}")
            cv.create_text(8, mid, text=row["label"],
                           fill=_ORD_FG, font=(UI_FONT, 9),
                           anchor="w", tags=f"er{idx}")
            val = row["value"]
            if val:
                color = "#ff6b6b" if row["warn"] else _ORD_FG
                cv.create_text(split_x + 8, mid, text=val,
                               fill=color, font=("Consolas", 9),
                               anchor="w", tags=f"er{idx}")

    # ── Events canvas input handlers ──────────────────────────────────────────

    def _on_event_motion(self, event: tk.Event) -> None:
        idx = self._events_idx_at_y(event.y)
        if idx == self._events_hov_idx:
            if idx is not None:
                self._update_event_btns(idx)
            return
        old = self._events_hov_idx
        self._events_hov_idx = idx
        if old is not None:
            self._events_redraw_row(old)
        if idx is not None:
            self._events_redraw_row(idx)
            iid     = self._events_rows[idx]["iid"]
            self._update_event_btns(idx)
            ev_name = (iid[4:]  if iid.startswith("ev__")      else
                       iid[9:]  if iid.startswith("form_ev__") else "")
            hint = _EVENT_DESCRIPTIONS.get(ev_name, ("", ""))[1]
            if hint:
                self._show_hint(hint)
            else:
                self._clear_hint()
        else:
            self._ev_clear_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._clear_hint()

    def _update_event_btns(self, idx: int) -> None:
        iid = self._events_rows[idx]["iid"]
        if iid == "ev__learn_guide":
            self._ev_clear_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._ev_btn_iid = None
            return
        bbox = self._events_bbox(iid)
        if not bbox:
            self._ev_clear_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._ev_btn_iid = None
            return
        x, y, w, h = bbox
        bw  = 18
        val = self._events_rows[idx]["value"].strip()
        if val:
            self._ev_wire_btn.place_forget()
            self._ev_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
            self._ev_clear_btn.lift()
            self._ev_btn_iid = iid
        else:
            self._ev_clear_btn.place_forget()
            can_wire = (
                (iid.startswith("ev__")      and self._current_widget is not None) or
                (iid.startswith("form_ev__") and self._form is not None)
            )
            if can_wire:
                self._ev_wire_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._ev_wire_btn.lift()
                self._ev_btn_iid = iid
            else:
                self._ev_wire_btn.place_forget()
                self._ev_btn_iid = None

    def _on_event_canvas_leave(self, event: tk.Event) -> None:
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest in (self._ev_clear_btn, self._ev_wire_btn):
            return
        if self._events_hov_idx is not None:
            old = self._events_hov_idx
            self._events_hov_idx = None
            self._events_redraw_row(old)
        self._ev_clear_btn.place_forget()
        self._ev_wire_btn.place_forget()
        self._clear_hint()

    def _on_ev_btn_leave(self, event: tk.Event) -> None:
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest is self._events_cv:
            return
        self._ev_clear_btn.config(fg="#888888")
        self._ev_wire_btn.config(fg="#555555")
        self._ev_clear_btn.place_forget()
        self._ev_wire_btn.place_forget()
        if self._events_hov_idx is not None:
            old = self._events_hov_idx
            self._events_hov_idx = None
            self._events_redraw_row(old)
        self._clear_hint()

    def _on_event_canvas_click(self, event: tk.Event) -> None:
        if self._ev_clearing:
            self._ev_clearing = False
            return
        iid = self._events_iid_at_y(event.y)
        if not iid:
            return
        if iid == "ev__learn_guide":
            self._open_event_guide()
            return
        split_x = int(self._events_cv.winfo_width() * _PROPS_SPLIT)
        if event.x < split_x:
            return  # name column — double-click navigates, single-click does nothing
        self._open_handler_picker(iid)

    def _on_event_canvas_dblclick(self, event: tk.Event) -> None:
        if not self._on_navigate_handler:
            return
        iid = self._events_iid_at_y(event.y)
        if not iid or iid == "ev__learn_guide":
            return
        handler = self._events_get(iid).strip()
        if handler:
            self._on_navigate_handler(handler)

    # ── Handlers tab internals ────────────────────────────────────────────────

    def _handlers_redraw(self) -> None:
        cv = self._handlers_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 160)
        defs = self._handlers_defs

        if not defs:
            msg = ("No handlers available for this form type"
                   if self._form else "Select the form to manage handlers")
            cv.create_text(w // 2, 24, text=msg,
                           fill=_ORD_DIM, font=(UI_FONT, 8), anchor="center")
            return

        for i, h in enumerate(defs):
            y0  = i * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            checked = h.id in self._handlers_enabled
            is_hov  = i == self._handlers_hov_idx

            bg = _ORD_HOV if is_hov else (_ORD_EVEN if i % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"hr{i}")

            # Checkbox
            cx, cy, r = 14, mid, 6
            if checked:
                cv.create_rectangle(cx - r, cy - r, cx + r, cy + r,
                                    fill="#007acc", outline="#007acc", tags=f"hr{i}")
                cv.create_text(cx, cy, text="✓", fill="#ffffff",
                               font=(UI_FONT, 8, "bold"), tags=f"hr{i}")
            else:
                cv.create_rectangle(cx - r, cy - r, cx + r, cy + r,
                                    fill="", outline="#555555", tags=f"hr{i}")

            # Handler name
            cv.create_text(cx + r + 8, mid, text=h.label,
                           fill=_ORD_FG, font=("Consolas", 9), anchor="w", tags=f"hr{i}")

            # Applies-to badge (dimmed, right-aligned)
            badge = "dialog" if h.applies_to == ("dialog",) else "all forms"
            cv.create_text(w - 6, mid, text=badge,
                           fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e", tags=f"hr{i}")

        cv.configure(scrollregion=(0, 0, w, len(defs) * _ORD_ROW_H))

    def _handlers_idx_at(self, y: int) -> int | None:
        i = int(y) // _ORD_ROW_H
        return i if 0 <= i < len(self._handlers_defs) else None

    def _handlers_motion(self, event: tk.Event) -> None:
        idx = self._handlers_idx_at(event.y)
        if idx == self._handlers_hov_idx:
            return
        self._handlers_hov_idx = idx
        self._handlers_redraw()
        if idx is not None:
            self._show_hint(self._handlers_defs[idx].description)
        else:
            self._clear_hint()

    def _handlers_leave(self, _event: tk.Event) -> None:
        if self._handlers_hov_idx is not None:
            self._handlers_hov_idx = None
            self._handlers_redraw()
        self._clear_hint()

    def _handlers_click(self, event: tk.Event) -> None:
        if self._handlers_dbl_pending:
            self._handlers_dbl_pending = False
            return
        if event.x > 28:
            return  # name area — only double-click acts here
        idx = self._handlers_idx_at(event.y)
        if idx is None:
            return
        h = self._handlers_defs[idx]
        enabled = h.id not in self._handlers_enabled
        if enabled:
            self._handlers_enabled.add(h.id)
        else:
            self._handlers_enabled.discard(h.id)
        self._handlers_redraw()
        if self._on_handler_toggle:
            self._on_handler_toggle(h.id, enabled)

    def _handlers_dblclick(self, event: tk.Event) -> None:
        self._handlers_dbl_pending = True
        if event.x <= 28:
            return  # checkbox zone — single-click handles it
        idx = self._handlers_idx_at(event.y)
        if idx is None:
            return
        h = self._handlers_defs[idx]
        if h.id not in self._handlers_enabled:
            self._handlers_enabled.add(h.id)
            self._handlers_redraw()
            if self._on_handler_toggle:
                self._on_handler_toggle(h.id, True)
        else:
            if self._on_navigate_handler:
                self._on_navigate_handler(h.id)

    # ── Props canvas data helpers ─────────────────────────────────────────────

    def _props_clear(self) -> None:
        self._props_rows.clear()
        self._props_row_map.clear()
        self._props_hov_idx = None

    def _props_insert(self, iid: str, label: str, value: str,
                      kind: str = "normal") -> None:
        """kind: 'header' | 'normal' | 'readonly'"""
        row: dict = {"iid": iid, "label": label, "value": value, "kind": kind,
                     "swatch": None, "warn": False, "link": False}
        self._props_row_map[iid] = len(self._props_rows)
        self._props_rows.append(row)

    def _props_set(self, iid: str, value: str) -> None:
        idx = self._props_row_map.get(iid)
        if idx is not None:
            self._props_rows[idx]["value"] = value
            self._props_redraw_row(idx)

    def _props_get(self, iid: str) -> str:
        idx = self._props_row_map.get(iid)
        return self._props_rows[idx]["value"] if idx is not None else ""

    def _props_exists(self, iid: str) -> bool:
        return iid in self._props_row_map

    def _props_set_swatch(self, iid: str, color: str | None) -> None:
        idx = self._props_row_map.get(iid)
        if idx is not None:
            self._props_rows[idx]["swatch"] = color
            self._props_redraw_row(idx)

    def _props_set_warn(self, iid: str, warn: bool) -> None:
        idx = self._props_row_map.get(iid)
        if idx is not None:
            self._props_rows[idx]["warn"] = warn
            self._props_redraw_row(idx)

    def _props_set_link(self, iid: str, link: bool) -> None:
        idx = self._props_row_map.get(iid)
        if idx is not None:
            self._props_rows[idx]["link"] = link

    def _props_bbox(self, iid: str) -> "tuple[int,int,int,int] | None":
        """Return (x, y, w, h) in canvas widget coords for the value column."""
        idx = self._props_row_map.get(iid)
        if idx is None:
            return None
        cv_w   = max(self._props_cv.winfo_width(), 160)
        split_x = max(80, int(cv_w * _PROPS_SPLIT))
        canvas_y = idx * _ORD_ROW_H
        scroll_top = int(self._props_cv.canvasy(0))
        screen_y = canvas_y - scroll_top
        cv_h = self._props_cv.winfo_height()
        if screen_y < -_ORD_ROW_H or screen_y >= cv_h:
            return None
        val_x = split_x + 1
        val_w = cv_w - val_x
        return (val_x, screen_y, val_w, _ORD_ROW_H)

    def _props_iid_at_y(self, widget_y: int) -> "str | None":
        canvas_y = int(self._props_cv.canvasy(widget_y))
        idx = canvas_y // _ORD_ROW_H
        return self._props_rows[idx]["iid"] if 0 <= idx < len(self._props_rows) else None

    def _props_idx_at_y(self, widget_y: int) -> "int | None":
        canvas_y = int(self._props_cv.canvasy(widget_y))
        idx = canvas_y // _ORD_ROW_H
        return idx if 0 <= idx < len(self._props_rows) else None

    def _props_redraw(self) -> None:
        cv = self._props_cv
        cv.delete("all")
        w = max(cv.winfo_width(), 160)

        if not self._props_rows:
            cv.configure(scrollregion=(0, 0, w, 40))
            return

        split_x  = max(80, int(w * _PROPS_SPLIT))
        total_h  = len(self._props_rows) * _ORD_ROW_H
        cv.configure(scrollregion=(0, 0, w, total_h))

        for i, row in enumerate(self._props_rows):
            y0  = i * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            is_hov = (i == self._props_hov_idx)

            if row["kind"] == "header":
                bg = _ORD_EVEN if i % 2 == 0 else _ORD_ODD
                cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"pr{i}")
                # Full separator line
                cv.create_line(6, mid, w - 6, mid, fill=_ORD_DIM, tags=f"pr{i}")
                # Text centered on full row width
                tid = cv.create_text(w // 2, mid, text=row["label"],
                                     fill=_ORD_DIM, font=(UI_FONT, 8),
                                     anchor="center", tags=f"pr{i}")
                # Mask line behind text with bg rect, then raise text
                tb = cv.bbox(tid)
                if tb:
                    cv.create_rectangle(tb[0] - 3, y0, tb[2] + 3, y1,
                                        fill=bg, outline="", tags=f"pr{i}")
                    cv.tag_raise(tid)
            else:
                bg = _ORD_HOV if is_hov else (_ORD_EVEN if i % 2 == 0 else _ORD_ODD)
                cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"pr{i}")

                # Divider
                cv.create_line(split_x, y0, split_x, y1, fill="#333333", tags=f"pr{i}")

                # Label
                lbl_color = _ORD_DIM if row["kind"] == "readonly" else _ORD_FG
                if row["link"]:
                    lbl_color = "#569cd6"
                cv.create_text(8, mid, text=row["label"],
                               fill=lbl_color, font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{i}")

                # Value
                val = row["value"]
                if row["swatch"]:
                    sx = split_x + 6
                    cv.create_rectangle(sx, mid - 6, sx + 12, mid + 6,
                                        fill=row["swatch"], outline="#555555",
                                        tags=f"pr{i}")
                    cv.create_text(sx + 16, mid, text=val,
                                   fill=_ORD_FG, font=(UI_FONT, 9),
                                   anchor="w", tags=f"pr{i}")
                elif row["warn"]:
                    cv.create_text(split_x + 8, mid, text=val,
                                   fill="#ff6b6b", font=(UI_FONT, 9),
                                   anchor="w", tags=f"pr{i}")
                else:
                    cv.create_text(split_x + 8, mid, text=val,
                                   fill=_ORD_FG, font=(UI_FONT, 9),
                                   anchor="w", tags=f"pr{i}")

    def _props_redraw_row(self, idx: int) -> None:
        """Redraw a single row in-place (no full delete)."""
        if not self._props_rows:
            return
        cv = self._props_cv
        w  = max(cv.winfo_width(), 160)
        cv.delete(f"pr{idx}")

        row     = self._props_rows[idx]
        y0      = idx * _ORD_ROW_H
        y1      = y0 + _ORD_ROW_H
        mid     = (y0 + y1) // 2
        split_x = max(80, int(w * _PROPS_SPLIT))
        is_hov  = (idx == self._props_hov_idx)

        if row["kind"] == "header":
            bg = _ORD_EVEN if idx % 2 == 0 else _ORD_ODD
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"pr{idx}")
            cv.create_line(6, mid, w - 6, mid, fill=_ORD_DIM, tags=f"pr{idx}")
            tid = cv.create_text(w // 2, mid, text=row["label"],
                                 fill=_ORD_DIM, font=(UI_FONT, 8),
                                 anchor="center", tags=f"pr{idx}")
            tb = cv.bbox(tid)
            if tb:
                cv.create_rectangle(tb[0] - 3, y0, tb[2] + 3, y1,
                                    fill=bg, outline="", tags=f"pr{idx}")
                cv.tag_raise(tid)
        else:
            bg = _ORD_HOV if is_hov else (_ORD_EVEN if idx % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"pr{idx}")
            cv.create_line(split_x, y0, split_x, y1, fill="#333333", tags=f"pr{idx}")

            lbl_color = _ORD_DIM if row["kind"] == "readonly" else _ORD_FG
            if row["link"]:
                lbl_color = "#569cd6"
            cv.create_text(8, mid, text=row["label"],
                           fill=lbl_color, font=(UI_FONT, 9),
                           anchor="w", tags=f"pr{idx}")

            val = row["value"]
            if row["swatch"]:
                sx = split_x + 6
                cv.create_rectangle(sx, mid - 6, sx + 12, mid + 6,
                                    fill=row["swatch"], outline="#555555",
                                    tags=f"pr{idx}")
                cv.create_text(sx + 16, mid, text=val,
                               fill=_ORD_FG, font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{idx}")
            elif row["warn"]:
                cv.create_text(split_x + 8, mid, text=val,
                               fill="#ff6b6b", font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{idx}")
            else:
                cv.create_text(split_x + 8, mid, text=val,
                               fill=_ORD_FG, font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{idx}")

    # ── Order tab internals ───────────────────────────────────────────────────

    def _order_redraw(self) -> None:
        cv = self._order_cv
        cv.delete("all")
        self._order_bgs.clear()
        w = cv.winfo_width()
        if w <= 1:
            return
        if not self._order_widgets:
            cv.create_text(
                w // 2, 40,
                text="No widgets on form.",
                fill=_ORD_DIM, font=(UI_FONT, 9), anchor="center",
            )
            cv.configure(scrollregion=(0, 0, w, 80))
            return
        total_h = len(self._order_widgets) * _ORD_ROW_H
        cv.configure(scrollregion=(0, 0, w, total_h))
        for i, widget in enumerate(self._order_widgets):
            self._order_draw_row(widget, i, w)

    def _order_draw_row(self, widget: WidgetDescriptor, idx: int, w: int) -> None:
        cv  = self._order_cv
        y   = idx * _ORD_ROW_H
        bg  = self._order_row_color(idx)
        tag = f"orow{idx}"

        rect = cv.create_rectangle(0, y, w, y + _ORD_ROW_H - 1,
                                   fill=bg, outline="", tags=tag)
        self._order_bgs[idx] = rect

        # Number badge
        r = 9
        bx, by = r + 4, y + _ORD_ROW_H // 2
        cv.create_oval(bx - r, by - r, bx + r, by + r,
                       fill=_ORD_NUM, outline="", tags=tag)
        cv.create_text(bx, by, text=str(idx + 1), fill="#ffffff",
                       font=(UI_FONT, 7, "bold"), anchor="center", tags=tag)

        # Widget ID
        cv.create_text(bx + r + 6, by, text=widget.id,
                       fill=_ORD_FG, font=("Consolas", 9),
                       anchor="w", tags=tag)

        # Type (dim, right-aligned)
        cv.create_text(w - 8, by, text=widget.type,
                       fill=_ORD_DIM, font=(UI_FONT, 8),
                       anchor="e", tags=tag)

        cv.tag_bind(tag, "<Enter>", lambda e, i=idx: self._order_hover_on(i))
        cv.tag_bind(tag, "<Leave>", lambda e, i=idx: self._order_hover_off(i))

    def _order_row_color(self, idx: int) -> str:
        if idx < len(self._order_widgets):
            if self._order_widgets[idx].id == self._order_sel_id:
                return _ORD_SEL
        return _ORD_EVEN if idx % 2 == 0 else _ORD_ODD

    def _order_hover_on(self, idx: int) -> None:
        if idx in self._order_bgs and self._order_drag_idx is None:
            wid = self._order_widgets[idx].id if idx < len(self._order_widgets) else None
            if wid != self._order_sel_id:
                self._order_cv.itemconfigure(self._order_bgs[idx], fill=_ORD_HOV)

    def _order_hover_off(self, idx: int) -> None:
        if idx in self._order_bgs:
            self._order_cv.itemconfigure(self._order_bgs[idx],
                                         fill=self._order_row_color(idx))

    def _order_press(self, event) -> None:
        idx = int(self._order_cv.canvasy(event.y)) // _ORD_ROW_H
        if 0 <= idx < len(self._order_widgets):
            self._order_drag_idx = idx
            if self._on_select_widget:
                self._on_select_widget(self._order_widgets[idx].id)

    def _order_motion(self, event) -> None:
        if self._order_drag_idx is None:
            return
        cv      = self._order_cv
        target  = self._order_drop_target(event.y)
        ghost_y = target * _ORD_ROW_H
        if self._order_drag_ghost is not None:
            cv.coords(self._order_drag_ghost, 0, ghost_y, cv.winfo_width(), ghost_y)
        else:
            self._order_drag_ghost = cv.create_line(
                0, ghost_y, cv.winfo_width(), ghost_y,
                fill="#007acc", width=2, tags="order_ghost",
            )
        cv.tag_raise("order_ghost")

    def _order_release(self, event) -> None:
        src = self._order_drag_idx
        if src is None:
            return
        if self._order_drag_ghost is not None:
            self._order_cv.delete(self._order_drag_ghost)
            self._order_drag_ghost = None
        self._order_drag_idx = None

        target = self._order_drop_target(event.y)
        dst = target if target <= src else target - 1
        dst = max(0, min(dst, len(self._order_widgets) - 1))

        if dst != src and self._on_reorder_widget and self._order_widgets:
            self._on_reorder_widget(self._order_widgets[src].id, dst)

    def _order_drop_target(self, canvas_y: int) -> int:
        """Return insertion index (0..N) from a canvas y coordinate."""
        cy  = int(self._order_cv.canvasy(canvas_y))
        idx = cy // _ORD_ROW_H
        if cy % _ORD_ROW_H > _ORD_ROW_H // 2:
            idx += 1
        return max(0, min(idx, len(self._order_widgets)))

    def _set_selector(self, widget_id: str | None) -> None:
        """Update the selector label to reflect the currently selected item."""
        for label, wid in self._selector_items:
            if wid == widget_id:
                self._selector_label.config(text=label)
                return
        # Fallback: show generic text if selector not yet populated
        if widget_id is None:
            self._selector_label.config(text="Form")
        else:
            self._selector_label.config(text=widget_id)

    def _open_selector_menu(self, event=None) -> None:
        """Pop up the control selector dropdown."""
        if not self._selector_items:
            return
        menu = tk.Menu(
            self.winfo_toplevel(), tearoff=0,
            bg="#2d2d2d", fg="#cccccc",
            activebackground="#094771", activeforeground="#ffffff",
            relief="flat", bd=1,
        )
        for label, wid in self._selector_items:
            def _cmd(w=wid):
                if self._on_select_widget:
                    self._on_select_widget(w)
            menu.add_command(label=label, command=_cmd, font=(UI_FONT, 9))
        try:
            rx = self._selector_label.winfo_rootx()
            ry = self._selector_label.winfo_rooty() + self._selector_label.winfo_height()
            menu.tk_popup(rx, ry)
        finally:
            menu.grab_release()

    def _show_status(self, message: str, duration_ms: int = 2000) -> None:
        """Briefly show an error message in the status bar at the bottom of the panel."""
        if self._status_after:
            self.after_cancel(self._status_after)
        self._status_label.config(text=message, fg="#ff6b6b")
        def _clear():
            self._status_after = None
            self._status_label.config(text="")
        self._status_after = self.after(duration_ms, _clear)

    def _show_hint(self, text: str) -> None:
        """Show a grey informational hint while hovering — only when no timed error is active."""
        if self._status_after is None:
            self._status_label.config(text=text, fg="#888888")

    def _clear_hint(self) -> None:
        if self._status_after is None:
            if self._nb.select() == str(self._order_frame):
                self._show_hint(
                    "Drag rows to reorder  ·  Tab key visits widgets in this order"
                )
            elif self._nb.select() == str(self._handlers_frame):
                self._show_hint("Click a row to enable or disable the handler")
            else:
                self._status_label.config(text="")

    def _on_tab_changed(self, _event=None) -> None:
        if self._nb.select() == str(self._order_frame):
            self._show_hint(
                "Drag rows to reorder  ·  Tab key visits widgets in this order"
            )
        elif self._nb.select() == str(self._handlers_frame):
            self._show_hint("Click a row to enable or disable the handler")
        else:
            self._status_label.config(text="")

    def flash_events_tab(self) -> None:
        """Switch to the Events tab; if already there, open the Events guide."""
        if self._nb.select() == str(self._events_frame):
            self._open_event_guide()
        else:
            self._nb.select(self._events_frame)

    def _open_event_guide(self, event=None) -> None:
        """Open the paginated Events guide window."""
        d = self._current_widget
        reg = REGISTRY.get(d.type, {}) if d else {}
        events = reg.get("events", [])

        # Build the events reference list as a formatted string for the second page
        lines: list[str] = []
        for ev in events:
            binding, desc = _EVENT_DESCRIPTIONS.get(ev, ("", ev))
            lines.append(f"{ev:<14}  {binding:<22}  {desc}")
        events_text = "\n".join(lines) if lines else "No events available for this widget type."

        widget_label = d.type if d else "Widget"

        GuideWindow(self, "Events Guide", [
            GuidePage(
                title="What are Events?",
                sections=[
                    ("THE IDEA",
                     "Events let your form react to things the user does — clicking a button, "
                     "typing in a field, moving the mouse. You wire an event to a handler method "
                     "and IDOL generates the stub for you.", "#569cd6"),
                    ("WIRING AN EVENT",
                     "1. Select a widget on the canvas.\n"
                     "2. Switch to the Events tab in the Properties panel.\n"
                     "3. Click the event row you want (e.g. click).\n"
                     "4. Type a method name starting with an underscore (e.g. _on_button_click).\n"
                     "5. Generate Code — the stub appears in your .py file ready to fill in.",
                     "#73c991"),
                    ("NAMING CONVENTION",
                     "Always prefix your handler names with an underscore (e.g. _on_submit). "
                     "Non-underscore names are treated as public helper methods and will appear "
                     "in the Functions section instead. IDOL warns you in red if you forget.",
                     "#e2c08d"),
                ],
                plain_english=(
                    "Think of events like a doorbell. The doorbell is the event (someone pressed it). "
                    "Your handler is what happens next (you walk to the door). "
                    "You decide which doorbells to listen for and what to do when they ring."
                ),
            ),
            GuidePage(
                title=f"Available Events — {widget_label}",
                sections=[
                    ("EVENT REFERENCE",
                     events_text, "#569cd6"),
                    ("AUTO-WIRE",
                     "Hover over an unwired event row and click the ✦ icon that appears to "
                     "auto-fill a handler name based on the widget name. "
                     "You can also type any name directly in the Handler column.",
                     "#cccccc"),
                    ("COMMAND EVENT",
                     "The command event (Button, Checkbutton, Radiobutton, Scale, Spinbox) is wired "
                     "as command= in the widget constructor rather than a .bind() call — "
                     "this is the standard tkinter pattern. Scale passes the current value "
                     "as an argument; use *args in the handler signature to receive it.",
                     "#e2c08d"),
                ],
                plain_english=(
                    "Each event maps to a tkinter binding string shown in the middle column. "
                    "IDOL handles the .bind() call for you — just name the method and write the body."
                ),
            ),
        ])

    def refresh_widget(self, descriptor: WidgetDescriptor) -> None:
        """Re-populate without switching the notebook tab (for canvas drag updates)."""
        if self._current_widget and self._current_widget.id == descriptor.id:
            self.load_widget(descriptor)

    # ── Populate helpers ──────────────────────────────────────────────────────

    def _populate_props(self, d: WidgetDescriptor, reg: dict) -> None:
        self._props_clear()
        # Name
        self._props_insert("widget__name", "name", d.id)
        # Geometry
        for key in ("x", "y", "width", "height"):
            self._props_insert(f"geo__{key}", key, str(getattr(d, key)))
        # Parent container (read-only)
        parent_val = d.parent_id if d.parent_id else "(form)"
        self._props_insert("geo__parent", "parent", parent_val, kind="readonly")
        # For children of a Notebook: show which tab this widget lives on
        if d.parent_id and self._form:
            par = self._form.get_widget(d.parent_id)
            if par and REGISTRY.get(par.type, {}).get("is_notebook"):
                self._props_insert("nb__tab", "  tab", d.tab or "")
        # Widget-specific props
        defaults = reg.get("default_props", {})
        color_props = reg.get("color_props", [])
        _state_reserved = (
            {"state"} | {c for clist in reg.get("state_color_props", {}).values()
                         for c in clist}
            if reg.get("state_prop") else set()
        )
        _validate_reserved = (
            {"validate", "validatecommand", "vcmd_args", "invalidcommand"}
            if reg.get("validate_prop") else set()
        )
        _colorize_reserved = (
            {"colorize", "colorize_altbg"}
            if reg.get("colorize_prop") else set()
        )
        seen: set[str] = set()
        for key in list(defaults) + [k for k in d.props if k not in defaults]:
            if key in seen or key in _state_reserved or key in _validate_reserved \
                    or key in _colorize_reserved:
                continue
            seen.add(key)
            val = d.props.get(key, defaults.get(key, ""))
            self._props_insert(f"prop__{key}", _PROP_LABELS.get(key, key), _display(val))
        # Color props — always show, apply swatches
        for key in color_props:
            val = d.props.get(key, "")
            if key not in seen:
                self._props_insert(f"prop__{key}", _PROP_LABELS.get(key, key), val)
                seen.add(key)
            if val:
                self._props_set_swatch(f"prop__{key}", val.upper())
        # State row + conditional color props
        if reg.get("state_prop"):
            current_state = d.props.get("state", "normal")
            self._props_insert("prop__state", "state", current_state)
            seen.add("state")
            state_colors = reg.get("state_color_props", {})
            for color_key in state_colors.get(current_state, []):
                label = _STATE_COLOR_LABELS.get(color_key, f"  --{color_key}")
                val   = d.props.get(color_key, "")
                self._props_insert(f"prop__{color_key}", label, val)
                seen.add(color_key)
                if val:
                    self._props_set_swatch(f"prop__{color_key}", val.upper())
        # Validate row + conditional sub-rows
        if reg.get("validate_prop"):
            current_validate = d.props.get("validate", "none")
            self._props_insert("prop__validate", "validate", current_validate)
            seen.add("validate")
            if current_validate != "none":
                for v_key, v_label in (("validatecommand", "  --vcmd"),
                                       ("invalidcommand",  "  --ivcmd")):
                    val = d.props.get(v_key, "")
                    self._props_insert(f"prop__{v_key}", v_label, val)
                    if val and not val.startswith("_"):
                        self._props_set_warn(f"prop__{v_key}", True)
                    if v_key == "validatecommand":
                        self._props_insert("prop__vcmd_args", "  --args",
                                           d.props.get("vcmd_args", "%P"))
                seen.update({"validatecommand", "vcmd_args", "invalidcommand"})
        # Colorize row + conditional alt-bg
        if reg.get("colorize_prop"):
            current_colorize = bool(d.props.get("colorize", False))
            self._props_insert("prop__colorize", "colorize", str(current_colorize))
            seen.add("colorize")
            if current_colorize:
                alt_bg = d.props.get("colorize_altbg", "")
                self._props_insert("prop__colorize_altbg", "  --alt bg", alt_bg)
                seen.add("colorize_altbg")
                if alt_bg:
                    self._props_set_swatch("prop__colorize_altbg", alt_bg.upper())
        # Variable binding section
        if reg.get("variable_prop"):
            var_types = reg.get("variable_types", ["StringVar"])
            vb = d.variable
            self._props_insert("var__section", "Variable", "", kind="header")
            self._props_insert("var__name",    "  variable", vb.name if vb else "")
            self._props_insert("var__type",    "  type",
                               vb.var_type if vb else var_types[0])
            self._props_insert("var__initial", "  initial", vb.initial if vb else "")
        # Layout / anchor section
        self._props_insert("anchor__section", "Layout", "", kind="header")
        anchor_disp = _ANCHOR_DISPLAY.get(d.anchor, d.anchor or "(none)")
        self._props_insert("anchor__value", "  anchor", anchor_disp)
        self._props_redraw()

    def _populate_events(self, d: WidgetDescriptor, reg: dict) -> None:
        self._events_clear()
        for ev in reg.get("events", []):
            handler = d.events.get(ev, "")
            iid     = f"ev__{ev}"
            self._events_insert(iid, ev, handler)
            if handler and not handler.startswith("_"):
                self._events_set_warn(iid, True)
        self._events_insert("ev__learn_guide", "? Events", "", kind="guide")
        self._events_redraw()

    # ── Props canvas input handlers ───────────────────────────────────────────

    def _on_prop_motion(self, event: tk.Event) -> None:
        idx = self._props_idx_at_y(event.y)
        if idx == self._props_hov_idx:
            if idx is not None:
                self._update_prop_clear_btn(idx)
            return
        old = self._props_hov_idx
        self._props_hov_idx = idx
        if old is not None:
            self._props_redraw_row(old)
        if idx is not None:
            self._props_redraw_row(idx)
            row = self._props_rows[idx]
            iid = row["iid"]
            self._update_prop_clear_btn(idx)
            key = iid.split("__", 1)[-1] if "__" in iid else iid
            hint = _PROP_HINTS.get(iid) or _PROP_HINTS.get(key)
            if hint:
                self._show_hint(hint)
            else:
                self._clear_hint()
        else:
            self._prop_clear_btn.place_forget()
            self._clear_hint()

    def _update_prop_clear_btn(self, idx: int) -> None:
        row = self._props_rows[idx]
        iid = row["iid"]
        val = row["value"]
        if self._is_prop_clearable(iid) and val and (iid != "anchor__value" or val != "(none)"):
            bbox = self._props_bbox(iid)
            if bbox:
                x, y, w, h = bbox
                bw = 18
                self._prop_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._prop_clear_btn.lift()
                self._prop_clear_iid = iid
                return
        self._prop_clear_btn.place_forget()
        self._prop_clear_iid = None

    def _on_prop_canvas_leave(self, event: tk.Event) -> None:
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest is self._prop_clear_btn:
            return
        if self._props_hov_idx is not None:
            old = self._props_hov_idx
            self._props_hov_idx = None
            self._props_redraw_row(old)
        self._prop_clear_btn.place_forget()
        self._clear_hint()

    def _on_prop_btn_leave(self, event: tk.Event) -> None:
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest is self._props_cv:
            return
        self._prop_clear_btn.config(fg="#888888")
        self._prop_clear_btn.place_forget()
        if self._props_hov_idx is not None:
            old = self._props_hov_idx
            self._props_hov_idx = None
            self._props_redraw_row(old)
        self._clear_hint()

    def _on_prop_canvas_click(self, event: tk.Event) -> None:
        if self._prop_clearing:
            self._prop_clearing = False
            return
        iid = self._props_iid_at_y(event.y)
        if iid:
            self._dispatch_prop_click(iid)

    def _dispatch_prop_click(self, row: str) -> None:
        if row in ("var__section", "geo__parent", "anchor__section"):
            return
        if row == "nb__tab":
            self._open_nb_tab_picker(row)
            return
        if row == "anchor__value":
            self._open_anchor_picker(row)
            return
        if row == "form__menu_bar":
            self._open_menu_editor()
        elif row == "form__bg" or self._is_color_row(row):
            self._open_color_picker(row)
        elif row == "form__border_style":
            self._props_open_dropdown(row, ["sizable", "fixed", "none"], self._commit_prop)
        elif row in ("form__maximize_box", "form__always_on_top"):
            self._props_open_dropdown(row, ["True", "False"], self._commit_prop)
        elif row == "prop__state":
            d = self._current_widget
            if d is None:
                return
            reg = REGISTRY.get(d.type, {})
            self._props_open_dropdown(row,
                reg.get("state_values", ["normal", "disabled"]), self._commit_prop)
        elif row == "prop__validate":
            d = self._current_widget
            if d is None:
                return
            reg = REGISTRY.get(d.type, {})
            self._props_open_dropdown(row,
                reg.get("validate_values",
                        ["none", "focus", "focusin", "focusout", "key", "all"]),
                self._commit_prop)
        elif row == "prop__vcmd_args":
            self._props_open_dropdown(row, _VCMD_ARG_PRESETS, self._commit_prop)
        elif row == "prop__colorize":
            self._props_open_dropdown(row, ["True", "False"], self._commit_prop)
        elif row.startswith("prop__") and (self._current_widget or self._multi_widgets):
            key  = row[6:]
            d_ref = self._current_widget or self._multi_widgets[0]
            if key == "font":
                if self._current_widget:
                    self._open_font_picker(row)
                return
            if isinstance(d_ref.props.get(key), list):
                if self._current_widget:
                    if key == "tabs":
                        self._open_notebook_tabs_editor(row)
                    else:
                        self._open_list_editor(row)
                return
            reg     = REGISTRY.get(d_ref.type, {})
            choices = reg.get("prop_choices", {}).get(key)
            if choices:
                self._props_open_dropdown(row, choices, self._commit_prop)
                return
            self._props_open_editor(row, self._commit_prop)
        elif row == "var__name":
            self._props_open_variable_picker(row)
        elif row == "var__type":
            d = self._current_widget
            if d is None:
                return
            reg       = REGISTRY.get(d.type, {})
            var_types = reg.get("variable_types", ["StringVar"])
            self._props_open_dropdown(row, var_types, self._commit_prop)
        elif row.startswith(("geo__", "widget__", "var__", "form__")):
            self._props_open_editor(row, self._commit_prop)

    # ── Props canvas editors ──────────────────────────────────────────────────

    def _props_open_editor(self, iid: str, commit_fn) -> None:
        self._dismiss_editor()
        bbox = self._props_bbox(iid)
        if not bbox:
            return
        x, y, w, h = bbox
        entry = tk.Entry(
            self._props_cv,
            font=("TkDefaultFont", 8),
            bg="#3c3c3c", fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#007acc",
        )
        entry.insert(0, self._props_get(iid))
        entry.place(x=x, y=y, width=w, height=h)
        self._entry_editor = entry

        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        self._props_cv.after_idle(_grab_focus)

        def commit(_=None):
            if self._entry_editor is not entry:
                return
            val = entry.get()
            self._pending_commit = None
            self._dismiss_editor()
            self._props_set(iid, val)
            commit_fn(iid, val)

        def cancel(_=None):
            self._pending_commit = None
            self._dismiss_editor()

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<Escape>",   cancel)
        entry.bind("<FocusOut>", commit)
        self._pending_commit = commit

    def _props_open_dropdown(self, iid: str, values: list, commit_fn) -> None:
        self._dismiss_editor()
        bbox = self._props_bbox(iid)
        if not bbox:
            return
        x, y, w, h = bbox

        prop_key   = iid.split("__", 1)[-1] if "__" in iid else ""
        item_hints = _DROPDOWN_ITEM_HINTS.get(prop_key, {})

        overlay = tk.Frame(self._props_cv, bg="#2d2d2d",
                           highlightthickness=1,
                           highlightbackground="#007acc")

        def _do_dismiss():
            try:
                overlay.destroy()
            except Exception:
                pass
            if self._entry_editor is overlay:
                self._entry_editor = None

        for val in values:
            lbl = tk.Label(overlay, text=val, bg="#2d2d2d", fg="#cccccc",
                           font=(UI_FONT, 9), anchor="w",
                           padx=6, pady=2, cursor="hand2")
            lbl.pack(fill="x")

            def _enter(e, v=val, lb=lbl):
                lb.config(bg="#094771", fg="#ffffff")
                hint = item_hints.get(v, "")
                if hint:
                    self._show_hint(hint)

            def _leave(e, lb=lbl):
                lb.config(bg="#2d2d2d", fg="#cccccc")

            def _click(e, v=val):
                _do_dismiss()
                self._props_set(iid, v)
                commit_fn(iid, v)

            lbl.bind("<Enter>",          _enter)
            lbl.bind("<Leave>",          _leave)
            lbl.bind("<ButtonRelease-1>", _click)

        item_w = max(w, max(len(v) * 7 + 24 for v in values) if values else w)
        overlay.place(x=x, y=y + h, width=item_w)
        self._entry_editor = overlay

        top   = self._props_cv.winfo_toplevel()
        _bid: list = []

        def _global_click(e):
            try:
                ox, oy = overlay.winfo_rootx(), overlay.winfo_rooty()
                ow, oh = overlay.winfo_width(), overlay.winfo_height()
                if not (ox <= e.x_root <= ox + ow and oy <= e.y_root <= oy + oh):
                    _do_dismiss()
                    if _bid:
                        top.unbind("<Button-1>", _bid[0])
            except Exception:
                pass

        _bid.append(top.bind("<Button-1>", _global_click, add=True))

    def _props_open_variable_picker(self, iid: str) -> None:
        from designer.var_picker import collect_form_variables, show_variable_popup
        self._dismiss_editor()
        if self._form is None:
            return
        bbox = self._props_bbox(iid)
        if not bbox:
            return
        x, y, w, h = bbox
        entry = tk.Entry(
            self._props_cv,
            font=("TkDefaultFont", 8),
            bg="#3c3c3c", fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#007acc",
        )
        entry.insert(0, self._props_get(iid))
        entry.place(x=x, y=y, width=w, height=h)
        self._entry_editor = entry

        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        self._props_cv.after_idle(_grab_focus)

        popup_ref: list = [None]
        variables     = collect_form_variables(self._form)
        var_type_map  = {n: vt for n, vt in variables}

        def _commit(_=None):
            val = entry.get()
            if popup_ref[0] and popup_ref[0].winfo_exists():
                popup_ref[0].destroy()
            self._dismiss_editor()
            self._props_set(iid, val)
            self._commit_prop(iid, val)

        def _on_select(name: str):
            entry.delete(0, "end")
            entry.insert(0, name)
            popup_ref[0] = None
            _commit()
            var_type = var_type_map.get(name)
            if var_type and self._props_exists("var__type"):
                self._props_set("var__type", var_type)
                self._commit_prop("var__type", var_type)

        entry.bind("<Return>", _commit)
        entry.bind("<Tab>",    _commit)
        entry.bind("<Escape>", lambda _: (
            popup_ref[0].destroy() if popup_ref[0] and popup_ref[0].winfo_exists() else None,
            self._dismiss_editor(),
        ))

        def _on_var_remove(name: str):
            if self._form is None:
                return
            for w in self._form.widgets:
                if w.variable and w.variable.name == name:
                    w.variable.name = ""
                    if self._on_prop_change:
                        self._on_prop_change(w.id, "__variable__", w.variable)
            for item in self._form.menu_items:
                if item.variable == name:
                    item.variable = ""
            d = self._current_widget
            if d is not None:
                self._populate_props(d, REGISTRY.get(d.type, {}))

        popup_ref[0] = show_variable_popup(
            anchor=entry,
            variables=variables,
            on_select=_on_select,
            entry_ref=entry,
            on_remove=_on_var_remove,
        )

    # ── Click handlers ────────────────────────────────────────────────────────

    # _on_prop_click replaced by _on_prop_canvas_click + _dispatch_prop_click above

    # _on_event_click / _on_event_double_click replaced by
    # _on_event_canvas_click / _on_event_canvas_dblclick above

    # ── Inline cell editor ────────────────────────────────────────────────────

    def _open_editor(self, tree: ttk.Treeview, row: str, col: str,
                     commit_fn: Callable[[str, str], None]) -> None:
        self._dismiss_editor()
        bbox = tree.bbox(row, col)
        if not bbox:
            return
        x, y, w, h = bbox
        entry = tk.Entry(
            tree,
            font=("TkDefaultFont", 8),
            bg="#3c3c3c", fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#007acc",
        )
        entry.insert(0, tree.set(row, col))
        entry.place(x=x, y=y, width=w, height=h)
        self._entry_editor = entry

        # Defer focus so the treeview's own Button-1 bindings can't steal it back
        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        tree.after_idle(_grab_focus)

        def commit(_=None):
            if self._entry_editor is not entry:
                return  # stale FocusOut after editor already replaced
            val = entry.get()
            self._pending_commit = None
            self._dismiss_editor()
            tree.set(row, col, val)
            commit_fn(row, val)

        def cancel(_=None):
            self._pending_commit = None
            self._dismiss_editor()

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<Escape>",   cancel)
        entry.bind("<FocusOut>", commit)
        self._pending_commit = commit

    # _open_variable_picker replaced by _props_open_variable_picker above

    def _open_handler_picker(self, iid: str) -> None:
        """Inline entry + handler picker popup for event handler rows (canvas-based)."""
        from designer.var_picker import collect_form_handlers, show_handler_popup
        if not iid.startswith("ev__") and not iid.startswith("form_ev__"):
            return
        self._dismiss_editor()
        bbox = self._events_bbox(iid)
        if not bbox:
            return
        x, y, w, h = bbox
        cv = self._events_cv
        # value column starts at the split
        split_x = int(cv.winfo_width() * _PROPS_SPLIT)
        val_w = cv.winfo_width() - split_x - 1
        entry = tk.Entry(
            cv,
            font=("TkDefaultFont", 8),
            bg="#3c3c3c", fg="#cccccc",
            insertbackground="#cccccc",
            relief="flat", bd=0,
            highlightthickness=1,
            highlightbackground="#007acc",
        )
        entry.insert(0, self._events_get(iid))
        entry.place(x=split_x, y=y, width=val_w, height=h)
        self._entry_editor = entry

        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        cv.after_idle(_grab_focus)

        popup_ref: list = [None]

        def _commit(_=None):
            val = entry.get()
            if popup_ref[0] and popup_ref[0].winfo_exists():
                popup_ref[0].destroy()
            self._dismiss_editor()
            self._events_set(iid, val)
            self._commit_event(iid, val)

        def _on_select(name: str):
            entry.delete(0, "end")
            entry.insert(0, name)
            popup_ref[0] = None
            _commit()

        entry.bind("<Return>", _commit)
        entry.bind("<Tab>",    _commit)
        entry.bind("<Escape>", lambda _: (
            popup_ref[0].destroy() if popup_ref[0] and popup_ref[0].winfo_exists() else None,
            self._dismiss_editor(),
        ))

        def _on_handler_remove(name: str):
            if self._form is None:
                return
            for w in self._form.widgets:
                for ev_key in list(w.events.keys()):
                    if w.events.get(ev_key) == name:
                        del w.events[ev_key]
                        if self._on_event_change:
                            self._on_event_change(w.id, ev_key, "")
            for item in self._form.menu_items:
                if item.command_handler == name:
                    item.command_handler = ""
            for ev_key in list(self._form.form_events.keys()):
                if self._form.form_events.get(ev_key) == name:
                    del self._form.form_events[ev_key]
                    row_iid = f"form_ev__{ev_key}"
                    if self._events_exists(row_iid):
                        self._events_set(row_iid, "")
                    if self._on_event_change:
                        self._on_event_change("__form__", ev_key, "")
            d = self._current_widget
            if d is not None:
                self._populate_events(d, REGISTRY.get(d.type, {}))

        handlers = collect_form_handlers(self._form) if self._form is not None else []
        popup_ref[0] = show_handler_popup(
            anchor=entry,
            handlers=handlers,
            on_select=_on_select,
            entry_ref=entry,
            on_remove=_on_handler_remove,
        )

    def _open_list_editor(self, row: str) -> None:
        """Inline list editor for array-type props (e.g. Combobox values).

        Enter adds an item and keeps the entry focused; × removes an item.
        Clicking outside (FocusOut to a widget outside the panel) dismisses.
        """
        self._dismiss_editor()
        d = self._current_widget
        if d is None:
            return
        key = row[6:]  # strip "prop__"
        current_list: list = list(d.props.get(key, []))

        bbox = self._props_bbox(row)
        if not bbox:
            return
        _, by, _, bh = bbox
        by = by + bh
        tree_w = self._props_cv.winfo_width() - 4

        panel = tk.Frame(self._props_cv, bg="#2d2d2d",
                         highlightthickness=1,
                         highlightbackground="#007acc")
        items_frame = tk.Frame(panel, bg="#2d2d2d")
        items_frame.pack(fill="x", padx=2, pady=(2, 0))

        def _do_commit():
            d.props[key] = list(current_list)
            self._props_set(row, _display(current_list))
            if self._on_prop_change:
                self._on_prop_change(d.id, key, list(current_list))

        entry_holder: list = []

        def _resize():
            panel.update_idletasks()
            h = panel.winfo_reqheight()
            panel.place(x=0, y=by, width=tree_w, height=max(h, 40))

        def _refresh_items():
            for child in items_frame.winfo_children():
                child.destroy()
            for i, item in enumerate(current_list):
                rf = tk.Frame(items_frame, bg="#2d2d2d")
                rf.pack(fill="x")
                tk.Label(rf, text=item, bg="#2d2d2d", fg="#cccccc",
                         font=("TkDefaultFont", 8), anchor="w").pack(
                             side="left", fill="x", expand=True, padx=(4, 0))
                xl = tk.Label(rf, text="×", bg="#2d2d2d", fg="#858585",
                              font=("TkDefaultFont", 8), cursor="hand2", padx=4)
                xl.pack(side="right")
                def _remove(idx=i):
                    del current_list[idx]
                    _refresh_items()
                    _do_commit()
                    if entry_holder:
                        entry_holder[0].focus_force()
                xl.bind("<Button-1>", lambda e, r=_remove: r())
            _resize()

        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(2, 0))
        entry = tk.Entry(panel, font=("TkDefaultFont", 8),
                         bg="#3c3c3c", fg="#cccccc",
                         insertbackground="#cccccc",
                         relief="flat", bd=0,
                         highlightthickness=0)
        entry.pack(fill="x", padx=2, pady=2, ipady=2)
        entry_holder.append(entry)

        _refresh_items()
        panel.place(x=0, y=by, width=tree_w)
        self._entry_editor = panel

        def _add_item(_=None):
            text = entry.get().strip()
            if text:
                current_list.append(text)
                entry.delete(0, "end")
                _refresh_items()
                _do_commit()
            entry.focus_force()
            return "break"

        _pending: list = []

        def _on_focus_out(_=None):
            aid = self._props_cv.after(100, _maybe_dismiss)
            _pending.append(aid)

        def _maybe_dismiss():
            try:
                fw = self._props_cv.winfo_toplevel().focus_get()
            except Exception:
                fw = None
            if fw is not None:
                w = fw
                while w is not None:
                    if w is panel:
                        return
                    try:
                        w = w.master
                    except Exception:
                        break
            _do_dismiss()

        def _do_dismiss(_=None):
            for aid in _pending:
                try:
                    self._props_cv.after_cancel(aid)
                except Exception:
                    pass
            try:
                panel.destroy()
            except Exception:
                pass
            if self._entry_editor is panel:
                self._entry_editor = None

        entry.bind("<Return>",   _add_item)
        entry.bind("<Escape>",   _do_dismiss)
        entry.bind("<FocusOut>", _on_focus_out)
        self._props_cv.after_idle(entry.focus_force)

    def _open_nb_tab_picker(self, row: str) -> None:
        """Dropdown to move a Notebook child to a different tab."""
        d = self._current_widget
        if d is None or not d.parent_id or not self._form:
            return
        par = self._form.get_widget(d.parent_id)
        if par is None:
            return
        tabs = par.props.get("tabs") or []
        if not tabs:
            return
        self._props_open_dropdown(row, tabs, self._commit_prop)

    def _open_notebook_tabs_editor(self, row: str) -> None:
        """Inline editor for Notebook tabs list with rename/add/remove."""
        self._dismiss_editor()
        d = self._current_widget
        if d is None:
            return
        current_list: list = list(d.props.get("tabs", ["Tab 1"]))

        bbox = self._props_bbox(row)
        if not bbox:
            return
        _, by, _, bh = bbox
        by = by + bh
        tree_w = self._props_cv.winfo_width() - 4

        panel = tk.Frame(self._props_cv, bg="#2d2d2d",
                         highlightthickness=1,
                         highlightbackground="#007acc")
        items_frame = tk.Frame(panel, bg="#2d2d2d")
        items_frame.pack(fill="x", padx=2, pady=(2, 0))

        def _do_commit(new_list: list) -> None:
            d.props["tabs"] = list(new_list)
            self._props_set(row, _display(new_list))
            if self._on_prop_change:
                self._on_prop_change(d.id, "tabs", list(new_list))

        entry_holder: list = []

        def _resize():
            panel.update_idletasks()
            h = panel.winfo_reqheight()
            panel.place(x=0, y=by, width=tree_w, height=max(h, 40))

        def _refresh_items():
            for child in items_frame.winfo_children():
                child.destroy()
            for i, tab in enumerate(current_list):
                rf = tk.Frame(items_frame, bg="#2d2d2d")
                rf.pack(fill="x")
                name_lbl = tk.Label(rf, text=tab, bg="#2d2d2d", fg="#cccccc",
                                    font=("TkDefaultFont", 8), anchor="w",
                                    cursor="hand2")
                name_lbl.pack(side="left", fill="x", expand=True, padx=(4, 0))
                xl = tk.Label(rf, text="×", bg="#2d2d2d", fg="#858585",
                              font=("TkDefaultFont", 8), cursor="hand2", padx=4)
                xl.pack(side="right")

                def _rename(idx=i, lbl=name_lbl):
                    old_name = current_list[idx]
                    ren_entry = tk.Entry(items_frame,
                                        font=("TkDefaultFont", 8),
                                        bg="#3c3c3c", fg="#cccccc",
                                        insertbackground="#cccccc",
                                        relief="flat", bd=0, highlightthickness=1,
                                        highlightbackground="#007acc")
                    lbl.pack_forget()
                    ren_entry.insert(0, old_name)
                    ren_entry.pack(fill="x", padx=4)
                    ren_entry.select_range(0, "end")
                    ren_entry.focus_force()

                    def _commit_rename(_=None):
                        new_name = ren_entry.get().strip()
                        if not new_name:
                            new_name = old_name
                        # Propagate rename to all children
                        if new_name != old_name and self._form:
                            for cw in self._form.widgets:
                                if cw.parent_id == d.id and cw.tab == old_name:
                                    cw.tab = new_name
                        current_list[idx] = new_name
                        _do_commit(current_list)
                        _refresh_items()

                    ren_entry.bind("<Return>", _commit_rename)
                    ren_entry.bind("<Escape>", lambda _: _refresh_items())
                    ren_entry.bind("<FocusOut>", lambda _: _commit_rename())

                name_lbl.bind("<Button-1>", lambda e, r=_rename: r())

                def _remove(idx=i):
                    removed = current_list[idx]
                    del current_list[idx]
                    remaining = list(current_list)
                    if remaining and self._form:
                        fallback = remaining[0]
                        for cw in self._form.widgets:
                            if cw.parent_id == d.id and cw.tab == removed:
                                cw.tab = fallback
                    elif not remaining and self._form:
                        for cw in self._form.widgets:
                            if cw.parent_id == d.id:
                                cw.tab = ""
                    _do_commit(current_list)
                    _refresh_items()
                    if entry_holder:
                        entry_holder[0].focus_force()

                xl.bind("<Button-1>", lambda e, r=_remove: r())
            _resize()

        ttk.Separator(panel, orient="horizontal").pack(fill="x", pady=(2, 0))
        entry = tk.Entry(panel, font=("TkDefaultFont", 8),
                         bg="#3c3c3c", fg="#cccccc",
                         insertbackground="#cccccc",
                         relief="flat", bd=0,
                         highlightthickness=0)
        entry.pack(fill="x", padx=2, pady=2, ipady=2)
        entry_holder.append(entry)

        _refresh_items()
        panel.place(x=0, y=by, width=tree_w)
        self._entry_editor = panel

        def _add_item(_=None):
            text = entry.get().strip()
            if text:
                current_list.append(text)
                entry.delete(0, "end")
                _refresh_items()
                _do_commit(current_list)
            entry.focus_force()
            return "break"

        _pending: list = []

        def _on_focus_out(_=None):
            aid = self._props_cv.after(100, _maybe_dismiss)
            _pending.append(aid)

        def _maybe_dismiss():
            try:
                fw = self._props_cv.winfo_toplevel().focus_get()
            except Exception:
                fw = None
            if fw is not None:
                w = fw
                while w is not None:
                    if w is panel:
                        return
                    try:
                        w = w.master
                    except Exception:
                        break
            _do_dismiss()

        def _do_dismiss(_=None):
            for aid in _pending:
                try:
                    self._props_cv.after_cancel(aid)
                except Exception:
                    pass
            try:
                panel.destroy()
            except Exception:
                pass
            if self._entry_editor is panel:
                self._entry_editor = None

        entry.bind("<Return>",   _add_item)
        entry.bind("<Escape>",   _do_dismiss)
        entry.bind("<FocusOut>", _on_focus_out)
        self._props_cv.after_idle(entry.focus_force)

    def _is_color_row(self, row_iid: str) -> bool:
        if not row_iid.startswith("prop__"):
            return False
        d = self._current_widget or (self._multi_widgets[0] if self._multi_widgets else None)
        if d is None:
            return False
        key = row_iid[6:]
        reg = REGISTRY.get(d.type, {})
        if key in reg.get("color_props", []):
            return True
        for color_list in reg.get("state_color_props", {}).values():
            if key in color_list:
                return True
        if key == "colorize_altbg" and reg.get("colorize_prop"):
            return True
        return False

    # Props that can be cleared back to "" (optional / skippable in codegen)
    _CLEARABLE_PROPS = {
        "show", "font", "justify", "relief", "borderwidth", "insertbackground",
        "wraplength", "resolution", "tickinterval", "increment", "maximum",
        "char_width", "char_height", "onvalue", "offvalue", "labelanchor",
        "selectmode", "wrap", "exportselection", "from_", "to",
    }

    def _is_prop_clearable(self, row_iid: str) -> bool:
        """Return True if this prop row has a value that can be cleared to empty."""
        if row_iid in ("var__name", "var__initial", "anchor__value", "form__bg"):
            return True
        if not row_iid.startswith("prop__"):
            return False
        key = row_iid[6:]
        if key in self._CLEARABLE_PROPS:
            return True
        return self._is_color_row(row_iid)

    def _open_dropdown(self, tree: ttk.Treeview, row: str, col: str,
                       values: list[str], commit_fn) -> None:
        self._dismiss_editor()
        bbox = tree.bbox(row, col)
        if not bbox:
            return
        x, y, w, h = bbox

        prop_key = row.split("__", 1)[-1] if "__" in row else ""
        item_hints = _DROPDOWN_ITEM_HINTS.get(prop_key, {})

        overlay = tk.Frame(tree, bg="#2d2d2d",
                           highlightthickness=1,
                           highlightbackground="#007acc")

        def _do_dismiss():
            try:
                overlay.destroy()
            except Exception:
                pass
            if self._entry_editor is overlay:
                self._entry_editor = None

        for val in values:
            lbl = tk.Label(overlay, text=val, bg="#2d2d2d", fg="#cccccc",
                           font=(UI_FONT, 9), anchor="w",
                           padx=6, pady=2, cursor="hand2")
            lbl.pack(fill="x")

            def _enter(e, v=val, l=lbl):
                l.config(bg="#094771", fg="#ffffff")
                hint = item_hints.get(v, "")
                if hint:
                    self._show_hint(hint)

            def _leave(e, l=lbl):
                l.config(bg="#2d2d2d", fg="#cccccc")

            def _click(e, v=val):
                _do_dismiss()
                tree.set(row, col, v)
                commit_fn(row, v)

            lbl.bind("<Enter>",           _enter)
            lbl.bind("<Leave>",           _leave)
            lbl.bind("<ButtonRelease-1>", _click)

        item_w = max(w, max(len(v) * 7 + 24 for v in values) if values else w)
        overlay.place(x=x, y=y + h, width=item_w)
        self._entry_editor = overlay

        top = tree.winfo_toplevel()
        _bid: list = []

        def _global_click(e):
            try:
                ox, oy = overlay.winfo_rootx(), overlay.winfo_rooty()
                ow, oh = overlay.winfo_width(), overlay.winfo_height()
                if not (ox <= e.x_root <= ox + ow and oy <= e.y_root <= oy + oh):
                    _do_dismiss()
                    if _bid:
                        top.unbind("<Button-1>", _bid[0])
            except Exception:
                pass

        _bid.append(top.bind("<Button-1>", _global_click, add=True))

    def _open_anchor_picker(self, row_iid: str) -> None:
        """Show a 3×3 grid popup for selecting the resize anchor preset."""
        self._dismiss_editor()
        bbox = self._props_bbox(row_iid)
        if not bbox:
            return
        x, y, w, h = bbox

        overlay = tk.Frame(self._props_cv, bg="#2d2d2d",
                           highlightthickness=1,
                           highlightbackground="#007acc")

        def _do_dismiss():
            try:
                overlay.destroy()
            except Exception:
                pass
            if self._entry_editor is overlay:
                self._entry_editor = None

        def _pick(anchor_val: str):
            _do_dismiss()
            disp = _ANCHOR_DISPLAY.get(anchor_val, anchor_val or "(none)")
            self._props_set(row_iid, disp)
            self._commit_prop(row_iid, anchor_val)

        # 3×3 grid
        grid_frame = tk.Frame(overlay, bg="#2d2d2d")
        grid_frame.pack(padx=4, pady=4)

        _GRID = [
            [("↖", "top_left"),    ("↑", "top"),    ("↗", "top_right")],
            [("←", "left"),        ("⊡", "all"),    ("→", "right")],
            [("↙", "bottom_left"), ("↓", "bottom"), ("↘", "bottom_right")],
        ]
        d = self._current_widget
        current = d.anchor if d else ""
        for r, row_cells in enumerate(_GRID):
            for c_idx, (sym, val) in enumerate(row_cells):
                active = (val == current)
                btn = tk.Label(
                    grid_frame, text=sym,
                    bg="#094771" if active else "#3c3c3c",
                    fg="#ffffff" if active else "#cccccc",
                    font=(UI_FONT, 10),
                    width=3, height=1,
                    relief="flat", cursor="hand2",
                )
                btn.grid(row=r, column=c_idx, padx=2, pady=2)

                def _enter(e, b=btn, v=val):
                    b.config(bg="#094771", fg="#ffffff")
                    self._show_hint(_ANCHOR_DESC.get(v, ""))

                def _leave(e, b=btn, v=val, cur=current):
                    b.config(bg="#094771" if v == cur else "#3c3c3c",
                             fg="#ffffff" if v == cur else "#cccccc")
                    self._clear_hint()

                btn.bind("<Enter>",           _enter)
                btn.bind("<Leave>",           _leave)
                btn.bind("<ButtonRelease-1>", lambda e, v=val: _pick(v))

        # Shift-key note
        tk.Label(overlay, text="Shift+resize ignores anchors",
                 bg="#2d2d2d", fg="#666666",
                 font=(UI_FONT, 7), anchor="center").pack(
            fill="x", padx=4, pady=(0, 4))

        # Position: 120px wide; flip above when near the canvas bottom
        popup_w = 120
        self._props_cv.update_idletasks()
        cv_w  = self._props_cv.winfo_width()
        cv_h  = self._props_cv.winfo_height()
        place_x = min(x, max(0, cv_w - popup_w - 2))
        overlay.place(x=place_x, y=y + h, width=popup_w)
        overlay.update_idletasks()
        popup_h = overlay.winfo_reqheight()
        if y + h + popup_h > cv_h:
            overlay.place(x=place_x, y=max(0, y - popup_h), width=popup_w)
        self._entry_editor = overlay

        top = self._props_cv.winfo_toplevel()
        _bid: list = []

        def _global_click(e):
            try:
                ox, oy = overlay.winfo_rootx(), overlay.winfo_rooty()
                ow, oh = overlay.winfo_width(), overlay.winfo_height()
                if not (ox <= e.x_root <= ox + ow and oy <= e.y_root <= oy + oh):
                    _do_dismiss()
                    if _bid:
                        top.unbind("<Button-1>", _bid[0])
            except Exception:
                pass

        _bid.append(top.bind("<Button-1>", _global_click, add=True))

    def _open_color_picker(self, row_iid: str) -> None:
        """Open a color picker for a color property cell."""
        current = self._props_get(row_iid).strip() or "#ffffff"
        from tkinter.colorchooser import askcolor
        result = askcolor(current, parent=self._props_cv.winfo_toplevel())
        color = result[1] if result else None
        if not color:
            return
        color = color.upper()
        self._props_set(row_iid, color)
        self._apply_color_swatch(row_iid, color)
        self._commit_prop(row_iid, color)

    def _open_menu_editor(self) -> None:
        self.open_menu_editor()

    def open_menu_editor(self, flash_item_idx: int | None = None) -> None:
        if self._form is None:
            return
        from designer.menu_editor import MenuEditor

        def _save(items):
            self._form.menu_items = items
            n = len(items)
            val = f"{n} item{'s' if n != 1 else ''}" if n else "(none)"
            self._props_set("form__menu_bar", val)
            if self._on_prop_change:
                self._on_prop_change("__form__", "menu_bar", items)

        editor = MenuEditor(self.winfo_toplevel(), self._form.menu_items, _save, form=self._form)
        if flash_item_idx is not None:
            def _flash():
                editor.select_item(flash_item_idx)
                editor.flash_command_field()
            editor.after(60, _flash)

    def _open_font_picker(self, row_iid: str) -> None:
        """Open the font chooser dialog for a font property cell."""
        from tkfontchooser import askfont
        d = self._current_widget
        if d is None:
            return

        # Build pre-population dict from current value (tuple or legacy string)
        current = d.props.get("font", "")
        init: dict = {}
        if isinstance(current, tuple) and current:
            init["family"] = current[0] if len(current) > 0 else ""
            init["size"]   = current[1] if len(current) > 1 else 10
            styles = set((current[2] if len(current) > 2 else "").split())
            if "bold"       in styles: init["weight"]     = "bold"
            if "italic"     in styles: init["slant"]      = "italic"
            if "underline"  in styles: init["underline"]  = 1
            if "overstrike" in styles: init["overstrike"] = 1
        elif isinstance(current, str) and current:
            parts = current.split()
            if parts: init["family"] = parts[0]
            if len(parts) > 1:
                try: init["size"] = int(parts[1])
                except ValueError: pass
            tags = {p.lower() for p in parts[2:]}
            if "bold"       in tags: init["weight"]     = "bold"
            if "italic"     in tags: init["slant"]      = "italic"
            if "underline"  in tags: init["underline"]  = 1
            if "overstrike" in tags: init["overstrike"] = 1

        result = askfont(self.winfo_toplevel(), title="Choose Font", font=init)
        if not result:
            return

        # Build tuple: ("Family", size, "bold italic") — unambiguous for any family name
        family = result.get("family", "TkDefaultFont")
        size   = result.get("size", 10)
        styles = []
        if result.get("weight")     == "bold":   styles.append("bold")
        if result.get("slant")      == "italic":  styles.append("italic")
        if result.get("underline"):               styles.append("underline")
        if result.get("overstrike"):              styles.append("overstrike")
        font_tuple = (family, size, " ".join(styles)) if styles else (family, size)

        # Display as "Family, size, style" in the panel; store tuple in props
        display = f"{family}, {size}" + (f", {' '.join(styles)}" if styles else "")
        self._props_set(row_iid, display)
        d.props["font"] = font_tuple
        if self._on_prop_change:
            self._on_prop_change(d.id, "font", font_tuple)

    def _apply_color_swatch(self, row_iid: str, color: str) -> None:
        """Store color swatch for the row and redraw it."""
        self._props_set_swatch(row_iid, color)

    # _on_event_hover / _on_event_leave replaced by _on_event_motion / _on_event_canvas_leave above
    # _on_prop_hover / _on_prop_leave / _clear_prop_hover replaced by canvas versions above

    def _on_ev_clear_click(self, event: tk.Event) -> None:
        self._ev_clearing = True
        row = self._ev_btn_iid
        if not row:
            return
        self._ev_btn_iid = None
        self._ev_clear_btn.place_forget()
        self._events_set(row, "")
        self._commit_event(row, "")

    def _on_ev_wire_click(self, event: tk.Event) -> None:
        self._ev_clearing = True
        row = self._ev_btn_iid
        if not row:
            return
        if not row.startswith("ev__") and not row.startswith("form_ev__"):
            return
        self._ev_btn_iid = None
        self._ev_wire_btn.place_forget()
        self._auto_wire_event(row)

    def _on_prop_clear_click(self, event: tk.Event) -> None:
        self._prop_clearing = True
        row = self._prop_clear_iid
        if not row:
            return
        self._prop_clear_iid = None
        self._prop_clear_btn.place_forget()
        if row == "anchor__value":
            self._props_set(row, "(none)")
            self._commit_prop(row, "")
            return
        self._props_set(row, "")
        if self._is_color_row(row) or row == "form__bg":
            self._props_set_swatch(row, None)
        self._commit_prop(row, "")

    def _dismiss_editor(self) -> None:
        if self._entry_editor:
            fn = self._pending_commit
            self._pending_commit = None
            if fn:
                try:
                    fn()
                    return  # fn calls _dismiss_editor which finishes cleanup
                except Exception:
                    pass
            try:
                self._entry_editor.destroy()
            except Exception:
                pass
            self._entry_editor = None

    # ── Commit callbacks ──────────────────────────────────────────────────────

    def _commit_prop(self, row_iid: str, raw: str) -> None:
        if row_iid.startswith("form__"):
            key = row_iid[6:]
            if key == "border_style":
                new_max = "True" if raw.lower() == "sizable" else "False"
                self._props_set("form__maximize_box", new_max)
                if self._on_prop_change:
                    self._on_prop_change("__form__", "maximize_box", new_max)
            elif key == "maximize_box":
                new_style = "sizable" if raw.lower() == "true" else "fixed"
                self._props_set("form__border_style", new_style)
                if self._on_prop_change:
                    self._on_prop_change("__form__", "border_style", new_style)
            if self._on_prop_change:
                self._on_prop_change("__form__", key, raw)
            return
        # Multi-select: apply relative delta to all selected widgets
        if self._multi_widgets and row_iid.startswith("geo__"):
            key = row_iid[5:]
            try:
                new_val = int(raw)
                old_val = getattr(self._multi_widgets[0], key)
                delta   = new_val - old_val
                for desc in self._multi_widgets:
                    setattr(desc, key, max(0, getattr(desc, key) + delta))
                if self._on_prop_change:
                    self._on_prop_change("__multi__", key, delta)
            except ValueError:
                pass
            return
        if self._multi_widgets and row_iid.startswith("prop__"):
            key = row_iid[6:]
            for desc in self._multi_widgets:
                desc.props[key] = _parse_value(raw, desc.props.get(key))
            if self._on_prop_change:
                self._on_prop_change("__multi__", key, raw)
            return
        if self._multi_widgets and row_iid == "anchor__value":
            anchor_val = raw if raw != "(none)" else ""
            for desc in self._multi_widgets:
                desc.anchor = anchor_val
            if self._on_prop_change:
                self._on_prop_change("__multi__", "__anchor__", anchor_val)
            return
        if row_iid == "widget__name":
            d = self._current_widget
            if d is None:
                return
            new_name = raw.strip()
            if not new_name or not new_name.isidentifier() or new_name == d.id:
                self._props_set(row_iid, d.id)
                return
            if self._form and any(w.id == new_name for w in self._form.widgets
                                  if w.id != d.id):
                self._props_set(row_iid, d.id)
                self._show_status(f'"{new_name}" is already in use')
                return
            old_id = d.id
            if self._on_prop_change:
                self._on_prop_change(old_id, "__name__", new_name)
            return
        d = self._current_widget
        if d is None:
            return
        if row_iid == "geo__parent":
            return  # read-only — drag to reparent
        if row_iid.startswith("geo__"):
            key = row_iid[5:]
            try:
                setattr(d, key, int(raw))
                if self._on_prop_change:
                    self._on_prop_change(d.id, key, int(raw))
            except ValueError:
                pass
        elif row_iid.startswith("prop__"):
            key = row_iid[6:]
            parsed = _parse_value(raw, d.props.get(key))
            d.props[key] = parsed
            if self._on_prop_change:
                self._on_prop_change(d.id, key, parsed)
            if key == "state":
                reg = REGISTRY.get(d.type, {})
                color_defaults = _STATE_COLOR_DEFAULTS.get(parsed, {})
                for color_key in reg.get("state_color_props", {}).get(parsed, []):
                    if not d.props.get(color_key) and color_key in color_defaults:
                        d.props[color_key] = color_defaults[color_key]
                        if self._on_prop_change:
                            self._on_prop_change(d.id, color_key, color_defaults[color_key])
                self.load_widget(d)
            elif key in ("validatecommand", "invalidcommand"):
                val = str(parsed)
                self._props_set_warn(row_iid, bool(val and not val.startswith("_")))
            elif key == "validate":
                if parsed != "none" and not d.props.get("validatecommand"):
                    auto = f"_{d.id}_validate"
                    d.props["validatecommand"] = auto
                    if self._on_prop_change:
                        self._on_prop_change(d.id, "validatecommand", auto)
                elif parsed == "none":
                    for vk in ("validatecommand", "vcmd_args", "invalidcommand"):
                        if d.props.pop(vk, None) is not None and self._on_prop_change:
                            self._on_prop_change(d.id, vk, "")
                self.load_widget(d)
            elif key == "colorize":
                self.load_widget(d)
            elif key == "scrollbar" and d.type == "Text":
                if parsed in ("Horizontal", "Both") and d.props.get("wrap") != "none":
                    d.props["wrap"] = "none"
                    self._props_set("prop__wrap", "none")
                    if self._on_prop_change:
                        self._on_prop_change(d.id, "wrap", "none")
            elif key in ("char_width", "char_height"):
                try:
                    count = int(str(parsed))
                    if count > 0:
                        if key == "char_width":
                            new_px = max(30, count * _CHAR_PX_W)
                            d.width = new_px
                            if self._props_exists("geo__width"):
                                self._props_set("geo__width", str(new_px))
                            if self._on_prop_change:
                                self._on_prop_change(d.id, "width", new_px)
                        else:
                            new_px = max(20, count * _CHAR_PX_H)
                            d.height = new_px
                            if self._props_exists("geo__height"):
                                self._props_set("geo__height", str(new_px))
                            if self._on_prop_change:
                                self._on_prop_change(d.id, "height", new_px)
                except (ValueError, TypeError):
                    pass
            elif key in ("onvalue", "offvalue") and d.variable is not None:
                inferred = _infer_var_type(str(parsed))
                reg = REGISTRY.get(d.type, {})
                if inferred in reg.get("variable_types", []):
                    d.variable.var_type = inferred
                    if self._props_exists("var__type"):
                        self._props_set("var__type", inferred)
                    if self._on_prop_change:
                        self._on_prop_change(d.id, "__variable__", d.variable)
        elif row_iid == "anchor__value":
            d.anchor = raw if raw != "(none)" else ""
            if self._on_prop_change:
                self._on_prop_change(d.id, "__anchor__", d.anchor)
        elif row_iid == "nb__tab":
            d.tab = raw
            if self._on_prop_change:
                self._on_prop_change(d.id, "__tab__", raw)
        elif row_iid.startswith("var__"):
            self._commit_variable(d, row_iid, raw)

    def _commit_variable(self, d: WidgetDescriptor, row_iid: str, raw: str) -> None:
        reg = REGISTRY.get(d.type, {})
        var_types = reg.get("variable_types", ["StringVar"])
        field = row_iid[5:]  # "name", "type", "initial"

        if field == "name":
            name = raw.strip()
            if not name:
                d.variable = None
            elif name.isidentifier():
                if d.variable is None:
                    d.variable = VariableBinding(name=name,
                                                 var_type=var_types[0],
                                                 initial="")
                else:
                    d.variable.name = name
            else:
                # Restore original
                self._props_set(row_iid, d.variable.name if d.variable else "")
                return
        elif field in ("type", "initial"):
            if d.variable is None:
                default_name = f"{d.id}_var"
                d.variable = VariableBinding(name=default_name,
                                             var_type=var_types[0],
                                             initial="")
                self._props_set("var__name", default_name)
            if field == "type":
                d.variable.var_type = raw.strip()
            else:
                d.variable.initial = raw.strip()

        if self._on_prop_change:
            self._on_prop_change(d.id, "__variable__", d.variable)

    def _commit_event(self, row_iid: str, raw: str) -> None:
        handler = raw.strip()

        if row_iid.startswith("form_ev__"):
            if self._form is None:
                return
            ev_key = row_iid[9:]
            if handler:
                self._form.form_events[ev_key] = handler
            else:
                self._form.form_events.pop(ev_key, None)
            if self._on_event_change:
                self._on_event_change("__form__", ev_key, handler)
            self._events_set_warn(row_iid, bool(handler and not handler.startswith("_")))
            return

        d = self._current_widget
        if d is None or not row_iid.startswith("ev__"):
            return
        event_key = row_iid[4:]
        if handler:
            d.events[event_key] = handler
        else:
            d.events.pop(event_key, None)
        if self._on_event_change:
            self._on_event_change(d.id, event_key, handler)
        self._events_set_warn(row_iid, bool(handler and not handler.startswith("_")))

    def _auto_wire_event(self, row_iid: str) -> None:
        """Click on event name → fill default handler and commit."""
        if row_iid.startswith("form_ev__"):
            if self._form is None:
                return
            ev_key = row_iid[9:]
            if self._form.form_events.get(ev_key):
                return  # already wired
            default = f"_on_{ev_key}"
            self._form.form_events[ev_key] = default
            self._events_set(row_iid, default)
            if self._on_event_change:
                self._on_event_change("__form__", ev_key, default)
            return

        d = self._current_widget
        if d is None or not row_iid.startswith("ev__"):
            return
        event_key = row_iid[4:]
        if d.events.get(event_key):
            return  # already wired
        default = f"_{d.id}_{event_key}"
        d.events[event_key] = default
        self._events_set(row_iid, default)
        if self._on_event_change:
            self._on_event_change(d.id, event_key, default)


# ── Helpers ───────────────────────────────────────────────────────────────────

_ANCHOR_DISPLAY: dict[str, str] = {
    "":             "(none)",
    "top_left":     "↖ top-left",
    "top":          "↑ top",
    "top_right":    "↗ top-right",
    "left":         "← left",
    "all":          "⊡ all",
    "right":        "→ right",
    "bottom_left":  "↙ bot-left",
    "bottom":       "↓ bottom",
    "bottom_right": "↘ bot-right",
}

_ANCHOR_DESC: dict[str, str] = {
    "top_left":     "Pinned top-left — no movement on resize",
    "top":          "Stretches width; top edge fixed",
    "top_right":    "Pinned top-right — follows right edge",
    "left":         "Stretches height; left edge fixed",
    "all":          "Scales position and size proportionally",
    "right":        "Pinned right; stretches height",
    "bottom_left":  "Pinned bottom-left — follows bottom edge",
    "bottom":       "Stretches width; bottom edge fixed",
    "bottom_right": "Pinned bottom-right corner",
}

_PROP_LABELS: dict[str, str] = {
    "bg":               "Background",
    "fg":               "Foreground",
    "insertbackground": "Insert Cursor",
}

_VALIDATE_LABELS: dict[str, str] = {
    "validatecommand": "  --vcmd",
    "vcmd_args":       "  --args",
    "invalidcommand":  "  --ivcmd",
}

_EVENT_DESCRIPTIONS: dict[str, tuple[str, str]] = {
    "command":     ("command=",           "Fired on activation — wired as constructor kwarg, not .bind()"),
    "click":       ("<Button-1>",         "Left mouse button click"),
    "dblclick":    ("<Double-Button-1>",  "Double click"),
    "rightclick":  ("<Button-3>",         "Right mouse button click"),
    "mousedown":   ("<ButtonPress>",      "Any mouse button pressed"),
    "mouseup":     ("<ButtonRelease>",    "Any mouse button released"),
    "mousemove":   ("<Motion>",           "Mouse moved over widget"),
    "mouseenter":  ("<Enter>",            "Mouse entered widget"),
    "mouseleave":  ("<Leave>",            "Mouse left widget"),
    "focusin":     ("<FocusIn>",          "Widget gained focus"),
    "focusout":    ("<FocusOut>",         "Widget lost focus"),
    "keypress":    ("<KeyPress>",         "Key pressed while focused"),
    "keydown":     ("<KeyPress>",         "Key pressed while focused"),
    "keyup":       ("<KeyRelease>",       "Key released while focused"),
    "change":        ("<<Modified>>",           "Content changed"),
    "comboselected": ("<<ComboboxSelected>>",   "Item selected from dropdown"),
    "listselect":    ("<<ListboxSelect>>",      "Item selected from listbox"),
    # Form-level events
    "load":       ("after_idle",          "Fired once when the form is fully built and shown"),
    "activate":   ("<FocusIn>",           "Fired when the form window gains focus (guard skips child focus events)"),
    "deactivate": ("<FocusOut>",          "Fired when the form window loses focus (guard skips child focus events)"),
    "unload":     ("WM_DELETE_WINDOW",    "Fired when the user closes the window — stub calls self.destroy()"),
    "resize":     ("<Configure>",         "Fired when the form is resized (guard skips child resize events)"),
}

_PROP_HINTS: dict[str, str] = {
    # Resize anchor
    "anchor__value":      "How this widget moves/resizes when the form is resized. Hold Shift while resizing the form to ignore all anchors.",
    # Widget identity & geometry
    "name":               "Unique identifier for this control in generated code",
    "x":                  "Horizontal position in pixels from the left edge of the form",
    "y":                  "Vertical position in pixels from the top edge of the form",
    "width":              "Width of the control in pixels",
    "height":             "Height of the control in pixels",
    # Common appearance
    "text":               "Text displayed on the control",
    "bg":                 "Background fill color",
    "fg":                 "Text / foreground color",
    "font":               "Font family, size, and style (click to open font picker)",
    "state":              "Interaction state: normal, disabled, or readonly",
    "relief":             "Border style: flat, sunken, raised, groove, ridge, or solid",
    "borderwidth":        "Border thickness in pixels",
    "justify":            "Text alignment when content spans multiple lines",
    "anchor":             "Alignment of content within the widget bounds: w pins indicator+text to the left edge (recommended for Checkbutton/Radiobutton)",
    "padx":               "Horizontal internal padding in pixels",
    "pady":               "Vertical internal padding in pixels",
    # Entry / Text
    "show":               "Mask character for password fields (e.g. *)",
    "insertbackground":   "Color of the blinking text insertion cursor",
    "selectbackground":   "Background color of selected text",
    "selectforeground":   "Text color of selected text",
    "exportselection":    "Allow selected text/items to be pasted into other widgets via middle-click",
    # Active / state colors
    "activebackground":   "Background color when the control is hovered or pressed",
    "activeforeground":   "Text color when the control is hovered or pressed",
    "disabledforeground": "Text color when the control is disabled",
    "readonlybackground": "Background color when the control is in read-only state",
    # Focus ring
    "highlightbackground": "Focus ring color when the control does not have keyboard focus",
    "highlightcolor":      "Focus ring color when the control has keyboard focus",
    # Spinbox / Scale / OptionMenu
    "from_":              "Minimum allowed value",
    "to":                 "Maximum allowed value",
    "increment":          "Amount to increase or decrease per step click",
    "wrap":               "Whether values wrap around when reaching min or max",
    "values":             "Comma-separated list of selectable options",
    "colorize":           "Alternate-row shading: True applies --alt bg color to every even row via itemconfigure()",
    "colorize_altbg":     "Background color applied to even-numbered rows when colorize is True",
    "orient":             "Layout direction: horizontal or vertical",
    # New additions
    "wraplength":         "Maximum line length in pixels before text wraps to the next line; 0 or empty means no wrapping",
    "selectmode":         "How many list items the user can select at once",
    "resolution":         "Smallest increment the slider snaps to; values are rounded to the nearest multiple",
    "tickinterval":       "Spacing between tick marks drawn along the slider; 0 or empty means no ticks",
    "maximum":            "Maximum value for the progress bar (default 100)",
    "char_width":         "Width of the widget in characters — sizes the content area independently of canvas pixel width",
    "char_height":        "Height of the widget in lines — sizes the content area independently of canvas pixel height",
    "onvalue":            "Value written to the variable when the checkbutton is checked (default 1)",
    "offvalue":           "Value written to the variable when the checkbutton is unchecked (default 0)",
    "labelanchor":        "Position of the label text on the LabelFrame border (compass direction)",
    "disabledbackground": "Background color when the widget is in the disabled state",
    "mode":               "Determinate tracks a known quantity; Indeterminate animates without a fixed end",
    # Validation
    "validate":           "When to run the validation function",
    "validatecommand":    "Method called to validate input — must start with _",
    "vcmd_args":          "Substitution codes passed to validator (%P = new value, %s = current)",
    "invalidcommand":     "Method called when validation fails — must start with _",
    # Form props
    "title":              "Window title shown in the title bar",
    "border_style":       "Window border: sizable (resizable), fixed, or none (no chrome)",
    "maximize_box":       "Whether the maximize / restore button is visible",
    "always_on_top":      "Pin this window above all other windows (wm_attributes -topmost)",
    "menu_bar":           "Click to open the Menu Editor and build a menu bar for this form",
}

_DROPDOWN_ITEM_HINTS: dict[str, dict[str, str]] = {
    "anchor": {
        "w":      "West — indicator + text flush to the left edge (recommended for radio/check)",
        "e":      "East — indicator + text flush to the right edge",
        "n":      "North — content pushed to the top edge",
        "s":      "South — content pushed to the bottom edge",
        "center": "Center — content centered within the widget bounds (tkinter default)",
        "nw":     "North-West — top-left corner",
        "ne":     "North-East — top-right corner",
        "sw":     "South-West — bottom-left corner",
        "se":     "South-East — bottom-right corner",
    },
    "state": {
        "normal":   "Normal — widget is fully interactive",
        "disabled": "Disabled — widget is greyed out and cannot be interacted with",
        "readonly": "Read-only — value is visible but cannot be edited by the user",
    },
    "validate": {
        "none":     "None — no input validation",
        "focus":    "Focus — validate when the widget gains or loses focus",
        "focusin":  "Focus in — validate only when the widget gains focus",
        "focusout": "Focus out — validate only when the widget loses focus",
        "key":      "Key — validate on every keystroke as the user types",
        "all":      "All — validate on every keystroke and every focus change",
    },
    "border_style": {
        "sizable": "Sizable — standard resizable window with all borders",
        "fixed":   "Fixed — window has a border but cannot be resized",
        "none":    "None — no border or title bar (overrideredirect); often used for splash screens",
    },
    "maximize_box": {
        "True":  "True — show the maximize / restore button in the title bar",
        "False": "False — hide the maximize button; window cannot be maximized",
    },
    "type": {
        "StringVar":  "StringVar — holds a string value; use for text, Entry, Label bindings",
        "IntVar":     "IntVar — holds an integer; use for Checkbutton, Radiobutton, Spinbox",
        "DoubleVar":  "DoubleVar — holds a float; use for Scale or any decimal value",
        "BooleanVar": "BooleanVar — holds True / False; use for Checkbutton toggles",
    },
    "colorize": {
        "True":  "True — apply alternate row background color to every even-numbered row",
        "False": "False — no alternate row shading; all rows use the default background",
    },
    "justify": {
        "left":   "Left — align text to the left edge of the widget",
        "center": "Center — center text horizontally within the widget",
        "right":  "Right — align text to the right edge of the widget",
    },
    "relief": {
        "flat":   "Flat — no visible border decoration (default for most widgets)",
        "sunken": "Sunken — border appears pressed inward; gives a recessed look",
        "raised": "Raised — border appears raised outward; gives a raised button look",
        "groove": "Groove — carved groove border; two-tone inset effect",
        "ridge":  "Ridge — raised ridge border; two-tone outset effect",
        "solid":  "Solid — plain solid single-color border",
    },
    "orient": {
        "horizontal": "Horizontal — widget runs left to right",
        "vertical":   "Vertical — widget runs top to bottom",
    },
    "selectmode": {
        "single":   "Single — only one item can be selected; clicking a new item deselects the previous",
        "browse":   "Browse — like single, but selection follows the mouse as it moves (tkinter default)",
        "multiple": "Multiple — any number of items can be selected; clicking toggles individual items",
        "extended": "Extended — range selection with Shift+click and Ctrl+click; most common for file lists",
    },
    "wrap": {
        "True":  "True — values wrap around: stepping past the max returns to the min, and vice versa",
        "False": "False — values stop at the min and max boundaries; no wrap-around",
    },
    "exportselection": {
        "True":  "True — selected text or items are automatically copied to the system clipboard",
        "False": "False — selections stay local to the widget and are not exported to the clipboard",
    },
    "labelanchor": {
        "nw": "nw — top-left corner of the border (tkinter default)",
        "n":  "n  — top center of the border",
        "ne": "ne — top-right corner",
        "en": "en — right side, upper",
        "e":  "e  — right side, center",
        "es": "es — right side, lower",
        "se": "se — bottom-right corner",
        "s":  "s  — bottom center",
        "sw": "sw — bottom-left corner",
        "ws": "ws — left side, lower",
        "w":  "w  — left side, center",
        "wn": "wn — left side, upper",
    },
    "mode": {
        "determinate":   "Determinate — fills from left to right to show measurable progress toward a known goal",
        "indeterminate": "Indeterminate — bounces back and forth to show activity when progress can't be measured",
    },
    "vcmd_args": {
        "%P":                        "%P — the new value the field would have if the edit is accepted",
        "%P, %S":                    "%P = new value  |  %S = the string being inserted or deleted",
        "%d, %P, %S":                "%d = action (1=insert, 0=delete)  |  %P = new value  |  %S = change string",
        "%s, %P, %S":                "%s = current value before edit  |  %P = new value  |  %S = change string",
        "%d, %i, %P, %S":            "%d = action  |  %i = index of change  |  %P = new value  |  %S = change string",
        "%d, %i, %P, %S, %s, %v, %V, %W": "%d action  %i index  %P new value  %S change  %s old value  %v validate mode  %V event  %W widget name",
    },
}

_CHAR_PX_W = 8   # approx px per character (default 9pt font)
_CHAR_PX_H = 20  # approx px per line

_VCMD_ARG_PRESETS: list[str] = [
    "%P",
    "%P, %S",
    "%d, %P, %S",
    "%s, %P, %S",
    "%d, %i, %P, %S",
    "%d, %i, %P, %S, %s, %v, %V, %W",
]

_STATE_COLOR_LABELS: dict[str, str] = {
    "readonlybackground": "  --bg",
    "disabledbackground": "  --bg",
    "disabledforeground": "  --fg",
}

_STATE_COLOR_DEFAULTS: dict[str, dict[str, str]] = {
    "readonly": {
        "readonlybackground": "#F0F0F0",
    },
    "disabled": {
        "disabledbackground": "#F5F5F5",
        "disabledforeground": "#A0A0A0",
    },
}


def _apply_tree_style() -> None:
    s = ttk.Style()
    s.configure("Props.Treeview",
                 background="#1e1e1e", foreground="#cccccc",
                 fieldbackground="#1e1e1e", rowheight=22, borderwidth=0)
    s.configure("Props.Treeview.Heading",
                 background="#252526", foreground="#858585", relief="flat")
    s.map("Props.Treeview",
          background=[("selected", "#094771")],
          foreground=[("selected", "#ffffff")])


def _make_tree(parent: tk.Widget, value_col_name: str = "Value") -> ttk.Treeview:
    tree = ttk.Treeview(
        parent,
        columns=("value",),
        show="tree headings",
        style="Props.Treeview",
        selectmode="browse",
    )
    tree.heading("#0",    text="Property",        anchor="w")
    tree.heading("value", text=value_col_name,    anchor="w")
    tree.column("#0",     width=110, minwidth=80, stretch=True)
    tree.column("value",  width=110, minwidth=80, stretch=True)

    sb = ttk.Scrollbar(parent, orient="vertical", command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    return tree


def _display(val: Any) -> str:
    """Human-readable string for a prop value shown in the tree."""
    if isinstance(val, list):
        return ", ".join(str(v) for v in val) if val else "(empty)"
    return str(val)


def _contrast_color(hex_color: str) -> str:
    """Return black or white for readable text on hex_color."""
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    try:
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return "#000000" if (0.299 * r + 0.587 * g + 0.114 * b) / 255 > 0.5 else "#ffffff"
    except Exception:
        return "#000000"


def _infer_var_type(val: str) -> str:
    """Return the most appropriate tkinter Var type for an on/offvalue string."""
    if val in ("True", "False"):
        return "BooleanVar"
    try:
        int(val)
        return "IntVar"
    except ValueError:
        pass
    try:
        float(val)
        return "DoubleVar"
    except ValueError:
        pass
    return "StringVar"


def _parse_value(raw: str, current: Any) -> Any:
    """Try to parse *raw* into the same type as *current*."""
    if isinstance(current, bool):
        return raw.strip().lower() in ("true", "1", "yes")
    if isinstance(current, int):
        try:
            return int(raw)
        except ValueError:
            return raw
    if isinstance(current, float):
        try:
            return float(raw)
        except ValueError:
            return raw
    if isinstance(current, list):
        return [v.strip() for v in raw.split(",") if v.strip()]
    return raw
