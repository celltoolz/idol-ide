"""GutterMixin — line-number / fold / breakpoint / git-stripe gutter.

Owns the drawing of the editor's left gutter column: the font-aware
layout math (`_compute_gutter`), the full-height background fill, and
the per-row content (git diff stripe, breakpoint dot, line number,
fold marker). The host's `render()` calls `_draw_gutter_background`
once before its row loop and `_draw_gutter_row` once per visible row;
the sticky-scroll band reuses `_draw_gutter_number` for its own
line-number slice.

Like every canvas_editor mixin, this operates on host-owned state
(`self._palette`, `self._line_h`, `self._git_hunk_map`,
`self._breakpoints`, `self.cur_line`, `self.folded`, …) and the
geometry attributes it sets itself (`_debug_w`, `_linenum_r`,
`_fold_x`, `_gutter_w`, `_text_x`). It calls the host's
`_line_is_foldable` (from FoldMixin). Imports only constants.py.
"""
from __future__ import annotations

from .constants import (
    _BREAKPOINT_COLOR,
    _BREAKPOINT_GHOST_COLOR,
    _GIT_HUNK_COLORS,
)


class GutterMixin:
    """Gutter layout + drawing. Mixed into CanvasCodeView."""

    def _compute_gutter(self) -> None:
        """Recompute font-aware gutter layout. Call after any font change."""
        cw = self._char_w
        self._debug_w   = 16
        # Right edge of line-number column: enough for 4 digits + small margin.
        self._linenum_r = self._debug_w + max(30, cw * 4)
        # Left edge of fold glyph: small gap after line numbers.
        self._fold_x    = self._linenum_r + max(4, cw // 2)
        # Right edge of gutter: fold glyph + one char width of clearance.
        self._gutter_w  = self._fold_x + max(14, cw + 4)
        # Where text begins: small gap after the gutter rectangle.
        self._text_x    = self._gutter_w + max(8, cw)

    def _draw_gutter_background(self, c, h: int) -> None:
        """Paint the full-height gutter background column. Called once per
        render, before the row loop."""
        c.create_rectangle(0, 0, self._gutter_w, h,
                           fill=self._palette["gutter_bg"], outline="")

    def _draw_gutter_number(self, canvas, y: int, lineno: int,
                            active: bool = False) -> None:
        """Draw a right-aligned 1-based line number in the gutter at row *y*.

        *lineno* is 0-indexed (displayed as `lineno + 1`). *active* uses the
        active-line color (cursor row); default is the plain gutter color.
        Shared by `_draw_gutter_row` (main canvas) and the sticky-scroll
        band, which draws onto its own `canvas`."""
        fg = (self._palette["gutter_fg_active"] if active
              else self._palette["gutter_fg"])
        canvas.create_text(self._linenum_r, y + self._line_h // 2,
                           text=str(lineno + 1), anchor="e",
                           fill=fg, font=self._font)

    def _draw_gutter_row(self, c, i: int, y: int) -> None:
        """Draw the gutter content for physical line *i* at row pixel-*y*.

        Paints OVER any token / indent guide that scrolled left of
        `_text_x` (the overlay mask), then redraws the gutter content
        (git stripe, breakpoint, line number, fold marker) on top.
        Without the mask, horizontally scrolled long lines bleed the
        start of each line into the line-number column."""
        c.create_rectangle(0, y, self._text_x, y + self._line_h,
                           fill=self._palette["gutter_bg"], outline="")
        git_kind = self._git_hunk_map.get(i)
        if git_kind:
            gcolor = _GIT_HUNK_COLORS.get(git_kind)
            if gcolor:
                c.create_rectangle(0, y, 3, y + self._line_h,
                                   fill=gcolor, outline="")
        if i in self._breakpoints or i == self._hover_breakpoint_line:
            cy_bp = y + self._line_h // 2
            cx_bp = self._debug_w // 2
            r_bp  = min(self._debug_w // 2 - 1, max(4, self._line_h // 3))
            fill_bp = (_BREAKPOINT_COLOR if i in self._breakpoints
                       else _BREAKPOINT_GHOST_COLOR)
            c.create_oval(cx_bp - r_bp, cy_bp - r_bp,
                          cx_bp + r_bp, cy_bp + r_bp,
                          fill=fill_bp, outline="")
        self._draw_gutter_number(c, y, i, active=(i == self.cur_line))
        if self._line_is_foldable(i):
            glyph = "▶" if i in self.folded else "▼"
            c.create_text(self._fold_x, y + self._line_h // 2, text=glyph,
                          anchor="w", fill=self._palette["gutter_fg"],
                          font=self._font)
