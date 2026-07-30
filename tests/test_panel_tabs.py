"""Panel tabs — Welcome, Packages, Learning, Settings — and which pane they open in.

Designer mode pack_forgets the main notebook (the canvas takes its slot), so a
tab added there is invisible: clicking Package Manager, Welcome, Learning Mode
or Settings from the nav bar or the menus looked like nothing happened at all.
They now open into whichever pane is on screen, and can be dragged between the
two instead of being turned into a blank Untitled buffer.

Exercises the real methods against a stand-in host, so the logic under test is
the shipped code without booting the whole app.
"""
from __future__ import annotations

import pytest

import app as app_mod


class FakeNotebook:
    """Just enough ttk.Notebook for the panel-tab bookkeeping."""

    def __init__(self, name: str):
        self.name = name
        self._tabs: list[str] = []
        self._selected: str | None = None

    def tabs(self):
        return tuple(self._tabs)

    def add(self, tab_id: str, text: str = ""):
        self._tabs.append(tab_id)

    def select(self, tab_id: str | None = None):
        if tab_id is None:
            return self._selected
        self._selected = tab_id
        return None

    def forget(self, index: int):
        tab_id = self._tabs.pop(index)
        if self._selected == tab_id:
            self._selected = self._tabs[-1] if self._tabs else None


class FakePanel:
    def __init__(self):
        self.refreshed = 0

    def refresh(self):
        self.refreshed += 1


class Host:
    """Minimal stand-in exposing only what the methods under test touch."""

    _PANEL_TAB_SLOTS         = app_mod.IDOL._PANEL_TAB_SLOTS
    _panel_kind_of           = app_mod.IDOL._panel_kind_of
    _panel_tab_home          = app_mod.IDOL._panel_tab_home
    _pane_visible            = app_mod.IDOL._pane_visible
    _pane_name               = app_mod.IDOL._pane_name
    _designer_split_notebook = app_mod.IDOL._designer_split_notebook
    _panel_target_notebook   = app_mod.IDOL._panel_target_notebook
    _forget_panel_tab        = app_mod.IDOL._forget_panel_tab
    _build_panel_tab         = app_mod.IDOL._build_panel_tab
    _toggle_panel_tab        = app_mod.IDOL._toggle_panel_tab
    _move_panel_tab          = app_mod.IDOL._move_panel_tab
    _backfill_main_notebook  = app_mod.IDOL._backfill_main_notebook
    view_welcome             = app_mod.IDOL.view_welcome
    view_package_manager     = app_mod.IDOL.view_package_manager
    view_settings            = app_mod.IDOL.view_settings
    view_learning_mode       = app_mod.IDOL.view_learning_mode

    def __init__(self, designer: bool = False, split: bool = False):
        self.notebook = FakeNotebook("main")
        self._notebook_r = FakeNotebook("split") if split else None
        self._split_active = split
        self._split_shown = split
        self._designer_mode = designer
        self._active_pane = "left"
        self._serial = 0
        self.learn_cursors = False
        self.editor_tabs = 0
        for tab_attr, panel_attr in self._PANEL_TAB_SLOTS.values():
            setattr(self, tab_attr, None)
            setattr(self, panel_attr, None)

    # ── collaborators the panel-tab code calls out to ────────────────────────

    def _ensure_split_shown(self):
        if self._notebook_r is None:
            self._notebook_r = FakeNotebook("split")
        self._split_active = True
        self._split_shown = True

    def _set_active_pane(self, pane: str):
        self._active_pane = pane

    def _refresh_nav_bar(self):
        pass

    def _learning_deactivate_cursors(self):
        self.learn_cursors = False

    def _new_tab(self, title: str, content: str):
        self.editor_tabs += 1
        tab_id = f"main.untitled{self.editor_tabs}"
        self.notebook.add(tab_id)
        self.notebook.select(tab_id)

    # ── panel builders ───────────────────────────────────────────────────────

    def _build(self, kind: str, nb: FakeNotebook):
        self._serial += 1
        tab_id = f"{nb.name}.{kind}{self._serial}"
        nb.add(tab_id)
        nb.select(tab_id)
        tab_attr, panel_attr = self._PANEL_TAB_SLOTS[kind]
        setattr(self, tab_attr, tab_id)
        setattr(self, panel_attr, FakePanel())
        if kind == "learning":
            self.learn_cursors = True

    def _build_welcome_tab(self, nb):
        self._build("welcome", nb)

    def _build_packages_tab(self, nb):
        self._build("packages", nb)

    def _build_learning_tab(self, nb):
        self._build("learning", nb)

    def _build_settings_tab(self, nb):
        self._build("settings", nb)


@pytest.fixture
def host():
    return Host()


# ── where a panel tab opens ──────────────────────────────────────────────────

def test_editor_mode_opens_into_the_main_notebook(host):
    host.view_package_manager()
    assert host._pkg_tab in host.notebook.tabs()
    assert host._notebook_r is None, "no split should be conjured up"


def test_designer_mode_opens_into_the_split(host):
    """The bug: the main notebook is off screen, so the click did nothing."""
    host._designer_mode = True
    host.view_package_manager()
    assert host._notebook_r is not None, "split should have been opened"
    assert host._pkg_tab in host._notebook_r.tabs()
    assert host._pkg_tab not in host.notebook.tabs()
    assert host._active_pane == "right"


@pytest.mark.parametrize("view, slot", [
    ("view_package_manager", "_pkg_tab"),
    ("view_settings",        "_settings_tab"),
    ("view_learning_mode",   "_learning_tab"),
    ("view_welcome",         "_welcome_tab"),
])
def test_every_panel_tab_reaches_the_split_in_designer_mode(view, slot):
    host = Host(designer=True)
    getattr(host, view)()
    assert getattr(host, slot) in host._notebook_r.tabs()


def test_entering_designer_relocates_an_open_panel_tab(host):
    host.view_package_manager()
    first = host._pkg_tab
    host._designer_mode = True
    host.view_package_manager()
    assert host._pkg_tab != first, "rebuilt — Tk cannot reparent a widget"
    assert first not in host.notebook.tabs()
    assert host._pkg_tab in host._notebook_r.tabs()


def test_leaving_designer_leaves_a_visible_split_tab_alone(host):
    """The split is still on screen after the mode switch, so the tab is still
    where the user can see it — nothing yanks it back to main."""
    host._designer_mode = True
    host.view_package_manager()
    host._designer_mode = False
    assert host._panel_tab_home("packages") is host._notebook_r
    host.view_package_manager()          # visible and focused → toggles shut
    assert host._pkg_tab is None


def test_a_panel_tab_in_a_hidden_split_comes_back_in_main(host):
    """Editor mode with the split toggled off: the split is not where the tab
    would open now, so it is rebuilt in the notebook that is showing."""
    host._designer_mode = True
    host.view_package_manager()
    host._designer_mode = False
    host._split_shown = False
    host.view_package_manager()
    assert host._pkg_tab in host.notebook.tabs()


def test_a_hidden_split_is_revealed_not_rebuilt():
    """Toggling the split off and pressing F3 should bring the panel back as it
    was, not tear down and re-create it."""
    host = Host(designer=True)
    host.view_package_manager()
    same = host._pkg_tab
    host._split_shown = False
    host.view_package_manager()
    assert host._pkg_tab == same
    assert host._split_shown


# ── toggling ─────────────────────────────────────────────────────────────────

def test_second_press_closes_a_visible_panel_tab(host):
    host.view_package_manager()
    host.view_package_manager()
    assert host._pkg_tab is None
    assert host._pkg_panel is None


def test_welcome_refocuses_instead_of_closing(host):
    host.view_welcome()
    tab = host._welcome_tab
    host.view_welcome()
    assert host._welcome_tab == tab, "Welcome is the fallback tab — never toggled shut"


def test_closing_the_last_main_tab_leaves_a_buffer_behind(host):
    host.view_package_manager()
    host.view_package_manager()          # closes it; main is otherwise empty
    assert host.notebook.tabs(), "main notebook must never be left blank"


def test_a_stale_slot_is_recovered(host):
    """A tab closed via its × leaves the slot pointing at nothing."""
    host.view_settings()
    host.notebook.forget(0)
    host.view_settings()
    assert host._settings_tab in host.notebook.tabs()


# ── dragging between panes ───────────────────────────────────────────────────

def test_drag_to_split_moves_the_panel_not_a_blank_buffer():
    """It used to open an Untitled tab in the split and close the dragged one."""
    host = Host(split=True)
    host.view_package_manager()
    host._move_panel_tab("packages", host._notebook_r)
    assert host._pkg_tab in host._notebook_r.tabs()
    assert host._pkg_panel is not None


def test_drag_back_to_main_moves_it_back():
    host = Host(split=True)
    host._designer_mode = True
    host.view_settings()
    host._designer_mode = False
    host._move_panel_tab("settings", host.notebook)
    assert host._settings_tab in host.notebook.tabs()
    assert not host._notebook_r.tabs()


def test_dragging_welcome_out_backfills_main():
    host = Host(split=True)
    host.view_welcome()
    host._move_panel_tab("welcome", host._notebook_r)
    assert host._welcome_tab in host._notebook_r.tabs()
    assert host.notebook.tabs(), "main notebook must never be left blank"


def test_learning_cursors_follow_the_tab():
    """The custom cursor overlay is installed with the tab and torn down with
    it — a move must not leave it on with no panel to explain it."""
    host = Host(split=True)
    host.view_learning_mode()
    assert host.learn_cursors
    host._move_panel_tab("learning", host._notebook_r)
    assert host.learn_cursors
    host.view_learning_mode()            # focused → closes
    assert not host.learn_cursors
