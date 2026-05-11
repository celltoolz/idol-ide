"""CompletionPopup — keyboard-navigable autocomplete dropdown."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from widgets.scrollbar import VerticalScrollbar

# LSP CompletionItemKind → short label
_KIND = {
    1:  "txt", 2:  " mt", 3:  " fn", 4:  "ctr", 5:  " fd",
    6:  " vr", 7:  " cl", 8:  "ifc", 9:  " md", 10: " pr",
    11: "val", 12: "enm", 13: "kw ", 14: " kw", 15: "snp",
    16: "ref", 17: "fld", 18: "evt", 19: "ops", 20: "typ",
    21: "prm", 22: "str",
}
_DEFAULT_KIND = "   "


class CompletionPopup:
    """Borderless listbox popup that sits below the editor cursor."""

    MAX_ROWS = 12

    def __init__(self, master: tk.Misc,
                 on_accept: Optional[Callable[[], None]] = None) -> None:
        self._master    = master
        self._on_accept = on_accept
        self._win: tk.Toplevel | None = None
        self._lb:  tk.Listbox | None = None
        self._items: list[dict] = []

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def visible(self) -> bool:
        return (self._win is not None
                and self._win.winfo_exists()
                and self._win.winfo_ismapped())

    def show(self, items: list[dict], root_x: int, root_y: int) -> None:
        """Populate and position the popup. Hides if *items* is empty."""
        if not items:
            self.hide()
            return

        self._items = items
        self._ensure_window()

        self._lb.delete(0, "end")
        for item in items:
            kind   = _KIND.get(item.get("kind", 0), _DEFAULT_KIND)
            label  = item.get("label", "")
            detail = (item.get("detail") or "").strip()
            if detail and len(detail) > 36:
                detail = detail[:35] + "…"
            row = f" {kind}  {label}"
            if detail:
                row += f"  —  {detail}"
            self._lb.insert("end", row)

        rows = min(len(items), self.MAX_ROWS)
        self._lb.configure(height=rows)
        self._lb.selection_clear(0, "end")
        self._lb.selection_set(0)
        self._lb.see(0)
        self._win.geometry(f"+{root_x}+{root_y}")
        self._win.deiconify()
        self._win.lift()

    def hide(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.withdraw()
        self._items = []

    def destroy(self) -> None:
        if self._win and self._win.winfo_exists():
            self._win.destroy()
        self._win = None
        self._lb  = None

    def select_next(self) -> None:
        self._move(+1)

    def select_prev(self) -> None:
        self._move(-1)

    def reposition(self, root_x: int, root_y: int) -> None:
        """Move the popup to a new screen position (call when window is dragged)."""
        if self._win and self._win.winfo_exists():
            self._win.geometry(f"+{root_x}+{root_y}")

    def get_selected(self) -> dict | None:
        if not self._items:
            return None
        if self._lb is None:
            return self._items[0]
        sel = self._lb.curselection()
        idx = sel[0] if sel else 0
        return self._items[idx] if idx < len(self._items) else None

    # ── Internal ──────────────────────────────────────────────────────────────

    def _ensure_window(self) -> None:
        if self._win and self._win.winfo_exists():
            return
        self._win = tk.Toplevel(self._master)
        self._win.overrideredirect(True)
        self._win.wm_attributes("-topmost", True)
        # Use the Toplevel background as a 1 px border (avoids bd clipping content)
        self._win.configure(bg="#3c3c3c")

        outer = tk.Frame(self._win, bg="#1e1e1e", bd=0)
        outer.pack(fill="both", expand=True, padx=1, pady=1)

        self._lb = tk.Listbox(
            outer,
            bg="#1e1e1e", fg="#d4d4d4",
            selectbackground="#094771", selectforeground="#ffffff",
            font=("Consolas", 10),
            borderwidth=0,
            highlightthickness=0,
            activestyle="none",
            exportselection=False,
            width=30,          # fixed char width so scrollbar always fits
        )
        sb = VerticalScrollbar(outer, command=self._lb.yview)
        self._lb.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")        # pack scrollbar first so it's never squeezed
        self._lb.pack(side="left", fill="both", expand=True)

        # Single click selects; double-click accepts
        self._lb.bind("<ButtonRelease-1>", self._on_click)
        self._lb.bind("<Double-ButtonRelease-1>", self._on_double_click)

    def _on_click(self, event) -> None:
        """Single click — just update the selection (already handled by Listbox)."""
        pass

    def _on_double_click(self, _event) -> None:
        """Double-click — accept selected item."""
        if self._on_accept:
            self._on_accept()

    def _move(self, delta: int) -> None:
        if not self._items or self._lb is None:
            return
        sel = self._lb.curselection()
        idx = (sel[0] + delta) if sel else 0
        idx = max(0, min(idx, len(self._items) - 1))
        self._lb.selection_clear(0, "end")
        self._lb.selection_set(idx)
        self._lb.see(idx)
