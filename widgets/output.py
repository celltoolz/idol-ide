from __future__ import annotations

import queue
import re
import tempfile
import tkinter as tk
from tkinter import Entry, Frame, Label, Text, ttk
from typing import Callable, Optional

_TRACEBACK_RE = re.compile(r'File "([^"]+)", line (\d+)')

_GUIDE_FG     = "#f1fa8c"   # amber — stands out from the dim Clear button
_GUIDE_FG_HOV = "#ffffff"

from editor.script_runner import ScriptRunner


class OutputPanel(ttk.Frame):
    """Terminal-style output panel for running Python files.

    Runs the subprocess in a background thread and pumps output into a queue
    that is drained every 50 ms on the main thread (safe for tkinter).

    An inline stdin bar appears at the bottom while a process is running,
    allowing input() calls to be answered without switching to the terminal.

    Usage:
        panel.run(filepath)   – run a file
        panel.terminate()     – kill the running process
        panel.clear()         – clear the text area
    """

    _BG       = "#1e1e1e"
    _FG       = "#f8f8f2"
    _BAR_BG   = "#252526"
    _INPUT_BG = "#3c3c3c"
    _STDIN_FG = "#9cdcfe"   # light-blue echo for typed input

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
        self.on_runtime_error: Optional[Callable[[str, int], None]] = None

        self._build_ui()
        self._poll()

    def _build_ui(self) -> None:
        # Grid layout: row 0 = text (expands), row 1 = stdin bar.
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # ── Text area ─────────────────────────────────────────────────────────
        text_frame = ttk.Frame(self)
        text_frame.grid(row=0, column=0, sticky="nsew")
        text_frame.grid_rowconfigure(0, weight=1)
        text_frame.grid_columnconfigure(0, weight=1)

        self._text = Text(
            text_frame,
            bg=self._BG, fg=self._FG,
            font=("Consolas", 10),
            state="disabled",
            wrap="word",
            relief="flat",
            borderwidth=0,
            insertbackground=self._FG,
        )
        vs = ttk.Scrollbar(text_frame, orient="vertical", command=self._text.yview)
        self._text.configure(yscrollcommand=vs.set)
        self._text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")

        self._text.tag_configure("stderr",  foreground="#ff5555")
        self._text.tag_configure("info",    foreground="#6272a4")
        self._text.tag_configure("success", foreground="#50fa7b")
        self._text.tag_configure("warning", foreground="#f1fa8c")
        self._text.tag_configure("stdin",   foreground=self._STDIN_FG)

        self._text.bind("<Button-3>", self._show_ctx)
        self._text.bind("<Button-2>", self._show_ctx)  # macOS two-finger tap

        # ── Stdin input bar ────────────────────────────────────────────────
        self._stdin_bar = Frame(self, bg=self._BAR_BG)
        self._stdin_bar.grid(row=1, column=0, sticky="ew")
        self._stdin_bar.grid_remove()   # hidden until a process runs

        Label(
            self._stdin_bar,
            text=" > ",
            bg=self._BAR_BG,
            fg=self._STDIN_FG,
            font=("Consolas", 10, "bold"),
        ).pack(side="left")

        self._stdin_entry = Entry(
            self._stdin_bar,
            bg=self._INPUT_BG,
            fg=self._FG,
            insertbackground=self._FG,
            relief="flat",
            font=("Consolas", 10),
            bd=4,
        )
        self._stdin_entry.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=4)
        self._stdin_entry.bind("<Return>",   self._on_stdin_submit)
        self._stdin_entry.bind("<KP_Enter>", self._on_stdin_submit)

    def build_tab_controls(self, parent) -> None:
        """Populate *parent* (the tab bar slot) with output-specific controls."""
        # Guide button — surfaced only when input() is detected in a debug session
        self._guide_btn = Label(
            parent, text="? input() & Debug",
            bg="#252526", fg=_GUIDE_FG,
            font=("Segoe UI", 8), cursor="hand2", pady=6, padx=6,
        )
        self._guide_btn.bind("<Button-1>", lambda _: self._open_debug_guide())
        self._guide_btn.bind("<Enter>", lambda _: self._guide_btn.config(fg=_GUIDE_FG_HOV))
        self._guide_btn.bind("<Leave>", lambda _: self._guide_btn.config(fg=_GUIDE_FG))
        # Not packed yet — shown via show_debug_input_guide_btn()

        self._copy_btn = Label(
            parent, text="⎘ Copy",
            bg="#252526", fg="#8a8a8a",
            font=("Segoe UI", 8), cursor="hand2", pady=6, padx=6,
        )
        self._copy_btn.pack(side="left")
        self._copy_btn.bind("<Button-1>", lambda _: self._copy_all())
        self._copy_btn.bind("<Enter>", lambda _: self._copy_btn.config(fg="#ffffff"))
        self._copy_btn.bind("<Leave>", lambda _: self._copy_btn.config(fg="#8a8a8a"))

        self._clear_btn = Label(
            parent, text="✕ Clear",
            bg="#252526", fg="#8a8a8a",
            font=("Segoe UI", 8), cursor="hand2", pady=6, padx=6,
        )
        self._clear_btn.pack(side="left")
        self._clear_btn.bind("<Button-1>", lambda _: self.clear())
        self._clear_btn.bind("<Enter>", lambda _: self._clear_btn.config(fg="#ffffff"))
        self._clear_btn.bind("<Leave>", lambda _: self._clear_btn.config(fg="#8a8a8a"))

    def show_debug_input_guide_btn(self, switch_fn: Callable) -> None:
        """Show the input() guide button to the left of Clear."""
        self._guide_switch_fn = switch_fn
        if hasattr(self, "_guide_btn"):
            self._guide_btn.pack(side="left", before=self._clear_btn)

    def hide_debug_input_guide_btn(self) -> None:
        """Hide the input() guide button (called on session end)."""
        if hasattr(self, "_guide_btn"):
            self._guide_btn.pack_forget()

    def _open_debug_guide(self) -> None:
        from utils.debug_input_guide import make_pages
        from widgets.guide_window import GuideWindow
        self.update_idletasks()
        w, h = 400, 440
        x = self.winfo_rootx()
        y = max(0, self.winfo_rooty() - h - 10)
        win = GuideWindow(
            self.winfo_toplevel(),
            "input() & Debug",
            make_pages(getattr(self, "_guide_switch_fn", None) or (lambda: None)),
            width=w,
            height=h,
        )
        win.geometry(f"{w}x{h}+{x}+{y}")

    # ── Copy helpers ──────────────────────────────────────────────────────────

    def _copy_all(self) -> None:
        text = self._text.get("1.0", "end-1c")
        if text:
            self.clipboard_clear()
            self.clipboard_append(text)

    def _copy_selection(self) -> None:
        try:
            text = self._text.get(tk.SEL_FIRST, tk.SEL_LAST)
            if text:
                self.clipboard_clear()
                self.clipboard_append(text)
        except tk.TclError:
            pass  # no selection — do nothing

    def _show_ctx(self, event) -> None:
        has_sel = bool(self._text.tag_ranges(tk.SEL))
        items = [
            ("Copy Selection", self._copy_selection, has_sel),
            ("Copy All",       self._copy_all,       True),
        ]
        self._show_overlay(event.x_root, event.y_root, items)

    def _show_overlay(self, x_root: int, y_root: int, items: list) -> None:
        existing = getattr(self, "_ctx_overlay", None)
        if existing:
            try:
                existing.destroy()
            except Exception:
                pass
        self._ctx_overlay = None

        top = self.winfo_toplevel()
        rel_x = x_root - top.winfo_rootx()
        rel_y = y_root - top.winfo_rooty()

        overlay = tk.Frame(top, bg="#2d2d2d",
                           highlightthickness=1, highlightbackground="#007acc")
        self._ctx_overlay = overlay

        bid: list = []

        def _dismiss():
            self._ctx_overlay = None
            try:
                overlay.destroy()
            except Exception:
                pass
            if bid:
                try:
                    top.unbind("<Button-1>", bid[0])
                except Exception:
                    pass

        def _global_click(e):
            w = e.widget
            while w is not None:
                if w is overlay:
                    return
                try:
                    w = w.master
                except AttributeError:
                    break
            _dismiss()

        for label, cmd, enabled in items:
            fg = "#cccccc" if enabled else "#555555"
            lbl = tk.Label(overlay, text=label, bg="#2d2d2d", fg=fg,
                           font=("Segoe UI", 9), anchor="w", padx=12, pady=3)
            lbl.pack(fill="x")
            if enabled:
                def _enter(e, l=lbl):  l.config(bg="#094771", fg="#ffffff")
                def _leave(e, l=lbl):  l.config(bg="#2d2d2d", fg="#cccccc")
                def _click(e, c=cmd):
                    _dismiss()
                    c()
                lbl.bind("<Enter>",    _enter)
                lbl.bind("<Leave>",    _leave)
                lbl.bind("<Button-1>", _click)

        overlay.place(x=rel_x, y=rel_y)
        overlay.lift()
        bid.append(top.bind("<Button-1>", _global_click, add=True))

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

    def run(self, filepath: str, python_path: str = "python") -> None:
        """Run *filepath* with *python_path*."""
        if self._is_running:
            return
        self.clear()
        self.write(f"$ python {filepath}\n\n", "info")
        self._start_run()
        self._runner.run(filepath, python_path)

    def run_code(self, code: str, label: str = "selection", python_path: str = "python") -> None:
        """Write *code* to a temp file and run it, showing output as [label]."""
        if self._is_running:
            return
        self.clear()
        self.write(f"$ python [{label}]\n\n", "info")
        self._start_run()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(code)
        tmp.close()
        self._runner.run(tmp.name, python_path)

    def terminate(self) -> None:
        """Kill the running process if one is active."""
        if self._runner.stop():
            self.write("\nProcess terminated by user.\n", "warning")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _start_run(self) -> None:
        self._is_running = True
        self._stdin_bar.grid()          # restore to row 3
        self._stdin_entry.delete(0, "end")
        self._stdin_entry.focus_set()
        if self._on_run_start:
            self._on_run_start()

    def _finish_run(self) -> None:
        self._is_running = False
        self._stdin_bar.grid_remove()   # hide without losing grid config
        if self._on_run_done:
            self._on_run_done()
        if self.on_runtime_error:
            self._try_fire_runtime_error()

    def _try_fire_runtime_error(self) -> None:
        """Parse the output for a Python traceback and fire on_runtime_error."""
        text = self._text.get("1.0", "end")
        if "exit code 0" in text:
            return
        matches = _TRACEBACK_RE.findall(text)
        if not matches:
            return
        filepath, lineno_str = matches[-1]
        try:
            self.on_runtime_error(filepath, int(lineno_str))
        except Exception:
            pass

    def _on_stdin_submit(self, _=None) -> None:
        text = self._stdin_entry.get()
        self._stdin_entry.delete(0, "end")
        self.write(text + "\n", "stdin")
        self._runner.send_input(text + "\n")

    def _poll(self) -> None:
        """Drain the output queue every 50 ms on the main thread."""
        try:
            while True:
                item = self._queue.get_nowait()
                if item is None:
                    self._finish_run()
                    break
                text, tag = item
                self.write(text, tag)
        except queue.Empty:
            pass
        self.after(50, self._poll)
