"""LearningManager — singleton connecting widget hover events to the Learning panel."""
from __future__ import annotations

from tkinter import ttk
from typing import Callable

from utils.learning_registry import REGISTRY


class LearningManager:
    """Singleton that connects widget hover events to the Learning panel.

    Usage:
        # At app startup:
        LearningManager.set_handler(my_show_fn)

        # When building any widget:
        LearningManager.register(some_widget, "outline_panel")
    """

    _handler: Callable[[str], None] | None = None
    _registrations: list = []   # list of (widget, lid, overlay)
    _originals: dict = {}       # widget → {"cursor", "highlightbackground", "highlightthickness"}
    _widget_lid: dict = {}      # widget → lid fast lookup
    _active: bool = False
    _on_click: Callable | None = None

    @classmethod
    def set_handler(cls, fn: Callable[[str], None]) -> None:
        cls._handler = fn

    @classmethod
    def register(cls, widget, lid: str, overlay: bool = True) -> None:
        """Register *widget* with a learning content ID.

        overlay=True  → widget gets cursor+flash treatment in Learning Mode
        overlay=False → registered but no flash (used for large panels)
        """
        if lid not in REGISTRY:
            return

        cls._registrations.append((widget, lid, overlay))
        cls._widget_lid[widget] = lid

        orig = {"cursor": "", "highlightbackground": "", "highlightthickness": 0}
        try:
            orig["cursor"] = widget.cget("cursor") or ""
        except Exception:
            pass
        try:
            if not isinstance(widget, ttk.Widget):
                orig["highlightbackground"] = widget.cget("highlightbackground") or ""
                orig["highlightthickness"] = int(widget.cget("highlightthickness") or 0)
        except Exception:
            pass
        cls._originals[widget] = orig

        def _fire(event=None):
            if cls._handler:
                cls._handler(lid)

        widget.bind("<Enter>", _fire, add="+")

    @classmethod
    def get_widget_originals(cls, widget) -> dict:
        """Return stored original style values for *widget*."""
        return cls._originals.get(
            widget, {"cursor": "", "highlightbackground": "", "highlightthickness": 0}
        )

    @classmethod
    def all_registrations(cls) -> list:
        """Return [(widget, lid)] for ALL registered widgets."""
        return [(w, l) for w, l, o in cls._registrations]

    @classmethod
    def overlay_registrations(cls) -> list:
        """Return [(widget, lid)] for widgets that had overlay=True (kept for compat)."""
        return [(w, l) for w, l, o in cls._registrations if o]

    @classmethod
    def set_active(cls, val: bool) -> None:
        cls._active = val

    @classmethod
    def is_active(cls) -> bool:
        return cls._active

    @classmethod
    def set_click_handler(cls, fn: Callable) -> None:
        cls._on_click = fn

    @classmethod
    def fire_click(cls, widget) -> None:
        """Dispatch a learning click for *widget* if it is registered."""
        lid = cls._widget_lid.get(widget)
        if lid and cls._on_click:
            cls._on_click(widget, lid)
