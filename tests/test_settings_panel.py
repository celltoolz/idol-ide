"""The Settings tab — rendered entirely from the schema."""
from __future__ import annotations

import inspect

import pytest

from utils import settings
from widgets.dark_checkbox import DarkCheckbox
from widgets.settings_panel import SettingsPanel

pytestmark = pytest.mark.gui


@pytest.fixture
def store(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "SETTINGS_FILE", tmp_path / "settings.json")
    settings.reload()
    yield
    settings.reload()


@pytest.fixture
def panel(tk_root, store):
    p = SettingsPanel(tk_root)
    p.pack(fill="both", expand=True)
    tk_root.update()
    return p


def _labels(widget) -> list[str]:
    """Every visible label string in the content pane."""
    import tkinter as tk

    out = []
    for child in widget.winfo_children():
        if isinstance(child, tk.Label):
            try:
                text = child.cget("text")
            except Exception:
                text = ""
            if text:
                out.append(str(text))
        out.extend(_labels(child))
    return out


# ── Rendering from the schema ─────────────────────────────────────────────────

def test_a_nav_entry_per_section(panel):
    assert set(panel._nav_labels) == set(settings.sections())


def test_first_section_is_selected_on_open(panel):
    assert panel._active == settings.sections()[0]


def test_rows_come_from_the_schema(panel, tk_root):
    """Nothing is hardcoded — the panel renders whatever the schema declares."""
    for section in settings.sections():
        panel._select(section)
        tk_root.update()
        shown = _labels(panel._inner)
        for s in settings.settings_in(section):
            assert s.label in shown, f"{s.key} missing from {section}"


def test_switching_section_swaps_the_rows(panel, tk_root):
    first, second = settings.sections()[0], settings.sections()[1]
    panel._select(first)
    tk_root.update()
    before = _labels(panel._inner)
    panel._select(second)
    tk_root.update()
    assert _labels(panel._inner) != before


def test_bool_settings_render_a_dark_checkbox(panel, tk_root):
    """Not a tk.Checkbutton — it takes platform colours and reads wrong on a
    dark panel."""
    target = next((s for s in settings.schema() if s.kind == "bool"), None)
    if target is None:
        pytest.skip("no bool settings declared yet")
    panel._select(target.section)
    tk_root.update()
    assert _count(panel._inner, DarkCheckbox) >= 1


# ── Search ────────────────────────────────────────────────────────────────────

def test_search_spans_every_section(panel, tk_root):
    """A setting must be findable without knowing its category."""
    other = next(s for s in settings.schema()
                 if s.section != settings.sections()[0])
    panel._select(settings.sections()[0])
    panel._query.set(other.label)
    tk_root.update()
    assert other.label in _labels(panel._inner)


def test_search_matches_the_dotted_key(panel, tk_root):
    """Someone reading a config file or commit message has the key, not the
    label."""
    target = settings.schema()[0]
    panel._query.set(target.key)
    tk_root.update()
    assert target.label in _labels(panel._inner)


def test_search_groups_hits_under_section_headings(panel, tk_root):
    panel._query.set("e")           # broad enough to hit several sections
    tk_root.update()
    shown = _labels(panel._inner)
    assert any(sec.upper() in shown for sec in settings.sections())


def test_no_match_says_so(panel, tk_root):
    panel._query.set("zzzz-nothing-matches")
    tk_root.update()
    assert any("No settings match" in t for t in _labels(panel._inner))


def test_clearing_search_returns_to_the_category(panel, tk_root):
    panel._query.set("zzzz-nothing-matches")
    tk_root.update()
    panel._query.set("")
    tk_root.update()
    for s in settings.settings_in(panel._active):
        assert s.label in _labels(panel._inner)


# ── Writes ────────────────────────────────────────────────────────────────────

def test_writing_persists_and_notifies(panel, tk_root):
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append((k, v)))
    try:
        panel._write("editor.minimap_visible", False)
        tk_root.update()
        assert settings.get("editor.minimap_visible") is False
        assert ("editor.minimap_visible", False) in seen
    finally:
        unsub()


def test_writing_does_not_rebuild_the_rows(panel, tk_root):
    """The flicker. Changing one value used to re-render the whole pane —
    destroying and recreating every row, which was visible as every other row
    blinking, and worse while searching (all sections are rendered then)."""
    panel._select("Editor")
    tk_root.update()
    before = list(panel._inner.winfo_children())
    assert before, "nothing rendered to compare"

    panel._write("editor.minimap_visible", False)
    tk_root.update_idletasks()
    tk_root.update()

    assert [str(w) for w in panel._inner.winfo_children()] == \
        [str(w) for w in before], "rows were rebuilt"
    assert all(w.winfo_exists() for w in before), "rows were destroyed"


def test_writing_while_searching_does_not_rebuild(panel, tk_root):
    """The more pronounced case — search renders every section's hits."""
    panel._query.set("a")
    tk_root.update()
    before = list(panel._inner.winfo_children())
    panel._write("editor.minimap_visible", False)
    tk_root.update_idletasks()
    tk_root.update()
    assert all(w.winfo_exists() for w in before)
    assert [str(w) for w in panel._inner.winfo_children()] == \
        [str(w) for w in before]


def test_reset_updates_the_control_not_only_the_store(panel, tk_root):
    """Reset moves the value behind the widget's back, so the control has to
    be re-read — otherwise the checkbox keeps showing the old state."""
    panel._select("Editor")
    tk_root.update()
    box = _first(panel._inner, DarkCheckbox)
    assert box is not None
    box._toggle()                       # drive the real control, as a user would
    tk_root.update()
    assert box.get() is False
    assert settings.get("editor.minimap_visible") is False

    panel._reset("editor.minimap_visible")
    tk_root.update()
    assert settings.is_default("editor.minimap_visible")
    assert box.get() is True, "control still shows the pre-reset value"


def test_panel_follows_a_change_made_elsewhere(panel, tk_root):
    """The View menu writes the same keys. An open panel showing a stale value
    would be worse than no panel."""
    panel._select("Editor")
    tk_root.update()
    box = _first(panel._inner, DarkCheckbox)
    assert box.get() is True

    settings.set("editor.minimap_visible", False)   # as the View menu would
    tk_root.update()
    assert box.get() is False
    assert "↺" in _labels(panel._inner)


def test_unsubscribes_when_destroyed(tk_root, store):
    """A destroyed panel left subscribed would fire callbacks at dead widgets."""
    p = SettingsPanel(tk_root)
    p.pack()
    tk_root.update()
    p.destroy()
    tk_root.update()
    settings.set("editor.minimap_visible", False)    # must not raise


def test_clicking_the_blank_reset_placeholder_does_nothing(panel, tk_root):
    """The label is always present at a fixed width so nothing shifts when it
    appears — clicking it while blank must not be a reset."""
    panel._select("Appearance")
    tk_root.update()
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append(k))
    try:
        panel._reset("appearance.theme")     # already default
        assert seen == []
    finally:
        unsub()


def test_reset_returns_to_the_default(panel, tk_root):
    settings.set("appearance.theme", "nord")
    panel._reset("appearance.theme")
    tk_root.update()
    assert settings.is_default("appearance.theme")


def test_reset_affordance_only_shows_for_changed_settings(panel, tk_root):
    panel._select("Appearance")
    tk_root.update()
    assert "↺" not in _labels(panel._inner)
    settings.set("appearance.theme", "nord")
    panel._render()
    tk_root.update()
    assert "↺" in _labels(panel._inner)


def test_numeric_entry_clamps_to_the_declared_range(panel):
    """Ranges live in the schema; the panel must honour them rather than each
    consumer re-validating."""
    src = inspect.getsource(SettingsPanel._entry_control)
    assert "minimum" in src and "maximum" in src


# ── App wiring ────────────────────────────────────────────────────────────────

def test_app_subscribes_for_live_apply():
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL.__init__)
    assert "subscribe(self._on_setting_changed)" in src


def test_live_apply_dispatches_per_key():
    """Re-applying everything on every change would re-theme every open tab
    because someone edited a URL."""
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL._on_setting_changed)
    for key in ("appearance.theme", "editor.font", "editor.minimap_visible",
                "ai.ollama_url"):
        assert key in src, f"{key} not handled on change"


def test_settings_reachable_from_menu_keybinding_and_welcome():
    import app as app_mod
    from menus import menubar

    assert "Control-comma" in inspect.getsource(app_mod.IDOL._bind_shortcuts)
    assert "app.view_settings" in inspect.getsource(menubar.build_menubar)
    assert "on_settings=" in inspect.getsource(app_mod.IDOL.view_welcome)


def test_settings_tab_toggles_like_the_package_manager():
    """Second invocation closes it, matching the tab it is modelled on."""
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL.view_settings)
    assert "forget" in src and "_settings_tab = None" in src


def _first(widget, cls):
    if isinstance(widget, cls):
        return widget
    for child in widget.winfo_children():
        found = _first(child, cls)
        if found is not None:
            return found
    return None


def _count(widget, cls) -> int:
    n = 1 if isinstance(widget, cls) else 0
    for child in widget.winfo_children():
        n += _count(child, cls)
    return n
