from __future__ import annotations

"""
FormModel → Python source generator.

generate(form, event_bodies) is the main entry point.
event_bodies comes from persistence.extract_event_bodies() and lets
regeneration preserve any code the user wrote inside event stubs.
"""

import textwrap
from typing import Any

from .model import FormModel, WidgetDescriptor
from .registry import REGISTRY

# tkinter binding string for each event key
_BINDINGS: dict[str, str] = {
    "click":       "<Button-1>",
    "dblclick":    "<Double-Button-1>",
    "rightclick":  "<Button-3>",
    "mousedown":   "<ButtonPress>",
    "mouseup":     "<ButtonRelease>",
    "mousemove":   "<Motion>",
    "mouseenter":  "<Enter>",
    "mouseleave":  "<Leave>",
    "focusin":     "<FocusIn>",
    "focusout":    "<FocusOut>",
    "keypress":    "<KeyPress>",
    "keydown":     "<KeyPress>",
    "keyup":       "<KeyRelease>",
    "change":        "<<Modified>>",
    "comboselected": "<<ComboboxSelected>>",
    "listselect":    "<<ListboxSelect>>",
}

_STUB    = "pass  # TODO"
_MENUBAR = 20  # menu bar strip height in canvas coords (matches canvas._MENUBAR)

# Props that are optional — skip codegen when value is empty string
_SKIP_IF_EMPTY = {"show", "font", "justify", "relief", "borderwidth", "insertbackground"}

# IDOL marker lines — must contain the tokens persistence.py detects
_IMPORT_B = "# ── IDOL:IMPORTS:BEGIN " + "─" * 49
_IMPORT_E = "# ── IDOL:IMPORTS:END "   + "─" * 51
_INIT_B   = "        # ── IDOL:BEGIN " + "─" * 55
_INIT_E   = "        # ── IDOL:END "   + "─" * 57


# ── Public API ────────────────────────────────────────────────────────────────

def generate(form: FormModel, event_bodies: dict[str, str] | None = None,
             pre_init: str = "", post_init: str = "", helpers: str = "",
             user_imports: str = "",
             event_signatures: dict[str, tuple[str, str]] | None = None) -> str:
    """Return Python source for *form*.

    event_bodies: {method_name: dedented_body_str} — user event handler code.
    pre_init:     user code placed between form setup and self._build_ui().
    post_init:    user code placed after self._build_ui().
    helpers:      full source of public helper methods (user-written).
    """
    bodies = event_bodies or {}
    sigs   = event_signatures or {}
    needs_ttk = _uses_ttk(form)

    out: list[str] = []

    # ── imports ───────────────────────────────────────────────────────────────
    out.append("import tkinter as tk")
    if needs_ttk:
        out.append("from tkinter import ttk")
    out.append(_IMPORT_B)
    if user_imports:
        for line in user_imports.splitlines():
            out.append(line)
    else:
        out.append("# Add your imports here")
    out.append(_IMPORT_E)
    out += ["", ""]

    # ── class header ──────────────────────────────────────────────────────────
    base = "tk.Tk" if form.form_type == "main" else "tk.Toplevel"
    out.append(f"class {form.name}({base}):")
    out.append("    def __init__(self):")

    # Generated form-setup block (includes variable declarations)
    out.append(_INIT_B)
    out.append("        super().__init__()")
    out.append(f'        self.title("{form.title}")')
    geom_h = form.height - (_MENUBAR if form.menu_items else 0)
    out.append(f'        self.geometry("{form.width}x{geom_h}")')
    if form.border_style == "none":
        out.append("        self.overrideredirect(True)")
    elif form.border_style == "fixed" or not form.maximize_box:
        out.append("        self.resizable(False, False)")
    if form.bg:
        out.append(f'        self.configure(bg="{form.bg}")')
    for line in _variable_decls(form):
        out.append(line)
    for line in _menu_variable_decls(form.menu_items):
        out.append(line)
    out.append(_INIT_E)
    out.append("")

    # User pre-build zone
    if pre_init:
        for line in pre_init.splitlines():
            out.append(("        " + line) if line.strip() else "")
        out.append("")

    # Generated _build_ui call block
    out.append(_INIT_B)
    out.append("        self._build_ui()")
    out.append(_INIT_E)
    out.append("")

    # User post-build zone
    if post_init:
        for line in post_init.splitlines():
            out.append(("        " + line) if line.strip() else "")
        out.append("")

    # ── _build_ui ─────────────────────────────────────────────────────────────
    out.append("    def _build_ui(self):")
    if not form.widgets and not form.menu_items:
        out.append(f"        {_STUB}")
    else:
        if form.menu_items:
            out.extend(_menu_lines(form.menu_items))
            bind_lines = _menu_bind_lines(form.menu_items)
            if bind_lines:
                out.append("")
                out.extend(bind_lines)
            out.append("")
        y_offset = _MENUBAR if form.menu_items else 0
        for w in form.widgets:
            out.extend(_widget_lines(w, y_offset=y_offset))
            out.append("")

    # ── event methods ─────────────────────────────────────────────────────────
    methods = _collect_methods(form)
    if methods:
        out.append("    # ── Events " + "─" * 63)
        out.append("")
        for name in methods:
            params, ret = sigs.get(name, ("*args", ""))
            ret_str = f" -> {ret}" if ret else ""
            out.append(f"    def {name}(self, {params}){ret_str}:")
            out.extend(_body_lines(name, bodies))
            out.append("")

    # ── helper methods ────────────────────────────────────────────────────────
    out.append("    # ── Functions " + "─" * 59)
    out.append("")
    if helpers:
        for line in helpers.splitlines():
            out.append(("    " + line) if line.strip() else "")
    else:
        out.append("    # Methods defined here are preserved across code generation.")
    out.append("")

    # ── entry point ───────────────────────────────────────────────────────────
    out += ["", f'if __name__ == "__main__":',
            f"    app = {form.name}()", "    app.mainloop()", ""]

    return "\n".join(out)


# ── Internals ─────────────────────────────────────────────────────────────────

def _uses_ttk(form: FormModel) -> bool:
    return any(
        REGISTRY.get(w.type, {}).get("tk_class", "").startswith("ttk.")
        for w in form.widgets
    )


def _prop_str(key: str, val: Any) -> str:
    """Format one kwarg for the widget constructor."""
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'{key}="{escaped}"'
    if isinstance(val, bool):
        return f"{key}={val}"
    if isinstance(val, (int, float)):
        return f"{key}={val}"
    # list / tuple / other — safe repr
    return f"{key}={repr(val)}"


def _widget_lines(w: WidgetDescriptor, y_offset: int = 0) -> list[str]:
    reg = REGISTRY.get(w.type)
    if not reg:
        return [f"        # Unknown widget type: {w.type}"]

    tk_class = reg["tk_class"]
    scrollbar = w.props.get("scrollbar", "None")
    use_vsb = scrollbar in ("Vertical", "Both")
    use_hsb = scrollbar in ("Horizontal", "Both")
    use_scrollbar = use_vsb or use_hsb

    # Build ordered kwargs: props first, then variable binding, then command
    _color_props = set(reg.get("color_props", []))
    _state_color_props = {
        c for clist in reg.get("state_color_props", {}).values() for c in clist
    }
    _all_color_props = _color_props | _state_color_props
    _vcmd_keys = {"validatecommand", "invalidcommand"}
    _list_insert_props = set(reg.get("list_insert_props", []))
    kw_parts: list[str] = []
    for k, v in w.props.items():
        if k == "scrollbar":
            continue  # structural prop — handled below, not a tkinter kwarg
        if k in _all_color_props and v == "":
            continue
        if k in _SKIP_IF_EMPTY and (v == "" or v == ()):
            continue
        if k == "state" and v == "normal":
            continue
        if k == "validate" and v == "none":
            continue
        if k == "vcmd_args":
            continue  # consumed when building validatecommand/invalidcommand
        if k in _list_insert_props:
            continue  # emitted as insert() calls after place()
        if reg.get("colorize_prop") and k in ("colorize", "colorize_altbg"):
            continue  # handled as itemconfigure loop after place()
        if k in _vcmd_keys:
            if v:
                args_raw = w.props.get("vcmd_args", "%P")
                arg_str = ", ".join(f"'{a.strip()}'" for a in args_raw.split(","))
                kw_parts.append(f"{k}=(self.register(self.{v}), {arg_str})")
            continue
        kw_parts.append(_prop_str(k, v))

    if w.variable:
        var_kwarg = reg.get("variable_prop", "textvariable")
        kw_parts.append(f"{var_kwarg}=self.{w.variable.name}")

    # command event → kwarg (all command-capable widgets)
    # Prefer explicit "command" key; fall back to Button's "click" legacy mapping.
    command_method = w.events.get("command") or (
        w.events.get("click") if w.type == "Button" else None
    )
    if command_method:
        kw_parts.append(f"command=self.{command_method}")

    original_parent = f"self.{w.parent_id}" if w.parent_id else "self"
    place_y = w.y if w.parent_id else w.y - y_offset
    lines: list[str] = []

    if use_scrollbar:
        # Wrap in a Frame so scrollbar(s) and widget pack cleanly inside it
        frame_id = f"self.{w.id}_frame"
        lines.append(f"        {frame_id} = tk.Frame({original_parent})")
        lines.append(
            f"        {frame_id}.place(x={w.x}, y={place_y},"
            f" width={w.width}, height={w.height})"
        )
        if use_vsb:
            lines.append(
                f"        self.{w.id}_vsb = ttk.Scrollbar({frame_id}, orient='vertical')"
            )
        if use_hsb:
            lines.append(
                f"        self.{w.id}_hsb = ttk.Scrollbar({frame_id}, orient='horizontal')"
            )
        if use_vsb:
            kw_parts.append(f"yscrollcommand=self.{w.id}_vsb.set")
        if use_hsb:
            kw_parts.append(f"xscrollcommand=self.{w.id}_hsb.set")
        kw_str = (", " + ", ".join(kw_parts)) if kw_parts else ""
        lines.append(f"        self.{w.id} = {tk_class}({frame_id}{kw_str})")
        if use_vsb:
            lines.append(f"        self.{w.id}_vsb.config(command=self.{w.id}.yview)")
        if use_hsb:
            lines.append(f"        self.{w.id}_hsb.config(command=self.{w.id}.xview)")
        if use_vsb:
            lines.append(f"        self.{w.id}_vsb.pack(side='right', fill='y')")
        if use_hsb:
            lines.append(f"        self.{w.id}_hsb.pack(side='bottom', fill='x')")
        lines.append(f"        self.{w.id}.pack(side='left', fill='both', expand=True)")
    else:
        kw_str = (", " + ", ".join(kw_parts)) if kw_parts else ""
        lines.append(f"        self.{w.id} = {tk_class}({original_parent}{kw_str})")
        lines.append(
            f"        self.{w.id}.place(x={w.x}, y={place_y},"
            f" width={w.width}, height={w.height})"
        )

    # list_insert_props — populate widget with insert() calls after place()/pack()
    for prop_key in reg.get("list_insert_props", []):
        vals = w.props.get(prop_key, [])
        if vals:
            lines.append(f"        for _item in {repr(vals)}:")
            lines.append(f"            self.{w.id}.insert(tk.END, _item)")

    # Alternate-row colorize
    if w.props.get("colorize"):
        alt_bg = w.props.get("colorize_altbg", "")
        if alt_bg:
            lines.append(f"        for i in range(0, self.{w.id}.size(), 2):")
            lines.append(f'            self.{w.id}.itemconfigure(i, background="{alt_bg}")')

    # .bind() for every wired event — skip keys handled as constructor kwargs
    for event_key, method_name in w.events.items():
        if event_key == "command":
            continue
        if w.type == "Button" and event_key == "click":
            continue
        binding = _BINDINGS.get(event_key)
        if binding and method_name:
            lines.append(
                f'        self.{w.id}.bind("{binding}", self.{method_name})'
            )

    return lines


def _collect_methods(form: FormModel) -> list[str]:
    """All unique event/validate method names across the form, in widget order."""
    seen: set[str] = set()
    methods: list[str] = []
    for w in form.widgets:
        for method_name in w.events.values():
            if method_name and method_name not in seen:
                seen.add(method_name)
                methods.append(method_name)
        for key in ("validatecommand", "invalidcommand"):
            method_name = w.props.get(key, "")
            # Only stub underscore-prefixed names; public names live in the
            # Functions section and are preserved by extract_helper_methods.
            if method_name and method_name.startswith("_") and method_name not in seen:
                seen.add(method_name)
                methods.append(method_name)
    for method_name in _menu_command_methods(form.menu_items):
        if method_name not in seen:
            seen.add(method_name)
            methods.append(method_name)
    return methods


def _menu_command_methods(items) -> list[str]:
    """Return the _click method names that _menu_lines will wire as commands."""
    methods: list[str] = []
    for i, item in enumerate(items):
        if not item.name or item.caption == "-" or item.indent == 0:
            continue
        if item.kind in ("checkbutton", "radiobutton"):
            if item.command_handler:
                methods.append(f"_{item.command_handler}_click")
            continue
        # Cascade items (those that have direct children) get no command
        is_cascade = any(
            items[j].indent == item.indent + 1
            for j in range(i + 1, len(items))
            if items[j].indent <= item.indent + 1
        )
        if not is_cascade:
            methods.append(f"_{item.name}_click")
    return methods


def _menu_variable_decls(items) -> list[str]:
    """Return self.xxx = tk.BooleanVar()/StringVar() lines for menu check/radiobutton items."""
    seen: set[str] = set()
    lines: list[str] = []
    for item in items:
        if not item.variable or item.variable in seen:
            continue
        if item.kind == "checkbutton":
            seen.add(item.variable)
            lines.append(f"        self.{item.variable} = tk.BooleanVar()")
        elif item.kind == "radiobutton":
            seen.add(item.variable)
            lines.append(f"        self.{item.variable} = tk.StringVar()")
    return lines


def _variable_decls(form: FormModel) -> list[str]:
    """Return 8-space-indented self.name = tk.VarType(...) lines, deduplicated."""
    seen: set[str] = set()
    lines: list[str] = []
    for w in form.widgets:
        vb = w.variable
        if vb is None or vb.name in seen:
            continue
        seen.add(vb.name)
        if vb.initial:
            val = _prop_str("value", _coerce_initial(vb.var_type, vb.initial))
            lines.append(f"        self.{vb.name} = tk.{vb.var_type}({val})")
        else:
            lines.append(f"        self.{vb.name} = tk.{vb.var_type}()")
    return lines


def _coerce_initial(var_type: str, initial: str):
    """Convert the initial-value string to the right Python type for codegen."""
    if var_type == "IntVar":
        try:
            return int(initial)
        except ValueError:
            return 0
    if var_type == "DoubleVar":
        try:
            return float(initial)
        except ValueError:
            return 0.0
    if var_type == "BooleanVar":
        return initial.strip().lower() in ("true", "1", "yes")
    return initial  # StringVar — keep as string


def _menu_lines(items) -> list[str]:
    """Generate _build_ui lines for a tk.Menu hierarchy from MenuItemDescriptor list."""
    from .model import MenuItemDescriptor  # local import avoids circular at module level
    lines: list[str] = []
    lines.append("        self._menu_bar = tk.Menu(self)")
    lines.append("        self.configure(menu=self._menu_bar)")

    # Stack tracks (indent_level, var_name) of open cascade menus
    # index 0 = top-level bar, index 1+ = sub-menus
    stack: list[str] = ["self._menu_bar"]

    for item in items:
        # Ensure stack depth matches item indent (indent 0 = child of bar = stack depth 1)
        target_depth = item.indent + 1
        # Trim stack if we've gone back up
        while len(stack) > target_depth:
            stack.pop()

        parent = stack[-1]
        disabled = "" if item.enabled else ', state="disabled"'

        if item.caption == "-":
            lines.append(f"        {parent}.add_separator()")
            continue

        label = item.display_caption.replace('"', '\\"')
        name  = item.name or ""
        ul    = f", underline={item.underline_index}" if item.underline_index >= 0 else ""

        # Check if any later item is a direct child of this one (i.e. it's a cascade)
        idx = items.index(item)
        is_cascade = any(
            items[j].indent == item.indent + 1
            for j in range(idx + 1, len(items))
            if items[j].indent <= item.indent + 1
        )

        if item.indent == 0:
            # Top-level: always a cascade on the menu bar
            var = f"self._m_{name}" if name else f"self._menu_bar_menu{idx}"
            lines.append(f"        {var} = tk.Menu({parent}, tearoff=0)")
            lines.append(f'        {parent}.add_cascade(label="{label}", menu={var}{ul}{disabled})')
            stack.append(var)
        elif is_cascade:
            # Sub-menu item that has children — emit as cascade
            var = f"self._m_{name}" if name else f"self._submenu{idx}"
            lines.append(f"        {var} = tk.Menu({parent}, tearoff=0)")
            lines.append(f'        {parent}.add_cascade(label="{label}", menu={var}{ul}{disabled})')
            stack.append(var)
        elif item.kind == "checkbutton":
            vvar = f", variable=self.{item.variable}" if item.variable else ""
            cmd  = f", command=self._{item.command_handler}_click" if item.command_handler else ""
            sc   = f', accelerator="{item.shortcut}"' if item.shortcut else ""
            lines.append(f'        {parent}.add_checkbutton(label="{label}"{vvar}{cmd}{sc}{ul}{disabled})')
        elif item.kind == "radiobutton":
            vvar = f", variable=self.{item.variable}" if item.variable else ""
            val  = f', value="{item.value}"' if item.value else ""
            cmd  = f", command=self._{item.command_handler}_click" if item.command_handler else ""
            sc   = f', accelerator="{item.shortcut}"' if item.shortcut else ""
            lines.append(f'        {parent}.add_radiobutton(label="{label}"{vvar}{val}{cmd}{sc}{ul}{disabled})')
        else:
            # Leaf command
            cmd = f", command=self._{name}_click" if name else ""
            sc  = f', accelerator="{item.shortcut}"' if item.shortcut else ""
            lines.append(f'        {parent}.add_command(label="{label}"{cmd}{sc}{ul}{disabled})')

    return lines


_SHORTCUT_SPECIAL = {"Del": "Delete", "Ins": "Insert"}
_SHORTCUT_MODS    = {"Ctrl": "Control", "Alt": "Alt", "Shift": "Shift"}

def _shortcut_to_event(shortcut: str) -> str | None:
    """Convert 'Ctrl+S' → '<Control-s>', 'F5' → '<F5>', 'Del' → '<Delete>', etc."""
    if not shortcut:
        return None
    parts = shortcut.split("+")
    key = parts[-1]
    key_mapped = _SHORTCUT_SPECIAL.get(key, key)
    if len(parts) == 1:
        # bare key: F-keys stay as-is, everything else lowercased
        if not key_mapped.startswith("F") or not key_mapped[1:].isdigit():
            key_mapped = key_mapped.lower()
        return f"<{key_mapped}>"
    mods = "-".join(_SHORTCUT_MODS.get(m, m) for m in parts[:-1])
    # letter keys go lowercase; F-keys and specials keep their case
    if len(key_mapped) == 1:
        key_mapped = key_mapped.lower()
    return f"<{mods}-{key_mapped}>"


def _menu_bind_lines(items) -> list[str]:
    """Generate self.bind(...) lines for menu items that have both a shortcut and a handler."""
    lines: list[str] = []
    for i, item in enumerate(items):
        if not item.shortcut or item.caption == "-" or item.indent == 0:
            continue
        # Determine the handler name
        if item.kind in ("checkbutton", "radiobutton"):
            handler = item.command_handler
        else:
            # Skip cascade items
            is_cascade = any(
                items[j].indent == item.indent + 1
                for j in range(i + 1, len(items))
                if items[j].indent <= item.indent + 1
            )
            handler = item.name if not is_cascade else ""
        if not handler:
            continue
        event = _shortcut_to_event(item.shortcut)
        if event:
            lines.append(f'        self.bind("{event}", self._{handler}_click)')
    return lines


def _body_lines(method_name: str, bodies: dict[str, str]) -> list[str]:
    """Return the 8-space-indented body lines for one event method."""
    raw = bodies.get(method_name, "").strip()
    if not raw or raw in (_STUB, "pass"):
        return [f"        {_STUB}"]
    # Re-indent each line to method body level (8 spaces)
    result: list[str] = []
    for line in textwrap.dedent(raw).splitlines():
        result.append(("        " + line) if line.strip() else "")
    return result or [f"        {_STUB}"]
