"""Shared editing constants for the canvas editor.

Neutral home for small constants used by more than one canvas_editor
module (and by canvas_codeview.py itself). Imports nothing internal, so
any canvas_editor module can import it without risking a circular import
against canvas_codeview.py (which imports the mixins at module load).

Currently holds the auto-pair table used by both primary editing
(canvas_codeview.py) and secondary-cursor editing (multicursor.py). The
bracket-matching constants will join here when bracket_matcher is
extracted.
"""
from __future__ import annotations

# Characters that auto-pair when typed. Maps opener → closer.
_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
# All openers and closers — used for skip-over-closer detection.
_CLOSERS = set(_PAIRS.values())
