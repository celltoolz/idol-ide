"""StickyScroll — pins enclosing class/def lines to the top of the editor."""
from __future__ import annotations

import re

import pygments
from tkinter import Frame, Label, Text


class StickyScroll(Frame):
    """Overlays the top of the full editor frame (gutter + code) with syntax-highlighted
    enclosing scope headers. Line numbers appear in the gutter column in the normal color.
    """

    _SCOPE_RE = re.compile(r"^(\s*)(class |def |async def )")

    def __init__(self, frame, codeview, line_numbers) -> None:
        super().__init__(frame, bd=0, highlightthickness=0)
        self._cv = codeview
        self._ln = line_numbers
        self._bg = "#282a36"
        self._fg = "#f8f8f2"
        self._sep_color = "#44475a"
        self._font: tuple = ("Fira Mono", 10)

        # Content row: gutter on the left, code on the right
        self._row = Frame(self, bd=0, highlightthickness=0)
        self._row.pack(fill="x", side="top")

        self._gutter = Frame(self._row, bd=0, highlightthickness=0)
        self._gutter.pack(side="left", fill="y")
        self._gutter.pack_propagate(False)  # hold the set width

        # pady=0 so each line is exactly font-height pixels, matching Labels below.
        self._display = Text(
            self._row,
            state="disabled",
            wrap="none",
            cursor="arrow",
            takefocus=False,
            bd=0,
            highlightthickness=0,
            padx=4,
            pady=0,
            height=1,
        )
        self._display.pack(side="left", fill="x", expand=True)

        self._sep = Frame(self, height=1)
        self._sep.pack(fill="x", side="top")

    # ── Public API ────────────────────────────────────────────────────────────

    def apply_colors(self, bg: str, fg: str, sep: str, font) -> None:
        """Update colors to match the active color scheme and sync token tags."""
        self._bg = bg
        self._fg = fg
        self._sep_color = sep
        self._font = font
        self.config(bg=bg)
        self._row.config(bg=bg)
        self._gutter.config(bg=bg)
        self._display.config(bg=bg, fg=fg, font=font, insertbackground=bg)
        self._sep.config(bg=sep)
        self._sync_tags()

    def refresh(self) -> None:
        """Recompute and redraw the sticky header based on the current scroll position."""
        scope_lines = self._find_scope_lines()

        # Clear previous content
        self._display.config(state="normal")
        self._display.delete("1.0", "end")
        for w in self._gutter.winfo_children():
            w.destroy()

        if not scope_lines:
            self._display.config(state="disabled", height=0)
            self.place_forget()
            return

        # Match gutter width to the live line-numbers widget
        gutter_w = self._ln.winfo_width()
        self._gutter.config(width=gutter_w)

        bp_w = getattr(self._ln, "BP_COL_WIDTH", 0)
        for i, (lineno, line_text) in enumerate(scope_lines):
            # pady=0 makes each Label exactly font-height pixels, matching the
            # Text widget's line height (which also uses pady=0).
            # Use a row Frame so we can push the number past the BP dot column.
            row = Frame(self._gutter, bg=self._bg)
            row.pack(fill="x")
            if bp_w:
                Frame(row, bg=self._bg, width=bp_w).pack(side="left")
            Label(
                row,
                text=f" {lineno} ",
                bg=self._bg,
                fg=self._fg,
                font=self._font,
                anchor="w",
                padx=0,
                pady=0,
                bd=0,
                relief="flat",
            ).pack(side="left", fill="x", expand=True)

            # Syntax-highlighted code in the text area
            if i > 0:
                self._display.insert("end", "\n")
            self._display.insert("end", line_text)
            self._apply_highlight(i + 1, line_text)

        self._display.config(state="disabled", height=len(scope_lines))
        # Subtract scrollbar and minimap (if visible) so we don't overlap them
        vs_w = self._cv._vs.winfo_width()
        mm = self._cv._minimap
        mm_w = mm.winfo_width() if mm.winfo_ismapped() else 0
        self.place(x=0, y=0, relwidth=1, width=-(vs_w + mm_w))
        self.lift()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sync_tags(self) -> None:
        """Copy Token.* foreground colors from the codeview into our display widget."""
        for tag in self._cv.tag_names():
            if not tag.startswith("Token"):
                continue
            opts = self._cv.tag_configure(tag)
            fg_tuple = opts.get("foreground")
            if fg_tuple and fg_tuple[4]:
                self._display.tag_configure(tag, foreground=fg_tuple[4])

    def _apply_highlight(self, line_num: int, line_text: str) -> None:
        """Apply pygments token tags to the already-inserted line."""
        col = 0
        for token, text in pygments.lex(line_text, self._cv._lexer):
            token_str = str(token)
            end_col = col + len(text)
            if token_str not in {"Token.Text.Whitespace", "Token.Text"}:
                self._display.tag_add(
                    token_str,
                    f"{line_num}.{col}",
                    f"{line_num}.{end_col}",
                )
            col = end_col

    def _find_scope_lines(self) -> list[tuple[int, str]]:
        """Walk backward from the top visible line collecting enclosing scope headers.

        Returns (line_number, text) pairs, outermost first. Only lines that have
        scrolled above the viewport are included, so the header vanishes the moment
        its line scrolls back into view.
        """
        sticky_h = self.winfo_height() if self.winfo_ismapped() else 0
        top_line = int(self._cv.index(f"@0,{sticky_h}").split(".")[0])
        if top_line <= 1:
            return []

        results: list[tuple[int, str]] = []
        min_indent: float = float("inf")

        for lineno in range(top_line - 1, 0, -1):
            raw = self._cv.get(f"{lineno}.0", f"{lineno}.end")
            m = self._SCOPE_RE.match(raw)
            if not m:
                continue
            indent = len(m.group(1))
            if indent < min_indent:
                results.append((lineno, raw.rstrip()))
                min_indent = indent
                if indent == 0:
                    break  # reached outermost scope

        return list(reversed(results))
