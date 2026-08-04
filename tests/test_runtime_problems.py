"""A failed run puts a real entry in the PROBLEMS panel.

Until this existed, no runtime error had *ever* appeared there. `_on_runtime_error`
painted the gutter triangle and flashed the PROBLEMS tab, and the panel it drew
attention to held whatever the linter had last found — which, for a crash caused
by a missing import, is nothing at all: ruff never resolves imports and
`compile()` never executes them.

The entry is **merged** in `_build_problem_entries` rather than pushed to the
panel, because `BottomPanel.update_problems` replaces the whole list on every
lint pass. An injected entry would survive until the next keystroke.

Bound onto a stand-in (the `Host` idiom from tests/test_project_root.py) — `IDOL`
owns the whole object graph and cannot be instantiated in a test.
"""
from __future__ import annotations

import app as app_mod

SEV_ERROR = 1
SEV_WARNING = 2

_build = app_mod.IDOL._build_problem_entries
_refresh = app_mod.IDOL._refresh_problems
_clear = app_mod.IDOL._clear_runtime_problems


class _Output:
    def __init__(self) -> None:
        self.pushed: list[list[dict]] = []

    def update_problems(self, entries):
        self.pushed.append(entries)


class _StatusBar:
    def __init__(self) -> None:
        self.counts: list[tuple[int, int]] = []

    def set_diagnostics(self, errors, warnings):
        self.counts.append((errors, warnings))


class _Host:
    """Only what the three methods under test touch."""

    def __init__(self, lsp=None, runtime=None) -> None:
        self._lsp_diagnostics = lsp or {}
        self._runtime_problems = runtime or []
        self._output = _Output()
        self._statusbar = _StatusBar()

    _build_problem_entries = _build
    _refresh_problems = _refresh
    _clear_runtime_problems = _clear


def _runtime_entry(message="ModuleNotFoundError: No module named 'PIL'"):
    return {
        "filepath": "/proj/app.py", "filename": "app.py",
        "line": 4, "col": 0, "severity": SEV_ERROR, "message": message,
    }


def _lsp_diag(line=9, severity=SEV_WARNING, message="unused import"):
    return {"range": {"start": {"line": line - 1, "character": 0}},
            "severity": severity, "message": message}


# ── Merging ──────────────────────────────────────────────────────────────────

def test_runtime_problem_appears_in_the_entries():
    host = _Host(runtime=[_runtime_entry()])
    entries = host._build_problem_entries()
    assert len(entries) == 1
    assert entries[0]["message"] == "ModuleNotFoundError: No module named 'PIL'"


def test_lint_problems_are_not_replaced_by_it():
    """The bug this shape avoids: a runtime entry must not cost the linter's."""
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]},
                 runtime=[_runtime_entry()])
    entries = host._build_problem_entries()
    assert len(entries) == 2
    assert {e["message"] for e in entries} == {
        "ModuleNotFoundError: No module named 'PIL'", "unused import"}


def test_the_crash_is_listed_first():
    """A crash you just watched happen outranks a lint warning."""
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]},
                 runtime=[_runtime_entry()])
    assert host._build_problem_entries()[0]["severity"] == SEV_ERROR


def test_a_later_lint_pass_does_not_wipe_it():
    """Diagnostics arriving is the event that used to erase an injected entry:
    the whole list is rebuilt, so the runtime problem has to be rebuilt too."""
    host = _Host(runtime=[_runtime_entry()])
    host._refresh_problems()
    host._lsp_diagnostics["file:///proj/app.py"] = [_lsp_diag()]
    host._refresh_problems()
    assert len(host._output.pushed[-1]) == 2


def test_no_runtime_problem_changes_nothing():
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]})
    assert len(host._build_problem_entries()) == 1


# ── Counting ─────────────────────────────────────────────────────────────────

def test_the_runtime_error_is_counted_in_the_status_bar():
    host = _Host(runtime=[_runtime_entry()])
    host._refresh_problems()
    assert host._statusbar.counts == [(1, 0)]


def test_errors_and_warnings_are_counted_separately():
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]},
                 runtime=[_runtime_entry()])
    host._refresh_problems()
    assert host._statusbar.counts == [(1, 1)]


# ── Clearing ─────────────────────────────────────────────────────────────────

def test_clearing_drops_the_entry_and_repushes():
    host = _Host(runtime=[_runtime_entry()])
    host._clear_runtime_problems()
    assert host._runtime_problems == []
    assert host._output.pushed[-1] == []


def test_clearing_leaves_lint_problems_alone():
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]},
                 runtime=[_runtime_entry()])
    host._clear_runtime_problems()
    assert len(host._output.pushed[-1]) == 1


def test_clearing_when_there_is_nothing_does_not_repush():
    """Idempotent and cheap, so callers that may or may not have one — run
    start, project close, the package-changed hub — can just call it."""
    host = _Host(lsp={"file:///proj/app.py": [_lsp_diag()]})
    host._clear_runtime_problems()
    assert host._output.pushed == []
