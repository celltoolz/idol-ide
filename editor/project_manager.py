"""ProjectManager — interpreter discovery and project scaffolding backend.

All blocking operations run on daemon threads and deliver results to the
main thread via after_fn (tkinter's `after`).
"""
from __future__ import annotations

import glob
import os
import re
import shutil
import subprocess
import sys
import threading
from typing import Callable


def _detect_pythons() -> list[tuple[str, str]]:
    """Return a list of (label, executable_path) for available Python interpreters."""
    seen_real: set[str] = set()
    seen_path: set[str] = set()
    results:   list[tuple[str, str]] = []

    def _add(path: str) -> None:
        resolved = shutil.which(path) or (path if os.path.isfile(path) else None)
        if not resolved:
            return
        norm = os.path.normcase(os.path.realpath(resolved))
        if norm in seen_real:
            return
        seen_real.add(norm)
        seen_path.add(os.path.normcase(resolved))
        try:
            out = subprocess.check_output(
                [resolved, "--version"], stderr=subprocess.STDOUT, timeout=3
            ).decode().strip()
            version = out.split()[-1]
        except Exception:
            return
        results.append((f"Python {version}  ({resolved})", resolved))

    def _add_venv(path: str) -> None:
        resolved = path if os.path.isfile(path) else None
        if not resolved:
            return
        norm = os.path.normcase(resolved)
        if norm in seen_path:
            return
        seen_path.add(norm)
        try:
            out = subprocess.check_output(
                [resolved, "--version"], stderr=subprocess.STDOUT, timeout=3
            ).decode().strip()
            version = out.split()[-1]
        except Exception:
            return
        results.append((f"Python {version}  ({resolved})", resolved))

    for prefix in ("/usr/bin", "/usr/local/bin", "/opt/homebrew/bin",
                   os.path.expanduser("~/.pyenv/shims")):
        for name in ("python3", "python", "python3.14", "python3.13",
                     "python3.12", "python3.11", "python3.10", "python3.9"):
            _add(os.path.join(prefix, name))

    for pattern in ("/usr/local/Cellar/python*/*/bin/python3",
                    "/opt/homebrew/Cellar/python*/*/bin/python3"):
        for p in sorted(glob.glob(pattern), reverse=True):
            _add(p)

    py = shutil.which("py")
    if py:
        try:
            out = subprocess.check_output([py, "-0p"], stderr=subprocess.STDOUT,
                                          timeout=3).decode()
            for line in out.splitlines():
                # Handles both old style "-3.12-64  path" and new "-V:3.14  path"
                m = re.search(r"-(?:V:)?(\d+\.\d+)[^\s]*\s+(.*python[^\s]*)",
                              line, re.IGNORECASE)
                if m:
                    _add(m.group(2).strip())
        except Exception:
            pass

    # Windows: scan user-level and system-level Python install directories
    if sys.platform == "win32":
        local_app = os.environ.get("LOCALAPPDATA", "")
        for base in (
            os.path.join(local_app, "Programs", "Python"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Python"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Python"),
        ):
            if os.path.isdir(base):
                for entry in sorted(os.listdir(base), reverse=True):
                    _add(os.path.join(base, entry, "python.exe"))

    for name in ("python3", "python", "python3.14", "python3.13", "python3.12",
                 "python3.11", "python3.10", "python3.9"):
        _add(name)

    exe = sys.executable
    if any(v in exe.replace("\\", "/") for v in ("/venv/", "/.venv/")):
        _add_venv(exe)
    for pattern in (
        os.path.expanduser("~/*/venv/bin/python3"),
        os.path.expanduser("~/*/.venv/bin/python3"),
        os.path.expanduser("~/venv/*/bin/python3"),
    ):
        for p in sorted(glob.glob(pattern)):
            _add_venv(p)

    return results if results else [("Python (system default)", sys.executable)]


def categorize_interpreter(exe: str) -> str:
    """Return 'venv' or 'system' for a given interpreter path.

    Detects venvs by looking for pyvenv.cfg in parent directories — authoritative
    regardless of directory name or symlink layout.
    """
    from pathlib import Path
    try:
        p = Path(exe).resolve()
        for parent in list(p.parents)[:4]:
            if (parent / "pyvenv.cfg").exists():
                return "venv"
    except OSError:
        pass
    return "system"


class ProjectManager:
    """Runs interpreter detection and project scaffolding on daemon threads."""

    def __init__(self, after_fn: Callable) -> None:
        self._after = after_fn

    def discover_interpreters(
        self,
        on_done: Callable[[list[tuple[str, str]]], None],
    ) -> None:
        """Detect available Python interpreters on a daemon thread.

        Calls on_done(results) on the main thread when complete.
        """
        def _run():
            results = _detect_pythons()
            self._after(0, on_done, results)

        threading.Thread(target=_run, daemon=True).start()

    def scaffold_project(
        self,
        path: str,
        python: str,
        create_venv: bool,
        create_git: bool,
        on_status: Callable[[str], None],
        on_done: Callable[[str | None], None],
        write_files_fn: Callable[[str], None] | None = None,
    ) -> None:
        """Create venv and/or git repo for a new project on a daemon thread.

        Calls on_status(msg) for progress updates (on main thread).
        Calls on_done(error) when complete; error is None on success.
        write_files_fn, if provided, is called between venv and git init.
        """
        def _run():
            error: str | None = None
            try:
                if create_venv:
                    self._after(0, on_status, "Creating virtual environment…")
                    subprocess.run([python, "-m", "venv", os.path.join(path, ".venv")],
                                   check=True, timeout=120)
                if write_files_fn:
                    self._after(0, on_status, "Writing starter files…")
                    write_files_fn(path)
                if create_git:
                    self._after(0, on_status, "Initializing git repository…")
                    subprocess.run(["git", "init", path], check=True, timeout=10)
            except subprocess.CalledProcessError as e:
                error = f"An error occurred during project setup:\n{e}"
            except Exception as e:
                error = str(e)
            self._after(0, on_done, error)

        threading.Thread(target=_run, daemon=True).start()
