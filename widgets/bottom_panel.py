"""BottomPanel — tabbed container for OUTPUT, TERMINAL, PROBLEMS, and DEBUG panels."""
from __future__ import annotations

import platform
import tkinter as tk
from tkinter import Frame, Label, ttk
from typing import Callable, Optional

from widgets.learning_manager import LearningManager

from .debug_panel import DebugPanel
from .output import OutputPanel
from .problems_panel import ProblemsPanel
from .terminal import TerminalPanel
from utils.ui_font import UI_FONT


class _Tooltip:
    """Lightweight hover tooltip — appears after 500 ms, destroyed on leave."""

    def __init__(self, widget, text: str) -> None:
        self._widget  = widget
        self._text    = text
        self._win     = None
        self._job     = None
        widget.bind("<Enter>", self._schedule, add=True)
        widget.bind("<Leave>", self._hide,     add=True)

    def _schedule(self, _=None) -> None:
        self._job = self._widget.after(500, self._show)

    def _show(self, _=None) -> None:
        if self._win:
            return
        x = self._widget.winfo_rootx() + 10
        y = self._widget.winfo_rooty() + self._widget.winfo_height() + 4
        self._win = tw = tk.Toplevel(self._widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        Label(
            tw, text=self._text,
            bg="#252526", fg="#cccccc",
            font=(UI_FONT, 8), relief="solid", bd=1,
            padx=6, pady=3,
        ).pack()

    def _hide(self, _=None) -> None:
        if self._job:
            try:
                self._widget.after_cancel(self._job)
            except Exception:
                pass
            self._job = None
        if self._win:
            self._win.destroy()
            self._win = None


class DebugFloatWindow(tk.Toplevel):
    """Floating debug panel that can be docked back into the editor."""

    _BG         = "#1e1e1e"
    _BAR_BG     = "#252526"
    _TAB_FG     = "#8a8a8a"
    _TAB_FG_ACT = "#ffffff"
    _BLUE       = "#007acc"

    def __init__(
        self,
        master,
        on_dock: Callable,
        on_bp_click: Callable,
        **kwargs,
    ) -> None:
        super().__init__(master, bg=self._BG, **kwargs)
        self.title("Debug — IDOL")
        self.geometry("700x350")
        self.minsize(400, 200)
        self._on_dock = on_dock
        self._topmost = False

        self._build_toolbar()
        self.panel = DebugPanel(self, on_breakpoint_click=on_bp_click)
        self.panel.pack(fill="both", expand=True)

        self.protocol("WM_DELETE_WINDOW", on_dock)

    def _build_toolbar(self) -> None:
        bar = Frame(self, bg=self._BAR_BG, height=28)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        Label(
            bar, text="DEBUG",
            bg=self._BAR_BG, fg=self._TAB_FG_ACT,
            font=(UI_FONT, 8, "bold"), pady=6,
        ).pack(side="left", padx=10)

        # ── Right-side controls ───────────────────────────────────────────────
        self._pin_lbl = Label(
            bar, text="📌",
            bg=self._BAR_BG, fg=self._TAB_FG,
            cursor="hand2", font=(UI_FONT, 10), pady=6,
        )
        self._pin_lbl.pack(side="right", padx=(0, 8))
        self._pin_lbl.bind("<Button-1>", lambda _: self._toggle_topmost())
        _Tooltip(self._pin_lbl, "Toggle always on top")

        Label(bar, text="|", bg=self._BAR_BG, fg="#3c3c3c", pady=6).pack(side="right")

        dock_lbl = Label(
            bar, text="⬅ Dock",
            bg=self._BAR_BG, fg=self._TAB_FG,
            cursor="hand2", font=(UI_FONT, 8), pady=6,
        )
        dock_lbl.pack(side="right", padx=(0, 8))
        dock_lbl.bind("<Button-1>", lambda _: self._on_dock())
        dock_lbl.bind("<Enter>", lambda _: dock_lbl.config(fg=self._TAB_FG_ACT))
        dock_lbl.bind("<Leave>", lambda _: dock_lbl.config(fg=self._TAB_FG))
        _Tooltip(dock_lbl, "Dock back into editor")

    def _toggle_topmost(self) -> None:
        self._topmost = not self._topmost
        self.attributes("-topmost", self._topmost)
        self._pin_lbl.config(fg=self._BLUE if self._topmost else self._TAB_FG)


class BottomPanel(ttk.Frame):
    """Tabbed bottom panel with OUTPUT, TERMINAL, PROBLEMS, and DEBUG tabs.

    Exposes the same public API as OutputPanel (run / terminate / clear)
    so the rest of the app doesn't need to know about the internal split.

    The DEBUG panel can be floated into its own window via the ⊡ button in
    the tab bar and docked back with the ⬅ Dock button on the float window.
    """

    _BG         = "#1e1e1e"
    _TAB_BG     = "#252526"
    _TAB_FG     = "#8a8a8a"
    _TAB_FG_ACT = "#ffffff"
    _INDICATOR  = "#007acc"
    _BLUE       = "#007acc"

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
        self._pending_cd: Optional[str] = None
        self._terminal_first_show: bool = True
        self._flash_job: Optional[str] = None
        self._flash_state: bool = False
        self._on_navigate  = on_navigate or (lambda *_: None)
        self._on_bp_click  = on_bp_click or (lambda *_: None)
        self.on_ask_ai_problems: Optional[Callable] = None
        self._debug_float_win: Optional[DebugFloatWindow] = None
        self._active_ctrls: Optional[Frame] = None

        self._build_tab_bar()

        # ── Panels ────────────────────────────────────────────────────────────
        self.output      = OutputPanel(self, on_run_start=on_run_start, on_run_done=on_run_done)
        self.terminal    = TerminalPanel(self)
        self.problems    = ProblemsPanel(self, on_navigate=self._on_navigate)
        self._docked_debug = DebugPanel(
            self,
            on_breakpoint_click=self._on_bp_click,
        )

        self._build_panel_controls()

        self.output.pack(fill="both", expand=True)

        self._set_active("output")

    # ── debug property — always returns the currently active debug panel ──────

    @property
    def debug(self) -> DebugPanel:
        if self._debug_float_win is not None:
            return self._debug_float_win.panel
        return self._docked_debug

    # ── Public API (mirrors OutputPanel) ─────────────────────────────────────

    def run(self, filepath: str, python_path: str = "python") -> None:
        self._set_active("output")
        self.output.run(filepath, python_path)

    def run_code(self, code: str, label: str = "selection", python_path: str = "python") -> None:
        self._set_active("output")
        self.output.run_code(code, label, python_path)

    def terminate(self) -> None:
        self.output.terminate()

    def clear(self) -> None:
        if self._active == "output":
            self.output.clear()
        elif self._active == "terminal":
            self.terminal.clear()

    # ── Internal ─────────────────────────────────────────────────────────────

    def _build_tab_bar(self) -> None:
        bar = Frame(self, bg=self._TAB_BG, height=28)
        bar.pack(fill="x", side="top")
        bar.pack_propagate(False)

        # ── Right-side control slot — filled per-panel in _build_panel_controls ──
        self._ctrl_slot = Frame(bar, bg=self._TAB_BG)
        self._ctrl_slot.pack(side="right", fill="y")

        self._tabs: dict[str, dict] = {}
        for key, label in (
            ("output",   "OUTPUT"),
            ("terminal", "TERMINAL"),
            ("problems", "PROBLEMS"),
            ("debug",    "DEBUG"),
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
        container = Frame(bar, bg=self._TAB_BG, padx=12, pady=0)
        container.pack(side="left")

        lbl = Label(
            container,
            text=label,
            bg=self._TAB_BG,
            fg=self._TAB_FG,
            font=(UI_FONT, 8, "bold"),
            cursor="hand2",
            pady=6,
        )
        lbl.pack(side="top")

        indicator = Frame(container, bg=self._INDICATOR, height=2)

        def _on_click(k=key):
            if LearningManager.is_active():
                LearningManager.fire_click(container)
                return
            # Clicking DEBUG tab while panel is floating docks it back
            if k == "debug" and self._debug_float_win is not None:
                self._dock_debug_back()
                return
            self._set_active(k)
        for widget in (container, lbl):
            widget.bind("<Button-1>", lambda _, fn=_on_click: fn())

        return {"container": container, "label": lbl, "indicator": indicator}

    def _build_panel_controls(self) -> None:
        """Create per-panel control frames inside the tab bar slot."""
        # ── Output ────────────────────────────────────────────────────────────
        self._output_ctrls = Frame(self._ctrl_slot, bg=self._TAB_BG)
        self.output.build_tab_controls(self._output_ctrls)

        # ── Terminal ──────────────────────────────────────────────────────────
        self._terminal_ctrls = Frame(self._ctrl_slot, bg=self._TAB_BG)
        self.terminal.build_tab_controls(self._terminal_ctrls)

        # ── Problems ──────────────────────────────────────────────────────────
        self._problems_ctrls = Frame(self._ctrl_slot, bg=self._TAB_BG)
        self._ask_ai_btn = Label(
            self._problems_ctrls, text="✦ Ask AI",
            bg=self._TAB_BG, fg="#c586c0",
            font=(UI_FONT, 8), cursor="hand2", pady=6, padx=6,
        )
        self._ask_ai_btn.bind("<Button-1>", lambda _: self._fire_ask_ai())
        self._ask_ai_btn.bind("<Enter>", lambda _: self._ask_ai_btn.config(fg="#e0a0f0"))
        self._ask_ai_btn.bind("<Leave>", lambda _: self._ask_ai_btn.config(fg="#c586c0"))

        # ── Debug — pop-out button ────────────────────────────────────────────
        self._debug_ctrls = Frame(self._ctrl_slot, bg=self._TAB_BG)
        self._popout_lbl = Label(
            self._debug_ctrls, text="⊡",
            bg=self._TAB_BG, fg=self._TAB_FG,
            cursor="hand2", font=(UI_FONT, 11), pady=4, padx=8,
        )
        self._popout_lbl.pack(side="left")
        self._popout_lbl.bind("<Button-1>", lambda _: self._toggle_debug_float())
        _Tooltip(self._popout_lbl, "Float debug panel")

        self._panel_ctrls = {
            "output":   self._output_ctrls,
            "terminal": self._terminal_ctrls,
            "problems": self._problems_ctrls,
            "debug":    self._debug_ctrls,
        }

    # ── Debug float / dock ────────────────────────────────────────────────────

    def _toggle_debug_float(self) -> None:
        if self._debug_float_win is not None:
            self._dock_debug_back()
        else:
            self._pop_debug_out()

    def _pop_debug_out(self) -> None:
        if self._debug_float_win is not None:
            return
        # Switch away from debug tab before hiding it (hides debug ctrls too)
        if self._active == "debug":
            self._set_active("output")

        self._debug_float_win = DebugFloatWindow(
            self,
            on_dock=self._dock_debug_back,
            on_bp_click=self._on_bp_click,
        )
        self._debug_float_win.panel.sync_from(self._docked_debug)

        # Hide the DEBUG tab from the bar while floating
        self._tabs["debug"]["container"].pack_forget()

    def _dock_debug_back(self) -> None:
        if self._debug_float_win is None:
            return
        self._docked_debug.sync_from(self._debug_float_win.panel)

        try:
            self._debug_float_win.destroy()
        except Exception:
            pass
        self._debug_float_win = None

        # Restore the DEBUG tab and switch to it (restores debug ctrls too)
        self._tabs["debug"]["container"].pack(side="left")
        self._set_active("debug")

    def set_cwd(self, cwd: str) -> None:
        self._cwd = cwd
        self.terminal._cwd = cwd
        if self._cwd_after_id is not None:
            self.after_cancel(self._cwd_after_id)
        self._cwd_after_id = self.after(250, self._apply_cwd)

    def _apply_cwd(self) -> None:
        self._cwd_after_id = None
        if not self._cwd:
            return
        if self._active == "terminal" and self.terminal._running:
            self.terminal.send_text(f'cd "{self._cwd}"\r')
        elif self.terminal._running:
            # Terminal is running but not the active tab — defer until shown
            self._pending_cd = self._cwd

    def update_problems(self, entries: list[dict]) -> None:
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
        # Show Ask AI button only when there are actionable problems
        if errors or warnings:
            self._ask_ai_btn.pack(side="left")
        else:
            self._ask_ai_btn.pack_forget()

    def _fire_ask_ai(self) -> None:
        if self.on_ask_ai_problems:
            self.on_ask_ai_problems()

    # ── Problems tab flash ────────────────────────────────────────────────────

    _FLASH_AMBER = "#f59e0b"
    _FLASH_MS    = 600

    def flash_problems_tab(self) -> None:
        """Flash the PROBLEMS tab amber until it's clicked or flash is stopped."""
        if self._active == "problems":
            return
        if self._flash_job is not None:
            return
        self._flash_state = False
        self._tick_flash()

    def stop_flash_problems_tab(self) -> None:
        """Stop flashing and restore the normal tab colour."""
        if self._flash_job is not None:
            try:
                self.after_cancel(self._flash_job)
            except Exception:
                pass
            self._flash_job = None
        lbl = self._tabs["problems"]["label"]
        normal = self._TAB_FG_ACT if self._active == "problems" else self._TAB_FG
        lbl.config(fg=normal)

    def _tick_flash(self) -> None:
        self._flash_state = not self._flash_state
        lbl = self._tabs["problems"]["label"]
        lbl.config(fg=self._FLASH_AMBER if self._flash_state else self._TAB_FG)
        self._flash_job = self.after(self._FLASH_MS, self._tick_flash)

    def _set_active(self, key: str) -> None:
        # If debug is floating and we're asked to switch to it, skip — it's
        # already visible in its own window
        if key == "debug" and self._debug_float_win is not None:
            return
        if key == "problems":
            self.stop_flash_problems_tab()

        # Swap per-panel control frame in the right-side slot
        if self._active_ctrls is not None:
            self._active_ctrls.pack_forget()
        self._active_ctrls = self._panel_ctrls.get(key)
        if self._active_ctrls is not None:
            self._active_ctrls.pack(side="right", fill="y")

        for k, tab in self._tabs.items():
            active = k == key
            tab["label"].config(fg=self._TAB_FG_ACT if active else self._TAB_FG)
            if active:
                tab["indicator"].pack(side="bottom", fill="x")
            else:
                tab["indicator"].pack_forget()

        for panel in (self.output, self.terminal, self.problems, self._docked_debug):
            panel.pack_forget()

        if key == "output":
            self.output.pack(fill="both", expand=True)
        elif key == "terminal":
            self.terminal.pack(fill="both", expand=True)
            if not self.terminal._running:
                self.terminal.start(cwd=self._cwd)
            elif self._pending_cd:
                self.terminal._send_silently(f'cd "{self._pending_cd}"\r')
                self._pending_cd = None
            if self._terminal_first_show:
                self._terminal_first_show = False
                if platform.system() == "Windows":
                    self.terminal.after(200, lambda: self.terminal.send_text("\x0c"))
                else:
                    self.terminal.after(50, lambda: self.terminal._text.yview_moveto(0))
        elif key == "problems":
            self.problems.pack(fill="both", expand=True)
        else:  # debug
            self._docked_debug.pack(fill="both", expand=True)

        self._active = key
