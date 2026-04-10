from __future__ import annotations

import queue
import subprocess
import tempfile
import threading
from tkinter import Text, ttk
from typing import Callable, Optional


class OutputPanel(ttk.Frame):
    """Terminal-style output panel for running Python files.

    Runs the subprocess in a background thread and pumps output into a queue
    that is drained every 50 ms on the main thread (safe for tkinter).

    Usage:
        panel.run(filepath)   – run a file
        panel.terminate()     – kill the running process
        panel.clear()         – clear the text area
    """

    def __init__(
        self,
        master,
        run_callback: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._run_callback = run_callback
        self._process: Optional[subprocess.Popen] = None
        self._queue: queue.Queue = queue.Queue()
        self._is_running = False

        self._build_ui()
        self._poll()

    def _build_ui(self) -> None:
        # ── Toolbar ──────────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", side="top", pady=(2, 0), padx=4)

        ttk.Label(toolbar, text="OUTPUT", font=("TkDefaultFont", 8, "bold")).pack(
            side="left", padx=(0, 8)
        )

        self._run_btn = ttk.Button(toolbar, text="▶  Run", width=8, command=self._on_run_click)
        self._run_btn.pack(side="left", padx=2)

        self._stop_btn = ttk.Button(
            toolbar, text="■  Stop", width=8, command=self.terminate, state="disabled"
        )
        self._stop_btn.pack(side="left", padx=2)

        ttk.Button(toolbar, text="✕  Clear", width=8, command=self.clear).pack(side="left", padx=2)

        ttk.Separator(self, orient="horizontal").pack(fill="x")

        # ── Text area ─────────────────────────────────────────────────────────
        text_frame = ttk.Frame(self)
        text_frame.pack(fill="both", expand=True)
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._text = Text(
            text_frame,
            bg="#1e1e1e", fg="#f8f8f2",
            font=("Consolas", 10),
            state="disabled",
            wrap="word",
            relief="flat",
            borderwidth=0,
            insertbackground="#f8f8f2",
        )
        vs = ttk.Scrollbar(text_frame, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vs.set)

        self._text.grid(row=0, column=0, sticky="nswe")
        vs.grid(row=0, column=1, sticky="ns")

        # Output tags
        self._text.tag_configure("stderr",  foreground="#ff5555")
        self._text.tag_configure("info",    foreground="#6272a4")
        self._text.tag_configure("success", foreground="#50fa7b")
        self._text.tag_configure("warning", foreground="#f1fa8c")

    # ── Public API ────────────────────────────────────────────────────────────

    def write(self, text: str, tag: str = "") -> None:
        """Append text (optionally with a colour tag) and scroll to end."""
        self._text.configure(state="normal")
        self._text.insert("end", text, tag)
        self._text.see("end")
        self._text.configure(state="disabled")

    def clear(self) -> None:
        self._text.configure(state="normal")
        self._text.delete("1.0", "end")
        self._text.configure(state="disabled")

    def run(self, filepath: str) -> None:
        """Run *filepath* with the system Python interpreter."""
        if self._is_running:
            return
        self.clear()
        self.write(f"$ python {filepath}\n\n", "info")
        self._is_running = True
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        threading.Thread(target=self._run_process, args=(filepath,), daemon=True).start()

    def run_code(self, code: str, label: str = "selection") -> None:
        """Write *code* to a temp file and run it, showing output as [label]."""
        if self._is_running:
            return
        self.clear()
        self.write(f"$ python [{label}]\n\n", "info")
        self._is_running = True
        self._run_btn.configure(state="disabled")
        self._stop_btn.configure(state="normal")
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(code)
        tmp.close()
        threading.Thread(
            target=self._run_process, args=(tmp.name,), daemon=True
        ).start()

    def terminate(self) -> None:
        """Kill the running process if one is active."""
        if self._process and self._process.poll() is None:
            self._process.terminate()
            self.write("\nProcess terminated by user.\n", "warning")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _on_run_click(self) -> None:
        if self._run_callback:
            self._run_callback()

    def _run_process(self, filepath: str) -> None:
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
                    self._queue.put((line, tag))

            t_out = threading.Thread(target=_drain, args=(self._process.stdout, ""), daemon=True)
            t_err = threading.Thread(target=_drain, args=(self._process.stderr, "stderr"), daemon=True)
            t_out.start()
            t_err.start()
            t_out.join()
            t_err.join()
            self._process.wait()

            rc = self._process.returncode
            tag = "success" if rc == 0 else "stderr"
            self._queue.put((f"\nProcess finished with exit code {rc}\n", tag))
        except FileNotFoundError:
            self._queue.put(("Error: Python interpreter not found on PATH.\n", "stderr"))
        except Exception as exc:
            self._queue.put((f"Error: {exc}\n", "stderr"))
        finally:
            self._queue.put(None)  # sentinel – process is done

    def _poll(self) -> None:
        """Drain the output queue every 50 ms on the main thread."""
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._is_running = False
                    self._run_btn.configure(state="normal")
                    self._stop_btn.configure(state="disabled")
                    break
                text, tag = item
                self.write(text, tag)
        except queue.Empty:
            pass
        self.after(50, self._poll)
