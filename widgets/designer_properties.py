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
        self._entry_editor:   tk.Entry | None           = None
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
            font=("Segoe UI", 8), anchor="w", padx=6, pady=2,
        )
        self._status_label.pack(fill="x", side="bottom")

        self._nb = ttk.Notebook(self, style="Props.TNotebook")
        self._nb.pack(fill="both", expand=True)

        # Properties tab
        self._props_frame = tk.Frame(self._nb, bg="#1e1e1e")
        self._nb.add(self._props_frame, text="  Properties  ")
        self._props_tree = _make_tree(self._props_frame)
        self._props_tree.bind("<Button-1>", self._on_prop_click)

        # Events tab
        self._events_frame = tk.Frame(self._nb, bg="#1e1e1e")
        self._nb.add(self._events_frame, text="  Events  ")

        self._events_tree = _make_tree(self._events_frame, value_col_name="Handler")
        self._events_tree.bind("<Button-1>", self._on_event_click)
        self._events_tree.bind("<Motion>",   self._on_event_hover)
        self._events_tree.bind("<Leave>",    self._on_event_leave)

        self._ev_hover_row: str | None = None
        self._ev_clear_btn = tk.Label(
            self._events_tree, text="×",
            bg="#3a3a3a", fg="#888888",
            font=("Segoe UI", 9), cursor="hand2", padx=2,
        )
        self._ev_clear_btn.bind("<Enter>",    lambda e: self._ev_clear_btn.config(fg="#ff6b6b"))
        self._ev_clear_btn.bind("<Leave>",    lambda e: self._ev_clear_btn.config(fg="#888888"))
        self._ev_clear_btn.bind("<Button-1>", self._on_ev_clear_click)

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
        self._status_label.config(text=message)
        self._status_after = self.after(
            duration_ms, lambda: self._status_label.config(text="")
        )

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
                     "Click the ✦ icon next to an event row to auto-fill a handler name based on "
                     "the widget name. You can also type any name directly in the Handler column.",
                     "#cccccc"),
                    ("BUTTON COMMAND",
                     "For Button widgets, the click event is wired as command= in the constructor "
                     "rather than a .bind() call — this is the standard tkinter pattern and "
                     "behaves identically from your handler's perspective.", "#e2c08d"),
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
        seen: set[str] = set()
        for key in list(defaults) + [k for k in d.props if k not in defaults]:
            if key in seen or key in _state_reserved or key in _validate_reserved:
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
        if row == "var__section":
            return  # section header — not editable
        if row == "form__bg" or self._is_color_row(row):
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
        elif row.startswith("prop__") and self._current_widget:
            key = row[6:]
            if key == "font":
                self._open_font_picker(row)
                return
            reg = REGISTRY.get(self._current_widget.type, {})
            choices = reg.get("prop_choices", {}).get(key)
            if choices:
                self._open_dropdown(tree, row, col, choices, self._commit_prop)
                return
            self._open_editor(tree, row, col, self._commit_prop)
            return
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
            # If no handler set yet, auto-wire on click; otherwise open editor
            if tree.set(row, "#1").strip():
                self._open_editor(tree, row, col, self._commit_event)
            else:
                self._auto_wire_event(row)
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
        return False

    def _open_dropdown(self, tree: ttk.Treeview, row: str, col: str,
                       values: list[str], commit_fn) -> None:
        self._dismiss_editor()
        bbox = tree.bbox(row, col)
        if not bbox:
            return
        x, y, w, h = bbox
        rx = tree.winfo_rootx() + x
        ry = tree.winfo_rooty() + y + h

        current = tree.set(row, col)
        menu = tk.Menu(tree.winfo_toplevel(), tearoff=0,
                       bg="#2d2d2d", fg="#cccccc",
                       activebackground="#094771", activeforeground="#ffffff",
                       relief="flat", bd=1)
        for val in values:
            def _cmd(v=val):
                tree.set(row, col, v)
                commit_fn(row, v)
            menu.add_command(label=val, command=_cmd,
                             font=("Segoe UI", 9),
                             columnbreak=False)
        try:
            menu.tk_popup(rx, ry)
        finally:
            menu.grab_release()

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
        self._ev_hover_row = row
        if not row or not tree.set(row, "#1").strip():
            self._ev_clear_btn.place_forget()
            return
        bbox = tree.bbox(row, "#1")
        if not bbox:
            self._ev_clear_btn.place_forget()
            return
        x, y, w, h = bbox
        bw = 18
        self._ev_clear_btn.place(x=x + w - bw, y=y, width=bw, height=h)
        self._ev_clear_btn.lift()

    def _on_event_leave(self, event: tk.Event) -> None:
        self._ev_hover_row = None
        self._ev_clear_btn.place_forget()

    def _on_ev_clear_click(self, event: tk.Event) -> None:
        row = self._ev_hover_row
        if not row:
            return
        self._ev_clear_btn.place_forget()
        self._ev_hover_row = None
        self._events_tree.set(row, "#1", "")
        self._commit_event(row, "")

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
                self.load_widget(d)
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
    "change":      ("<<Modified>>",       "Content changed"),
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
        return ", ".join(str(v) for v in val)
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
