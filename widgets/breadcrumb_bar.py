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
        get_line: Callable[[int], str] | None = None,
        highlight_fn: Callable[[str], list[tuple[str, str]]] | None = None,
    ) -> None:
        super().__init__(parent, bg=_BG, height=self.HEIGHT)
        self.pack_propagate(False)
        self._on_navigate = on_navigate
        self._on_set_root = on_set_root
        self._get_line = get_line
        self._highlight_fn = highlight_fn
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
                        lambda _, w=drill, lo=locs, n=name, sc=list(scope), fp=filepath:
                            self._show_locals(lo, n, w, sc, fp),
                    )
                    drill.bind("<Enter>", lambda _, d=drill: d.config(fg=_FG_FILE))
                    drill.bind("<Leave>", lambda _, d=drill: d.config(fg=_FG_DIM))

    # ── Picker ──────────────────────────────────────────────────────────────────

    def _close_picker(self) -> None:
        if self._picker and self._picker.winfo_exists():
            self._picker.destroy()
        self._picker = None

    # ── Shared popup infrastructure ───────────────────────────────────────────

    def _make_popup(self, anchor: tk.Label, popup_w: int = 280,
                    with_footer: bool = False):
        """Create the Toplevel + scrollable canvas. Returns
        (popup, inner, canvas, vsb, rows, selected_idx, footer_or_None)."""
        from tkinter import ttk

        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.configure(bg=_PICK_BDR)
        popup.attributes("-topmost", True)
        self._picker = popup

        border = tk.Frame(popup, bg=_PICK_BDR)
        border.pack(fill="both", expand=True, padx=1, pady=1)

        # Footer is packed FIRST (side="bottom") so it reserves space before
        # the scrollable area expands to fill the rest.
        footer: tk.Frame | None = None
        if with_footer:
            tk.Frame(border, bg=_PICK_BDR, height=1).pack(side="bottom", fill="x")
            footer = tk.Frame(border, bg="#1a1a1d")
            footer.pack(side="bottom", fill="x")

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
        return popup, inner, canvas, vsb, rows, selected_idx, footer

    def _finalise_popup(self, popup, canvas, vsb, rows, selected_idx,
                        anchor: tk.Label, popup_w: int,
                        content_h: int, max_h: int, footer_h: int = 0) -> None:
        """Size, position, bind focus-loss and keyboard nav, then show."""
        ROW_H = 26

        def _highlight(idx: int) -> None:
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        def _navigate(ln: int) -> None:
            self._close_picker()
            self._on_navigate(ln)

        popup_h = min(content_h, max_h) + 2 + footer_h
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
        popup, inner, canvas, vsb, rows, sel, _ = self._make_popup(anchor, popup_w)

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
                     scope_name: str, anchor: tk.Label,
                     scope: list | None = None,
                     filepath: str | None = None) -> None:
        """Show variables/nested defs inside the current function/method."""
        if self._picker and self._picker.winfo_exists():
            self._close_picker()
            return
        if not locals_:
            return

        ROW_H, HDR_H, SEC_H, MAX_H, FOOTER_H, popup_w = 26, 20, 18, 14 * 26, 32, 320

        _LOCAL_FG = "#abb2bf"
        _ICONS: dict[str, str] = {
            "nested_fn":    "◈",
            "nested_class": "◉",
            "local":        "◦",
            "attr":         "◦",
            "param":        "◦",
        }
        _FG_MAP: dict[str, str] = {
            "nested_fn":    _TAG_FG.get("method",   _FG_FILE),   # green
            "nested_class": _TAG_FG.get("class",    _FG_FILE),   # cyan
            "local":        _LOCAL_FG,                            # soft grey
            "attr":         "#ff79c6",                            # pink
            "param":        "#bd93f9",                            # purple
        }
        _SEC_LABELS: dict[str, str] = {
            "nested_fn":    "NESTED",
            "nested_class": "NESTED",
            "local":        "LOCALS",
            "attr":         "ATTRIBUTES",
            "param":        "PARAMETERS",
        }
        _GROUP_ORDER = ["param", "attr", "local", "nested_fn", "nested_class"]

        popup, inner, canvas, vsb, rows, sel, footer = self._make_popup(
            anchor, popup_w, with_footer=True
        )

        # ── Footer preview strip ──────────────────────────────────────────────
        preview_text = tk.Text(
            footer,
            height=1, state="disabled", wrap="none",
            bd=0, highlightthickness=0,
            bg="#1a1a1d", fg=_FG_DIM,
            font=("Segoe UI", 8),
            padx=8, pady=6,
            cursor="arrow", takefocus=False,
        )
        preview_text.pack(fill="x", expand=True)
        # Colour tags for each segment type
        preview_text.tag_configure("dim",          foreground=_FG_DIM)
        preview_text.tag_configure("sep",          foreground=_FG_SEP)
        preview_text.tag_configure("class",        foreground=_TAG_FG.get("class",    _FG_FILE))
        preview_text.tag_configure("method",       foreground=_TAG_FG.get("method",   _FG_FILE))
        preview_text.tag_configure("function",     foreground=_TAG_FG.get("function", _FG_FILE))
        preview_text.tag_configure("attr",         foreground="#ff79c6")
        preview_text.tag_configure("local",        foreground=_LOCAL_FG)
        preview_text.tag_configure("param",        foreground="#bd93f9")
        preview_text.tag_configure("nested_fn",    foreground=_TAG_FG.get("method",   _FG_FILE))
        preview_text.tag_configure("nested_class", foreground=_TAG_FG.get("class",    _FG_FILE))
        preview_text.tag_configure("src",          foreground="#cccccc")

        # ── Footer marquee animation ──────────────────────────────────────────
        _mq: dict = {"job": None, "check": None, "pos": 0.0, "dir": 1, "pause": 0}

        def _marquee_step() -> None:
            if not preview_text.winfo_exists():
                return
            if _mq["pause"] > 0:
                _mq["pause"] -= 1
                _mq["job"] = preview_text.after(30, _marquee_step)
                return
            start, end = preview_text.xview()
            visible = end - start
            max_pos = 1.0 - visible
            if max_pos <= 0.001:
                return
            w = preview_text.winfo_width()
            step = (visible / w * 2.0) if w > 0 else 0.01
            _mq["pos"] += _mq["dir"] * step
            if _mq["pos"] >= max_pos:
                _mq["pos"] = max_pos
                _mq["dir"] = -1
                _mq["pause"] = 15   # ~450 ms pause at right end
            elif _mq["pos"] <= 0.0:
                _mq["pos"] = 0.0
                _mq["dir"] = 1
                _mq["pause"] = 15   # ~450 ms pause at left end
            preview_text.xview_moveto(_mq["pos"])
            _mq["job"] = preview_text.after(30, _marquee_step)

        def _start_marquee() -> None:
            if _mq["job"]:
                preview_text.after_cancel(_mq["job"])
            _mq["pos"]   = 0.0
            _mq["dir"]   = 1
            _mq["pause"] = 0
            _mq["job"]   = preview_text.after(600, _marquee_step)  # initial delay

        def _stop_marquee() -> None:
            if _mq["check"]:
                preview_text.after_cancel(_mq["check"])
                _mq["check"] = None
            if _mq["job"]:
                preview_text.after_cancel(_mq["job"])
                _mq["job"] = None
            _mq["pos"] = 0.0
            preview_text.xview_moveto(0.0)

        def _update_preview(ltag: str, lname: str, lline: int) -> None:
            print(f"[mq-dbg] _update_preview called: {lname!r}")
            _stop_marquee()
            preview_text.configure(state="normal")
            preview_text.delete("1.0", "end")
            preview_text.insert("end", lname, ltag)
            if self._get_line:
                src = self._get_line(lline).strip()
                if src:
                    preview_text.insert("end", "  :  ", "sep")
                    if self._highlight_fn:
                        for tok_text, color in self._highlight_fn(src):
                            if tok_text:
                                tag = f"hl_{color.lstrip('#')}"
                                preview_text.tag_configure(tag, foreground=color)
                                preview_text.insert("end", tok_text, tag)
                    else:
                        preview_text.insert("end", src, "src")
            preview_text.configure(state="disabled")
            # Start marquee if content overflows the footer width.
            # Defer the xview check by one frame — on macOS Aqua Tk,
            # update_idletasks() alone is not enough to flush the text
            # layout, so xview() returns (0.0, 1.0) immediately after
            # insert even when there is real overflow.
            def _maybe_start_marquee() -> None:
                _mq["check"] = None
                xv = preview_text.xview() if preview_text.winfo_exists() else ("gone",)
                w  = preview_text.winfo_width() if preview_text.winfo_exists() else -1
                print(f"[mq-dbg] _maybe_start_marquee: xview={xv}  width={w}px")
                if preview_text.winfo_exists() and preview_text.xview()[1] < 1.0:
                    print("[mq-dbg] → starting marquee")
                    _start_marquee()
            _mq["check"] = preview_text.after(50, _maybe_start_marquee)

        # ── Scrollable content ────────────────────────────────────────────────
        def _wheel(e):
            canvas.yview_scroll(-1 if (e.delta > 0 or e.num == 4) else 1, "units")

        def _highlight(idx):
            for i, (r, nl, ll, _) in enumerate(rows):
                bg = _PICK_SEL if i == idx else _PICK_BG
                r.configure(bg=bg); nl.configure(bg=bg); ll.configure(bg=bg)

        # Top "IN <SCOPE>" header
        hdr = tk.Frame(inner, bg=_PICK_BG, height=HDR_H)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text=f"IN  {scope_name.upper()}", bg=_PICK_BG, fg=_FG_DIM,
                 font=("Segoe UI", 7, "bold"), anchor="w", padx=10).pack(side="left", fill="y")

        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for ltag, lname, lline in locals_:
            groups[ltag].append((lname, lline))

        content_h = HDR_H
        seen_sections: set[str] = set()

        for gkey in _GROUP_ORDER:
            if gkey not in groups:
                continue
            sec_label = _SEC_LABELS.get(gkey, gkey.upper())
            if sec_label not in seen_sections:
                seen_sections.add(sec_label)
                if content_h > HDR_H:
                    tk.Frame(inner, bg=_PICK_BDR, height=1).pack(fill="x")
                    content_h += 1
                sec = tk.Frame(inner, bg=_PICK_BG, height=SEC_H)
                sec.pack(fill="x"); sec.pack_propagate(False)
                tk.Label(sec, text=sec_label, bg=_PICK_BG, fg=_FG_DIM,
                         font=("Segoe UI", 7), anchor="w", padx=10).pack(side="left", fill="y")
                content_h += SEC_H

            fg   = _FG_MAP.get(gkey, _LOCAL_FG)
            icon = _ICONS.get(gkey, "◦")
            for lname, lline in groups[gkey]:
                row = tk.Frame(inner, bg=_PICK_BG, cursor="hand2", height=ROW_H)
                row.pack(fill="x"); row.pack_propagate(False)
                nl = tk.Label(row, text=f"{icon}  {lname}", bg=_PICK_BG, fg=fg,
                              font=("Segoe UI", 9), anchor="w", padx=12, pady=0)
                nl.pack(side="left", fill="y")
                ll = tk.Label(row, text=f":{lline}", bg=_PICK_BG, fg=_FG_DIM,
                              font=("Segoe UI", 8), anchor="e", padx=8, pady=0)
                ll.pack(side="right", fill="y")

                idx = len(rows); rows.append((row, nl, ll, lline))
                content_h += ROW_H

                def _enter(_, i=idx, t=gkey, n=lname, ln=lline):
                    sel[0] = i; _highlight(i); _update_preview(t, n, ln)
                def _leave(_): _highlight(sel[0])
                def _click(_, ln=lline): self._close_picker(); self._on_navigate(ln)

                for w in (row, nl, ll):
                    w.bind("<Enter>", _enter); w.bind("<Leave>", _leave)
                    w.bind("<Button-1>", _click)
                    w.bind("<MouseWheel>", _wheel)
                    w.bind("<Button-4>", _wheel); w.bind("<Button-5>", _wheel)

        self._finalise_popup(popup, canvas, vsb, rows, sel, anchor, popup_w,
                             content_h, MAX_H, footer_h=FOOTER_H)


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
