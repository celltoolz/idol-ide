"""The tracked (latched) project root.

`_project_file_path()` used to re-discover the `.idol-project` from the explorer
root on every read, so anything that moved the tree changed which project IDOL
thought was open — Set as Root Directory on a subfolder silently stopped
`_autosave_workspace` writing the project file.

Exercises the real methods against a stand-in host, so the logic under test is
the shipped code without booting the whole app.
"""
from __future__ import annotations

import inspect
import os
from pathlib import Path

import pytest

import app as app_mod
from utils import session as session_mod


class Host:
    """Minimal stand-in exposing only what the methods under test touch."""
    _find_project_file  = app_mod.IDOL._find_project_file
    _set_open_project   = app_mod.IDOL._set_open_project
    _autosave_workspace = app_mod.IDOL._autosave_workspace
    _clip_scope_root    = app_mod.IDOL._clip_scope_root

    def __init__(self):
        self._project_path = None
        self._clip_panel = None
        self._clip_scope = None

    def _sync_clip_scope(self):
        self._clip_scope = self._clip_scope_root()

    def _save_clip_history(self):
        pass

    def _set_project_root(self, path):
        """The real one also moves explorer + terminal; only the latch matters."""
        self._set_open_project(self._find_project_file(path))


@pytest.fixture
def host():
    return Host()


@pytest.fixture
def projects(tmp_path):
    def _mk(name, filename=None):
        d = tmp_path / name
        d.mkdir(parents=True, exist_ok=True)
        (d / (filename or f"{name}.idol-project")).write_text("{}", encoding="utf-8")
        return d
    return _mk


# ── discovery ────────────────────────────────────────────────────────────────

def test_finds_the_project_file(host, projects):
    assert Path(host._find_project_file(projects("alpha"))).name == "alpha.idol-project"


def test_plain_folder_is_not_a_project(host, tmp_path):
    d = tmp_path / "plain"; d.mkdir()
    assert host._find_project_file(d) is None


def test_subfolder_is_not_a_project(host, projects):
    sub = projects("alpha") / "src"; sub.mkdir()
    assert host._find_project_file(sub) is None


def test_missing_directory_is_not_a_project(host, tmp_path):
    assert host._find_project_file(tmp_path / "ghost") is None


def test_discovery_prefers_the_dirname_match(host, projects):
    two = projects("two", "zzz.idol-project")
    (two / "two.idol-project").write_text("{}", encoding="utf-8")
    assert Path(host._find_project_file(two)).name == "two.idol-project"


# ── latching ─────────────────────────────────────────────────────────────────

def test_opening_latches_the_project(host, projects):
    a = projects("alpha")
    host._set_project_root(str(a))
    assert Path(host._project_path).name == "alpha.idol-project"
    assert os.path.normcase(host._clip_scope) == os.path.normcase(str(a))


def test_switching_moves_the_latch(host, projects):
    host._set_project_root(str(projects("alpha")))
    b = projects("beta")
    host._set_project_root(str(b))
    assert Path(host._project_path).name == "beta.idol-project"
    assert os.path.normcase(host._clip_scope) == os.path.normcase(str(b))


def test_explicit_open_beats_discovery(host, projects):
    """A folder with two project files must autosave into the one that was
    actually opened, not whichever wins by name."""
    two = projects("two", "zzz.idol-project")
    (two / "two.idol-project").write_text("{}", encoding="utf-8")
    host._set_open_project(str(two / "zzz.idol-project"))
    assert Path(host._project_path).name == "zzz.idol-project"


def test_closing_clears_the_latch(host, projects):
    """`_teardown_project` re-roots to $HOME then clears explicitly — a
    `.idol-project` sitting in the home folder must not be picked up."""
    homeish = projects("homeish")
    host._set_project_root(str(homeish))
    assert host._project_path is not None
    host._set_open_project(None)
    assert host._project_path is None
    assert host._clip_scope is None


def test_relatching_the_same_path_is_a_no_op(host, projects):
    a = projects("alpha")
    host._set_open_project(str(a / "alpha.idol-project"))
    host._clip_scope = "SENTINEL"
    host._set_open_project(str(a / "." / "alpha.idol-project"))
    assert host._clip_scope == "SENTINEL"
    assert os.path.isabs(host._project_path)


# ── autosave targets the latch ───────────────────────────────────────────────

def test_autosave_writes_latched_project_then_auto_session(host, projects, monkeypatch):
    saved = []
    monkeypatch.setattr(session_mod, "save", lambda a, p=None: saved.append(p))
    host._set_project_root(str(projects("alpha")))
    host._autosave_workspace()
    assert [Path(s).name if s else None for s in saved] == ["alpha.idol-project", None]


def test_autosave_with_no_project_writes_only_the_auto_session(host, monkeypatch):
    saved = []
    monkeypatch.setattr(session_mod, "save", lambda a, p=None: saved.append(p))
    host._autosave_workspace()
    assert saved == [None]


# ── wiring ───────────────────────────────────────────────────────────────────
# The fix is that explorer-root changes must not touch the latch. Asserted
# structurally: a value assertion would pass trivially whether or not the call
# was still there.

def test_explorer_root_paths_do_not_latch():
    assert "_set_open_project" not in inspect.getsource(app_mod.IDOL._set_explorer_root)
    assert "_set_open_project" not in inspect.getsource(
        app_mod.IDOL._on_explorer_root_change)


def test_clipboard_scope_no_longer_syncs_off_the_explorer_root():
    assert "_sync_clip_scope" not in inspect.getsource(
        app_mod.IDOL._on_explorer_root_change)


def test_project_root_does_latch():
    assert "_set_open_project" in inspect.getsource(app_mod.IDOL._set_project_root)
