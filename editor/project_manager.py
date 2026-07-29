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

from utils import conda_env


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

    # Conda envs: registry file + well-known base installs. The bare
    # --version probe is safe for unactivated conda pythons (needs no
    # Library\bin DLLs); anything heavier would.
    conda_prefixes = conda_env.list_conda_env_prefixes()
    seen_conda = {os.path.normcase(p) for p in conda_prefixes}
    for base in conda_env.find_base_prefixes():
        if os.path.normcase(base) not in seen_conda:
            conda_prefixes.append(base)
    for prefix in conda_prefixes:
        exe = conda_env.python_exe_for(prefix)
        if not os.path.isfile(exe):
            continue
        norm = os.path.normcase(os.path.realpath(exe))
        if norm in seen_real or os.path.normcase(exe) in seen_path:
            continue
        seen_real.add(norm)
        seen_path.add(os.path.normcase(exe))
        try:
            out = subprocess.check_output(
                [exe, "--version"], stderr=subprocess.STDOUT, timeout=3
            ).decode().strip()
            version = out.split()[-1]
        except Exception:
            continue
        name = conda_env.env_name_for(prefix)
        results.append((f"Python {version}  (conda: {name})  ({exe})", exe))

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
    """Return 'venv', 'conda', or 'system' for a given interpreter path.

    Detects venvs by looking for pyvenv.cfg in parent directories of the
    original path (not resolved) — on Linux, venv pythons are symlinks to
    the system binary so resolve() would lose the venv directory context.
    The pyvenv.cfg check runs first: a venv created *from* a conda python
    is still a venv.
    """
    from pathlib import Path
    try:
        for parent in list(Path(exe).parents)[:4]:
            if (parent / "pyvenv.cfg").exists():
                return "venv"
    except OSError:
        pass
    if conda_env.is_conda_env(exe):
        return "conda"
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
        conda_py_version: str | None = None,
        conda_channels: list[str] | None = None,
    ) -> None:
        """Create venv and/or git repo for a new project on a daemon thread.

        Calls on_status(msg) for progress updates (on main thread).
        Calls on_done(error) when complete; error is None on success.
        write_files_fn, if provided, is called between venv and git init.
        conda_py_version ("3.12" etc.) pins the python version when *python*
        is a conda interpreter; None falls back to the interpreter's own
        version.
        conda_channels scopes `conda create` to the same channels the project's
        environment.yml will declare, highest priority first. Without it the new
        env is solved against whatever ~/.condarc happened to say, so a project
        can be wrong from birth — its own file lists one set of channels while
        the env it ships with was built from another.
        """
        def _run():
            error: str | None = None
            try:
                if create_venv:
                    if conda_env.is_conda_env(python):
                        # Conda interpreter selected → create a project-local
                        # conda env instead of a venv. Pinned to the selected
                        # interpreter's version so the env matches what the
                        # user picked. Conda solves + downloads, so the
                        # timeout is much longer than venv's.
                        self._after(0, on_status,
                                    "Creating conda environment… (this can take a few minutes)")
                        conda_exe = conda_env.find_conda_exe(
                            conda_env.conda_prefix_for(python))
                        if not conda_exe:
                            raise RuntimeError(
                                "conda executable not found for the selected interpreter")
                        ver = conda_py_version
                        if not ver:
                            ver_out = subprocess.check_output(
                                [python, "--version"], stderr=subprocess.STDOUT, timeout=10
                            ).decode().strip()
                            ver = ".".join(ver_out.split()[-1].split(".")[:2])
                        chan: list[str] = []
                        for channel in (conda_channels or []):
                            if channel:
                                chan += ["-c", channel]
                        result = subprocess.run(
                            [conda_exe, "create", "-p", os.path.join(path, ".conda"),
                             "-y", *chan, f"python={ver}"],
                            capture_output=True, text=True, timeout=600,
                        )
                        if result.returncode != 0:
                            # Surface conda's own stderr (ToS prompts, network
                            # errors) so the user sees actionable instructions.
                            tail = (result.stderr or result.stdout or "").strip()[-800:]
                            raise RuntimeError(f"conda create failed:\n{tail}")
                    else:
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
