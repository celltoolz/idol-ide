"""The View menu after Settings took over the preference items.

The split is by *shape*, not by category: a preference you set once and forget
belongs in the panel, which can show its current value and offer reset. A
toggle you flip constantly stays in the menu — but bound to the same stored
value, so the two are one setting with two surfaces rather than two settings.
"""
from __future__ import annotations

import ast
import inspect
import textwrap

from menus import menubar
from utils import settings

_MENU_SRC = inspect.getsource(menubar.build_menubar)


def _menu_labels() -> set[str]:
    """Every `label=` string actually passed to a menu call.

    Parsed, not grepped: the comments in menubar.py name the items that moved
    out, so a substring search over the source finds its own documentation.
    """
    tree = ast.parse(textwrap.dedent(_MENU_SRC))
    return {
        kw.value.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for kw in node.keywords
        if kw.arg == "label" and isinstance(kw.value, ast.Constant)
        and isinstance(kw.value.value, str)
    }


LABELS = _menu_labels()


# ── Moved into Settings ───────────────────────────────────────────────────────

def test_change_font_left_the_view_menu():
    assert not [x for x in LABELS if "Change Font" in x]


def test_active_line_items_left_the_view_menu():
    assert not [x for x in LABELS if "Highlight Active Line" in x]
    assert not [x for x in LABELS if "Active Line Color" in x]


def test_show_minimap_left_the_view_menu():
    assert not [x for x in LABELS if "Show Minimap" in x]


def test_everything_removed_has_a_home_in_the_schema():
    """Removing a menu item without a replacement would just delete a feature."""
    for key in ("editor.font", "editor.highlight_active_line",
                "editor.active_line_color", "editor.minimap_visible"):
        assert settings.get_setting(key) is not None, key


# ── Kept in the View menu ─────────────────────────────────────────────────────

def test_frequent_toggles_stay_in_the_menu():
    for label in ("Show Sidebar", "Show Panels", "Zen Mode"):
        assert label in LABELS, f"{label} should stay a menu toggle"


def test_theme_stays_as_a_submenu():
    """A preference, but switching it is frequent and a submenu beats a
    dropdown in a panel. Both write the same key."""
    assert "Theme" in LABELS
    assert settings.get_setting("appearance.theme") is not None


def test_actions_are_untouched():
    """These were never settings — they do something."""
    for label in ("Split Editor", "Source Control", "Clipboard History"):
        assert label in LABELS


def test_settings_entry_exists():
    assert "Settings" in LABELS
    assert "app.view_settings" in _MENU_SRC


# ── One value, two surfaces ───────────────────────────────────────────────────

def test_kept_toggles_write_through_to_the_store():
    """Otherwise the menu and the panel would drift into two settings."""
    import app as app_mod

    for fn, key in (
        (app_mod.IDOL.view_toggle_sidebar, "appearance.show_sidebar"),
        (app_mod.IDOL.view_toggle_output, "appearance.show_panels"),
        (app_mod.IDOL.view_change_theme, "appearance.theme"),
    ):
        assert key in inspect.getsource(fn), f"{fn.__name__} does not persist"


def test_ctrl_l_still_opens_the_font_chooser():
    """Change Font left the menu; the shortcut keeps working for people who
    already use it."""
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL._bind_shortcuts)
    assert "Control-l" in src and "view_change_font" in src


# ── Welcome tab ───────────────────────────────────────────────────────────────

def test_welcome_startup_checkbox_writes_the_setting():
    from widgets import welcome

    src = inspect.getsource(welcome.WelcomePanel._on_startup_toggle)
    assert "general.show_welcome_on_startup" in src


def test_welcome_uses_the_canvas_checkbox():
    """tk.Checkbutton takes platform colours and renders light on a dark
    panel — IDOL draws its own everywhere else.

    Checked over the AST: the comment explaining the swap names the class it
    replaced, so a substring search flags its own rationale.
    """
    from widgets import welcome

    tree = ast.parse(textwrap.dedent(inspect.getsource(welcome.WelcomePanel)))
    constructed = {
        node.func.attr if isinstance(node.func, ast.Attribute) else
        getattr(node.func, "id", "")
        for node in ast.walk(tree) if isinstance(node, ast.Call)
    }
    assert "Checkbutton" not in constructed
    assert "DarkCheckbox" in constructed


def test_show_welcome_is_a_declared_preference():
    s = settings.get_setting("general.show_welcome_on_startup")
    assert s is not None and s.section == "General"
