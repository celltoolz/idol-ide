"""Clipboard history — canvas-virtualized row renderer.

Each clipboard entry is drawn as canvas primitives (rect + text items).
Hover state is updated via itemconfigure on the background rect only — no
widget teardown, no full redraw, sub-millisecond repaint on mouse movement.

This is the pilot for the canvas-renderer pattern that will eventually back
the Outline, References, Source Control, and Explorer panels.  The same
pattern scales to 10 000-row lists: add a <Configure>+yview_moveto handler
that only draws the visible slice.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from tkinter import Canvas, Entry, Frame, Label, Scrollbar, StringVar
from typing import Callable


_MAX   = 50      # ring buffer depth
_ROW_H = 54      # px per row

# ── Palette ───────────────────────────────────────────────────────────────────
_BG      = "#1e1e1e"
_EVEN    = "#252526"
_ODD     = "#2a2a2b"
_HOV     = "#2d2d30"
_SEL     = "#094771"
_FG      = "#cccccc"
_FG_CODE = "#d4d4d4"
_FG_META = "#636363"
_FG_PIN  = "#e8a844"
_ACCENT  = "#007acc"
_SEARCH  = "#3c3c3c"
_BORDER  = "#454545"
_TOOLBAR = "#2d2d2d"


@dataclass
class ClipEntry:
    text:   str
    source: str      = ""
    ts:     datetime = field(default_factory=datetime.now)
    pinned: bool     = False


class ClipboardHistoryPanel(Frame):
    """Canvas-rendered clipboard ring.

    Call push(text, source) whenever the editor copies or cuts.
    The on_paste callback receives the selected text and should insert it into
    the active editor then close/hide the overlay.

    Keyboard shortcuts (when panel has focus):
      Up / Down   — move keyboard selection
      Enter       — paste selected entry
      Ctrl+C      — paste selected entry (natural: "copy from history")
      Escape      — handled by the parent Toplevel binding
    """

    _PX = 10   # horizontal padding
    _PY = 7    # vertical padding (top of row)

    def __init__(self, parent, on_paste: Callable[[str], None] | None = None):
        super().__init__(parent, bg=_BG)
        self._on_paste  = on_paste
        self._window    = None          # set via set_window(); used by pin button
        self._pinned_top: bool = False
        self._ring:    deque[ClipEntry] = deque()
        self._visible: list[ClipEntry]  = []
        self._hovered: int | None       = None
        self._key_sel: int | None       = None   # keyboard-navigated selection
        self._row_bgs: dict[int, int]   = {}     # idx → canvas rect item id

        # ── Toolbar ───────────────────────────────────────────────────────────
        tb = Frame(self, bg=_TOOLBAR, height=28)
        tb.pack(fill="x")
        tb.pack_propagate(False)

        Label(tb, text="Clipboard History", bg=_TOOLBAR, fg="#cccccc",
              font=("Segoe UI", 9, "bold")).pack(side="left", padx=8)

        # Clear-unpinned button
        self._clear_btn = Label(tb, text="🗑", bg=_TOOLBAR, fg="#888",
                                font=("Segoe UI", 10), cursor="hand2")
        self._clear_btn.pack(side="right", padx=(0, 8))
        self._clear_btn.bind("<Button-1>", lambda _: self.clear_unpinned())
        self._clear_btn.bind("<Enter>", lambda _: self._clear_btn.config(fg="#cccccc"))
        self._clear_btn.bind("<Leave>", lambda _: self._clear_btn.config(fg="#888"))

        # Pin-to-top button
        self._pin_btn = Label(tb, text="📌", bg=_TOOLBAR, fg="#888",
                              font=("Segoe UI", 10), cursor="hand2")
        self._pin_btn.pack(side="right", padx=(0, 4))
        self._pin_btn.bind("<Button-1>", lambda _: self._toggle_topmost())
        self._pin_btn.bind("<Enter>",
                           lambda _: self._pin_btn.config(
                               fg=_FG_PIN if not self._pinned_top else "#ffdf80"))
        self._pin_btn.bind("<Leave>",
                           lambda _: self._pin_btn.config(
                               fg=_FG_PIN if self._pinned_top else "#888"))

        # ── Search bar ────────────────────────────────────────────────────────
        sf = Frame(self, bg=_BORDER, padx=1, pady=1)
        sf.pack(fill="x", padx=6, pady=(6, 4))
        inner = Frame(sf, bg=_SEARCH)
        inner.pack(fill="x")
        Label(inner, text="⌕", bg=_SEARCH, fg="#888",
              font=("Segoe UI", 10)).pack(side="left", padx=(6, 2))
        self._q = StringVar()
        self._q.trace_add("write", lambda *_: self._apply_filter())
        self._search = Entry(
            inner, textvariable=self._q, bg=_SEARCH, fg=_FG,
            insertbackground=_FG, relief="flat", font=("Segoe UI", 9), bd=0,
        )
        self._search.pack(side="left", fill="x", expand=True, pady=4, padx=(0, 6))

        # ── Row count label ───────────────────────────────────────────────────
        self._count_lbl = Label(self, bg=_BG, fg=_FG_META,
                                font=("Segoe UI", 8), anchor="e")
        self._count_lbl.pack(fill="x", padx=8)

        # ── Canvas + scrollbar ────────────────────────────────────────────────
        body = Frame(self, bg=_BG)
        body.pack(fill="both", expand=True)
        self._sb = Scrollbar(body, orient="vertical")
        self._sb.pack(side="right", fill="y")
        self._cv = Canvas(body, bg=_BG, highlightthickness=0,
                          yscrollcommand=self._sb.set)
        self._cv.pack(side="left", fill="both", expand=True)
        self._sb.config(command=self._cv.yview)

        self._cv.bind("<Configure>", lambda _: self._redraw())
        self._cv.bind(
            "<MouseWheel>",
            lambda e: self._cv.yview_scroll(-1 * (e.delta // 120), "units"),
        )

        # ── Keyboard navigation (canvas must have focus) ──────────────────────
        self._cv.bind("<Up>",        lambda _: self._key_move(-1))
        self._cv.bind("<Down>",      lambda _: self._key_move(+1))
        self._cv.bind("<Return>",    lambda _: self._key_paste())
        self._cv.bind("<Control-c>", lambda _: self._key_paste())
        # Make canvas focusable so key events fire when clicked
        self._cv.bind("<Button-1>",  lambda _: self._cv.focus_set(), add=True)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_window(self, top) -> None:
        """Tell the panel which Toplevel it lives in (for pin-to-top)."""
        self._window = top

    def push(self, text: str, source: str = "") -> None:
        """Add an entry; deduplicates by content (most-recent wins)."""
        if not text.strip():
            return
        self._ring = deque(e for e in self._ring if e.text != text)
        self._ring.appendleft(ClipEntry(text=text, source=source))
        if len(self._ring) > _MAX:
            pinned   = [e for e in self._ring if e.pinned]
            unpinned = [e for e in self._ring if not e.pinned]
            keep = _MAX - len(pinned)
            self._ring = deque(pinned + unpinned[:keep])
        self._apply_filter()

    def clear_unpinned(self) -> None:
        self._ring = deque(e for e in self._ring if e.pinned)
        self._apply_filter()

    def focus_search(self) -> None:
        self._search.focus_set()
        self._search.select_range(0, "end")

    # ── Internal ──────────────────────────────────────────────────────────────

    def _toggle_topmost(self) -> None:
        if self._window is None:
            return
        self._pinned_top = not self._pinned_top
        self._window.attributes("-topmost", self._pinned_top)
        self._pin_btn.config(fg=_FG_PIN if self._pinned_top else "#888")

    def _apply_filter(self) -> None:
        q = self._q.get().strip().lower()
        self._visible = [
            e for e in self._ring
            if not q or q in e.text.lower() or q in e.source.lower()
        ]
        self._hovered  = None
        self._key_sel  = 0 if self._visible else None
        self._row_bgs.clear()
        n = len(self._ring)
        self._count_lbl.config(
            text=f"{len(self._visible)} of {n} entr{'y' if n == 1 else 'ies'}"
            if q else (f"{n} entr{'y' if n == 1 else 'ies'}" if n else "")
        )
        self._redraw()

    def _redraw(self) -> None:
        """Full canvas redraw.  Called on data / filter / resize changes only."""
        cv = self._cv
        cv.delete("all")
        self._row_bgs.clear()
        w = cv.winfo_width()
        if w <= 1:
            return
        if not self._visible:
            cv.create_text(
                w // 2, 72,
                text="No clipboard entries yet.\n\nCopy or cut text in the editor\nto start building history.",
                fill=_FG_META, font=("Segoe UI", 9), justify="center", anchor="n",
            )
            return
        total_h = len(self._visible) * _ROW_H
        cv.configure(scrollregion=(0, 0, w, total_h))
        for i, entry in enumerate(self._visible):
            self._draw_row(entry, i, w)

    def _draw_row(self, entry: ClipEntry, idx: int, w: int) -> None:
        cv  = self._cv
        y   = idx * _ROW_H
        tag = f"r{idx}"
        bg  = self._row_color(idx)

        # Background rect — the ONLY item touched during hover / key selection
        rect = cv.create_rectangle(0, y, w, y + _ROW_H - 1,
                                   fill=bg, outline="", tags=(tag,))
        self._row_bgs[idx] = rect

        # Pinned accent bar (left edge)
        px = self._PX
        if entry.pinned:
            cv.create_rectangle(0, y, 3, y + _ROW_H - 1,
                                fill=_FG_PIN, outline="", tags=(tag,))
            px += 6

        # Text preview — first line, monospace
        first_line = entry.text.split("\n", 1)[0]
        extra = entry.text.count("\n")
        suffix = f"  +{extra} line{'s' if extra > 1 else ''}" if extra else ""
        cv.create_text(
            px, y + self._PY,
            text=first_line + suffix,
            anchor="nw", fill=_FG_CODE,
            font=("Consolas", 9),
            width=w - px - self._PX,
            tags=(tag,),
        )

        # Metadata (filename · HH:MM:SS) — bottom-right
        parts = ([entry.source] if entry.source else []) + [entry.ts.strftime("%H:%M:%S")]
        cv.create_text(
            w - self._PX, y + _ROW_H - self._PY,
            text="  ·  ".join(parts),
            anchor="se", fill=_FG_META,
            font=("Segoe UI", 8),
            tags=(tag,),
        )

        # ── Tag-level bindings ────────────────────────────────────────────────
        cv.tag_bind(tag, "<Enter>",    lambda e, i=idx: self._hover_on(i))
        cv.tag_bind(tag, "<Leave>",    lambda e, i=idx: self._hover_off(i))
        cv.tag_bind(tag, "<Button-1>", lambda e, i=idx: self._select(i))
        cv.tag_bind(tag, "<Button-3>", lambda e, i=idx: self._toggle_pin(i))

    def _row_color(self, idx: int) -> str:
        if idx == self._key_sel:
            return _SEL
        return _EVEN if idx % 2 == 0 else _ODD

    # ── Hover — pure itemconfigure, no redraw ─────────────────────────────────

    def _hover_on(self, idx: int) -> None:
        prev, self._hovered = self._hovered, idx
        if prev is not None and prev != idx:
            self._restore_bg(prev)
        if idx in self._row_bgs and idx != self._key_sel:
            self._cv.itemconfigure(self._row_bgs[idx], fill=_HOV)

    def _hover_off(self, idx: int) -> None:
        if self._hovered == idx:
            self._hovered = None
        self._restore_bg(idx)

    def _restore_bg(self, idx: int) -> None:
        if idx in self._row_bgs:
            self._cv.itemconfigure(self._row_bgs[idx], fill=self._row_color(idx))

    # ── Click / keyboard actions ──────────────────────────────────────────────

    def _select(self, idx: int) -> None:
        """Mouse click — flash selection color then paste."""
        if 0 <= idx < len(self._visible):
            prev = self._key_sel
            self._key_sel = idx
            if prev is not None:
                self._restore_bg(prev)
            if idx in self._row_bgs:
                self._cv.itemconfigure(self._row_bgs[idx], fill=_SEL)
            if self._on_paste:
                self.after(80, lambda: self._on_paste(self._visible[idx].text))

    def _key_move(self, delta: int) -> None:
        """Up/Down arrow — move keyboard selection."""
        if not self._visible:
            return
        prev = self._key_sel
        cur  = (prev or 0) + delta
        cur  = max(0, min(cur, len(self._visible) - 1))
        self._key_sel = cur
        if prev is not None and prev != cur:
            self._restore_bg(prev)
        if cur in self._row_bgs:
            self._cv.itemconfigure(self._row_bgs[cur], fill=_SEL)
        # Ensure selected row is visible
        total_h = len(self._visible) * _ROW_H
        if total_h > 0:
            self._cv.yview_moveto(cur * _ROW_H / total_h)

    def _key_paste(self) -> None:
        """Enter or Ctrl+C — paste keyboard-selected entry."""
        idx = self._key_sel
        if idx is not None and 0 <= idx < len(self._visible) and self._on_paste:
            self._on_paste(self._visible[idx].text)

    def _toggle_pin(self, idx: int) -> None:
        """Right-click — toggle pin; redraws just that row."""
        if 0 <= idx < len(self._visible):
            self._visible[idx].pinned = not self._visible[idx].pinned
            w = self._cv.winfo_width()
            self._cv.delete(f"r{idx}")
            if idx in self._row_bgs:
                del self._row_bgs[idx]
            self._draw_row(self._visible[idx], idx, w)
