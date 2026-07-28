"""Shared fixtures.

Two environmental facts shape everything here:

1. IDOL is a Tkinter app, so some tests need a real display. Those are marked
   `gui` and skip cleanly when there isn't one, so `pytest` works over SSH, in
   a container, and on a Linux CI runner without xvfb — it just covers less.
2. Several tests assert on *ruff's* output. They shell out to the pinned ruff
   from requirements.txt rather than importing anything, because the thing
   under test is what the user's Problems panel will actually show.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def _tk_session():
    """One Tk root for the whole run.

    Creating and destroying a root per test is flaky — the interpreter loses
    track of the Tcl library between teardowns and later roots fail with
    "Can't find a usable tk.tcl", which surfaced as tests skipping at random.
    One root per session is also markedly faster.

    Deliberately *not* withdrawn: the canvas editor computes layout from
    `winfo_height()`, and a withdrawn toplevel reports 1px, which would make
    scroll and ensure-visible assertions meaningless instead of failing loudly.
    """
    tk = pytest.importorskip("tkinter")
    try:
        root = tk.Tk()
    except tk.TclError as exc:                       # no DISPLAY, no Tk build
        pytest.skip(f"no usable Tk display: {exc}")
    root.geometry("900x650")
    try:
        yield root
    finally:
        try:
            root.destroy()
        except Exception:
            pass


@pytest.fixture
def tk_root(_tk_session):
    """A clean widget surface on the shared root — children are torn down
    between tests so widget state cannot leak, but the root itself persists."""
    for child in list(_tk_session.winfo_children()):
        try:
            child.destroy()
        except Exception:
            pass
    _tk_session.update()
    return _tk_session


@pytest.fixture(scope="session")
def ruff():
    """Run the pinned ruff: `ruff("check", "--isolated", path)` -> CompletedProcess.

    Invoked as `python -m ruff` rather than by locating the executable, so it
    resolves to the interpreter running the tests on every platform without
    Scripts/ vs bin/ guesswork.
    """
    probe = subprocess.run(
        [sys.executable, "-m", "ruff", "--version"], capture_output=True
    )
    if probe.returncode != 0:
        pytest.skip("ruff is not installed in this environment")

    def _run(*args: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            [sys.executable, "-m", "ruff", *args],
            capture_output=True, text=True,
        )

    return _run


@pytest.fixture
def lint_source(ruff, tmp_path):
    """Write *src* to a temp file and return ruff's findings as a code list.

    `--isolated` so a ruff config living above the temp directory can never
    change the result, and an explicit `--select` because the assertions are
    about specific rules — several of which are not defaults on the pinned
    version, which is the whole point of checking them.
    """
    counter = {"n": 0}

    def _lint(src: str, select: str = "I,E4,F", name: str | None = None) -> list[str]:
        counter["n"] += 1
        p = tmp_path / (name or f"sample{counter['n']}.py")
        p.write_text(src, encoding="utf-8")
        proc = ruff("check", "--isolated", "--select", select,
                    "--output-format=concise", str(p))
        if proc.returncode == 0:
            return []
        codes = []
        for line in proc.stdout.splitlines():
            parts = line.split(": ", 1)
            if len(parts) == 2:
                codes.append(parts[1].split()[0])
        return codes

    return _lint
