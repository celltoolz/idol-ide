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
_ORD_NB_NUM  = "#4ec9b0"   # teal badge for Notebook-scoped widgets
_ORD_NB_IND  = 16          # indent px for Notebook children
_ORD_HDR_H   = 22          # height of tab-group header rows
_ORD_HDR_BG  = "#1a1a1a"
_ORD_HDR_FG  = "#4ec9b0"
_PROPS_SPLIT = 0.44   # fraction of width for the label column


def _parse_multi_wire_name(option: str) -> str:
    """Convert a multi-wire option string to a display name for the Connected row.

    "Dialog1:destroy (exit)"  → "→ Dialog1 (destroy)"
    "Dialog1:hide (withdraw)" → "→ Dialog1"
    "Dialog1"                 → "→ Dialog1"
    """
    if ":" in option:
        dialog, _, mode = option.partition(":")
        tag = " (destroy)" if mode.startswith("destroy") else ""
        return f"→ {dialog}{tag}"
    return f"→ {option}"


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
        on_prop_change:           Optional[Callable[[str, str, Any],  None]] = None,
        on_event_change:          Optional[Callable[[str, str, str], None]] = None,
        on_select_widget:         Optional[Callable[[str | None],    None]] = None,
        on_navigate_handler:      Optional[Callable[[str],           None]] = None,
        on_reorder_widget:        Optional[Callable[[str, int],      None]] = None,
        on_handler_toggle:        Optional[Callable[[str, bool],     None]] = None,
        on_handler_connect:       Optional[Callable[[str, "str | None"], None]] = None,
        on_handler_disconnect:    Optional[Callable[[str, "Any"],    None]] = None,
        on_handler_edit:          Optional[Callable[[str],           None]] = None,
        on_component_prop_change:    Optional[Callable[[str, str, Any], None]] = None,
        on_component_connect:        Optional[Callable[[str, str],      None]] = None,
        on_component_disconnect:     Optional[Callable[[str, str, str], None]] = None,
        on_component_edit:           Optional[Callable[[str, str, str], None]] = None,
        on_select_component:         Optional[Callable[[str],           None]] = None,
        on_install_pillow:           Optional[Callable[[],              None]] = None,
        on_ci_tags_needed:           Optional[Callable] = None,
        on_canvas_tags_needed:       Optional[Callable] = None,
        on_ci_image_paths_needed:    Optional[Callable[[], list]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg="#252526", **kwargs)
        self._on_prop_change           = on_prop_change
        self._on_event_change          = on_event_change
        self._on_select_widget         = on_select_widget
        self._on_navigate_handler      = on_navigate_handler
        self._on_reorder_widget        = on_reorder_widget
        self._on_handler_toggle        = on_handler_toggle
        self._on_handler_connect       = on_handler_connect
        self._on_handler_disconnect    = on_handler_disconnect
        self._on_handler_edit          = on_handler_edit
        self._on_component_prop_change    = on_component_prop_change
        self._on_component_connect        = on_component_connect
        self._on_component_disconnect     = on_component_disconnect
        self._on_component_edit           = on_component_edit
        self._on_select_component         = on_select_component
        self._on_install_pillow           = on_install_pillow
        self._on_ci_tags_needed           = on_ci_tags_needed
        self._on_canvas_tags_needed       = on_canvas_tags_needed
        self._on_ci_image_paths_needed    = on_ci_image_paths_needed
        self._active_python: str          = __import__("sys").executable
        self._pil_available: "bool | None" = None
        self._project_dir: str            = __import__("os").getcwd()
        self._current_widget: WidgetDescriptor | None  = None
        self._multi_widgets:  list[WidgetDescriptor]    = []
        self._entry_editor:   tk.Widget | None          = None
        self._pending_commit: "Callable[[], None] | None" = None
        self._form:           FormModel | None          = None
        # (display_label, id_or_None, kind)  kind = "form" | "widget" | "component"
        self._selector_items: list[tuple[str, str | None, str]] = []
        self._status_after:   str | None                = None
        self._prop_clearing:  bool                      = False
        self._ev_clearing:    bool                      = False
        self._prop_clear_iid: str | None                = None
        self._ev_btn_iid:     str | None                = None
        # Component mode state
        self._comp_mode:      bool                      = False
        self._comp_id:        str | None                = None
        self._comp_def:       "Any | None"              = None
        self._comp_form:      "Any | None"              = None   # override form for component lookups
        self._comp_hov_idx:   int | None                = None
        self._comp_dtitles_expanded: bool               = False
        # Widgets wired to the selected component's handlers (comp mode)
        # list of (method_name, "{widget_id}.{ev_key}") tuples
        self._comp_connections:    list[tuple[str, str]] = []
        self._comp_conn_hov_idx:   int | None             = None
        # Component handlers wired to the currently-loaded widget/form
        # list of (method_name, label, removable, removal_key|(comp_id,wid,ev)|None)
        self._widget_comp_handlers: list[tuple] = []
        self._widget_comp_hov_idx:  int | None             = None
        # Connectable comp handlers not yet wired — shown in Available Components with ⚡
        self._widget_comp_avail: list[tuple[str, str, str]] = []  # (method, comp_id, handler_id)
        self._widget_comp_avail_hov_idx: int | None = None
        self._handlers_avail_comp_y0: int = 0
        self._avail_comp_expanded: bool = False
        self._avail_comp_hdr_canvas_y: int = -1
        # Handlers tab — Available / Connected split
        self._handlers_avail_defs: list = []          # HandlerDef objects (not wired)
        self._handlers_conn_rows:  list = []          # dicts with conn info
        self._handlers_hov_conn_idx: int | None = None
        self._handlers_avail_y0: int = 0              # canvas Y of first Available row
        self._handlers_conn_y0:  int = 0              # canvas Y of first Connected row
        self._handlers_wch_y0:   int = 0              # canvas Y of first WCH row
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
            w.bind("<Button-1>",   self._open_selector_menu)
            w.bind("<MouseWheel>", self._selector_scroll)

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

        # Floating … edit button for comp_wire rows — mirrors _comp_edit_btn styling
        self._ev_edit_btn = tk.Label(
            self._events_cv, text="…",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=3,
        )
        self._ev_edit_btn.bind("<Enter>",        lambda e: self._ev_edit_btn.config(fg="#cccccc"))
        self._ev_edit_btn.bind("<Leave>",        self._on_ev_btn_leave)
        self._ev_edit_btn.bind("<ButtonRelease-1>", self._on_ev_edit_click)

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

        _hb = tk.Frame(self._handlers_frame, bg=_ORD_BG)
        _hb.pack(fill="both", expand=True)
        self._handlers_sb = VerticalScrollbar(_hb, bg=_ORD_BG)
        self._handlers_sb.pack(side="right", fill="y")
        self._handlers_cv = tk.Canvas(
            _hb, bg=_ORD_BG, highlightthickness=0,
            yscrollcommand=self._handlers_sb.set,
        )
        self._handlers_cv.pack(side="left", fill="both", expand=True)
        self._handlers_sb.configure(command=self._handlers_cv.yview)
        self._handlers_cv.bind("<Configure>",  lambda _: self._handlers_redraw())
        self._handlers_cv.bind("<MouseWheel>",
            lambda e: self._handlers_cv.yview_scroll(-1 * (e.delta // 120), "units"))
        self._handlers_cv.bind("<Motion>",     self._handlers_motion)
        self._handlers_cv.bind("<Leave>",      self._handlers_leave)
        self._handlers_cv.bind("<ButtonRelease-1>", self._handlers_click)
        self._handlers_cv.bind("<Double-Button-1>", self._handlers_dblclick)

        self._handlers_defs:    list = []   # HandlerDef list for current form
        self._handlers_enabled: set[str] = set()
        self._handlers_hov_idx: int | None = None
        self._handlers_dbl_pending: bool = False

        # ── Floating buttons for form-handler rows (Handlers tab) ─────────────
        self._handler_wire_btn = tk.Label(
            self._handlers_cv, text="⚡",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=2,
        )
        self._handler_wire_btn.bind("<Enter>",
            lambda e: self._handler_wire_btn.config(fg="#dfc700"))
        self._handler_wire_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._handler_wire_btn.bind("<ButtonRelease-1>", self._on_handler_wire_click)

        self._handler_edit_btn = tk.Label(
            self._handlers_cv, text="…",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=3,
        )
        self._handler_edit_btn.bind("<Enter>",
            lambda e: self._handler_edit_btn.config(fg="#cccccc"))
        self._handler_edit_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._handler_edit_btn.bind("<ButtonRelease-1>", self._on_handler_edit_click)

        self._handler_disco_btn = tk.Label(
            self._handlers_cv, text="×",
            bg="#3a1a1a", fg="#ff6b6b",
            font=(UI_FONT, 10, "bold"), cursor="hand2", padx=3,
        )
        self._handler_disco_btn.bind("<Enter>",
            lambda e: self._handler_disco_btn.config(bg="#5a1a1a"))
        self._handler_disco_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._handler_disco_btn.bind("<ButtonRelease-1>", self._on_handler_disco_click)

        # ── Floating ⚡ connect button for component handler rows ──────────────
        self._comp_connect_btn = tk.Label(
            self._handlers_cv, text="⚡",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=2,
        )
        self._comp_connect_btn.bind("<Enter>",
            lambda e: self._comp_connect_btn.config(fg="#dfc700"))
        self._comp_connect_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._comp_connect_btn.bind("<ButtonRelease-1>", self._on_comp_connect_click)

        # Floating × disconnect button for Connected Components rows
        self._comp_disconnect_btn = tk.Label(
            self._handlers_cv, text="×",
            bg="#3a1a1a", fg="#ff6b6b",
            font=(UI_FONT, 10, "bold"), cursor="hand2", padx=4,
        )
        self._comp_disconnect_btn.bind("<Enter>",
            lambda e: self._comp_disconnect_btn.config(bg="#5a1a1a"))
        self._comp_disconnect_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._comp_disconnect_btn.bind("<ButtonRelease-1>", self._on_comp_disconnect_click)

        # Floating … edit button for wired Connected Components rows
        self._comp_edit_btn = tk.Label(
            self._handlers_cv, text="…",
            bg="#3a3a3a", fg="#555555",
            font=(UI_FONT, 9), cursor="hand2", padx=3,
        )
        self._comp_edit_btn.bind("<Enter>",
            lambda e: self._comp_edit_btn.config(fg="#cccccc"))
        self._comp_edit_btn.bind("<Leave>", self._on_handler_btn_leave)
        self._comp_edit_btn.bind("<ButtonRelease-1>", self._on_comp_edit_click)

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
        self._order_drag_idx:   int | None = None  # display index of dragged row
        self._order_drag_ghost: int | None = None
        # Display list: ('w', widget, nb_info) | ('h', tab_name)
        self._order_display: list = []
        self._disp_to_w:     dict[int, int] = {}   # display_idx → _order_widgets idx

    # ── Public API ────────────────────────────────────────────────────────────

    def load_widget(self, descriptor: WidgetDescriptor) -> None:
        """Populate the panel from *descriptor*."""
        # Migrate legacy Canvas "border: bool" → highlightthickness/bd int props
        if descriptor.type == "Canvas" and "border" in descriptor.props \
                and "highlightthickness" not in descriptor.props:
            legacy = descriptor.props.pop("border", False)
            no_border = str(legacy).lower() in ("false", "0")
            descriptor.props["highlightthickness"] = 0 if no_border else None
            descriptor.props["bd"] = 0 if no_border else None
        self._exit_comp_mode()
        self._dismiss_editor()
        self._current_widget = descriptor
        self._multi_widgets  = []
        reg = REGISTRY.get(descriptor.type, {})
        self._set_selector(descriptor.id)
        self._populate_props(descriptor, reg)
        if descriptor.props.get("image"):
            self._check_pil_async(
                lambda ok: self._update_pil_warning_row("prop__image", ok)
            )
        self._populate_events(descriptor, reg)
        self._widget_comp_handlers = self._collect_widget_comp_handlers(descriptor)
        self._widget_comp_avail    = self._collect_canvas_img_avail(descriptor)
        if self._form:
            self.load_handlers(self._form)

    def load_form(self, form: FormModel) -> None:
        """Show form-level properties when the canvas background is selected."""
        self._exit_comp_mode()
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
        # Background image row
        import os as _os
        img_disp = _os.path.basename(form.image) if form.image else ""
        self._props_insert("form__image", "image", img_disp)
        # Menu bar row (blue link)
        n = len(form.menu_items)
        menu_val = f"{n} item{'s' if n != 1 else ''}" if n else "(none)"
        self._props_insert("form__menu_bar", "menu bar", menu_val)
        self._props_set_link("form__menu_bar", True)
        self._props_redraw()
        if form.image:
            self._check_pil_async(
                lambda ok: self._update_pil_warning_row("form__image", ok)
            )

        self._events_clear()
        for ev in ("load", "activate", "deactivate", "unload", "resize"):
            handler = form.form_events.get(ev, "")
            self._events_insert(f"form_ev__{ev}", ev, handler)
        self._events_insert("ev__learn_guide", "? Events", "", kind="guide")
        self._events_redraw()

        self.load_handlers(form)
        self.refresh_order(form, None)

    def load_handlers(self, form: FormModel) -> None:
        """Populate the Handlers tab — Available / Connected split (no checkboxes)."""
        from designer.handlers import handlers_for
        from designer.model import HandlerWire
        all_defs = handlers_for(form.form_type)
        self._handlers_defs    = all_defs
        self._handlers_enabled = set(form.enabled_handlers)
        self._handlers_hov_idx       = None
        self._handlers_hov_conn_idx  = None

        wires     = list(getattr(form, "handler_wires",   []))
        h_options = dict(getattr(form, "handler_options", {}))

        # ── Widget-selected mode ───────────────────────────────────────────────
        # Show only connectable handlers compatible with this widget type.
        # Connected = only wires that target this specific widget.
        if self._current_widget is not None:
            widget = self._current_widget
            widget_wired_ids = {
                wire.handler_id for wire in wires
                if wire.widget_id == widget.id
            }
            self._handlers_avail_defs = [
                h for h in all_defs
                if h.connectable
                and (not h.applies_to_widgets or widget.type in h.applies_to_widgets)
                and (h.id not in widget_wired_ids or h.multi_wire)
            ]
            conn_rows: list[dict] = []
            for wire in wires:
                if wire.widget_id != widget.id:
                    continue
                hdef = next((h for h in all_defs if h.id == wire.handler_id), None)
                if hdef:
                    name = (_parse_multi_wire_name(wire.option) if hdef.multi_wire and wire.option
                            else hdef.id)
                    conn_rows.append({
                        "handler_id": hdef.id,
                        "name":       name,
                        "target":     wire.event_key,
                        "removable":  True,
                        "editable":   (bool(hdef.options) and hdef.generates_stub) or bool(hdef.secondary_options),
                        "wire":       wire,
                        "option":     wire.option,
                        "hdef":       hdef,
                    })
            self._handlers_conn_rows = conn_rows
            # Component handlers — show those not yet wired to this specific widget,
            # filtered by applies_to_widgets when the handler has a widget-type restriction.
            widget_methods = set(widget.events.values())
            from designer.component_registry import COMPONENT_REGISTRY as _CR
            self._widget_comp_avail = []
            for _method, _comp_id, _hid in self._collect_form_comp_avail(form):
                if _method in widget_methods:
                    continue
                _comp = form.get_component(_comp_id)
                _cdef = _CR.get(_comp.type) if _comp else None
                _hdef = next((h for h in _cdef.handler_defs if h.id == _hid), None) if _cdef else None
                if _hdef and _hdef.applies_to_widgets and widget.type not in _hdef.applies_to_widgets:
                    continue
                self._widget_comp_avail.append((_method, _comp_id, _hid))
            self._widget_comp_handlers = self._collect_widget_comp_handlers(widget)
            self._handlers_redraw()
            return

        # ── Form-selected mode (show everything) ──────────────────────────────
        enabled_set = set(form.enabled_handlers)
        connected_ids: set[str] = set()
        conn_rows = []

        # Connectable handler IDs that already have wires — shown per-wire below
        wired_connectable_ids = {
            wire.handler_id for wire in wires
            if any(h.connectable and h.id == wire.handler_id for h in all_defs)
        }

        # Built-in wired / always-wired handlers (skip connectable if they have wires)
        for h in all_defs:
            if h.always_wired or h.id in enabled_set:
                connected_ids.add(h.id)
                if h.connectable and h.id in wired_connectable_ids:
                    continue  # shown per-wire in the next loop
                option = h_options.get(h.id, "")
                conn_rows.append({
                    "handler_id": h.id,
                    "name":       h.id,
                    "target":     h.display_target,
                    "removable":  not h.always_wired,
                    "editable":   bool(h.options),
                    "wire":       None,
                    "option":     option,
                    "hdef":       h,
                })

        # Connectable handler wires (one row per HandlerWire)
        for wire in wires:
            hdef = next((h for h in all_defs if h.id == wire.handler_id), None)
            if hdef and hdef.connectable:
                connected_ids.add(hdef.id)
                if wire.widget_id == "__form__":
                    target = f"form.{wire.event_key}"
                elif wire.widget_id:
                    target = f"{wire.widget_id}.{wire.event_key}"
                else:
                    target = wire.event_key
                # multi_wire handlers: show the resolved action as the row name
                name = (_parse_multi_wire_name(wire.option) if hdef.multi_wire and wire.option
                        else hdef.id)
                conn_rows.append({
                    "handler_id": hdef.id,
                    "name":       name,
                    "target":     target,
                    "removable":  True,
                    "editable":   (bool(hdef.options) and hdef.generates_stub) or bool(hdef.secondary_options),
                    "wire":       wire,
                    "option":     wire.option,
                    "hdef":       hdef,
                })

        # multi_wire handlers (e.g. _open_dialog) stay in Available even when wired
        self._handlers_avail_defs = [
            h for h in all_defs
            if h.id not in connected_ids or h.multi_wire
        ]
        self._handlers_conn_rows  = conn_rows

        self._widget_comp_handlers = self._collect_form_comp_handlers(form)
        self._widget_comp_avail    = self._collect_form_comp_avail(form)
        self._handlers_redraw()

    def _collect_widget_comp_handlers(self, descriptor: WidgetDescriptor) -> list[tuple]:
        """Return (method, label, removable, removal_key) for component handlers on descriptor."""
        if self._form is None:
            return []
        from designer.component_registry import COMPONENT_REGISTRY
        comp_method_to_comp: dict[str, str] = {}
        for comp in self._form.components:
            cdef = COMPONENT_REGISTRY.get(comp.type)
            if cdef:
                for hdef in cdef.handler_defs:
                    comp_method_to_comp[f"_{comp.id}{hdef.label}"] = comp.id
        result: list[tuple] = []
        for ev_key, method in descriptor.events.items():
            if method in comp_method_to_comp:
                comp_id = comp_method_to_comp[method]
                result.append((method, f"via {ev_key}", True, (comp_id, descriptor.id, ev_key)))
        # canvas_button connections targeting this Canvas widget
        if descriptor.type == "Canvas":
            for comp in self._form.components:
                if comp.type != "Image":
                    continue
                for btn in (comp.props.get("canvas_buttons") or []):
                    if btn.get("canvas_id") != descriptor.id:
                        continue
                    tag = btn.get("tag", "?")
                    result.append((
                        f"_{tag}_click",
                        f"{comp.id}  ·  {tag}",
                        True,
                        (comp.id, "__canvas_btn__", tag),
                    ))
        return result

    def _collect_canvas_img_avail(self, descriptor: "WidgetDescriptor") -> list[tuple]:
        """Return (method, comp_id, handler_id) for Image comps available for canvas_button on a Canvas widget."""
        if descriptor.type != "Canvas" or self._form is None:
            return []
        result = []
        for comp in self._form.components:
            if comp.type != "Image":
                continue
            if not comp.props.get("paths"):
                continue
            result.append((f"{comp.id}  canvas button", comp.id, "canvas_button"))
        return result

    def _collect_comp_connections(self, comp_id: str) -> list[tuple[str, str, bool, "tuple[str,str] | None"]]:
        """Return (method, label, removable, removal_key) for every connection to this component.

        Non-connector handlers (e.g. _tick) are always shown as wired to Form.init (not removable).
        Wired widget events are removable via the × button.
        """
        if self._form is None or self._comp_def is None:
            return []
        form_name = self._form.name
        result: list[tuple[str, str, bool, "tuple[str,str] | None"]] = []

        # Implicit connections (non-connectable callbacks like _tick, _on_file_selected)
        # only show as connected once at least one connectable sibling is wired,
        # or the Timer is auto-enabled.
        comp_obj = self._form.get_component(comp_id)
        timer_auto = (comp_obj is not None
                      and comp_obj.type == "Timer"
                      and comp_obj.props.get("enabled", True))
        connectable = self._comp_connectable_handlers()
        any_wired = any(
            any(f"_{comp_id}{hdef.label}" in w.events.values() for w in self._form.widgets)
            for hdef in connectable
        )
        mode = str(comp_obj.props.get("socket_type", "")) if comp_obj and comp_obj.type == "Socket" else ""
        for hdef in self._comp_def.handler_defs:
            if hdef.applies_to_modes and mode not in hdef.applies_to_modes:
                continue
            if not hdef.has_connector and (any_wired or timer_auto):
                result.append((f"_{comp_id}{hdef.label}", f"{form_name}.init", False, None))

        # canvas_button entries (stored in comp.props, not widget.events)
        comp_obj2 = self._form.get_component(comp_id)
        if comp_obj2 and comp_obj2.type == "Image":
            for btn in (comp_obj2.props.get("canvas_buttons") or []):
                tag = btn.get("tag", "?")
                canvas_id = btn.get("canvas_id", "?")
                result.append((
                    f"_{tag}_click",
                    f"{canvas_id}  ·  {tag}",
                    True,
                    ("__canvas_btn__", tag),
                ))

        # Explicit widget.events connections
        comp_methods: set[str] = {f"_{comp_id}{hdef.label}" for hdef in self._comp_def.handler_defs}
        for widget in self._form.widgets:
            for ev_key, method in widget.events.items():
                if method in comp_methods:
                    result.append((method, f"{widget.id}.{ev_key}", True, (widget.id, ev_key)))
        # Menu item command connections
        for mi in self._form.menu_items:
            if mi.command_handler in comp_methods:
                result.append((
                    mi.command_handler,
                    f"{mi.name}.command",
                    True,
                    (f"__mi__{mi.name}", "command"),
                ))
        return result

    # ── CommonDialog per-handler title helpers ────────────────────────────────

    _CD_HANDLER_TITLE_KEYS: "list[tuple[str, str]]" = [
        ("show_open",      "show_open_title"),
        ("show_save",      "show_save_title"),
        ("choose_dir",     "choose_dir_title"),
        ("ask_open_file",  "ask_open_file_title"),
        ("ask_save_file",  "ask_save_file_title"),
        ("choose_color",   "choose_color_title"),
        ("ask_input",      "ask_input_title"),
        ("messagebox",     "messagebox_title"),
    ]

    def _insert_dialog_titles_section(self, descriptor) -> None:
        """Add the collapsible Dialog Titles section for a CommonDialog component."""
        if self._form is None or self._comp_def is None:
            return
        # Build map: method_name → "widget_id.event_key" for wired events
        method_to_conn: dict[str, str] = {}
        for w in self._form.widgets:
            for ev_key, ev_method in w.events.items():
                method_to_conn[ev_method] = f"{w.id}.{ev_key}"
        # Collect rows: connectable handlers that are wired (title may be empty)
        qualifying: list[tuple[str, str, str]] = []
        for handler_id, prop_key in self._CD_HANDLER_TITLE_KEYS:
            hdef = next((h for h in self._comp_def.handler_defs if h.id == handler_id), None)
            if hdef is None or not hdef.has_connector:
                continue
            method    = f"_{descriptor.id}{hdef.label}"
            if method not in method_to_conn:
                continue
            title_val = str(descriptor.props.get(prop_key, ""))
            qualifying.append((handler_id, prop_key, title_val))
        if not qualifying:
            return
        arrow   = "▼" if self._comp_dtitles_expanded else "▶"
        set_titles = [t for _, _, t in qualifying if t]
        summary = ", ".join(set_titles[:3]) + ("..." if len(set_titles) > 3 else "")
        self._props_insert("comp__dtitle__header", f"{arrow} Dialog Title",
                           summary or "(none set)")
        self._props_set_link("comp__dtitle__header", True)
        if self._comp_dtitles_expanded:
            for handler_id, prop_key, title_val in qualifying:
                self._props_insert(
                    f"comp__dtitle__{prop_key}",
                    f"  {handler_id}",
                    title_val,
                )

    def _dtitle_conn_hint(self, prop_key: str) -> str:
        """Return 'Connected to widget.event' hint for a Dialog Title sub-row."""
        if self._form is None or self._comp_def is None or self._comp_id is None:
            return ""
        handler_id = next(
            (hid for hid, pk in self._CD_HANDLER_TITLE_KEYS if pk == prop_key), None
        )
        if handler_id is None:
            return ""
        hdef = next((h for h in self._comp_def.handler_defs if h.id == handler_id), None)
        if hdef is None:
            return ""
        method = f"_{self._comp_id}{hdef.label}"
        for w in self._form.widgets:
            for ev_key, ev_method in w.events.items():
                if ev_method == method:
                    return f"Connected to {w.id}.{ev_key}"
        return ""

    def _form_image_hint(self) -> str:
        """Dynamic hint for the form__image property row."""
        if not self._form or not self._form.image:
            return "Background Image  (click to pick a file)"
        import os
        basename = os.path.basename(self._form.image)
        resolved = os.path.join(self._project_dir, self._form.image)
        try:
            from PIL import Image
            with Image.open(resolved) as img:
                w, h = img.size
            return f"Background Image\n{basename}  Width: {w}  Height: {h}"
        except Exception:
            pass
        try:
            photo = tk.PhotoImage(file=resolved)
            w, h = photo.width(), photo.height()
            del photo
            return f"Background Image\n{basename}  Width: {w}  Height: {h}"
        except Exception:
            return f"Background Image\n{basename}"

    def _insert_comp_prop_rows(self, descriptor, comp_def) -> None:
        """Insert prop rows, skipping Socket mode-specific props that don't apply."""
        mode = str(descriptor.props.get("socket_type", "")) if descriptor.type == "Socket" else ""
        for pd in comp_def.prop_defs:
            if descriptor.type == "Socket":
                if pd.key in self._SOCKET_SERVER_ONLY and mode != "server":
                    continue
                if pd.key in self._SOCKET_CLIENT_ONLY and mode != "client":
                    continue
            val = descriptor.props.get(pd.key, pd.default)
            if pd.kind == "image_list":
                paths = val if isinstance(val, list) else []
                n = len(paths)
                display = f"{n} image{'s' if n != 1 else ''}" if n else "(none)"
            else:
                display = str(val)
            self._props_insert(f"comp__{pd.key}", pd.label, display,
                               kind="readonly" if pd.kind == "readonly" else "normal")

    def _rebuild_comp_props(self, descriptor) -> None:
        """Rebuild just the Properties tab rows for the selected component."""
        if self._comp_def is None:
            return
        self._props_clear()
        self._props_insert("comp____name__", "name", descriptor.id)
        self._insert_comp_prop_rows(descriptor, self._comp_def)
        if descriptor.type == "CommonDialog":
            self._insert_dialog_titles_section(descriptor)
        self._props_redraw()

    def _collect_form_comp_handlers(self, form: FormModel) -> list[tuple]:
        """Return (method, label, removable, removal_key) for all component handlers on the form.

        Auto-wired handlers (has_connector=False) are not removable.
        Handlers wired to a widget event or menu item command are removable.
        removal_key is (comp_id, widget_id, ev_key) for widget events and
        (comp_id, "__mi__"+item_name, "command") for menu item commands.
        """
        from designer.component_registry import COMPONENT_REGISTRY
        # Build map: method_name → (comp_id, target_id, ev_key)
        wired: dict[str, tuple] = {}
        all_comp_methods: dict[str, str] = {}  # method → comp_id
        for comp in form.components:
            cdef = COMPONENT_REGISTRY.get(comp.type)
            if cdef:
                for hdef in cdef.handler_defs:
                    all_comp_methods[f"_{comp.id}{hdef.label}"] = comp.id
        for widget in form.widgets:
            for ev_key, method in widget.events.items():
                if method in all_comp_methods:
                    wired[method] = (all_comp_methods[method], widget.id, ev_key)
        # Also scan menu items for component handler commands
        for mi in form.menu_items:
            if mi.command_handler and mi.command_handler in all_comp_methods:
                method = mi.command_handler
                wired[method] = (all_comp_methods[method], f"__mi__{mi.name}", "command")

        result: list[tuple] = []
        for comp in form.components:
            cdef = COMPONENT_REGISTRY.get(comp.type)
            if cdef:
                any_conn_wired = any(
                    f"_{comp.id}{h.label}" in wired
                    for h in cdef.handler_defs if h.has_connector
                )
                timer_auto = (comp.type == "Timer" and comp.props.get("enabled", True))
                # Protected (non-connectable) callbacks first
                for hdef in cdef.handler_defs:
                    if hdef.has_connector:
                        continue
                    if any_conn_wired or timer_auto:
                        method = f"_{comp.id}{hdef.label}"
                        result.append((method, comp.id, False, None))
                # Wired connectable handlers after
                for hdef in cdef.handler_defs:
                    if not hdef.has_connector:
                        continue
                    method = f"_{comp.id}{hdef.label}"
                    if method in wired:
                        _, target_id, ev_key = wired[method]
                        label = (f"{target_id[6:]}.command"  # strip __mi__ prefix for display
                                 if target_id.startswith("__mi__")
                                 else f"{target_id}.{ev_key}")
                        result.append((method, label, True, wired[method]))
        return result

    def _collect_form_comp_avail(self, form: FormModel) -> list[tuple[str, str, str]]:
        """Return (method, comp_id, handler_id) for all connectable component handlers."""
        from designer.component_registry import COMPONENT_REGISTRY
        result: list[tuple[str, str, str]] = []
        for comp in form.components:
            cdef = COMPONENT_REGISTRY.get(comp.type)
            if cdef:
                for hdef in cdef.handler_defs:
                    if hdef.has_connector:
                        result.append((f"_{comp.id}{hdef.label}", comp.id, hdef.id))
        return result

    def load_component(self, descriptor, comp_def, form=None) -> None:
        """Switch the panel into component mode and show the component's properties/handlers."""
        self._exit_comp_mode()
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._comp_mode  = True
        self._comp_id    = descriptor.id
        self._comp_def   = comp_def
        # Allow caller to override which form is used for component lookups (e.g. CI mode)
        self._comp_form  = form
        self._comp_hov_idx = None
        self._set_selector(descriptor.id)

        # Populate Properties tab with PropDef rows
        self._props_clear()
        self._props_insert("comp____name__", "name", descriptor.id)
        self._insert_comp_prop_rows(descriptor, comp_def)
        if descriptor.type == "CommonDialog":
            self._insert_dialog_titles_section(descriptor)
        self._props_redraw()

        # Events tab: show wired widget/menu event connections for this component
        self._refresh_comp_events()

        # Draw component handlers + connected-widget section in the Handlers tab
        self._handlers_defs     = []
        self._handlers_enabled  = set()
        self._comp_connections  = self._collect_comp_connections(descriptor.id)
        self._comp_conn_hov_idx = None
        self._handlers_redraw()

    def _refresh_comp_events(self) -> None:
        """Rebuild the Events tab for the active component from current widget wires."""
        _form = self._comp_form or self._form
        if not self._comp_mode or not self._comp_id or not _form or not self._comp_def:
            return
        self._events_clear()
        _cid = self._comp_id
        _methods = {f"_{_cid}{hd.label}" for hd in self._comp_def.handler_defs}
        for _w in _form.widgets:
            for _ev, _meth in _w.events.items():
                if _meth in _methods:
                    self._events_insert(
                        f"comp_wire__{_w.id}__{_ev}", _ev, _meth,
                        kind="comp_wire", conn_widget=_w.id)
        for _mi in _form.menu_items:
            if _mi.command_handler in _methods:
                self._events_insert(
                    f"comp_wire__mi__{_mi.name}", "command", _mi.command_handler,
                    kind="comp_wire", conn_widget=f"__mi__{_mi.name}")
        self._events_redraw()

    def refresh_comp_connections(self) -> None:
        """Re-collect and redraw after a component wire is added or removed."""
        if self._comp_mode and self._comp_id:
            self._comp_connections = self._collect_comp_connections(self._comp_id)
            self._handlers_redraw()
            self._refresh_comp_events()
            # Refresh props so Dialog Titles section picks up new wires/titles
            comp_obj = self._form.get_component(self._comp_id) if self._form else None
            if comp_obj and self._comp_def:
                self._rebuild_comp_props(comp_obj)
        elif self._current_widget is not None and self._form is not None:
            self.load_handlers(self._form)
            reg = REGISTRY.get(self._current_widget.type, {})
            self._populate_events(self._current_widget, reg)
        elif self._form is not None:
            self.load_handlers(self._form)

    def _exit_comp_mode(self) -> None:
        if not self._comp_mode:
            return
        self._comp_connect_btn.place_forget()
        self._comp_disconnect_btn.place_forget()
        self._comp_edit_btn.place_forget()
        self._comp_mode              = False
        self._comp_id                = None
        self._comp_def               = None
        self._comp_form              = None
        self._comp_hov_idx           = None
        self._comp_connections       = []
        self._comp_conn_hov_idx      = None
        self._comp_dtitles_expanded  = False

    # ── Socket-aware handler helpers ──────────────────────────────────────────

    _SOCKET_SERVER_ONLY = {"max_clients", "bind_address"}
    _SOCKET_CLIENT_ONLY = {"retry_on_fail", "retry_interval"}

    def _socket_mode(self) -> str:
        """Return 'server', 'client', or '' for the currently selected Socket component."""
        if not self._comp_mode or not self._form or not self._comp_id:
            return ""
        comp = self._form.get_component(self._comp_id)
        if comp and comp.type == "Socket":
            return str(comp.props.get("socket_type", ""))
        return ""

    def _comp_connectable_handlers(self) -> list:
        """Connectable handler defs for the active component, filtered by socket mode."""
        if not self._comp_def:
            return []
        mode = self._socket_mode()
        return [
            h for h in self._comp_def.handler_defs
            if h.has_connector
            and (not h.applies_to_modes or mode in h.applies_to_modes)
        ]

    def load_multi(self, descriptors: list[WidgetDescriptor]) -> None:
        """Show shared properties panel for a multi-widget selection."""
        self._exit_comp_mode()
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
        self._exit_comp_mode()
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
        fkind = "TopLevel" if form.form_type == "dialog" else "Form"
        self._selector_items = [(f"{form.name}  ({fkind})", None, "form")]
        for w in form.widgets:
            self._selector_items.append((f"{w.id}  ({w.type})", w.id, "widget"))
        for comp in form.components:
            self._selector_items.append((f"{comp.id}  ({comp.type})", comp.id, "component"))

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
                       kind: str = "event", conn_widget: str = "") -> None:
        """kind: 'event' | 'guide' | 'comp_wire'"""
        row: dict = {"iid": iid, "label": label, "value": value,
                     "kind": kind, "warn": False, "conn_widget": conn_widget}
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
            elif self._events_rows[idx].get("kind") == "comp_wire":
                cw = self._events_rows[idx].get("conn_widget", "")
                label = (f"menu: {cw[6:]}" if cw.startswith("__mi__") else cw)
                self._show_hint(f"connected to: {label}  ···  click to edit wire" if label else "connected component")
            else:
                self._clear_hint()
        else:
            self._ev_clear_btn.place_forget()
            self._ev_edit_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._clear_hint()

    def _update_event_btns(self, idx: int) -> None:
        iid = self._events_rows[idx]["iid"]
        if iid == "ev__learn_guide":
            self._ev_clear_btn.place_forget()
            self._ev_edit_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._ev_btn_iid = None
            return
        bbox = self._events_bbox(iid)
        if not bbox:
            self._ev_clear_btn.place_forget()
            self._ev_edit_btn.place_forget()
            self._ev_wire_btn.place_forget()
            self._ev_btn_iid = None
            return
        x, y, w, h = bbox
        bw  = 18
        val = self._events_rows[idx]["value"].strip()
        if val:
            self._ev_wire_btn.place_forget()
            if self._events_rows[idx].get("kind") == "comp_wire":
                self._ev_clear_btn.place_forget()
                self._ev_edit_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._ev_edit_btn.lift()
            else:
                self._ev_edit_btn.place_forget()
                self._ev_clear_btn.config(text="×")
                self._ev_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._ev_clear_btn.lift()
            self._ev_btn_iid = iid
        else:
            self._ev_clear_btn.place_forget()
            self._ev_edit_btn.place_forget()
            can_wire = (
                (iid.startswith("ev__")      and self._current_widget is not None) or
                (iid.startswith("form_ev__") and self._form is not None)
            )
            entry_active = (
                self._entry_editor is not None
                and self._entry_editor.winfo_exists()
                and self._entry_editor.master is self._events_cv
            )
            if can_wire and not entry_active:
                self._ev_wire_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._ev_wire_btn.lift()
                self._ev_btn_iid = iid
            else:
                self._ev_wire_btn.place_forget()
                self._ev_btn_iid = None

    def _on_event_canvas_leave(self, event: tk.Event) -> None:
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest in (self._ev_clear_btn, self._ev_edit_btn, self._ev_wire_btn):
            return
        if self._events_hov_idx is not None:
            old = self._events_hov_idx
            self._events_hov_idx = None
            self._events_redraw_row(old)
        self._ev_clear_btn.place_forget()
        self._ev_edit_btn.place_forget()
        self._ev_wire_btn.place_forget()
        self._clear_hint()

    def _on_ev_btn_leave(self, event: tk.Event) -> None:
        # Always reset colors immediately (mirrors _on_handler_btn_leave pattern)
        self._ev_clear_btn.config(text="×", fg="#888888")
        self._ev_edit_btn.config(fg="#555555")
        self._ev_wire_btn.config(fg="#555555")
        dest = self.winfo_containing(event.x_root, event.y_root)
        if dest is self._events_cv:
            return
        self._ev_clear_btn.place_forget()
        self._ev_edit_btn.place_forget()
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
        # Canvas .delete("all") removes drawn items but NOT placed Label widgets.
        # Reset all floating buttons so stale placements don't linger between redraws.
        self._handler_wire_btn.place_forget()
        self._handler_edit_btn.place_forget()
        self._handler_disco_btn.place_forget()
        self._comp_connect_btn.place_forget()
        self._comp_disconnect_btn.place_forget()
        self._comp_edit_btn.place_forget()
        w = max(cv.winfo_width(), 160)

        if self._comp_mode and self._comp_def is not None:
            self._comp_handlers_redraw(cv, w)
            return

        if not self._handlers_defs:
            msg = ("No handlers available for this form type"
                   if self._form else "Select the form to manage handlers")
            cv.create_text(w // 2, 24, text=msg,
                           fill=_ORD_DIM, font=(UI_FONT, 8), anchor="center")
            cv.configure(scrollregion=(0, 0, w, 40))
            return

        scroll_top = int(cv.canvasy(0))
        y = 0
        avail = self._handlers_avail_defs
        conn  = self._handlers_conn_rows

        # ── Available section ─────────────────────────────────────────────────
        if avail:
            cv.create_rectangle(0, y, w, y + _ORD_HDR_H, fill=_ORD_HDR_BG, outline="")
            cv.create_text(8, y + _ORD_HDR_H // 2, text="Available",
                           fill=_ORD_DIM, font=(UI_FONT, 7, "bold"), anchor="w")
            y += _ORD_HDR_H

        self._handlers_avail_y0 = y
        for i, h in enumerate(avail):
            y0  = y + i * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            is_hov = i == self._handlers_hov_idx

            bg = _ORD_HOV if is_hov else (_ORD_EVEN if i % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")
            cv.create_text(8, mid, text=h.id,
                           fill=_ORD_FG, font=("Consolas", 9), anchor="w")
            if self._current_widget is not None:
                badge = self._current_widget.type
            elif h.applies_to == ("dialog",):
                badge = "dialog"
            else:
                badge = "all forms"
            badge_x = w - 6 if not is_hov else w - 26
            cv.create_text(badge_x, mid, text=badge,
                           fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e")

            if is_hov:
                self._handler_wire_btn.place(x=w - 2, y=y0 - scroll_top + 2,
                                             anchor="ne", height=_ORD_ROW_H - 4)
                self._handler_wire_btn._handler_id = h.id  # type: ignore[attr-defined]

        y += len(avail) * _ORD_ROW_H

        # ── Connected section ─────────────────────────────────────────────────
        if conn:
            if avail:
                cv.create_line(0, y, w, y, fill="#3a3a3a")
                y += 1
            cv.create_rectangle(0, y, w, y + _ORD_HDR_H, fill=_ORD_HDR_BG, outline="")
            cv.create_text(8, y + _ORD_HDR_H // 2, text="Connected",
                           fill=_ORD_HDR_FG, font=(UI_FONT, 7, "bold"), anchor="w")
            y += _ORD_HDR_H

        self._handlers_conn_y0 = y
        for j, row in enumerate(conn):
            y0  = y + j * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            is_hov = j == self._handlers_hov_conn_idx

            bg = _ORD_HOV if is_hov else (_ORD_EVEN if j % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")
            cv.create_text(8, mid, text=row["name"],
                           fill=_ORD_NB_NUM, font=("Consolas", 9), anchor="w")

            if row["target"]:
                # shift target left to make room for buttons on hover
                btn_reserve = 0
                if is_hov and row["removable"]:
                    btn_reserve += 20
                if is_hov and row["editable"]:
                    btn_reserve += 20
                target_x = w - 6 - btn_reserve
                cv.create_text(target_x, mid, text=row["target"],
                               fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e")

            if is_hov:
                btn_x = w - 2
                btn_h = _ORD_ROW_H - 4
                if row["removable"]:
                    self._handler_disco_btn.place(x=btn_x, y=y0 - scroll_top + 2,
                                                  anchor="ne", height=btn_h)
                    self._handler_disco_btn._conn_row = row  # type: ignore[attr-defined]
                    btn_x -= 20
                if row["editable"]:
                    self._handler_edit_btn.place(x=btn_x, y=y0 - scroll_top + 2,
                                                 anchor="ne", height=btn_h)
                    self._handler_edit_btn._conn_row = row  # type: ignore[attr-defined]

        y += len(conn) * _ORD_ROW_H

        # ── Connected Components section (widget-level comp wires) ────────────
        avail_comps = self._widget_comp_avail
        wch = self._widget_comp_handlers
        if avail_comps or wch:
            cv.create_line(0, y, w, y, fill="#3a3a3a")
            y += 1

        # Available Components sub-section (foldable; collapsed by default)
        if avail_comps:
            arrow = "▼" if self._avail_comp_expanded else "▶"
            cv.create_rectangle(0, y, w, y + _ORD_HDR_H, fill=_ORD_HDR_BG, outline="")
            cv.create_text(8, y + _ORD_HDR_H // 2,
                           text=f"{arrow} Available Components",
                           fill=_ORD_DIM, font=(UI_FONT, 7, "bold"), anchor="w")
            self._avail_comp_hdr_canvas_y = y
            y += _ORD_HDR_H
            self._handlers_avail_comp_y0 = y
            if self._avail_comp_expanded:
                for j, (method, comp_id, handler_id) in enumerate(avail_comps):
                    y0  = y + j * _ORD_ROW_H
                    y1  = y0 + _ORD_ROW_H
                    mid = (y0 + y1) // 2
                    is_hov = j == self._widget_comp_avail_hov_idx
                    bg  = _ORD_HOV if is_hov else (_ORD_EVEN if j % 2 == 0 else _ORD_ODD)
                    cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")
                    cv.create_text(8, mid, text=method,
                                   fill=_ORD_FG, font=("Consolas", 9), anchor="w")
                    badge_x = w - 6 if not is_hov else w - 26
                    cv.create_text(badge_x, mid, text=comp_id,
                                   fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e")
                    if is_hov:
                        self._comp_connect_btn.place(x=w - 2, y=y0 - scroll_top + 2,
                                                     anchor="ne", height=_ORD_ROW_H - 4)
                        self._comp_connect_btn._handler_id    = handler_id   # type: ignore[attr-defined]
                        self._comp_connect_btn._comp_id_override = comp_id   # type: ignore[attr-defined]
                y += len(avail_comps) * _ORD_ROW_H
        else:
            self._avail_comp_hdr_canvas_y = -1
            self._handlers_avail_comp_y0 = y

        if wch:
            if avail_comps:
                cv.create_line(0, y, w, y, fill="#3a3a3a")
                y += 1
            cv.create_rectangle(0, y, w, y + _ORD_HDR_H, fill=_ORD_HDR_BG, outline="")
            cv.create_text(8, y + _ORD_HDR_H // 2, text="⚡ Connected Components",
                           fill=_ORD_HDR_FG, font=(UI_FONT, 7, "bold"), anchor="w")
            y += _ORD_HDR_H
            self._handlers_wch_y0 = y
            for j, row_tup in enumerate(wch):
                method, label, removable, removal_key = row_tup
                y0  = y + j * _ORD_ROW_H
                y1  = y0 + _ORD_ROW_H
                mid = (y0 + y1) // 2
                is_hov = j == self._widget_comp_hov_idx
                bg = _ORD_HOV if is_hov else (_ORD_EVEN if j % 2 == 0 else _ORD_ODD)
                cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")
                cv.create_text(8, mid, text=method,
                               fill=_ORD_NB_NUM, font=("Consolas", 9), anchor="w")
                btn_reserve = (40 if removable else 0) if is_hov else 0
                label_x = w - 6 - btn_reserve
                cv.create_text(label_x, mid, text=label,
                               fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e")
                if removable and is_hov:
                    btn_x = w - 2
                    btn_h = _ORD_ROW_H - 4
                    self._comp_disconnect_btn.place(x=btn_x, y=y0 - scroll_top + 2,
                                                    anchor="ne", height=btn_h)
                    self._comp_disconnect_btn._wch_removal = removal_key  # type: ignore[attr-defined]
                    self._comp_edit_btn.place(x=btn_x - 20, y=y0 - scroll_top + 2,
                                              anchor="ne", height=btn_h)
                    self._comp_edit_btn._wch_removal = removal_key  # type: ignore[attr-defined]
            y += len(wch) * _ORD_ROW_H
        else:
            self._handlers_wch_y0 = y

        cv.configure(scrollregion=(0, 0, w, max(y, 40)))

    def _comp_handlers_redraw(self, cv: tk.Canvas, w: int) -> None:
        scroll_top = int(cv.canvasy(0))
        # Only connectable handlers appear in the top section; always-wired ones
        # (has_connector=False) are shown exclusively in Connected Components below.
        handler_defs = self._comp_connectable_handlers()
        for i, hd in enumerate(handler_defs):
            y0  = i * _ORD_ROW_H
            y1  = y0 + _ORD_ROW_H
            mid = (y0 + y1) // 2
            is_hov = i == self._comp_hov_idx

            bg = _ORD_HOV if is_hov else (_ORD_EVEN if i % 2 == 0 else _ORD_ODD)
            cv.create_rectangle(0, y0, w, y1, fill=bg, outline="", tags=f"chr{i}")

            method = f"_{self._comp_id}{hd.label}"
            cv.create_text(8, mid, text=method,
                           fill=_ORD_FG, font=("Consolas", 9), anchor="w", tags=f"chr{i}")

            if hd.has_connector and is_hov:
                btn_x = w - 4
                btn_h = _ORD_ROW_H - 4
                self._comp_connect_btn.place(x=btn_x, y=y0 - scroll_top + 2, anchor="ne", height=btn_h)
                self._comp_connect_btn._handler_id = hd.id  # type: ignore[attr-defined]

        total_rows = len(handler_defs)
        cc = self._comp_connections
        if cc:
            sep_y = total_rows * _ORD_ROW_H
            cv.create_line(0, sep_y, w, sep_y, fill="#3a3a3a")
            hdr_y = sep_y + 1
            cv.create_rectangle(0, hdr_y, w, hdr_y + _ORD_HDR_H, fill=_ORD_HDR_BG, outline="")
            cv.create_text(8, hdr_y + _ORD_HDR_H // 2, text="⚡ Connected Components",
                           fill=_ORD_HDR_FG, font=(UI_FONT, 7, "bold"), anchor="w")
            for j, (method, label, removable, removal_key) in enumerate(cc):
                row_start = hdr_y + _ORD_HDR_H
                y0  = row_start + j * _ORD_ROW_H
                y1  = y0 + _ORD_ROW_H
                mid = (y0 + y1) // 2
                is_hov = j == self._comp_conn_hov_idx
                bg = _ORD_HOV if is_hov else (_ORD_EVEN if j % 2 == 0 else _ORD_ODD)
                cv.create_rectangle(0, y0, w, y1, fill=bg, outline="")
                cv.create_text(8, mid, text=method,
                               fill=_ORD_NB_NUM, font=("Consolas", 9), anchor="w")
                btn_reserve = (40 if removable else 0) if is_hov else 0
                label_x = w - 6 - btn_reserve
                cv.create_text(label_x, mid, text=label,
                               fill=_ORD_DIM, font=(UI_FONT, 7), anchor="e")
                if removable and is_hov:
                    btn_x = w - 2
                    btn_h = _ORD_ROW_H - 4
                    self._comp_disconnect_btn.place(x=btn_x, y=y0 - scroll_top + 2,
                                                    anchor="ne", height=btn_h)
                    self._comp_disconnect_btn._removal_key = removal_key  # type: ignore[attr-defined]
                    self._comp_edit_btn.place(x=btn_x - 20, y=y0 - scroll_top + 2,
                                              anchor="ne", height=btn_h)
                    self._comp_edit_btn._removal_key = removal_key  # type: ignore[attr-defined]
            total_px = hdr_y + _ORD_HDR_H + len(cc) * _ORD_ROW_H
        else:
            total_px = total_rows * _ORD_ROW_H
        cv.configure(scrollregion=(0, 0, w, total_px))

    def _comp_connection_at(self, y: int) -> int | None:
        """Return index into _comp_connections for y in the Connected Components section, or None."""
        if not self._comp_mode or not self._comp_connections or not self._comp_def:
            return None
        n_connectable = len(self._comp_connectable_handlers())
        section_start = n_connectable * _ORD_ROW_H + 1 + _ORD_HDR_H
        if y < section_start:
            return None
        idx = (y - section_start) // _ORD_ROW_H
        return idx if 0 <= idx < len(self._comp_connections) else None

    def _handlers_idx_at(self, y: int) -> int | None:
        """Available-section row index at canvas y, or None."""
        if self._comp_mode and self._comp_def:
            i = int(y) // _ORD_ROW_H
            n = len(self._comp_connectable_handlers())
            return i if 0 <= i < n else None
        y0 = self._handlers_avail_y0
        if y < y0:
            return None
        i = (y - y0) // _ORD_ROW_H
        return i if 0 <= i < len(self._handlers_avail_defs) else None

    def _handlers_conn_idx_at(self, y: int) -> int | None:
        """Connected-section row index at canvas y, or None."""
        if self._comp_mode or not self._handlers_conn_rows:
            return None
        y0 = self._handlers_conn_y0
        if y < y0:
            return None
        i = (y - y0) // _ORD_ROW_H
        return i if 0 <= i < len(self._handlers_conn_rows) else None

    def _avail_comp_idx_at(self, y: int) -> int | None:
        """Row index in the Available Components section, or None."""
        if self._comp_mode or not self._widget_comp_avail or not self._avail_comp_expanded:
            return None
        y0 = self._handlers_avail_comp_y0
        if y < y0:
            return None
        i = (y - y0) // _ORD_ROW_H
        return i if 0 <= i < len(self._widget_comp_avail) else None

    def _widget_comp_handler_at(self, y: int) -> int | None:
        """Return index into _widget_comp_handlers for the Connected Components section, or None."""
        if not self._widget_comp_handlers or self._comp_mode:
            return None
        y0 = self._handlers_wch_y0
        if y < y0:
            return None
        idx = (y - y0) // _ORD_ROW_H
        return idx if 0 <= idx < len(self._widget_comp_handlers) else None

    def _handlers_motion(self, event: tk.Event) -> None:
        cy = int(self._handlers_cv.canvasy(event.y))
        if self._comp_mode:
            idx      = self._handlers_idx_at(cy)
            conn_idx = self._comp_connection_at(cy)
            if idx != self._comp_hov_idx or conn_idx != self._comp_conn_hov_idx:
                self._comp_hov_idx      = idx
                self._comp_conn_hov_idx = conn_idx
                self._comp_connect_btn.place_forget()
                self._comp_disconnect_btn.place_forget()
                self._handlers_redraw()
                if idx is not None and self._comp_def:
                    self._show_hint(self._comp_def.handler_defs[idx].description)
                elif conn_idx is not None:
                    method, label, removable, _ = self._comp_connections[conn_idx]
                    suffix = " — double-click to jump" if not removable else " — double-click to jump · … to edit · × to disconnect"
                    self._show_hint(f"{method}  ({label}){suffix}")
                else:
                    self._clear_hint()
            return

        avail_idx      = self._handlers_idx_at(cy)
        conn_idx       = self._handlers_conn_idx_at(cy)
        avail_comp_idx = self._avail_comp_idx_at(cy)
        comp_idx       = self._widget_comp_handler_at(cy)

        if (avail_idx      == self._handlers_hov_idx
                and conn_idx       == self._handlers_hov_conn_idx
                and avail_comp_idx == self._widget_comp_avail_hov_idx
                and comp_idx       == self._widget_comp_hov_idx):
            return

        self._handlers_hov_idx          = avail_idx
        self._handlers_hov_conn_idx     = conn_idx
        self._widget_comp_avail_hov_idx = avail_comp_idx
        self._widget_comp_hov_idx       = comp_idx
        self._handler_wire_btn.place_forget()
        self._handler_edit_btn.place_forget()
        self._handler_disco_btn.place_forget()
        self._comp_connect_btn.place_forget()
        self._handlers_redraw()

        if avail_idx is not None:
            self._show_hint(self._handlers_avail_defs[avail_idx].description)
        elif conn_idx is not None:
            row = self._handlers_conn_rows[conn_idx]
            parts = [f"{row['name']}  ({row['target']})", "double-click to jump"]
            if row["removable"]:
                parts.append("× to disconnect")
            if row["editable"]:
                parts.append("… to edit options")
            self._show_hint("  ·  ".join(parts[:1]) + " — " + " · ".join(parts[1:]))
        elif avail_comp_idx is not None:
            method, comp_id, _ = self._widget_comp_avail[avail_comp_idx]
            self._show_hint(f"{method}  ({comp_id}) — ⚡ to connect")
        elif comp_idx is not None:
            method, label, removable, _ = self._widget_comp_handlers[comp_idx]
            suffix = " — double-click to jump · … to edit · × to disconnect" if removable else " — double-click to jump"
            self._show_hint(f"{method}  ({label}){suffix}")
        else:
            self._clear_hint()

    def _handlers_leave(self, _event: tk.Event) -> None:
        if self._comp_mode:
            changed = self._comp_hov_idx is not None or self._comp_conn_hov_idx is not None
            self._comp_hov_idx      = None
            self._comp_conn_hov_idx = None
            if changed:
                self._comp_connect_btn.place_forget()
                self._comp_disconnect_btn.place_forget()
                self._handlers_redraw()
            self._clear_hint()
            return
        changed = (self._handlers_hov_idx          is not None
                   or self._handlers_hov_conn_idx     is not None
                   or self._widget_comp_avail_hov_idx is not None
                   or self._widget_comp_hov_idx       is not None)
        self._handlers_hov_idx          = None
        self._handlers_hov_conn_idx     = None
        self._widget_comp_avail_hov_idx = None
        self._widget_comp_hov_idx       = None
        if changed:
            self._handler_wire_btn.place_forget()
            self._handler_edit_btn.place_forget()
            self._handler_disco_btn.place_forget()
            self._comp_connect_btn.place_forget()
            self._comp_disconnect_btn.place_forget()
            self._comp_edit_btn.place_forget()
            self._handlers_redraw()
        self._clear_hint()

    def _on_handler_btn_leave(self, event: tk.Event) -> None:
        """Leave handler for floating action buttons.

        Resets the button color immediately, then checks pointer position
        synchronously: by the time <Leave> fires the pointer is already at
        the new position, so no deferral is needed. If the pointer is still
        inside the canvas bounds the canvas <Motion> event will re-place the
        button correctly; if the pointer left the canvas entirely we call the
        full leave handler to clean everything up.
        """
        btn = event.widget
        if btn in (self._handler_wire_btn, self._handler_edit_btn,
                   self._comp_connect_btn, self._comp_edit_btn):
            btn.config(fg="#555555")
        elif btn in (self._handler_disco_btn, self._comp_disconnect_btn):
            btn.config(bg="#3a1a1a")

        cv = self._handlers_cv
        rx, ry = cv.winfo_rootx(), cv.winfo_rooty()
        px, py = cv.winfo_pointerxy()
        if not (rx <= px < rx + cv.winfo_width() and ry <= py < ry + cv.winfo_height()):
            self._handlers_leave(event)

    def _handlers_click(self, event: tk.Event) -> None:
        if self._comp_mode:
            return  # ⚡ / × buttons handle actions; plain click does nothing
        if self._handlers_dbl_pending:
            self._handlers_dbl_pending = False
            return
        cy = int(self._handlers_cv.canvasy(event.y))
        if (self._avail_comp_hdr_canvas_y >= 0
                and self._avail_comp_hdr_canvas_y <= cy < self._avail_comp_hdr_canvas_y + _ORD_HDR_H):
            self._avail_comp_expanded = not self._avail_comp_expanded
            self._widget_comp_avail_hov_idx = None
            self._handlers_redraw()

    def _handlers_dblclick(self, event: tk.Event) -> None:
        cy = int(self._handlers_cv.canvasy(event.y))
        if self._comp_mode:
            conn_idx = self._comp_connection_at(cy)
            if conn_idx is not None:
                method, _label, _removable, _key = self._comp_connections[conn_idx]
                if self._on_navigate_handler:
                    self._on_navigate_handler(method)
            return
        self._handlers_dbl_pending = True

        # Connected section double-click → jump to code
        conn_idx = self._handlers_conn_idx_at(cy)
        if conn_idx is not None:
            row = self._handlers_conn_rows[conn_idx]
            if self._on_navigate_handler:
                self._on_navigate_handler(row["handler_id"])
            return

        # Connected Components (widget-level comp wires) → jump
        comp_idx = self._widget_comp_handler_at(cy)
        if comp_idx is not None:
            method, *_ = self._widget_comp_handlers[comp_idx]
            if self._on_navigate_handler:
                self._on_navigate_handler(method)
            return

        # Available section double-click → quick-connect (same as ⚡)
        avail_idx = self._handlers_idx_at(cy)
        if avail_idx is not None:
            h = self._handlers_avail_defs[avail_idx]
            if self._on_handler_connect:
                self._on_handler_connect(h.id)

    def _on_comp_connect_click(self, _event: tk.Event) -> None:
        hid = getattr(self._comp_connect_btn, "_handler_id", None)
        # In comp mode use panel state; in form/widget view use button override set by avail-comp row
        cid = (self._comp_id if self._comp_mode
               else getattr(self._comp_connect_btn, "_comp_id_override", None))
        if hid and cid and self._on_component_connect:
            self._on_component_connect(cid, hid)

    def _on_comp_disconnect_click(self, _event: tk.Event) -> None:
        if self._comp_mode:
            # Component selected: (widget_id, ev_key) stored, comp_id from mode state
            key = getattr(self._comp_disconnect_btn, "_removal_key", None)
            if key and self._comp_id and self._on_component_disconnect:
                widget_id, ev_key = key
                self._on_component_disconnect(self._comp_id, widget_id, ev_key)
        else:
            # Form/widget selected: full (comp_id, widget_id, ev_key) stored
            key = getattr(self._comp_disconnect_btn, "_wch_removal", None)
            if key and self._on_component_disconnect:
                comp_id, widget_id, ev_key = key
                self._on_component_disconnect(comp_id, widget_id, ev_key)

    def _on_comp_edit_click(self, _event: tk.Event) -> None:
        if self._comp_mode:
            key = getattr(self._comp_edit_btn, "_removal_key", None)
            if key and self._comp_id and self._on_component_edit:
                widget_id, ev_key = key
                self._on_component_edit(self._comp_id, widget_id, ev_key)
        else:
            key = getattr(self._comp_edit_btn, "_wch_removal", None)
            if key and self._on_component_edit:
                comp_id, widget_id, ev_key = key
                self._on_component_edit(comp_id, widget_id, ev_key)

    def _on_handler_wire_click(self, _event: tk.Event) -> None:
        hid = getattr(self._handler_wire_btn, "_handler_id", None)
        if hid and self._on_handler_connect:
            preselect = self._current_widget.id if self._current_widget else None
            self._on_handler_connect(hid, preselect)

    def _on_handler_edit_click(self, _event: tk.Event) -> None:
        row = getattr(self._handler_edit_btn, "_conn_row", None)
        if row and self._on_handler_edit:
            self._on_handler_edit(row["handler_id"], row.get("wire"))

    def _on_handler_disco_click(self, _event: tk.Event) -> None:
        row = getattr(self._handler_disco_btn, "_conn_row", None)
        if row and self._on_handler_disconnect:
            self._on_handler_disconnect(row["handler_id"], row.get("wire"))

    # ── Props canvas data helpers ─────────────────────────────────────────────

    def _props_clear(self) -> None:
        self._props_rows.clear()
        self._props_row_map.clear()
        self._props_hov_idx = None

    def _props_insert(self, iid: str, label: str, value: str,
                      kind: str = "normal", orig: "str | None" = None) -> None:
        """kind: 'header' | 'normal' | 'readonly'"""
        row: dict = {"iid": iid, "label": label, "value": value, "kind": kind,
                     "swatch": None, "warn": False, "link": False, "orig": orig}
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

    # ── Image / PIL helpers ───────────────────────────────────────────────────

    def set_active_python(self, exe: str) -> None:
        self._active_python = exe
        self._pil_available = None

    def set_project_dir(self, path: str) -> None:
        self._project_dir = path

    def _check_pil_async(self, on_result: "Callable[[bool], None]") -> None:
        if self._pil_available is not None:
            on_result(self._pil_available)
            return
        import threading, subprocess
        def _run():
            try:
                r = subprocess.run(
                    [self._active_python, "-c", "import PIL"],
                    capture_output=True, timeout=10
                )
                ok = (r.returncode == 0)
            except Exception:
                ok = False
            self._pil_available = ok
            self.after(0, lambda: on_result(ok))
        threading.Thread(target=_run, daemon=True).start()

    def _open_image_picker(self, row_iid: str) -> None:
        import os, shutil
        from tkinter.filedialog import askopenfilename
        d = self._current_widget
        if d is None:
            return
        picked = askopenfilename(
            title="Select image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ]
        )
        if not picked:
            return
        # Copy into <project>/images/ so the generated app is self-contained
        images_dir = os.path.join(self._project_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        basename = os.path.basename(picked)
        dest = os.path.join(images_dir, basename)
        # Avoid clobbering an existing file that is different from the source
        if os.path.exists(dest):
            try:
                same = os.path.samefile(picked, dest)
            except OSError:
                same = False
            if not same:
                name, ext = os.path.splitext(basename)
                counter = 1
                while os.path.exists(dest):
                    dest = os.path.join(images_dir, f"{name}_{counter}{ext}")
                    counter += 1
        if not os.path.exists(dest):
            shutil.copy2(picked, dest)
        # Store as forward-slash relative path so codegen is cross-platform
        rel = os.path.relpath(dest, self._project_dir).replace("\\", "/")
        d.props["image"] = rel
        self._props_set(row_iid, os.path.basename(rel))
        if self._on_prop_change:
            self._on_prop_change(d.id, "image", rel)
        self._check_pil_async(lambda ok: self._update_pil_warning_row(row_iid, ok))

    def _open_comp_image_picker(self, row_iid: str) -> None:
        import os, shutil
        from tkinter.filedialog import askopenfilenames
        lookup_form = self._comp_form or self._form
        if not lookup_form or not self._comp_id:
            return
        comp = lookup_form.get_component(self._comp_id)
        if comp is None:
            return
        picked = askopenfilenames(
            title="Select image(s)",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ]
        )
        if not picked:
            return
        images_dir = os.path.join(self._project_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        existing = list(comp.props.get("paths", []))
        rel_paths = list(existing)  # start with existing images
        for src in picked:
            basename = os.path.basename(src)
            dest = os.path.join(images_dir, basename)
            if os.path.exists(dest):
                try:
                    same = os.path.samefile(src, dest)
                except OSError:
                    same = False
                if not same:
                    name, ext = os.path.splitext(basename)
                    counter = 1
                    while os.path.exists(dest):
                        dest = os.path.join(images_dir, f"{name}_{counter}{ext}")
                        counter += 1
            if not os.path.exists(dest):
                shutil.copy2(src, dest)
            rel = os.path.relpath(dest, self._project_dir).replace("\\", "/")
            if rel not in rel_paths:
                rel_paths.append(rel)
        comp.props["paths"] = rel_paths
        n = len(rel_paths)
        display = f"{n} image{'s' if n != 1 else ''}"
        self._props_set(row_iid, display)
        if self._on_component_prop_change:
            self._on_component_prop_change(self._comp_id, "paths", rel_paths)

    def _open_form_image_picker(self, row_iid: str) -> None:
        import os, shutil
        from tkinter.filedialog import askopenfilename
        if self._form is None:
            return
        picked = askopenfilename(
            title="Select background image",
            filetypes=[
                ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.webp"),
                ("All files", "*.*"),
            ]
        )
        if not picked:
            return
        images_dir = os.path.join(self._project_dir, "images")
        os.makedirs(images_dir, exist_ok=True)
        basename = os.path.basename(picked)
        dest = os.path.join(images_dir, basename)
        if os.path.exists(dest):
            try:
                same = os.path.samefile(picked, dest)
            except OSError:
                same = False
            if not same:
                name, ext = os.path.splitext(basename)
                counter = 1
                while os.path.exists(dest):
                    dest = os.path.join(images_dir, f"{name}_{counter}{ext}")
                    counter += 1
        if not os.path.exists(dest):
            shutil.copy2(picked, dest)
        rel = os.path.relpath(dest, self._project_dir).replace("\\", "/")
        self._props_set(row_iid, os.path.basename(rel))
        if self._on_prop_change:
            self._on_prop_change("__form__", "image", rel)
        self._check_pil_async(lambda ok: self._update_pil_warning_row(row_iid, ok))

    def _update_pil_warning_row(self, image_row_iid: str, pil_ok: bool) -> None:
        if pil_ok:
            idx = self._props_row_map.get("pil__warning")
            if idx is not None:
                self._props_rows.pop(idx)
                del self._props_row_map["pil__warning"]
                for i in range(idx, len(self._props_rows)):
                    self._props_row_map[self._props_rows[i]["iid"]] = i
                self._props_redraw()
        else:
            if "pil__warning" in self._props_row_map:
                return
            img_idx = self._props_row_map.get(image_row_iid)
            if img_idx is None:
                return
            warn_row = {
                "iid": "pil__warning", "label": "PIL",
                "value": "⚠ click to install Pillow",
                "kind": "warn_link", "swatch": None, "warn": False, "link": False,
            }
            insert_at = img_idx + 1
            self._props_rows.insert(insert_at, warn_row)
            for i in range(insert_at, len(self._props_rows)):
                self._props_row_map[self._props_rows[i]["iid"]] = i
            self._props_redraw()

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
                elif row["kind"] == "warn_link":
                    cv.create_text(split_x + 8, mid, text=val,
                                   fill="#ff9f43", font=(UI_FONT, 9),
                                   anchor="w", tags=f"pr{i}")
                elif row["warn"]:
                    cv.create_text(split_x + 8, mid, text=val,
                                   fill="#ff6b6b", font=(UI_FONT, 9),
                                   anchor="w", tags=f"pr{i}")
                else:
                    _vtid = cv.create_text(split_x + 8, mid, text=val,
                                           fill=_ORD_FG, font=(UI_FONT, 9),
                                           anchor="w", tags=f"pr{i}")
                    if row.get("orig"):
                        _tb = cv.bbox(_vtid)
                        if _tb:
                            cv.create_text(_tb[2] + 10, mid,
                                           text=f"(original: {row['orig']})",
                                           fill="#e8a838", font=(UI_FONT, 8),
                                           anchor="w", tags=f"pr{i}")

    def _props_redraw_row(self, idx: int) -> None:
        """Redraw a single row in-place (no full delete)."""
        if not self._props_rows or idx >= len(self._props_rows):
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
            elif row["kind"] == "warn_link":
                cv.create_text(split_x + 8, mid, text=val,
                               fill="#ff9f43", font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{idx}")
            elif row["warn"]:
                cv.create_text(split_x + 8, mid, text=val,
                               fill="#ff6b6b", font=(UI_FONT, 9),
                               anchor="w", tags=f"pr{idx}")
            else:
                _vtid = cv.create_text(split_x + 8, mid, text=val,
                                       fill=_ORD_FG, font=(UI_FONT, 9),
                                       anchor="w", tags=f"pr{idx}")
                if row.get("orig"):
                    _tb = cv.bbox(_vtid)
                    if _tb:
                        cv.create_text(_tb[2] + 10, mid,
                                       text=f"(original: {row['orig']})",
                                       fill="#e8a838", font=(UI_FONT, 8),
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

        # Pre-index Notebook children by nb_id → tab_name → [(w_idx, widget)]
        nb_children: dict[str, dict[str, list]] = {}
        nb_child_indices: set[int] = set()
        for w_idx, widget in enumerate(self._order_widgets):
            if widget.parent_id and self._form:
                par = self._form.get_widget(widget.parent_id)
                if par and REGISTRY.get(par.type, {}).get("is_notebook"):
                    nb_child_indices.add(w_idx)
                    tab = widget.tab or ""
                    nb_children.setdefault(par.id, {}).setdefault(tab, []).append(
                        (w_idx, widget)
                    )

        # Build display list: ('w', widget, nb_info) | ('h', tab_name)
        display: list = []
        disp_to_w: dict[int, int] = {}
        emitted_nb: set[str] = set()
        for w_idx, widget in enumerate(self._order_widgets):
            if w_idx in nb_child_indices:
                continue  # emitted as part of its Notebook's block

            d_idx = len(display)
            display.append(('w', widget, None))
            disp_to_w[d_idx] = w_idx

            if REGISTRY.get(widget.type, {}).get("is_notebook") and widget.id not in emitted_nb:
                emitted_nb.add(widget.id)
                tabs = widget.props.get("tabs", [])
                children_by_tab = nb_children.get(widget.id, {})
                for tab_name in tabs:
                    children = children_by_tab.get(tab_name, [])
                    if not children:
                        continue
                    display.append(('h', tab_name))
                    for i, (cw_idx, cwidget) in enumerate(children, 1):
                        cd_idx = len(display)
                        display.append(('w', cwidget, (i, tab_name)))
                        disp_to_w[cd_idx] = cw_idx

        self._order_display = display
        self._disp_to_w = disp_to_w

        total_h = sum(_ORD_HDR_H if d[0] == 'h' else _ORD_ROW_H for d in display)
        cv.configure(scrollregion=(0, 0, w, total_h))
        y = 0
        for d_idx, item in enumerate(display):
            if item[0] == 'h':
                self._order_draw_header(item[1], y, w)
                y += _ORD_HDR_H
            else:
                self._order_draw_row(item[1], d_idx, y, w, item[2])
                y += _ORD_ROW_H


    def _order_draw_header(self, tab_name: str, y: int, w: int) -> None:
        cv = self._order_cv
        cv.create_rectangle(0, y, w, y + _ORD_HDR_H - 1,
                            fill=_ORD_HDR_BG, outline="")
        cv.create_rectangle(0, y, 3, y + _ORD_HDR_H - 1,
                            fill=_ORD_HDR_FG, outline="")
        cv.create_text(_ORD_NB_IND + 6, y + _ORD_HDR_H // 2,
                       text=tab_name, fill=_ORD_HDR_FG,
                       font=(UI_FONT, 8), anchor="w")

    def _order_draw_row(self, widget: WidgetDescriptor, d_idx: int, y: int, w: int,
                        nb_info: tuple[int, str] | None = None) -> None:
        cv  = self._order_cv
        bg  = self._order_row_color(d_idx)
        tag = f"orow{d_idx}"

        is_nb_child = nb_info is not None
        indent = _ORD_NB_IND if is_nb_child else 0

        rect = cv.create_rectangle(0, y, w, y + _ORD_ROW_H - 1,
                                   fill=bg, outline="", tags=tag)
        self._order_bgs[d_idx] = rect

        if is_nb_child:
            cv.create_rectangle(0, y, 3, y + _ORD_ROW_H - 1,
                                fill=_ORD_NB_NUM, outline="", tags=tag)

        r = 9
        bx = indent + r + 4
        by = y + _ORD_ROW_H // 2
        w_idx      = self._disp_to_w.get(d_idx, 0)
        badge_num  = nb_info[0] if is_nb_child else (w_idx + 1)
        badge_fill = _ORD_NB_NUM if is_nb_child else _ORD_NUM
        badge_fg   = "#1e1e1e" if is_nb_child else "#ffffff"
        cv.create_oval(bx - r, by - r, bx + r, by + r,
                       fill=badge_fill, outline="", tags=tag)
        cv.create_text(bx, by, text=str(badge_num), fill=badge_fg,
                       font=(UI_FONT, 7, "bold"), anchor="center", tags=tag)

        cv.create_text(bx + r + 6, by, text=widget.id,
                       fill=_ORD_FG, font=("Consolas", 9),
                       anchor="w", tags=tag)

        cv.create_text(w - 8, by, text=widget.type,
                       fill=_ORD_DIM, font=(UI_FONT, 8),
                       anchor="e", tags=tag)

        cv.tag_bind(tag, "<Enter>", lambda e, i=d_idx: self._order_hover_on(i))
        cv.tag_bind(tag, "<Leave>", lambda e, i=d_idx: self._order_hover_off(i))

    def _order_row_color(self, d_idx: int) -> str:
        w_idx = self._disp_to_w.get(d_idx)
        if w_idx is not None and w_idx < len(self._order_widgets):
            if self._order_widgets[w_idx].id == self._order_sel_id:
                return _ORD_SEL
        return _ORD_EVEN if d_idx % 2 == 0 else _ORD_ODD

    def _order_hover_on(self, d_idx: int) -> None:
        if d_idx in self._order_bgs and self._order_drag_idx is None:
            w_idx = self._disp_to_w.get(d_idx)
            wid = self._order_widgets[w_idx].id if w_idx is not None else None
            if wid != self._order_sel_id:
                self._order_cv.itemconfigure(self._order_bgs[d_idx], fill=_ORD_HOV)

    def _order_hover_off(self, d_idx: int) -> None:
        if d_idx in self._order_bgs:
            self._order_cv.itemconfigure(self._order_bgs[d_idx],
                                         fill=self._order_row_color(d_idx))

    def _order_y_to_disp(self, canvas_y: int) -> int:
        """Return display index for a canvas y coordinate, accounting for header rows."""
        cy = int(self._order_cv.canvasy(canvas_y))
        y = 0
        for i, item in enumerate(self._order_display):
            h = _ORD_HDR_H if item[0] == 'h' else _ORD_ROW_H
            if cy < y + h:
                return i
            y += h
        return len(self._order_display)

    def _order_press(self, event) -> None:
        d_idx = self._order_y_to_disp(event.y)
        if d_idx not in self._disp_to_w:
            return  # header row — not selectable/draggable
        self._order_drag_idx = d_idx
        w_idx = self._disp_to_w[d_idx]
        if w_idx < len(self._order_widgets) and self._on_select_widget:
            self._on_select_widget(self._order_widgets[w_idx].id)

    def _order_motion(self, event) -> None:
        if self._order_drag_idx is None:
            return
        cv = self._order_cv
        target  = self._order_drop_target(event.y)
        ghost_y = self._disp_idx_to_y(target)
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

        src_d = src
        if src_d not in self._disp_to_w:
            return
        src_w = self._disp_to_w[src_d]
        dragged_widget = self._order_widgets[src_w]

        target_d = self._order_drop_target(event.y)

        # If dragged widget is a Notebook child, check if drop lands in a different tab section
        if dragged_widget.parent_id and self._form:
            par = self._form.get_widget(dragged_widget.parent_id)
            if par and REGISTRY.get(par.type, {}).get("is_notebook"):
                target_tab = self._nearest_nb_tab(target_d)
                if target_tab is not None and target_tab != dragged_widget.tab and self._on_prop_change:
                    dragged_widget.tab = target_tab
                    self._on_prop_change(dragged_widget.id, "__tab__", target_tab)
                    return

        # Count widget rows before target_d to get insertion widget index
        dst_w = sum(1 for i in range(target_d) if i in self._disp_to_w)
        if target_d > src_d:
            dst_w -= 1
        dst_w = max(0, min(dst_w, len(self._order_widgets) - 1))

        if dst_w != src_w and self._on_reorder_widget and self._order_widgets:
            self._on_reorder_widget(self._order_widgets[src_w].id, dst_w)

    def _nearest_nb_tab(self, d_idx: int) -> str | None:
        """Return the tab name of the section that insertion point d_idx falls into.

        d_idx is an insertion point ("insert before item N"), so walk backwards
        from d_idx-1 to find the enclosing tab header, not the header AT d_idx.
        """
        top = min(d_idx - 1, len(self._order_display) - 1)
        for i in range(top, -1, -1):
            if self._order_display[i][0] == 'h':
                return self._order_display[i][1]
        return None

    def _order_drop_target(self, canvas_y: int) -> int:
        """Return display insertion index (0..N) from a canvas y coordinate."""
        cy = int(self._order_cv.canvasy(canvas_y))
        y = 0
        for i, item in enumerate(self._order_display):
            h = _ORD_HDR_H if item[0] == 'h' else _ORD_ROW_H
            mid = y + h // 2
            if cy <= mid:
                return i
            y += h
        return len(self._order_display)

    def _disp_idx_to_y(self, d_idx: int) -> int:
        """Return the canvas y coordinate for display index d_idx."""
        y = 0
        for i, item in enumerate(self._order_display):
            if i == d_idx:
                return y
            y += _ORD_HDR_H if item[0] == 'h' else _ORD_ROW_H
        return y

    def _set_selector(self, widget_id: str | None) -> None:
        """Update the selector label to reflect the currently selected item."""
        for label, wid, _kind in self._selector_items:
            if wid == widget_id:
                self._selector_label.config(text=label)
                return
        # Fallback: show generic text if selector not yet populated
        if widget_id is None:
            self._selector_label.config(text="Form")
        else:
            self._selector_label.config(text=widget_id)

    def _selector_scroll(self, event: tk.Event) -> None:
        """Mouse-wheel navigation through the selector items."""
        if not self._selector_items:
            return
        # Determine current index
        if self._comp_mode and self._comp_id:
            current_wid = self._comp_id
        elif self._current_widget:
            current_wid = self._current_widget.id
        else:
            current_wid = None  # form selected
        cur_idx = next(
            (i for i, (_, wid, _) in enumerate(self._selector_items) if wid == current_wid),
            0,
        )
        delta = -1 if event.delta > 0 else 1
        new_idx = max(0, min(len(self._selector_items) - 1, cur_idx + delta))
        if new_idx == cur_idx:
            return
        _, wid, kind = self._selector_items[new_idx]
        if kind == "component":
            if self._on_select_component:
                self._on_select_component(wid)
        else:
            if self._on_select_widget:
                self._on_select_widget(wid)

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
        last_kind: str = ""
        for label, wid, kind in self._selector_items:
            if kind == "component" and last_kind != "component":
                menu.add_separator()
            if kind == "component":
                def _cmd(w=wid):
                    if self._on_select_component:
                        self._on_select_component(w)
            else:
                def _cmd(w=wid):
                    if self._on_select_widget:
                        self._on_select_widget(w)
            menu.add_command(label=label, command=_cmd, font=(UI_FONT, 9))
            last_kind = kind
        try:
            rx = self._selector_label.winfo_rootx()
            ry = self._selector_label.winfo_rooty() + self._selector_label.winfo_height()
            menu.tk_popup(rx, ry)
        finally:
            menu.grab_release()

    def show_hint(self, message: str, duration_ms: int = 3000) -> None:
        """Public: briefly show an informational message in the status bar."""
        self._show_status(message, duration_ms)

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

    def _order_hint_text(self) -> str:
        return "Drag rows to reorder  ·  Tab key visits widgets in this order"

    def _clear_hint(self) -> None:
        if self._status_after is None:
            if self._nb.select() == str(self._order_frame):
                self._show_hint(self._order_hint_text())
            elif self._nb.select() == str(self._handlers_frame):
                self._show_hint("Click a row to enable or disable the handler")
            else:
                self._status_label.config(text="")

    def _on_tab_changed(self, _event=None) -> None:
        if self._nb.select() == str(self._order_frame):
            self._show_hint(self._order_hint_text())
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
            val = str(getattr(d, key))
            orig = None
            if d.type == "Canvas" and key == "width":
                _cw = d.props.get("_ci_orig_w")
                if _cw is not None and _cw != d.width:
                    orig = str(_cw)
            elif d.type == "Canvas" and key == "height":
                _ch = d.props.get("_ci_orig_h")
                if _ch is not None and _ch != d.height:
                    orig = str(_ch)
            self._props_insert(f"geo__{key}", key, val, orig=orig)
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
            if key in ("_ci_orig_w", "_ci_orig_h"):
                continue
            if key == "_ci_tags":
                tags = d.props.get("_ci_tags", [])
                display_val = ", ".join(tags) if tags else "(click to add tags)"
                self._props_insert("prop___ci_tags", "tags", display_val)
                continue
            if key == "_canvas_tags":
                tags = d.props.get("_canvas_tags", [])
                display_val = f"{len(tags)} tag{'s' if len(tags) != 1 else ''}" if tags else "(click to manage)"
                self._props_insert("prop___canvas_tags", "tags", display_val)
                continue
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

        # Build canvas_button event map so generated methods show inline in
        # their matching event rows rather than as separate rows at the bottom.
        cb_event_map: dict[str, list[str]] = {}
        if d.type == "Canvas" and self._form:
            for comp in self._form.components:
                if comp.type != "Image":
                    continue
                for btn in (comp.props.get("canvas_buttons") or []):
                    if btn.get("canvas_id") != d.id:
                        continue
                    tag = btn.get("tag", "")
                    if not tag:
                        continue
                    pairs = [("mousedown", f"_{tag}_down"), ("mouseup", f"_{tag}_up")]
                    if btn.get("hover_key"):
                        pairs += [("mouseenter", f"_{tag}_enter"),
                                  ("mouseleave", f"_{tag}_leave")]
                    for ev_name, method in pairs:
                        cb_event_map.setdefault(ev_name, []).append(method)

        for ev in reg.get("events", []):
            iid = f"ev__{ev}"
            cb_methods = cb_event_map.get(ev)
            if cb_methods:
                # Show canvas_button generated method in the existing row, readonly
                display = cb_methods[0]
                if len(cb_methods) > 1:
                    display += f" +{len(cb_methods) - 1}"
                self._events_insert(iid, ev, display, kind="readonly")
            else:
                handler = d.events.get(ev, "")
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
            # Dynamic hints
            if iid == "form__image":
                self._show_hint(self._form_image_hint())
            elif iid.startswith("comp__dtitle__") and iid != "comp__dtitle__header":
                prop_key = iid[14:]   # strip "comp__dtitle__"
                self._show_hint(self._dtitle_conn_hint(prop_key))
            else:
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

    def _dispatch_comp_prop_click(self, row: str) -> None:
        if self._comp_def is None:
            return
        key = row[6:]   # strip "comp__"
        if key == "__name__":
            self._props_open_editor(row, self._commit_comp_prop)
            return
        if key == "dtitle__header":
            self._comp_dtitles_expanded = not self._comp_dtitles_expanded
            comp_obj = self._form.get_component(self._comp_id) if self._form and self._comp_id else None
            if comp_obj:
                self._rebuild_comp_props(comp_obj)
            return
        if key.startswith("dtitle__") and key != "dtitle__header":
            self._props_open_editor(row, self._commit_comp_prop)
            return
        pd  = next((p for p in self._comp_def.prop_defs if p.key == key), None)
        if pd is None or pd.kind == "readonly":
            return
        if pd.kind == "image_list":
            self._open_comp_image_picker(row)
        elif pd.kind == "canvas_ref":
            lookup_form = self._comp_form or self._form
            canvas_ids = ["None", "Global"] + [
                w.id for w in (lookup_form.widgets if lookup_form else [])
                if w.type == "Canvas"
            ]
            self._props_open_dropdown(row, canvas_ids, self._commit_comp_prop)
        elif pd.kind == "bool":
            self._props_open_dropdown(row, ["True", "False"], self._commit_comp_prop)
        else:
            self._props_open_editor(row, self._commit_comp_prop)

    def _commit_comp_prop(self, row_iid: str, raw: str) -> None:
        key = row_iid[6:]   # strip "comp__"
        if self._comp_def is None or self._comp_id is None:
            return
        if key == "__name__":
            name = raw.strip()
            if name and self._on_component_prop_change:
                self._on_component_prop_change(self._comp_id, "__name__", name)
            return
        if key.startswith("dtitle__") and key != "dtitle__header":
            prop_key = key[8:]   # e.g. "show_open_title"
            self._props_set(row_iid, raw)
            if self._on_component_prop_change:
                self._on_component_prop_change(self._comp_id, prop_key, raw)
            comp_obj = self._form.get_component(self._comp_id) if self._form else None
            if comp_obj:
                self._rebuild_comp_props(comp_obj)
            return
        pd = next((p for p in self._comp_def.prop_defs if p.key == key), None)
        if pd is None:
            return
        if pd.kind == "int":
            try:
                value: Any = int(raw)
            except ValueError:
                return
        elif pd.kind == "bool":
            value = raw.lower() == "true"
        else:
            value = raw
        # canvas_ref: warn + clear images when moving from a specific canvas to a different one
        if pd.kind == "canvas_ref":
            lookup_form = self._comp_form or self._form
            comp_obj = lookup_form.get_component(self._comp_id) if lookup_form else None
            if comp_obj:
                old_parent = comp_obj.props.get("parent", "None")
                is_specific = old_parent not in ("", "None", "Global")
                if is_specific and old_parent != value and comp_obj.props.get("paths"):
                    import tkinter.messagebox as _mb
                    n = len(comp_obj.props["paths"])
                    ok = _mb.askyesno(
                        "Change Canvas",
                        f"This Image component has {n} image{'s' if n != 1 else ''} linked "
                        f"to '{old_parent}'.\n\nChanging the canvas will remove all those images "
                        "from the component.\n\nContinue?",
                    )
                    if not ok:
                        return
                    comp_obj.props["paths"] = []
                    if self._on_component_prop_change:
                        self._on_component_prop_change(self._comp_id, "paths", [])
        self._props_set(row_iid, str(value))
        self._props_redraw()
        if self._on_component_prop_change:
            self._on_component_prop_change(self._comp_id, key, value)

    def _dispatch_prop_click(self, row: str) -> None:
        if self._comp_mode and row.startswith("comp__"):
            self._dispatch_comp_prop_click(row)
            return
        # Tags pool row for canvas widget — open canvas tags pool manager
        if row == "prop___canvas_tags":
            d = self._current_widget
            if d is not None and self._on_canvas_tags_needed:
                def _after_canvas_tags():
                    tags = d.props.get("_canvas_tags", [])
                    n = len(tags)
                    display = f"{n} tag{'s' if n != 1 else ''}" if tags else "(click to manage)"
                    self._props_set("prop___canvas_tags", display)
                self._on_canvas_tags_needed(d, _after_canvas_tags)
            return
        # Tags row for canvas items — open tag editor
        if row == "prop___ci_tags":
            d = self._current_widget
            if d is not None and self._on_ci_tags_needed:
                def _after_tags():
                    tags = d.props.get("_ci_tags", [])
                    display = ", ".join(tags) if tags else "(click to add tags)"
                    self._props_set("prop___ci_tags", display)
                self._on_ci_tags_needed(d, None, _after_tags)
            return
        if row == "pil__warning":
            if self._on_install_pillow:
                self._on_install_pillow()
            return
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
        elif row == "form__image":
            self._open_form_image_picker(row)
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
            if key == "image":
                if self._current_widget:
                    self._open_image_picker(row)
                return
            if key == "image_path" and self._on_ci_image_paths_needed:
                paths = self._on_ci_image_paths_needed()
                if paths:
                    self._props_open_dropdown(row, paths, self._commit_prop)
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
        "image", "compound",
    }

    def _is_prop_clearable(self, row_iid: str) -> bool:
        """Return True if this prop row has a value that can be cleared to empty."""
        if row_iid in ("var__name", "var__initial", "anchor__value", "form__bg", "form__image"):
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

    def _on_ev_edit_click(self, event: tk.Event) -> None:
        self._ev_clearing = True
        row = self._ev_btn_iid
        if not row:
            return
        self._ev_btn_iid = None
        self._ev_edit_btn.place_forget()
        idx = self._events_row_map.get(row)
        if idx is not None and self._events_rows[idx].get("kind") == "comp_wire":
            widget_id = self._events_rows[idx].get("conn_widget", "")
            ev_key    = self._events_rows[idx]["label"]
            if self._comp_id and self._on_component_edit and widget_id:
                self._on_component_edit(self._comp_id, widget_id, ev_key)

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
            if key in _NULLABLE_INT_PROPS:
                stripped = raw.strip()
                if stripped == "":
                    if self._prop_clearing:
                        # × clicked — mark as omitted (None = not emitted in codegen)
                        d.props[key] = None
                        self._props_set(row_iid, "")
                        if self._on_prop_change:
                            self._on_prop_change(d.id, key, None)
                    else:
                        # Blank entry — revert display to current value, no commit
                        old = d.props.get(key, 0)
                        self._props_set(row_iid, "" if old is None else str(old))
                    return
                try:
                    val = int(stripped)
                except ValueError:
                    # Invalid int — revert display
                    old = d.props.get(key, 0)
                    self._props_set(row_iid, "" if old is None else str(old))
                    return
                d.props[key] = val
                if self._on_prop_change:
                    self._on_prop_change(d.id, key, val)
                return
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
        # CI items always route through the tag callback so the correct binding_tag is set
        if "_ci_tags" in d.props and self._on_ci_tags_needed:
            def _proceed():
                self._do_auto_wire(d, row_iid, event_key)
            self._on_ci_tags_needed(d, event_key, _proceed)
            return
        self._do_auto_wire(d, row_iid, event_key)

    def _do_auto_wire(self, d: "WidgetDescriptor", row_iid: str, event_key: str) -> None:
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
    "bd":               "border",
}

# Props that store int-or-None; None means "omit from generated code entirely"
_NULLABLE_INT_PROPS: frozenset[str] = frozenset({"highlightthickness", "bd"})

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
    "tabchanged":    ("<<NotebookTabChanged>>", "Active tab changed — use self.widget.tab(self.widget.select(), 'text') to get the new tab name"),
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
    # Widget image / compound
    "image":              "Background image displayed on this widget (click to pick a file; requires Pillow)",
    "compound":           "When both text and image are set, controls which is shown and where: none shows only the image, left/right/top/bottom places the image beside the text",
    # Canvas-specific
    "highlightthickness": "Focus-highlight ring width in pixels (0 = none); click × to omit entirely and let tkinter use its default",
    "bd":                 "Canvas border (bd) width in pixels (0 = none); click × to omit entirely and let tkinter use its default",
    "sizing":             "sizable — widget fills its placed bounds and can be resized; fit image — widget locks to the natural dimensions of the background image (resize handles disabled)",
    # Scrollbar
    "scrollbar":          "Attach a scrollbar: None, Vertical, Horizontal, or Both",
    # Notebook tabs
    "tabs":               "Ordered list of tab names; click to open the tab editor",
    # Radiobutton
    "value":              "The value written to the linked variable when this radio button is selected; each button in a group should have a unique value",
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

    sb = VerticalScrollbar(parent, command=tree.yview)
    tree.configure(yscrollcommand=sb.set)
    sb.pack(side="right", fill="y")
    tree.pack(fill="both", expand=True)
    return tree


def _display(val: Any) -> str:
    """Human-readable string for a prop value shown in the tree."""
    if val is None:
        return ""
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
