"""Bracket-match highlighting for CanvasCodeView.

Extracted from canvas_codeview.py (P3 decomposition). `BracketMatcherMixin`
is inherited by `CanvasCodeView`.

Reads `self.lines`, `self.cur_line`, `self.cur_col`, the bracket constants
from `.constants`, and the host's `_caret_contexts` (TokenizerMixin). No
canvas, no render attributes. Render calls `_find_bracket_pair()` once per
paint and outlines the returned pair.

Matches `()[]{}` via a directional depth scan and `'` / `"` via same-line
parity over the line's *string delimiters* (`_match_quote`).

**The character under the cursor must be code.** A `(` typed into a comment
or sitting in a string's body no longer highlights against a real bracket
elsewhere in the file — that was noise, and it is the half of "matching
doesn't feel right" that shows rather than types. Quotes are held to the
matching rule instead: a quote highlights only when it actually delimits a
string, which `_caret_contexts` reports as a context change across it. That
one test drops escaped quotes, the `'` in `"don't"`, anything in a comment,
and the two filler quotes of a `'''` run — so a triple-quoted delimiter now
pairs outer-to-outer rather than to its own neighbour.

Known limitations: the cross-line depth **scan** is still comment-unaware,
so a stray `(` inside a comment between the cursor's bracket and its partner
can still throw the depth off. Fixing that means classifying every line the
scan walks, which on an unmatched bracket is the whole file, on every paint
— deliberately left alone. Quotes are never matched across lines.
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
        candidates = self._bracket_candidates()
        if not candidates:
            return None
        # Every candidate is on cur_line, so one context scan covers them all.
        contexts = self._caret_contexts(self.cur_line)
        for r, c in candidates:
            ch = self.lines[r][c]
            if ch in _BRACKET_OPEN_TO_CLOSE:
                if contexts[c] != "code":
                    continue          # in a comment or a string's body
                m = self._scan_forward(r, c, ch, _BRACKET_OPEN_TO_CLOSE[ch])
                if m is not None:
                    return ((r, c), m)
            elif ch in _BRACKET_CLOSE_TO_OPEN:
                if contexts[c] != "code":
                    continue
                m = self._scan_backward(r, c, ch, _BRACKET_CLOSE_TO_OPEN[ch])
                if m is not None:
                    return (m, (r, c))
            elif ch in _QUOTES:
                pair = self._match_quote(r, c, ch, contexts)
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

    def _quote_cols(self, line: str, q: str, contexts: list[str]) -> list[int]:
        """Columns of every `q` on `line` that actually **delimits** a string.

        A quote delimits iff the caret context changes across it — "code" on
        its left and "string" on its right when opening, the reverse when
        closing. `contexts` is the host's `_caret_contexts(row)`, which has one
        more entry than the line has characters, so `contexts[i + 1]` is always
        in range.

        That single test replaces the old hand-rolled backslash skip and does
        strictly more: it also drops quotes inside another string's body (the
        `'` in `"don't"`), quotes anywhere in a comment, and the two filler
        quotes of a `'''` run — leaving a triple to pair outer-to-outer."""
        return [i for i, ch in enumerate(line)
                if ch == q and contexts[i] != contexts[i + 1]]

    def _match_quote(self, r: int, c: int, q: str, contexts: list[str]):
        """Match a string-delimiting quote of type `q` at (r, c) to its
        same-line partner by parity. Even index in the delimiter list ⇒ opener
        (partner is the next quote); odd ⇒ closer (partner is the previous).
        Returns ((openL, openC), (closeL, closeC)), or None when the quote at
        `c` does not delimit a string or has no same-line partner."""
        cols = self._quote_cols(self.lines[r], q, contexts)
        if c not in cols:
            return None            # escaped, in a comment, or in a string body
        idx = cols.index(c)
        if idx % 2 == 0:                      # opener
            if idx + 1 < len(cols):
                return ((r, c), (r, cols[idx + 1]))
        else:                                 # closer
            return ((r, cols[idx - 1]), (r, c))
        return None
