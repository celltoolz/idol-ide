"""DebugPanel — split panel: breakpoint list (left) + locals viewer (right)."""
from __future__ import annotations

import os
from tkinter import Frame, Label, PanedWindow, Text, ttk
from typing import Callable


class DebugPanel(Frame):
    _BG       = "#1e1e1e"
    _BG_PANE  = "#252526"
    _FG       = "#cccccc"
    _FG_DIM   = "#6e7681"
    _FG_HEAD  = "#858585"
    _HOVER_BG = "#2a2d2e"
    _DOT_ERR  = "#f44747"
    _DOT_BP   = "#e51400"

    def __init__(
        self,
        master,
        on_breakpoint_click: Callable[[str, int], None],
        **kwargs,
    ) -> None:
        super().__init__(master, bg=self._BG, **kwargs)
        self._on_bp_click   = on_breakpoint_click
        self._bp_entries: list[dict] = []
        self._last_locals:  list[dict] = []
        self._build_ui()

    # ── Layout ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        pane = PanedWindow(
            self,
            orient="horizontal",
            bg=self._BG,
            sashwidth=4,
            sashrelief="flat",
            bd=0,
        )
        pane.pack(fill="both", expand=True)

        # ── Left: breakpoints ─────────────────────────────────────────────────
        left = Frame(pane, bg=self._BG)
        pane.add(left, minsize=120, width=220)

        Label(
            left,
            text="BREAKPOINTS",
            bg=self._BG_PANE,
            fg=self._FG_HEAD,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            padx=8,
            pady=4,
        ).pack(fill="x")

        bp_sb = ttk.Scrollbar(left, orient="vertical")
        bp_sb.pack(side="right", fill="y")
        self._bp_text = Text(
            left,
            bg=self._BG,
            fg=self._FG,
            font=("Segoe UI", 9),
            cursor="arrow",
            bd=0,
            relief="flat",
            wrap="none",
            state="disabled",
            yscrollcommand=bp_sb.set,
            selectbackground=self._BG,
            padx=6,
            pady=4,
        )
        self._bp_text.pack(fill="both", expand=True)
        bp_sb.config(command=self._bp_text.yview)

        self._unsaved_warn = Label(
            left,
            text="  ⚠ Save file to make breakpoints permanent",
            bg=self._BG,
            fg="#e2c08d",
            font=("Segoe UI", 8),
            anchor="w",
            pady=3,
        )

        self._bp_text.tag_configure("dot",   foreground=self._DOT_BP, font=("Segoe UI", 9, "bold"))
        self._bp_text.tag_configure("file",  foreground=self._FG)
        self._bp_text.tag_configure("line",  foreground=self._FG_DIM)
        self._bp_text.tag_configure("hover", background=self._HOVER_BG)
        self._bp_text.tag_configure("empty", foreground=self._FG_DIM)
        self._bp_text.bind("<Motion>",   self._bp_motion)
        self._bp_text.bind("<Leave>",    lambda _: self._bp_text.tag_remove("hover", "1.0", "end"))
        self._bp_text.bind("<Button-1>", self._bp_click)

        # ── Right: locals ─────────────────────────────────────────────────────
        right = Frame(pane, bg=self._BG)
        pane.add(right, minsize=200)

        Label(
            right,
            text="LOCALS",
            bg=self._BG_PANE,
            fg=self._FG_HEAD,
            font=("Segoe UI", 8, "bold"),
            anchor="w",
            padx=8,
            pady=4,
        ).pack(fill="x")

        loc_sb = ttk.Scrollbar(right, orient="vertical")
        loc_sb.pack(side="right", fill="y")
        self._loc_text = Text(
            right,
            bg=self._BG,
            fg=self._FG,
            font=("Consolas", 9),
            cursor="arrow",
            bd=0,
            relief="flat",
            wrap="none",
            state="disabled",
            yscrollcommand=loc_sb.set,
            selectbackground=self._BG,
            padx=6,
            pady=4,
        )
        self._loc_text.pack(fill="both", expand=True)
        loc_sb.config(command=self._loc_text.yview)

        self._loc_text.tag_configure("name",  foreground="#9cdcfe")
        self._loc_text.tag_configure("sep",   foreground=self._FG_DIM)
        self._loc_text.tag_configure("value", foreground="#ce9178")
        self._loc_text.tag_configure("type",  foreground=self._FG_DIM)
        self._loc_text.tag_configure("empty", foreground=self._FG_DIM)

    # ── Public API ────────────────────────────────────────────────────────────

    def update_breakpoints(self, entries: list[dict]) -> None:
        """Refresh the breakpoints list.

        entries: [{"filepath": str, "filename": str, "line": int}]
        """
        self._bp_entries = sorted(entries, key=lambda e: (e.get("filename", ""), e.get("line", 0)))
        self._bp_text.config(state="normal")
        self._bp_text.delete("1.0", "end")
        if not self._bp_entries:
            self._bp_text.insert("end", "  No breakpoints set", "empty")
        else:
            for i, e in enumerate(self._bp_entries):
                if i:
                    self._bp_text.insert("end", "\n")
                self._bp_text.insert("end", "  ● ", "dot")
                self._bp_text.insert("end", e.get("filename", ""), "file")
                self._bp_text.insert("end", f":{e.get('line', 0)}", "line")
        self._bp_text.config(state="disabled")

    def update_locals(self, variables: list[dict]) -> None:
        """Refresh the locals pane with *variables* from the DAP response."""
        self._last_locals = variables
        self._loc_text.config(state="normal")
        self._loc_text.delete("1.0", "end")
        visible = [v for v in variables if not v.get("name", "").startswith("__")]
        if not visible:
            self._loc_text.insert("end", "  No locals in scope", "empty")
        else:
            for i, var in enumerate(visible):
                if i:
                    self._loc_text.insert("end", "\n")
                name  = var.get("name", "")
                value = var.get("value", "")
                vtype = var.get("type", "")
                type_hint = f"  {vtype}" if vtype else ""
                self._loc_text.insert("end", f"  {name}", "name")
                self._loc_text.insert("end", "  =  ", "sep")
                self._loc_text.insert("end", value, "value")
                if type_hint:
                    self._loc_text.insert("end", type_hint, "type")
        self._loc_text.config(state="disabled")

    def clear_session(self) -> None:
        """Reset both panes to their idle state."""
        self._last_locals = []
        self._loc_text.config(state="normal")
        self._loc_text.delete("1.0", "end")
        self._loc_text.insert("end", "  Start a debug session (F5) to inspect locals", "empty")
        self._loc_text.config(state="disabled")

    def show_unsaved_warning(self) -> None:
        self._unsaved_warn.pack(fill="x", before=self._bp_text)

    def hide_unsaved_warning(self) -> None:
        self._unsaved_warn.pack_forget()

    def sync_from(self, other: "DebugPanel") -> None:
        """Copy displayed state from *other* into this panel (used on dock/undock)."""
        self.update_breakpoints(list(other._bp_entries))
        if other._last_locals:
            self.update_locals(list(other._last_locals))
        else:
            self.clear_session()

    # ── Breakpoint list interaction ───────────────────────────────────────────

    def _row_at(self, event, widget: Text) -> int | None:
        row = int(widget.index(f"@{event.x},{event.y}").split(".")[0]) - 1
        return row if 0 <= row < len(self._bp_entries) else None

    def _bp_motion(self, event) -> None:
        self._bp_text.tag_remove("hover", "1.0", "end")
        row = self._row_at(event, self._bp_text)
        if row is not None:
            self._bp_text.tag_add("hover", f"{row + 1}.0", f"{row + 1}.end+1c")

    def _bp_click(self, event) -> None:
        row = self._row_at(event, self._bp_text)
        if row is not None:
            e = self._bp_entries[row]
            self._on_bp_click(e["filepath"], e["line"])
