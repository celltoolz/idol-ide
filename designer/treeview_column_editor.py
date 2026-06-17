from __future__ import annotations

import tkinter as tk
from typing import Callable

from .registry import normalize_tree_columns
from .toolbar import _add_tooltip
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

_ANCHOR_VALUES = ["w", "center", "e"]
_ANCHOR_LABEL  = {"w": "left", "center": "center", "e": "right"}

# Grid column index per field — headers and cells share these so they align.
_C_ID, _C_HEAD, _C_WIDTH, _C_ANCHOR, _C_STRETCH, _C_UP, _C_DOWN, _C_DEL = range(8)


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

        # One grid hosts both the header row and the data rows so columns align.
        self._grid = tk.Frame(self, bg=_BG)
        self._grid.pack(fill="x", padx=14, pady=(10, 2))
        for col, text in ((_C_ID, "ID"), (_C_HEAD, "Heading"), (_C_WIDTH, "Width"),
                          (_C_ANCHOR, "Anchor"), (_C_STRETCH, "Stretch")):
            tk.Label(self._grid, text=text, bg=_BG, fg=_FG_DIM,
                     font=(UI_FONT, 8, "bold"), anchor="w").grid(
                         row=0, column=col, sticky="w", padx=(0, 8), pady=(0, 3))

        for col in normalize_tree_columns(columns):
            self._add_row(col)
        if not self._rows:
            self._add_row(None)
        self._regrid()

        # Add-column button
        add = tk.Label(self, text="  ＋ Add Column  ", bg=_BTN_BG, fg=_FG,
                       font=(UI_FONT, 9), cursor="hand2", padx=4, pady=3)
        add.pack(anchor="w", padx=14, pady=(8, 4))
        add.bind("<ButtonRelease-1>", lambda e: (self._add_row(None), self._regrid()))

        tk.Frame(self, bg=_BORDER, height=1).pack(fill="x", padx=14, pady=(6, 0))

        # Save / Cancel
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
        g = self._grid
        id_e = self._entry(g, width=10)
        id_e.insert(0, col["id"] if col else "")
        head_e = self._entry(g, width=20)
        head_e.insert(0, col["heading"] if col else f"Column {len(self._rows) + 1}")
        width_e = self._entry(g, width=6)
        width_e.insert(0, str(col["width"]) if col else "120")

        anchor_var = tk.StringVar(value=(col["anchor"] if col else "w"))
        anchor_btn = tk.Label(g, bg=_ENTRY_BG, fg=_FG, font=(UI_FONT, 9),
                              anchor="w", cursor="hand2", padx=6, pady=3,
                              relief="solid", bd=1, width=8)

        def _set_anchor(val, v=anchor_var, b=anchor_btn):
            v.set(val)
            b.config(text=f"{_ANCHOR_LABEL[val]}  ▾")

        def _open_anchor_menu(_=None, b=anchor_btn, setter=_set_anchor):
            m = tk.Menu(self, tearoff=0, bg=_BG2, fg=_FG,
                        activebackground=_ACCENT, activeforeground="#ffffff",
                        font=(UI_FONT, 9), bd=0)
            for val in _ANCHOR_VALUES:
                m.add_command(label=_ANCHOR_LABEL[val],
                              command=lambda vv=val: setter(vv))
            m.tk_popup(b.winfo_rootx(), b.winfo_rooty() + b.winfo_height())

        _set_anchor(anchor_var.get())
        anchor_btn.bind("<Button-1>", _open_anchor_menu)

        stretch_var = tk.BooleanVar(value=(col["stretch"] if col else True))
        stretch_cb = StyledCheckbox(g, "", stretch_var, bg=_BG)

        up = self._action(g, "↑", "Move column up")
        down = self._action(g, "↓", "Move column down")
        delete = self._action(g, "×", "Remove column")

        row = {"id": id_e, "heading": head_e, "width": width_e,
               "anchor": anchor_var, "stretch": stretch_var,
               "anchor_btn": anchor_btn, "stretch_cb": stretch_cb,
               "up": up, "down": down, "del": delete}
        up.bind("<ButtonRelease-1>", lambda e, r=row: self._move(r, -1))
        down.bind("<ButtonRelease-1>", lambda e, r=row: self._move(r, +1))
        delete.bind("<ButtonRelease-1>", lambda e, r=row: self._remove(r))
        self._rows.append(row)

    def _regrid(self) -> None:
        """(Re)place every row's widgets in the shared grid, in list order."""
        cells = (("id", _C_ID), ("heading", _C_HEAD), ("width", _C_WIDTH),
                 ("anchor_btn", _C_ANCHOR), ("stretch_cb", _C_STRETCH),
                 ("up", _C_UP), ("down", _C_DOWN), ("del", _C_DEL))
        for idx, row in enumerate(self._rows, start=1):
            for key, col in cells:
                row[key].grid(row=idx, column=col, sticky="w", padx=(0, 8), pady=1)

    def _remove(self, row: dict) -> None:
        if len(self._rows) <= 1:
            return  # keep at least one column
        for key in ("id", "heading", "width", "anchor_btn", "stretch_cb",
                    "up", "down", "del"):
            row[key].destroy()
        self._rows.remove(row)
        self._regrid()

    def _move(self, row: dict, delta: int) -> None:
        i = self._rows.index(row)
        j = i + delta
        if not (0 <= j < len(self._rows)):
            return
        self._rows[i], self._rows[j] = self._rows[j], self._rows[i]
        self._regrid()

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
        return tk.Entry(parent, width=width, bg=_ENTRY_BG, fg=_FG,
                        insertbackground=_FG, relief="flat",
                        font=(UI_FONT, 9), highlightthickness=1,
                        highlightbackground=_BORDER, highlightcolor=_ACCENT)

    def _action(self, parent, glyph: str, tip: str) -> tk.Label:
        lbl = tk.Label(parent, text=glyph, bg=_BG, fg=_FG_DIM,
                       font=(UI_FONT, 11), cursor="hand2", width=2)
        lbl.bind("<Enter>", lambda e, w=lbl: w.config(fg=_ACCENT))
        lbl.bind("<Leave>", lambda e, w=lbl: w.config(fg=_FG_DIM))
        _add_tooltip(lbl, tip)
        return lbl

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
