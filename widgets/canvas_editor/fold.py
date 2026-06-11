"""Fold logic for CanvasCodeView — block folding + fold-aware coordinate mapping.

Extracted from canvas_codeview.py (P3 decomposition). `FoldMixin` is
inherited by `CanvasCodeView`.

Unlike the tokenizer, fold is NOT a clean leaf:
  * The three fold-marker regexes (`_SECTION_MARKER`, `_IDOL_BEGIN_RE`,
    `_IDOL_END_RE`) are shared vocabulary — render/minimap/coordinate code
    that stays in canvas_codeview.py imports them back from here.
  * The mixin operates on host-owned state: `self.lines`, `self.folded`
    (the set of folded physical line indices), and `self._fold_dot_rects`
    (render output, read by `_hit_fold_dots`). All three stay initialized
    in CanvasCodeView._init_state; the mixin never creates them.

The fold-skip loop in `_visual_to_physical` / `_visual_row_count` /
`_visual_row_of` is mirrored (not shared) by several inline copies that
remain in render/minimap/coords. Deduplicating those into one iterator is
a future refactor, deliberately out of scope for this behavior-preserving
move.
"""
from __future__ import annotations

import re


# A "# ── Name ─────" section marker — foldable like a block opener.
# Matches IDOL/widgets/linenums.py:_SECTION_MARKER.
_SECTION_MARKER = re.compile(r"^\s*# ─{2,}")
# IDOL designer codegen pair markers — fold the entire BEGIN…END block.
_IDOL_BEGIN_RE  = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:BEGIN")
_IDOL_END_RE    = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:END")


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
        cur_v = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(line):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            if cur_v == v_row:
                return i
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            cur_v += 1
        return len(self.lines) - 1

    def _visual_row_count(self) -> int:
        n = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(line):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            n += 1
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
        return n

    def _visual_row_of(self, line_idx: int) -> int:
        v = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(line):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            if i == line_idx:
                return v
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            v += 1
        return v

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
