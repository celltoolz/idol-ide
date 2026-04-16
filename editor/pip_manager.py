"""PipManager — subprocess backend for pip operations.

All methods run on daemon threads and deliver results to the main thread
via after_fn (tkinter's `after`).
"""
from __future__ import annotations

import json
import subprocess
import sys
import threading
from typing import Callable


class PipManager:
    """Runs pip subprocesses on daemon threads, fires callbacks on the main thread."""

    def __init__(self, after_fn: Callable) -> None:
        self._after = after_fn

    def fetch_installed(self, on_done: Callable[[dict[str, str]], None]) -> None:
        """Fetch installed packages via `pip list --format=json`.

        Calls on_done(name_to_version) on the main thread when complete.
        """
        def _run():
            try:
                result = subprocess.run(
                    [sys.executable, "-m", "pip", "list", "--format=json"],
                    capture_output=True, text=True, timeout=15,
                )
                pkgs = json.loads(result.stdout)
                installed = {p["name"]: p["version"] for p in pkgs}
            except Exception:
                installed = {}
            self._after(0, on_done, installed)

        threading.Thread(target=_run, daemon=True).start()

    def run_operation(
        self,
        args: list[str],
        on_line: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Run `pip <args>`, streaming each output line via on_line.

        Calls on_done() on the main thread when the process exits.
        If an exception is raised and on_error is provided, calls on_error(msg)
        instead of routing through on_line.
        """
        def _run():
            try:
                proc = subprocess.Popen(
                    [sys.executable, "-m", "pip"] + args,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True,
                )
                for line in proc.stdout:
                    self._after(0, on_line, line)
                proc.wait()
            except Exception as e:
                if on_error:
                    self._after(0, on_error, str(e))
                else:
                    self._after(0, on_line, str(e) + "\n")
            self._after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()
