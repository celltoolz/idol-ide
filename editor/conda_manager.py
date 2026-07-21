"""CondaManager — subprocess backend for conda package operations.

Peer backend to PipManager with the same daemon-thread + after_fn
contract, used by the Package Manager panel when the active interpreter
is a conda environment. Install is conda-first with an automatic pip
fallback (packages not on conda's channels retry via pip inside the
env); uninstall routes by each package's recorded origin.

All conda invocations use ``-p <prefix>`` so base, named, and
project-local ``-p`` environments work identically.
"""
from __future__ import annotations

import json
import subprocess
import threading
from typing import Callable

from utils import conda_env


class CondaManager:
    """Runs conda subprocesses on daemon threads, fires callbacks on the main thread."""

    def __init__(self, after_fn: Callable) -> None:
        self._after = after_fn
        self._python_exe: str = ""
        self._prefix: str | None = None
        self._conda_exe: str | None = None

    def set_python(self, exe: str) -> None:
        """Point the manager at a conda env via its python executable."""
        self._python_exe = exe
        self._prefix = conda_env.conda_prefix_for(exe)
        self._conda_exe = conda_env.find_conda_exe(self._prefix) if self._prefix else None

    @property
    def available(self) -> bool:
        """True when the env prefix and a conda executable were both located."""
        return bool(self._prefix and self._conda_exe)

    def fetch_installed(
        self,
        on_done: Callable[[dict[str, str], dict[str, str]], None],
    ) -> None:
        """Fetch installed packages via `conda list -p <prefix> --json`.

        Calls on_done(name_to_version, name_to_origin) on the main thread;
        origin is "pypi" for pip-installed packages, "conda" otherwise.
        """
        conda_exe, prefix = self._conda_exe, self._prefix

        def _run():
            installed: dict[str, str] = {}
            origins: dict[str, str] = {}
            try:
                result = subprocess.run(
                    [conda_exe, "list", "-p", prefix, "--json"],
                    capture_output=True, text=True, timeout=30,
                )
                for p in json.loads(result.stdout):
                    installed[p["name"]] = p["version"]
                    origins[p["name"]] = (
                        "pypi" if p.get("channel") == "pypi" else "conda"
                    )
            except Exception:
                installed, origins = {}, {}
            self._after(0, on_done, installed, origins)

        threading.Thread(target=_run, daemon=True).start()

    def install(
        self,
        name: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Install via conda; on any conda failure, retry with pip in the env."""
        conda_exe, prefix, python = self._conda_exe, self._prefix, self._python_exe

        def _run():
            try:
                rc = self._stream([conda_exe, "install", "-p", prefix, "-y", name],
                                  on_line, env=None)
                if rc != 0:
                    self._after(0, on_line,
                                f"\nconda could not install '{name}' — "
                                "retrying with pip inside the environment…\n")
                    self._stream([python, "-m", "pip", "install", name],
                                 on_line, env=conda_env.runtime_env(python))
            except Exception as e:
                if on_error:
                    self._after(0, on_error, str(e))
                else:
                    self._after(0, on_line, str(e) + "\n")
            self._after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def uninstall(
        self,
        name: str,
        origin: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Remove via the tool that installed the package (origin routing)."""
        conda_exe, prefix, python = self._conda_exe, self._prefix, self._python_exe
        if origin == "pypi":
            cmd = [python, "-m", "pip", "uninstall", "-y", name]
            env = conda_env.runtime_env(python)
        else:
            cmd = [conda_exe, "remove", "-p", prefix, "-y", name]
            env = None

        def _run():
            try:
                self._stream(cmd, on_line, env=env)
            except Exception as e:
                if on_error:
                    self._after(0, on_error, str(e))
                else:
                    self._after(0, on_line, str(e) + "\n")
            self._after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def _stream(self, cmd: list[str], on_line: Callable[[str], None],
                env: dict[str, str] | None) -> int:
        """Run *cmd* streaming stdout lines via after_fn; returns the exit code."""
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env,
        )
        for line in proc.stdout:
            self._after(0, on_line, line)
        proc.wait()
        return proc.returncode
