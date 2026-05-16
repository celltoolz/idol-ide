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
    "tabchanged":    "<<NotebookTabChanged>>",
}

_STUB        = "pass  # TODO"
_MENUBAR     = 20  # menu bar strip height in canvas coords (matches canvas._MENUBAR)
_LF_LABEL_H  = 17  # LabelFrame label strip height (matches canvas._LF_LABEL_H)
_NB_TAB_H    = 26  # Notebook tab-strip height (matches canvas._NB_TAB_H)

# Anchors that change the widget's size (not just its position)
_SIZE_ANCHORS = {"all", "top", "bottom", "left", "right"}

# Form-level event defaults: {ev_key: (params, default_body)}
# params="" means no event argument (load/unload are direct callbacks, not .bind())
_FORM_EV_DEFAULTS: dict[str, tuple[str, str]] = {
    "load":       ("",      "pass  # TODO"),
    "activate":   ("event", "if event.widget is not self:\n    return\npass  # TODO"),
    "deactivate": ("event", "if event.widget is not self:\n    return\npass  # TODO"),
    "unload":     ("",      "self.destroy()"),
    "resize":     ("event", "if event.widget is not self:\n    return\npass  # TODO"),
}

# Props that are optional — skip codegen when value is empty string
_SKIP_IF_EMPTY = {
    "show", "font", "justify", "relief", "borderwidth", "insertbackground",
    "wraplength", "resolution", "tickinterval", "increment", "maximum",
    "char_width", "char_height", "onvalue", "offvalue", "labelanchor",
    "selectmode", "wrap", "exportselection", "values", "from_", "to",
}

# Props stored as "True"/"False" strings (dropdown) that must become Python booleans
_BOOL_PROPS = {"wrap", "exportselection"}

# Prop names that must be renamed when emitting constructor kwargs
_PROP_RENAMES = {"char_width": "width", "char_height": "height"}

# IDOL marker lines — must contain the tokens persistence.py detects
_IMPORT_B        = "# ── IDOL:IMPORTS:BEGIN "        + "─" * 49
_IMPORT_E        = "# ── IDOL:IMPORTS:END "          + "─" * 51
_DIALOG_IMPORT_B = "# ── IDOL:DIALOG_IMPORTS:BEGIN " + "─" * 10 + "(Do not modify below)" + "─" * 11
_DIALOG_IMPORT_E = "# ── IDOL:DIALOG_IMPORTS:END "   + "─" * 12 + "(Do not modify above)" + "─" * 11
_INIT_B          = "        # ── IDOL:BEGIN " + "─" * 21 + "(Do not modify below)" + "─" * 21
_INIT_E          = "        # ── IDOL:END "   + "─" * 23 + "(Do not modify above)" + "─" * 21


# ── Public API ────────────────────────────────────────────────────────────────

def generate(form: FormModel, event_bodies: dict[str, str] | None = None,
             pre_init: str = "", post_init: str = "", helpers: str = "",
             user_imports: str = "",
             event_signatures: dict[str, tuple[str, str]] | None = None,
             linked_dialogs: list[str] | None = None) -> str:
    """Return Python source for *form*.

    event_bodies:   {method_name: dedented_body_str} — user event handler code.
    pre_init:       user code placed between form setup and self._build_ui().
    post_init:      user code placed after self._build_ui().
    helpers:        full source of public helper methods (user-written).
    linked_dialogs: dialog class names owned by this form; generates _open_X methods.
    """
    bodies   = dict(event_bodies or {})
    sigs     = event_signatures or {}
    dialogs  = linked_dialogs or []
    needs_ttk = _uses_ttk(form)

    # Migrate old single-use opener bodies to the new instance-based pattern
    for _d in dialogs:
        _old = f"{_d}(self).deiconify()"
        if bodies.get(f"_open_{_d}", "").strip() == _old:
            del bodies[f"_open_{_d}"]

    # Resolve active handlers from catalog
    from designer.handlers import handlers_for, HANDLER_CATALOG
    _all_handler_ids = {h.id for h in HANDLER_CATALOG}
    _enabled = set(form.enabled_handlers) & _all_handler_ids
    _catalog  = {h.id: h for h in handlers_for(form.form_type)}
    active_handlers = [h for h in handlers_for(form.form_type) if h.id in _enabled]

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
    if dialogs:
        out.append(_DIALOG_IMPORT_B)
        for d in dialogs:
            out.append(f"from {d} import {d}")
        out.append(_DIALOG_IMPORT_E)
    out += ["", ""]

    # ── class header ──────────────────────────────────────────────────────────
    is_dialog = form.form_type != "main"
    base = "tk.Tk" if not is_dialog else "tk.Toplevel"
    out.append(f"class {form.name}({base}):")
    if is_dialog:
        out.append("    def __init__(self, parent, **kwargs):")
    else:
        out.append("    def __init__(self):")

    # Generated form-setup block (includes variable declarations)
    out.append(_INIT_B)
    if is_dialog:
        out.append("        super().__init__(parent, **kwargs)")
        out.append("        self.withdraw()")
    else:
        out.append("        super().__init__()")
    out.append(f'        self.title("{form.title}")')
    geom_h = form.height - (_MENUBAR if form.menu_items else 0)
    out.append(f'        self.geometry("{form.width}x{geom_h}")')
    if form.border_style == "none":
        out.append("        self.overrideredirect(True)")
    elif form.border_style == "fixed" or not form.maximize_box:
        out.append("        self.resizable(False, False)")
    if form.always_on_top:
        out.append('        self.attributes("-topmost", True)')
    if form.bg:
        out.append(f'        self.configure(bg="{form.bg}")')
    for line in _variable_decls(form):
        out.append(line)
    for line in _menu_variable_decls(form.menu_items):
        out.append(line)
    for d in dialogs:
        out.append(f"        self.dlg_{d} = {d}(self)")
    if dialogs:
        out.append("        self.focus()")
    out.append(_INIT_E)
    out.append("")

    # User pre-build zone
    if pre_init:
        for line in pre_init.splitlines():
            out.append(("        " + line) if line.strip() else "")
        out.append("")

    # Generated _build_ui call block + form event bindings
    _anchored = [w for w in form.widgets if w.anchor and w.anchor != "top_left"]
    out.append(_INIT_B)
    out.append("        self._build_ui()")
    for ev_key, method_name in form.form_events.items():
        if not method_name:
            continue
        binding_line = _form_event_binding(ev_key, method_name)
        if binding_line:
            out.append(f"        {binding_line}")
    if _anchored:
        out.append("        self.bind(\"<Configure>\", self._apply_anchor_layout)")
    for h in active_handlers:
        if h.wiring:
            out.append(f"        {h.wiring}")
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
            out.extend(_widget_lines(w, y_offset=y_offset, form=form))
            out.append("")

    # ── anchor resize handler (IDOL-generated, always overwritten) ───────────
    if _anchored:
        # Container widgets with size-changing anchors that have anchored children
        # need local _pw_XXX / _ph_XXX variables so children can reference them.
        _dyn_containers: dict[str, "WidgetDescriptor"] = {
            w.id: w for w in form.widgets
            if w.anchor in _SIZE_ANCHORS
            and REGISTRY.get(w.type, {}).get("is_container")
            and any(c.parent_id == w.id and c.anchor and c.anchor != "top_left"
                    for c in form.widgets)
        }

        out.append("    def _apply_anchor_layout(self, event):")
        out.append("        if event.widget is not self:")
        out.append("            return")
        out.append("        _fw, _fh = event.width, event.height")

        # Emit local size vars for dynamic parent containers (parents precede
        # children in form.widgets, so order is safe)
        for par in form.widgets:
            if par.id not in _dyn_containers:
                continue
            if par.type == "LabelFrame":
                lh = _LF_LABEL_H
            elif REGISTRY.get(par.type, {}).get("is_notebook"):
                lh = _NB_TAB_H
            else:
                lh = 0
            pw_expr, ph_expr = _container_new_size_exprs(par, form.width, form.height)
            out.append(f"        _pw_{par.id} = {pw_expr}")
            if lh:
                out.append(f"        _ph_{par.id} = {ph_expr} - {lh}")
            else:
                out.append(f"        _ph_{par.id} = {ph_expr}")

        for w in _anchored:
            if w.parent_id:
                par = form.get_widget(w.parent_id)
                if par:
                    if par.type == "LabelFrame":
                        lh = _LF_LABEL_H
                    elif REGISTRY.get(par.type, {}).get("is_notebook"):
                        lh = _NB_TAB_H
                    else:
                        lh = 0
                    if par.id in _dyn_containers:
                        line = _anchor_resize_line(
                            w, par.width, par.height - lh,
                            f"_pw_{par.id}", f"_ph_{par.id}",
                        )
                    else:
                        # Fixed-size parent: child position never changes, skip
                        line = ""
                else:
                    line = _anchor_resize_line(w, form.width, form.height)
            else:
                line = _anchor_resize_line(w, form.width, form.height)
            if line:
                out.append(line)
        out.append("")

    # ── event methods ─────────────────────────────────────────────────────────
    # Build reverse map: method_name → ev_key, for form-level events
    form_ev_map: dict[str, str] = {
        m: k for k, m in form.form_events.items() if m
    }
    methods = _collect_methods(form)
    opener_names = [f"_open_{d}" for d in dialogs]
    if methods or opener_names or active_handlers:
        out.append("    # ── Events " + "─" * 63)
        out.append("")
        for h in active_handlers:
            sig_params = f", {h.params}" if h.params else ""
            out.append(f"    def {h.id}(self{sig_params}):")
            out.extend(_body_lines(h.id, bodies, h.default_body))
            out.append("")
        for name in methods:
            ev_key = form_ev_map.get(name)
            if ev_key and name not in sigs:
                defs = _FORM_EV_DEFAULTS.get(ev_key, ("event", ""))
                default_params, default_body = defs
            else:
                default_params, default_body = "*args", ""
            params, ret = sigs.get(name, (default_params, ""))
            ret_str = f" -> {ret}" if ret else ""
            sig_params = f", {params}" if params else ""
            out.append(f"    def {name}(self{sig_params}){ret_str}:")
            out.extend(_body_lines(name, bodies, default_body))
            out.append("")
        for d in dialogs:
            opener = f"_open_{d}"
            default_body = f"self.dlg_{d}.deiconify()"
            out.append(f"    def {opener}(self):")
            out.extend(_body_lines(opener, bodies, default_body))
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
    if not is_dialog:
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
    emit_key = _PROP_RENAMES.get(key, key)
    if key in ("char_width", "char_height") and isinstance(val, str):
        try:
            return f"{emit_key}={int(val)}"
        except ValueError:
            pass
    if isinstance(val, str) and key in _BOOL_PROPS:
        if val in ("True", "False"):
            return f"{emit_key}={val}"
        return f'{emit_key}="{val}"'
    if isinstance(val, str):
        escaped = val.replace("\\", "\\\\").replace('"', '\\"')
        return f'{emit_key}="{escaped}"'
    if isinstance(val, bool):
        return f"{emit_key}={val}"
    if isinstance(val, (int, float)):
        return f"{emit_key}={val}"
    if isinstance(val, list):
        return f"{emit_key}={tuple(val)!r}"
    return f"{emit_key}={repr(val)}"


def _widget_lines(w: WidgetDescriptor, y_offset: int = 0, form: "FormModel | None" = None) -> list[str]:
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
        if k in ("scrollbar", "tabs"):
            continue  # structural props — not tkinter kwargs
        if k in _all_color_props and v == "":
            continue
        if k in _SKIP_IF_EMPTY and (v == "" or v == () or v == []):
            continue
        if k in ("char_width", "char_height") and (v == "" or v == 0):
            continue
        if k in ("from_", "to") and w.props.get("values"):
            continue  # values= list mode; from_/to are irrelevant
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

    # Resolve parent — Notebook children attach to their tab Frame, not the Notebook
    if w.parent_id:
        par = form.get_widget(w.parent_id) if form else None
        if par and REGISTRY.get(par.type, {}).get("is_notebook"):
            tabs = par.props.get("tabs") or []
            tab_idx = tabs.index(w.tab) if w.tab in tabs else 0
            original_parent = f"self._tab_{par.id}_{tab_idx}"
        else:
            original_parent = f"self.{w.parent_id}"
    else:
        original_parent = "self"
    place_y = w.y if w.parent_id else w.y - y_offset
    lines: list[str] = []

    # ── Notebook: create widget + one Frame per tab ───────────────────────────
    if REGISTRY.get(w.type, {}).get("is_notebook"):
        kw_str = ""  # bg on Notebook doesn't apply directly; skip widget kwargs
        lines.append(f"        self.{w.id} = {tk_class}({original_parent})")
        lines.append(
            f"        self.{w.id}.place(x={w.x}, y={place_y},"
            f" width={w.width}, height={w.height})"
        )
        for i, tab_name in enumerate(w.props.get("tabs") or ["Tab 1"]):
            fvar = f"self._tab_{w.id}_{i}"
            bg_part = f', bg="{w.props["bg"]}"' if w.props.get("bg") else ""
            lines.append(f"        {fvar} = tk.Frame(self.{w.id}{bg_part})")
            lines.append(f"        self.{w.id}.add({fvar}, text={repr(tab_name)})")
        for event_key, method_name in w.events.items():
            binding = _BINDINGS.get(event_key)
            if binding and method_name:
                lines.append(
                    f'        self.{w.id}.bind("{binding}", self.{method_name})'
                )
        return lines

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
        _place_parts = [f"x={w.x}", f"y={place_y}"]
        if not w.props.get("char_width"):
            _place_parts.append(f"width={w.width}")
        if not w.props.get("char_height"):
            _place_parts.append(f"height={w.height}")
        lines.append(f"        self.{w.id}.place({', '.join(_place_parts)})")

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
    for method_name in form.form_events.values():
        if method_name and method_name not in seen:
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


def _form_event_binding(ev_key: str, method_name: str) -> str:
    """Return the __init__ line that wires a form-level event."""
    if ev_key == "load":
        return f"self.after_idle(self.{method_name})"
    if ev_key == "unload":
        return f'self.protocol("WM_DELETE_WINDOW", self.{method_name})'
    _map = {
        "activate":   "<FocusIn>",
        "deactivate": "<FocusOut>",
        "resize":     "<Configure>",
    }
    binding = _map.get(ev_key)
    if binding:
        return f'self.bind("{binding}", self.{method_name})'
    return ""


def _body_lines(method_name: str, bodies: dict[str, str],
                default_body: str = "") -> list[str]:
    """Return the 8-space-indented body lines for one event method."""
    raw = bodies.get(method_name, "").strip()
    stub = raw if (raw and raw not in (_STUB, "pass")) else ""
    if not stub:
        stub = default_body
    if not stub:
        return [f"        {_STUB}"]
    # Re-indent each line to method body level (8 spaces)
    result: list[str] = []
    for line in textwrap.dedent(stub).splitlines():
        result.append(("        " + line) if line.strip() else "")
    return result or [f"        {_STUB}"]


# ── Anchor resize codegen ──────────────────────────────────────────────────────

def _container_new_size_exprs(par: "WidgetDescriptor",
                               form_w: int, form_h: int) -> tuple[str, str]:
    """Return (new_outer_width_expr, new_outer_height_expr) for a dynamic container."""
    a = par.anchor
    x, y, pw, ph = par.x, par.y, par.width, par.height
    rm = form_w - (x + pw)
    bm = form_h - (y + ph)
    if a == "all":
        return (f"round({pw} * _fw / {form_w})", f"round({ph} * _fh / {form_h})")
    if a in ("top", "bottom"):
        return (f"_fw - {x} - {rm}", str(ph))
    if a in ("left", "right"):
        return (str(pw), f"_fh - {y} - {bm}")
    return (str(pw), str(ph))


def _anchor_resize_line(w: "WidgetDescriptor", ref_w: int, ref_h: int,
                         fw_expr: str = "_fw", fh_expr: str = "_fh") -> str:
    """Return the self.widget.place(...) line for one anchored widget, or ''.

    ref_w/ref_h are the original design-time reference dimensions (form or parent
    content area).  fw_expr/fh_expr are the Python expressions for those dimensions
    at runtime (default: '_fw'/'_fh' for form-level; pass a local variable name for
    children of dynamic parent containers).
    """
    a = w.anchor
    x, y, ww, wh = w.x, w.y, w.width, w.height
    rm = ref_w - (x + ww)
    bm = ref_h - (y + wh)
    kwargs: dict[str, str] = {}

    if a == "all":
        kwargs = {
            "x":      f"round({x} * {fw_expr} / {ref_w})",
            "y":      f"round({y} * {fh_expr} / {ref_h})",
            "width":  f"round({ww} * {fw_expr} / {ref_w})",
            "height": f"round({wh} * {fh_expr} / {ref_h})",
        }
    elif a == "top":          # pin top, stretch H
        kwargs = {"width": f"{fw_expr} - {x} - {rm}"}
    elif a == "bottom":       # pin bottom, stretch H
        kwargs = {"y": f"{fh_expr} - {bm} - {wh}", "width": f"{fw_expr} - {x} - {rm}"}
    elif a == "left":         # pin left, stretch V
        kwargs = {"height": f"{fh_expr} - {y} - {bm}"}
    elif a == "right":        # pin right, stretch V
        kwargs = {"x": f"{fw_expr} - {rm} - {ww}", "height": f"{fh_expr} - {y} - {bm}"}
    elif a == "top_right":    # pin top-right corner
        kwargs = {"x": f"{fw_expr} - {rm} - {ww}"}
    elif a == "bottom_left":  # pin bottom-left corner
        kwargs = {"y": f"{fh_expr} - {bm} - {wh}"}
    elif a == "bottom_right": # pin bottom-right corner
        kwargs = {"x": f"{fw_expr} - {rm} - {ww}", "y": f"{fh_expr} - {bm} - {wh}"}

    if not kwargs:
        return ""
    args = ", ".join(f"{k}={v}" for k, v in kwargs.items())
    return f"        self.{w.id}.place({args})"
