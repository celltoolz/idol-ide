from __future__ import annotations

import tkinter as tk
from typing import Callable

from .registry import normalize_tree_columns
from widgets.styled_checkbox import StyledCheckbox
from utils.ui_font import UI_FONT

_BG       = "#1e1e1e"
_BG2      = "#2d2d2d"
_FG       = "#cccccc"
_FG_DIM   = "#858585"
_ACCENT   = "#569cd6"
_BTN_BG   = "#3a3a3a"
_ENTRY_BG = "#3c3c3c"
_BORDER   = "#3c3c3c"

_ANCHOR_CYCLE = ["w", "center", "e"]
_ANCHOR_LABEL = {"w": "left", "center": "center", "e": "right"}


class TreeviewColumnEditor(tk.Toplevel):
    """Dialog for editing a Treeview's columns: id, heading, width, anchor, stretch.

    Works on an internal copy; calls ``on_save(columns)`` with a normalized list
    of column dicts only when the user clicks Save.
    """

    def __init__(self, parent, columns, on_save: Callable[[list[dict]], None]) -> None:
        super().__init__(parent)
        self._on_save = on_save
        self._rows: list[dict] = []  # one dict of widgets/vars per column row

        self.title("Treeview Columns")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.withdraw()

        tk.Label(self, text="Columns", bg=_BG, fg=_FG,
                 font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(self,
                 text="Leave ID blank to auto-derive it from the heading.",
                 bg=_BG, fg=_FG_DIM, font=(UI_FONT, 8)).pack(anchor="w", padx=14)

        # Header labels
        hdr = tk.Frame(self, bg=_BG)
        hdr.pack(fill="x", padx=14, pady=(10, 2))
        for text, w in (("ID", 10), ("Heading", 20), ("Width", 7),
                        ("Anchor", 8), ("Stretch", 8), ("", 8)):
            tk.Label(hdr, text=text, bg=_BG, fg=_FG_DIM, font=(UI_FONT, 8, "bold"),
                     width=w, anchor="w").pack(side="left", padx=(0, 4))

        # Rows container
        self._rows_frame = tk.Frame(self, bg=_BG)
        self._rows_frame.pack(fill="x", padx=14)

        for col in normalize_tree_columns(columns):
            self._add_row(col)
        if not self._rows:
            self._add_row(None)

        # Add-column button
        add = tk.Label(self, text="  ＋ Add Column  ", bg=_BTN_BG, fg=_FG,
                       font=(UI_FONT, 9), cursor="hand2", padx=4, pady=3)
        add.pack(anchor="w", padx=14, pady=(8, 4))
        add.bind("<ButtonRelease-1>", lambda e: self._add_row(None))

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x", padx=14, pady=(6, 0))

        # OK / Cancel
        btns = tk.Frame(self, bg=_BG)
        btns.pack(fill="x", padx=14, pady=(8, 12))
        self._make_btn(btns, "Cancel", self.destroy)
        self._make_btn(btns, "Save", self._save, accent=True)

        self.bind("<Escape>", lambda e: self.destroy())
        self._center(parent)
        self.deiconify()
        self.grab_set()

    # ── Row management ─────────────────────────────────────────────────────────

    def _add_row(self, col: "dict | None") -> None:
        rf = tk.Frame(self._rows_frame, bg=_BG)
        rf.pack(fill="x", pady=1)

        id_e = self._entry(rf, width=10)
        id_e.insert(0, col["id"] if col else "")
        head_e = self._entry(rf, width=20)
        head_e.insert(0, col["heading"] if col else f"Column {len(self._rows) + 1}")
        width_e = self._entry(rf, width=7)
        width_e.insert(0, str(col["width"]) if col else "120")

        anchor_var = tk.StringVar(value=(col["anchor"] if col else "w"))
        anchor_btn = tk.Label(rf, bg=_ENTRY_BG, fg=_FG, font=(UI_FONT, 8),
                              width=8, anchor="w", cursor="hand2", padx=4, pady=2)
        anchor_btn.pack(side="left", padx=(0, 4))
        def _cycle(_=None, v=anchor_var, b=anchor_btn):
            nxt = _ANCHOR_CYCLE[(_ANCHOR_CYCLE.index(v.get()) + 1) % len(_ANCHOR_CYCLE)]
            v.set(nxt)
            b.config(text=_ANCHOR_LABEL[nxt])
        anchor_btn.config(text=_ANCHOR_LABEL[anchor_var.get()])
        anchor_btn.bind("<ButtonRelease-1>", _cycle)

        stretch_var = tk.BooleanVar(value=(col["stretch"] if col else True))
        stretch_holder = tk.Frame(rf, bg=_BG, width=64)
        stretch_holder.pack(side="left", padx=(0, 4))
        stretch_holder.pack_propagate(False)
        StyledCheckbox(stretch_holder, "", stretch_var, bg=_BG).pack(side="left")

        actions = tk.Frame(rf, bg=_BG)
        actions.pack(side="left")
        row = {"frame": rf, "id": id_e, "heading": head_e, "width": width_e,
               "anchor": anchor_var, "stretch": stretch_var}
        for glyph, cmd in (("↑", lambda r=row: self._move(r, -1)),
                           ("↓", lambda r=row: self._move(r, +1)),
                           ("×", lambda r=row: self._remove(r))):
            lbl = tk.Label(actions, text=glyph, bg=_BG, fg=_FG_DIM,
                           font=(UI_FONT, 10), cursor="hand2", width=2)
            lbl.pack(side="left")
            lbl.bind("<ButtonRelease-1>", lambda e, c=cmd: c())
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(fg=_ACCENT))
            lbl.bind("<Leave>", lambda e, w=lbl: w.config(fg=_FG_DIM))

        self._rows.append(row)
        self._resize()

    def _remove(self, row: dict) -> None:
        if len(self._rows) <= 1:
            return  # keep at least one column
        row["frame"].destroy()
        self._rows.remove(row)
        self._resize()

    def _move(self, row: dict, delta: int) -> None:
        i = self._rows.index(row)
        j = i + delta
        if not (0 <= j < len(self._rows)):
            return
        self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
        for r in self._rows:
            r["frame"].pack_forget()
        for r in self._rows:
            r["frame"].pack(fill="x", pady=1)

    # ── Save ───────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        cols: list[dict] = []
        for r in self._rows:
            heading = r["heading"].get().strip()
            if not heading and not r["id"].get().strip():
                continue  # skip fully blank rows
            try:
                width = int(r["width"].get().strip() or 120)
            except ValueError:
                width = 120
            cols.append({
                "id":      r["id"].get().strip(),
                "heading": heading,
                "width":   max(20, width),
                "anchor":  r["anchor"].get(),
                "stretch": bool(r["stretch"].get()),
            })
        self._on_save(normalize_tree_columns(cols))
        self.destroy()

    # ── Widget helpers ───────────────────────────────────────────────────────

    def _entry(self, parent, width: int) -> tk.Entry:
        e = tk.Entry(parent, width=width, bg=_ENTRY_BG, fg=_FG,
                     insertbackground=_FG, relief="flat",
                     font=(UI_FONT, 9), highlightthickness=1,
                     highlightbackground=_BORDER, highlightcolor=_ACCENT)
        e.pack(side="left", padx=(0, 4), ipady=2)
        return e

    def _make_btn(self, parent, text, cmd, accent=False) -> None:
        b = tk.Label(parent, text=text, bg=_ACCENT if accent else _BTN_BG,
                     fg="#ffffff" if accent else _FG, font=(UI_FONT, 9),
                     cursor="hand2", padx=12, pady=4)
        b.pack(side="right", padx=(6, 0))
        b.bind("<ButtonRelease-1>", lambda e: cmd())

    def _resize(self) -> None:
        self.update_idletasks()

    def _center(self, parent) -> None:
        self.update_idletasks()
        try:
            px = parent.winfo_rootx() + parent.winfo_width() // 2
            py = parent.winfo_rooty() + parent.winfo_height() // 2
            self.geometry(f"+{px - self.winfo_reqwidth() // 2}"
                          f"+{max(0, py - self.winfo_reqheight() // 2)}")
        except Exception:
            pass
