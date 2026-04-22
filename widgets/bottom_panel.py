"""BottomPanel — tabbed container for OUTPUT, TERMINAL, and PROBLEMS panels."""
from __future__ import annotations

import platform
from tkinter import Frame, Label, ttk
from typing import Callable, Optional

from utils.learning_registry import LearningManager

from .debug_panel import DebugPanel
from .output import OutputPanel
from .problems_panel import ProblemsPanel
from .terminal import TerminalPanel


class BottomPanel(ttk.Frame):
    """Tabbed bottom panel with OUTPUT, TERMINAL, PROBLEMS, and DEBUG tabs.

    Exposes the same public API as OutputPanel (run / terminate / clear)
    so the rest of the app doesn't need to know about the internal split.
    """

    _BG         = "#1e1e1e"
    _TAB_BG     = "#252526"
    _TAB_FG     = "#8a8a8a"
    _TAB_FG_ACT = "#ffffff"
    _INDICATOR  = "#007acc"   # blue underline on active tab

    def __init__(
        self,
        master,
        on_run_start: Optional[Callable[[], None]] = None,
        on_run_done: Optional[Callable[[], None]] = None,
        cwd: Optional[str] = None,
        on_navigate: Optional[Callable[[str, int, int], None]] = None,
        on_bp_click: Optional[Callable[[str, int], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._active: str = "output"
        self._cwd = cwd
        self._cwd_after_id: Optional[str] = None
        self._terminal_first_show: bool = True
        self._on_navigate = on_navigate or (lambda *_: None)

        self._build_tab_bar()

        # ── Panels ────────────────────────────────────────────────────────────
        self.output   = OutputPanel(self, on_run_start=on_run_start, on_run_done=on_run_done)
        self.terminal = TerminalPanel(self)
        self.problems = ProblemsPanel(self, on_navigate=self._on_navigate)
        self.debug    = DebugPanel(
            self,
            on_breakpoint_click=on_bp_click or (lambda *_: None),
        )

        self.output.pack(fill="both", expand=True)
        # terminal, problems, and debug start hidden

        self._set_active("output")

    # ── Public API (mirrors OutputPanel) ──────────────────────────────────────

    def run(self, filepath: str) -> None:
        self._set_active("output")
        self.output.run(filepath)

    def run_code(self, code: str, label: str = "selection") -> None:
        self._set_active("output")
        self.output.run_code(code, label)

    def terminate(self) -> None:
        self.output.terminate()

    def clear(self) -> None:
        if self._active == "output":
            self.output.clear()
        elif self._active == "terminal":
            self.terminal.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        bar = Frame(self, bg=self._TAB_BG, height=28)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        self._tabs: dict[str, dict] = {}
        for key, label in (
            ("output", "OUTPUT"),
            ("terminal", "TERMINAL"),
            ("problems", "PROBLEMS"),
            ("debug", "DEBUG"),
        ):
            self._tabs[key] = self._make_tab(bar, key, label)
        self.output_tab_btn   = self._tabs["output"]["container"]
        self.output_tab_lbl   = self._tabs["output"]["label"]
        self.terminal_tab_btn = self._tabs["terminal"]["container"]
        self.terminal_tab_lbl = self._tabs["terminal"]["label"]
        self.problems_tab_btn = self._tabs["problems"]["container"]
        self.problems_tab_lbl = self._tabs["problems"]["label"]
        self.debug_tab_btn    = self._tabs["debug"]["container"]
        self.debug_tab_lbl    = self._tabs["debug"]["label"]

    def _make_tab(self, bar: Frame, key: str, label: str) -> dict:
        """Create a single tab button and return references to its widgets."""
        container = Frame(bar, bg=self._TAB_BG, padx=12, pady=0)
        container.pack(side="left")

        lbl = Label(
            container,
            text=label,
            bg=self._TAB_BG,
            fg=self._TAB_FG,
            font=("Segoe UI", 8, "bold"),
            cursor="hand2",
            pady=6,
        )
        lbl.pack(side="top")

        # Active indicator line (shown only for active tab)
        indicator = Frame(container, bg=self._INDICATOR, height=2)
        # Not packed initially

        def _on_click(k=key):
            if LearningManager.is_active():
                LearningManager.fire_click(container)
                return
            self._set_active(k)
        for widget in (container, lbl):
            widget.bind("<Button-1>", lambda _, fn=_on_click: fn())

        return {"container": container, "label": lbl, "indicator": indicator}

    def set_cwd(self, cwd: str) -> None:
        """Update the working directory; debounced cd to a running terminal."""
        self._cwd = cwd
        self.terminal._cwd = cwd  # keep terminal in sync for restarts
        # Debounce: cancel any pending cd and schedule a new one
        if self._cwd_after_id is not None:
            self.after_cancel(self._cwd_after_id)
        self._cwd_after_id = self.after(250, self._apply_cwd)

    def _apply_cwd(self) -> None:
        self._cwd_after_id = None
        if self._active == "terminal" and self.terminal._running and self._cwd:
            self.terminal.send_text(f'cd "{self._cwd}"\r')

    def update_problems(self, entries: list[dict]) -> None:
        """Push fresh diagnostics to the Problems panel and update the tab badge."""
        self.problems.update(entries)
        errors   = sum(1 for e in entries if e.get("severity") == 1)
        warnings = sum(1 for e in entries if e.get("severity") == 2)
        parts = []
        if errors:
            parts.append(f"✕{errors}")
        if warnings:
            parts.append(f"⚠{warnings}")
        badge = "  " + "  ".join(parts) if parts else ""
        self._tabs["problems"]["label"].config(text=f"PROBLEMS{badge}")

    def _set_active(self, key: str) -> None:
        # Update tab styling
        for k, tab in self._tabs.items():
            active = k == key
            tab["label"].config(fg=self._TAB_FG_ACT if active else self._TAB_FG)
            if active:
                tab["indicator"].pack(side="bottom", fill="x")
            else:
                tab["indicator"].pack_forget()

        # Hide all panels then show the selected one
        for panel in (self.output, self.terminal, self.problems, self.debug):
            panel.pack_forget()

        if key == "output":
            self.output.pack(fill="both", expand=True)
        elif key == "terminal":
            self.terminal.pack(fill="both", expand=True)
            if not self.terminal._running:
                self.terminal.start(cwd=self._cwd)
            if self._terminal_first_show:
                self._terminal_first_show = False
                if platform.system() == "Windows":
                    # After resize settles, Ctrl+L makes PSReadLine redraw the prompt
                    # cleanly from (0,0) — fixes missing prompt on first keypress.
                    self.terminal.after(200, lambda: self.terminal.send_text("\x0c"))
                else:
                    self.terminal.after(50, lambda: self.terminal._text.yview_moveto(0))
        elif key == "problems":
            self.problems.pack(fill="both", expand=True)
        else:  # debug
            self.debug.pack(fill="both", expand=True)

        self._active = key
