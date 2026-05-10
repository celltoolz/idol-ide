"""ProblemsPanel — scrollable list of LSP diagnostics with click-to-navigate."""
from __future__ import annotations

import re
import tkinter as tk
from tkinter import Frame, Text, ttk
from typing import Callable

from utils.ruff_rules import lookup as _rule_lookup
from utils.ui_font import UI_FONT

_CODE_RE = re.compile(r'\(([A-Z]\d+|[a-z][a-z0-9\-]+)\)$')

_SEV_ERROR   = 1
_SEV_WARNING = 2
_SEV_INFO    = 3

_ICONS  = {_SEV_ERROR: "●", _SEV_WARNING: "●", _SEV_INFO: "●"}
_COLORS = {_SEV_ERROR: "#f44747", _SEV_WARNING: "#cca700", _SEV_INFO: "#75beff"}
_TAGS   = {_SEV_ERROR: "sev_error", _SEV_WARNING: "sev_warning", _SEV_INFO: "sev_info"}
_ORDER  = {_SEV_ERROR: 0, _SEV_WARNING: 1, _SEV_INFO: 2}


class ProblemsPanel(Frame):
    _BG       = "#1e1e1e"
    _FG       = "#cccccc"
    _FG_DIM   = "#6e7681"
    _HOVER_BG = "#2a2d2e"

    def __init__(
        self,
        master,
        on_navigate: Callable[[str, int, int], None],
        **kwargs,
    ) -> None:
        super().__init__(master, bg=self._BG, **kwargs)
        self._on_navigate = on_navigate
        self._entries: list[dict] = []
        self.on_ask_ai_entry: Callable[[dict], None] | None = None
        self._tooltip_win: tk.Toplevel | None = None
        self._tooltip_job: str | None = None
        self._tooltip_row: int | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        sb = ttk.Scrollbar(self, orient="vertical")
        sb.pack(side="right", fill="y")

        self._text = Text(
            self,
            bg=self._BG,
            fg=self._FG,
            font=(UI_FONT, 9),
            cursor="arrow",
            bd=0,
            relief="flat",
            wrap="none",
            state="disabled",
            yscrollcommand=sb.set,
            selectbackground=self._BG,
            selectforeground=self._FG,
            inactiveselectbackground=self._BG,
            padx=4,
            pady=4,
        )
        self._text.pack(side="left", fill="both", expand=True)
        sb.config(command=self._text.yview)

        for sev, tag in _TAGS.items():
            self._text.tag_configure(
                tag,
                foreground=_COLORS[sev],
                font=(UI_FONT, 9, "bold"),
            )
        self._text.tag_configure("msg",  foreground=self._FG)
        self._text.tag_configure("loc",  foreground=self._FG_DIM)
        self._text.tag_configure("hover", background=self._HOVER_BG)
        self._text.tag_configure(
            "empty",
            foreground=self._FG_DIM,
            font=(UI_FONT, 9),
        )

        self._text.bind("<Motion>",        self._on_motion)
        self._text.bind("<Leave>",         self._on_leave)
        self._text.bind("<Button-1>",      self._on_click)
        self._text.bind("<Double-Button-1>", self._on_double_click)

    # ── Public API ────────────────────────────────────────────────────────────

    def update(self, entries: list[dict]) -> None:
        """Repopulate the list with *entries* (sorted: errors → warnings → info)."""
        self._entries = sorted(
            entries,
            key=lambda e: (
                _ORDER.get(e.get("severity", _SEV_WARNING), 99),
                e.get("filename", ""),
                e.get("line", 0),
            ),
        )
        self._text.config(state="normal")
        self._text.delete("1.0", "end")

        if not self._entries:
            self._text.insert("end", "  No problems detected", "empty")
        else:
            for i, entry in enumerate(self._entries):
                if i:
                    self._text.insert("end", "\n")
                sev  = entry.get("severity", _SEV_WARNING)
                tag  = _TAGS.get(sev, "sev_info")
                icon = _ICONS.get(sev, "●")
                msg  = entry.get("message", "").replace("\n", " ")
                loc  = f"  {entry.get('filename','')}:{entry.get('line', 0)}"

                self._text.insert("end", f"  {icon}  ", tag)
                self._text.insert("end", msg, "msg")
                self._text.insert("end", loc, "loc")

        self._text.config(state="disabled")

    # ── Event handlers ────────────────────────────────────────────────────────

    def _row_at(self, event) -> int | None:
        row = int(self._text.index(f"@{event.x},{event.y}").split(".")[0]) - 1
        return row if 0 <= row < len(self._entries) else None

    def _on_click(self, event) -> None:
        row = self._row_at(event)
        if row is not None:
            e = self._entries[row]
            self._on_navigate(e["filepath"], e["line"], e.get("col", 0))

    def _on_double_click(self, event) -> None:
        row = self._row_at(event)
        if row is not None and self.on_ask_ai_entry:
            self.on_ask_ai_entry(self._entries[row])

    def _on_motion(self, event) -> None:
        self._text.tag_remove("hover", "1.0", "end")
        row = self._row_at(event)
        if row is not None:
            self._text.tag_add("hover", f"{row + 1}.0", f"{row + 1}.end+1c")
        if row != self._tooltip_row:
            self._cancel_tooltip()
            self._tooltip_row = row
            if row is not None:
                rx, ry = event.x_root, event.y_root
                self._tooltip_job = self._text.after(
                    600, lambda: self._show_tooltip(row, rx, ry)
                )

    def _on_leave(self, _) -> None:
        self._text.tag_remove("hover", "1.0", "end")
        self._cancel_tooltip()

    # ── Tooltip ───────────────────────────────────────────────────────────────

    def _cancel_tooltip(self) -> None:
        if self._tooltip_job:
            try:
                self._text.after_cancel(self._tooltip_job)
            except Exception:
                pass
            self._tooltip_job = None
        if self._tooltip_win:
            try:
                self._tooltip_win.destroy()
            except Exception:
                pass
            self._tooltip_win = None
        self._tooltip_row = None

    def _show_tooltip(self, row: int, rx: int, ry: int) -> None:
        self._tooltip_job = None
        if row >= len(self._entries):
            return
        entry = self._entries[row]
        msg   = entry.get("message", "")
        sev   = entry.get("severity", _SEV_WARNING)

        # Extract the code from the end of the message, e.g. "Some message (F821)"
        code = ""
        m = _CODE_RE.search(msg)
        if m:
            code = m.group(1)

        rule = _rule_lookup(code) if code else None
        short_name  = rule[0] if rule else ""
        description = rule[1] if rule else msg

        sev_color = _COLORS.get(sev, "#cccccc")
        sep_color = "#3c3c3c"
        dim_color = "#858585"
        bg        = "#252526"

        win = tk.Toplevel(self._text)
        win.wm_overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg=sep_color)          # 1px border via bg bleed

        inner = tk.Frame(win, bg=bg, padx=12, pady=8)
        inner.pack(padx=1, pady=1)

        # Header: code + short name
        header = f"{code} — {short_name}" if code and short_name else (code or short_name or "Issue")
        tk.Label(
            inner, text=header,
            bg=bg, fg=sev_color,
            font=(UI_FONT, 9, "bold"), anchor="w", justify="left",
        ).pack(fill="x")

        # Separator
        tk.Frame(inner, bg=sep_color, height=1).pack(fill="x", pady=(4, 0))

        # Description — wrap at ~320px
        tk.Label(
            inner, text=description,
            bg=bg, fg="#cccccc",
            font=(UI_FONT, 9), wraplength=320,
            anchor="w", justify="left",
        ).pack(fill="x", pady=(4, 0))

        # Separator
        tk.Frame(inner, bg=sep_color, height=1).pack(fill="x", pady=(6, 0))

        # Footer hint
        tk.Label(
            inner, text="Double-click to Ask AI about this problem.",
            bg=bg, fg=dim_color,
            font=(UI_FONT, 8, "italic"), anchor="w", justify="left",
        ).pack(fill="x", pady=(4, 0))

        win.update_idletasks()
        tw = win.winfo_width()
        th = win.winfo_height()
        # Position just below and to the right of the cursor
        x = rx + 12
        y = ry + 16
        # Keep on screen
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        if x + tw > sw:
            x = sw - tw - 8
        if y + th > sh:
            y = ry - th - 8
        win.wm_geometry(f"+{x}+{y}")

        self._tooltip_win = win
