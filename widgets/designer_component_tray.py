from __future__ import annotations

import tkinter as tk
from typing import Callable, Optional

from utils.ui_font import UI_FONT

_BG      = "#1e1e1e"
_CHIP    = "#2d2d30"
_CHIP_HV = "#3e3e42"
_CHIP_AC = "#094771"
_ACCENT  = "#007acc"
_FG      = "#cccccc"
_DIM     = "#555555"


class ComponentTray(tk.Frame):
    """Horizontal strip below the canvas showing non-visual component chips.

    Each chip is an icon + name label pair. Clicking selects the chip and
    fires on_select(comp_id). Right-clicking shows a popup with Rename/Delete.
    """

    def __init__(
        self,
        master,
        on_select:   Optional[Callable[[str], None]] = None,
        on_deselect: Optional[Callable[[], None]] = None,
        on_delete:   Optional[Callable[[str], None]] = None,
        on_rename:   Optional[Callable[[str, str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, height=36, **kwargs)
        self.pack_propagate(False)
        self._on_select   = on_select
        self._on_deselect = on_deselect
        self._on_delete   = on_delete
        self._on_rename   = on_rename

        self._selected: str | None = None
        self._chips:    dict[str, _Chip] = {}   # comp_id → chip widget

        # Empty-state label (shown when no components)
        self._empty = tk.Label(
            self, text="No components — add one from the palette",
            bg=_BG, fg=_DIM, font=(UI_FONT, 8),
        )
        self._empty.place(relx=0.5, rely=0.5, anchor="center")

        # Inner frame that holds chips side by side
        self._strip = tk.Frame(self, bg=_BG)
        self._strip.pack(side="left", fill="y", padx=(4, 0))

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, components: list) -> None:
        """Rebuild chips from a list of ComponentDescriptor objects (id, type, props)."""
        for chip in self._chips.values():
            chip.destroy()
        self._chips.clear()

        for comp in components:
            self._add_chip(comp.id, comp.type)

        self._sync_empty()
        # Re-apply selection highlight if still valid
        if self._selected and self._selected in self._chips:
            self._chips[self._selected].set_active(True)
        else:
            self._selected = None

    def select(self, comp_id: str) -> None:
        """Highlight *comp_id* chip without firing the callback."""
        self._apply_selection(comp_id)

    def deselect(self) -> None:
        """Clear the active chip without firing on_deselect."""
        self._apply_selection(None)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _add_chip(self, comp_id: str, type_key: str) -> None:
        from designer.component_registry import COMPONENT_REGISTRY
        icon = COMPONENT_REGISTRY.get(type_key, None)
        glyph = icon.icon if icon else "?"
        chip = _Chip(
            self._strip, comp_id, glyph,
            on_click=self._handle_click,
            on_right=self._handle_right,
        )
        chip.pack(side="left", padx=(0, 2), fill="y")
        self._chips[comp_id] = chip

    def _sync_empty(self) -> None:
        if self._chips:
            self._empty.place_forget()
        else:
            self._empty.place(relx=0.5, rely=0.5, anchor="center")

    def _handle_click(self, comp_id: str) -> None:
        if self._selected == comp_id:
            # Toggle off — deselect
            self._apply_selection(None)
            if self._on_deselect:
                self._on_deselect()
        else:
            self._apply_selection(comp_id)
            if self._on_select:
                self._on_select(comp_id)

    def _handle_right(self, comp_id: str, x_root: int, y_root: int) -> None:
        menu = tk.Menu(self, tearoff=0, bg="#2d2d30", fg="#cccccc",
                       activebackground="#094771", activeforeground="#ffffff",
                       font=(UI_FONT, 9), bd=0, relief="flat")
        menu.add_command(label="Rename…", command=lambda: self._do_rename(comp_id))
        menu.add_separator()
        menu.add_command(label="Delete", command=lambda: self._do_delete(comp_id))
        menu.tk_popup(x_root, y_root)

    def _do_rename(self, comp_id: str) -> None:
        dlg = _RenameDialog(self.winfo_toplevel(), comp_id)
        new_name = dlg.result
        if new_name and new_name != comp_id and self._on_rename:
            self._on_rename(comp_id, new_name)

    def _do_delete(self, comp_id: str) -> None:
        if self._selected == comp_id:
            self._apply_selection(None)
        if self._on_delete:
            self._on_delete(comp_id)

    def _apply_selection(self, comp_id: str | None) -> None:
        if self._selected and self._selected in self._chips:
            self._chips[self._selected].set_active(False)
        self._selected = comp_id
        if comp_id and comp_id in self._chips:
            self._chips[comp_id].set_active(True)


# ── Chip widget ───────────────────────────────────────────────────────────────

class _Chip(tk.Frame):
    """One icon+name chip in the tray."""

    def __init__(
        self,
        master,
        comp_id: str,
        glyph: str,
        on_click: Callable[[str], None],
        on_right: Callable[[str, int, int], None],
    ) -> None:
        super().__init__(master, bg=_CHIP, cursor="hand2",
                         padx=0, pady=0)
        self._comp_id = comp_id
        self._on_click = on_click
        self._on_right = on_right

        # Left blue accent bar (3px, shown when active)
        self._accent = tk.Frame(self, bg=_CHIP, width=3)
        self._accent.pack(side="left", fill="y")

        inner = tk.Frame(self, bg=_CHIP, padx=4, pady=0)
        inner.pack(side="left", fill="both", expand=True)

        icon_lbl = tk.Label(inner, text=glyph, bg=_CHIP, fg=_FG,
                            font=(UI_FONT, 11))
        icon_lbl.pack(side="left")

        name_lbl = tk.Label(inner, text=comp_id, bg=_CHIP, fg=_FG,
                            font=(UI_FONT, 8), padx=3)
        name_lbl.pack(side="left")

        self._inner  = inner
        self._labels = [icon_lbl, name_lbl]

        for w in [self, self._accent, inner, icon_lbl, name_lbl]:
            w.bind("<ButtonRelease-1>", lambda e: self._on_click(self._comp_id))
            w.bind("<Button-3>",
                   lambda e: self._on_right(self._comp_id, e.x_root, e.y_root))
            w.bind("<Enter>", lambda e: self._hover(True))
            w.bind("<Leave>", lambda e: self._hover(False))

    def set_active(self, active: bool) -> None:
        bg = _CHIP_AC if active else _CHIP
        ac = _ACCENT  if active else _CHIP
        self.config(bg=bg)
        self._accent.config(bg=ac)
        self._inner.config(bg=bg)
        for lbl in self._labels:
            lbl.config(bg=bg)

    def _hover(self, entering: bool) -> None:
        if self._is_active():
            return
        bg = _CHIP_HV if entering else _CHIP
        self.config(bg=bg)
        self._inner.config(bg=bg)
        for lbl in self._labels:
            lbl.config(bg=bg)

    def _is_active(self) -> bool:
        return self.cget("bg") == _CHIP_AC


# ── Rename dialog ─────────────────────────────────────────────────────────────

class _RenameDialog(tk.Toplevel):
    """Inline dialog to rename a component."""

    def __init__(self, parent: tk.Misc, current_name: str) -> None:
        super().__init__(parent)
        self.result: str | None = None
        self.title("Rename Component")
        self.resizable(False, False)
        self.configure(bg="#252526")
        self.transient(parent)
        self.grab_set()

        tk.Label(self, text="New name:", bg="#252526", fg="#cccccc",
                 font=(UI_FONT, 9)).pack(padx=12, pady=(10, 4), anchor="w")

        self._var = tk.StringVar(value=current_name)
        entry = tk.Entry(self, textvariable=self._var,
                         bg="#3c3c3c", fg="#cccccc",
                         insertbackground="#cccccc",
                         font=(UI_FONT, 9), relief="flat", bd=4)
        entry.pack(padx=12, fill="x")
        entry.select_range(0, "end")
        entry.focus_set()
        entry.bind("<Return>", lambda e: self._commit())
        entry.bind("<Escape>", lambda e: self.destroy())

        btn_row = tk.Frame(self, bg="#252526")
        btn_row.pack(fill="x", padx=12, pady=(8, 10))

        for text, cmd in [("Rename", self._commit), ("Cancel", self.destroy)]:
            tk.Label(btn_row, text=text, bg="#094771", fg="#ffffff",
                     font=(UI_FONT, 9), padx=10, pady=3, cursor="hand2"
                     ).pack(side="left", padx=(0, 6))
        # Re-bind properly with ButtonRelease-1 per project style
        for child in btn_row.winfo_children():
            t = child.cget("text")
            child.bind("<ButtonRelease-1>",
                       lambda e, c=(self._commit if t == "Rename" else self.destroy): c())

        self.wait_window()

    def _commit(self) -> None:
        name = self._var.get().strip()
        if name:
            self.result = name
        self.destroy()
