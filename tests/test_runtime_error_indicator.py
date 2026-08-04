"""Which frame the runtime-error indicator jumps to, and when it fires at all.

Three latent defects in `OutputPanel._try_fire_runtime_error`, found by reading
the code rather than from any reported failure — see TODO.md for why the report
that prompted the read was withdrawn.

  * success was decided by searching the whole buffer for "exit code 0"
  * the frame to jump to was `matches[-1]`, the innermost one
  * every failure inside `on_runtime_error` was swallowed silently

Bound onto a stand-in rather than a real panel: none of these touch a widget
beyond reading text and writing a line, so they stay headless.
"""
from __future__ import annotations

import pytest

from widgets.output import OutputPanel

_pick = OutputPanel._pick_error_frame
_fire = OutputPanel._try_fire_runtime_error
_set_root = OutputPanel._set_run_root


class _Runner:
    def __init__(self, returncode=1) -> None:
        self.returncode = returncode


class _Panel:
    """Only what the three methods under test touch."""

    def __init__(self, text: str = "", returncode: int = 1, root: str = "") -> None:
        import os
        self._text_value = text
        self._runner = _Runner(returncode)
        self._run_root = os.path.normcase(os.path.abspath(root)) if root else ""
        self.fired: list[tuple[str, int]] = []
        self.messages: list[str] = []
        self.written: list[str] = []
        self.raise_on_fire: Exception | None = None

    # stand-ins for the real collaborators
    @property
    def _text(self):
        outer = self

        class _T:
            def get(self, *_a):
                return outer._text_value
        return _T()

    def write(self, text, tag=None) -> None:
        self.written.append(text)

    def on_runtime_error(self, path, lineno, message="") -> None:
        if self.raise_on_fire:
            raise self.raise_on_fire
        self.fired.append((path, lineno))
        self.messages.append(message)

    _pick_error_frame = _pick
    _is_under_run_root = OutputPanel._is_under_run_root
    # staticmethod: accessing it on the class yields the plain function, which
    # would bind as a method here and swallow `text` into `self`.
    _exception_message = staticmethod(OutputPanel._exception_message)


def _tb(*frames: tuple[str, int]) -> str:
    body = "\n".join(f'  File "{p}", line {n}, in <module>' for p, n in frames)
    return "Traceback (most recent call last):\n" + body + "\nValueError: boom\n"


# ── Which frame ──────────────────────────────────────────────────────────────

@pytest.fixture
def project(tmp_path):
    """A project dir with a script, plus a 'dependency' outside it."""
    (tmp_path / "proj").mkdir()
    app = tmp_path / "proj" / "app.py"
    app.write_text("x = 1\n")
    lib = tmp_path / "site-packages" / "dep"
    lib.mkdir(parents=True)
    mod = lib / "core.py"
    mod.write_text("y = 2\n")
    return {"root": str(tmp_path / "proj"), "app": str(app), "lib": str(mod)}


def test_dependency_frame_is_not_preferred_over_the_users_code(project):
    """The reported shape: an exception raised inside a library. `matches[-1]`
    is that library, so IDOL opened a file the user cannot act on."""
    panel = _Panel(root=project["root"])
    frame = panel._pick_error_frame(
        [(project["app"], "10"), (project["lib"], "99")])
    assert frame == (project["app"], 10)


def test_innermost_project_frame_wins_among_several(project):
    """Innermost *of the user's own*, not outermost — the call that failed."""
    other = project["root"] + "/helper.py"
    with open(other, "w") as fh:
        fh.write("z = 3\n")
    panel = _Panel(root=project["root"])
    frame = panel._pick_error_frame(
        [(project["app"], "10"), (other, "20"), (project["lib"], "99")])
    assert frame == (other, 20)


def test_frames_whose_file_is_gone_are_skipped(project):
    panel = _Panel(root=project["root"])
    frame = panel._pick_error_frame(
        [(project["app"], "10"), (project["root"] + "/deleted.py", "5")])
    assert frame == (project["app"], 10)


def test_falls_back_to_the_innermost_real_file(project):
    """Nothing in the project: a library frame still beats doing nothing."""
    panel = _Panel(root=project["root"] + "/nowhere")
    frame = panel._pick_error_frame([(project["lib"], "99")])
    assert frame == (project["lib"], 99)


def test_no_usable_frame_returns_none(project):
    panel = _Panel(root=project["root"])
    assert panel._pick_error_frame([]) is None
    assert panel._pick_error_frame([("/nope/gone.py", "3")]) is None


def test_non_numeric_line_is_ignored(project):
    panel = _Panel(root=project["root"])
    assert panel._pick_error_frame([(project["app"], "not-a-number")]) is None


# ── When it fires ────────────────────────────────────────────────────────────

def test_exit_code_zero_in_program_output_no_longer_suppresses(project):
    """A program that prints the string used to silence its own crash."""
    text = "look, exit code 0 is fine\n" + _tb((project["app"], 4))
    panel = _Panel(text=text, returncode=1, root=project["root"])
    _fire(panel)
    assert panel.fired == [(project["app"], 4)]


def test_a_successful_run_does_not_fire(project):
    """A program that caught its own exception and printed it. Includes the
    real exit line, so this pins the new contract rather than scoring a point
    off a stand-in the old substring check would have handled too."""
    text = (_tb((project["app"], 4))
            + "\nProcess finished with exit code 0\n")
    panel = _Panel(text=text, returncode=0, root=project["root"])
    _fire(panel)
    assert panel.fired == []


def test_a_failure_reports_instead_of_vanishing(project):
    """The swallowed exception is why the last report of this was
    undiagnosable — it looked identical to 'no traceback found'."""
    panel = _Panel(text=_tb((project["app"], 4)), returncode=1,
                   root=project["root"])
    panel.raise_on_fire = RuntimeError("tab is gone")
    _fire(panel)
    assert panel.fired == []
    assert any("tab is gone" in w for w in panel.written)


# ── The exception message ────────────────────────────────────────────────────
#
# The PROBLEMS entry is only worth having if it says what went wrong. Python
# closes a traceback with the exception at column 0, after the indented frames.

_msg = OutputPanel._exception_message


def test_exception_message_is_the_last_unindented_line():
    text = _tb(("app.py", 4))
    assert _msg(text) == "ValueError: boom"


def test_exception_message_ignores_output_written_after_the_run():
    """This panel keeps being written to — the Package Manager streams pip and
    conda output through it — so the search has to stop at the exit line."""
    text = (_tb(("app.py", 4))
            + "\nProcess finished with exit code 1\n"
            + "\n$ conda install -y pillow\nSolving environment: done\n")
    assert _msg(text) == "ValueError: boom"


def test_chained_traceback_reports_the_exception_that_stopped_the_run():
    text = (_tb(("app.py", 4))
            + "\nDuring handling of the above exception, another occurred:\n\n"
            + "Traceback (most recent call last):\n"
            + '  File "app.py", line 9, in <module>\n'
            + "RuntimeError: the real one\n")
    assert _msg(text) == "RuntimeError: the real one"


def test_no_traceback_gives_no_message():
    assert _msg("just some output\n") == ""


def test_message_reaches_the_host(project):
    panel = _Panel(text=_tb((project["app"], 4)), returncode=1,
                   root=project["root"])
    _fire(panel)
    assert panel.messages == ["ValueError: boom"]


# ── The run root ─────────────────────────────────────────────────────────────

def test_run_root_prefers_the_cwd(project, tmp_path):
    panel = _Panel()
    _set_root(panel, project["root"], project["app"])
    import os
    assert panel._run_root == os.path.normcase(os.path.abspath(project["root"]))


def test_run_root_falls_back_to_the_scripts_directory(project):
    """The legacy no-cwd case, where the project root is not knowable here."""
    panel = _Panel()
    _set_root(panel, None, project["app"])
    import os
    assert panel._run_root == os.path.normcase(
        os.path.dirname(os.path.abspath(project["app"])))
