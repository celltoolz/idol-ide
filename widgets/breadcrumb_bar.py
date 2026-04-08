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
                is_last = i == len(scope) - 1

                # Crumb label — clicking shows siblings
                sibs, locs = _get_picker_data(tag, name, start, scope, outline)
                lbl = tk.Label(
                    self._inner, text=name, bg=_BG, fg=fg,
                    font=("Segoe UI", 9), padx=2, pady=0,
                    cursor="hand2",
                )
                lbl.pack(side="left")
                lbl.bind(
                    "<Button-1>",
                    lambda _, w=lbl, s=sibs: self._show_siblings(s, w),
                )
                lbl.bind("<Enter>", lambda _, l=lbl: l.config(bg=_BG_HOVER))
                lbl.bind("<Leave>", lambda _, l=lbl: l.config(bg=_BG))

                if not is_last:
                    _sep(self._inner)
                elif locs:
                    # Drill-down › after the innermost crumb — clicking shows locals
                    drill = tk.Label(
                        self._inner, text="›", bg=_BG, fg=_FG_DIM,
                        font=("Segoe UI", 9), padx=3, pady=0,
                        cursor="hand2",
                    )
                    drill.pack(side="left")
                    drill.bind(
                        "<Button-1>",
                        lambda _, w=drill, lo=locs, n=name: self._show_locals(lo, n, w),
                    )
                    drill.bind("<Enter>", lambda _, d=drill: d.config(fg=_FG_FILE))
                    drill.bind("<Leave>", lambda _, d=drill: d.config(fg=_FG_DIM))

    # ── Picker ──────────────────────────────────────────────────────────────────

    def _close_picker(self) -> None:
        if self._picker and self._picker.winfo_exists():
            self._picker.destroy()
        self._picker = None

    # ── Shared popup infrastructure ───────────────────────────────────────────

    def _make_popup(self, anchor: tk.Label, popup_w: int = 280) \
            -> "tuple[tk.Toplevel, tk.Frame, tk.Canvas, any, list, list[int]]":
        """Create the Toplevel + scrollable canvas. Returns
        (popup, inner, canvas, vsb, rows, selected_idx)."""
        from tkinter import ttk

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=_PICK_BDR)
        popup.attributes("-topmost", True)
        self._picker = popup

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

        rows: list = []
        selected_idx = [0]
        return popup, inner, canvas, vsb, rows, selected_idx

    def _finalise_popup(self, popup, canvas, vsb, rows, selected_idx,
                        anchor: tk.Label, popup_w: int,
                        content_h: int, max_h: int) -> None:
        """Size, position, bind focus-loss and keyboard nav, then show."""
        ROW_H = 26

        def _highlight(idx: int) -> None:
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        def _navigate(ln: int) -> None:
            self._close_picker()
            self._on_navigate(ln)

        popup_h = min(content_h, max_h) + 2
        if content_h <= max_h:
            vsb.pack_forget()

        x = anchor.winfo_rootx()
        y = anchor.winfo_rooty() + anchor.winfo_height() + 2
        if y + popup_h > popup.winfo_screenheight() - 20:
            y = anchor.winfo_rooty() - popup_h - 2
        popup.geometry(f"{popup_w}x{popup_h}+{x}+{y}")

        if rows:
            _highlight(0)

        def _wheel(e):
            canvas.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")
        canvas.bind("<MouseWheel>", _wheel)
        canvas.bind("<Button-4>", _wheel); canvas.bind("<Button-5>", _wheel)

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

    # ── Sibling picker (crumb click) ──────────────────────────────────────────

    def _show_siblings(self, symbols: list[tuple[str, str, int]], anchor: tk.Label) -> None:
        """Show peer symbols at this scope level."""
        if self._picker and self._picker.winfo_exists():
            self._close_picker()
            return
        if not symbols:
            return

        ROW_H, MAX_H, popup_w = 26, 14 * 26, 280
        popup, inner, canvas, vsb, rows, sel = self._make_popup(anchor, popup_w)

        def _wheel(e):
            canvas.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")

        def _highlight(idx):
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        for tag, name, lineno in symbols:
            fg = _TAG_FG.get(tag, _FG_FILE)
            row = tk.Frame(inner, bg=_PICK_BG, cursor="hand2", height=ROW_H)
            row.pack(fill="x"); row.pack_propagate(False)
            nl = tk.Label(row, text=name, bg=_PICK_BG, fg=fg,
                          font=("Segoe UI", 9), anchor="w", padx=12, pady=0)
            nl.pack(side="left", fill="y")
            ll = tk.Label(row, text=f":{lineno}", bg=_PICK_BG, fg=_FG_DIM,
                          font=("Segoe UI", 8), anchor="e", padx=8, pady=0)
            ll.pack(side="right", fill="y")

            idx = len(rows); rows.append((row, nl, ll, lineno))

            def _enter(_, i=idx): sel[0] = i; _highlight(i)
            def _leave(_): _highlight(sel[0])
            def _click(_, ln=lineno): self._close_picker(); self._on_navigate(ln)

            for w in (row, nl, ll):
                w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
                w.bind("<Button-1>", _click)
                w.bind("<MouseWheel>", _wheel)
                w.bind("<Button-4>", _wheel); w.bind("<Button-5>", _wheel)

        self._finalise_popup(popup, canvas, vsb, rows, sel, anchor, popup_w,
                             len(symbols) * ROW_H, MAX_H)

    # ── Locals picker (drill-down › click) ────────────────────────────────────

    def _show_locals(self, locals_: list[tuple[str, str, int]],
                     scope_name: str, anchor: tk.Label) -> None:
        """Show variables/nested defs inside the current function/method."""
        if self._picker and self._picker.winfo_exists():
            self._close_picker()
            return
        if not locals_:
            return

        ROW_H, HDR_H, MAX_H, popup_w = 26, 20, 14 * 26, 280

        _LOCAL_FG = "#abb2bf"
        _ICONS    = {"nested_fn": "◈", "nested_class": "◉", "local": "◦"}
        _FG_MAP   = {"nested_fn":    _TAG_FG.get("method",   _FG_FILE),
                     "nested_class": _TAG_FG.get("class",    _FG_FILE),
                     "local":        _LOCAL_FG}

        popup, inner, canvas, vsb, rows, sel = self._make_popup(anchor, popup_w)

        def _wheel(e):
            canvas.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")

        def _highlight(idx):
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        # Section header
        hdr = tk.Frame(inner, bg=_PICK_BG, height=HDR_H)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"IN  {scope_name.upper()}", bg=_PICK_BG, fg=_FG_DIM,
                 font=("Segoe UI", 7, "bold"), anchor="w", padx=10).pack(side="left", fill="y")

        for ltag, lname, lline in locals_:
            fg   = _FG_MAP.get(ltag, _LOCAL_FG)
            icon = _ICONS.get(ltag, "◦")
            row  = tk.Frame(inner, bg=_PICK_BG, cursor="hand2", height=ROW_H)
            row.pack(fill="x"); row.pack_propagate(False)
            tl = tk.Label(row, text="  ├─", bg=_PICK_BG, fg="#4a4a4a",
                          font=("Consolas", 8), padx=4, pady=0)
            tl.pack(side="left", fill="y")
            nl = tk.Label(row, text=f"{icon}  {lname}", bg=_PICK_BG, fg=fg,
                          font=("Segoe UI", 9), anchor="w", padx=2, pady=0)
            nl.pack(side="left", fill="y")
            ll = tk.Label(row, text=f":{lline}", bg=_PICK_BG, fg=_FG_DIM,
                          font=("Segoe UI", 8), anchor="e", padx=8, pady=0)
            ll.pack(side="right", fill="y")

            idx = len(rows); rows.append((row, nl, ll, lline))

            def _enter(_, i=idx): sel[0] = i; _highlight(i)
            def _leave(_): _highlight(sel[0])
            def _click(_, ln=lline): self._close_picker(); self._on_navigate(ln)

            for w in (row, nl, ll, tl):
                w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
                w.bind("<Button-1>", _click)
                w.bind("<MouseWheel>", _wheel)
                w.bind("<Button-4>", _wheel); w.bind("<Button-5>", _wheel)

        content_h = HDR_H + len(locals_) * ROW_H
        self._finalise_popup(popup, canvas, vsb, rows, sel, anchor, popup_w,
                             content_h, MAX_H)


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
    """Return (siblings, locals).

    siblings — peer symbols at the same nesting level (crumb click).
    locals   — symbols defined inside this function/method (drill-down › click).
    """
    if tag == "class":
        return outline.get_module_symbols(), []
    if tag == "function":
        return outline.get_module_symbols(), outline.get_local_symbols(start)
    if tag == "method":
        class_entry = next((s for s in scope if s[0] == "class"), None)
        sibs = outline.get_class_methods(class_entry[2]) if class_entry else []
        return sibs, outline.get_local_symbols(start)
    return [], []
