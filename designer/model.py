from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class VariableBinding:
    """A tkinter variable (StringVar/IntVar/DoubleVar/BooleanVar) bound to a widget."""
    name:     str   # attribute name on self, e.g. "result_var" → self.result_var
    var_type: str   # "StringVar" | "IntVar" | "DoubleVar" | "BooleanVar"
    initial:  str   # initial value as a string; "" = use tkinter default

    def to_dict(self) -> dict:
        return {"name": self.name, "var_type": self.var_type, "initial": self.initial}

    @staticmethod
    def from_dict(d: dict) -> "VariableBinding":
        return VariableBinding(
            name=d.get("name", ""),
            var_type=d.get("var_type", "StringVar"),
            initial=d.get("initial", ""),
        )


@dataclass
class WidgetDescriptor:
    """Canonical description of one widget on the canvas."""
    id: str                              # e.g. "btn_submit"
    type: str                            # registry key, e.g. "Button"
    x: int = 0
    y: int = 0
    width: int = 100
    height: int = 30
    props: dict[str, Any] = field(default_factory=dict)    # text, bg, fg, font, ...
    events: dict[str, str] = field(default_factory=dict)   # {"click": "_btn_submit_click"}
    variable: VariableBinding | None = field(default=None) # optional tkinter variable
    parent_id: str | None = field(default=None)            # Frame/LabelFrame container, or None = form

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id,
            "type": self.type,
            "x": self.x,
            "y": self.y,
            "width": self.width,
            "height": self.height,
            "props": dict(self.props),
            "events": dict(self.events),
        }
        if self.variable is not None:
            d["variable"] = self.variable.to_dict()
        if self.parent_id is not None:
            d["parent_id"] = self.parent_id
        return d

    @staticmethod
    def from_dict(d: dict) -> "WidgetDescriptor":
        var_data = d.get("variable")
        return WidgetDescriptor(
            id=d["id"],
            type=d["type"],
            x=d.get("x", 0),
            y=d.get("y", 0),
            width=d.get("width", 100),
            height=d.get("height", 30),
            props=d.get("props", {}),
            events=d.get("events", {}),
            variable=VariableBinding.from_dict(var_data) if var_data else None,
            parent_id=d.get("parent_id", None),
        )


@dataclass
class MenuItemDescriptor:
    """One row in the Menu Editor — a top-level menu, menu item, or separator."""
    caption:  str  = ""     # display text; "-" = separator line
    name:     str  = ""     # code identifier, e.g. "open_form2"
    indent:   int  = 0      # 0 = top-level cascade, 1 = item/separator, 2 = sub-item
    enabled:  bool = True
    visible:  bool = True
    shortcut: str  = ""
    kind:            str  = "command"  # "command" | "checkbutton" | "radiobutton"
    variable:        str  = ""         # variable attribute name for check/radiobutton
    value:           str  = ""         # radiobutton value string
    command_handler: str  = ""         # optional command handler name for check/radiobutton

    @property
    def display_caption(self) -> str:
        """Caption with the & access-key marker stripped for display."""
        idx = self.caption.find("&")
        if idx == -1 or idx >= len(self.caption) - 1:
            return self.caption
        return self.caption[:idx] + self.caption[idx + 1:]

    @property
    def underline_index(self) -> int:
        """0-based index of the underlined character, or -1 if none."""
        idx = self.caption.find("&")
        if idx == -1 or idx >= len(self.caption) - 1:
            return -1
        return idx

    def to_dict(self) -> dict:
        return {
            "caption":  self.caption,
            "name":     self.name,
            "indent":   self.indent,
            "enabled":  self.enabled,
            "visible":  self.visible,
            "shortcut": self.shortcut,
            "kind":            self.kind,
            "variable":        self.variable,
            "value":           self.value,
            "command_handler": self.command_handler,
        }

    @staticmethod
    def from_dict(d: dict) -> "MenuItemDescriptor":
        return MenuItemDescriptor(
            caption  = d.get("caption",  ""),
            name     = d.get("name",     ""),
            indent   = d.get("indent",   0),
            enabled  = d.get("enabled",  True),
            visible  = d.get("visible",  True),
            shortcut = d.get("shortcut", ""),
            kind            = d.get("kind",            "command"),
            variable        = d.get("variable",        ""),
            value           = d.get("value",           ""),
            command_handler = d.get("command_handler", ""),
        )


@dataclass
class FormModel:
    """Canonical description of one form (one .form.json / one generated .py)."""
    name: str = "Form1"
    title: str = "Form1"
    width: int = 800
    height: int = 600
    border_style: str = "sizable"         # "sizable" | "fixed" | "none"
    maximize_box: bool = True
    bg: str = ""                         # "" = system default
    form_type:  str = "main"              # "main" (tk.Tk) | "dialog" (tk.Toplevel, v2)
    widgets:    list[WidgetDescriptor]    = field(default_factory=list)
    menu_items: list[MenuItemDescriptor]  = field(default_factory=list)
    form_events: dict[str, str]           = field(default_factory=dict)  # {ev_key: method_name}

    # ── widget lookup helpers ──────────────────────────────────────────────────

    def get_widget(self, widget_id: str) -> WidgetDescriptor | None:
        for w in self.widgets:
            if w.id == widget_id:
                return w
        return None

    def add_widget(self, widget: WidgetDescriptor) -> None:
        self.widgets.append(widget)

    def remove_widget(self, widget_id: str) -> bool:
        before = len(self.widgets)
        self.widgets = [w for w in self.widgets if w.id != widget_id]
        return len(self.widgets) < before

    def next_id(self, type_key: str) -> str:
        """Generate the next unique id for a widget type, e.g. 'btn3'."""
        prefix = _ID_PREFIXES.get(type_key, type_key.lower())
        existing = {w.id for w in self.widgets}
        n = 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

    # ── serialization ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "border_style": self.border_style,
            "maximize_box": self.maximize_box,
            "bg": self.bg,
            "form_type": self.form_type,
            "widgets":    [w.to_dict() for w in self.widgets],
            "menu_items": [m.to_dict() for m in self.menu_items],
            "form_events": dict(self.form_events),
        }

    @staticmethod
    def from_dict(d: dict) -> "FormModel":
        # Migrate legacy resizable_x/resizable_y to border_style
        if "border_style" not in d:
            rx = d.get("resizable_x", True)
            ry = d.get("resizable_y", True)
            border_style = "sizable" if (rx and ry) else "fixed"
        else:
            border_style = d["border_style"]
        return FormModel(
            name=d.get("name", "Form1"),
            title=d.get("title", "Form1"),
            width=d.get("width", 800),
            height=d.get("height", 600),
            border_style=border_style,
            maximize_box=d.get("maximize_box", True),
            bg=d.get("bg", ""),
            form_type=d.get("form_type", "main"),
            widgets    =[WidgetDescriptor.from_dict(w)    for w in d.get("widgets",    [])],
            menu_items =[MenuItemDescriptor.from_dict(m)  for m in d.get("menu_items", [])],
            form_events=dict(d.get("form_events", {})),
        )


# Short id prefixes per widget type
_ID_PREFIXES: dict[str, str] = {
    "Button":      "btn",
    "Label":       "lbl",
    "Entry":       "ent",
    "Text":        "txt",
    "Checkbutton": "chk",
    "Radiobutton": "rad",
    "Combobox":    "cmb",
    "Listbox":     "lst",
    "Frame":       "frm",
    "LabelFrame":  "lfr",
    "Scale":       "scl",
    "Spinbox":     "spn",
    "Progressbar": "prg",
    "Separator":   "sep",
}
