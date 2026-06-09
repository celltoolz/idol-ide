from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class CanvasItemDescriptor:
    """One item placed inside a tk.Canvas widget (create_image / create_rectangle / etc.)."""
    id: str            # e.g. "ci_img1", "ci_rect1" — scoped per canvas widget
    kind: str          # "image" | "rectangle" | "oval" | "text" | "line"
    x: int = 0
    y: int = 0
    width: int = 64    # bounding box width (line: x-endpoint offset from origin)
    height: int = 64   # bounding box height (line: y-endpoint offset from origin)
    tags: list[str] = field(default_factory=list)
    props: dict[str, Any] = field(default_factory=dict)          # fill, outline, image_path, text, font, …
    bindings: dict[str, str] = field(default_factory=dict)       # tk event str → method name
    binding_tags: dict[str, str] = field(default_factory=dict)   # tk event str → specific tag for tag_bind

    def to_dict(self) -> dict:
        d: dict = {
            "id": self.id, "kind": self.kind,
            "x": self.x, "y": self.y, "width": self.width, "height": self.height,
            "tags": list(self.tags),
            "props": dict(self.props),
            "bindings": dict(self.bindings),
        }
        if self.binding_tags:
            d["binding_tags"] = dict(self.binding_tags)
        return d

    @staticmethod
    def from_dict(d: dict) -> "CanvasItemDescriptor":
        return CanvasItemDescriptor(
            id=d.get("id", ""), kind=d.get("kind", "image"),
            x=d.get("x", 0), y=d.get("y", 0),
            width=d.get("width", 64), height=d.get("height", 64),
            tags=list(d.get("tags", [])),
            props=dict(d.get("props", {})),
            bindings=dict(d.get("bindings", {})),
            binding_tags=dict(d.get("binding_tags", {})),
        )


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
    # Resize anchor — one of: "" | "top_left" | "top" | "top_right" | "left" | "all"
    #                         | "right" | "bottom_left" | "bottom" | "bottom_right"
    anchor: str = ""
    # For children of a Notebook widget: the tab name this widget belongs to
    tab: str = ""
    # Canvas items placed inside this widget (only used when type == "Canvas")
    canvas_items: list[CanvasItemDescriptor] = field(default_factory=list)

    def next_item_id(self, kind: str) -> str:
        """Generate the next unique canvas item id, e.g. 'ci_img1'."""
        _KIND_PREFIXES = {
            "image": "ci_img", "rectangle": "ci_rect", "oval": "ci_oval",
            "text": "ci_text", "line": "ci_line",
        }
        prefix = _KIND_PREFIXES.get(kind, f"ci_{kind}")
        existing = {ci.id for ci in self.canvas_items}
        n = 1
        while f"{prefix}{n}" in existing:
            n += 1
        return f"{prefix}{n}"

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
        if self.anchor:
            d["anchor"] = self.anchor
        if self.tab:
            d["tab"] = self.tab
        if self.canvas_items:
            d["canvas_items"] = [ci.to_dict() for ci in self.canvas_items]
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
            anchor=d.get("anchor", ""),
            tab=d.get("tab", ""),
            canvas_items=[CanvasItemDescriptor.from_dict(ci) for ci in d.get("canvas_items", [])],
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
class HandlerWire:
    """One connection between a form handler and either a built-in target or a widget event."""
    handler_id: str   # e.g. "_on_escape"
    widget_id:  str   # widget id for widget-event wires; "" for built-in (always_wired)
    event_key:  str   # e.g. "click"; for always_wired this mirrors display_target
    option:     str = ""  # selected option name, e.g. "hide", "toggle"

    def to_dict(self) -> dict:
        d: dict = {
            "handler_id": self.handler_id,
            "widget_id":  self.widget_id,
            "event_key":  self.event_key,
        }
        if self.option:
            d["option"] = self.option
        return d

    @staticmethod
    def from_dict(d: dict) -> "HandlerWire":
        return HandlerWire(
            handler_id=d.get("handler_id", ""),
            widget_id =d.get("widget_id",  ""),
            event_key =d.get("event_key",  ""),
            option    =d.get("option",     ""),
        )


@dataclass
class ComponentDescriptor:
    """A non-visual component placed in the component tray (e.g. Timer, FileDialog)."""
    id:    str        # "timer1"
    type:  str        # "Timer"
    props: dict[str, Any] = field(default_factory=dict)  # {"interval": 1000, "enabled": True}

    def to_dict(self) -> dict:
        return {"id": self.id, "type": self.type, "props": dict(self.props)}

    @staticmethod
    def from_dict(d: dict) -> "ComponentDescriptor":
        return ComponentDescriptor(
            id=d.get("id", ""),
            type=d.get("type", ""),
            props=dict(d.get("props", {})),
        )


@dataclass
class FormModel:
    """Canonical description of one form (one .form.json / one generated .py)."""
    name: str = "Form1"
    title: str = "Form1"
    width: int = 800
    height: int = 600
    border_style:   str  = "sizable"       # "sizable" | "fixed" | "none"
    maximize_box:   bool = True
    always_on_top:  bool = False
    bg: str = ""                         # "" = system default
    image: str = ""                      # relative path to background image, "" = none
    form_type:  str = "main"              # "main" (tk.Tk) | "dialog" (tk.Toplevel)
    widgets:    list[WidgetDescriptor]    = field(default_factory=list)
    menu_items: list[MenuItemDescriptor]  = field(default_factory=list)
    form_events: dict[str, str]           = field(default_factory=dict)  # {ev_key: method_name}
    linked_dialogs: list[str]             = field(default_factory=list)  # dialog names owned by this form
    enabled_handlers: list[str]           = field(default_factory=list)  # handler IDs from HANDLER_CATALOG
    components: list[ComponentDescriptor] = field(default_factory=list)  # non-visual tray components
    handler_wires:   list[HandlerWire]    = field(default_factory=list)  # explicit handler→widget-event wires
    handler_options: dict[str, str]       = field(default_factory=dict)  # {handler_id: option_name}

    # ── component lookup helpers ───────────────────────────────────────────────

    def get_component(self, comp_id: str) -> "ComponentDescriptor | None":
        for c in self.components:
            if c.id == comp_id:
                return c
        return None

    def next_component_id(self, default_name: str) -> str:
        """Generate the next unique id for a component type, e.g. 'timer1', 'timer2'."""
        existing = {c.id for c in self.components}
        n = 1
        while f"{default_name}{n}" in existing:
            n += 1
        return f"{default_name}{n}"

    # ── widget lookup helpers ──────────────────────────────────────────────────

    def get_widget(self, widget_id: str) -> WidgetDescriptor | None:
        for w in self.widgets:
            if w.id == widget_id:
                return w
        return None

    def get_menu_item(self, name: str) -> "MenuItemDescriptor | None":
        for m in self.menu_items:
            if m.name == name:
                return m
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

    def move_widget(self, widget_id: str, new_idx: int) -> bool:
        """Move widget to new_idx in the widgets list (tab/z order). Returns True if moved."""
        cur_idx = next((i for i, w in enumerate(self.widgets) if w.id == widget_id), None)
        if cur_idx is None:
            return False
        new_idx = max(0, min(new_idx, len(self.widgets) - 1))
        if cur_idx == new_idx:
            return False
        widget = self.widgets.pop(cur_idx)
        self.widgets.insert(new_idx, widget)
        return True

    # ── serialization ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:

        d: dict = {
            "name": self.name,
            "title": self.title,
            "width": self.width,
            "height": self.height,
            "border_style":  self.border_style,
            "maximize_box":  self.maximize_box,
            "always_on_top": self.always_on_top,
            "bg": self.bg,
            "form_type": self.form_type,
            "widgets":    [w.to_dict() for w in self.widgets],
            "menu_items": [m.to_dict() for m in self.menu_items],
            "form_events": dict(self.form_events),
        }
        if self.image:
            d["image"] = self.image
        if self.linked_dialogs:
            d["linked_dialogs"] = list(self.linked_dialogs)
        if self.enabled_handlers:
            d["enabled_handlers"] = list(self.enabled_handlers)
        if self.components:
            d["components"] = [c.to_dict() for c in self.components]
        if self.handler_wires:
            d["handler_wires"] = [w.to_dict() for w in self.handler_wires]
        if self.handler_options:
            d["handler_options"] = dict(self.handler_options)
        return d

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
            always_on_top=d.get("always_on_top", False),
            bg=d.get("bg", ""),
            image=d.get("image", ""),
            form_type=d.get("form_type", "main"),
            widgets       =[WidgetDescriptor.from_dict(w)    for w in d.get("widgets",    [])],
            menu_items    =[MenuItemDescriptor.from_dict(m)  for m in d.get("menu_items", [])],
            form_events   =dict(d.get("form_events", {})),
            linked_dialogs=list(d.get("linked_dialogs", [])),
            enabled_handlers=_load_enabled_handlers(d),
            components=[ComponentDescriptor.from_dict(c) for c in d.get("components", [])],
            handler_wires=[HandlerWire.from_dict(w) for w in d.get("handler_wires", [])],
            handler_options=dict(d.get("handler_options", {})),
        )


def _load_enabled_handlers(d: dict) -> list[str]:
    """Return enabled_handlers for a form dict, migrating old files that lack the key."""
    if "enabled_handlers" in d:
        return list(d["enabled_handlers"])
    # Old saved file — seed defaults based on form_type
    from designer.handlers import default_enabled_for
    return default_enabled_for(d.get("form_type", "main"))


# ── Canvas item ↔ WidgetDescriptor conversion ─────────────────────────────────

_CI_KIND_TO_TYPE = {
    "rectangle": "CanvasRect",
    "oval":      "CanvasOval",
    "text":      "CanvasText",
    "line":      "CanvasLine",
    "image":     "CanvasImage",
}
_CI_TYPE_TO_KIND = {v: k for k, v in _CI_KIND_TO_TYPE.items()}

# Logical event name → tk binding string for canvas items (subset of codegen._BINDINGS)
_CI_EVENT_TO_TK: dict[str, str] = {
    "click":      "<Button-1>",
    "dblclick":   "<Double-Button-1>",
    "rightclick": "<Button-3>",
    "mousedown":  "<ButtonPress>",
    "mouseup":    "<ButtonRelease>",
    "mousemove":  "<Motion>",
    "mouseenter": "<Enter>",
    "mouseleave": "<Leave>",
}
_CI_TK_TO_EVENT: dict[str, str] = {v: k for k, v in _CI_EVENT_TO_TK.items()}


def ci_to_widget(ci: "CanvasItemDescriptor") -> "WidgetDescriptor":
    """Convert a CanvasItemDescriptor to a WidgetDescriptor for sub-form editing."""
    props = dict(ci.props)
    props["_ci_tags"] = list(ci.tags)
    if ci.binding_tags:
        props["_ci_binding_tags"] = dict(ci.binding_tags)
    events = {_CI_TK_TO_EVENT[tk]: method
              for tk, method in ci.bindings.items()
              if tk in _CI_TK_TO_EVENT and method}
    return WidgetDescriptor(
        id=ci.id,
        type=_CI_KIND_TO_TYPE[ci.kind],
        x=ci.x, y=ci.y,
        width=ci.width, height=ci.height,
        props=props,
        events=events,
    )


def widget_to_ci(w: "WidgetDescriptor") -> "CanvasItemDescriptor":
    """Convert a WidgetDescriptor (from sub-form) back to a CanvasItemDescriptor."""
    props = dict(w.props)
    tags = props.pop("_ci_tags", [])
    binding_tags = props.pop("_ci_binding_tags", {})
    bindings = {_CI_EVENT_TO_TK[ev]: method
                for ev, method in w.events.items()
                if ev in _CI_EVENT_TO_TK and method}
    return CanvasItemDescriptor(
        id=w.id,
        kind=_CI_TYPE_TO_KIND[w.type],
        x=w.x, y=w.y,
        width=w.width, height=w.height,
        tags=list(tags),
        props=props,
        bindings=bindings,
        binding_tags=dict(binding_tags),
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
