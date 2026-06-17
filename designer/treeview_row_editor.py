from __future__ import annotations

import tkinter as tk
from typing import Callable

from .registry import normalize_tree_columns, normalize_tree_rows
from utils.ui_font import UI_FONT

_BG       = "#1e1e1e"
_FG       = "#cccccc"
_FG_DIM   = "#858585"
_ACCENT   = "#569cd6"
_BTN_BG   = "#3a3a3a"
_ENTRY_BG = "#3c3c3c"
_BORDER   = "#3c3c3c"


class TreeviewRowEditor(tk.Toplevel):
    """Dialog for editing a Treeview's seed rows.

    The grid columns are derived from the widget's current columns (plus a
    ``(tree)`` cell for the ``#0`` label when ``show`` includes the tree column).
    Calls ``on_save(rows)`` with a list of ``{text, values}`` dicts on Save.
    """

    def __init__(self, parent, columns, rows, show: str,
                 on_save: Callable[[list[dict]], None]) -> None:
        super().__init__(parent)
        self._on_save = on_save
        self._cols = normalize_tree_columns(columns)
        self._rows: list[list] = []  # one list of cell-entries per row

        # Field descriptors: ("text", label) for #0, then (col_index, heading).
        self._fields: list[tuple] = []
        if "tree" in show:
            self._fields.append(("text", "(tree)"))
        for i, col in enumerate(self._cols):
            self._fields.append((i, col["heading"] or f"Column {i + 1}"))

        self.title("Treeview Rows")
        self.configure(bg=_BG)
        self.resizable(False, False)
        self.transient(parent)
        self.withdraw()

        tk.Label(self, text="Rows", bg=_BG, fg=_FG,
                 font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=14, pady=(12, 2))
        tk.Label(self, text="Seed rows inserted at startup — clear or replace them in code.",
                 bg=_BG, fg=_FG_DIM, font=(UI_FONT, 8)).pack(anchor="w", padx=14)

        if not self._fields:
            tk.Label(self, text="Add columns (or enable the tree column) first.",
                     bg=_BG, fg=_FG_DIM, font=(UI_FONT, 9)).pack(
                         anchor="w", padx=14, pady=(12, 0))
        else:
            # Header labels aligned to the cell entries
            hdr = tk.Frame(self, bg=_BG)
            hdr.pack(fill="x", padx=14, pady=(10, 2))
            for _, label in self._fields:
                tk.Label(hdr, text=label, bg=_BG, fg=_FG_DIM,
                         font=(UI_FONT, 8, "bold"), width=14, anchor="w").pack(
                             side="left", padx=(0, 4))
            tk.Label(hdr, text="", bg=_BG, width=8).pack(side="left")

        self._rows_frame = tk.Frame(self, bg=_BG)
        self._rows_frame.pack(fill="x", padx=14)

        for r in normalize_tree_rows(rows):
            self._add_row(r)

        if self._fields:
            add = tk.Label(self, text="  ＋ Add Row  ", bg=_BTN_BG, fg=_FG,
                           font=(UI_FONT, 9), cursor="hand2", padx=4, pady=3)
            add.pack(anchor="w", padx=14, pady=(8, 4))
            add.bind("<ButtonRelease-1>", lambda e: self._add_row(None))

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x", padx=14, pady=(6, 0))

        btns = tk.Frame(self, bg=_BG)
        btns.pack(fill="x", padx=14, pady=(8, 12))
        self._make_btn(btns, "Cancel", self.destroy)
        self._make_btn(btns, "Save", self._save, accent=True)

        self.bind("<Escape>", lambda e: self.destroy())
        self._center(parent)
        self.deiconify()
        self.grab_set()

    # ── Rows ────────────────────────────────────────────────────────────────

    def _add_row(self, rowdata: "dict | None") -> None:
        rf = tk.Frame(self._rows_frame, bg=_BG)
        rf.pack(fill="x", pady=1)
        cells: list[tuple] = []
        for key, _label in self._fields:
            e = tk.Entry(rf, width=14, bg=_ENTRY_BG, fg=_FG, insertbackground=_FG,
                         relief="flat", font=(UI_FONT, 9), highlightthickness=1,
                         highlightbackground=_BORDER, highlightcolor=_ACCENT)
            e.pack(side="left", padx=(0, 4), ipady=2)
            if rowdata is not None:
                if key == "text":
                    e.insert(0, rowdata.get("text", ""))
                else:
                    vals = rowdata.get("values", [])
                    e.insert(0, vals[key] if key < len(vals) else "")
            cells.append((key, e))

        entry = (rf, cells)
        actions = tk.Frame(rf, bg=_BG)
        actions.pack(side="left")
        for glyph, cmd in (("↑", lambda r=entry: self._move(r, -1)),
                           ("↓", lambda r=entry: self._move(r, +1)),
                           ("×", lambda r=entry: self._remove(r))):
            lbl = tk.Label(actions, text=glyph, bg=_BG, fg=_FG_DIM,
                           font=(UI_FONT, 10), cursor="hand2", width=2)
            lbl.pack(side="left")
            lbl.bind("<ButtonRelease-1>", lambda e, c=cmd: c())
            lbl.bind("<Enter>", lambda e, w=lbl: w.config(fg=_ACCENT))
            lbl.bind("<Leave>", lambda e, w=lbl: w.config(fg=_FG_DIM))

        self._rows.append(entry)

    def _remove(self, entry: tuple) -> None:
        entry[0].destroy()
        self._rows.remove(entry)

    def _move(self, entry: tuple, delta: int) -> None:
        i = self._rows.index(entry)
        j = i + delta
        if not (0 <= j < len(self._rows)):
            return
        self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
        for r in self._rows:
            r[0].pack_forget()
        for r in self._rows:
            r[0].pack(fill="x", pady=1)

    # ── Save ────────────────────────────────────────────────────────────────

    def _save(self) -> None:
        out: list[dict] = []
        ncols = len(self._cols)
        for _rf, cells in self._rows:
            text = ""
            values = [""] * ncols
            for key, entry in cells:
                v = entry.get()
                if key == "text":
                    text = v
                elif isinstance(key, int) and key < ncols:
                    values[key] = v
            if not text.strip() and not any(s.strip() for s in values):
                continue
            out.append({"text": text, "values": values})
        self._on_save(out)
        self.destroy()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_btn(self, parent, text, cmd, accent=False) -> None:
        b = tk.Label(parent, text=text, bg=_ACCENT if accent else _BTN_BG,
                     fg="#ffffff" if accent else _FG, font=(UI_FONT, 9),
                     cursor="hand2", padx=12, pady=4)
        b.pack(side="right", padx=(6, 0))
        b.bind("<ButtonRelease-1>", lambda e: cmd())

    def _center(self, parent) -> None:
        self.update_idletasks()
        rw, rh = self.winfo_reqwidth(), self.winfo_reqheight()
        try:
            px = parent.winfo_rootx() + parent.winfo_width() // 2 - rw // 2
            py = parent.winfo_rooty() + parent.winfo_height() // 2 - rh // 2
        except Exception:
            px, py = 200, 200
        # Clamp inside the screen so a maximized parent can't push us off-edge
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        px = max(0, min(px, sw - rw))
        py = max(0, min(py, sh - rh))
        self.geometry(f"+{px}+{py}")
