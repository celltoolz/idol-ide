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
    "change":      "<<Modified>>",
}

_STUB = "pass  # TODO"

# IDOL:BEGIN/END marker lines — must contain the tokens persistence.py detects
_INIT_B = "        # ── IDOL:BEGIN " + "─" * 55
_INIT_E = "        # ── IDOL:END "   + "─" * 57


# ── Public API ────────────────────────────────────────────────────────────────

def generate(form: FormModel, event_bodies: dict[str, str] | None = None,
             pre_init: str = "", post_init: str = "", helpers: str = "") -> str:
    """Return Python source for *form*.

    event_bodies: {method_name: dedented_body_str} — user event handler code.
    pre_init:     user code placed between form setup and self._build_ui().
    post_init:    user code placed after self._build_ui().
    helpers:      full source of public helper methods (user-written).
    """
    bodies = event_bodies or {}
    needs_ttk = _uses_ttk(form)

    out: list[str] = []

    # ── imports ───────────────────────────────────────────────────────────────
    out.append("import tkinter as tk")
    if needs_ttk:
        out.append("from tkinter import ttk")
    out += ["", ""]

    # ── class header ──────────────────────────────────────────────────────────
    base = "tk.Tk" if form.form_type == "main" else "tk.Toplevel"
    out.append(f"class {form.name}({base}):")
    out.append("    def __init__(self):")

    # Generated form-setup block (includes variable declarations)
    out.append(_INIT_B)
    out.append("        super().__init__()")
    out.append(f'        self.title("{form.title}")')
    out.append(f'        self.geometry("{form.width}x{form.height}")')
    if form.border_style == "none":
        out.append("        self.overrideredirect(True)")
    elif form.border_style == "fixed" or not form.maximize_box:
        out.append("        self.resizable(False, False)")
    if form.bg:
        out.append(f'        self.configure(bg="{form.bg}")')
    for line in _variable_decls(form):
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
    if not form.widgets:
        out.append(f"        {_STUB}")
    else:
        for w in form.widgets:
            out.extend(_widget_lines(w))
            out.append("")

    # ── event methods ─────────────────────────────────────────────────────────
    methods = _collect_methods(form)
    if methods:
        out.append("    # ── Events " + "─" * 63)
        out.append("")
        for name in methods:
            out.append(f"    def {name}(self, *args):")
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


def _widget_lines(w: WidgetDescriptor) -> list[str]:
    reg = REGISTRY.get(w.type)
    if not reg:
        return [f"        # Unknown widget type: {w.type}"]

    tk_class = reg["tk_class"]

    # Build ordered kwargs: props first, then variable binding, then command
    # Skip color props that are empty (unset) to avoid passing bg="" to tkinter
    _color_props = set(reg.get("color_props", []))
    kw_parts: list[str] = [
        _prop_str(k, v) for k, v in w.props.items()
        if not (k in _color_props and v == "")
    ]

    if w.variable:
        var_kwarg = reg.get("variable_prop", "textvariable")
        kw_parts.append(f"{var_kwarg}=self.{w.variable.name}")

    click_method = w.events.get("click")
    if w.type == "Button" and click_method:
        kw_parts.append(f"command=self.{click_method}")

    kw_str = (", " + ", ".join(kw_parts)) if kw_parts else ""
    lines = [f"        self.{w.id} = {tk_class}(self{kw_str})"]
    lines.append(
        f"        self.{w.id}.place(x={w.x}, y={w.y},"
        f" width={w.width}, height={w.height})"
    )

    # .bind() for every wired event that isn't a Button command
    for event_key, method_name in w.events.items():
        if w.type == "Button" and event_key == "click":
            continue
        binding = _BINDINGS.get(event_key)
        if binding and method_name:
            lines.append(
                f'        self.{w.id}.bind("{binding}", self.{method_name})'
            )

    return lines


def _collect_methods(form: FormModel) -> list[str]:
    """All unique event method names across the form, in widget/event order."""
    seen: set[str] = set()
    methods: list[str] = []
    for w in form.widgets:
        for method_name in w.events.values():
            if method_name and method_name not in seen:
                seen.add(method_name)
                methods.append(method_name)
    return methods


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
