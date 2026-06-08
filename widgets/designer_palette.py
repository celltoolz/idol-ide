from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional

from designer.component_registry import COMPONENT_REGISTRY, all_component_types
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

_CI_TOOLS: list[tuple] = [
    (None,        "Select"),
    ("image",     "Image"),
    ("rectangle", "Rectangle"),
    ("oval",      "Oval"),
    ("text",      "Text"),
    ("line",      "Line"),
]


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
        on_component_add: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, **kwargs)
        self._on_tool_select  = on_tool_select
        self._on_place        = on_place
        self._on_drag_drop    = on_drag_drop
        self._on_component_add = on_component_add
        self._selected: str | None = None   # None = pointer tool
        self._items:    dict[str | None, tk.Frame] = {}
        self._drag_pending: dict | None = None
        self._ghost: tk.Toplevel | None = None
        # CI mode state
        self._on_ci_arm: Optional[Callable[[str | None], None]] = None
        self._ci_armed: str = "__none__"  # sentinel — no CI tool highlighted
        self._ci_rows:  dict[str | None, tk.Frame] = {}
        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Normal palette ────────────────────────────────────────────────────
        # Header
        self._widgets_header = tk.Label(self, text="WIDGETS", bg=_BG, fg=_DIM,
                                        font=(UI_FONT, 8, "bold"), anchor="w", padx=8)
        self._widgets_header.pack(fill="x", pady=(8, 2))
        self._widgets_sep = ttk.Separator(self, orient="horizontal")
        self._widgets_sep.pack(fill="x")

        # Scrollable list
        self._scroll_canvas = tk.Canvas(self, bg=_BG, highlightthickness=0, bd=0)
        self._scroll_sb = VerticalScrollbar(self, command=self._scroll_canvas.yview)
        self._scroll_canvas.configure(yscrollcommand=self._scroll_sb.set)
        self._scroll_sb.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

        self._list = tk.Frame(self._scroll_canvas, bg=_BG)
        self._scroll_canvas.create_window((0, 0), window=self._list, anchor="nw")
        self._list.bind("<Configure>",
                        lambda e: self._scroll_canvas.configure(
                            scrollregion=self._scroll_canvas.bbox("all")))
        self._scroll_canvas.bind(
            "<MouseWheel>",
            lambda e: self._scroll_canvas.yview_scroll(-1 * (e.delta // 120), "units"))

        # Pointer (select) tool
        self._add_item(None, "Pointer", self._draw_pointer)

        ttk.Separator(self._list, orient="horizontal").pack(fill="x", pady=4)

        # One entry per widget type
        for type_key in all_types():
            reg = REGISTRY[type_key]
            self._add_item(type_key, reg["label"], reg["draw_preview"])

        # ── COMPONENTS section ────────────────────────────────────────────────
        ttk.Separator(self._list, orient="horizontal").pack(fill="x", pady=4)
        tk.Label(self._list, text="COMPONENTS", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w",
                 padx=8).pack(fill="x", pady=(0, 2))

        for type_key in all_component_types():
            cdef = COMPONENT_REGISTRY[type_key]
            self._add_component_item(type_key, cdef.label, cdef.icon)

        # Select pointer by default
        self._apply_selection(None)

        # ── CI mode frame (hidden until enter_ci_mode()) ──────────────────────
        self._ci_frame = tk.Frame(self, bg=_BG)
        tk.Label(self._ci_frame, text="CANVAS ITEMS", bg=_BG, fg=_DIM,
                 font=(UI_FONT, 8, "bold"), anchor="w",
                 padx=8).pack(fill="x", pady=(8, 2))
        ttk.Separator(self._ci_frame, orient="horizontal").pack(fill="x")
        self._ci_list = tk.Frame(self._ci_frame, bg=_BG)
        self._ci_list.pack(fill="both", expand=True)
        for kind, label in _CI_TOOLS:
            self._add_ci_item(kind, label)

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

    def _add_component_item(self, type_key: str, label: str, icon: str) -> None:
        row = tk.Frame(self._list, bg=_ITEM, cursor="hand2")
        row.pack(fill="x", padx=4, pady=1)

        accent = tk.Frame(row, bg=_ITEM, width=3)
        accent.pack(side="left", fill="y")

        icon_lbl = tk.Label(row, text=icon, bg=_ITEM, fg=_FG,
                            font=(UI_FONT, 13), width=3, anchor="center")
        icon_lbl.pack(side="left", padx=(4, 2), pady=2)

        name_lbl = tk.Label(row, text=label, bg=_ITEM, fg=_FG,
                            font=(UI_FONT, 8), anchor="w")
        name_lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

        for w in (row, accent, icon_lbl, name_lbl):
            w.bind("<ButtonRelease-1>", lambda e, k=type_key: self._comp_add(k))
            w.bind("<Enter>", lambda e, r=row, a=accent, il=icon_lbl, nl=name_lbl:
                   self._comp_hover(r, a, il, nl, True))
            w.bind("<Leave>", lambda e, r=row, a=accent, il=icon_lbl, nl=name_lbl:
                   self._comp_hover(r, a, il, nl, False))

    def _add_ci_item(self, kind: str | None, label: str) -> None:
        row = tk.Frame(self._ci_list, bg=_ITEM, cursor="hand2")
        row.pack(fill="x", padx=4, pady=1)

        accent = tk.Frame(row, bg=_ITEM, width=3)
        accent.pack(side="left", fill="y")

        prev = tk.Canvas(row, width=_PREVIEW_W, height=_PREVIEW_H,
                         bg="#f5f5f5", highlightthickness=1,
                         highlightbackground="#555555")
        prev.pack(side="left", padx=(4, 6), pady=4)
        draw_fn = {
            None:        self._draw_pointer,
            "image":     self._draw_ci_image,
            "rectangle": self._draw_ci_rect,
            "oval":      self._draw_ci_oval,
            "text":      self._draw_ci_text,
            "line":      self._draw_ci_line,
        }.get(kind, self._draw_pointer)
        draw_fn(prev, 2, 1, _PREVIEW_W - 4, _PREVIEW_H - 2)

        lbl = tk.Label(row, text=label, bg=_ITEM, fg=_FG,
                       font=(UI_FONT, 8), anchor="w")
        lbl.pack(side="left", fill="x", expand=True, padx=(0, 4))

        for widget in (row, prev, lbl, accent):
            widget.bind("<ButtonRelease-1>", lambda e, k=kind: self._ci_select(k))
            widget.bind("<Enter>",  lambda e, r=row, k=kind: self._ci_hover(r, k, True))
            widget.bind("<Leave>",  lambda e, r=row, k=kind: self._ci_hover(r, k, False))

        self._ci_rows[kind] = row
        row._accent = accent  # type: ignore[attr-defined]

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def selected_tool(self) -> str | None:
        return self._selected

    def reset_to_pointer(self) -> None:
        if self._on_ci_arm is not None:
            self.set_ci_armed(None)
            if self._on_ci_arm:
                self._on_ci_arm(None)
        else:
            self._apply_selection(None)

    def enter_ci_mode(self, on_arm: Callable[[str | None], None]) -> None:
        """Swap palette to Canvas Item placement mode."""
        self._on_ci_arm = on_arm
        self._ci_armed  = "__none__"
        # Hide normal content
        self._scroll_sb.pack_forget()
        self._scroll_canvas.pack_forget()
        self._widgets_header.pack_forget()
        self._widgets_sep.pack_forget()
        # Show CI frame
        self._ci_frame.pack(fill="both", expand=True)
        self.set_ci_armed(None)  # highlight Select

    def exit_ci_mode(self) -> None:
        """Restore normal widget palette."""
        if self._on_ci_arm is None:
            return
        self._ci_frame.pack_forget()
        self._on_ci_arm = None
        self._ci_armed  = "__none__"
        # Restore normal content
        self._widgets_header.pack(fill="x", pady=(8, 2))
        self._widgets_sep.pack(fill="x")
        self._scroll_sb.pack(side="right", fill="y")
        self._scroll_canvas.pack(side="left", fill="both", expand=True)

    def set_ci_armed(self, kind: str | None) -> None:
        """Update highlighted tool in CI mode."""
        old = self._ci_armed
        if old in self._ci_rows:
            row = self._ci_rows[old]
            row.config(bg=_ITEM)
            row._accent.config(bg=_ITEM)  # type: ignore[attr-defined]
            for child in row.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg=_ITEM)
        self._ci_armed = kind  # type: ignore[assignment]
        if kind in self._ci_rows:
            row = self._ci_rows[kind]
            row.config(bg=_ACT)
            row._accent.config(bg=_BORDER)  # type: ignore[attr-defined]
            for child in row.winfo_children():
                if not isinstance(child, tk.Canvas):
                    child.config(bg=_ACT)

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

    def _comp_add(self, type_key: str) -> None:
        if self._on_component_add:
            self._on_component_add(type_key)

    def _comp_hover(self, row: tk.Frame, accent: tk.Frame,
                    icon_lbl: tk.Label, name_lbl: tk.Label,
                    entering: bool) -> None:
        bg = "#3e3e42" if entering else _ITEM
        row.config(bg=bg)
        accent.config(bg=bg)
        icon_lbl.config(bg=bg)
        name_lbl.config(bg=bg)

    def _ci_select(self, kind: str | None) -> None:
        self.set_ci_armed(kind)
        if self._on_ci_arm:
            self._on_ci_arm(kind)

    def _ci_hover(self, row: tk.Frame, kind: str | None, entering: bool) -> None:
        if kind == self._ci_armed:
            return
        bg = "#3e3e42" if entering else _ITEM
        row.config(bg=bg)
        for child in row.winfo_children():
            if not isinstance(child, tk.Canvas):
                child.config(bg=bg)

    # ── Pointer tool preview ──────────────────────────────────────────────────

    @staticmethod
    def _draw_pointer(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        cx, cy = x + w // 2, y + h // 2
        pts = [cx, cy-8, cx+5, cy+2, cx+2, cy+1, cx+3, cy+6,
               cx+1, cy+6, cx, cy+2, cx-3, cy+4]
        c.create_polygon(pts, fill="#cccccc", outline="#888888", width=1)

    @staticmethod
    def _draw_ci_rect(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        m = 4
        c.create_rectangle(x + m, y + m, x + w - m, y + h - m,
                            outline="#4ec9b0", fill="", width=1.5)

    @staticmethod
    def _draw_ci_oval(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        m = 4
        c.create_oval(x + m, y + m, x + w - m, y + h - m,
                      outline="#ce9178", fill="", width=1.5)

    @staticmethod
    def _draw_ci_image(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        m = 4
        c.create_rectangle(x + m, y + m, x + w - m, y + h - m,
                            outline="#569cd6", fill="", width=1)
        cx = x + w // 2
        my = y + h - m - 2
        c.create_polygon([cx - 5, my, cx, y + m + 3, cx + 5, my],
                         outline="#569cd6", fill="", width=1)

    @staticmethod
    def _draw_ci_text(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        c.create_text(x + w // 2, y + h // 2, text="T",
                      fill="#d4d4d4", font=("Consolas", 11, "bold"), anchor="center")

    @staticmethod
    def _draw_ci_line(c: tk.Canvas, x: int, y: int, w: int, h: int) -> None:
        m = 5
        c.create_line(x + m, y + h - m, x + w - m, y + m,
                      fill="#9cdcfe", width=2)
