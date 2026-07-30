"""IDOL's font chooser, replacing tkfontchooser."""
from __future__ import annotations

import inspect
import tkinter as tk

import pytest

from widgets.dark_checkbox import DarkCheckbox
from widgets.font_chooser import _STYLES, FontChooserDialog, _families, askfont

pytestmark = pytest.mark.gui


def _drive(tk_root, action, tries=80):
    """Run *action* on the modal once it exists — `askfont` blocks in
    `wait_window`, so there is no chance to grab a reference first."""
    state = {"n": 0}

    def run():
        for w in tk_root.winfo_children():
            if isinstance(w, FontChooserDialog):
                action(w)
                return
        state["n"] += 1
        if state["n"] < tries:
            tk_root.after(20, run)

    tk_root.after(20, run)


# ── Font discovery ────────────────────────────────────────────────────────────

def test_families_are_sorted_and_unique(tk_root):
    fams = _families()
    assert fams, "no font families found"
    assert len(fams) == len(set(fams))
    assert fams == sorted(fams, key=str.lower)


def test_families_drop_windows_vertical_variants(tk_root):
    """Windows lists '@Name' rotated CJK variants; they are noise in a picker."""
    assert not [f for f in _families() if f.startswith("@")]


# ── Opens on the current font (the requirement the old dialog failed) ─────────

def test_opens_on_the_given_font(tk_root):
    seen = {}
    target = _families()[3]

    def check(dlg):
        seen["family"] = dlg._family
        seen["size"] = dlg._size
        seen["weight"] = dlg._weight
        seen["slant"] = dlg._slant
        seen["entry"] = dlg._family_entry.get()
        seen["style_entry"] = dlg._style_entry.get()
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=target, size=18, weight="bold", slant="italic")
    assert seen["family"] == target
    assert seen["size"] == 18
    assert (seen["weight"], seen["slant"]) == ("bold", "italic")
    assert seen["entry"] == target
    assert seen["style_entry"] == "Bold Italic"


def test_selection_is_scrolled_into_view(tk_root):
    """Selecting without `see()` leaves the current font off-screen in a list
    of several hundred families."""
    target = _families()[-1]
    seen = {}

    def check(dlg):
        sel = dlg._family_list.curselection()
        seen["selected"] = dlg._family_list.get(sel[0]) if sel else None
        seen["visible"] = dlg._family_list.bbox(sel[0]) is not None if sel else False
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=target, size=10)
    assert seen["selected"] == target
    assert seen["visible"], "current family selected but scrolled out of view"


def test_unknown_family_falls_back_without_raising(tk_root):
    seen = {}

    def check(dlg):
        seen["family"] = dlg._family
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family="No Such Font 12345", size=10)
    assert seen["family"] in _families()


# ── Result shape ──────────────────────────────────────────────────────────────

def test_result_matches_the_tkfontchooser_keys(tk_root):
    """Both call sites read these keys; the swap must be import-only."""
    _drive(tk_root, lambda d: d._ok())
    result = askfont(tk_root, family=_families()[0], size=14, weight="bold")
    assert set(result) == {"family", "size", "weight", "slant",
                           "underline", "overstrike"}
    assert result["size"] == 14
    assert result["weight"] == "bold"


def test_cancel_returns_none(tk_root):
    _drive(tk_root, lambda d: d._cancel())
    assert askfont(tk_root, family=_families()[0]) is None


def test_askfont_requires_a_parent():
    with pytest.raises(ValueError):
        askfont(None)


def test_askfont_tolerates_stray_kwargs(tk_root):
    """The old signature was `**font_args`; a leftover keyword must not raise."""
    _drive(tk_root, lambda d: d._cancel())
    assert askfont(tk_root, family=_families()[0], text="Abcd",
                   some_old_kwarg=1) is None


# ── Effects ───────────────────────────────────────────────────────────────────

def test_effects_hidden_for_the_editor(tk_root):
    """Underline/strikeout are Designer widget concerns; the editor ignores
    them, so its caller must not show controls that do nothing."""
    seen = {}

    def check(dlg):
        seen["boxes"] = _count_checkboxes(dlg)
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0], show_effects=False)
    assert seen["boxes"] == 0


def test_effects_shown_by_default(tk_root):
    seen = {}

    def check(dlg):
        seen["boxes"] = _count_checkboxes(dlg)
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0])
    assert seen["boxes"] == 2


def test_effects_round_trip(tk_root):
    def check(dlg):
        dlg._underline_var.set(True)
        dlg._overstrike_var.set(True)
        dlg._ok()

    _drive(tk_root, check)
    result = askfont(tk_root, family=_families()[0], underline=False)
    assert result["underline"] is True
    assert result["overstrike"] is True


def _count_checkboxes(widget) -> int:
    n = 0
    for child in widget.winfo_children():
        if isinstance(child, DarkCheckbox):
            n += 1
        n += _count_checkboxes(child)
    return n


# ── Preview must not resize the dialog ────────────────────────────────────────

def test_huge_size_does_not_grow_the_dialog(tk_root):
    """A 72pt sample scrolls inside the fixed preview box; the window must not
    stretch to fit it."""
    seen = {}

    def check(dlg):
        dlg.update_idletasks()
        seen["small"] = (dlg.winfo_reqwidth(), dlg.winfo_reqheight())
        dlg._size = 72
        dlg._refresh_preview()
        dlg.update_idletasks()
        seen["large"] = (dlg.winfo_reqwidth(), dlg.winfo_reqheight())
        seen["scrollregion"] = dlg._preview.cget("scrollregion")
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0], size=9)
    assert seen["small"] == seen["large"], (
        f"dialog grew from {seen['small']} to {seen['large']} on a big font"
    )
    assert seen["scrollregion"], "preview has no scrollregion to scroll"


def test_preview_scrollregion_tracks_the_sample(tk_root):
    seen = {}

    def check(dlg):
        dlg._size = 8
        dlg._refresh_preview()
        seen["small"] = dlg._preview.bbox("all")
        dlg._size = 48
        dlg._refresh_preview()
        seen["large"] = dlg._preview.bbox("all")
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0])
    assert seen["large"][2] > seen["small"][2], "preview did not grow with size"


# ── Filtering ─────────────────────────────────────────────────────────────────

def test_family_filter_narrows_the_list(tk_root):
    seen = {}

    def check(dlg):
        full = dlg._family_list.size()
        dlg._family_entry.delete(0, "end")
        dlg._family_entry.insert(0, _families()[0][:3])
        dlg._on_family_typed()
        seen["full"], seen["filtered"] = full, dlg._family_list.size()
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0])
    assert 0 < seen["filtered"] <= seen["full"]


def test_filter_ignores_navigation_keys(tk_root):
    """Enter's KeyRelease arrives after the handler that acted on it; refiltering
    there would wipe the list out from under the selection."""
    seen = {}

    def check(dlg):
        dlg._family_entry.delete(0, "end")
        dlg._family_entry.insert(0, "zzzz-no-match")
        dlg._on_family_typed(type("E", (), {"keysym": "Return"})())
        seen["size"] = dlg._family_list.size()
        dlg._cancel()

    _drive(tk_root, check)
    askfont(tk_root, family=_families()[0])
    assert seen["size"] > 0, "a Return keyrelease emptied the family list"


# ── Style table ───────────────────────────────────────────────────────────────

def test_style_table_covers_every_weight_slant_pair():
    pairs = {(w, s) for _label, w, s in _STYLES}
    assert pairs == {("normal", "roman"), ("normal", "italic"),
                     ("bold", "roman"), ("bold", "italic")}


# ── Call sites ────────────────────────────────────────────────────────────────

def test_no_call_site_still_uses_tkfontchooser():
    import app as app_mod
    from widgets import designer_properties

    for fn in (app_mod.IDOL.view_change_font,
               designer_properties.DesignerProperties._open_font_picker):
        assert "tkfontchooser" not in inspect.getsource(fn), fn.__qualname__


def test_designer_splats_its_initial_font():
    """`askfont(..., font=init)` put the dict in **kwargs under "font", where
    nothing read it — the designer's picker never opened on the current font.

    Inspected over the AST: the comment explaining the old bug contains the
    literal `font=init`, so a substring search flags its own documentation.
    """
    import ast
    import textwrap

    from widgets import designer_properties

    tree = ast.parse(textwrap.dedent(inspect.getsource(
        designer_properties.DesignerProperties._open_font_picker)))
    calls = [n for n in ast.walk(tree)
             if isinstance(n, ast.Call)
             and getattr(n.func, "id", getattr(n.func, "attr", "")) == "askfont"]
    assert len(calls) == 1
    call = calls[0]
    assert any(kw.arg is None for kw in call.keywords), "initial font not splatted"
    assert not any(kw.arg == "font" for kw in call.keywords), \
        "passing font= puts the dict in **kwargs where nothing reads it"


def test_editor_passes_its_current_font():
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL.view_change_font)
    assert "family=family" in src and "size=" in src
    assert "show_effects=False" in src


# ── Shared checkbox ───────────────────────────────────────────────────────────

def test_dark_checkbox_toggles_and_reports(tk_root):
    calls = []
    cb = DarkCheckbox(tk_root, text="X", command=lambda: calls.append(1))
    cb.pack()
    tk_root.update()
    assert cb.get() is False
    cb._toggle()
    assert cb.get() is True and calls == [1]


def test_dark_checkbox_disabled_ignores_clicks(tk_root):
    calls = []
    cb = DarkCheckbox(tk_root, text="X", command=lambda: calls.append(1))
    cb.pack()
    tk_root.update()
    cb.set_enabled(False)
    cb._toggle()
    assert cb.get() is False and calls == []


def test_menu_editor_checkbox_still_accepts_state(tk_root):
    """The menu editor calls `configure(state="disabled")` on its checkboxes."""
    from designer.menu_editor import _DarkCheckbox

    cb = _DarkCheckbox(tk_root, text="Enabled", variable=tk.BooleanVar())
    cb.pack()
    tk_root.update()
    cb.configure(state="disabled")
    assert cb._enabled is False
    cb.configure(state="normal")
    assert cb._enabled is True
