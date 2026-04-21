from __future__ import annotations

import queue
import tempfile
from tkinter import Text, ttk
from typing import Callable, Optional

from editor.script_runner import ScriptRunner


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
        on_run_start: Optional[Callable[[], None]] = None,
        on_run_done: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_run_start = on_run_start
        self._on_run_done = on_run_done
        self._queue: queue.Queue = queue.Queue()
        self._runner = ScriptRunner(on_output=self._queue.put)
        self._is_running = False

        self._build_ui()
        self._poll()

    def _build_ui(self) -> None:
        # ── Header label ──────────────────────────────────────────────────────
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", side="top", pady=(2, 0), padx=4)
        ttk.Label(toolbar, text="OUTPUT", font=("TkDefaultFont", 8, "bold")).pack(side="left")
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
        if self._on_run_start:
            self._on_run_start()
        self._runner.run(filepath)

    def run_code(self, code: str, label: str = "selection") -> None:
        """Write *code* to a temp file and run it, showing output as [label]."""
        if self._is_running:
            return
        self.clear()
        self.write(f"$ python [{label}]\n\n", "info")
        self._is_running = True
        if self._on_run_start:
            self._on_run_start()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(code)
        tmp.close()
        self._runner.run(tmp.name)

    def terminate(self) -> None:
        """Kill the running process if one is active."""
        if self._runner.stop():
            self.write("\nProcess terminated by user.\n", "warning")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _poll(self) -> None:
        """Drain the output queue every 50 ms on the main thread."""
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._is_running = False
                    if self._on_run_done:
                        self._on_run_done()
                    break
                text, tag = item
                self.write(text, tag)
        except queue.Empty:
            pass
        self.after(50, self._poll)
