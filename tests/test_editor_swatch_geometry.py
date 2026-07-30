"""Column<->pixel mapping must account for the inline colour swatches.

The render loop inserts a colour-preview square before every hex literal and
uses an italic font for some token categories, so a raw `font.measure(line[:col])`
does not describe where the glyphs actually are. Every overlay that converts
columns to pixels — selection, multi-cursor selection, find highlights — and the
click handler that converts back have to use the same swatch-aware helper, or
they drift by the square's width at the first hex literal on the line.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from widgets.canvas_codeview import CanvasCodeView

pytestmark = pytest.mark.gui

WITH_SWATCH = 'BG = "#0d1117" + tail'
NO_SWATCH   = 'BG = "hello123" + tail'


@pytest.fixture
def cv(tk_root):
    view = CanvasCodeView(tk_root)
    view.pack(fill="both", expand=True)
    view.set_filepath("scratch.py")
    tk_root.update()
    return view


def test_measure_includes_the_swatch_width(cv, tk_root):
    """Past the literal, the swatch-aware measure must exceed the raw one by
    exactly the square plus its gap."""
    cv.set_text(WITH_SWATCH + "\n")
    tk_root.update()
    cv.render()
    col = len(WITH_SWATCH)
    raw = cv._font.measure(WITH_SWATCH[:col])
    aware = cv._measure_to_col(WITH_SWATCH, col)
    assert aware - raw == max(6, cv._line_h - 10) + 3


def test_measure_matches_raw_when_no_swatch(cv, tk_root):
    cv.set_text(NO_SWATCH + "\n")
    tk_root.update()
    cv.render()
    col = len(NO_SWATCH)
    assert cv._measure_to_col(NO_SWATCH, col) == cv._font.measure(NO_SWATCH[:col])


def test_measure_is_monotonic_across_the_swatch(cv, tk_root):
    """Stepping one column at a time must never move the caret backwards —
    that jitter is what made shift-selection look wrong at the swatch."""
    cv.set_text(WITH_SWATCH + "\n")
    tk_root.update()
    cv.render()
    xs = [cv._measure_to_col(WITH_SWATCH, c) for c in range(len(WITH_SWATCH) + 1)]
    assert xs == sorted(xs), "column->pixel went backwards"


def test_column_pixel_round_trip_across_the_swatch(cv, tk_root):
    """`_col_from_x` is the inverse of `_measure_to_col`.

    Clicking at the pixel a column reports must land back on that column, or a
    click to the right of a swatch selects the wrong character.
    """
    cv.set_text(WITH_SWATCH + "\n")
    tk_root.update()
    cv.render()
    bad = []
    for col in range(len(WITH_SWATCH) + 1):
        px = cv._measure_to_col(WITH_SWATCH, col) + cv._text_x - cv._scroll_x
        got = cv._col_from_x(0, px)
        if got != col:
            bad.append((col, got))
    assert not bad, f"round trip failed for {bad}"


def test_round_trip_without_a_swatch_still_works(cv, tk_root):
    """Guards the rewrite of `_col_from_x` against breaking the ordinary case."""
    cv.set_text(NO_SWATCH + "\n")
    tk_root.update()
    cv.render()
    bad = []
    for col in range(len(NO_SWATCH) + 1):
        px = cv._measure_to_col(NO_SWATCH, col) + cv._text_x - cv._scroll_x
        got = cv._col_from_x(0, px)
        if got != col:
            bad.append((col, got))
    assert not bad, f"round trip failed for {bad}"


def test_selection_rect_spans_the_swatch(cv, tk_root):
    """Selecting the literal must cover its swatch — the square belongs to the
    literal, so a selection including the opening quote includes the square."""
    cv.set_text(WITH_SWATCH + "\n")
    tk_root.update()
    cv.render()
    quote = WITH_SWATCH.index('"')
    before = cv._measure_to_col(WITH_SWATCH, quote)
    after = cv._measure_to_col(WITH_SWATCH, quote + 1)
    square = max(6, cv._line_h - 10) + 3
    assert after - before >= square, "selection does not cover the swatch"


def _selection_rects(cv):
    """The selection highlight rectangles actually on the canvas."""
    want = cv._palette["select_bg"]
    out = []
    for item in cv.canvas.find_all():
        if cv.canvas.type(item) != "rectangle":
            continue
        if str(cv.canvas.itemcget(item, "fill")).lower() == want.lower():
            out.append(cv.canvas.coords(item))
    return out


def test_drawn_selection_rect_reaches_past_the_swatch(cv, tk_root):
    """The reported bug, at the pixels.

    Selecting from the line start through the whole hex literal must paint a
    rectangle that ends where the literal actually ends on screen. With a raw
    font.measure it stopped short by the swatch's width, so the highlight
    visibly lagged the text once the selection crossed the square.
    """
    cv.set_text(WITH_SWATCH + "\n")
    tk_root.update()
    end_col = WITH_SWATCH.index('"', WITH_SWATCH.index('"') + 1) + 1
    cv.set_selection((0, 0), (0, end_col))
    cv.render()

    rects = _selection_rects(cv)
    assert rects, "no selection rectangle was drawn"
    x2 = max(r[2] for r in rects)
    expected = cv._text_x0 + cv._measure_to_col(WITH_SWATCH, end_col)
    assert abs(x2 - expected) < 1.5, (
        f"selection ends at {x2}, glyphs end at {expected} — "
        f"short by {expected - x2:.0f}px (the swatch)"
    )


def test_drawn_selection_is_exact_without_a_swatch(cv, tk_root):
    """The same assertion on a line with no literal, so the test above is
    measuring the swatch rather than a constant fudge."""
    cv.set_text(NO_SWATCH + "\n")
    tk_root.update()
    cv.set_selection((0, 0), (0, len(NO_SWATCH)))
    cv.render()

    x2 = max(r[2] for r in _selection_rects(cv))
    expected = cv._text_x0 + cv._font.measure(NO_SWATCH)
    assert abs(x2 - expected) < 1.5


# ── The drawing paths must all use the aware helper ───────────────────────────

def _uses_raw_measure(fn) -> bool:
    """True if the function measures a line slice with a bare font.measure."""
    import textwrap

    tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "measure"
                and node.args
                and isinstance(node.args[0], ast.Subscript)):
            return True                    # e.g. font.measure(line_text[:c1])
    return False


def test_overlays_do_not_use_a_raw_measure():
    from widgets.canvas_editor.multicursor import MultiCursorMixin

    for fn in (CanvasCodeView._draw_selection,
               CanvasCodeView._draw_find_matches_on_line,
               MultiCursorMixin._draw_mc_selections):
        assert not _uses_raw_measure(fn), (
            f"{fn.__qualname__} measures a line slice directly; it must go "
            f"through _measure_to_col or it drifts at every colour swatch"
        )
