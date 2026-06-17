"""Fold logic for CanvasCodeView — block folding + fold-aware coordinate mapping.

Extracted from canvas_codeview.py (P3 decomposition). `FoldMixin` is
inherited by `CanvasCodeView`.

The mixin operates on host-owned state: `self.lines`, `self.folded` (the set
of folded physical line indices), and `self._fold_dot_rects` (render output,
read by `_hit_fold_dots`). All three stay initialized in
CanvasCodeView._init_state; the mixin never creates them.

The fold-skip walk shared by `_visual_to_physical` / `_visual_row_count` /
`_visual_row_of` lives in `constants.iter_visible`; those three are thin
adapters over it. The fold-marker regexes moved to constants.py too (so
iter_visible can reach them from the leaf), and minimap.py / canvas_codeview.py
now import them from there.
"""
from __future__ import annotations

from .constants import (
    _IDOL_BEGIN_RE,
    _IDOL_END_RE,
    _SECTION_MARKER,
    iter_visible,
)


class FoldMixin:
    """Block folding + fold-aware visual↔physical row mapping.

    Operates on host state owned by CanvasCodeView: `self.lines`,
    `self.folded` (set[int] of folded line indices), and
    `self._fold_dot_rects` (populated by render, read by _hit_fold_dots)."""

    def _line_is_foldable(self, i: int) -> bool:
        """A line opens a foldable block when it is a `# ── …` section
        marker OR ends with a block-opening token (`:`, `(`, `[`, `{`)
        AND has at least one more-indented line directly below.
        Mirrors IDOL/widgets/linenums.py:_get_fold_range first-line
        check — without it we mis-marked any line followed by an
        indented continuation as foldable (chained method calls,
        multi-line expressions, etc.)."""
        if not (0 <= i < len(self.lines)):
            return False
        line = self.lines[i]
        if _IDOL_END_RE.match(line):
            return False
        if _SECTION_MARKER.match(line):
            return True
        if not line.rstrip().endswith((":", "(", "[", "{")):
            return False
        if i + 1 >= len(self.lines):
            return False
        nl = self.lines[i + 1]
        if not nl.strip():
            return False
        ci = len(line) - len(line.lstrip())
        ni = len(nl) - len(nl.lstrip())
        return ni > ci

    def _visual_to_physical(self, v_row: int) -> int:
        """Physical line index of the `v_row`-th visible row."""
        for cur_v, (i, _line) in enumerate(iter_visible(self.lines, self.folded)):
            if cur_v == v_row:
                return i
        return len(self.lines) - 1

    def _visual_row_count(self) -> int:
        """Total number of rows currently visible (folds collapsed)."""
        return sum(1 for _ in iter_visible(self.lines, self.folded))

    def _visual_row_of(self, line_idx: int) -> int:
        """Visible row index of physical `line_idx`.

        If `line_idx` is hidden inside a fold (or out of range), returns the
        total visible-row count — matching the original loop's fall-through.
        """
        v = 0
        for i, _line in iter_visible(self.lines, self.folded):
            if i == line_idx:
                return v
            v += 1
        return v

    # ── Public fold API ──────────────────────────────────────────────────────

    def fold_all(self) -> None:
        """Fold every foldable block in the document, then repaint."""
        for i in range(len(self.lines)):
            if self._line_is_foldable(i):
                self.folded.add(i)
        self.render()

    def unfold_all(self) -> None:
        """Clear all folds, then repaint."""
        self.folded.clear()
        self.render()

    def _fold_end(self, start: int) -> int:
        """Return the physical index of the last hidden line in a fold at `start`.

        Mirrors the skip logic in _visual_to_physical so the two stay in sync.
        """
        line = self.lines[start]
        if _IDOL_BEGIN_RE.match(line):
            for i in range(start + 1, len(self.lines)):
                if _IDOL_END_RE.match(self.lines[i]):
                    return i
            return len(self.lines) - 1
        if _SECTION_MARKER.match(line):
            si = len(line) - len(line.lstrip())
            last = start
            for i in range(start + 1, len(self.lines)):
                ln = self.lines[i]
                if ln.strip():
                    ind = len(ln) - len(ln.lstrip())
                    if ind < si or (ind == si and _SECTION_MARKER.match(ln)):
                        return last
                last = i
            return last
        base_ind = len(line) - len(line.lstrip())
        last = start
        for i in range(start + 1, len(self.lines)):
            ln = self.lines[i]
            if ln.strip() and len(ln) - len(ln.lstrip()) <= base_ind:
                return last
            last = i
        return last

    def _shift_folds(self, after: int, delta: int = 1) -> None:
        """Shift fold indices strictly after `after` by `delta`.

        Call with delta=+1 after inserting a line at after+1, or delta=-1
        after deleting a line that was at after+1.  Indices equal to `after`
        are never moved (the line at `after` itself didn't shift).
        """
        if self.folded:
            self.folded = {f + delta if f > after else f for f in self.folded}

    def _hit_fold_dots(self, x: float, y: float) -> int | None:
        """Return the physical line index of the fold-dots indicator at
        the given canvas coords, or None."""
        for x1, y1, x2, y2, row in self._fold_dot_rects:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return row
        return None
