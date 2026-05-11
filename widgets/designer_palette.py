from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from designer.registry import REGISTRY, all_types
from utils.ui_font import UI_FONT
from widgets.scrollbar import VerticalScrollbar

_BG     = "#252526"
_ITEM   = "#2d2d30"
_ACT    = "#094771"
_FG     = "#cccccc"
_DIM    = "#858585"
_BORDER = "#007acc"

_PREVIEW_W = 56
_PREVIEW_H = 22


class DesignerPalette(tk.Frame):
    """Widget toolbox panel shown in the left pane during Designer mode.

    Displays a 'Pointer' (select) tool plus one entry per widget type.
    Each entry shows a canvas-drawn mini-preview and a text label.
    Clicking fires on_tool_select(type_key) where type_key is the registry
    key (e.g. 'Button') or None for the pointer/select tool.
    Dragging a widget onto the canvas fires on_drag_drop(type_key, x_root, y_root).
    """

    def __init__(
        self,
        master,
        on_tool_select: Optional[Callable[[str | None], None]] = None,
        on_place: Optional[Callable[[str], None]] = None,
        on_drag_drop: Optional[Callable[[str, int, int], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, **kwargs)
        self._on_tool_select = on_tool_select
        self._on_place = on_place
        self._on_drag_drop = on_drag_drop
        self._selected: str | None = None   # None = pointer tool
        self._items:    dict[str | None, tk.Frame] = {}
        self._drag_pending: dict | None = None
        self._ghost: tk.Toplevel | None = None
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # Header
        tk.Label(self, text="WIDGETS", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w",
                 padx=8).pack(fill="x", pady=(8, 2))
        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # Scrollable list
        canvas = tk.Canvas(self, bg=_BG, highlightthickness=0, bd=0)
        sb = VerticalScrollbar(self, command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        self._list = tk.Frame(canvas, bg=_BG)
        canvas.create_window((0, 0), window=self._list, anchor="nw")
        self._list.bind("<Configure>",
                        lambda e: canvas.configure(
                            scrollregion=canvas.bbox("all")))
        canvas.bind("<MouseWheel>",
                    lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Pointer (select) tool
        self._add_item(None, "Pointer", self._draw_pointer)

        ttk.Separator(self._list, orient="horizontal").pack(fill="x", pady=4)

        # One entry per widget type
        for type_key in all_types():
            reg = REGISTRY[type_key]
            self._add_item(type_key, reg["label"], reg["draw_preview"])

        # Select pointer by default
        self._apply_selection(None)

    def _add_item(self, type_key: str | None, label: str, draw_fn) -> None:
        row = tk.Frame(self._list, bg=_ITEM, cursor="hand2")
        row.pack(fill="x", padx=4, pady=1)

        # Left accent bar (shown when selected)
        accent = tk.Frame(row, bg=_ITEM, width=3)
        accent.pack(side="left", fill="y")

        # Mini canvas preview
        prev = tk.Canvas(row, width=_PREVIEW_W, height=_PREVIEW_H,
                         bg="#f5f5f5", highlightthickness=1,
                         highlightbackground="#555555")
        prev.pack(side="left", padx=(4, 6), pady=4)
        draw_fn(prev, 2, 1, _PREVIEW_W - 4, _PREVIEW_H - 2)

        # Label
        lbl = tk.Label(row, text=label, bg=_ITEM, fg=_FG,
                       font=(UI_FONT, 8), anchor="w")
        lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

        # Bind click on all child widgets
        for widget in (row, prev, lbl, accent):
            widget.bind("<Button-1>",         lambda e, k=type_key: self._on_press(k, e))
            widget.bind("<B1-Motion>",         lambda e, k=type_key: self._on_drag_motion(k, e))
            widget.bind("<ButtonRelease-1>",   lambda e, k=type_key: self._on_drag_release(k, e))
            widget.bind("<Double-Button-1>",   lambda _, k=type_key: self._place(k))
            widget.bind("<Enter>",    lambda _, r=row, a=accent, k=type_key:
                        self._on_enter(r, a, k))
            widget.bind("<Leave>",    lambda _, r=row, a=accent, k=type_key:
                        self._on_leave(r, a, k))

        self._items[type_key] = row
        row._accent = accent   # type: ignore[attr-defined]

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_tool(self) -> str | None:
        return self._selected

    def reset_to_pointer(self) -> None:
        self._apply_selection(None)

    # ── Interaction ───────────────────────────────────────────────────────────

    def _select(self, type_key: str | None) -> None:
        self._apply_selection(type_key)
        if self._on_tool_select:
            self._on_tool_select(type_key)

    def _place(self, type_key: str | None) -> None:
        if type_key is None:
            return
        self._apply_selection(None)
        if self._on_place:
            self._on_place(type_key)

    def _on_press(self, type_key: str | None, event: tk.Event) -> None:
        self._drag_pending = {
            "type_key": type_key,
            "start_x":  event.x_root,
            "start_y":  event.y_root,
            "dragging": False,
        }

    def _on_drag_motion(self, type_key: str | None, event: tk.Event) -> None:
        if self._drag_pending is None or type_key is None:
            return
        if not self._drag_pending["dragging"]:
            dx = abs(event.x_root - self._drag_pending["start_x"])
            dy = abs(event.y_root - self._drag_pending["start_y"])
            if dx > 5 or dy > 5:
                self._drag_pending["dragging"] = True
                self._show_ghost(type_key)
        if self._drag_pending["dragging"]:
            self._move_ghost(event.x_root, event.y_root)

    def _on_drag_release(self, type_key: str | None, event: tk.Event) -> None:
        if self._drag_pending is None:
            self._select(type_key)
            return
        was_dragging = self._drag_pending["dragging"]
        self._drag_pending = None
        self._hide_ghost()
        if was_dragging:
            if type_key is not None and self._on_drag_drop:
                self._on_drag_drop(type_key, event.x_root, event.y_root)
        else:
            self._select(type_key)

    def _show_ghost(self, type_key: str) -> None:
        self._hide_ghost()
        self._ghost = tk.Toplevel(self.winfo_toplevel())
        self._ghost.overrideredirect(True)
        self._ghost.attributes("-topmost", True)
        self._ghost.attributes("-alpha", 0.85)
        tk.Label(
            self._ghost, text=f"  {type_key}  ",
            bg=_ACT, fg="#ffffff",
            font=(UI_FONT, 9), relief="solid", bd=1,
        ).pack()

    def _move_ghost(self, x_root: int, y_root: int) -> None:
        if self._ghost:
            self._ghost.geometry(f"+{x_root + 14}+{y_root + 10}")

    def _hide_ghost(self) -> None:
        if self._ghost:
            self._ghost.destroy()
            self._ghost = None

    def _apply_selection(self, type_key: str | None) -> None:
        # Clear old selection
        if self._selected in self._items:
            old = self._items[self._selected]
            old.config(bg=_ITEM)
            old._accent.config(bg=_ITEM)   # type: ignore[attr-defined]
            for child in old.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg=_ITEM)
        self._selected = type_key
        # Highlight new selection
        if type_key in self._items:
            row = self._items[type_key]
            row.config(bg=_ACT)
            row._accent.config(bg=_BORDER)  # type: ignore[attr-defined]
            for child in row.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg=_ACT)

    def _on_enter(self, row: tk.Frame, accent: tk.Frame,
                  type_key: str | None) -> None:
        if type_key != self._selected:
            row.config(bg="#3e3e42")
            for child in row.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg="#3e3e42")

    def _on_leave(self, row: tk.Frame, accent: tk.Frame,
                  type_key: str | None) -> None:
        if type_key != self._selected:
            row.config(bg=_ITEM)
            for child in row.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg=_ITEM)

    # ── Pointer tool preview ──────────────────────────────────────────────────

    @staticmethod
    def _draw_pointer(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        cx, cy = x + w // 2, y + h // 2
        pts = [cx, cy-8, cx+5, cy+2, cx+2, cy+1, cx+3, cy+6,
               cx+1, cy+6, cx, cy+2, cx-3, cy+4]
        c.create_polygon(pts, fill="#cccccc", outline="#888888", width=1)
