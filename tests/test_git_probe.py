"""`git_manager.probe_identity` — the synchronous "can we offer git?" check.

The New Project wizard has to answer that before it can draw its Environment
step, so unlike `get_global_identity` this one runs on the main thread and
cannot afford to raise.  It used to live in `widgets/project_wizard.py` as
three bare `subprocess.run` calls with only the *first* wrapped in a
`try`/`except`, so a slow or wedged `git config` raised `TimeoutExpired`
straight out of the wizard's `__init__` and took the dialog with it.  Moving it
here also puts the subprocess calls back on the right side of the import rule:
`widgets/` may read from `editor/`, never run subprocesses itself.

No display needed — deliberately not marked `gui`, so `-m "not gui"` still
covers it.
"""
from __future__ import annotations

import inspect
import shutil
import subprocess

import pytest

from editor import git_manager


# ── totality: a verdict, never an exception ──────────────────────────────────

def test_every_call_failing_is_still_a_verdict(monkeypatch):
    def _boom(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 5)

    monkeypatch.setattr(subprocess, "run", _boom)
    ok, warning = git_manager.probe_identity()
    assert ok is False
    assert warning, "a falsy warning would render as a blank ⚠ row"


@pytest.mark.parametrize("failing", ["config user.name", "config user.email"])
def test_a_hung_identity_call_still_names_what_is_missing(monkeypatch, failing):
    """Not merely "doesn't raise" — the verdict has to stay useful when the
    call that dies is one of the two *after* the version probe, which is
    exactly the pair that used to be unguarded."""
    if not shutil.which("git"):
        pytest.skip("needs a real git for the version probe to succeed")

    real_run = subprocess.run

    def _selective(cmd, *args, **kwargs):
        if " ".join(cmd[1:]) == failing:
            raise subprocess.TimeoutExpired(cmd, 5)
        return real_run(cmd, *args, **kwargs)

    monkeypatch.setattr(subprocess, "run", _selective)
    ok, warning = git_manager.probe_identity()
    assert ok is False
    assert failing.split()[-1] in warning


def test_a_nonzero_exit_is_not_mistaken_for_a_value(monkeypatch):
    """`git config <unset key>` exits 1 with empty stdout; the old code read
    `.stdout` regardless of the return code and happened to agree."""
    monkeypatch.setattr(
        subprocess, "run",
        lambda *a, **k: subprocess.CompletedProcess(a[0], 1, "garbage", ""),
    )
    ok, warning = git_manager.probe_identity()
    assert ok is False


# ── the two verdicts it has to tell apart ────────────────────────────────────

def test_missing_git_is_reported_as_missing_git(monkeypatch):
    monkeypatch.setattr(git_manager, "_run_git", lambda *a, **k: "")
    ok, warning = git_manager.probe_identity()
    assert ok is False
    assert "not installed" in warning, "wrong warning routes to the wrong guide"


def test_git_present_but_no_identity(monkeypatch):
    def _fake(args, *a, **k):
        return "git version 2.43.0" if args == ["--version"] else ""

    monkeypatch.setattr(git_manager, "_run_git", _fake)
    ok, warning = git_manager.probe_identity()
    assert ok is False
    assert "identity" in warning
    assert "user.name" in warning and "user.email" in warning


def test_a_configured_identity_passes(monkeypatch):
    monkeypatch.setattr(git_manager, "_run_git", lambda *a, **k: "x")
    assert git_manager.probe_identity() == (True, "")


# ── layering ─────────────────────────────────────────────────────────────────

def test_the_wizard_delegates_instead_of_shelling_out():
    import widgets.project_wizard as pw_mod

    assert "probe_identity" in inspect.getsource(pw_mod.ProjectWizard._check_git)
    assert "import subprocess" not in inspect.getsource(pw_mod), (
        "widgets/ may import from editor/, but must not run subprocesses itself"
    )
