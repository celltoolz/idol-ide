"""ScriptRunner — subprocess backend for running Python scripts.

Spawns the process on a daemon thread and pushes (line, tag) tuples to
on_output (a thread-safe queue.put). Sends None as a sentinel when done.
"""
from __future__ import annotations

import subprocess
import threading
from typing import Callable


class ScriptRunner:
    """Runs a Python script in a subprocess, streaming output via a callback."""

    def __init__(self, on_output: Callable) -> None:
        self._on_output = on_output
        self._process: subprocess.Popen | None = None

    def run(self, filepath: str) -> None:
        """Spawn *filepath* with the system Python interpreter."""
        def _run():
            try:
                self._process = subprocess.Popen(
                    ["python", filepath],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    bufsize=1,
                )

                def _drain(stream, tag: str) -> None:
                    for line in stream:
                        self._on_output((line, tag))

                t_out = threading.Thread(target=_drain, args=(self._process.stdout, ""), daemon=True)
                t_err = threading.Thread(target=_drain, args=(self._process.stderr, "stderr"), daemon=True)
                t_out.start()
                t_err.start()
                t_out.join()
                t_err.join()
                self._process.wait()

                rc = self._process.returncode
                tag = "success" if rc == 0 else "stderr"
                self._on_output((f"\nProcess finished with exit code {rc}\n", tag))
            except FileNotFoundError:
                self._on_output(("Error: Python interpreter not found on PATH.\n", "stderr"))
            except Exception as exc:
                self._on_output((f"Error: {exc}\n", "stderr"))
            finally:
                self._on_output(None)  # sentinel — process is done

        threading.Thread(target=_run, daemon=True).start()

    def stop(self) -> bool:
        """Terminate the running process. Returns True if a process was killed."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            return True
        return False
