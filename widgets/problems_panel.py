"""ProblemsPanel — scrollable list of LSP diagnostics with click-to-navigate."""
from __future__ import annotations

from tkinter import Frame, Text, ttk
from typing import Callable

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
        self._build_ui()

    def _build_ui(self) -> None:
        sb = ttk.Scrollbar(self, orient="vertical")
        sb.pack(side="right", fill="y")

        self._text = Text(
            self,
            bg=self._BG,
            fg=self._FG,
            font=("Segoe UI", 9),
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
                font=("Segoe UI", 9, "bold"),
            )
        self._text.tag_configure("msg",  foreground=self._FG)
        self._text.tag_configure("loc",  foreground=self._FG_DIM)
        self._text.tag_configure("hover", background=self._HOVER_BG)
        self._text.tag_configure(
            "empty",
            foreground=self._FG_DIM,
            font=("Segoe UI", 9),
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

    def _on_leave(self, _) -> None:
        self._text.tag_remove("hover", "1.0", "end")
