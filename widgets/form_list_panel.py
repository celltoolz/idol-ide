from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable, Optional
from utils.ui_font import UI_FONT

_BG        = "#252526"
_HDR_BG    = "#2d2d2d"
_SEC_BG    = "#1e1e1e"
_SEL       = "#094771"
_HOV       = "#2a2d2e"
_DROP_HL   = "#007acc"   # drop-target highlight
_FG        = "#cccccc"
_DIM       = "#858585"
_UNLINK_FG = "#cc6666"
_ROW_H          = 26
_ICON_X         = 10
_LABEL_X        = 26
_DRAG_THRESHOLD = 5   # pixels of movement before drag activates


class FormListPanel(tk.Frame):
    """Tree panel above the designer palette.

    Shows main forms at top level and their linked dialogs indented below.
    Unlinked dialogs appear in a separate section at the bottom.

    Callbacks
    ---------
    on_select(name)              – click on any row
    on_new()                     – + button pressed
    on_link(dialog, form)        – drag dialog dropped onto a form row
    on_unlink(dialog, form)      – × clicked on a linked dialog row
    on_delete(name)              – × clicked on a form/unlinked-dialog row
    """

    def __init__(
        self,
        master,
        on_select: Optional[Callable[[str], None]] = None,
        on_new:    Optional[Callable[[], None]]    = None,
        on_link:   Optional[Callable[[str, str], None]] = None,
        on_unlink: Optional[Callable[[str, str], None]] = None,
        on_delete: Optional[Callable[[str], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=_BG, **kwargs)
        self._on_select = on_select
        self._on_new    = on_new
        self._on_link   = on_link
        self._on_unlink = on_unlink
        self._on_delete = on_delete

        self._forms:  list[tuple[str, str]] = []  # [(name, form_type), ...]
        self._links:  dict[str, list[str]]  = {}  # {form_name: [dialog_names]}
        self._active: str | None = None

        # Drag state
        self._drag_name:    str | None  = None   # dialog being dragged (confirmed)
        self._drag_parent:  str | None  = None   # its current parent form (if linked)
        self._drag_pending: dict | None = None   # press recorded, waiting for threshold
        self._drop_idx:     int | None  = None   # row index highlighted as drop target
        self._hov_idx:      int | None  = None
        self._rows:         list[dict]  = []     # built by _build_rows()
        self._ghost:        tk.Toplevel | None = None  # floating drag preview

        self._build_ui()

    # ── Construction ──────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        hdr = tk.Frame(self, bg=_HDR_BG, height=24)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        tk.Label(
            hdr, text="FORMS", bg=_HDR_BG, fg=_DIM,
            font=(UI_FONT, 8, "bold"), anchor="w", padx=8,
        ).pack(side="left")

        self._add_lbl = tk.Label(
            hdr, text="+", bg=_HDR_BG, fg=_DIM,
            font=(UI_FONT, 12), cursor="hand2", padx=8,
        )
        self._add_lbl.pack(side="right")
        self._add_lbl.bind("<Enter>", lambda _: self._add_lbl.config(fg=_FG))
        self._add_lbl.bind("<Leave>", lambda _: self._add_lbl.config(fg=_DIM))
        self._add_lbl.bind("<Button-1>", lambda _: self._on_new and self._on_new())

        self._canvas = tk.Canvas(self, bg=_BG, highlightthickness=0, bd=0)
        self._canvas.pack(fill="both", expand=True)
        self._canvas.bind("<Motion>",          self._motion)
        self._canvas.bind("<Leave>",           self._leave)
        self._canvas.bind("<ButtonPress-1>",   self._drag_start)
        self._canvas.bind("<B1-Motion>",       self._drag_motion)
        self._canvas.bind("<ButtonRelease-1>", self._drag_release)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

    # ── Public API ────────────────────────────────────────────────────────────

    def set_forms(
        self,
        forms:  list[tuple[str, str]],
        links:  dict[str, list[str]] | None = None,
        active: str | None = None,
    ) -> None:
        """Refresh the tree.

        forms  – [(name, form_type), ...]
        links  – {form_name: [dialog_name, ...]}
        active – currently active form/dialog name
        """
        self._forms  = list(forms)
        self._links  = {k: list(v) for k, v in (links or {}).items()}
        self._active = active
        self._hov_idx  = None
        self._drop_idx = None
        self._rows = self._build_rows()
        self._redraw()
        self._sync_height()

    def set_active(self, name: str | None) -> None:
        self._active = name
        self._redraw()

    # ── Row building ──────────────────────────────────────────────────────────

    def _build_rows(self) -> list[dict]:
        rows: list[dict] = []
        all_linked: set[str] = set()

        for fname, ftype in self._forms:
            if ftype == "main":
                rows.append({"kind": "form", "name": fname, "parent": None, "indent": 0})
                for dname in self._links.get(fname, []):
                    rows.append({"kind": "linked", "name": dname, "parent": fname, "indent": 1})
                    all_linked.add(dname)

        unlinked = [
            (n, t) for n, t in self._forms
            if t != "main" and n not in all_linked
        ]
        if unlinked:
            rows.append({"kind": "section", "name": "Unlinked", "parent": None, "indent": 0})
            for dname, _ in unlinked:
                rows.append({"kind": "dialog", "name": dname, "parent": None, "indent": 1})

        return rows

    # ── Drawing ───────────────────────────────────────────────────────────────

    def _sync_height(self) -> None:
        h = max(_ROW_H, len(self._rows) * _ROW_H)
        self._canvas.configure(height=h)

    def _redraw(self) -> None:
        c = self._canvas
        c.delete("all")
        cw = max(c.winfo_width(), 160)

        for i, row in enumerate(self._rows):
            y0 = i * _ROW_H
            y1 = y0 + _ROW_H
            kind   = row["kind"]
            name   = row["name"]
            indent = row["indent"]
            is_active  = name == self._active and kind != "section"
            is_hov     = i == self._hov_idx and kind != "section"
            is_drop    = i == self._drop_idx

            # Background
            if is_drop:
                bg = _DROP_HL
            elif is_active:
                bg = _SEL
            elif kind == "section":
                bg = _SEC_BG
            elif is_hov:
                bg = _HOV
            else:
                bg = _BG

            c.create_rectangle(0, y0, cw, y1, fill=bg, outline="")

            x = _ICON_X + indent * 14

            if kind == "section":
                # Dim separator label
                c.create_line(4, (y0 + y1) // 2, x - 2, (y0 + y1) // 2,
                              fill="#444", width=1)
                c.create_text(x, (y0 + y1) // 2, text=name, fill="#555",
                              font=(UI_FONT, 7, "bold"), anchor="w")
                continue

            # Icon — drawn as canvas primitives for cross-platform consistency
            if kind == "form":
                icon_fg = "#569cd6"
            else:
                icon_fg = "#9cdcfe" if kind == "linked" else "#858585"

            cy = (y0 + y1) // 2
            if kind == "form":
                # Miniature window: outer rect + title-bar line
                c.create_rectangle(x, cy - 5, x + 11, cy + 4,
                                   outline=icon_fg, fill="", width=1)
                c.create_line(x + 1, cy - 2, x + 10, cy - 2,
                              fill=icon_fg, width=1)
            else:
                # Two overlapping windows (dialog)
                c.create_rectangle(x + 3, cy - 5, x + 11, cy + 2,
                                   outline=icon_fg, fill=bg, width=1)
                c.create_line(x + 4, cy - 3, x + 10, cy - 3,
                              fill=icon_fg, width=1)
                c.create_rectangle(x, cy - 2, x + 8, cy + 4,
                                   outline=icon_fg, fill=bg, width=1)
                c.create_line(x + 1, cy, x + 7, cy,
                              fill=icon_fg, width=1)

            # Name
            label_x = x + 16
            fg = _FG if is_active else (_FG if kind == "linked" else _DIM)
            c.create_text(label_x, (y0 + y1) // 2, text=name, fill=fg,
                          font=(UI_FONT, 9), anchor="w")

            # × button on hover — unlink for linked dialogs, delete for forms/unlinked dialogs
            if is_hov and not self._drag_name:
                if kind == "linked":
                    c.create_text(
                        cw - 8, (y0 + y1) // 2,
                        text="×", fill=_UNLINK_FG,
                        font=(UI_FONT, 10, "bold"), anchor="e",
                        tags=(f"unlink_{i}",),
                    )
                elif kind in ("form", "dialog"):
                    c.create_text(
                        cw - 8, (y0 + y1) // 2,
                        text="×", fill=_UNLINK_FG,
                        font=(UI_FONT, 10, "bold"), anchor="e",
                        tags=(f"delete_{i}",),
                    )

    # ── Mouse: click ──────────────────────────────────────────────────────────

    def _idx_at(self, y: int) -> int | None:
        i = y // _ROW_H
        return i if 0 <= i < len(self._rows) else None

    def _motion(self, event: tk.Event) -> None:
        if self._drag_name:
            return  # handled by _drag_motion
        idx = self._idx_at(event.y)
        row = self._rows[idx] if idx is not None else None
        new_hov = idx if (row and row["kind"] != "section") else None
        if new_hov != self._hov_idx:
            self._hov_idx = new_hov
            self._redraw()

    def _leave(self, _event: tk.Event) -> None:
        if self._hov_idx is not None or self._drop_idx is not None:
            self._hov_idx  = None
            self._drop_idx = None
            self._redraw()

    # ── Mouse: drag-to-link ───────────────────────────────────────────────────

    def _drag_start(self, event: tk.Event) -> None:
        idx = self._idx_at(event.y)
        if idx is None:
            return
        row = self._rows[idx]
        if row["kind"] not in ("linked", "dialog"):
            return
        # Record the press — drag activates only after threshold movement
        self._drag_pending = {
            "name":    row["name"],
            "parent":  row.get("parent"),
            "start_x": event.x_root,
            "start_y": event.y_root,
        }

    def _drag_motion(self, event: tk.Event) -> None:
        if self._drag_name:
            # Active drag — move ghost and update drop target
            self._move_ghost(event.x_root, event.y_root)
            idx = self._idx_at(event.y)
            new_drop = idx if (idx is not None and self._rows[idx]["kind"] == "form") else None
            if new_drop != self._drop_idx:
                self._drop_idx = new_drop
                self._redraw()
        elif self._drag_pending:
            # Check if the mouse has moved far enough to commit to a drag
            dx = abs(event.x_root - self._drag_pending["start_x"])
            dy = abs(event.y_root - self._drag_pending["start_y"])
            if dx > _DRAG_THRESHOLD or dy > _DRAG_THRESHOLD:
                self._drag_name   = self._drag_pending["name"]
                self._drag_parent = self._drag_pending["parent"]
                self._drag_pending = None
                self._drop_idx    = None
                self._canvas.config(cursor="fleur")
                self._show_ghost(self._drag_name, event.x_root, event.y_root)

    def _drag_release(self, event: tk.Event) -> None:
        self._drag_pending = None  # always clear pending on release

        if self._drag_name:
            dialog_name   = self._drag_name
            drag_parent   = self._drag_parent
            self._drag_name   = None
            self._drag_parent = None
            drop_idx          = self._drop_idx
            self._drop_idx    = None
            self._hide_ghost()
            self._canvas.config(cursor="")

            if drop_idx is not None and drop_idx < len(self._rows):
                target_row = self._rows[drop_idx]
                if target_row["kind"] == "form":
                    target_form = target_row["name"]
                    if drag_parent and drag_parent != target_form:
                        if self._on_unlink:
                            self._on_unlink(dialog_name, drag_parent)
                    if target_form != drag_parent:
                        if self._on_link:
                            self._on_link(dialog_name, target_form)
                        return
            self._redraw()
        else:
            # No drag crossed the threshold — treat as a plain click
            idx = self._idx_at(event.y)
            if idx is None:
                return
            row = self._rows[idx]
            if row["kind"] == "section":
                return
            cw = self._canvas.winfo_width()
            if row["kind"] == "linked" and event.x >= cw - 20:
                if self._on_unlink:
                    self._on_unlink(row["name"], row["parent"])
                return
            if row["kind"] in ("form", "dialog") and event.x >= cw - 20:
                if self._on_delete:
                    self._on_delete(row["name"])
                return
            if self._on_select:
                self._on_select(row["name"])

    # ── Ghost drag preview ────────────────────────────────────────────────────

    def _show_ghost(self, name: str, x_root: int, y_root: int) -> None:
        self._hide_ghost()
        win = tk.Toplevel(self)
        win.overrideredirect(True)
        win.wm_attributes("-topmost", True)
        try:
            win.wm_attributes("-alpha", 0.82)
        except Exception:
            pass
        win.configure(bg="#094771")
        tk.Label(
            win,
            text=f"  {name}  ",
            bg="#094771",
            fg="#ffffff",
            font=(UI_FONT, 9),
            padx=4,
            pady=3,
        ).pack()
        win.update_idletasks()
        self._ghost = win
        self._move_ghost(x_root, y_root)

    def _move_ghost(self, x_root: int, y_root: int) -> None:
        if self._ghost is None:
            return
        try:
            self._ghost.geometry(f"+{x_root + 14}+{y_root + 6}")
        except Exception:
            pass

    def _hide_ghost(self) -> None:
        if self._ghost is not None:
            try:
                self._ghost.destroy()
            except Exception:
                pass
            self._ghost = None
