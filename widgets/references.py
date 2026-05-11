"""ReferencesPanel — shows all occurrences of a word in the current file."""
from __future__ import annotations

import re
from tkinter import Frame, Label, Text, ttk
from typing import Callable
from utils.ui_font import UI_FONT
from widgets.scrollbar import VerticalScrollbar


class ReferencesPanel(ttk.Frame):
    """Collapsible panel listing every occurrence of a symbol.

    Uses a tk.Text widget (not Treeview) so each row can have
    line:col in one color and the preview in another.
    """

    def __init__(self, parent, on_navigate: Callable[[int], None]) -> None:
        super().__init__(parent, style="Sidebar.TFrame")
        self._on_navigate = on_navigate
        self._bg      = "#1e1e1e"
        self._fg      = "#cccccc"
        self._sel     = "#094771"
        self._accent  = "#569cd6"   # line:col color — updates with theme
        self._preview_fg = "#cccccc"  # preview text color
        self._comment_fg = "#6a9955"  # count label color
        self._results: list[int] = []  # line numbers in order
        self._build_ui()

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, word: str, codeview) -> None:
        text    = codeview.get("1.0", "end-1c")
        pattern = re.compile(r"\b" + re.escape(word) + r"\b")
        results = []
        for lineno, line in enumerate(text.splitlines(), 1):
            for m in pattern.finditer(line):
                preview = line.strip()
                if len(preview) > 55:
                    preview = preview[:55] + "…"
                results.append((lineno, m.start(), preview))

        self._results = [r[0] for r in results]
        self._word_lbl.config(text=f'"{word}"')
        count = len(results)
        self._count_lbl.config(
            text=f"{count} reference{'s' if count != 1 else ''}"
        )

        self._list.config(state="normal")
        self._list.delete("1.0", "end")

        for i, (lineno, col, preview) in enumerate(results):
            if i > 0:
                self._list.insert("end", "\n")
            loc = f"  {lineno}:{col + 1}"
            self._list.insert("end", loc, "loc")
            self._list.insert("end", f"  {preview}", "preview")

        self._list.config(state="disabled")

    def apply_theme(self, bg: str, fg: str, select_bg: str,
                    accent: str = "", comment: str = "") -> None:
        self._bg  = bg
        self._fg  = fg
        self._sel = select_bg
        if accent:
            self._accent = accent
        if comment:
            self._comment_fg = comment

        self._header.config(bg=bg)
        self._word_lbl.config(bg=bg, fg=self._accent)
        self._count_lbl.config(bg=bg, fg=self._comment_fg)
        self._list.config(
            bg=bg,
            fg=fg,
            selectbackground=select_bg,
            selectforeground=fg,
            insertbackground=bg,
        )
        self._apply_tags()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _apply_tags(self) -> None:
        self._list.tag_configure("loc",     foreground=self._accent,     font=(UI_FONT, 9, "bold"))
        self._list.tag_configure("preview", foreground=self._preview_fg, font=(UI_FONT, 9))
        self._list.tag_configure("hover",   background=self._sel)

    def _build_ui(self) -> None:
        # ── Header ────────────────────────────────────────────────────────────
        self._header = Frame(self, bg=self._bg)
        self._header.pack(fill="x", side="top", pady=(2, 0))

        self._word_lbl = Label(
            self._header, text="References",
            bg=self._bg, fg=self._accent,
            font=(UI_FONT, 8, "bold"), anchor="w", padx=6,
        )
        self._word_lbl.pack(side="left", fill="x", expand=True)

        self._count_lbl = Label(
            self._header, text="",
            bg=self._bg, fg=self._comment_fg,
            font=(UI_FONT, 8), padx=6,
        )
        self._count_lbl.pack(side="right")

        # ── Text list ─────────────────────────────────────────────────────────
        frame = Frame(self, bg=self._bg)
        frame.pack(fill="both", expand=True)

        vs = VerticalScrollbar(frame)
        vs.pack(side="right", fill="y")

        self._list = Text(
            frame,
            state="disabled",
            wrap="none",
            cursor="arrow",
            takefocus=False,
            bd=0, highlightthickness=0,
            padx=0, pady=2,
            spacing1=2, spacing3=2,
        )
        self._list.pack(side="left", fill="both", expand=True)
        self._list.config(yscrollcommand=vs.set)
        vs.config(command=self._list.yview)

        self._apply_tags()

        self._list.bind("<ButtonRelease-1>", self._on_click)
        self._list.bind("<Motion>",          self._on_motion)
        self._list.bind("<Leave>",           self._on_leave)

    def _row_at(self, event) -> int | None:
        """Return the 0-based row index under the mouse, or None."""
        idx = self._list.index(f"@{event.x},{event.y}")
        row = int(idx.split(".")[0]) - 1
        if 0 <= row < len(self._results):
            return row
        return None

    def _on_click(self, event) -> None:
        row = self._row_at(event)
        if row is not None:
            self._on_navigate(self._results[row])

    def _on_motion(self, event) -> None:
        self._list.tag_remove("hover", "1.0", "end")
        row = self._row_at(event)
        if row is not None:
            self._list.tag_add("hover", f"{row + 1}.0", f"{row + 1}.end")

    def _on_leave(self, _) -> None:
        self._list.tag_remove("hover", "1.0", "end")
