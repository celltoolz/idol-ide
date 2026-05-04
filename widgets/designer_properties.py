from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from designer.model import FormModel, VariableBinding, WidgetDescriptor
from designer.registry import REGISTRY
from widgets.guide_window import GuideWindow, GuidePage


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
        on_prop_change:   Optional[Callable[[str, str, Any],  None]] = None,
        on_event_change:  Optional[Callable[[str, str, str], None]] = None,
        on_select_widget: Optional[Callable[[str | None],    None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg="#252526", **kwargs)
        self._on_prop_change   = on_prop_change
        self._on_event_change  = on_event_change
        self._on_select_widget = on_select_widget
        self._current_widget: WidgetDescriptor | None  = None
        self._multi_widgets:  list[WidgetDescriptor]    = []
        self._entry_editor:   tk.Widget | None          = None
        self._form:           FormModel | None          = None
        # (display_label, widget_id | None)  — None means the form itself
        self._selector_items: list[tuple[str, str | None]] = []
        self._status_after:   str | None                = None
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
            font=("Segoe UI", 9), anchor="w", padx=6,
            cursor="hand2",
        )
        self._selector_label.pack(side="left", fill="x", expand=True)

        self._selector_arrow = tk.Label(
            sel_frame, text="▼",
            bg="#3c3c3c", fg="#858585",
            font=("Segoe UI", 7), padx=4,
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

        # Status bar — shown briefly when a validation error occurs
        self._status_label = tk.Label(
            self, text="", bg="#252526", fg="#ff6b6b",
            font=("Segoe UI", 8), anchor="nw", padx=6, pady=4,
            justify="left", wraplength=200,
        )
        self._status_label.pack(fill="x", side="bottom")
        self._status_label.bind(
            "<Configure>",
            lambda e: self._status_label.config(wraplength=max(1, e.width - 12)),
        )

        self._nb = ttk.Notebook(self, style="Props.TNotebook")
        self._nb.pack(fill="both", expand=True)

        # Properties tab
        self._props_frame = tk.Frame(self._nb, bg="#1e1e1e")
        self._nb.add(self._props_frame, text="  Properties  ")
        self._props_tree = _make_tree(self._props_frame)
        self._props_tree.tag_configure("hover", foreground="#569cd6")
        self._props_tree.bind("<Button-1>", self._on_prop_click)
        self._props_tree.bind("<Motion>",   self._on_prop_hover)
        self._props_tree.bind("<Leave>",    self._on_prop_leave)
        self._prop_hover_row:        str | None = None
        self._prop_hover_saved_tags: tuple      = ()
        self._prop_clear_btn = tk.Label(
            self._props_tree, text="×",
            bg="#3a3a3a", fg="#888888",
            font=("Segoe UI", 9), cursor="hand2", padx=2,
        )
        self._prop_clear_btn.bind("<Enter>",    lambda e: self._prop_clear_btn.config(fg="#ff6b6b"))
        self._prop_clear_btn.bind("<Leave>",    lambda e: self._prop_clear_btn.config(fg="#888888"))
        self._prop_clear_btn.bind("<Button-1>", self._on_prop_clear_click)

        # Events tab
        self._events_frame = tk.Frame(self._nb, bg="#1e1e1e")
        self._nb.add(self._events_frame, text="  Events  ")

        self._events_tree = _make_tree(self._events_frame, value_col_name="Handler")
        self._events_tree.tag_configure("hover", foreground="#569cd6")
        self._events_tree.bind("<Button-1>", self._on_event_click)
        self._events_tree.bind("<Motion>",   self._on_event_hover)
        self._events_tree.bind("<Leave>",    self._on_event_leave)

        self._ev_hover_row:        str | None = None
        self._ev_hover_saved_tags: tuple      = ()
        self._ev_clear_btn = tk.Label(
            self._events_tree, text="×",
            bg="#3a3a3a", fg="#888888",
            font=("Segoe UI", 9), cursor="hand2", padx=2,
        )
        self._ev_clear_btn.bind("<Enter>",    lambda e: self._ev_clear_btn.config(fg="#ff6b6b"))
        self._ev_clear_btn.bind("<Leave>",    lambda e: self._ev_clear_btn.config(fg="#888888"))
        self._ev_clear_btn.bind("<Button-1>", self._on_ev_clear_click)

        self._ev_wire_btn = tk.Label(
            self._events_tree, text="✦",
            bg="#3a3a3a", fg="#555555",
            font=("Segoe UI", 9), cursor="hand2", padx=2,
        )
        self._ev_wire_btn.bind("<Enter>",    lambda e: self._ev_wire_btn.config(fg="#569cd6"))
        self._ev_wire_btn.bind("<Leave>",    lambda e: self._ev_wire_btn.config(fg="#555555"))
        self._ev_wire_btn.bind("<Button-1>", self._on_ev_wire_click)

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

    def load_form(self, form: FormModel) -> None:
        """Show form-level properties when the canvas background is selected."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._set_selector(None)

        self._props_tree.delete(*self._props_tree.get_children())
        for key, label, val in [
            ("title",        "title",        form.title),
            ("width",        "width",        form.width),
            ("height",       "height",       form.height),
            ("border_style", "border style", form.border_style),
            ("maximize_box", "maximize",     form.maximize_box),
            ("bg",           "background",   form.bg),
        ]:
            self._props_tree.insert("", "end", iid=f"form__{key}",
                                    text=label, values=(str(val),))
        # Tint the background row with the current color
        self._apply_color_swatch("form__bg", (form.bg or "#f5f5f5").upper())
        # Menu bar row
        n = len(form.menu_items)
        menu_val = f"{n} item{'s' if n != 1 else ''}" if n else "(none)"
        self._props_tree.insert("", "end", iid="form__menu_bar",
                                text="menu bar", values=(menu_val,))
        self._props_tree.tag_configure("menu_bar_link", foreground="#569cd6")
        self._props_tree.item("form__menu_bar", tags=("menu_bar_link",))

        self._events_tree.delete(*self._events_tree.get_children())
        for ev in ("load", "activate", "deactivate", "unload"):
            self._events_tree.insert("", "end", iid=f"form_ev__{ev}",
                                     text=ev, values=("",))

    def load_multi(self, descriptors: list[WidgetDescriptor]) -> None:
        """Show geometry-only panel for a multi-widget selection."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = list(descriptors)
        self._selector_label.config(text=f"({len(descriptors)} widgets selected)")
        primary = descriptors[0] if descriptors else None

        self._props_tree.delete(*self._props_tree.get_children())
        if primary:
            for key in ("x", "y", "width", "height"):
                self._props_tree.insert("", "end", iid=f"geo__{key}",
                                        text=key, values=(str(getattr(primary, key)),))
        self._events_tree.delete(*self._events_tree.get_children())

    def clear(self) -> None:
        """Reset to the empty / no-selection state."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._selector_items = []
        self._selector_label.config(text="Properties")
        self._props_tree.delete(*self._props_tree.get_children())
        self._events_tree.delete(*self._events_tree.get_children())

    def set_form(self, form: FormModel) -> None:
        """Rebuild the control selector dropdown from the current form."""
        self._form = form
        self._selector_items = [(f"{form.name}  (Form)", None)]
        for w in form.widgets:
            self._selector_items.append((f"{w.id}  ({w.type})", w.id))

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
            menu.add_command(label=label, command=_cmd, font=("Segoe UI", 9))
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
            self._status_label.config(text="")

    def flash_events_tab(self) -> None:
        """Switch to the Events tab."""
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
        self._props_tree.delete(*self._props_tree.get_children())
        # Name first (the widget's ID / variable name)
        self._props_tree.insert("", "end", iid="widget__name",
                                text="name", values=(d.id,))
        # Geometry
        for key in ("x", "y", "width", "height"):
            self._props_tree.insert("", "end", iid=f"geo__{key}",
                                    text=key, values=(str(getattr(d, key)),))
        # Parent container (read-only — drag to reparent)
        parent_val = d.parent_id if d.parent_id else "(form)"
        self._props_tree.insert("", "end", iid="geo__parent",
                                text="parent", values=(parent_val,))
        # Widget-specific props — exclude state/validate (handled in dedicated blocks)
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
            self._props_tree.insert("", "end", iid=f"prop__{key}",
                                    text=_PROP_LABELS.get(key, key), values=(_display(val),))
        # Color props — always show even when not set, apply swatches
        for key in color_props:
            if key in seen:
                val = d.props.get(key, "")
            else:
                val = d.props.get(key, "")
                self._props_tree.insert("", "end", iid=f"prop__{key}",
                                        text=_PROP_LABELS.get(key, key), values=(val,))
                seen.add(key)
            if val:
                self._apply_color_swatch(f"prop__{key}", val.upper())
        # State row + conditional indented color props
        if reg.get("state_prop"):
            current_state = d.props.get("state", "normal")
            self._props_tree.insert("", "end", iid="prop__state",
                                    text="state", values=(current_state,))
            seen.add("state")
            state_colors = reg.get("state_color_props", {})
            for color_key in state_colors.get(current_state, []):
                label = _STATE_COLOR_LABELS.get(color_key, f"  --{color_key}")
                val = d.props.get(color_key, "")
                self._props_tree.insert("", "end", iid=f"prop__{color_key}",
                                        text=label, values=(val,))
                seen.add(color_key)
                if val:
                    self._apply_color_swatch(f"prop__{color_key}", val.upper())

        # Validate row + conditional vcmd / --args / ivcmd rows
        if reg.get("validate_prop"):
            current_validate = d.props.get("validate", "none")
            self._props_tree.insert("", "end", iid="prop__validate",
                                    text="validate", values=(current_validate,))
            seen.add("validate")
            if current_validate != "none":
                self._props_tree.tag_configure("vcmd_warn", foreground="#ff6b6b")
                for v_key, v_label in (("validatecommand", "  --vcmd"),
                                       ("invalidcommand",  "  --ivcmd")):
                    val = d.props.get(v_key, "")
                    self._props_tree.insert("", "end", iid=f"prop__{v_key}",
                                            text=v_label, values=(val,))
                    if val and not val.startswith("_"):
                        self._props_tree.item(f"prop__{v_key}", tags=("vcmd_warn",))
                    # --args between the two command rows
                    if v_key == "validatecommand":
                        self._props_tree.insert("", "end", iid="prop__vcmd_args",
                                                text="  --args",
                                                values=(d.props.get("vcmd_args", "%P"),))
                seen.update({"validatecommand", "vcmd_args", "invalidcommand"})

        # Colorize row + conditional alt-bg color row
        if reg.get("colorize_prop"):
            current_colorize = bool(d.props.get("colorize", False))
            self._props_tree.insert("", "end", iid="prop__colorize",
                                    text="colorize", values=(str(current_colorize),))
            seen.add("colorize")
            if current_colorize:
                alt_bg = d.props.get("colorize_altbg", "")
                self._props_tree.insert("", "end", iid="prop__colorize_altbg",
                                        text="  --alt bg", values=(alt_bg,))
                seen.add("colorize_altbg")
                if alt_bg:
                    self._apply_color_swatch("prop__colorize_altbg", alt_bg.upper())

        # Variable binding section (only for widgets that support it)
        if reg.get("variable_prop"):
            var_types = reg.get("variable_types", ["StringVar"])
            vb = d.variable
            self._props_tree.insert("", "end", iid="var__section",
                                    text="── Variable", values=("",))
            self._props_tree.tag_configure("var_section",
                                           foreground="#569cd6", font=("Segoe UI", 8))
            self._props_tree.item("var__section", tags=("var_section",))
            self._props_tree.insert("", "end", iid="var__name",
                                    text="  variable", values=(vb.name if vb else "",))
            self._props_tree.insert("", "end", iid="var__type",
                                    text="  type",
                                    values=(vb.var_type if vb else var_types[0],))
            self._props_tree.insert("", "end", iid="var__initial",
                                    text="  initial", values=(vb.initial if vb else "",))

    def _populate_events(self, d: WidgetDescriptor, reg: dict) -> None:
        self._events_tree.delete(*self._events_tree.get_children())
        self._events_tree.tag_configure("name_warn", foreground="#ff6b6b")
        self._events_tree.tag_configure("ev_guide_link", foreground="#569cd6")
        for ev in reg.get("events", []):
            handler = d.events.get(ev, "")
            iid = f"ev__{ev}"
            self._events_tree.insert("", "end", iid=iid, text=ev, values=(handler,))
            if handler and not handler.startswith("_"):
                self._events_tree.item(iid, tags=("name_warn",))
        self._events_tree.insert("", "end", iid="ev__learn_guide",
                                 text="? Events", values=("",),
                                 tags=("ev_guide_link",))

    # ── Click handlers ────────────────────────────────────────────────────────

    def _on_prop_click(self, event: tk.Event) -> None:
        tree = self._props_tree
        row  = tree.identify_row(event.y)
        col  = tree.identify_column(event.x)
        if not row or col != "#1":
            return
        if row in ("var__section", "geo__parent"):
            return  # not editable
        if row == "form__menu_bar":
            self._open_menu_editor()
        elif row == "form__bg" or self._is_color_row(row):
            self._open_color_picker(row)
        elif row == "form__border_style":
            self._open_dropdown(self._props_tree, row, col,
                                ["sizable", "fixed", "none"], self._commit_prop)
        elif row == "form__maximize_box":
            self._open_dropdown(self._props_tree, row, col,
                                ["True", "False"], self._commit_prop)
        elif row == "prop__state":
            d = self._current_widget
            if d is None:
                return
            reg = REGISTRY.get(d.type, {})
            self._open_dropdown(tree, row, col,
                                reg.get("state_values", ["normal", "disabled"]),
                                self._commit_prop)
        elif row == "prop__validate":
            d = self._current_widget
            if d is None:
                return
            reg = REGISTRY.get(d.type, {})
            self._open_dropdown(tree, row, col,
                                reg.get("validate_values",
                                        ["none", "focus", "focusin", "focusout", "key", "all"]),
                                self._commit_prop)
        elif row == "prop__vcmd_args":
            self._open_dropdown(tree, row, col, _VCMD_ARG_PRESETS, self._commit_prop)
        elif row == "prop__colorize":
            self._open_dropdown(tree, row, col, ["True", "False"], self._commit_prop)
        elif row.startswith("prop__") and self._current_widget:
            key = row[6:]
            if key == "font":
                self._open_font_picker(row)
                return
            if isinstance(self._current_widget.props.get(key), list):
                self._open_list_editor(row)
                return
            reg = REGISTRY.get(self._current_widget.type, {})
            choices = reg.get("prop_choices", {}).get(key)
            if choices:
                self._open_dropdown(tree, row, col, choices, self._commit_prop)
                return
            self._open_editor(tree, row, col, self._commit_prop)
            return
        elif row == "var__name":
            self._open_variable_picker(tree, row, col)
        elif row == "var__type":
            d = self._current_widget
            if d is None:
                return
            reg = REGISTRY.get(d.type, {})
            var_types = reg.get("variable_types", ["StringVar"])
            self._open_dropdown(tree, row, col, var_types, self._commit_prop)
        else:
            self._open_editor(tree, row, col, self._commit_prop)

    def _on_event_click(self, event: tk.Event) -> None:
        tree = self._events_tree
        row  = tree.identify_row(event.y)
        col  = tree.identify_column(event.x)
        if not row:
            return
        if row == "ev__learn_guide":
            self._open_event_guide()
            return
        if col == "#1":
            self._open_handler_picker(tree, row, col)
        elif col == "#0":
            self._auto_wire_event(row)

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
            val = entry.get()
            self._dismiss_editor()
            tree.set(row, col, val)
            commit_fn(row, val)

        entry.bind("<Return>",   commit)
        entry.bind("<Tab>",      commit)
        entry.bind("<Escape>",   lambda _: self._dismiss_editor())
        entry.bind("<FocusOut>", commit)

    def _open_variable_picker(self, tree: ttk.Treeview, row: str, col: str) -> None:
        """Inline entry + variable picker popup for the var__name row."""
        from designer.var_picker import collect_form_variables, show_variable_popup
        self._dismiss_editor()
        if self._form is None:
            return
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

        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        tree.after_idle(_grab_focus)

        popup_ref: list = [None]

        def _commit(_=None):
            val = entry.get()
            if popup_ref[0] and popup_ref[0].winfo_exists():
                popup_ref[0].destroy()
            self._dismiss_editor()
            tree.set(row, col, val)
            self._commit_prop(row, val)

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

        variables = collect_form_variables(self._form)
        popup_ref[0] = show_variable_popup(
            anchor=entry,
            variables=variables,
            on_select=_on_select,
            entry_ref=entry,
        )

    def _open_handler_picker(self, tree: ttk.Treeview, row: str, col: str) -> None:
        """Inline entry + handler picker popup for event handler rows."""
        from designer.var_picker import collect_form_handlers, show_handler_popup
        if not row.startswith("ev__"):
            return
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

        def _grab_focus():
            try:
                entry.focus_force()
                entry.select_range(0, "end")
                entry.icursor("end")
            except Exception:
                pass
        tree.after_idle(_grab_focus)

        popup_ref: list = [None]

        def _commit(_=None):
            val = entry.get()
            if popup_ref[0] and popup_ref[0].winfo_exists():
                popup_ref[0].destroy()
            self._dismiss_editor()
            tree.set(row, col, val)
            self._commit_event(row, val)

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

        handlers = collect_form_handlers(self._form) if self._form is not None else []
        popup_ref[0] = show_handler_popup(
            anchor=entry,
            handlers=handlers,
            on_select=_on_select,
            entry_ref=entry,
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

        bbox = self._props_tree.bbox(row, "#1")
        if not bbox:
            return
        _, by, _, _ = bbox
        tree_w = self._props_tree.winfo_width() - 4

        panel = tk.Frame(self._props_tree, bg="#2d2d2d",
                         highlightthickness=1,
                         highlightbackground="#007acc")
        items_frame = tk.Frame(panel, bg="#2d2d2d")
        items_frame.pack(fill="x", padx=2, pady=(2, 0))

        def _do_commit():
            d.props[key] = list(current_list)
            self._props_tree.set(row, "#1", _display(current_list))
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
            aid = self._props_tree.after(100, _maybe_dismiss)
            _pending.append(aid)

        def _maybe_dismiss():
            try:
                fw = self._props_tree.winfo_toplevel().focus_get()
            except Exception:
                fw = None
            # Stay open if focus is still inside the panel
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
                    self._props_tree.after_cancel(aid)
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
        self._props_tree.after_idle(entry.focus_force)

    def _is_color_row(self, row_iid: str) -> bool:
        if not row_iid.startswith("prop__"):
            return False
        d = self._current_widget
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
    _CLEARABLE_PROPS = {"show", "font", "justify", "relief", "borderwidth", "insertbackground"}

    def _is_prop_clearable(self, row_iid: str) -> bool:
        """Return True if this prop row has a value that can be cleared to empty."""
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
                           font=("Segoe UI", 9), anchor="w",
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

            lbl.bind("<Enter>",    _enter)
            lbl.bind("<Leave>",    _leave)
            lbl.bind("<Button-1>", _click)

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

    def _open_color_picker(self, row_iid: str) -> None:
        """Open a color picker for a color property cell."""
        current = self._props_tree.set(row_iid, "#1").strip() or "#ffffff"
        from tkinter.colorchooser import askcolor
        result = askcolor(current, parent=self._props_tree.winfo_toplevel())
        color = result[1] if result else None
        if not color:
            return
        color = color.upper()
        self._props_tree.set(row_iid, "#1", color)
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
            self._props_tree.set("form__menu_bar", "#1", val)
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
        self._props_tree.set(row_iid, "#1", display)
        d.props["font"] = font_tuple
        if self._on_prop_change:
            self._on_prop_change(d.id, "font", font_tuple)

    def _apply_color_swatch(self, row_iid: str, color: str) -> None:
        """Tint the treeview row to preview the color."""
        try:
            tag = f"swatch:{row_iid}"
            fg  = _contrast_color(color)
            self._props_tree.tag_configure(tag, background=color, foreground=fg)
            self._props_tree.item(row_iid, tags=(tag,))
        except Exception:
            pass

    def _on_event_hover(self, event: tk.Event) -> None:
        tree = self._events_tree
        row  = tree.identify_row(event.y)
        if row == self._ev_hover_row:
            return
        # restore previous row's tags
        if self._ev_hover_row:
            try:
                tree.item(self._ev_hover_row, tags=self._ev_hover_saved_tags)
            except Exception:
                pass
        self._ev_hover_row = row
        self._ev_hover_saved_tags = ()
        if not row:
            self._ev_clear_btn.place_forget()
            return
        self._ev_hover_saved_tags = tuple(tree.item(row, "tags") or ())
        tree.item(row, tags=(*self._ev_hover_saved_tags, "hover"))
        ev_name = row[4:] if row.startswith("ev__") else row[8:] if row.startswith("form_ev__") else ""
        hint = _EVENT_DESCRIPTIONS.get(ev_name, ("", ""))[1]
        if hint:
            self._show_hint(hint)
        bbox = tree.bbox(row, "#1")
        if not bbox:
            self._ev_clear_btn.place_forget()
            self._ev_wire_btn.place_forget()
            return
        x, y, w, h = bbox
        bw = 18
        if tree.set(row, "#1").strip():
            # Wired row — show × to clear
            self._ev_wire_btn.place_forget()
            self._ev_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
            self._ev_clear_btn.lift()
        else:
            # Unwired row — show ✦ to auto-wire
            self._ev_clear_btn.place_forget()
            if row.startswith("ev__") and self._current_widget:
                self._ev_wire_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._ev_wire_btn.lift()
            else:
                self._ev_wire_btn.place_forget()

    def _on_prop_hover(self, event: tk.Event) -> None:
        tree = self._props_tree
        row  = tree.identify_row(event.y)
        if row == self._prop_hover_row:
            return
        self._clear_prop_hover()
        if not row or row == "var__section":
            return
        self._prop_hover_saved_tags = tuple(tree.item(row, "tags") or ())
        self._prop_hover_row = row
        tree.item(row, tags=(*self._prop_hover_saved_tags, "hover"))
        if self._is_prop_clearable(row) and tree.set(row, "#1").strip():
            bbox = tree.bbox(row, "#1")
            if bbox:
                x, y, w, h = bbox
                bw = 18
                self._prop_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
                self._prop_clear_btn.lift()
        key = row.split("__", 1)[-1] if "__" in row else row
        hint = _PROP_HINTS.get(key)
        if hint:
            self._show_hint(hint)

    def _on_prop_leave(self, event: tk.Event) -> None:
        self._clear_prop_hover()

    def _clear_prop_hover(self) -> None:
        self._prop_clear_btn.place_forget()
        self._clear_hint()
        if self._prop_hover_row:
            try:
                self._props_tree.item(self._prop_hover_row,
                                      tags=self._prop_hover_saved_tags)
            except Exception:
                pass
            self._prop_hover_row = None
            self._prop_hover_saved_tags = ()

    def _on_event_leave(self, event: tk.Event) -> None:
        if self._ev_hover_row:
            try:
                self._events_tree.item(self._ev_hover_row, tags=self._ev_hover_saved_tags)
            except Exception:
                pass
        self._ev_hover_row = None
        self._ev_hover_saved_tags = ()
        self._ev_clear_btn.place_forget()
        self._ev_wire_btn.place_forget()
        self._clear_hint()

    def _on_ev_clear_click(self, event: tk.Event) -> None:
        row = self._ev_hover_row
        if not row:
            return
        self._ev_clear_btn.place_forget()
        self._ev_hover_row = None
        self._events_tree.set(row, "#1", "")
        self._commit_event(row, "")

    def _on_ev_wire_click(self, event: tk.Event) -> None:
        row = self._ev_hover_row
        if not row or not row.startswith("ev__"):
            return
        self._ev_wire_btn.place_forget()
        self._auto_wire_event(row)

    def _on_prop_clear_click(self, event: tk.Event) -> None:
        row = self._prop_hover_row
        if not row:
            return
        self._clear_prop_hover()
        self._props_tree.set(row, "#1", "")
        if self._is_color_row(row):
            self._props_tree.item(row, tags=())
        self._commit_prop(row, "")

    def _dismiss_editor(self) -> None:
        if self._entry_editor:
            try:
                self._entry_editor.destroy()
            except Exception:
                pass
            self._entry_editor = None

    # ── Commit callbacks ──────────────────────────────────────────────────────

    def _commit_prop(self, row_iid: str, raw: str) -> None:
        if row_iid.startswith("form__"):
            key = row_iid[6:]
            # Keep border_style and maximize_box in sync
            if key == "border_style":
                new_max = "True" if raw.lower() == "sizable" else "False"
                self._props_tree.set("form__maximize_box", "#1", new_max)
                if self._on_prop_change:
                    self._on_prop_change("__form__", "maximize_box", new_max)
            elif key == "maximize_box":
                new_style = "sizable" if raw.lower() == "true" else "fixed"
                self._props_tree.set("form__border_style", "#1", new_style)
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
        if row_iid == "widget__name":
            d = self._current_widget
            if d is None:
                return
            new_name = raw.strip()
            if not new_name or not new_name.isidentifier() or new_name == d.id:
                self._props_tree.set(row_iid, "#1", d.id)
                return
            if self._form and any(w.id == new_name for w in self._form.widgets
                                  if w.id != d.id):
                self._props_tree.set(row_iid, "#1", d.id)
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
                self._props_tree.tag_configure("vcmd_warn", foreground="#ff6b6b")
                val = str(parsed)
                if val and not val.startswith("_"):
                    self._props_tree.item(row_iid, tags=("vcmd_warn",))
                else:
                    self._props_tree.item(row_iid, tags=())
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
                    self._props_tree.set("prop__wrap", "#1", "none")
                    if self._on_prop_change:
                        self._on_prop_change(d.id, "wrap", "none")
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
                self._props_tree.set(row_iid, "#1",
                                     d.variable.name if d.variable else "")
                return
        elif field in ("type", "initial"):
            if d.variable is None:
                # Auto-create with default name
                default_name = f"{d.id}_var"
                d.variable = VariableBinding(name=default_name,
                                             var_type=var_types[0],
                                             initial="")
                self._props_tree.set("var__name", "#1", default_name)
            if field == "type":
                d.variable.var_type = raw.strip()
            else:
                d.variable.initial = raw.strip()

        if self._on_prop_change:
            self._on_prop_change(d.id, "__variable__", d.variable)

    def _commit_event(self, row_iid: str, raw: str) -> None:
        d = self._current_widget
        if d is None or not row_iid.startswith("ev__"):
            return
        event_key = row_iid[4:]
        handler = raw.strip()
        if handler:
            d.events[event_key] = handler
        else:
            d.events.pop(event_key, None)
        if self._on_event_change:
            self._on_event_change(d.id, event_key, handler)
        self._events_tree.tag_configure("name_warn", foreground="#ff6b6b")
        if handler and not handler.startswith("_"):
            self._events_tree.item(row_iid, tags=("name_warn",))
        else:
            self._events_tree.item(row_iid, tags=())

    def _auto_wire_event(self, row_iid: str) -> None:
        """Click on event name → fill default handler and commit."""
        d = self._current_widget
        if d is None or not row_iid.startswith("ev__"):
            return
        event_key = row_iid[4:]
        if d.events.get(event_key):
            return  # already wired
        default = f"_{d.id}_{event_key}"
        d.events[event_key] = default
        self._events_tree.set(row_iid, "#1", default)
        if self._on_event_change:
            self._on_event_change(d.id, event_key, default)


# ── Helpers ───────────────────────────────────────────────────────────────────

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
}

_PROP_HINTS: dict[str, str] = {
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
    "exportselection":    "Copy selection to clipboard automatically when text is selected",
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
    # Validation
    "validate":           "When to run the validation function",
    "validatecommand":    "Method called to validate input — must start with _",
    "vcmd_args":          "Substitution codes passed to validator (%P = new value, %s = current)",
    "invalidcommand":     "Method called when validation fails — must start with _",
    # Form props
    "title":              "Window title shown in the title bar",
    "border_style":       "Window border: sizable (resizable), fixed, or none (no chrome)",
    "maximize_box":       "Whether the maximize / restore button is visible",
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
}

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
