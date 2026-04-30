from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from designer.model import FormModel, VariableBinding, WidgetDescriptor
from designer.registry import REGISTRY


class DesignerProperties(tk.Frame):
    """Properties + Events panel for the GUI Designer.

    Displayed in the right pane of _h_pane while Designer mode is active.
    Exposes load_widget(), load_form(), and clear() as the public API.
    Fires on_prop_change(widget_id, key, value) and
         on_event_change(widget_id, event_key, handler_name) on user edits.
    """

    def __init__(
        self,
        master,
        on_prop_change:  Optional[Callable[[str, str, Any],  None]] = None,
        on_event_change: Optional[Callable[[str, str, str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg="#252526", **kwargs)
        self._on_prop_change  = on_prop_change
        self._on_event_change = on_event_change
        self._current_widget: WidgetDescriptor | None       = None
        self._multi_widgets:  list[WidgetDescriptor]         = []
        self._entry_editor:   tk.Entry | None                = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        _apply_tree_style()

        # Header — shows "widget_id  (Type)" or "Form1  (Form)"
        self._header = tk.Label(
            self, text="Properties",
            bg="#252526", fg="#cccccc",
            font=("Segoe UI", 9, "bold"),
            anchor="w", padx=8,
        )
        self._header.pack(fill="x", side="top", pady=(6, 2))
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Notebook: Properties | Events
        nb_style = ttk.Style()
        nb_style.configure("Props.TNotebook",        background="#252526", borderwidth=0)
        nb_style.configure("Props.TNotebook.Tab",    background="#1e1e1e", foreground="#858585",
                           padding=(8, 3))
        nb_style.map("Props.TNotebook.Tab",
                     background=[("selected", "#252526")],
                     foreground=[("selected", "#cccccc")])

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

    # ── Public API ────────────────────────────────────────────────────────────

    def load_widget(self, descriptor: WidgetDescriptor) -> None:
        """Populate the panel from *descriptor*."""
        self._dismiss_editor()
        self._current_widget = descriptor
        self._multi_widgets  = []
        reg = REGISTRY.get(descriptor.type, {})
        self._header.config(text=f"{descriptor.id}  ({descriptor.type})")
        self._populate_props(descriptor, reg)
        self._populate_events(descriptor, reg)

    def load_form(self, form: FormModel) -> None:
        """Show form-level properties when the canvas background is selected."""
        self._dismiss_editor()
        self._current_widget = None
        self._multi_widgets  = []
        self._header.config(text=f"{form.name}  (Form)")

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
        self._header.config(text=f"{len(descriptors)} widgets selected")
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
        self._header.config(text="Properties")
        self._props_tree.delete(*self._props_tree.get_children())
        self._events_tree.delete(*self._events_tree.get_children())

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
        # Widget-specific props (default order from registry, then any extras)
        defaults = reg.get("default_props", {})
        color_props = reg.get("color_props", [])
        seen: set[str] = set()
        for key in list(defaults) + [k for k in d.props if k not in defaults]:
            if key in seen:
                continue
            seen.add(key)
            val = d.props.get(key, defaults.get(key, ""))
            self._props_tree.insert("", "end", iid=f"prop__{key}",
                                    text=key, values=(_display(val),))
        # Color props — always show even when not set, apply swatches
        for key in color_props:
            if key in seen:
                # Already inserted above — just apply swatch if value is set
                val = d.props.get(key, "")
            else:
                val = d.props.get(key, "")
                self._props_tree.insert("", "end", iid=f"prop__{key}",
                                        text=key, values=(val,))
                seen.add(key)
            if val:
                self._apply_color_swatch(f"prop__{key}", val.upper())
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
        for ev in reg.get("events", []):
            handler = d.events.get(ev, "")
            self._events_tree.insert("", "end", iid=f"ev__{ev}",
                                     text=ev, values=(handler,))

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
        return key in REGISTRY.get(d.type, {}).get("color_props", [])

    def _open_dropdown(self, tree: ttk.Treeview, row: str, col: str,
                       values: list[str], commit_fn) -> None:
        self._dismiss_editor()
        bbox = tree.bbox(row, col)
        if not bbox:
            return
        x, y, w, h = bbox
        combo = ttk.Combobox(tree, values=values, state="readonly",
                             font=("TkDefaultFont", 8))
        current = tree.set(row, col)
        combo.set(current if current in values else values[0])
        combo.place(x=x, y=y, width=w, height=h)
        self._entry_editor = combo

        def commit(_=None):
            val = combo.get()
            self._dismiss_editor()
            tree.set(row, col, val)
            commit_fn(row, val)

        combo.bind("<<ComboboxSelected>>", commit)
        combo.bind("<FocusOut>",           commit)
        combo.bind("<Escape>",             lambda _: self._dismiss_editor())
        tree.after_idle(combo.focus_force)

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

    def _apply_color_swatch(self, row_iid: str, color: str) -> None:
        """Tint the treeview row to preview the color."""
        try:
            tag = f"swatch:{row_iid}"
            fg  = _contrast_color(color)
            self._props_tree.tag_configure(tag, background=color, foreground=fg)
            self._props_tree.item(row_iid, tags=(tag,))
        except Exception:
            pass

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
                # Restore original if invalid
                self._props_tree.set(row_iid, "#1", d.id)
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
