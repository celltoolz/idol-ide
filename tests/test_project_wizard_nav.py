"""The project wizard's nav strip — enabled state, cursor, and Next's binding.

`_show_progress` greys both nav buttons out for the duration of the setup run.
The success screen then relabels Next to "Open Project →" and re-points it at
`_open_project`, but nothing re-enabled either button: the one live control on
that screen kept the disabled colour and lost the hand cursor every other
button in the wizard has, and Back sat there greyed while still carrying its
binding — a button that worked but looked dead.

`_render` now resets the Next button's state *and* its binding before each
step draws, so Back out of the success screen lands on a Summary step whose
Next creates a project rather than re-opening the one just made.
"""
from __future__ import annotations

import inspect

import pytest

pytestmark = pytest.mark.gui


@pytest.fixture
def wizard(tk_root, monkeypatch):
    from widgets.project_wizard import ProjectWizard

    # `__init__` shells out to `git --version` / `git config` with a 5s timeout
    # apiece. None of that is under test here, and on a loaded machine it is
    # slow enough to make these tests flaky, so the probe is stubbed out.
    monkeypatch.setattr(ProjectWizard, "_check_git", staticmethod(lambda: (True, "")))

    wiz = ProjectWizard(tk_root, on_complete=lambda *a, **k: None)
    tk_root.update()
    yield wiz
    try:
        wiz.destroy()
    except Exception:
        pass


def _cursor(widget) -> str:
    return str(widget["cursor"])


# ── the reported bug ─────────────────────────────────────────────────────────

def test_success_screen_buttons_use_the_hand_cursor(wizard, tmp_path):
    wizard._step = len(wizard._STEPS) - 1
    wizard._show_progress()                 # what greys them out
    assert _cursor(wizard._next_btn) == ""  # …and it really does

    wizard._show_success(str(tmp_path))
    assert _cursor(wizard._next_btn) == "hand2", "Open Project → is live"
    assert _cursor(wizard._prev_btn) == "hand2", "← Back is live"


def test_success_screen_buttons_lose_the_disabled_colour(wizard, tmp_path):
    wizard._step = len(wizard._STEPS) - 1
    wizard._show_progress()
    disabled_bg = str(wizard._next_btn["bg"])

    wizard._show_success(str(tmp_path))
    assert str(wizard._next_btn["bg"]) != disabled_bg
    assert str(wizard._prev_btn["bg"]) != disabled_bg


# ── what an enabled Back has to land on ──────────────────────────────────────

def test_back_from_success_returns_to_a_working_summary(wizard, tmp_path):
    wizard._step = len(wizard._STEPS) - 1
    wizard._show_progress()
    wizard._show_success(str(tmp_path))

    wizard._prev()
    assert wizard._step == len(wizard._STEPS) - 2
    assert _cursor(wizard._next_btn) == "hand2"
    assert wizard._next_btn["text"] != "Open Project →", (
        "Next must go back to advancing the wizard, not re-opening the project"
    )


def test_render_rebinds_next_to_the_wizard(wizard):
    """`_show_success` unbinds Next and points it at `_open_project`; only
    `_render` can put it back, so the reset has to live there."""
    src = inspect.getsource(type(wizard)._render)
    assert "_next_btn.unbind" in src
    assert "self._next()" in src
    assert "_set_nav_enabled(self._next_btn, True)" in src


def test_detection_still_disables_next(wizard):
    """The reset in `_render` runs before the step draws, so a step that wants
    Next disabled can still disable it."""
    wizard._detecting = True
    wizard._step = 1
    wizard._render()
    assert _cursor(wizard._next_btn) == "", "Next stays dead while detecting"
