"""SourceControlPanel — Git Stage/Unstage/Commit/Push/Pull sidebar panel."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import Frame, Label, Menu, ttk
from typing import Callable

from utils import bind_right_click
from utils.git_diagnostics import (
    classify_file, analyze_files, health_checks, git_installed,
    FileInfo, Issue, HealthCheck
)
from utils.learning_registry import LearningManager
from widgets.guide_window import GuideWindow, GuidePage


_BG       = "#252526"
_ITEM_BG  = "#1e1e1e"
_HOV_BG   = "#2a2d2e"
_HDR_BG   = "#2d2d30"
_FG       = "#cccccc"
_DIM      = "#858585"
_BTN_BG   = "#0e639c"
_BTN_ACT  = "#1177bb"

STATUS_COLORS = {
    "M": "#e2c08d",
    "A": "#73c991",
    "U": "#cccccc",
    "D": "#f14c4c",
}
STATUS_LABELS = {"M": "M", "A": "A", "U": "U", "D": "D"}


class _Tooltip:
    """Simple hover tooltip."""
    def __init__(self, widget, text: str) -> None:
        self._tip = None
        widget.bind("<Enter>",    lambda e: self._show(e, text))
        widget.bind("<Leave>",    lambda _: self._hide())
        widget.bind("<Button-1>", lambda _: self._hide())
        bind_right_click(widget, lambda _: self._hide())
        widget.bind("<Destroy>",  lambda _: self._hide())

    def _show(self, event, text: str) -> None:
        self._hide()
        x = event.widget.winfo_rootx() + event.widget.winfo_width() + 4
        y = event.widget.winfo_rooty()
        self._tip = tk.Toplevel()
        self._tip.overrideredirect(True)
        self._tip.attributes("-topmost", True)
        bg = "#1e1e1e"
        frame = Frame(self._tip, bg="#555555", padx=1, pady=1)
        frame.pack()
        Label(frame, text=text, bg=bg, fg="#cccccc",
              font=("Segoe UI", 8), justify="left",
              wraplength=220, padx=8, pady=5).pack()
        self._tip.geometry(f"+{x}+{y}")

    def _hide(self) -> None:
        if self._tip:
            try:
                self._tip.destroy()
            except Exception:
                pass
            self._tip = None


class _FileRow(Frame):
    """A single file entry row with hover highlight."""

    def __init__(self, parent, path: str, status: str,
                 on_click: Callable, on_right_click: Callable,
                 bg: str = _ITEM_BG) -> None:
        super().__init__(parent, bg=bg, cursor="hand2")
        self._bg = bg
        color = STATUS_COLORS.get(status, _FG)
        name = os.path.basename(path)

        lbl = Label(self, text=f"  {name}", bg=bg, fg=color,
                    font=("Segoe UI", 9), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)

        Label(self, text=f" {status} ", bg=bg, fg=color,
              font=("Segoe UI", 9, "bold")).pack(side="right", padx=(0, 4))

        for w in (self, lbl):
            w.bind("<Enter>",           lambda _: self._hover(True))
            w.bind("<Leave>",           lambda _: self._hover(False))
            w.bind("<Double-Button-1>", lambda _, p=path: on_click(p))
            bind_right_click(w, lambda e, p=path: on_right_click(e, p))

        # Hover tooltip: file classification + explanation (on row only)
        _STATUS_WORDS = {"M": "Modified", "A": "Added", "U": "Untracked", "D": "Deleted"}
        status_word = _STATUS_WORDS.get(status, status)
        info = classify_file(path)
        _Tooltip(self, f"{info.label} — {status_word}\n{info.explanation}")

    def _hover(self, on: bool) -> None:
        c = _HOV_BG if on else self._bg
        self.config(bg=c)
        for w in self.winfo_children():
            w.config(bg=c)


class _Section(Frame):
    """Collapsible section header + virtually-rendered scrollable file list.

    Only the rows visible in the canvas viewport (plus a small buffer) are
    created as widgets. Rows outside the viewport are destroyed. This keeps
    memory and render time constant regardless of list size.
    """

    _ROW_H  = 22   # fixed px height per row
    _BUFFER = 4    # extra rows to keep alive above/below the visible area

    def __init__(self, parent, title: str, bg: str = _BG,
                 on_toggle: Callable | None = None) -> None:
        super().__init__(parent, bg=bg)
        self.pack_propagate(False)
        self._collapsed    = False
        self._bg           = bg
        self._on_toggle    = on_toggle
        self._panel_menu_cb = None   # set by bind_panel_menu
        self._vs_visible   = False   # tracks scrollbar state to avoid redundant pack/forget
        self._configuring  = False   # re-entrancy guard for _on_canvas_configure

        # Data store
        self._items: list[tuple[str, str]] = []
        self._on_click      = None
        self._on_right_click_file = None

        # Currently rendered rows: index → (canvas_window_id, _FileRow widget)
        self._rendered: dict[int, tuple[int, Frame]] = {}
        self._canvas_w: int = 1

        # ── Header ───────────────────────────────────────────────────────────
        hdr = self._hdr = Frame(self, bg=_HDR_BG, height=24, cursor="hand2")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._arrow = Label(hdr, text="▾", bg=_HDR_BG, fg=_FG,
                            font=("Segoe UI", 8))
        self._arrow.pack(side="left", padx=(4, 0))

        Label(hdr, text=title, bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)

        self._count_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_DIM,
                                font=("Segoe UI", 8), padx=6)
        self._count_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle())
        hdr.bind("<Button-1>", lambda _: self._toggle())

        # ── Scrollable canvas ─────────────────────────────────────────────────
        self._scroll_frame = Frame(self, bg=_ITEM_BG)
        self._scroll_frame.pack_propagate(False)

        self._canvas = tk.Canvas(self._scroll_frame, bg=_ITEM_BG,
                                 highlightthickness=0, bd=0, height=1)
        self._vs = ttk.Scrollbar(self._scroll_frame, orient="vertical",
                                 command=self._scroll_to)
        self._canvas.configure(yscrollcommand=self._vs.set)
        self._canvas.pack(side="left", fill="both", expand=True)

        self._canvas.bind("<Configure>", self._on_canvas_configure)
        for w in (self._canvas, self._scroll_frame):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

    # ── Scroll plumbing ───────────────────────────────────────────────────────

    def _scroll_to(self, *args) -> None:
        self._canvas.yview(*args)
        self._render_visible()

    def _on_wheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")
        self._render_visible()

    def _on_canvas_configure(self, event) -> None:
        if self._configuring:
            return
        self._configuring = True
        try:
            self._canvas_w = event.width
            # Update width of every already-rendered window
            for wid, _ in self._rendered.values():
                self._canvas.itemconfigure(wid, width=self._canvas_w)
            self._update_scrollbar()
            self._render_visible()
        finally:
            self._configuring = False

    def _update_scrollbar(self) -> None:
        total_h  = len(self._items) * self._ROW_H
        canvas_h = self._canvas.winfo_height()
        needs = total_h > canvas_h
        if needs and not self._vs_visible:
            self._vs_visible = True
            self._vs.pack(side="right", fill="y")
        elif not needs and self._vs_visible:
            self._vs_visible = False
            self._vs.pack_forget()

    # ── Virtual render ────────────────────────────────────────────────────────

    def _render_visible(self) -> None:
        if not self._items:
            return
        canvas_h = self._canvas.winfo_height()
        if canvas_h <= 1:
            return

        top = self._canvas.canvasy(0)
        bot = self._canvas.canvasy(canvas_h)

        first = max(0, int(top // self._ROW_H) - self._BUFFER)
        last  = min(len(self._items) - 1,
                    int(bot // self._ROW_H) + self._BUFFER)

        # Destroy rows that have scrolled out of range
        stale = [i for i in self._rendered if i < first or i > last]
        for i in stale:
            wid, widget = self._rendered.pop(i)
            self._canvas.delete(wid)
            widget.destroy()

        # Create rows that are now in range
        for i in range(first, last + 1):
            if i in self._rendered:
                continue
            path, status = self._items[i]
            row = _FileRow(self._canvas, path, status,
                           self._on_click, self._on_right_click_file,
                           bg=_ITEM_BG)
            wid = self._canvas.create_window(
                0, i * self._ROW_H,
                window=row, anchor="nw", width=self._canvas_w,
            )
            self._rendered[i] = (wid, row)
            # File rows get their own right-click; wheel forwarded to canvas
            for w in (row,) + tuple(row.winfo_children()):
                w.bind("<MouseWheel>", self._on_wheel)
                w.bind("<Button-4>",   self._on_wheel)
                w.bind("<Button-5>",   self._on_wheel)

    # ── Public API ────────────────────────────────────────────────────────────

    def populate(self, items: dict[str, str],
                 on_click: Callable, on_right_click: Callable,
                 panel_menu_cb: Callable | None = None) -> None:
        # Clear existing rendered rows
        for wid, widget in self._rendered.values():
            self._canvas.delete(wid)
            widget.destroy()
        self._rendered.clear()

        self._items               = list(items.items())
        self._on_click            = on_click
        self._on_right_click_file = on_right_click
        if panel_menu_cb:
            self._panel_menu_cb = panel_menu_cb

        total_h = len(self._items) * self._ROW_H
        self._canvas.configure(scrollregion=(0, 0, self._canvas_w, total_h))
        self._canvas.yview_moveto(0)

        self.set_count(len(self._items))
        self._update_scrollbar()
        self._render_visible()
        if not self._collapsed:
            self._repack()

    def set_count(self, n: int) -> None:
        self._count_lbl.config(text=f"({n})")

    def bind_panel_menu(self, callback) -> None:
        self._panel_menu_cb = callback
        for w in (self, self._scroll_frame, self._canvas):
            bind_right_click(w, callback)
        # Apply to already-rendered rows
        for _, widget in self._rendered.values():
            for w in (widget,) + tuple(widget.winfo_children()):
                bind_right_click(w, callback)

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._arrow.config(text="▸" if self._collapsed else "▾")
        self._repack()
        if self._on_toggle:
            self._on_toggle()

    def _repack(self) -> None:
        self._scroll_frame.pack_forget()
        if not self._collapsed:
            self._scroll_frame.pack(fill="both", expand=True)
            self.after(10, self._render_visible)

    def apply_theme(self, bg: str, fg: str) -> None:
        self._bg = bg
        self.config(bg=bg)
        self._scroll_frame.config(bg=bg)
        self._canvas.config(bg=bg)


class _HistorySection(Frame):
    """Collapsible commit history: search bar + scrollable commit rows with
    expandable file lists and hover popups."""

    _ROW_H      = 26   # commit row height px
    _FILE_ROW_H = 20   # file sub-row height px
    _HDR_H      = 24   # section header height px
    _SEARCH_H   = 36   # search bar height px

    _REF_COLORS = ["#569cd6", "#73c991", "#c586c0", "#ce9178", "#dcdcaa", "#4ec9b0"]

    def __init__(self, parent,
                 on_diff:       "Callable[[str, str], None] | None" = None,
                 on_expand:     "Callable[[str], None] | None"      = None,
                 on_load_more:  "Callable[[], None] | None"         = None,
                 on_toggle:     "Callable[[], None] | None"         = None) -> None:
        super().__init__(parent, bg=_BG)
        self.pack_propagate(False)

        self._on_diff       = on_diff
        self._on_expand     = on_expand
        self._on_load_more  = on_load_more
        self._on_toggle     = on_toggle

        self._commits:    list  = []
        self._filtered:   list  = []
        self._expanded:   set   = set()
        self._file_cache: dict  = {}   # hash -> list[(status, path)] | None=loading
        self._collapsed        = True
        self._search_active    = False
        self._hover_popup      = None
        self._hover_after      = None

        self._build_header()
        self._build_search()
        self._build_canvas()

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_header(self) -> None:
        hdr = self._hdr = Frame(self, bg=_HDR_BG, height=self._HDR_H, cursor="hand2")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._arrow = Label(hdr, text="▸", bg=_HDR_BG, fg=_FG,
                            font=("Segoe UI", 8))
        self._arrow.pack(side="left", padx=(4, 0))
        Label(hdr, text="HISTORY", bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)
        self._count_lbl = Label(hdr, text="", bg=_HDR_BG, fg=_DIM,
                                font=("Segoe UI", 8), padx=6)
        self._count_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle())
        hdr.bind("<Button-1>", lambda _: self._toggle())

    def _build_search(self) -> None:
        self._search_frame = Frame(self, bg=_BG)

        inner = Frame(self._search_frame, bg="#3c3c3c")
        inner.pack(fill="x", padx=6, pady=4)

        Label(inner, text="⌕", bg="#3c3c3c", fg=_DIM,
              font=("Segoe UI", 10), padx=4).pack(side="left")

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._apply_filter())
        self._search_entry = tk.Entry(
            inner, textvariable=self._search_var,
            bg="#3c3c3c", fg=_DIM, insertbackground=_FG,
            relief="flat", font=("Segoe UI", 8), bd=0,
        )
        self._search_entry.insert(0, "Filter commits…")
        self._search_entry.pack(side="left", fill="x", expand=True, padx=4, pady=3)
        self._search_entry.bind("<FocusIn>",  self._search_focus_in)
        self._search_entry.bind("<FocusOut>", self._search_focus_out)

    def _build_canvas(self) -> None:
        self._canvas_frame = Frame(self, bg=_BG)

        self._vsb = ttk.Scrollbar(self._canvas_frame, orient="vertical")
        self._vsb.pack(side="right", fill="y")
        self._canvas = tk.Canvas(self._canvas_frame, bg=_BG,
                                 highlightthickness=0, bd=0,
                                 yscrollcommand=self._vsb.set)
        self._canvas.pack(side="left", fill="both", expand=True)
        self._vsb.configure(command=self._canvas.yview)

        self._inner = Frame(self._canvas, bg=_BG)
        self._win = self._canvas.create_window(0, 0, window=self._inner, anchor="nw")
        self._inner.bind("<Configure>",
                         lambda _: self._canvas.configure(
                             scrollregion=self._canvas.bbox("all")))
        self._canvas.bind("<Configure>",
                          lambda e: self._canvas.itemconfigure(
                              self._win, width=e.width))
        for w in (self._canvas, self._inner):
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

    # ── Scroll ────────────────────────────────────────────────────────────────

    def _on_wheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._canvas.yview_scroll(-1, "units")
        else:
            self._canvas.yview_scroll(1, "units")

    # ── Toggle / search ───────────────────────────────────────────────────────

    def _toggle(self) -> None:
        self._collapsed = not self._collapsed
        self._arrow.config(text="▸" if self._collapsed else "▾")
        if self._collapsed:
            self._search_frame.pack_forget()
            self._canvas_frame.pack_forget()
        else:
            self._search_frame.pack(fill="x")
            self._canvas_frame.pack(fill="both", expand=True)
        if self._on_toggle:
            self._on_toggle()

    def _search_focus_in(self, _) -> None:
        if not self._search_active:
            self._search_entry.delete(0, "end")
            self._search_entry.config(fg=_FG)
            self._search_active = True

    def _search_focus_out(self, _) -> None:
        if not self._search_entry.get():
            self._search_entry.insert(0, "Filter commits…")
            self._search_entry.config(fg=_DIM)
            self._search_active = False

    # ── Public API ────────────────────────────────────────────────────────────

    def load(self, commits: list) -> None:
        self._commits = commits
        self._count_lbl.config(text=f"({len(commits)})")
        self._apply_filter()

    def cache_files(self, commit_hash: str, files: list) -> None:
        """Called when git returns the file list for an expanded commit."""
        self._file_cache[commit_hash] = files
        self._rebuild_rows()

    def apply_theme(self, bg: str, fg: str) -> None:
        pass   # colours are hardcoded to dark theme constants for now

    # ── Filter + render ───────────────────────────────────────────────────────

    def _apply_filter(self) -> None:
        query = (self._search_var.get().lower().strip()
                 if self._search_active else "")
        if query:
            self._filtered = [
                c for c in self._commits
                if query in c.subject.lower()
                or query in c.author.lower()
                or query in c.short.lower()
                or any(query in r.lower() for r in c.refs)
            ]
        else:
            self._filtered = list(self._commits)
        self._rebuild_rows()

    def _rebuild_rows(self) -> None:
        if not hasattr(self, "_inner"):
            return   # canvas not built yet (trace fired during __init__)
        self._hide_hover()
        for w in self._inner.winfo_children():
            w.destroy()
        for commit in self._filtered:
            self._build_commit_row(commit)
        # "Load more" button
        if len(self._commits) >= 50 and self._on_load_more:
            btn_f = Frame(self._inner, bg=_BG)
            btn_f.pack(fill="x", pady=4)
            lbl = Label(btn_f, text="  Load 50 more…", bg=_BG, fg=_DIM,
                        font=("Segoe UI", 8), cursor="hand2", pady=4, anchor="w")
            lbl.pack(fill="x")
            lbl.bind("<Button-1>", lambda _: self._on_load_more())
            lbl.bind("<Enter>", lambda _: lbl.config(fg=_FG))
            lbl.bind("<Leave>", lambda _: lbl.config(fg=_DIM))
            btn_f.bind("<MouseWheel>", self._on_wheel)
            lbl.bind("<MouseWheel>",   self._on_wheel)

    def _ref_color(self, ref: str, idx: int) -> str:
        rl = ref.lower()
        if "main" in rl or "master" in rl:  return "#569cd6"
        if rl.startswith("tag:"):           return "#dcdcaa"
        if "head" in rl:                    return "#73c991"
        if "origin" in rl:                  return "#4ec9b0"
        return self._REF_COLORS[idx % len(self._REF_COLORS)]

    def _build_commit_row(self, commit) -> None:
        is_expanded = commit.hash in self._expanded

        row = Frame(self._inner, bg=_ITEM_BG, cursor="hand2",
                    height=self._ROW_H)
        row.pack(fill="x")
        row.pack_propagate(False)

        # Dot
        Label(row, text="●", bg=_ITEM_BG, fg="#569cd6",
              font=("Segoe UI", 7), padx=4).pack(side="left")

        # Ref badges (max 2)
        for i, ref in enumerate(commit.refs[:2]):
            if not ref:
                continue
            display = ref
            if "->" in ref:
                display = ref.split("->")[-1].strip()
            elif ref.lower().startswith("tag:"):
                display = ref[4:].strip()
            if display.startswith("origin/"):
                display = display[7:]
            if len(display) > 10:
                display = display[:9] + "…"
            color = self._ref_color(ref, i)
            Label(row, text=f" {display} ", bg=_ITEM_BG, fg=color,
                  font=("Segoe UI", 7, "bold"), padx=1).pack(side="left")

        # Short hash
        Label(row, text=commit.short, bg=_ITEM_BG, fg=_DIM,
              font=("Consolas", 8), padx=3).pack(side="left")

        # Author + time (right side)
        Label(row, text=f"{commit.author}  {commit.rel_time}",
              bg=_ITEM_BG, fg=_DIM,
              font=("Segoe UI", 7), padx=4).pack(side="right")

        # Subject (fills remaining width)
        Label(row, text=commit.subject, bg=_ITEM_BG, fg=_FG,
              font=("Segoe UI", 8), anchor="w").pack(
                  side="left", fill="x", expand=True)

        # Expand arrow overlay (bottom-right)
        exp = Label(row, text="▾" if is_expanded else "▸",
                    bg=_ITEM_BG, fg=_DIM, font=("Segoe UI", 7), padx=4)
        exp.place(relx=0.0, rely=0.5, anchor="w", x=2)

        def _hover_enter(e, c=commit, r=row):
            self._schedule_hover(e, c)
            self._row_highlight(r, True)

        def _hover_leave(_, r=row):
            self._cancel_hover()
            self._row_highlight(r, False)

        def _click(_, c=commit):
            self._hide_hover()
            self._toggle_expand(c)

        for w in [row] + list(row.winfo_children()):
            w.bind("<Enter>",      _hover_enter)
            w.bind("<Leave>",      _hover_leave)
            w.bind("<Button-1>",   _click)
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

        # File sub-rows when expanded
        if is_expanded:
            files = self._file_cache.get(commit.hash)
            if files is None:
                # Still loading
                loading = Frame(self._inner, bg=_BG)
                loading.pack(fill="x")
                Label(loading, text="     Loading…", bg=_BG, fg=_DIM,
                      font=("Segoe UI", 8), pady=2).pack(side="left")
                for w in (loading,) + tuple(loading.winfo_children()):
                    w.bind("<MouseWheel>", self._on_wheel)
            else:
                for status, filepath in files:
                    self._build_file_row(commit.hash, status, filepath)

    def _build_file_row(self, commit_hash: str,
                        status: str, filepath: str) -> None:
        color = STATUS_COLORS.get(status, _FG)
        row = Frame(self._inner, bg=_BG, cursor="hand2",
                    height=self._FILE_ROW_H)
        row.pack(fill="x")
        row.pack_propagate(False)

        Label(row, text="   │ ", bg=_BG, fg=_DIM,
              font=("Segoe UI", 8)).pack(side="left")
        Label(row, text=os.path.basename(filepath), bg=_BG, fg=color,
              font=("Segoe UI", 8), anchor="w").pack(
                  side="left", fill="x", expand=True)
        Label(row, text=f" {status} ", bg=_BG, fg=color,
              font=("Segoe UI", 8, "bold"), padx=4).pack(side="right")

        def _enter(_, r=row):
            r.config(bg=_HOV_BG)
            for w in r.winfo_children(): w.config(bg=_HOV_BG)

        def _leave(_, r=row):
            r.config(bg=_BG)
            for w in r.winfo_children(): w.config(bg=_BG)

        def _click(_, h=commit_hash, fp=filepath):
            if self._on_diff:
                self._on_diff(h, fp)

        for w in [row] + list(row.winfo_children()):
            w.bind("<Enter>",      _enter)
            w.bind("<Leave>",      _leave)
            w.bind("<Button-1>",   _click)
            w.bind("<MouseWheel>", self._on_wheel)
            w.bind("<Button-4>",   self._on_wheel)
            w.bind("<Button-5>",   self._on_wheel)

    def _row_highlight(self, row: Frame, on: bool) -> None:
        c = _HOV_BG if on else _ITEM_BG
        try:
            row.config(bg=c)
            for w in row.winfo_children():
                w.config(bg=c)
        except Exception:
            pass

    def _toggle_expand(self, commit) -> None:
        if commit.hash in self._expanded:
            self._expanded.discard(commit.hash)
        else:
            self._expanded.add(commit.hash)
            if commit.hash not in self._file_cache:
                self._file_cache[commit.hash] = None   # mark as loading
                if self._on_expand:
                    self._on_expand(commit.hash)
        self._rebuild_rows()

    # ── Hover popup ───────────────────────────────────────────────────────────

    def _schedule_hover(self, event, commit) -> None:
        self._cancel_hover()
        self._hover_after = self.after(
            550, lambda e=event, c=commit: self._show_hover(e, c))

    def _cancel_hover(self) -> None:
        if self._hover_after:
            self.after_cancel(self._hover_after)
            self._hover_after = None

    def _hide_hover(self) -> None:
        self._cancel_hover()
        if self._hover_popup:
            try:
                self._hover_popup.destroy()
            except Exception:
                pass
            self._hover_popup = None

    def _show_hover(self, event, commit) -> None:
        self._hide_hover()
        popup = tk.Toplevel(self)
        popup.overrideredirect(True)
        popup.attributes("-topmost", True)
        self._hover_popup = popup

        outer = Frame(popup, bg="#454545", padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        body = Frame(outer, bg="#1e1e1e", padx=10, pady=8)
        body.pack(fill="both", expand=True)

        # Hash · relative time
        Label(body, text=f"{commit.hash[:12]}  ·  {commit.rel_time}",
              bg="#1e1e1e", fg=_DIM, font=("Consolas", 8)).pack(anchor="w")
        # Author
        Label(body, text=commit.author, bg="#1e1e1e", fg="#73c991",
              font=("Segoe UI", 8)).pack(anchor="w")
        # Absolute time
        abs_display = commit.abs_time[:19].replace("T", "  ")
        Label(body, text=abs_display, bg="#1e1e1e", fg=_DIM,
              font=("Segoe UI", 7)).pack(anchor="w")

        Frame(body, bg="#454545", height=1).pack(fill="x", pady=(5, 4))

        # Subject (wrapped)
        Label(body, text=commit.subject, bg="#1e1e1e", fg=_FG,
              font=("Segoe UI", 9), wraplength=300,
              justify="left").pack(anchor="w")

        # Ref badges
        if commit.refs:
            Frame(body, bg="#454545", height=1).pack(fill="x", pady=(5, 3))
            for i, ref in enumerate(commit.refs):
                color = self._ref_color(ref, i)
                Label(body, text=f"  {ref}", bg="#1e1e1e", fg=color,
                      font=("Segoe UI", 8)).pack(anchor="w")

        popup.update_idletasks()
        pw = popup.winfo_reqwidth()
        ph = popup.winfo_reqheight()
        x  = event.x_root + 14
        y  = event.y_root - ph // 2
        sw = popup.winfo_screenwidth()
        sh = popup.winfo_screenheight()
        if x + pw > sw - 10:
            x = event.x_root - pw - 14
        y = max(10, min(y, sh - ph - 10))
        popup.geometry(f"+{x}+{y}")
        popup.bind("<Leave>", lambda _: self._hide_hover())


class SourceControlPanel(ttk.Frame):
    """Git source control panel: staged / unstaged file lists + commit UI."""

    _GITIGNORE_WARN_THRESHOLD = 50

    def __init__(
        self,
        parent,
        on_stage:             Callable[[str], None],
        on_unstage:           Callable[[str], None],
        on_discard:           Callable[[str], None],
        on_commit:            Callable[[str], None],
        on_push:              Callable[[], None],
        on_pull:              Callable[[], None],
        on_diff:              Callable[[str], None],
        on_create_gitignore:  Callable[[], None] | None = None,
        on_add_to_gitignore:  Callable[[str], None] | None = None,
        on_untrack_venv:      Callable[[], None] | None = None,
        gitignore_check_fn:   Callable[[], bool] | None = None,
        repo_root_fn:         Callable[[], str] | None = None,
        on_history_diff:      Callable[[str, str], None] | None = None,
        on_expand_commit:     Callable[[str], None] | None = None,
        **kwargs,
    ) -> None:
        super().__init__(parent, **kwargs)
        self._on_stage              = on_stage
        self._on_unstage            = on_unstage
        self._on_discard            = on_discard
        self._on_commit             = on_commit
        self._on_push               = on_push
        self._on_pull               = on_pull
        self._on_diff               = on_diff
        self._on_create_gitignore   = on_create_gitignore
        self._on_add_to_gitignore   = on_add_to_gitignore
        self._on_untrack_venv       = on_untrack_venv
        self._gitignore_check_fn    = gitignore_check_fn
        self._repo_root_fn          = repo_root_fn
        self._on_history_diff       = on_history_diff
        self._on_expand_commit      = on_expand_commit
        self._ctx_path            = ""
        self._warn_visible        = False
        self._last_staged:  dict[str, str] = {}
        self._last_unstaged: dict[str, str] = {}

        ttk.Style().configure("SC.TFrame", background=_BG)
        self.configure(style="SC.TFrame")

        self._build_commit_area()
        ttk.Separator(self, orient="horizontal").pack(fill="x")
        self._build_body_canvas()
        self._build_health_panel()

        # Smart warning banner — shown when issues detected
        self._warn_frame = Frame(self._body_frame, bg="#3c2a00", cursor="hand2")
        self._warn_lbl = Label(self._warn_frame,
                         text="", bg="#3c2a00", fg="#e2c08d",
                         font=("Segoe UI", 8), justify="left",
                         padx=8, pady=4, cursor="hand2", wraplength=180)
        self._warn_lbl.pack(side="left", fill="x", expand=True)
        self._warn_details_btn = Label(self._warn_frame, text="Details →",
                                       bg="#3c2a00", fg="#e2c08d",
                                       font=("Segoe UI", 8, "bold"),
                                       padx=6, pady=4, cursor="hand2")
        self._warn_details_btn.pack(side="right")
        for w in (self._warn_frame, self._warn_lbl, self._warn_details_btn):
            w.bind("<Button-1>", lambda _: self._open_wizard())
        for w in (self._warn_frame, self._warn_lbl, self._warn_details_btn):
            w.bind("<MouseWheel>", self._on_body_wheel)
            w.bind("<Button-4>",   self._on_body_wheel)
            w.bind("<Button-5>",   self._on_body_wheel)
        self._current_issues: list[Issue] = []

        self._staged_sec   = _Section(self._body_frame, "STAGED CHANGES",
                                      on_toggle=self._repack_sections)
        self._sep = ttk.Separator(self._body_frame, orient="horizontal")
        self._unstaged_sec = _Section(self._body_frame, "CHANGES",
                                      on_toggle=self._repack_sections)
        self._hist_sep   = ttk.Separator(self._body_frame, orient="horizontal")
        self._history_sec = _HistorySection(
            self._body_frame,
            on_diff=self._on_history_diff,
            on_expand=self._on_expand_commit,
            on_load_more=self._history_load_more,
            on_toggle=self._repack_sections,
        )
        self._history_offset = 0   # how many commits already loaded
        self._repack_sections()

        LearningManager.register(self._staged_sec,   "sc_stage_btn")
        LearningManager.register(self._unstaged_sec, "sc_stage_btn")
        LearningManager.register(self._history_sec,  "commit_history")

        # Single unified context menu — items shown/hidden based on context
        self._ctx_menu = Menu(self, tearoff=0)
        self._ctx_menu.add_command(label="Open Changes",     command=self._ctx_do_diff)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Stage Changes",    command=self._ctx_do_stage)
        self._ctx_menu.add_command(label="Unstage Changes",  command=self._ctx_do_unstage)
        self._ctx_menu.add_command(label="Discard Changes",  command=self._ctx_do_discard)
        self._ctx_menu.add_separator()
        self._ctx_menu.add_command(label="Add to .gitignore", command=self._ctx_add_to_gitignore)
        self._ctx_menu.add_command(label="Create .gitignore", command=self._ctx_create_gitignore)

        self._ctx_section = None  # "staged" | "changes" | None
        bind_right_click(self, lambda e: self._show_ctx(e, "", None))
        self._staged_sec.bind_panel_menu(lambda e: self._show_ctx(e, "", None))
        self._unstaged_sec.bind_panel_menu(lambda e: self._show_ctx(e, "", None))

    # ── Layout ────────────────────────────────────────────────────────────────

    def _repack_sections(self) -> None:
        """Re-pack all sections so layout reflects current state."""
        self._warn_frame.pack_forget()
        self._staged_sec.pack_forget()
        self._sep.pack_forget()
        self._unstaged_sec.pack_forget()
        self._hist_sep.pack_forget()
        self._history_sec.pack_forget()

        staged_has_items = bool(self._staged_sec._items)

        if self._warn_visible:
            self._warn_frame.pack(fill="x")
        self._staged_sec.pack(fill="x")
        if staged_has_items:
            self._sep.pack(fill="x")
        self._unstaged_sec.pack(fill="x")
        self._hist_sep.pack(fill="x")
        self._history_sec.pack(fill="x")
        self._update_body_layout()

    # ── Public API ────────────────────────────────────────────────────────────

    def refresh(self, staged: dict[str, str], unstaged: dict[str, str]) -> None:
        """Re-populate both file lists and update diagnostics."""
        self._last_staged   = staged
        self._last_unstaged = unstaged

        # Smart issue detection
        repo_root = self._repo_root_fn() if self._repo_root_fn else ""
        fix_fns = {
            "create_gitignore": self._ctx_create_gitignore,
            "untrack_venv":     self._ctx_untrack_venv,
        }
        self._current_issues = analyze_files(unstaged, fix_fns=fix_fns, repo_root=repo_root)

        # Update warning banner with specific message
        high_issues = [i for i in self._current_issues if i.severity == "high"]
        self._warn_visible = bool(high_issues)
        if self._warn_visible:
            if len(high_issues) == 1:
                msg = f"⚠ {high_issues[0].title}"
            else:
                msg = f"⚠ {len(high_issues)} issues detected"
            self._warn_lbl.config(text=msg)
            self._warn_frame.pack(fill="x", before=self._staged_sec)
        else:
            self._warn_frame.pack_forget()

        # Update health panel
        self._refresh_health(staged, unstaged)

        self._staged_sec.populate(
            staged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "staged"),
            panel_menu_cb=lambda e: self._show_ctx(e, "", None),
        )
        self._unstaged_sec.populate(
            unstaged,
            on_click=self._on_diff,
            on_right_click=lambda e, p: self._show_ctx(e, p, "changes"),
            panel_menu_cb=lambda e: self._show_ctx(e, "", None),
        )
        self._repack_sections()

    def refresh_history(self, commits: list) -> None:
        """Populate the HISTORY section with a new commit list."""
        self._history_offset = len(commits)
        self._history_sec.load(commits)
        self._repack_sections()

    def commit_files_ready(self, commit_hash: str, files: list) -> None:
        """Forward fetched file list to the history section."""
        self._history_sec.cache_files(commit_hash, files)

    def _history_load_more(self) -> None:
        """Called when user clicks 'Load 50 more' — delegated to app via on_expand."""
        # Re-use on_expand_commit with a sentinel to signal load-more
        if self._on_expand_commit:
            self._on_expand_commit(f"__load_more__:{self._history_offset}")

    def apply_theme(self, bg: str, fg: str, select_bg: str) -> None:
        ttk.Style().configure("SC.TFrame", background=bg)
        self._staged_sec.apply_theme(bg, fg)
        self._unstaged_sec.apply_theme(bg, fg)

    # ── Commit area ───────────────────────────────────────────────────────────

    def _build_commit_area(self) -> None:
        outer = Frame(self, bg=_BG, padx=6, pady=6)
        outer.pack(fill="x")

        # Placeholder-style Text widget for commit message
        self._msg = tk.Text(
            outer,
            height=3,
            bg="#3c3c3c",
            fg=_DIM,
            insertbackground=_FG,
            font=("Segoe UI", 9),
            relief="flat",
            padx=6,
            pady=4,
            wrap="word",
        )
        self._msg.insert("1.0", "Commit message…")
        self._msg.pack(fill="x")
        self._msg.bind("<FocusIn>",  self._msg_focus_in)
        self._msg.bind("<FocusOut>", self._msg_focus_out)
        self._placeholder_active = True

        # Buttons row — Labels used instead of Buttons for consistent cross-platform styling
        btn_row = Frame(outer, bg=_BG)
        btn_row.pack(fill="x", pady=(5, 0))

        def _btn(parent, text, command):
            lbl = Label(parent, text=text, bg=_BTN_BG, fg="white",
                        font=("Segoe UI", 8, "bold"), cursor="hand2",
                        padx=8, pady=3)
            lbl.bind("<Button-1>", lambda _: command())
            lbl.bind("<Enter>", lambda _: lbl.config(bg=_BTN_ACT))
            lbl.bind("<Leave>", lambda _: lbl.config(bg=_BTN_BG))
            return lbl

        self._commit_btn = _btn(btn_row, "✓ Commit", self._do_commit)
        self._commit_btn.pack(side="left")
        self._push_btn = self._make_confirm_btn(btn_row, "↑ Push", self._on_push)
        self._push_btn.pack(side="left", padx=(4, 0))
        self._pull_btn = self._make_confirm_btn(btn_row, "↓ Pull", self._on_pull)
        self._pull_btn.pack(side="left", padx=(4, 0))

        LearningManager.register(self._commit_btn, "sc_commit_btn")
        LearningManager.register(self._push_btn,   "sc_push_btn")
        LearningManager.register(self._pull_btn,   "sc_pull_btn")

    _BTN_CONFIRM = "#c47a00"   # amber — "are you sure?"
    _BTN_CONF_ACT = "#d48b0e"  # slightly lighter on hover

    def _make_confirm_btn(self, parent, label: str, action: Callable) -> Label:
        """Two-stage push/pull button: first click arms it (amber), second fires."""
        _armed = [False]
        _reset_id = [None]

        lbl = Label(parent, text=label, bg=_BTN_BG, fg="white",
                    font=("Segoe UI", 8, "bold"), cursor="hand2",
                    padx=8, pady=3)

        def _reset():
            _armed[0] = False
            lbl.config(text=label, bg=_BTN_BG)
            if _reset_id[0]:
                lbl.after_cancel(_reset_id[0])
                _reset_id[0] = None

        def _click(_evt=None):
            if not _armed[0]:
                # Arm it
                _armed[0] = True
                lbl.config(text=label.split()[0] + " Confirm?",
                           bg=self._BTN_CONFIRM)
                if _reset_id[0]:
                    lbl.after_cancel(_reset_id[0])
                _reset_id[0] = lbl.after(3000, _reset)
            else:
                # Execute and reset
                _reset()
                action()

        def _enter(_):
            lbl.config(bg=self._BTN_CONF_ACT if _armed[0] else _BTN_ACT)

        def _leave(_):
            lbl.config(bg=self._BTN_CONFIRM if _armed[0] else _BTN_BG)

        lbl.bind("<Button-1>", _click)
        lbl.bind("<Enter>",    _enter)
        lbl.bind("<Leave>",    _leave)
        return lbl

    def _msg_focus_in(self, _) -> None:
        if self._placeholder_active:
            self._msg.delete("1.0", "end")
            self._msg.config(fg=_FG)
            self._placeholder_active = False

    def _msg_focus_out(self, _) -> None:
        if not self._msg.get("1.0", "end-1c").strip():
            self._msg.delete("1.0", "end")
            self._msg.insert("1.0", "Commit message…")
            self._msg.config(fg=_DIM)
            self._placeholder_active = True

    def _do_commit(self) -> None:
        msg = self._msg.get("1.0", "end-1c").strip()
        if not msg or self._placeholder_active:
            return
        self._on_commit(msg)
        # Clear message field after commit
        self._msg.delete("1.0", "end")
        self._msg.insert("1.0", "Commit message…")
        self._msg.config(fg=_DIM)
        self._placeholder_active = True

    # ── Scrollable body ───────────────────────────────────────────────────────

    def _build_body_canvas(self) -> None:
        """Create the scrollable canvas that holds health + file sections."""
        self._body_updating = False
        self._body_vs_visible = True
        body_outer = Frame(self, bg=_BG)
        body_outer.pack(fill="both", expand=True)
        self._body_vsb = ttk.Scrollbar(body_outer, orient="vertical")
        self._body_vsb.pack(side="right", fill="y")
        self._body_canvas = tk.Canvas(body_outer, bg=_BG, highlightthickness=0, bd=0,
                                      yscrollcommand=self._body_vsb.set)
        self._body_canvas.pack(side="left", fill="both", expand=True)
        self._body_vsb.configure(command=self._body_canvas.yview)
        self._body_frame = Frame(self._body_canvas, bg=_BG)
        self._body_win = self._body_canvas.create_window(
            0, 0, window=self._body_frame, anchor="nw"
        )
        self._body_frame.bind("<Configure>", lambda _e: self._update_body_layout())
        self._body_canvas.bind("<Configure>", lambda _e: self._update_body_layout())
        for w in (self._body_canvas, self._body_frame):
            w.bind("<MouseWheel>", self._on_body_wheel)
            w.bind("<Button-4>",   self._on_body_wheel)
            w.bind("<Button-5>",   self._on_body_wheel)
        bind_right_click(self._body_canvas, lambda e: self._show_ctx(e, "", None))
        bind_right_click(self._body_frame,  lambda e: self._show_ctx(e, "", None))

    def _on_body_wheel(self, event) -> None:
        if event.num == 4 or event.delta > 0:
            self._body_canvas.yview_scroll(-1, "units")
        else:
            self._body_canvas.yview_scroll(1, "units")

    def _update_body_layout(self) -> None:
        """Compute section heights and update canvas scrollregion."""
        if self._body_updating:
            return
        self._body_updating = True
        try:
            self.update_idletasks()   # flush pending geometry before measuring
            canvas_h = self._body_canvas.winfo_height()
            canvas_w = self._body_canvas.winfo_width()
            if canvas_h <= 1 or canvas_w <= 1:
                return

            _HDR = 24
            _ROW = _Section._ROW_H
            _MAX_SEC = 250
            _MIN_CONTENT = 60

            # Fixed content heights
            if self._health_collapsed:
                health_h = _HDR
            else:
                health_h = max(_HDR, self._health_frame.winfo_reqheight())
            warn_h = self._warn_frame.winfo_reqheight() if self._warn_visible else 0

            # Section natural heights
            _SEARCH = _HistorySection._SEARCH_H
            staged_has   = bool(self._staged_sec._items)
            n_staged     = len(self._staged_sec._items)
            n_unstaged   = len(self._unstaged_sec._items)
            n_history    = len(self._history_sec._filtered)
            sep_h        = 2 if staged_has else 0
            hist_sep_h   = 1

            if self._staged_sec._collapsed or not staged_has:
                staged_natural = _HDR
            else:
                staged_natural = _HDR + max(_MIN_CONTENT, min(n_staged * _ROW, _MAX_SEC))

            if self._unstaged_sec._collapsed:
                unstaged_natural = _HDR
            else:
                unstaged_natural = _HDR + max(_MIN_CONTENT if n_unstaged > 0 else 0,
                                              min(n_unstaged * _ROW, _MAX_SEC))

            if self._history_sec._collapsed:
                history_natural = _HDR
            else:
                history_natural = _HDR + _SEARCH + max(
                    _MIN_CONTENT if n_history > 0 else 0,
                    min(n_history * _HistorySection._ROW_H, _MAX_SEC))

            fixed_h       = health_h + warn_h + sep_h + hist_sep_h
            total_natural = fixed_h + staged_natural + unstaged_natural + history_natural
            extra         = max(0, canvas_h - total_natural)

            staged_growable   = staged_has and not self._staged_sec._collapsed
            unstaged_growable = not self._unstaged_sec._collapsed
            history_growable  = not self._history_sec._collapsed and n_history > 0
            n_growable        = sum([staged_growable, unstaged_growable, history_growable])
            extra_per         = extra // n_growable if n_growable > 0 else 0

            staged_h   = staged_natural   + (extra_per if staged_growable   else 0)
            unstaged_h = unstaged_natural + (extra_per if unstaged_growable else 0)
            history_h  = history_natural  + (extra_per if history_growable  else 0)

            # Give leftover pixel(s) to unstaged
            used = fixed_h + staged_h + unstaged_h + history_h
            leftover = canvas_h - used
            if leftover > 0 and unstaged_growable:
                unstaged_h += leftover

            self._staged_sec.config(height=staged_h)
            self._unstaged_sec.config(height=unstaged_h)
            self._history_sec.config(height=history_h)

            frame_h = max(fixed_h + staged_h + unstaged_h + history_h, canvas_h)
            self._body_canvas.itemconfigure(self._body_win, width=canvas_w, height=frame_h)
            self._body_canvas.configure(scrollregion=(0, 0, 0, frame_h))
        finally:
            self._body_updating = False

    # ── Git Health panel ──────────────────────────────────────────────────────

    def _build_health_panel(self) -> None:
        """Build the collapsible Git Health checklist panel."""
        self._health_collapsed = True
        self._health_frame = Frame(self._body_frame, bg=_BG)

        hdr = self._health_hdr = Frame(self._health_frame, bg=_HDR_BG, height=24, cursor="hand2")
        hdr.pack(fill="x")
        hdr.pack_propagate(False)

        self._health_arrow = Label(hdr, text="▸", bg=_HDR_BG, fg=_FG,
                                   font=("Segoe UI", 8))
        self._health_arrow.pack(side="left", padx=(4, 0))
        Label(hdr, text="GIT HEALTH", bg=_HDR_BG, fg=_FG,
              font=("Segoe UI", 8, "bold"), anchor="w").pack(
                  side="left", fill="x", expand=True)
        self._health_status_lbl = Label(hdr, text="", bg=_HDR_BG,
                                        font=("Segoe UI", 8), padx=6)
        self._health_status_lbl.pack(side="right")

        for w in hdr.winfo_children():
            w.bind("<Button-1>", lambda _: self._toggle_health())
        hdr.bind("<Button-1>", lambda _: self._toggle_health())

        self._health_body = Frame(self._health_frame, bg=_BG)
        self._health_rows: list[Frame] = []

        self._health_frame.pack(fill="x")
        LearningManager.register(self._health_frame, "git_health_panel")

        # Populate immediately so git-not-installed is visible before any git callback fires
        self._refresh_health({}, {})

    def _toggle_health(self) -> None:
        self._health_collapsed = not self._health_collapsed
        self._health_arrow.config(text="▸" if self._health_collapsed else "▾")
        if self._health_collapsed:
            self._health_body.pack_forget()
        else:
            self._health_body.pack(fill="x")
        self._update_body_layout()

    def _refresh_health(self, staged: dict[str, str], unstaged: dict[str, str]) -> None:
        """Rebuild the health checklist rows."""
        for w in self._health_body.winfo_children():
            w.destroy()

        if not git_installed():
            self._health_status_lbl.config(text="!", fg="#f14c4c", bg=_HDR_BG)
            self._render_git_missing_row()
            return

        fix_fns = {"create_gitignore": self._ctx_create_gitignore}
        # Pass repo root via gitignore_check_fn closure if available
        checks = self._get_health_checks(staged, unstaged, fix_fns)

        passed = sum(1 for c in checks if c.passed)
        total  = len(checks)
        all_ok = passed == total
        self._health_status_lbl.config(
            text=f"{passed}/{total}" ,
            fg="#73c991" if all_ok else "#e2c08d",
            bg=_HDR_BG,
        )

        for check in checks:
            row = Frame(self._health_body, bg=_BG)
            row.pack(fill="x", padx=6, pady=1)

            icon = "✓" if check.passed else "✗"
            color = "#73c991" if check.passed else "#f14c4c"
            Label(row, text=icon, bg=_BG, fg=color,
                  font=("Segoe UI", 9, "bold"), width=2).pack(side="left")
            Label(row, text=check.label, bg=_BG, fg=_FG,
                  font=("Segoe UI", 8), anchor="w").pack(side="left", fill="x", expand=True)

            if check.fix_fn:
                btn = Label(row, text=check.fix_label, bg=_BTN_BG, fg="white",
                            font=("Segoe UI", 7, "bold"), padx=4, pady=1,
                            cursor="hand2")
                btn.pack(side="right", padx=(0, 2))
                btn.bind("<Button-1>", lambda _, fn=check.fix_fn: fn())

            _Tooltip(row, check.detail)
            for w in (row,) + tuple(row.winfo_children()):
                w.bind("<MouseWheel>", self._on_body_wheel)
                w.bind("<Button-4>",   self._on_body_wheel)
                w.bind("<Button-5>",   self._on_body_wheel)

    def _render_git_missing_row(self) -> None:
        from utils.git_install_guide import get_pages
        row = Frame(self._health_body, bg=_BG, cursor="hand2")
        row.pack(fill="x", padx=6, pady=1)
        Label(row, text="✗", bg=_BG, fg="#f14c4c",
              font=("Segoe UI", 9, "bold"), width=2).pack(side="left")
        lbl = Label(row, text="Git is not installed", bg=_BG, fg=_FG,
                    font=("Segoe UI", 8), anchor="w")
        lbl.pack(side="left", fill="x", expand=True)
        btn = Label(row, text="How to Install →", bg=_BTN_BG, fg="white",
                    font=("Segoe UI", 7, "bold"), padx=4, pady=1, cursor="hand2")
        btn.pack(side="right", padx=(0, 2))

        def _open(_=None):
            GuideWindow(self, "Install Git", get_pages())

        for w in (row, lbl, btn):
            w.bind("<Button-1>", _open)
            w.bind("<MouseWheel>", self._on_body_wheel)
            w.bind("<Button-4>",   self._on_body_wheel)
            w.bind("<Button-5>",   self._on_body_wheel)
        _Tooltip(row, "Git was not found on PATH — click 'How to Install →' for setup instructions.")

    def _get_health_checks(self, staged, unstaged, fix_fns) -> list[HealthCheck]:
        """Get health checks using repo root from app."""
        repo_root = self._repo_root_fn() if self._repo_root_fn else ""
        return health_checks(repo_root, staged, unstaged, fix_fns=fix_fns)

    # ── Guided fix wizard ─────────────────────────────────────────────────────

    def _open_wizard(self) -> None:
        """Open the step-by-step guided fix wizard using GuideWindow."""
        if not self._current_issues:
            return
        pages = [
            GuidePage(
                title=issue.title,
                subtitle=f"Issue {i + 1} of {len(self._current_issues)}",
                sections=[
                    ("WHAT HAPPENED",  issue.what, "#e2c08d"),
                    ("WHY IT MATTERS", issue.why,  "#f14c4c"),
                    ("HOW TO FIX IT",  issue.how,  "#73c991"),
                ],
                action_label=issue.fix_label if issue.fix_fn else "",
                action_fn=issue.fix_fn,
            )
            for i, issue in enumerate(self._current_issues)
        ]
        GuideWindow(self, "Git Fix Guide", pages)

    # ── Context menu helpers ──────────────────────────────────────────────────

    def _show_ctx(self, event, path: str, section: str | None) -> None:
        self._ctx_path    = path
        self._ctx_section = section

        # Show/hide items based on context
        has_file = bool(path)
        self._ctx_menu.entryconfigure("Open Changes",      state="normal" if has_file else "disabled")
        self._ctx_menu.entryconfigure("Stage Changes",     state="normal" if has_file and section == "changes" else "disabled")
        self._ctx_menu.entryconfigure("Unstage Changes",   state="normal" if has_file and section == "staged"  else "disabled")
        self._ctx_menu.entryconfigure("Discard Changes",   state="normal" if has_file and section == "changes" else "disabled")
        self._ctx_menu.entryconfigure("Add to .gitignore", state="normal" if has_file else "disabled")

        self._ctx_menu.tk_popup(event.x_root, event.y_root)

    def _ctx_do_stage(self)   -> None: self._on_stage(self._ctx_path)
    def _ctx_do_unstage(self) -> None: self._on_unstage(self._ctx_path)
    def _ctx_do_discard(self) -> None: self._on_discard(self._ctx_path)
    def _ctx_do_diff(self)    -> None: self._on_diff(self._ctx_path)

    def _ctx_add_to_gitignore(self) -> None:
        if self._on_add_to_gitignore and self._ctx_path:
            self._on_add_to_gitignore(self._ctx_path)

    def _ctx_create_gitignore(self) -> None:
        if self._on_create_gitignore:
            self._on_create_gitignore()

    def _ctx_untrack_venv(self) -> None:
        if self._on_untrack_venv:
            self._on_untrack_venv()

