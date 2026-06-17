"""Shared editing constants for the canvas editor.

Neutral home for small constants used by more than one canvas_editor
module (and by canvas_codeview.py itself). Imports nothing internal, so
any canvas_editor module can import it without risking a circular import
against canvas_codeview.py (which imports the mixins at module load).

Contains the auto-pair table used by both primary editing (canvas_codeview.py)
and secondary-cursor editing (multicursor.py), the bracket-matching constants
extracted from bracket_matcher, and the fold-marker regexes + `iter_visible`
generator shared by every fold-aware caller (fold.py, minimap.py,
canvas_codeview.py).
"""
from __future__ import annotations

import re

# Characters that auto-pair when typed. Maps opener → closer.
_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
# All openers and closers — used for skip-over-closer detection.
_CLOSERS = set(_PAIRS.values())

# Bracket pairs for match-highlighting (no quotes — same char on both
# sides would defeat the depth-counting scan in bracket_matcher.py).
_BRACKET_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_BRACKET_CLOSE_TO_OPEN = {v: k for k, v in _BRACKET_OPEN_TO_CLOSE.items()}
_ALL_BRACKETS = set(_BRACKET_OPEN_TO_CLOSE) | set(_BRACKET_CLOSE_TO_OPEN)

# Quote chars (opener == closer) — match-highlighted by same-line parity
# in bracket_matcher.py, not by the directional depth scan.
_QUOTES = {q for q, cl in _PAIRS.items() if q == cl}
# Chars that trigger match-highlight candidate detection (brackets + quotes).
# Kept separate from _ALL_BRACKETS so that set stays semantically brackets-only.
_MATCH_CHARS = _ALL_BRACKETS | _QUOTES

# Editor font — family + size shared by the main canvas font, the minimap
# (canvas_editor/minimap.py), and assorted tooltip/preview widgets.
_FONT_FAMILY = "Consolas"
_FONT_SIZE   = 11

# Minimap column width (px). Shared: the minimap widget, the text-viewport
# width reservation, and the sticky-scroll band clip.
_MINIMAP_W = 90   # IDOL parity (canvas_editor/minimap.py:WIDTH)

# ── Gutter palette ────────────────────────────────────────────────────────────
# Breakpoint dot colors drawn in the gutter's debug zone.
_BREAKPOINT_COLOR       = "#f14c4c"   # bright red, matches IDOL linenums.py
_BREAKPOINT_GHOST_COLOR = "#6b2020"   # dim red — hover preview

# Git-diff gutter stripe palette — mirrors widgets/linenums.py's
# `_GUTTER_COLORS`. Kind names come from `editor/git_manager.py`'s
# hunk-classification: "added" (new lines), "modified" (edited lines),
# "deleted" (lines removed — shown as a marker on the survivor below).
_GIT_HUNK_COLORS = {
    "added":    "#4ec994",
    "modified": "#c5a028",
    "deleted":  "#f14c4c",
}

# ── Fold-marker regexes ─────────────────────────────────────────────────────
# Shared fold vocabulary. These previously lived in fold.py as a sanctioned
# exception to the constants-only import rule; they moved here so `iter_visible`
# (below) — and every fold-aware caller — can reach them from the leaf with no
# circular-import risk against canvas_codeview.py.
#
# A "# ── Name ─────" section marker — foldable like a block opener.
# Matches IDOL/widgets/linenums.py:_SECTION_MARKER.
_SECTION_MARKER = re.compile(r"^\s*# ─{2,}")
# IDOL designer codegen pair markers — fold the entire BEGIN…END block.
_IDOL_BEGIN_RE  = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:BEGIN")
_IDOL_END_RE    = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:END")


def iter_visible(lines, folded):
    """Yield ``(physical_index, line)`` for every line not hidden by a fold.

    The single source of truth for the fold-skip walk that maps the physical
    ``lines`` list onto the visible rows shown in the editor. A folded opener is
    itself visible (yielded); the lines it conceals are not. Callers that need a
    plain physical→visual mapping should use ``FoldMixin._visual_row_of`` (built
    on this); use ``iter_visible`` directly only when the per-line work differs.

    Three fold kinds set the skip state, mirroring how each is closed:
      * IDOL BEGIN…END markers   — hide through the matching END line.
      * ``# ── …`` section headers — hide until the next same-indent section
        header or a line at a lower indent.
      * ordinary block openers    — hide until the next line at an indent <= the
        opener's.

    This does NOT model the render loop's ``skip_close_char`` bracket inclusion
    (pulling a trailing ``)``/``]``/``}`` into the fold); that extra rule is
    render-only and stays in canvas_codeview.py's paint loop.
    """
    skip = None
    for i, line in enumerate(lines):
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
        yield i, line
        if i in folded:
            if _IDOL_BEGIN_RE.match(line):
                skip = -1
            elif _SECTION_MARKER.match(line):
                skip = -(len(line) - len(line.lstrip()) + 2)
            else:
                skip = len(line) - len(line.lstrip())
