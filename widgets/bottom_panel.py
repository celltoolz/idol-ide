"""BottomPanel — tabbed container for OUTPUT and TERMINAL panels."""
from __future__ import annotations

from tkinter import Frame, Label, ttk
from typing import Callable, Optional

from .output import OutputPanel
from .terminal import TerminalPanel


class BottomPanel(ttk.Frame):
    """Tabbed bottom panel with OUTPUT and TERMINAL tabs.

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
        run_callback: Optional[Callable[[], None]] = None,
        cwd: Optional[str] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._active: str = "output"
        self._cwd = cwd
        self._cwd_after_id: Optional[str] = None

        self._build_tab_bar()

        # ── Panels ────────────────────────────────────────────────────────────
        self.output   = OutputPanel(self,  run_callback=run_callback)
        self.terminal = TerminalPanel(self)

        self.output.pack(fill="both", expand=True)
        # terminal starts hidden

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
        else:
            self.terminal.clear()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        bar = Frame(self, bg=self._TAB_BG, height=28)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        self._tabs: dict[str, dict] = {}
        for key, label in (("output", "OUTPUT"), ("terminal", "TERMINAL")):
            tab = self._make_tab(bar, key, label)
            self._tabs[key] = tab
        self.output_tab_btn   = self._tabs["output"]["container"]
        self.terminal_tab_btn = self._tabs["terminal"]["container"]

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

        for widget in (container, lbl):
            widget.bind("<Button-1>", lambda _, k=key: self._set_active(k))

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

    def _set_active(self, key: str) -> None:
        # Update tab styling
        for k, tab in self._tabs.items():
            active = k == key
            tab["label"].config(fg=self._TAB_FG_ACT if active else self._TAB_FG)
            if active:
                tab["indicator"].pack(side="bottom", fill="x")
            else:
                tab["indicator"].pack_forget()

        # Swap visible panel — start terminal with cwd on first show
        if key == "output":
            self.terminal.pack_forget()
            self.output.pack(fill="both", expand=True)
        else:
            self.output.pack_forget()
            self.terminal.pack(fill="both", expand=True)
            if not self.terminal._running:
                self.terminal.start(cwd=self._cwd)

        self._active = key
