"""Bracket-match highlighting for CanvasCodeView.

Extracted from canvas_codeview.py (P3 decomposition). `BracketMatcherMixin`
is inherited by `CanvasCodeView`.

Pure logic: reads only `self.lines`, `self.cur_line`, `self.cur_col` and
the bracket constants from `.constants`. No canvas, no render attributes,
no host-method calls. Render calls `_find_bracket_pair()` once per paint
and outlines the returned pair.

Matches `()[]{}` via a directional depth scan and `'` / `"` via same-line
parity (`_match_quote`). The scanner is string/comment-unaware by design,
matching existing bracket fidelity (a delimiter inside a string or comment
still highlights).

Known limitation: triple-quoted delimiters (`'''` / `\"\"\"`) are paired as
adjacent same-line quotes by parity, not as triple-to-triple; quotes are
never matched across lines.
"""
from __future__ import annotations

from .constants import (
    _BRACKET_CLOSE_TO_OPEN,
    _BRACKET_OPEN_TO_CLOSE,
    _MATCH_CHARS,
    _QUOTES,
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
            elif ch in _QUOTES:
                pair = self._match_quote(r, c, ch)
                if pair is not None:
                    return pair
        return None

    def _bracket_candidates(self) -> list[tuple[int, int]]:
        out = []
        if not (0 <= self.cur_line < len(self.lines)):
            return out
        line = self.lines[self.cur_line]
        # Char AT cursor (if any)
        if 0 <= self.cur_col < len(line) and line[self.cur_col] in _MATCH_CHARS:
            out.append((self.cur_line, self.cur_col))
        # Char immediately before cursor (more common — cursor sits right
        # after a typed-or-clicked bracket). Guard against cur_col
        # dangling past the end after a destructive edit.
        if 0 < self.cur_col <= len(line) and line[self.cur_col - 1] in _MATCH_CHARS:
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

    def _quote_cols(self, line: str, q: str) -> list[int]:
        """Columns of every UNESCAPED `q` on `line`, left to right.
        Backslash-escaping handled the same way as the tokenizer
        (_comment_start / _scan_triple_state): skip the char after `\\`."""
        cols = []
        i, n = 0, len(line)
        while i < n:
            ch = line[i]
            if ch == "\\":
                i += 2          # skip escaped char
                continue
            if ch == q:
                cols.append(i)
            i += 1
        return cols

    def _match_quote(self, r: int, c: int, q: str):
        """Match a quote of type `q` at (r, c) to its same-line partner by
        parity. Even index in the unescaped-quote list ⇒ opener (partner is
        the next quote); odd ⇒ closer (partner is the previous). Returns
        ((openL, openC), (closeL, closeC)) or None when the quote is escaped
        or has no same-line partner."""
        cols = self._quote_cols(self.lines[r], q)
        if c not in cols:
            return None                       # the quote at c is escaped
        idx = cols.index(c)
        if idx % 2 == 0:                      # opener
            if idx + 1 < len(cols):
                return ((r, c), (r, cols[idx + 1]))
        else:                                 # closer
            return ((r, cols[idx - 1]), (r, c))
        return None
