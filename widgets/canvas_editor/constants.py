"""Shared editing constants for the canvas editor.

Neutral home for small constants used by more than one canvas_editor
module (and by canvas_codeview.py itself). Imports nothing internal, so
any canvas_editor module can import it without risking a circular import
against canvas_codeview.py (which imports the mixins at module load).

Contains the auto-pair table used by both primary editing (canvas_codeview.py)
and secondary-cursor editing (multicursor.py), as well as the bracket-matching
constants extracted from bracket_matcher.
"""
from __future__ import annotations

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
