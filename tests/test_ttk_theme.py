"""The ttk theme IDOL installs must not leave TEntry's selection colours empty.

This is the Linux file-dialog bug, made testable on every platform.

Tk's X11 `tk_getOpenFile` draws its file list with `::tk::IconList` (a canvas),
and `iconlist.tcl` colours the selection with:

    set cbg [ttk::style lookup TEntry -selectbackground focus]
    set cfg [ttk::style lookup TEntry -selectforeground focus]
    $canvas create rect $bbox -fill $cbg -outline $cbg
    $canvas itemconfigure $tTag -fill $cfg

An empty lookup means `-fill ""` — the highlight and the filename are drawn
invisible, so clicking a file made it vanish. `theme_create(parent="alt")`
returns "" for both even though `alt` itself defines them.

Windows and macOS use the native dialog and never run that Tcl, so the symptom
was Linux-only while the broken style was universal — which is exactly why this
test does not need Linux to be useful.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui

# The lookup iconlist.tcl performs, verbatim.
_STATE = ["focus"]


@pytest.fixture
def styled(tk_root):
    """A Style with IDOL's real notebook theme installed."""
    from tkinter import ttk

    from widgets.notebook import CustomNotebook

    # Idempotent: the class guards on __initialized, and theme_create raises if
    # the theme already exists. Instantiating a notebook is what triggers it in
    # the app, so do the same rather than reaching for the private classmethod.
    CustomNotebook(tk_root)
    tk_root.update()
    return ttk.Style()


@pytest.mark.parametrize("option", ["selectbackground", "selectforeground"])
def test_tentry_selection_colour_is_set(styled, option):
    value = styled.lookup("TEntry", option, _STATE)
    assert value, (
        f"TEntry {option} is empty under IDOL's theme. Tk's X11 file dialog "
        f"would draw its selection with -fill '' and the clicked file would "
        f"render invisible."
    )


@pytest.mark.parametrize("option", ["selectbackground", "selectforeground"])
def test_tcombobox_selection_colour_is_set(styled, option):
    assert styled.lookup("TCombobox", option, _STATE)


def test_selection_colours_actually_contrast(styled):
    """Equal fg and bg would hide the text just as effectively as empty ones."""
    bg = styled.lookup("TEntry", "selectbackground", _STATE)
    fg = styled.lookup("TEntry", "selectforeground", _STATE)
    assert bg.lower() != fg.lower()


def test_the_underlying_ttk_behaviour_still_holds(tk_root):
    """Guard the *reason* the fix exists.

    `alt` defines TEntry's selection colours; a theme derived from it does not
    inherit them into the state-qualified lookup. If a future ttk changes that,
    this fails and the explicit configure can be reconsidered.
    """
    from tkinter import ttk

    s = ttk.Style()
    previous = s.theme_use()
    try:
        assert s.lookup("TEntry", "selectbackground", _STATE, "alt")
        name = "idol_theme_probe"
        if name not in s.theme_names():
            s.theme_create(name, parent="alt", settings={})
        s.theme_use(name)
        assert s.lookup("TEntry", "selectbackground", _STATE) == "", (
            "ttk now inherits TEntry selection colours into a derived theme; "
            "the explicit configure in notebook.py may no longer be needed."
        )
    finally:
        # `theme_use` is global. Leaving the probe theme installed would follow
        # every later test in the session into a different widget appearance.
        s.theme_use(previous)
