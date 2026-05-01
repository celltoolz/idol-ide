from __future__ import annotations

"""
Widget type registry — one entry per supported widget.

Each entry defines:
  tk_class       : import path used in generated code
  default_size   : (width, height) placed on canvas
  default_props  : props written into a new WidgetDescriptor
  events         : ordered list of event keys shown in the Events tab
  draw_preview   : callable(canvas, x, y, w, h) — draws the palette mini-preview
"""

import tkinter as tk
from typing import Callable


# ── Preview drawing helpers ────────────────────────────────────────────────────

def _raised_rect(c: tk.Canvas, x: int, y: int, w: int, h: int,
                 text: str = "", bg: str = "#d4d0c8", fg: str = "#000000") -> None:
    c.create_rectangle(x+2, y+2, x+w-2, y+h-2, fill=bg, outline="#ffffff", width=1)
    c.create_rectangle(x+2, y+2, x+w-2, y+h-2, fill="", outline="#808080", width=1)
    if text:
        c.create_text(x+w//2, y+h//2, text=text, fill=fg, font=("TkDefaultFont", 7))


def _sunken_rect(c: tk.Canvas, x: int, y: int, w: int, h: int,
                 text: str = "") -> None:
    c.create_rectangle(x+2, y+2, x+w-2, y+h-2, fill="#ffffff", outline="#808080", width=1)
    c.create_rectangle(x+3, y+3, x+w-3, y+h-3, fill="", outline="#c0c0c0", width=1)
    if text:
        c.create_text(x+6, y+h//2, text=text, fill="#808080",
                      font=("TkDefaultFont", 7), anchor="w")


def _draw_button(c, x, y, w, h):  _raised_rect(c, x, y, w, h, text="Button")
def _draw_label(c, x, y, w, h):
    c.create_text(x+w//2, y+h//2, text="Label", fill="#cccccc",
                  font=("TkDefaultFont", 7))

def _draw_entry(c, x, y, w, h):   _sunken_rect(c, x, y, w, h, text="abc|")
def _draw_text(c, x, y, w, h):
    _sunken_rect(c, x, y, w, h)
    c.create_text(x+5, y+5, text="Text", fill="#808080",
                  font=("TkDefaultFont", 7), anchor="nw")

def _draw_checkbutton(c, x, y, w, h):
    bx, by = x+2, y+h//2-5
    c.create_rectangle(bx, by, bx+10, by+10, outline="#808080", fill="#ffffff")
    c.create_line(bx+2, by+5, bx+4, by+8, fill="#000080", width=1)
    c.create_line(bx+4, by+8, bx+9, by+2, fill="#000080", width=1)
    c.create_text(bx+14, y+h//2, text="Check", fill="#cccccc",
                  font=("TkDefaultFont", 7), anchor="w")

def _draw_radiobutton(c, x, y, w, h):
    cx2, cy2 = x+7, y+h//2
    c.create_oval(cx2-5, cy2-5, cx2+5, cy2+5, outline="#808080", fill="#ffffff")
    c.create_oval(cx2-2, cy2-2, cx2+2, cy2+2, fill="#000080", outline="")
    c.create_text(cx2+9, y+h//2, text="Radio", fill="#cccccc",
                  font=("TkDefaultFont", 7), anchor="w")

def _draw_combobox(c, x, y, w, h):
    _sunken_rect(c, x, y, w-14, h)
    c.create_rectangle(x+w-14, y+2, x+w-2, y+h-2, fill="#d4d0c8", outline="#808080")
    c.create_text(x+w-8, y+h//2, text="▼", fill="#000000",
                  font=("TkDefaultFont", 6))

def _draw_listbox(c, x, y, w, h):
    _sunken_rect(c, x, y, w, h)
    for i, item in enumerate(["Item 1", "Item 2"]):
        iy = y+4 + i*10
        if i == 0:
            c.create_rectangle(x+3, iy-1, x+w-3, iy+9,
                                fill="#000080", outline="")
        c.create_text(x+5, iy+4, text=item,
                      fill="#ffffff" if i == 0 else "#cccccc",
                      font=("TkDefaultFont", 6), anchor="w")

def _draw_frame(c, x, y, w, h):
    c.create_rectangle(x+2, y+2, x+w-2, y+h-2,
                        outline="#808080", fill="", dash=(3, 3))

def _draw_labelframe(c, x, y, w, h):
    c.create_rectangle(x+2, y+8, x+w-2, y+h-2,
                        outline="#808080", fill="", dash=(3, 3))
    c.create_rectangle(x+6, y+4, x+36, y+14, fill="#1e1e1e", outline="")
    c.create_text(x+20, y+10, text="Group", fill="#cccccc",
                  font=("TkDefaultFont", 6))

def _draw_scale(c, x, y, w, h):
    cy2 = y + h//2
    c.create_line(x+4, cy2, x+w-4, cy2, fill="#808080", width=2)
    tx = x + (w-8)//2 + 4
    c.create_rectangle(tx-3, cy2-6, tx+3, cy2+6, fill="#d4d0c8", outline="#808080")

def _draw_spinbox(c, x, y, w, h):
    _sunken_rect(c, x, y, w-14, h, text="0")
    bw = 14
    bx = x + w - bw
    mid = y + h//2
    c.create_rectangle(bx, y+2, x+w-2, mid, fill="#d4d0c8", outline="#808080")
    c.create_rectangle(bx, mid, x+w-2, y+h-2, fill="#d4d0c8", outline="#808080")
    c.create_text(bx+7, y+h//4+1, text="▲", fill="#000000", font=("TkDefaultFont", 5))
    c.create_text(bx+7, y+3*h//4, text="▼", fill="#000000", font=("TkDefaultFont", 5))

def _draw_progressbar(c, x, y, w, h):
    _sunken_rect(c, x, y, w, h)
    fill_w = int((w-6) * 0.6)
    c.create_rectangle(x+3, y+3, x+3+fill_w, y+h-3, fill="#0078d4", outline="")

def _draw_separator(c, x, y, w, h):
    cy2 = y + h//2
    c.create_line(x+2, cy2, x+w-2, cy2, fill="#808080", width=1)


# ── Common prop choice lists ──────────────────────────────────────────────────

_JUSTIFY = ["left", "center", "right"]
_RELIEF  = ["flat", "sunken", "raised", "groove", "ridge", "solid"]


# ── Common event sets ──────────────────────────────────────────────────────────

_MOUSE_EVENTS   = ["click", "dblclick", "rightclick",
                   "mousedown", "mouseup", "mousemove",
                   "mouseenter", "mouseleave"]
_FOCUS_EVENTS   = ["focusin", "focusout"]
_KEY_EVENTS     = ["keypress", "keydown", "keyup"]
_CHANGE_EVENTS  = ["change"]

_WIDGET_EVENTS  = _MOUSE_EVENTS + _FOCUS_EVENTS + _KEY_EVENTS + _CHANGE_EVENTS
_SIMPLE_EVENTS  = _MOUSE_EVENTS + _FOCUS_EVENTS


# ── Registry ──────────────────────────────────────────────────────────────────

REGISTRY: dict[str, dict] = {
    "Button": {
        "label":        "Button",
        "tk_class":     "tk.Button",
        "default_size": (90, 30),
        "default_props": {"text": "Button", "bg": "#E1E1E1", "fg": "#000000",
                          "font": "", "justify": "", "relief": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS + _KEY_EVENTS,
        "draw_preview": _draw_button,
        "color_props":  ["bg", "fg"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
        "state_color_props": {"disabled": ["disabledforeground"]},
        "prop_choices": {"justify": _JUSTIFY, "relief": _RELIEF},
    },
    "Label": {
        "label":        "Label",
        "tk_class":     "tk.Label",
        "default_size": (80, 25),
        "default_props": {"text": "Label", "bg": "#F0F0F0", "fg": "#000000",
                          "font": "", "justify": "", "relief": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS,
        "draw_preview": _draw_label,
        "variable_prop":  "textvariable",
        "variable_types": ["StringVar"],
        "color_props":  ["bg", "fg"],
        "prop_choices": {"justify": _JUSTIFY, "relief": _RELIEF},
    },
    "Entry": {
        "label":        "Entry",
        "tk_class":     "tk.Entry",
        "default_size": (120, 25),
        "default_props": {"text": "", "bg": "#FFFFFF", "fg": "#000000",
                          "show": "", "font": "", "justify": "", "relief": "",
                          "insertbackground": "", "borderwidth": ""},
        "events":       _WIDGET_EVENTS,
        "draw_preview": _draw_entry,
        "variable_prop":  "textvariable",
        "variable_types": ["StringVar", "IntVar", "DoubleVar"],
        "color_props":  ["bg", "fg", "insertbackground"],
        "state_prop":   True,
        "state_values": ["normal", "readonly", "disabled"],
        "state_color_props": {
            "readonly": ["readonlybackground"],
            "disabled": ["disabledbackground", "disabledforeground"],
        },
        "validate_prop":   True,
        "validate_values": ["none", "focus", "focusin", "focusout", "key", "all"],
        "prop_choices": {"justify": _JUSTIFY, "relief": _RELIEF},
    },
    "Text": {
        "label":        "Text",
        "tk_class":     "tk.Text",
        "default_size": (180, 80),
        "default_props": {"wrap": "word", "bg": "#FFFFFF", "fg": "#000000",
                          "font": "", "relief": "", "insertbackground": "", "borderwidth": ""},
        "events":       _WIDGET_EVENTS,
        "draw_preview": _draw_text,
        "color_props":  ["bg", "fg", "insertbackground"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
        "prop_choices": {"relief": _RELIEF},
    },
    "Checkbutton": {
        "label":        "Checkbutton",
        "tk_class":     "tk.Checkbutton",
        "default_size": (100, 25),
        "default_props": {"text": "Check", "bg": "#F0F0F0", "fg": "#000000",
                          "font": "", "justify": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS + _CHANGE_EVENTS,
        "draw_preview": _draw_checkbutton,
        "variable_prop":  "variable",
        "variable_types": ["BooleanVar", "IntVar"],
        "color_props":  ["bg", "fg"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
        "state_color_props": {"disabled": ["disabledforeground"]},
        "prop_choices": {"justify": _JUSTIFY},
    },
    "Radiobutton": {
        "label":        "Radiobutton",
        "tk_class":     "tk.Radiobutton",
        "default_size": (100, 25),
        "default_props": {"text": "Radio", "value": "1", "bg": "#F0F0F0", "fg": "#000000",
                          "font": "", "justify": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS + _CHANGE_EVENTS,
        "draw_preview": _draw_radiobutton,
        "variable_prop":  "variable",
        "variable_types": ["IntVar", "StringVar"],
        "color_props":  ["bg", "fg"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
        "state_color_props": {"disabled": ["disabledforeground"]},
        "prop_choices": {"justify": _JUSTIFY},
    },
    "Combobox": {
        "label":        "Combobox",
        "tk_class":     "ttk.Combobox",
        "default_size": (120, 25),
        "default_props": {"values": []},
        "events":       _SIMPLE_EVENTS + _CHANGE_EVENTS + _KEY_EVENTS,
        "draw_preview": _draw_combobox,
        "variable_prop":  "textvariable",
        "variable_types": ["StringVar"],
        "state_prop":   True,
        "state_values": ["normal", "readonly", "disabled"],
    },
    "Listbox": {
        "label":        "Listbox",
        "tk_class":     "tk.Listbox",
        "default_size": (120, 80),
        "default_props": {"bg": "#FFFFFF", "fg": "#000000",
                          "font": "", "relief": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS + _CHANGE_EVENTS,
        "draw_preview": _draw_listbox,
        "color_props":  ["bg", "fg"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
        "prop_choices": {"relief": _RELIEF},
    },
    "Frame": {
        "label":        "Frame",
        "tk_class":     "tk.Frame",
        "default_size": (160, 100),
        "default_props": {"bg": "#F0F0F0", "relief": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS,
        "draw_preview": _draw_frame,
        "color_props":  ["bg"],
        "prop_choices": {"relief": _RELIEF},
    },
    "LabelFrame": {
        "label":        "LabelFrame",
        "tk_class":     "tk.LabelFrame",
        "default_size": (160, 100),
        "default_props": {"text": "Group", "bg": "#F0F0F0", "fg": "#000000",
                          "font": "", "relief": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS,
        "draw_preview": _draw_labelframe,
        "color_props":  ["bg", "fg"],
        "prop_choices": {"relief": _RELIEF},
    },
    "Scale": {
        "label":        "Scale",
        "tk_class":     "tk.Scale",
        "default_size": (150, 30),
        "default_props": {"orient": "horizontal", "from_": 0, "to": 100,
                          "bg": "#F0F0F0", "fg": "#000000", "font": "", "borderwidth": ""},
        "events":       _SIMPLE_EVENTS + _CHANGE_EVENTS,
        "draw_preview": _draw_scale,
        "variable_prop":  "variable",
        "variable_types": ["DoubleVar", "IntVar"],
        "color_props":  ["bg", "fg"],
        "state_prop":   True,
        "state_values": ["normal", "disabled"],
    },
    "Spinbox": {
        "label":        "Spinbox",
        "tk_class":     "tk.Spinbox",
        "default_size": (80, 25),
        "default_props": {"from_": 0, "to": 100, "bg": "#FFFFFF", "fg": "#000000",
                          "font": "", "justify": "", "relief": "",
                          "insertbackground": "", "borderwidth": ""},
        "events":       _WIDGET_EVENTS,
        "draw_preview": _draw_spinbox,
        "variable_prop":  "textvariable",
        "variable_types": ["StringVar", "IntVar", "DoubleVar"],
        "color_props":  ["bg", "fg", "insertbackground"],
        "state_prop":   True,
        "state_values": ["normal", "readonly", "disabled"],
        "state_color_props": {
            "readonly": ["readonlybackground"],
            "disabled": ["disabledbackground", "disabledforeground"],
        },
        "validate_prop":   True,
        "validate_values": ["none", "focus", "focusin", "focusout", "key", "all"],
        "prop_choices": {"justify": _JUSTIFY, "relief": _RELIEF},
    },
    "Progressbar": {
        "label":        "Progressbar",
        "tk_class":     "ttk.Progressbar",
        "default_size": (150, 20),
        "default_props": {"orient": "horizontal", "mode": "determinate"},
        "events":       _SIMPLE_EVENTS,
        "draw_preview": _draw_progressbar,
    },
    "Separator": {
        "label":        "Separator",
        "tk_class":     "ttk.Separator",
        "default_size": (150, 10),
        "default_props": {"orient": "horizontal"},
        "events":       [],
        "draw_preview": _draw_separator,
    },
}


def get(type_key: str) -> dict:
    """Return the registry entry for a widget type, raising KeyError if unknown."""
    return REGISTRY[type_key]


def all_types() -> list[str]:
    """Return all widget type keys in palette display order."""
    return list(REGISTRY.keys())
