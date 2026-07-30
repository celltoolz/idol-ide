"""Editor preferences — the toggles that used to vanish on restart.

Highlight Active Line, Active Line Colour, Show Sidebar and Show Panels were
persisted nowhere at all; tab size, autocomplete and smart pairs had no
preference to begin with. These pin both the engine flags and the wiring.
"""
from __future__ import annotations

import ast
import inspect

import pytest

from utils import settings
from widgets.canvas_codeview import CanvasCodeView

pytestmark = pytest.mark.gui


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.reload()
    yield
    settings.reload()


@pytest.fixture
def cv(tk_root):
    view = CanvasCodeView(tk_root)
    view.pack(fill="both", expand=True)
    view.set_filepath("scratch.py")
    tk_root.update()
    return view


# ── Smart pairs ───────────────────────────────────────────────────────────────

def test_pairs_auto_close_when_enabled(cv):
    cv.set_text("")
    cv.set_cursor(0, 0)
    cv._insert_char_with_pairs("(")
    assert cv.lines[0] == "()"
    assert cv.cur_col == 1, "cursor should sit between the pair"


def test_pairs_do_not_close_when_disabled(cv):
    cv.smart_pairs_enabled = False
    cv.set_text("")
    cv.set_cursor(0, 0)
    cv._insert_char_with_pairs("(")
    assert cv.lines[0] == "("


def test_disabled_pairs_do_not_swallow_a_typed_closer(cv):
    """Skip-over is the same feature from the other side. With pairing off
    there is no auto-inserted closer to skip, so eating the keystroke would be
    exactly the surprise the preference removes."""
    cv.smart_pairs_enabled = False
    cv.set_text(")")
    cv.set_cursor(0, 0)
    cv._insert_char_with_pairs(")")
    assert cv.lines[0] == "))"


def test_enabled_pairs_still_skip_over_a_closer(cv):
    cv.set_text("()")
    cv.set_cursor(0, 1)
    cv._insert_char_with_pairs(")")
    assert cv.lines[0] == "()"
    assert cv.cur_col == 2


def test_disabled_pairs_still_replace_a_selection(cv):
    cv.set_text("hello")
    cv.smart_pairs_enabled = False
    cv.set_selection((0, 0), (0, 5))
    cv._insert_char_with_pairs("x")
    assert cv.lines[0] == "x"


def test_disabled_pairs_remain_undoable(cv):
    cv.smart_pairs_enabled = False
    cv.set_text("ab")
    cv.set_cursor(0, 2)
    cv._insert_char_with_pairs("(")
    assert cv.lines[0] == "ab("
    cv._undo()
    assert cv.lines[0] == "ab"


# ── Autocomplete ──────────────────────────────────────────────────────────────

def test_autocomplete_gate_hides_an_open_popup(cv, monkeypatch):
    """The preference can be switched off while a popup is on screen, so the
    gate has to hide rather than just return."""
    hidden = []
    monkeypatch.setattr(cv, "_hide_autocomplete", lambda: hidden.append(1))
    cv.autocomplete_enabled = False
    cv._maybe_show_autocomplete()
    assert hidden == [1]


def test_autocomplete_runs_when_enabled(cv, monkeypatch):
    called = []
    monkeypatch.setattr(cv, "_current_prefix", lambda: called.append(1) or "")
    cv.autocomplete_enabled = True
    cv._maybe_show_autocomplete()
    assert called == [1]


# ── Engine defaults ───────────────────────────────────────────────────────────

def test_engine_defaults_are_on(cv):
    """A codeview built without a host still behaves as it always did."""
    assert cv.autocomplete_enabled is True
    assert cv.smart_pairs_enabled is True
    assert cv.tab_size == 4


# ── Schema ────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("key", [
    "editor.tab_size", "editor.highlight_active_line",
    "editor.active_line_color", "editor.autocomplete", "editor.smart_pairs",
    "appearance.show_sidebar", "appearance.show_panels",
])
def test_new_preferences_are_declared(key):
    assert settings.get_setting(key) is not None, f"{key} missing from schema"


def test_tab_size_declares_a_range():
    s = settings.get_setting("editor.tab_size")
    assert s.minimum is not None and s.maximum is not None
    assert s.minimum <= s.default <= s.maximum


def test_active_line_colour_defaults_to_following_the_theme(store):
    """Empty means "no override" — the theme's own colour wins."""
    assert settings.get("editor.active_line_color") == ""


# ── Wiring ────────────────────────────────────────────────────────────────────

def test_new_tabs_inherit_preferences():
    """Otherwise "Autocomplete: off" comes back on as soon as a file opens."""
    import app as app_mod

    src = inspect.getsource(app_mod)
    tree = ast.parse(src)
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "IDOL")
    for name in ("_new_tab", "_new_tab_in"):
        fn = next(f for f in cls.body
                  if isinstance(f, ast.FunctionDef) and f.name == name)
        seg = ast.get_source_segment(src, fn) or ""
        assert "_apply_editor_prefs" in seg, f"{name} does not apply prefs"


def test_apply_editor_prefs_covers_every_engine_flag():
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL._apply_editor_prefs)
    for flag in ("highlight_active_line", "_active_line_color",
                 "autocomplete_enabled", "smart_pairs_enabled", "tab_size"):
        assert flag in src, f"{flag} not applied"


@pytest.mark.parametrize("key", [
    "editor.active_line_color", "editor.highlight_active_line",
    "editor.autocomplete", "editor.smart_pairs", "editor.tab_size",
    "appearance.show_sidebar", "appearance.show_panels",
])
def test_live_apply_handles_every_new_key(key):
    import app as app_mod

    assert key in inspect.getsource(app_mod.IDOL._on_setting_changed)


def test_view_toggles_write_to_the_store():
    """The menu items and the panel must be two views of one value, not two
    values — phase 4 leans on this."""
    import app as app_mod

    for fn, key in (
        (app_mod.IDOL.view_toggle_highlight, "editor.highlight_active_line"),
        (app_mod.IDOL.view_active_line_color, "editor.active_line_color"),
        (app_mod.IDOL.view_toggle_output, "appearance.show_panels"),
        (app_mod.IDOL.view_toggle_sidebar, "appearance.show_sidebar"),
    ):
        assert key in inspect.getsource(fn), f"{fn.__name__} does not persist"


def test_store_driven_toggles_do_not_write_back():
    """Applying a preference must not immediately re-save it — that is the
    loop that turns one change into a write storm."""
    import app as app_mod

    for name in ("view_toggle_sidebar", "view_toggle_output",
                 "view_toggle_minimap", "view_change_theme"):
        sig = inspect.signature(getattr(app_mod.IDOL, name))
        assert "persist" in sig.parameters, f"{name} has no persist opt-out"


def test_panel_tab_is_workspace_state_not_a_preference():
    """Which bottom tab was open is "what was I doing here"; whether the panel
    shows at all is "how do I like my IDE"."""
    from utils import session as session_mod

    assert "panel_tab" in inspect.getsource(session_mod.save)
    # Restored in the deferred layout stage, alongside run_target and the
    # sashes — the panel has to exist before a tab can be selected in it.
    assert "panel_tab" in inspect.getsource(session_mod._apply_pane_sashes)
    assert settings.get_setting("appearance.panel_tab") is None


def test_zen_mode_is_deliberately_not_persisted():
    """Transient focus state, not a preference — restoring into it would open
    IDOL with everything hidden and no obvious way back."""
    assert settings.get_setting("view.zen_mode") is None
    assert settings.get_setting("appearance.zen_mode") is None
