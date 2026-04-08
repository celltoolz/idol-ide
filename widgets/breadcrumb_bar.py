"""BreadcrumbBar — thin bar showing file path + current symbol scope.

Sits between the tab row and the editor content inside each tab frame.
Path folder crumbs are clickable (sets explorer root).
Symbol crumbs are clickable (opens a sibling-symbol picker dropdown).
"""

from __future__ import annotations

import os
import tkinter as tk
from typing import Callable

_BG       = "#2d2d30"
_BG_HOVER = "#3e3e42"
_BORDER   = "#3c3c3c"
_FG_DIM   = "#858585"
_FG_FILE  = "#cccccc"
_FG_SEP   = "#555555"
_PICK_BG  = "#252526"
_PICK_BDR = "#3c3c3c"
_PICK_SEL = "#094771"

_TAG_FG: dict[str, str] = {
    "class":    "#8be9fd",
    "method":   "#50fa7b",
    "function": "#ffb86c",
}


class BreadcrumbBar(tk.Frame):
    """Horizontal breadcrumb bar for a single editor tab."""

    HEIGHT = 22

    def __init__(
        self,
        parent,
        on_navigate: Callable[[int], None],
        on_set_root: Callable[[str], None] | None = None,
    ) -> None:
        super().__init__(parent, bg=_BG, height=self.HEIGHT)
        self.pack_propagate(False)
        self._on_navigate = on_navigate
        self._on_set_root = on_set_root
        self._last_line: int = -1
        self._last_path: str | None = ""
        self._last_key: tuple = ()   # cache key = (filepath, scope_tuple, path_parts_tuple)
        self._picker: tk.Toplevel | None = None

        # 1-px separator at the very bottom
        tk.Frame(self, bg=_BORDER, height=1).pack(side="bottom", fill="x")

        # Scrollable inner frame for crumbs (left-padded)
        self._inner = tk.Frame(self, bg=_BG)
        self._inner.pack(side="top", fill="both", expand=True, padx=(8, 4))

    # ── Public API ─────────────────────────────────────────────────────────────

    def update_crumbs(
        self,
        filepath: str | None,
        explorer_root: str | None,
        cursor_line: int,
        outline,
        is_python: bool,
    ) -> None:
        """Re-render only when the visible content actually changes.

        Computes the scope chain and path parts first; only calls _render if
        the result differs from the last render — so moving within a method
        produces zero widget churn.
        """
        # Fast reject: same line+file as last tick (most common case)
        if cursor_line == self._last_line and filepath == self._last_path:
            return
        self._last_line = cursor_line
        self._last_path = filepath

        # Compute what we'd render
        path_parts = tuple(
            (label, folder) for label, folder in _path_parts(filepath, explorer_root)
        )
        scope: tuple = ()
        if is_python and outline is not None:
            scope = tuple(
                (tag, name, start)
                for tag, name, start in outline.get_scope_at(cursor_line)
            )

        key = (filepath, path_parts, scope)
        if key == self._last_key:
            return  # content unchanged — skip all widget work
        self._last_key = key

        self._render(filepath, explorer_root, cursor_line, outline, is_python,
                     _path_parts_cache=list(path_parts),
                     _scope_cache=list(scope))

    def invalidate(self) -> None:
        """Force a full re-render on the next update_crumbs call."""
        self._last_line = -1
        self._last_key = ()

    # ── Rendering ──────────────────────────────────────────────────────────────

    def _render(
        self,
        filepath: str | None,
        explorer_root: str | None,
        cursor_line: int,
        outline,
        is_python: bool,
        _path_parts_cache: list | None = None,
        _scope_cache: list | None = None,
    ) -> None:
        for w in self._inner.winfo_children():
            w.destroy()
        self._close_picker()

        # ── Path crumbs ──────────────────────────────────────────────────────
        parts = _path_parts_cache if _path_parts_cache is not None else _path_parts(filepath, explorer_root)
        for i, (label, folder_path) in enumerate(parts):
            is_last_path = i == len(parts) - 1
            fg = _FG_FILE if is_last_path else _FG_DIM

            lbl = tk.Label(
                self._inner, text=label, bg=_BG, fg=fg,
                font=("Segoe UI", 9), padx=2, pady=0,
            )
            lbl.pack(side="left")

            if folder_path and self._on_set_root:
                lbl.config(cursor="hand2")
                lbl.bind("<Button-1>", lambda _, p=folder_path: self._on_set_root(p))
                lbl.bind("<Enter>", lambda _, l=lbl: l.config(fg=_FG_FILE))
                lbl.bind("<Leave>", lambda _, l=lbl, f=fg: l.config(fg=f))

            if not is_last_path:
                _sep(self._inner)

        # ── Symbol crumbs ────────────────────────────────────────────────────
        scope = _scope_cache if _scope_cache is not None else (
            outline.get_scope_at(cursor_line) if (is_python and outline) else []
        )
        if scope:
            _sep(self._inner)
            for i, (tag, name, start) in enumerate(scope):
                fg = _TAG_FG.get(tag, _FG_FILE)
                lbl = tk.Label(
                    self._inner, text=name, bg=_BG, fg=fg,
                    font=("Segoe UI", 9), padx=2, pady=0,
                    cursor="hand2",
                )
                lbl.pack(side="left")
                sibs, locs = _get_picker_data(tag, name, start, scope, outline)
                lbl.bind(
                    "<Button-1>",
                    lambda _, w=lbl, s=sibs, lo=locs, n=name: self._show_picker(s, lo, n, w),
                )
                lbl.bind("<Enter>", lambda _, l=lbl: l.config(bg=_BG_HOVER))
                lbl.bind("<Leave>", lambda _, l=lbl: l.config(bg=_BG))
                if i < len(scope) - 1:
                    _sep(self._inner)

    # ── Picker ──────────────────────────────────────────────────────────────────

    def _close_picker(self) -> None:
        if self._picker and self._picker.winfo_exists():
            self._picker.destroy()
        self._picker = None

    def _show_picker(
        self,
        symbols: list[tuple[str, str, int]],
        locals_: list[tuple[str, str, int]],
        scope_name: str,
        anchor: tk.Label,
    ) -> None:
        # Toggle off if already open
        if self._picker and self._picker.winfo_exists():
            self._close_picker()
            return
        if not symbols and not locals_:
            return

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=_PICK_BDR)
        popup.attributes("-topmost", True)
        self._picker = popup

        from tkinter import ttk

        MAX_VISIBLE = 14
        ROW_H       = 26
        HDR_H       = 20
        popup_w     = 300

        border = tk.Frame(popup, bg=_PICK_BDR)
        border.pack(fill="both", expand=True, padx=1, pady=1)

        canvas = tk.Canvas(border, bg=_PICK_BG, highlightthickness=0, bd=0,
                           width=popup_w - 2)
        vsb = ttk.Scrollbar(border, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        inner = tk.Frame(canvas, bg=_PICK_BG)
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        inner.bind("<Configure>", lambda _: (
            canvas.configure(scrollregion=canvas.bbox("all")),
            canvas.itemconfigure(win_id, width=canvas.winfo_width()),
        ))
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(win_id, width=e.width))

        # rows that are selectable (skip section headers)
        rows: list[tuple[tk.Frame, tk.Label, tk.Label, int]] = []  # (frame, name_lbl, line_lbl, lineno)
        selected_idx = [0]

        _LOCAL_FG = "#abb2bf"
        _LOCAL_ICONS = {"nested_fn": "◈", "nested_class": "◉", "local": "◦"}
        _LOCAL_FG_MAP = {"nested_fn": _TAG_FG.get("method", _FG_FILE),
                         "nested_class": _TAG_FG.get("class", _FG_FILE),
                         "local": _LOCAL_FG}

        def _wheel(e):
            canvas.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")

        def _highlight(idx: int) -> None:
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        def _navigate(ln: int) -> None:
            self._close_picker()
            self._on_navigate(ln)

        def _add_section_header(text: str) -> None:
            hdr = tk.Frame(inner, bg=_PICK_BG, height=HDR_H)
            hdr.pack(fill="x")
            hdr.pack_propagate(False)
            tk.Label(hdr, text=text, bg=_PICK_BG, fg=_FG_DIM,
                     font=("Segoe UI", 7, "bold"), anchor="w", padx=10).pack(
                         side="left", fill="y")

        def _add_divider() -> None:
            tk.Frame(inner, bg="#3c3c3c", height=1).pack(fill="x", padx=6, pady=2)

        def _add_row(tag: str, name: str, lineno: int, indent: int = 0) -> None:
            fg = _TAG_FG.get(tag, _FG_FILE)
            row = tk.Frame(inner, bg=_PICK_BG, cursor="hand2", height=ROW_H)
            row.pack(fill="x")
            row.pack_propagate(False)
            pad = 10 + indent * 16
            name_lbl = tk.Label(row, text=name, bg=_PICK_BG, fg=fg,
                                 font=("Segoe UI", 9), anchor="w", padx=pad, pady=0)
            name_lbl.pack(side="left", fill="y")
            line_lbl = tk.Label(row, text=f":{lineno}", bg=_PICK_BG, fg=_FG_DIM,
                                 font=("Segoe UI", 8), anchor="e", padx=8, pady=0)
            line_lbl.pack(side="right", fill="y")

            idx = len(rows)
            rows.append((row, name_lbl, line_lbl, lineno))

            def _enter(_): selected_idx[0] = idx; _highlight(idx)
            def _leave(_): _highlight(selected_idx[0])
            def _click(_): _navigate(lineno)

            for w in (row, name_lbl, line_lbl):
                w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
                w.bind("<Button-1>", _click)
                w.bind("<MouseWheel>", _wheel)
                w.bind("<Button-4>", _wheel); w.bind("<Button-5>", _wheel)

        def _add_local_row(ltag: str, lname: str, lline: int) -> None:
            fg = _LOCAL_FG_MAP.get(ltag, _LOCAL_FG)
            icon = _LOCAL_ICONS.get(ltag, "◦")
            row = tk.Frame(inner, bg=_PICK_BG, cursor="hand2", height=ROW_H)
            row.pack(fill="x")
            row.pack_propagate(False)
            # Tree line prefix + indent
            tree_lbl = tk.Label(row, text="  ├─", bg=_PICK_BG, fg="#4a4a4a",
                                 font=("Consolas", 8), padx=4, pady=0)
            tree_lbl.pack(side="left", fill="y")
            name_lbl = tk.Label(row, text=f"{icon}  {lname}", bg=_PICK_BG, fg=fg,
                                 font=("Segoe UI", 9), anchor="w", padx=2, pady=0)
            name_lbl.pack(side="left", fill="y")
            line_lbl = tk.Label(row, text=f":{lline}", bg=_PICK_BG, fg=_FG_DIM,
                                 font=("Segoe UI", 8), anchor="e", padx=8, pady=0)
            line_lbl.pack(side="right", fill="y")

            idx = len(rows)
            rows.append((row, name_lbl, line_lbl, lline))

            def _enter(_): selected_idx[0] = idx; _highlight(idx)
            def _leave(_): _highlight(selected_idx[0])
            def _click(_): _navigate(lline)

            for w in (row, name_lbl, line_lbl, tree_lbl):
                w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
                w.bind("<Button-1>", _click)
                w.bind("<MouseWheel>", _wheel)
                w.bind("<Button-4>", _wheel); w.bind("<Button-5>", _wheel)

        # ── Section 1: siblings ──────────────────────────────────────────────
        if symbols:
            _add_section_header("SYMBOLS")
            for tag, name, lineno in symbols:
                _add_row(tag, name, lineno)

        # ── Section 2: locals inside current scope ───────────────────────────
        if locals_:
            if symbols:
                _add_divider()
            _add_section_header(f"IN  {scope_name.upper()}")
            for ltag, lname, lline in locals_:
                _add_local_row(ltag, lname, lline)

        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>", _wheel); canvas.bind("<Button-5>", _wheel)

        # Keyboard nav (only over selectable rows)
        navigable = [r[3] for r in rows]

        def _key(event):
            if event.keysym == "Down":
                selected_idx[0] = min(selected_idx[0] + 1, len(rows) - 1)
                _highlight(selected_idx[0])
                canvas.yview_moveto(selected_idx[0] / max(len(rows), 1))
            elif event.keysym == "Up":
                selected_idx[0] = max(selected_idx[0] - 1, 0)
                _highlight(selected_idx[0])
                canvas.yview_moveto(selected_idx[0] / max(len(rows), 1))
            elif event.keysym in ("Return", "space") and navigable:
                _navigate(navigable[selected_idx[0]])
            elif event.keysym == "Escape":
                self._close_picker()

        popup.bind("<KeyPress>", _key)

        # Size popup
        total_rows = len(rows)
        n_headers = (1 if symbols else 0) + (1 if locals_ else 0)
        n_dividers = 1 if (symbols and locals_) else 0
        content_h = total_rows * ROW_H + n_headers * HDR_H + n_dividers * 5
        popup_h = min(content_h, MAX_VISIBLE * ROW_H) + 2
        needs_scroll = content_h > popup_h
        if not needs_scroll:
            vsb.pack_forget()

        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        screen_h = popup.winfo_screenheight()
        if y + popup_h > screen_h - 20:
            y = anchor.winfo_rooty() - popup_h - 2

        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")
        if rows:
            _highlight(0)

        def _check_focus():
            if not popup.winfo_exists():
                return
            try:
                focused = str(popup.focus_get())
            except Exception:
                focused = ""
            if not focused.startswith(str(popup)):
                popup.destroy()
                self._picker = None

        popup.bind("<FocusOut>", lambda _: popup.after(100, _check_focus))
        popup.focus_set()


# ── Module-level helpers ───────────────────────────────────────────────────────

def _sep(parent: tk.Frame) -> None:
    tk.Label(
        parent, text="›", bg=_BG, fg=_FG_SEP,
        font=("Segoe UI", 9), padx=1, pady=0,
    ).pack(side="left")


def _path_parts(
    filepath: str | None,
    explorer_root: str | None,
) -> list[tuple[str, str | None]]:
    """Return [(label, clickable_folder_path_or_None), ...] for the path crumbs."""
    if not filepath:
        return [("Untitled", None)]

    try:
        if explorer_root:
            rel = os.path.relpath(filepath, explorer_root)
            if rel.startswith(".."):
                return [(os.path.basename(filepath), None)]
        else:
            rel = os.path.basename(filepath)
    except ValueError:
        return [(os.path.basename(filepath), None)]

    parts = rel.replace("\\", "/").split("/")

    MAX = 5
    if len(parts) > MAX:
        parts = parts[:1] + ["…"] + parts[-(MAX - 2):]

    result: list[tuple[str, str | None]] = []
    accumulated: str | None = explorer_root or ""

    for i, part in enumerate(parts):
        if part == "…":
            result.append(("…", None))
            accumulated = None  # can't reconstruct paths past ellipsis
            continue
        is_file = i == len(parts) - 1
        if is_file:
            result.append((part, None))
        else:
            if accumulated is not None:
                accumulated = os.path.join(accumulated, part)
                result.append((part, accumulated))
            else:
                result.append((part, None))

    return result


def _get_picker_data(
    tag: str,
    name: str,
    start: int,
    scope: list[tuple[str, str, int]],
    outline,
) -> tuple[list[tuple[str, str, int]], list[tuple[str, str, int]]]:
    """Return (siblings, locals) for the picker.

    siblings — peer symbols at the same nesting level (used to jump around).
    locals   — symbols defined inside this function/method (shown below a divider).
    """
    if tag == "class":
        siblings = outline.get_module_symbols()
        locals_: list[tuple[str, str, int]] = []
    elif tag == "function":
        siblings = outline.get_module_symbols()
        locals_ = outline.get_local_symbols(start)
    elif tag == "method":
        class_entry = next((s for s in scope if s[0] == "class"), None)
        siblings = outline.get_class_methods(class_entry[2]) if class_entry else []
        locals_ = outline.get_local_symbols(start)
    else:
        siblings = []
        locals_ = []
    return siblings, locals_
