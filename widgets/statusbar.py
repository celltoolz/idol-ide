from __future__ import annotations

from tkinter import ttk
from typing import Callable, Optional


class StatusBar(ttk.Frame):
    """VS Code-style status bar: Ln/Col | Lexer | Encoding | Spaces.

    The indent indicator is clickable — it cycles through 2 / 4 / 8 spaces
    and fires *on_indent_change(size)* so the app can update the active editor.
    """

    _INDENT_CYCLE = [2, 4, 8]

    def __init__(
        self,
        master,
        on_indent_change: Optional[Callable[[int], None]] = None,
        on_diagnostics_click: Optional[Callable[[], None]] = None,
        on_interpreter_click: Optional[Callable[[], None]] = None,
        on_run_entry_click: Optional[Callable[[], None]] = None,
        **kwargs,
    ) -> None:
        super().__init__(master, **kwargs)
        self._on_indent_change = on_indent_change
        self._on_diagnostics_click = on_diagnostics_click
        self._on_interpreter_click = on_interpreter_click
        self._on_run_entry_click = on_run_entry_click
        self._indent_size = 4
        self._branch_name = ""
        self._ahead = 0
        self._behind = 0
        self._build_ui()

    def _build_ui(self) -> None:
        style = ttk.Style()
        style.configure("SB.TFrame",        background="#1e1e1e")
        style.configure("SB.TLabel",        background="#1e1e1e", foreground="#858585",
                        font=("TkDefaultFont", 8))
        style.configure("SB.Hi.TLabel",     background="#1e1e1e", foreground="#cccccc",
                        font=("TkDefaultFont", 8))

        self.configure(style="SB.TFrame")

        # Top border
        ttk.Separator(self, orient="horizontal").pack(fill="x", side="top")

        # ── Right side (packed right-to-left) ─────────────────────────────────
        self._indent_lbl = ttk.Label(self, style="SB.Hi.TLabel", cursor="hand2")
        self._indent_lbl.pack(side="right", padx=(2, 10), pady=2)
        self._indent_lbl.bind("<Button-1>", self._on_indent_click)
        self._vsep()

        self._encoding_lbl = ttk.Label(self, text="UTF-8", style="SB.TLabel")
        self._encoding_lbl.pack(side="right", padx=(2, 8), pady=2)
        self._vsep()

        self._lexer_lbl = ttk.Label(self, text="", style="SB.Hi.TLabel")
        self._lexer_lbl.pack(side="right", padx=(2, 8), pady=2)
        self._vsep()

        # ── Left side ─────────────────────────────────────────────────────────
        self._branch_lbl = ttk.Label(self, text="", style="SB.Hi.TLabel")
        # hidden until set_branch() is called with a real name
        self._branch_sep = ttk.Separator(self, orient="vertical")

        self._pos_lbl = ttk.Label(self, text="Ln 1, Col 1", style="SB.TLabel")
        self._pos_lbl.pack(side="left", padx=(10, 2), pady=2)

        self._refresh_indent_label()

    def _vsep(self) -> None:
        ttk.Separator(self, orient="vertical").pack(side="right", fill="y", padx=4, pady=3)

    # ── Public API ────────────────────────────────────────────────────────────

    def set_position(self, line: int, col: int, cursors: int = 1) -> None:
        pos = f"Ln {line}, Col {col + 1}"
        if cursors > 1:
            pos += f"  |  {cursors} cursors"
        self._pos_lbl.config(text=pos)

    def set_branch(self, name: str) -> None:
        """Show or update the git branch indicator on the left of the status bar."""
        self._branch_name = name
        self._refresh_branch_label()

    def set_ahead_behind(self, ahead: int, behind: int) -> None:
        """Update the ahead/behind counts shown next to the branch name."""
        self._ahead = ahead
        self._behind = behind
        self._refresh_branch_label()

    def _refresh_branch_label(self) -> None:
        name = self._branch_name
        if not name:
            self._branch_lbl.pack_forget()
            self._branch_sep.pack_forget()
            return
        text = f"⎇ {name}"
        if self._ahead:
            text += f" ↑{self._ahead}"
        if self._behind:
            text += f" ↓{self._behind}"
        self._branch_lbl.config(text=text)
        self._branch_sep.pack(side="left", fill="y", padx=4, pady=3)
        self._branch_lbl.pack(side="left", padx=(4, 2), pady=2)

    def set_lexer(self, name: str) -> None:
        self._lexer_lbl.config(text=name)

    def set_indent(self, size: int) -> None:
        self._indent_size = size
        self._refresh_indent_label()

    def set_diagnostics(self, errors: int, warnings: int) -> None:
        """Show or hide the error/warning counts on the left of the status bar."""
        if not hasattr(self, "_diag_lbl"):
            self._diag_sep = ttk.Separator(self, orient="vertical")
            self._diag_lbl = ttk.Label(self, style="SB.TLabel", cursor="hand2")
        if errors or warnings:
            parts = []
            if errors:
                parts.append(f"✕ {errors}")
            if warnings:
                parts.append(f"⚠ {warnings}")
            self._diag_lbl.config(text="  ".join(parts))
            if self._on_diagnostics_click:
                self._diag_lbl.bind(
                    "<Button-1>",
                    lambda _: self._on_diagnostics_click(),
                )
            self._diag_sep.pack(side="left", fill="y", padx=4, pady=3)
            self._diag_lbl.pack(side="left", padx=(0, 4), pady=2)
        else:
            self._diag_sep.pack_forget()
            self._diag_lbl.pack_forget()

    def set_run_entry(self, label: str) -> None:
        """Show or update the run-entry file indicator (right side, left of interpreter)."""
        if not hasattr(self, "_run_entry_lbl"):
            self._run_entry_sep = ttk.Separator(self, orient="vertical")
            self._run_entry_lbl = ttk.Label(self, style="SB.Hi.TLabel", cursor="hand2")
            if self._on_run_entry_click:
                self._run_entry_lbl.bind("<Button-1>", lambda _: self._on_run_entry_click())
        if label:
            self._run_entry_lbl.config(text=f"\u25b6 {label}")
            self._run_entry_lbl.pack(side="right", padx=(2, 8), pady=2)
            self._run_entry_sep.pack(side="right", fill="y", padx=4, pady=3)
            # Keep interpreter rightmost
            if hasattr(self, "_interp_lbl"):
                self._interp_lbl.pack_forget()
                self._interp_sep.pack_forget()
                self._interp_lbl.pack(side="right", padx=(2, 8), pady=2)
                self._interp_sep.pack(side="right", fill="y", padx=4, pady=3)
        else:
            if hasattr(self, "_run_entry_lbl"):
                self._run_entry_lbl.pack_forget()
                self._run_entry_sep.pack_forget()

    def get_run_entry_anchor(self) -> tuple[int, int]:
        if hasattr(self, "_run_entry_lbl"):
            return self._run_entry_lbl.winfo_rootx(), self._run_entry_lbl.winfo_rooty()
        return self.winfo_rootx(), self.winfo_rooty()

    def set_interpreter(self, label: str) -> None:
        """Show or update the active Python interpreter on the right of the status bar."""
        if not hasattr(self, "_interp_lbl"):
            self._interp_sep = ttk.Separator(self, orient="vertical")
            self._interp_lbl = ttk.Label(self, style="SB.Hi.TLabel", cursor="hand2")
            if self._on_interpreter_click:
                self._interp_lbl.bind("<Button-1>", lambda _: self._on_interpreter_click())
        if label:
            self._interp_lbl.config(text=label)
            self._interp_lbl.pack(side="right", padx=(2, 8), pady=2)
            self._interp_sep.pack(side="right", fill="y", padx=4, pady=3)
        else:
            if hasattr(self, "_interp_lbl"):
                self._interp_lbl.pack_forget()
                self._interp_sep.pack_forget()

    def get_interp_anchor(self) -> tuple[int, int]:
        """Return (rootx, rooty) of the interpreter label for picker positioning."""
        if hasattr(self, "_interp_lbl"):
            return self._interp_lbl.winfo_rootx(), self._interp_lbl.winfo_rooty()
        return self.winfo_rootx(), self.winfo_rooty()

    def set_overwrite(self, active: bool) -> None:
        """Show OVR indicator when Insert/overwrite mode is on."""
        if active:
            if not hasattr(self, "_ovr_lbl"):
                self._ovr_sep = ttk.Separator(self, orient="vertical")
                self._ovr_lbl = ttk.Label(self, text="OVR", style="SB.Hi.TLabel")
            self._ovr_sep.pack(side="right", fill="y", padx=4, pady=3)
            self._ovr_lbl.pack(side="right", padx=(2, 8), pady=2)
        else:
            if hasattr(self, "_ovr_lbl"):
                self._ovr_lbl.pack_forget()
                self._ovr_sep.pack_forget()

    @property
    def indent_size(self) -> int:
        return self._indent_size

    # ── Internals ─────────────────────────────────────────────────────────────

    def _refresh_indent_label(self) -> None:
        self._indent_lbl.config(text=f"Spaces: {self._indent_size}")

    def _on_indent_click(self, _) -> None:
        try:
            idx = self._INDENT_CYCLE.index(self._indent_size)
        except ValueError:
            idx = 0
        self._indent_size = self._INDENT_CYCLE[(idx + 1) % len(self._INDENT_CYCLE)]
        self._refresh_indent_label()
        if self._on_indent_change:
            self._on_indent_change(self._indent_size)
