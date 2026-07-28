"""Undo behaviour of `CanvasCodeView`'s public mutation API.

Regression cover for Find/Replace being invisible to undo: the public methods
mutated the buffer without ever snapshotting it, so Ctrl+Z after a replace
skipped back past it to whatever the user last typed.
"""
from __future__ import annotations

import pytest

from widgets.canvas_codeview import CanvasCodeView

pytestmark = pytest.mark.gui

BASE = "foo bar\nfoo baz\nfoo qux"


@pytest.fixture
def cv(tk_root):
    view = CanvasCodeView(tk_root)
    view.pack(fill="both", expand=True)
    # `language` is set by set_filepath and read during render — without this
    # the first paint raises AttributeError.
    view.set_filepath("scratch.py")
    tk_root.update()
    view.set_text(BASE)
    return view


def test_replace_range_is_one_undo_step(cv):
    cv.replace_range((0, 0), (0, 3), "XXX")
    assert cv.get_text() == "XXX bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == BASE


def test_pure_insertion_via_empty_range_is_undoable(cv):
    """`delete_range` returns early on an empty range, so `replace_range` has to
    take the snapshot itself or a pure insertion goes unrecorded."""
    cv.replace_range((0, 0), (0, 0), "ZZ")
    assert cv.get_text() == "ZZfoo bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == BASE


def test_pure_deletion_is_undoable(cv):
    cv.replace_range((0, 0), (0, 4), "")
    assert cv.get_text() == "bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == BASE


def test_undo_group_collapses_a_sweep(cv):
    """Replace All must undo as one action, not one match at a time."""
    cv.begin_undo_group()
    try:
        for ln in (2, 1, 0):
            cv.replace_range((ln, 0), (ln, 3), "QUX")
    finally:
        cv.end_undo_group()
    assert cv.get_text() == "QUX bar\nQUX baz\nQUX qux"
    cv._undo()
    assert cv.get_text() == BASE
    cv._redo()
    assert cv.get_text() == "QUX bar\nQUX baz\nQUX qux"


def test_undo_groups_nest_without_extra_snapshots(cv):
    before = len(cv._undo_stack)
    cv.begin_undo_group()
    cv.begin_undo_group()
    cv.insert("A")
    cv.end_undo_group()
    cv.insert("B")
    cv.end_undo_group()
    assert len(cv._undo_stack) - before == 1
    cv._undo()
    assert cv.get_text() == BASE


def test_consecutive_sweeps_are_separate_undo_steps(cv):
    """Typing in the Find box does not move the editor cursor, so `_undo_op`
    coalescing would have merged two Replace Alls into one. The explicit group
    must not."""
    for word in ("AAA", "BBB"):
        cv.begin_undo_group()
        try:
            cv.replace_range((0, 0), (0, 3), word)
        finally:
            cv.end_undo_group()
    assert cv.get_text() == "BBB bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == "AAA bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == BASE


def test_pure_deletion_fires_on_change(cv):
    """Replace All with an empty replacement never inserts, and the insert was
    the only thing firing the notification — so the tab stayed clean and the
    linter stale."""
    fired = []
    cv.on_change = lambda: fired.append(1)
    cv.replace_range((0, 0), (0, 4), "")
    assert fired


def test_insert_is_undoable(cv):
    """The clipboard-history paste path."""
    cv.set_cursor(0, 0)
    cv.insert("pasted\n")
    assert cv.get_text() == "pasted\n" + BASE
    cv._undo()
    assert cv.get_text() == BASE


def test_insert_over_selection_is_one_step(cv):
    cv.set_selection((0, 0), (0, 3))
    cv.insert("HI")
    assert cv.get_text() == "HI bar\nfoo baz\nfoo qux"
    cv._undo()
    assert cv.get_text() == BASE
