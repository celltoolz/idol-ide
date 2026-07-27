"""PyflakesLinter — local diagnostics engine, always active alongside the LSP.

Priority:
  1. ruff subprocess  — error-resilient parser, reports multiple syntax errors
  2. compile()        — catches the first syntax error (Python built-in)

Runs in a debounced background thread on every file change.  Exposes the same
open_file / change_file / close_file / on_diagnostics interface as LspManager.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from typing import Callable, Optional

from .lsp_manager import path_to_uri

SEV_ERROR   = 1
SEV_WARNING = 2
SEV_INFO    = 3

# Ruff uses both numeric (E999, F821) and descriptive (invalid-syntax,
# undefined-name) codes depending on version — handle both forms.

# Will not run or will definitely crash at runtime
_CRASH_CODES = frozenset({
    "E999", "invalid-syntax",           # parse/syntax failures
    "F821", "F822", "undefined-name",   # certain NameError at runtime
})

# Pure style/cleanup — no effect on program correctness
_STYLE_CODES = frozenset({
    "F401", "unused-import",
    "F841", "unused-variable", "unused-local",
})

# Single-char numeric prefixes that are purely stylistic
_INFO_PREFIXES = frozenset("INDQ")

# Two-char numeric prefixes that are purely stylistic
_INFO_PREFIXES_2 = frozenset({"UP", "TC", "CO", "YT"})


def _ruff_severity(code: str) -> int:
    """Map a ruff error code to SEV_ERROR / SEV_WARNING / SEV_INFO.

    Red   (ERROR) — program will not run or will definitely crash.
    Yellow (WARN) — likely bugs: undefined names, unused bindings, etc.
    Blue   (INFO) — pure style/convention, no effect on correctness.
    """
    if not code:
        return SEV_WARNING
    # Definite crashes — covers both numeric E999 and descriptive invalid-syntax
    if code in _CRASH_CODES or code.startswith("E9"):
        return SEV_ERROR
    # Pure style — both numeric F401 and descriptive unused-import etc.
    if code in _STYLE_CODES:
        return SEV_INFO
    first = code[0]
    # pycodestyle style rules (E1xx-E8xx)
    if first == "E":
        return SEV_INFO
    # isort / naming / docstrings / quotes
    if first in _INFO_PREFIXES:
        return SEV_INFO
    # pycodestyle whitespace warnings, except W605 (invalid escape = real bug)
    if first == "W" and code != "W605":
        return SEV_INFO
    # pyupgrade / type-checking imports / trailing commas / flake8-2020
    if code[:2] in _INFO_PREFIXES_2:
        return SEV_INFO
    if code.startswith("ANN"):
        return SEV_INFO
    # Everything else: bugbear, ruff-specific, security…
    return SEV_WARNING


# Resolved once at import time — same Scripts dir as the running Python
_SCRIPTS = os.path.dirname(sys.executable)


def _find_ruff() -> str | None:
    """Return the path to the ruff executable in the active env, or None."""
    import shutil
    for name in ("ruff", "ruff.exe"):
        candidate = os.path.join(_SCRIPTS, name)
        if os.path.isfile(candidate):
            return candidate
    return shutil.which("ruff")


_RUFF_EXE: str | None = _find_ruff()


class PyflakesLinter:
    """Drop-in diagnostic source — always used for diagnostics in IDOL."""

    _DEBOUNCE_MS = 400

    def __init__(self, after_fn: Callable) -> None:
        self._after_fn  = after_fn
        self._files: dict[str, str] = {}       # uri → source text
        self._versions: dict[str, int] = {}    # uri → latest scheduled version
        self.on_diagnostics: Optional[Callable[[str, list], None]] = None

    # ── Same public API as LspManager ────────────────────────────────────────

    @property
    def ready(self) -> bool:
        return True

    def open_file(self, path: str, text: str, language_id: str = "python") -> None:
        uri = path_to_uri(path)
        self._files[uri] = text
        self._schedule(uri)

    def change_file(self, path: str, text: str) -> None:
        uri = path_to_uri(path)
        self._files[uri] = text
        self._schedule(uri)

    def close_file(self, path: str) -> None:
        uri = path_to_uri(path)
        self._files.pop(uri, None)
        self._versions.pop(uri, None)

    def save_file(self, path: str) -> None:
        pass

    def stop(self) -> None:
        self._files.clear()
        self._versions.clear()

    def hover(self, *_a, **_kw) -> None:
        pass

    def definition(self, *_a, **_kw) -> None:
        pass

    def completion(self, *_a, callback: Callable | None = None, **_kw) -> None:
        if callback:
            callback([])

    # ── Internal ─────────────────────────────────────────────────────────────

    def _schedule(self, uri: str) -> None:
        v = self._versions.get(uri, 0) + 1
        self._versions[uri] = v
        self._after_fn(self._DEBOUNCE_MS, lambda u=uri, ver=v: self._run(u, ver))

    def _run(self, uri: str, version: int) -> None:
        if self._versions.get(uri) != version:
            return
        source = self._files.get(uri)
        if source is None:
            return
        threading.Thread(
            target=self._lint, args=(uri, source), daemon=True
        ).start()

    def _lint(self, uri: str, source: str) -> None:
        try:
            diags = _run_checks(source, uri)
        except Exception:
            diags = []
        if self.on_diagnostics:
            self._after_fn(0, lambda: self.on_diagnostics(uri, diags))


# ── Linting logic (background thread) ────────────────────────────────────────

def _run_checks(source: str, uri: str) -> list[dict]:
    """Return LSP-style diagnostics via ruff → compile() fallback chain."""
    # Extract a plain filesystem path from the URI for use as stdin-filename
    from .lsp_manager import uri_to_path
    try:
        filename = uri_to_path(uri)
    except Exception:
        filename = uri

    # Stage 1 — ruff subprocess (error-resilient, reports multiple syntax errors)
    if _RUFF_EXE:
        result = _run_ruff(source, filename)
        if result is not None:
            return result

    # Stage 2 — compile() for syntax errors
    return _run_fallback(source, filename)


# IDOL's fallback rule set, used only when the file being linted has no ruff
# config of its own. Written out rather than left to ruff's defaults because
# those defaults are a moving target: 0.16 widened them from 59 rules to 413,
# which turned a beginner's own file into a wall of style warnings overnight.
# This is deliberately the pyflakes-and-real-errors set — the same thing a
# user's project has been getting — and not IDOL's house style: the E7 rules
# ruff.toml switches off are about *this* codebase's idioms, and imposing them
# on someone else's code would be presumptuous.
_IDOL_BASELINE_SELECT = "E4,E7,E9,F"

# Filenames ruff itself treats as configuration.
_RUFF_CONFIG_FILES = ("ruff.toml", ".ruff.toml")


def _has_own_ruff_config(filename: str) -> bool:
    """True when a ruff config governs *filename*.

    Mirrors ruff's own discovery: walk up from the file's directory looking for
    `ruff.toml` / `.ruff.toml`, or a `pyproject.toml` that actually carries a
    `[tool.ruff]` section (a pyproject without one does not stop ruff's search).

    Deliberately un-cached. It is a handful of `stat` calls against a run that
    already spawns a subprocess, and caching would need invalidation the moment
    a user added or removed a config mid-session.
    """
    if not filename:
        return False
    try:
        d = os.path.dirname(os.path.abspath(filename))
    except (OSError, ValueError):
        return False
    while True:
        for name in _RUFF_CONFIG_FILES:
            if os.path.isfile(os.path.join(d, name)):
                return True
        pyproject = os.path.join(d, "pyproject.toml")
        if os.path.isfile(pyproject):
            try:
                with open(pyproject, encoding="utf-8", errors="replace") as fh:
                    if "[tool.ruff" in fh.read():
                        return True
            except OSError:
                pass
        parent = os.path.dirname(d)
        if parent == d:          # hit the filesystem root
            return False
        d = parent


def _run_ruff(source: str, filename: str) -> list[dict] | None:
    """Run `ruff check` via subprocess; return diagnostics or None on failure.

    A project that configures ruff gets **its own** rules — an IDE that quietly
    overrode a deliberate lint setup would be worse than one that says nothing.
    Only a project with no config falls back to `_IDOL_BASELINE_SELECT`.
    """
    cmd = [
        _RUFF_EXE,
        "check",
        "--output-format=json",
        "--stdin-filename", filename,
    ]
    if not _has_own_ruff_config(filename):
        cmd += ["--select", _IDOL_BASELINE_SELECT]
    cmd.append("-")             # read source from stdin
    try:
        proc = subprocess.run(
            cmd,
            input=source.encode("utf-8"),
            capture_output=True,
            timeout=15,
        )
        # exit 0 = no issues, exit 1 = issues found — both are valid
        if proc.returncode not in (0, 1):
            return None
        items = json.loads(proc.stdout.decode("utf-8"))
        diags: list[dict] = []
        for item in items:
            loc     = item.get("location") or {}
            end_loc = item.get("end_location") or loc
            line    = max((loc.get("row", 1) or 1) - 1, 0)
            col     = max((loc.get("column", 1) or 1) - 1, 0)
            end_ln  = max((end_loc.get("row", 1) or 1) - 1, 0)
            end_col = max((end_loc.get("column", 1) or 1) - 1, 0)
            code    = item.get("code") or ""
            msg     = item.get("message") or ""
            sev     = _ruff_severity(code)
            label   = f"{msg} ({code})" if code else msg
            diags.append({
                "range": {
                    "start": {"line": line,   "character": col},
                    "end":   {"line": end_ln, "character": end_col},
                },
                "severity": sev,
                "message":  label,
            })
        return diags
    except Exception:
        return None


def _run_fallback(source: str, filename: str) -> list[dict]:
    """compile() fallback when ruff is unavailable."""
    diags: list[dict] = []

    try:
        compile(source, filename, "exec")
    except SyntaxError as e:
        line = (e.lineno or 1) - 1
        col  = max((e.offset or 1) - 1, 0)
        diags.append(_make_diag(e.msg or str(e), line, col, SEV_ERROR))
        return diags

    return diags


def _make_diag(message: str, line: int, col: int, severity: int) -> dict:
    return {
        "range": {
            "start": {"line": line, "character": col},
            "end":   {"line": line, "character": col + 1},
        },
        "severity": severity,
        "message":  message,
    }
