from __future__ import annotations

import os
import queue
import re
import tempfile
import tkinter as tk
import traceback as _traceback
from tkinter import Entry, Frame, Label, Text, ttk
from typing import Callable, Optional
from utils import missing_module as _missing_module
from utils.thread_safe_after import rearm_after
from utils.ui_font import UI_FONT
from widgets.scrollbar import VerticalScrollbar

_TRACEBACK_RE = re.compile(r'File "([^"]+)", line (\d+)')
_OFFER_TAG    = "install_offer"

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
        #: Where the current run considers "the project" — used to tell the
        #: user's own frames from a dependency's when picking which one to
        #: jump to. Normcased absolute, or "" before the first run.
        self._run_root: str = ""
        self.on_runtime_error: Optional[Callable[[str, int], None]] = None
        #: Host hooks for the missing-module offer. `resolve_missing_module`
        #: maps an import name to (package, backend) for the *active*
        #: interpreter — only the app knows which that is — and returns None to
        #: decline the offer; `on_install_module` performs the install.
        self.resolve_missing_module: Optional[
            Callable[[str], "tuple[str, str] | None"]] = None
        self.on_install_module: Optional[Callable[[str], None]] = None

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
        vs = VerticalScrollbar(text_frame, command=self._text.yview)
        self._text.configure(yscrollcommand=vs.set)
        self._text.grid(row=0, column=0, sticky="nsew")
        vs.grid(row=0, column=1, sticky="ns")

        self._text.tag_configure("stderr",  foreground="#ff5555")
        self._text.tag_configure("info",    foreground="#6272a4")
        self._text.tag_configure("success", foreground="#50fa7b")
        self._text.tag_configure("warning", foreground="#f1fa8c")
        self._text.tag_configure("stdin",   foreground=self._STDIN_FG)
        self._text.tag_configure(_OFFER_TAG, foreground="#73c991",
                                 underline=True)

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
            font=(UI_FONT, 8), cursor="hand2", pady=6, padx=6,
        )
        self._guide_btn.bind("<Button-1>", lambda _: self._open_debug_guide())
        self._guide_btn.bind("<Enter>", lambda _: self._guide_btn.config(fg=_GUIDE_FG_HOV))
        self._guide_btn.bind("<Leave>", lambda _: self._guide_btn.config(fg=_GUIDE_FG))
        # Not packed yet — shown via show_debug_input_guide_btn()

        self._copy_btn = Label(
            parent, text="⎘ Copy",
            bg="#252526", fg="#8a8a8a",
            font=(UI_FONT, 8), cursor="hand2", pady=6, padx=6,
        )
        self._copy_btn.pack(side="left")
        self._copy_btn.bind("<Button-1>", lambda _: self._copy_all())
        self._copy_btn.bind("<Enter>", lambda _: self._copy_btn.config(fg="#ffffff"))
        self._copy_btn.bind("<Leave>", lambda _: self._copy_btn.config(fg="#8a8a8a"))

        self._clear_btn = Label(
            parent, text="✕ Clear",
            bg="#252526", fg="#8a8a8a",
            font=(UI_FONT, 8), cursor="hand2", pady=6, padx=6,
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
                           font=(UI_FONT, 9), anchor="w", padx=12, pady=3)
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

    def run(
        self, filepath: str, python_path: str = "python", cwd: str | None = None
    ) -> None:
        """Run *filepath* with *python_path* in working directory *cwd*."""
        if self._is_running:
            return
        self.clear()
        if cwd:
            self.write(f"$ cd {cwd}\n", "info")
        self.write(f"$ python {filepath}\n\n", "info")
        self._set_run_root(cwd, filepath)
        self._start_run()
        self._runner.run(filepath, python_path, cwd)

    def run_code(
        self,
        code: str,
        label: str = "selection",
        python_path: str = "python",
        cwd: str | None = None,
    ) -> None:
        """Write *code* to a temp file and run it, showing output as [label]."""
        if self._is_running:
            return
        self.clear()
        if cwd:
            self.write(f"$ cd {cwd}\n", "info")
        self.write(f"$ python [{label}]\n\n", "info")
        self._start_run()
        tmp = tempfile.NamedTemporaryFile(
            mode="w", suffix=".py", delete=False, encoding="utf-8"
        )
        tmp.write(code)
        tmp.close()
        # The scratch file, not *cwd* — a run-selection buffer lives in the
        # system temp dir, so scoping to the project would rule out the only
        # frame that is actually the user's code.
        self._set_run_root(os.path.dirname(tmp.name), tmp.name)
        self._runner.run(tmp.name, python_path, cwd)

    def terminate(self) -> None:
        """Kill the running process if one is active."""
        if self._runner.stop():
            self.write("\nProcess terminated by user.\n", "warning")

    # ── Internals ─────────────────────────────────────────────────────────────

    def _set_run_root(self, cwd: str | None, filepath: str) -> None:
        """Record the boundary between the user's code and everything else.

        The run cwd when there is one — `app._compute_run_cwd` makes that the
        project root or the script's directory — and the script's own folder
        otherwise, which is the legacy inherit-IDOL's-cwd case where the
        project root is not knowable from here.
        """
        base = cwd or os.path.dirname(os.path.abspath(filepath))
        self._run_root = os.path.normcase(os.path.abspath(base))

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
        self._offer_missing_module()

    def _try_fire_runtime_error(self) -> None:
        """Parse the output for a Python traceback and fire on_runtime_error.

        The success check reads the process's actual exit status rather than
        searching the buffer for "exit code 0". That string is only in the
        buffer because `script_runner` writes it there, and this panel is
        written to by things that are not runs at all — the Package Manager
        streams pip and conda output through it without clearing first. A
        program that merely *prints* "exit code 0" was enough to suppress the
        indicator for its own crash.
        """
        if self._runner.returncode == 0:
            return
        matches = _TRACEBACK_RE.findall(self._text.get("1.0", "end"))
        frame = self._pick_error_frame(matches)
        if frame is None:
            return
        filepath, lineno = frame
        try:
            self.on_runtime_error(filepath, lineno)
        except Exception as exc:
            # Swallowing this is what made the last report of a non-firing
            # indicator undiagnosable: a stale path, or _open_file_at raising,
            # looked exactly like "no traceback found". Name it in the panel
            # and keep the detail for whoever launched IDOL from a terminal.
            _traceback.print_exc()
            self.write(f"\n(could not open the error location: {exc})\n", "info")

    # ── Missing-module offer ──────────────────────────────────────────────────

    def _offer_missing_module(self) -> None:
        """Turn `No module named 'X'` into something the user can act on.

        Nothing else in IDOL can catch this. Ruff never resolves imports and
        `compile()` never executes them, so a missing dependency is invisible
        until the run — which makes the run output the right and only place to
        notice it. See the Problems-panel note in TODO.md.
        """
        if self._runner.returncode == 0:
            return
        module = _missing_module.parse(self._text.get("1.0", "end"))
        if not module:
            return
        if _missing_module.is_stdlib(module):
            top = module.split(".")[0]
            self.write(
                f"\n'{top}' is part of the Python standard library, so no "
                f"package will supply it — this interpreter was built without "
                f"it. On Linux that is usually a separate system package.\n",
                "warning")
            return
        if not (self.resolve_missing_module and self.on_install_module):
            return
        resolved = self.resolve_missing_module(module)
        if not resolved:
            return
        self._write_install_offer(module, *resolved)

    def _write_install_offer(self, module: str, package: str,
                             backend: str) -> None:
        self._text.configure(state="normal")
        start = self._text.index("end-1c")
        self._text.insert("end", f"\n  ⬇ Install '{package}' with {backend}",
                          _OFFER_TAG)
        end = self._text.index("end-1c")
        # Only worth explaining when the two names differ — which is the whole
        # reason the offer names a package rather than echoing the import.
        if package.lower() != module.lower():
            self._text.insert(
                "end", f"     ({module} comes from the {package} package)",
                "info")
        self._text.insert("end", "\n")
        self._text.tag_add(_OFFER_TAG, start, end)
        self._text.tag_raise(_OFFER_TAG)
        self._text.configure(state="disabled")
        self._text.see("end")

        def _click(_e=None):
            # One offer per run: re-clicking mid-install would start a second.
            self._text.tag_remove(_OFFER_TAG, "1.0", "end")
            self._text.configure(cursor="")
            if self.on_install_module:
                self.on_install_module(package)

        self._text.tag_unbind(_OFFER_TAG, "<ButtonRelease-1>")
        self._text.tag_bind(_OFFER_TAG, "<ButtonRelease-1>", _click)
        self._text.tag_bind(_OFFER_TAG, "<Enter>",
                            lambda _e: self._text.configure(cursor="hand2"))
        self._text.tag_bind(_OFFER_TAG, "<Leave>",
                            lambda _e: self._text.configure(cursor=""))

    def _pick_error_frame(self, matches) -> "tuple[str, int] | None":
        """Choose which traceback frame to jump to.

        The innermost frame — `matches[-1]` — is the wrong answer twice over.
        An exception raised *inside* a dependency ends in `site-packages`, so
        IDOL opened a library file instead of the code that called it; and a
        chained traceback ("During handling of the above exception…") ends in
        whichever exception was re-raised last, which may be nothing to do
        with where the run actually went wrong.

        Innermost frame that is the user's own code, then. Frames whose file
        no longer exists are skipped entirely rather than merely deprioritised
        — jumping to a path that is gone is the failure the caller can do
        least with.
        """
        frames: list[tuple[str, int]] = []
        for path, lineno in matches:
            try:
                n = int(lineno)
            except ValueError:
                continue
            if os.path.isfile(path):
                frames.append((path, n))
        if not frames:
            return None
        if self._run_root:
            for path, n in reversed(frames):
                if self._is_under_run_root(path):
                    return path, n
        # Nothing in the project: the innermost real file still beats nothing.
        return frames[-1]

    def _is_under_run_root(self, path: str) -> bool:
        try:
            common = os.path.commonpath(
                [os.path.normcase(os.path.abspath(path)), self._run_root])
        except ValueError:
            return False        # different drives on Windows
        return common == self._run_root

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
        rearm_after(self, 50, self._poll)
