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


# ── the latched explorer root ────────────────────────────────────────────────
# `self._explorer_root` was read by three sites and assigned by none, so every
# one of them silently used its fallback. Two of those keyed the remembered
# interpreter, which made it machine-global instead of per-project: the write
# and the read were wrong *consistently*, so the value round-tripped and
# nothing looked broken.


class RootHost:
    """Stand-in for the explorer-root latch and the interpreter key."""
    _on_explorer_root_change = app_mod.IDOL._on_explorer_root_change
    _init_interpreter        = app_mod.IDOL._init_interpreter

    def __init__(self):
        self._explorer_root = ""
        self._git = None
        self._designer_mode = False
        self._active_python = ""
        self._active_python_label = ""
        self._files = {}
        self._output = type("O", (), {"set_cwd": lambda s, p: None})()
        self._statusbar = type("S", (), {"set_interpreter": lambda s, lbl: None})()
        self._safe_after = lambda delay, cb, *a: cb(*a)
        self.started_git = 0

    def _start_git(self):
        self.started_git += 1

    def _enter_editor_mode(self):
        pass

    def _get_short_interp_label(self, label):
        return label

    def _find_project_python(self, _fp):
        return ""


def test_explorer_root_is_latched_on_every_change(tmp_path):
    host = RootHost()
    host._on_explorer_root_change(str(tmp_path))
    assert host._explorer_root == str(tmp_path)
    other = tmp_path / "sub"
    other.mkdir()
    host._on_explorer_root_change(str(other))
    assert host._explorer_root == str(other)


def test_remembered_interpreter_is_read_after_the_root_settles(tmp_path, monkeypatch):
    """The ordering half of the fix, and the reason latching alone is not enough.

    `_init_interpreter` runs from `_build_layout`, which is *before* the startup
    path that opens a project and sets the explorer root — so at call time there
    is no root to key on. The settings read therefore happens inside the
    `discover_interpreters` callback, which is delivered through `_safe_after`
    and so cannot run until the mainloop starts. Without this, latching the root
    would fix the write and leave the read looking up a key nothing writes.
    """
    import editor.project_manager as pm_mod
    from utils import settings as settings_mod

    captured = {}

    class FakePM:
        def __init__(self, _after):
            pass

        def discover_interpreters(self, cb):
            captured["cb"] = cb

    monkeypatch.setattr(pm_mod, "ProjectManager", FakePM)
    asked: list[str] = []
    monkeypatch.setattr(settings_mod, "get",
                        lambda key, default=None: asked.append(key))

    host = RootHost()
    host._init_interpreter()
    # Nothing read yet: at this point in startup there is no root to key on.
    assert asked == []

    # The root settles, *then* the background probe returns.
    host._on_explorer_root_change(str(tmp_path))
    captured["cb"]([])
    assert asked == [f"interpreter:{tmp_path}"]


def test_both_interpreter_sites_key_off_the_latched_root():
    """Write and read must derive the key the same way or they cannot agree.

    Structural, like the latch assertions above: a value assertion would pass
    whether or not the site still consulted the attribute.
    """
    for method in (app_mod.IDOL._init_interpreter,
                   app_mod.IDOL._set_active_interpreter):
        src = inspect.getsource(method)
        assert "self._explorer_root" in src
        # The bug was reading it through getattr with a default, which hid that
        # the attribute never existed.
        assert 'getattr(self, "_explorer_root"' not in src
