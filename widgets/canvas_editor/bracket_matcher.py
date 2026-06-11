"""Bracket-match highlighting for CanvasCodeView.

Extracted from canvas_codeview.py (P3 decomposition). `BracketMatcherMixin`
is inherited by `CanvasCodeView`.

Pure logic: reads only `self.lines`, `self.cur_line`, `self.cur_col` and
the bracket constants from `.constants`. No canvas, no render attributes,
no host-method calls. Render calls `_find_bracket_pair()` once per paint
and outlines the returned pair.

NOTE: currently matches only `()[]{}` — quote match-highlighting is added
in a follow-up commit (same-line parity-based `_scan_quote`). The scanner
is string/comment-unaware by design, matching existing bracket fidelity.
"""
from __future__ import annotations

from .constants import (
    _ALL_BRACKETS,
    _BRACKET_CLOSE_TO_OPEN,
    _BRACKET_OPEN_TO_CLOSE,
)


class BracketMatcherMixin:
    """Cursor-adjacent bracket matching, mixed into CanvasCodeView.

    Reads host state `self.lines`, `self.cur_line`, `self.cur_col`."""

    def _find_bracket_pair(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """If the cursor is on (or immediately after) a bracket, return
        ((opener_line, opener_col), (closer_line, closer_col)) for the
        matching pair. Otherwise None."""
        # Look at char AT cursor first, then char immediately BEFORE cursor —
        # matches VS Code-style "cursor on either side of a bracket counts".
        for r, c in self._bracket_candidates():
            ch = self.lines[r][c]
            if ch in _BRACKET_OPEN_TO_CLOSE:
                m = self._scan_forward(r, c, ch, _BRACKET_OPEN_TO_CLOSE[ch])
                if m is not None:
                    return ((r, c), m)
            elif ch in _BRACKET_CLOSE_TO_OPEN:
                m = self._scan_backward(r, c, ch, _BRACKET_CLOSE_TO_OPEN[ch])
                if m is not None:
                    return (m, (r, c))
        return None

    def _bracket_candidates(self) -> list[tuple[int, int]]:
        out = []
        if not (0 <= self.cur_line < len(self.lines)):
            return out
        line = self.lines[self.cur_line]
        # Char AT cursor (if any)
        if 0 <= self.cur_col < len(line) and line[self.cur_col] in _ALL_BRACKETS:
            out.append((self.cur_line, self.cur_col))
        # Char immediately before cursor (more common — cursor sits right
        # after a typed-or-clicked bracket). Guard against cur_col
        # dangling past the end after a destructive edit.
        if 0 < self.cur_col <= len(line) and line[self.cur_col - 1] in _ALL_BRACKETS:
            out.append((self.cur_line, self.cur_col - 1))
        return out

    def _scan_forward(self, r0, c0, opener, closer):
        depth = 0
        for r in range(r0, len(self.lines)):
            line = self.lines[r]
            start = c0 + 1 if r == r0 else 0
            for c in range(start, len(line)):
                ch = line[c]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    if depth == 0:
                        return (r, c)
                    depth -= 1
        return None

    def _scan_backward(self, r0, c0, closer, opener):
        depth = 0
        for r in range(r0, -1, -1):
            line = self.lines[r]
            end = c0 - 1 if r == r0 else len(line) - 1
            for c in range(end, -1, -1):
                ch = line[c]
                if ch == closer:
                    depth += 1
                elif ch == opener:
                    if depth == 0:
                        return (r, c)
                    depth -= 1
        return None
