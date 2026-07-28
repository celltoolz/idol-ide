"""Colour picker widget, and the editor's swatch hit-testing / literal rewrite."""
from __future__ import annotations

import pytest

from widgets.color_picker import (
    ColorPicker,
    ColorPickerPopup,
    hex_to_rgb,
    parse_hex,
    rgb_to_hex,
)

# ── Pure colour helpers ───────────────────────────────────────────────────────


@pytest.mark.parametrize("raw,expect", [
    ("#ff00aa", "#ff00aa"),
    ("#FF00AA", "#ff00aa"),
    ("ff00aa",  "#ff00aa"),
    ("#f0a",    "#ff00aa"),      # shorthand expands
    ("  #f0a ", "#ff00aa"),      # surrounding space tolerated
    ("#fff",    "#ffffff"),
])
def test_parse_hex_accepts(raw, expect):
    assert parse_hex(raw) == expect


@pytest.mark.parametrize("raw", ["", "#", "#gg0000", "#ff00a", "#ff00aaa",
                                 "red", None, "#ff 00 aa"])
def test_parse_hex_rejects(raw):
    assert parse_hex(raw) is None


def test_rgb_round_trip():
    assert hex_to_rgb("#3a7bd5") == (58, 123, 213)
    assert rgb_to_hex(58, 123, 213) == "#3a7bd5"


@pytest.mark.parametrize("r,g,b,expect", [
    (-20, 0, 0, "#000000"),      # clamps low
    (300, 0, 0, "#ff0000"),      # clamps high
    (255.7, 0, 0, "#ff0000"),    # tolerates floats from the HSV round trip
])
def test_rgb_to_hex_clamps(r, g, b, expect):
    assert rgb_to_hex(r, g, b) == expect


def test_hsv_round_trip_is_lossless():
    """Every colour must survive rgb -> hsv -> rgb exactly.

    `colorsys` hands back 31.999999999999996 for what went in as 32, so
    truncating instead of rounding shifted a channel by one — a colour would
    quietly drift every time the picker opened on it. Exercises the maths
    directly rather than through the widget: it is the maths that was wrong,
    and 4096 widget renders would cost 14s for the same coverage.
    """
    import colorsys

    drifted = []
    for r in range(0, 256, 17):          # 16 steps per channel = 4096 colours
        for g in range(0, 256, 17):
            for b in range(0, 256, 17):
                want = f"#{r:02x}{g:02x}{b:02x}"
                h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
                got = rgb_to_hex(*(c * 255 for c in colorsys.hsv_to_rgb(h, s, v)))
                if got != want:
                    drifted.append((want, got))
    assert not drifted, f"{len(drifted)} colours drifted, e.g. {drifted[:5]}"


# ── The widget ────────────────────────────────────────────────────────────────

pytestmark_gui = pytest.mark.gui


@pytest.fixture
def picker(tk_root):
    changes: list[str] = []
    p = ColorPicker(tk_root, color="#3a7bd5", on_change=changes.append)
    p.pack()
    tk_root.update()
    p.changes = changes          # type: ignore[attr-defined]
    return p


@pytest.mark.gui
def test_round_trips_the_initial_colour(picker):
    assert picker.get_color() == "#3a7bd5"


@pytest.mark.gui
def test_set_color_does_not_fire_on_change(picker):
    """Only user interaction should write to the document."""
    picker.set_color("#112233")
    assert picker.get_color() == "#112233"
    assert picker.changes == []


@pytest.mark.gui
def test_greyscale_keeps_the_current_hue(picker):
    """Dragging value to black must not snap the square back to red — a
    greyscale colour carries no hue, so the picker keeps the one on screen."""
    picker.set_color("#3a7bd5")
    hue_before = picker._h
    picker.set_color("#000000")
    assert picker._h == hue_before


@pytest.mark.gui
def test_hex_entry_applies_and_fires(picker):
    picker._entry_var.set("#10c020")
    picker._commit_entry()
    assert picker.get_color() == "#10c020"
    assert picker.changes == ["#10c020"]


@pytest.mark.gui
def test_hex_entry_rejects_garbage_without_firing(picker):
    before = picker.get_color()
    picker._entry_var.set("not a colour")
    picker._commit_entry()
    assert picker.get_color() == before
    assert picker.changes == []
    # The field snaps back rather than leaving invalid text sitting there.
    assert picker._entry_var.get().lower() == before


@pytest.mark.gui
def test_dragging_the_sv_square_fires_changes(picker):
    picker._drag_target = "sv"
    picker._apply(picker._sv_x0 + 5, picker._sv_y0 + 5)
    assert picker.changes, "dragging the square should report a colour"


@pytest.mark.gui
def test_drag_stays_in_the_zone_it_started_in(picker):
    """Dragging out of the square and across the hue strip must not start
    changing hue mid-stroke."""
    picker.set_color("#3a7bd5")
    hue_before = picker._h
    picker._drag_target = "sv"
    picker._apply(picker._hue_x0 + 2, picker._sv_y0 + 40)   # over the hue strip
    assert picker._h == hue_before


# ── Popup lifetime ────────────────────────────────────────────────────────────

@pytest.mark.gui
def test_popup_close_fires_on_close_once(tk_root):
    closed = []
    pop = ColorPickerPopup(tk_root, "#123456", on_close=lambda: closed.append(1))
    pop.close()
    pop.close()                  # idempotent
    assert closed == [1]


@pytest.mark.gui
def test_keep_alive_cancels_a_pending_close(tk_root):
    closed = []
    pop = ColorPickerPopup(tk_root, "#123456", on_close=lambda: closed.append(1))
    pop.schedule_close(50)
    pop.keep_alive()
    tk_root.after(120, tk_root.quit)
    tk_root.mainloop()
    assert closed == [], "keep_alive should have cancelled the close"
    pop.close()


@pytest.mark.gui
def test_scheduled_close_actually_fires(tk_root):
    closed = []
    pop = ColorPickerPopup(tk_root, "#123456", on_close=lambda: closed.append(1))
    pop.schedule_close(30)
    tk_root.after(150, tk_root.quit)
    tk_root.mainloop()
    assert closed == [1]


# ── Editor integration ────────────────────────────────────────────────────────

@pytest.fixture
def cv(tk_root):
    from widgets.canvas_codeview import CanvasCodeView
    view = CanvasCodeView(tk_root)
    view.pack(fill="both", expand=True)
    view.set_filepath("scratch.py")
    tk_root.update()
    return view


@pytest.mark.gui
def test_swatches_are_recorded_for_hex_literals(cv, tk_root):
    cv.set_text('BG = "#0d1117"\nFG = \'#fff\'\nNOPE = "hello"\n')
    tk_root.update()
    cv.render()
    colors = sorted(s[4] for s in cv._color_swatches)
    assert colors == ["#0d1117", "#ffffff"]


@pytest.mark.gui
def test_swatch_hit_test_returns_the_literal_span(cv, tk_root):
    cv.set_text('BG = "#0d1117"\n')
    tk_root.update()
    cv.render()
    x1, y1, x2, y2, *_ = cv._color_swatches[0]
    hit = cv.color_swatch_at((x1 + x2) / 2, (y1 + y2) / 2)
    assert hit is not None
    assert hit["color"] == "#0d1117"
    assert hit["line"] == 0
    literal = cv.lines[0][hit["col_start"]:hit["col_end"]]
    assert literal == '"#0d1117"'


@pytest.mark.gui
def test_swatch_hit_test_misses_elsewhere(cv, tk_root):
    cv.set_text('BG = "#0d1117"\n')
    tk_root.update()
    cv.render()
    assert cv.color_swatch_at(2000, 2000) is None


@pytest.mark.gui
@pytest.mark.parametrize("source,expect", [
    ('BG = "#0D1117"', 'BG = "#3A7BD5"'),      # uppercase preserved
    ("BG = '#0d1117'", "BG = '#3a7bd5'"),      # lowercase + single quotes kept
    ("BG = '#f0a'",    "BG = '#3a7bd5'"),      # shorthand expands
])
def test_replace_preserves_quote_style_and_case(cv, tk_root, source, expect):
    cv.set_text(source + "\n")
    tk_root.update()
    cv.render()
    hit = cv.color_swatch_at(*[(a + b) / 2 for a, b in
                               ((cv._color_swatches[0][0], cv._color_swatches[0][2]),
                                (cv._color_swatches[0][1], cv._color_swatches[0][3]))])
    cv.replace_color_literal(hit["line"], hit["col_start"], hit["col_end"], "#3a7bd5")
    assert cv.lines[0] == expect


@pytest.mark.gui
def test_replace_returns_the_shifted_span(cv, tk_root):
    """`#rgb` -> `#rrggbb` lengthens the literal; the caller needs the new
    bounds or the next drag step rewrites the wrong range."""
    cv.set_text("BG = '#f0a'\n")
    tk_root.update()
    cv.render()
    hit = cv.color_swatch_at(*_center(cv._color_swatches[0]))
    span = cv.replace_color_literal(hit["line"], hit["col_start"],
                                    hit["col_end"], "#3a7bd5")
    assert span is not None
    assert cv.lines[0][span[0]:span[1]] == "'#3a7bd5'"


@pytest.mark.gui
def test_replace_refuses_a_span_that_is_no_longer_a_colour(cv, tk_root):
    cv.set_text('BG = "#0d1117"\n')
    tk_root.update()
    cv.render()
    cv.set_text('BG = "hello world"\n')
    assert cv.replace_color_literal(0, 5, 14, "#3a7bd5") is None


@pytest.mark.gui
def test_replace_is_undoable_as_one_group(cv, tk_root):
    """Mirrors what app.py does: one group for the whole picking session."""
    cv.set_text('BG = "#0d1117"\n')
    tk_root.update()
    cv.render()
    hit = cv.color_swatch_at(*_center(cv._color_swatches[0]))
    cv.begin_undo_group()
    try:
        span = (hit["col_start"], hit["col_end"])
        for color in ("#111111", "#222222", "#333333"):
            span = cv.replace_color_literal(0, span[0], span[1], color)
    finally:
        cv.end_undo_group()
    assert cv.lines[0] == 'BG = "#333333"'
    cv._undo()
    assert cv.lines[0] == 'BG = "#0d1117"'


def _center(swatch):
    x1, y1, x2, y2, *_ = swatch
    return (x1 + x2) / 2, (y1 + y2) / 2


# ── Dismissal wiring ──────────────────────────────────────────────────────────
# An open picker is anchored to a swatch's screen position, so anything that
# moves the buffer under it leaves it pointing at the wrong line. Structural,
# because exercising the real paths needs a live IDOL.

import ast          # noqa: E402  — used only by the wiring checks below
import inspect      # noqa: E402


@pytest.fixture(scope="module")
def idol_src(repo_root):
    return (repo_root / "app.py").read_text(encoding="utf-8")


class _DismissHost:
    """Minimal stand-in exposing what the dismissal wiring touches."""

    _COLOR_DISMISS_TAG = None          # filled in from the real class below
    _bind_color_picker_dismiss = None
    _on_scroll_dismiss_color = None
    _on_leave_dismiss_color = None

    def __init__(self):
        self._color_dismiss_bound = False
        self._color_popup = None
        self.closed = 0
        self.scheduled = 0

    def _close_color_popup(self):
        self.closed += 1


def _make_host():
    import app as app_mod

    for name in ("_COLOR_DISMISS_TAG", "_bind_color_picker_dismiss",
                 "_on_scroll_dismiss_color", "_on_leave_dismiss_color"):
        setattr(_DismissHost, name, getattr(app_mod.IDOL, name))
    return _DismissHost()


@pytest.mark.gui
@pytest.mark.parametrize("sequence,kwargs", [
    ("<MouseWheel>", {"delta": 120}),      # Windows / macOS
    ("<Button-4>", {}),                    # X11 scroll up
    ("<Button-5>", {}),                    # X11 scroll down
])
def test_wheel_over_the_editor_closes_the_picker(cv, tk_root, sequence, kwargs):
    """The Windows bug, reproduced.

    The engine's own wheel handlers return "break", which in Tk stops every
    remaining binding for the event — including `add="+"` ones. As a plain
    widget binding this never fired on Windows. Linux only looked correct
    because X11 sends the wheel as a button event, whose grab emits crossing
    events, so the <Leave> handler was doing the work instead.
    """
    host = _make_host()
    host._bind_color_picker_dismiss(cv)
    cv.canvas.focus_set()
    tk_root.update()

    cv.canvas.event_generate(sequence, x=20, y=20, **kwargs)
    tk_root.update()
    assert host.closed == 1, f"{sequence} did not dismiss the picker"


@pytest.mark.gui
def test_dismissal_runs_ahead_of_the_engine_binding(cv, tk_root):
    """The tag must sit *before* the widget's own tag, or `break` wins."""
    host = _make_host()
    host._bind_color_picker_dismiss(cv)
    tags = cv.canvas.bindtags()
    assert tags[0] == host._COLOR_DISMISS_TAG
    assert str(cv.canvas) in tags        # widget's own tag still present


@pytest.mark.gui
def test_scrolling_still_scrolls(cv, tk_root):
    """Dismissal must not swallow the event — no handler returns "break"."""
    cv.set_text("\n".join(f"line {i}" for i in range(200)))
    tk_root.update()
    cv.render()
    host = _make_host()
    host._bind_color_picker_dismiss(cv)
    cv.canvas.focus_set()
    tk_root.update()

    before = cv.scroll_y
    cv.canvas.event_generate("<MouseWheel>", delta=-120, x=20, y=20)
    tk_root.update()
    assert cv.scroll_y != before, "the editor stopped scrolling"


@pytest.mark.gui
def test_binding_the_same_canvas_twice_does_not_stack_tags(cv):
    host = _make_host()
    host._bind_color_picker_dismiss(cv)
    host._bind_color_picker_dismiss(cv)
    assert cv.canvas.bindtags().count(host._COLOR_DISMISS_TAG) == 1


def test_leaving_the_canvas_only_schedules_the_close():
    """The pointer travelling to the popup leaves the canvas on the way — an
    immediate close there would kill the popup mid-journey."""
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL._on_leave_dismiss_color)
    assert "schedule_close" in src
    assert "_close_color_popup" not in src


def test_no_dismiss_handler_returns_break():
    """Returning "break" here would stop the engine scrolling at all.

    Checked over the AST, not the source text — the docstrings explaining the
    hazard contain the word, and a substring search would flag them.
    """
    import textwrap

    import app as app_mod

    for fn in (app_mod.IDOL._on_scroll_dismiss_color,
               app_mod.IDOL._on_leave_dismiss_color):
        tree = ast.parse(textwrap.dedent(inspect.getsource(fn)))
        returns = [n for n in ast.walk(tree) if isinstance(n, ast.Return)]
        assert not [r for r in returns
                    if isinstance(r.value, ast.Constant) and r.value.value == "break"], \
            f"{fn.__name__} returns 'break'"


def test_both_panes_wire_dismissal(idol_src):
    tree = ast.parse(idol_src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "IDOL")
    callers = {
        fn.name for fn in cls.body
        if isinstance(fn, ast.FunctionDef)
        and "_bind_color_picker_dismiss(" in (ast.get_source_segment(idol_src, fn) or "")
        and fn.name != "_bind_color_picker_dismiss"
    }
    # One per pane: the main notebook's tab builder and the split's.
    assert len(callers) >= 2, f"only wired in {callers}"


def test_tab_change_closes_the_picker(idol_src):
    import app as app_mod

    assert "_close_color_popup" in inspect.getsource(app_mod.IDOL._on_tab_changed)
