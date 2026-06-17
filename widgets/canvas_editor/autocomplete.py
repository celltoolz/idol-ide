"""Autocomplete for CanvasCodeView — completion popup + offline fallback.

Extracted from canvas_codeview.py (P3 decomposition). `AutocompleteMixin`
is inherited by `CanvasCodeView`.

The popup is a `tk.Toplevel` + `tk.Listbox` created lazily; render() never
touches it. Completion items come from the host's `on_completion_request`
hook (LSP, wired by app.py) when set, else from the synchronous buffer-word
fallback (`_buffer_word_items`). A sequence number (`_ac_seq`) guards
against stale async responses.

State (`_ac_top`, `_ac_listbox`, `_ac_items`, `_ac_prefix`, `_ac_seq`,
`on_completion_request`) is host-owned in CanvasCodeView._init_state so
app.py can set `on_completion_request` and call `_hide_autocomplete`.

Cross-mixin dependency (MRO must place AutocompleteMixin after FoldMixin):
  * FoldMixin._visual_row_of — popup Y anchoring through folded lines.
"""
from __future__ import annotations

import re
import tkinter as tk

from .constants import _FONT_FAMILY

# Identifier run — used by the offline buffer-word fallback to harvest
# candidate words from the buffer.
_WORD_RE = re.compile(r"\w+")


class AutocompleteMixin:
    """Completion popup + offline fallback, mixed into CanvasCodeView.

    Reads host state (`self.lines`, `self.cur_line`, `self.cur_col`,
    `self.canvas`, `self.scroll_y`, `self._line_h`, `self._palette`, the
    `_ac_*` attrs, `self.on_completion_request`) and calls host/cross-mixin
    methods
    (`self._measure_to_col`, `self._visual_row_of`, `self._insert_text`,
    `self.render`)."""

    _AC_KEYWORDS = (
        "False None True and as assert async await break class continue "
        "def del elif else except finally for from global if import in is "
        "lambda nonlocal not or pass raise return try while with yield"
    ).split()
    _AC_BUILTINS = (
        "abs all any bool bytes callable chr classmethod compile complex "
        "dict dir divmod enumerate eval exec filter float format "
        "frozenset getattr globals hasattr hash hex id input int isinstance "
        "issubclass iter len list locals map max memoryview min next object "
        "oct open ord pow print property range repr reversed round set "
        "setattr slice sorted staticmethod str sum super tuple type vars "
        "zip self cls"
    ).split()

    def _current_prefix(self) -> str:
        """Return the identifier prefix immediately before the cursor."""
        line = self.lines[self.cur_line]
        c = self.cur_col
        start = c
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1
        return line[start:c]

    def _buffer_word_items(self, prefix: str,
                           trigger_char: str | None) -> list[str]:
        """Synchronous fallback when no `on_completion_request` host hook
        is wired. Returns [] on `.` trigger — dumping every identifier in
        the buffer as member candidates would be noise; real member
        completion needs an LSP."""
        if trigger_char == ".":
            return []
        words: set[str] = set(self._AC_KEYWORDS) | set(self._AC_BUILTINS)
        for line in self.lines:
            for m in _WORD_RE.findall(line):
                if len(m) >= 2 and not m[0].isdigit():
                    words.add(m)
        return sorted(
            {w for w in words if w != prefix and w.startswith(prefix)},
            key=lambda w: w.lower(),
        )[:30]

    def _maybe_show_autocomplete(self) -> None:
        """Decide whether to show, narrow, or hide the autocomplete popup.

        Triggers:
          • prefix is ≥1 char of an identifier — normal completion, or
          • char immediately before the prefix is `.` — member access.

        Completion source is async-friendly via `on_completion_request`
        (host supplies items via callback). A sequence number guards
        against a stale LSP response overwriting a fresher request.
        """
        prefix = self._current_prefix()
        line = self.lines[self.cur_line]
        prefix_start = self.cur_col - len(prefix)
        is_member = (prefix_start > 0
                     and line[prefix_start - 1] == ".")
        if not is_member and len(prefix) < 1:
            self._hide_autocomplete()
            return
        trigger = "." if is_member else None
        self._ac_seq += 1
        seq = self._ac_seq

        def deliver(items, _prefix=prefix, _seq=seq):
            if _seq != self._ac_seq:
                return  # stale — newer request superseded this one
            # If the user typed/deleted between request and response,
            # the prefix may no longer match — the new request will
            # handle it.
            if self._current_prefix() != _prefix:
                return
            items = sorted(
                {w for w in items if w != _prefix and w.startswith(_prefix)},
                key=lambda w: w.lower(),
            )[:30]
            if not items:
                self._hide_autocomplete()
                return
            self._ac_items = items
            self._ac_prefix = _prefix
            self._show_autocomplete_popup()

        if self.on_completion_request is not None:
            try:
                self.on_completion_request(prefix, trigger, deliver)
            except Exception:
                deliver([])
        else:
            deliver(self._buffer_word_items(prefix, trigger))

    def _show_autocomplete_popup(self) -> None:
        # Geometry — anchor under the typed prefix.
        line = self.lines[self.cur_line]
        col = self.cur_col - len(self._ac_prefix)
        cx = self._text_x0 + self._measure_to_col(line, col)
        cy = (self._visual_row_of(self.cur_line) - self.scroll_y + 1) * self._line_h
        rx = self.canvas.winfo_rootx() + cx
        ry = self.canvas.winfo_rooty() + cy

        if self._ac_top is None:
            self._ac_top = tk.Toplevel(self)
            self._ac_top.overrideredirect(True)
            self._ac_top.attributes("-topmost", True)
            self._ac_listbox = tk.Listbox(
                self._ac_top,
                font=(_FONT_FAMILY, 10),
                relief="flat", borderwidth=1,
                highlightthickness=0,
                activestyle="none",
                width=24, height=8,
            )
            self._ac_listbox.pack(fill="both", expand=True)
            self._ac_listbox.bind("<ButtonRelease-1>",
                                  lambda _: self._accept_autocomplete())
            self._ac_listbox.bind("<Double-Button-1>",
                                  lambda _: self._accept_autocomplete())
        # Theme the popup from the active palette on every show, so it
        # follows set_theme even though the Toplevel is cached after first use.
        # selectforeground uses fg (not white) so the selected row stays
        # readable on light themes' pale select_bg.
        self._ac_listbox.configure(
            bg=self._palette.get("sticky_bg", self._palette["bg"]),
            fg=self._palette["fg"],
            selectbackground=self._palette["select_bg"],
            selectforeground=self._palette["fg"],
        )
        self._ac_listbox.delete(0, "end")
        for it in self._ac_items:
            self._ac_listbox.insert("end", it)
        self._ac_listbox.selection_set(0)
        self._ac_listbox.activate(0)
        self._ac_top.geometry(f"+{rx}+{ry}")
        self._ac_top.deiconify()

    def _hide_autocomplete(self) -> None:
        if self._ac_top is not None:
            self._ac_top.withdraw()
        self._ac_items = []
        self._ac_prefix = ""

    def _ac_dismiss_if_unfocused(self) -> None:
        if self._ac_top is None or self._ac_top.state() != "normal":
            return
        focused = self.focus_get()
        if focused is not self.canvas and focused is not self._ac_listbox:
            self._hide_autocomplete()

    def _ac_select(self, delta: int) -> None:
        if not self._ac_items or self._ac_listbox is None:
            return
        cur = self._ac_listbox.curselection()
        idx = (cur[0] if cur else 0) + delta
        idx = max(0, min(len(self._ac_items) - 1, idx))
        self._ac_listbox.selection_clear(0, "end")
        self._ac_listbox.selection_set(idx)
        self._ac_listbox.activate(idx)
        self._ac_listbox.see(idx)

    def _accept_autocomplete(self) -> None:
        if not self._ac_items or self._ac_listbox is None:
            return
        cur = self._ac_listbox.curselection()
        idx = cur[0] if cur else 0
        choice = self._ac_items[idx]
        suffix = choice[len(self._ac_prefix):]
        if suffix:
            self._insert_text(suffix)
        self._hide_autocomplete()
        self.render()
