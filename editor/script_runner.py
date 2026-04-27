"""ScriptRunner — subprocess backend for running Python scripts.

Spawns the process on a daemon thread and pushes (text, tag) tuples to
on_output (a thread-safe queue.put). Sends None as a sentinel when done.

Stdout is opened in binary mode and read one byte at a time so input()
prompts (no trailing newline) appear immediately without TextIOWrapper
buffering getting in the way.
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
        self._stdin_lock = threading.Lock()

    def run(self, filepath: str, python_path: str = "python") -> None:
        """Spawn *filepath* with *python_path* (defaults to system Python)."""
        def _run():
            try:
                self._process = subprocess.Popen(
                    [python_path, "-u", filepath],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE,
                    bufsize=0,          # binary, no OS-level buffering
                )

                def _drain_stdout() -> None:
                    # Binary read 1 byte at a time — accumulate into UTF-8
                    # characters so multi-byte sequences are decoded correctly.
                    buf = b""
                    while True:
                        b = self._process.stdout.read(1)
                        if not b:
                            if buf:
                                self._on_output((buf.decode("utf-8", errors="replace"), ""))
                            break
                        buf += b
                        try:
                            text = buf.decode("utf-8")
                            self._on_output((text, ""))
                            buf = b""
                        except UnicodeDecodeError:
                            if len(buf) > 4:   # give up on corrupt sequence
                                self._on_output((buf.decode("utf-8", errors="replace"), ""))
                                buf = b""

                def _drain_stderr() -> None:
                    while True:
                        line = self._process.stderr.readline()
                        if not line:
                            break
                        self._on_output((line.decode("utf-8", errors="replace"), "stderr"))

                t_out = threading.Thread(target=_drain_stdout, daemon=True)
                t_err = threading.Thread(target=_drain_stderr, daemon=True)
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

    def send_input(self, text: str) -> None:
        """Write *text* to the running process's stdin."""
        with self._stdin_lock:
            if self._process and self._process.poll() is None:
                try:
                    self._process.stdin.write(text.encode("utf-8"))
                    self._process.stdin.flush()
                except Exception:
                    pass

    def stop(self) -> bool:
        """Terminate the running process. Returns True if a process was killed."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            return True
        return False
