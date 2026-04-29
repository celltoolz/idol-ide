from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Any, Callable, Optional

from designer.model import FormModel, WidgetDescriptor
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
        self._current_widget: WidgetDescriptor | None = None
        self._entry_editor:   tk.Entry | None = None
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
        reg = REGISTRY.get(descriptor.type, {})
        self._header.config(text=f"{descriptor.id}  ({descriptor.type})")
        self._populate_props(descriptor, reg)
        self._populate_events(descriptor, reg)

    def load_form(self, form: FormModel) -> None:
        """Show form-level properties when the canvas background is selected."""
        self._dismiss_editor()
        self._current_widget = None
        self._header.config(text=f"{form.name}  (Form)")

        self._props_tree.delete(*self._props_tree.get_children())
        for key, label, val in [
            ("title",       "title",       form.title),
            ("width",       "width",       form.width),
            ("height",      "height",      form.height),
            ("resizable_x", "resizable_x", form.resizable_x),
            ("resizable_y", "resizable_y", form.resizable_y),
            ("bg",          "background",  form.bg),
        ]:
            self._props_tree.insert("", "end", iid=f"form__{key}",
                                    text=label, values=(str(val),))
        # Tint the background row with the current color
        self._apply_color_swatch("form__bg", form.bg or "#f5f5f5")

        self._events_tree.delete(*self._events_tree.get_children())
        for ev in ("load", "activate", "deactivate", "unload"):
            self._events_tree.insert("", "end", iid=f"form_ev__{ev}",
                                     text=ev, values=("",))

    def clear(self) -> None:
        """Reset to the empty / no-selection state."""
        self._dismiss_editor()
        self._current_widget = None
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
        # Geometry first
        for key in ("x", "y", "width", "height"):
            self._props_tree.insert("", "end", iid=f"geo__{key}",
                                    text=key, values=(str(getattr(d, key)),))
        # Widget-specific props (default order from registry, then any extras)
        defaults = reg.get("default_props", {})
        seen: set[str] = set()
        for key in list(defaults) + [k for k in d.props if k not in defaults]:
            if key in seen:
                continue
            seen.add(key)
            val = d.props.get(key, defaults.get(key, ""))
            self._props_tree.insert("", "end", iid=f"prop__{key}",
                                    text=key, values=(_display(val),))

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
        if row == "form__bg":
            self._open_color_picker(row)
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

    def _open_color_picker(self, row_iid: str) -> None:
        """Open a color picker for a color property cell."""
        current = self._props_tree.set(row_iid, "#1").strip() or "#ffffff"
        try:
            from tkcolorpicker import askcolor
            color = askcolor(current, self._props_tree.winfo_toplevel())[1]
        except Exception:
            from tkinter.colorchooser import askcolor as _fallback
            result = _fallback(current, parent=self._props_tree.winfo_toplevel())
            color = result[1] if result else None
        if not color:
            return
        color = color.lower()
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
