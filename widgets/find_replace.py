from __future__ import annotations

import re
import tkinter as tk
from tkinter import BooleanVar, StringVar
from utils.ui_font import UI_FONT


# ── Editor-engine adapter ─────────────────────────────────────────────────────
# FindReplaceBar predates the canvas-rendered editor; it was written
# entirely against tk.Text indices ("1.0 + N chars" strings + tag_*
# operations). To support BOTH the legacy `CodeView` and the new
# `CanvasCodeView` (which has no Text tags), match storage was switched
# to plain char offsets (start, end). These helpers translate between
# offsets and whatever each engine's API needs.

def _is_canvas_cv(cv) -> bool:
    """True when *cv* is the canvas-rendered editor (no Text tags)."""
    return type(cv).__name__ == "CanvasCodeView"

def _full_text(cv) -> str:
    if _is_canvas_cv(cv):
        return cv.get_text()
    return cv.get("1.0", "end-1c")

def _selected_text(cv) -> str:
    if _is_canvas_cv(cv):
        return cv.selected_text()
    try:
        return cv.get("sel.first", "sel.last")
    except tk.TclError:
        return ""

def _offset_to_lc(text: str, offset: int) -> tuple[int, int]:
    """Char offset → (0-indexed line, 0-indexed col). Engine-agnostic."""
    before = text[:offset]
    line = before.count("\n")
    last_nl = before.rfind("\n")
    col = offset - (last_nl + 1) if last_nl >= 0 else offset
    return (line, col)

def _matches_to_ranges(text: str,
                       offsets: list[tuple[int, int]]
                       ) -> list[tuple[tuple[int, int], tuple[int, int]]]:
    """Convert a list of (start_offset, end_offset) to the
    `((sl,sc),(el,ec))` shape `CanvasCodeView.set_find_matches`
    expects."""
    return [(_offset_to_lc(text, s), _offset_to_lc(text, e))
            for s, e in offsets]


# ── Colour constants ──────────────────────────────────────────────────────────
_BG          = "#252526"   # bar background
_FG          = "#cccccc"   # normal text
_ENTRY_BG    = "#3c3c3c"   # entry / button background
_ACTIVE_BG   = "#094771"   # toggled option button (case / word / regex)
_FOCUS_BLUE  = "#007acc"   # entry border on focus, current-match highlight
_MATCH_BG    = "#613315"   # all-matches highlight (dark orange, VS Code style)
_CURRENT_BG  = "#007acc"   # current match highlight
_BTN_HOVER   = "#4a4a4a"   # subtle hover for icon buttons
_BORDER_IDLE = "#474747"   # entry border when not focused


def _icon_btn(
    parent: tk.Widget,
    text: str,
    command,
    tooltip: str = "",
    width: int = 3,
) -> tk.Button:
    """Create a flat icon button that matches the dark theme."""
    btn = tk.Button(
        parent,
        text=text,
        command=command,
        bg=_ENTRY_BG,
        fg=_FG,
        activebackground=_BTN_HOVER,
        activeforeground=_FG,
        relief="flat",
        bd=0,
        padx=4,
        pady=2,
        width=width,
        cursor="hand2",
        font=(UI_FONT, 9),
    )
    # Hover effect
    btn.bind("<Enter>", lambda _: btn.config(bg=_BTN_HOVER))
    btn.bind("<Leave>", lambda _: btn.config(
        bg=_ACTIVE_BG if getattr(btn, "_active", False) else _ENTRY_BG
    ))
    return btn


def _toggle_btn(parent: tk.Widget, text: str, var: BooleanVar, command) -> tk.Button:
    """A toggle button that highlights when active."""
    btn = tk.Button(
        parent,
        text=text,
        bg=_ENTRY_BG,
        fg=_FG,
        activebackground=_BTN_HOVER,
        activeforeground=_FG,
        relief="flat",
        bd=0,
        padx=4,
        pady=2,
        width=3,
        cursor="hand2",
        font=(UI_FONT, 9),
    )
    btn._active = False  # type: ignore[attr-defined]

    def _on_click():
        var.set(not var.get())
        btn._active = var.get()
        btn.config(bg=_ACTIVE_BG if btn._active else _ENTRY_BG)
        command()

    btn.config(command=_on_click)
    btn.bind("<Enter>", lambda _: btn.config(bg=_BTN_HOVER if not btn._active else _ACTIVE_BG))
    btn.bind("<Leave>", lambda _: btn.config(bg=_ACTIVE_BG if btn._active else _ENTRY_BG))
    return btn


def _styled_entry(parent: tk.Widget, textvariable: StringVar, width: int = 24) -> tk.Entry:
    """Dark-themed flat entry with a blue border on focus."""
    # Outer frame acts as the 1-px border
    frame = tk.Frame(parent, bg=_BORDER_IDLE, padx=1, pady=1)
    entry = tk.Entry(
        frame,
        textvariable=textvariable,
        bg=_ENTRY_BG,
        fg=_FG,
        insertbackground="white",
        selectbackground=_FOCUS_BLUE,
        selectforeground="white",
        relief="flat",
        bd=0,
        highlightthickness=0,
        width=width,
        font=(UI_FONT, 9),
    )
    entry.pack(fill="both", expand=True)

    def _on_focus_in(_):
        frame.config(bg=_FOCUS_BLUE)

    def _on_focus_out(_):
        frame.config(bg=_BORDER_IDLE)

    entry.bind("<FocusIn>",  _on_focus_in)
    entry.bind("<FocusOut>", _on_focus_out)

    # Expose the outer frame as entry._frame so the caller can grid/pack it
    entry._frame = frame  # type: ignore[attr-defined]
    return entry


class FindReplaceBar(tk.Frame):
    """VS Code-style inline find/replace bar.

    Lives inside the editor frame and is placed/hidden via place() /
    place_forget().  It is NOT a Toplevel.

    Usage
    -----
    bar = FindReplaceBar(editor_frame)
    bar.show(codeview)   # make visible, focus the find entry
    bar.hide()           # hide and clear highlights
    """

    def __init__(self, master: tk.Widget) -> None:
        super().__init__(master, bg=_BG, padx=6, pady=4)

        self._cv: tk.Text | None = None          # current codeview
        # Engine-agnostic match storage — (start_offset, end_offset)
        # char offsets into the buffer text. Converted to either
        # `cv.index(...)` strings (legacy) or `((line,col),(line,col))`
        # tuples (canvas) at the apply step.
        self._matches: list[tuple[int, int]] = []
        self._current: int = -1
        self._after_id: str | None = None
        self._replace_visible: bool = False

        # StringVars / BooleanVars
        self.find_var    = StringVar()
        self.replace_var = StringVar()
        self.case_var    = BooleanVar()
        self.word_var    = BooleanVar()
        self.regex_var   = BooleanVar()

        self._build_ui()

        # Live search — debounced 150 ms
        self.find_var.trace_add("write", lambda *_: self._schedule_update())

        # Start hidden
        self.place_forget()

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        # ── Row 0: find row ───────────────────────────────────────────────────
        find_row = tk.Frame(self, bg=_BG)
        find_row.pack(fill="x", side="top")

        # Chevron toggle (▸ collapsed / ▾ expanded)
        self._chevron_btn = _icon_btn(find_row, "▸", self._toggle_replace, width=2)
        self._chevron_btn.pack(side="left", padx=(0, 4))

        # Find entry (with its border frame)
        self.find_entry = _styled_entry(find_row, self.find_var, width=26)
        self.find_entry._frame.pack(side="left", padx=(0, 4))

        # Option toggles: Aa  ab  .*
        self._case_btn  = _toggle_btn(find_row, "Aa", self.case_var,  self._update)
        self._word_btn  = _toggle_btn(find_row, "ab", self.word_var,  self._update)
        self._regex_btn = _toggle_btn(find_row, ".*", self.regex_var, self._update)
        for btn in (self._case_btn, self._word_btn, self._regex_btn):
            btn.pack(side="left", padx=1)

        # Match count label  "1 of 5"
        self._count_lbl = tk.Label(
            find_row, text="", bg=_BG, fg="#858585",
            font=(UI_FONT, 8), width=8, anchor="w",
        )
        self._count_lbl.pack(side="left", padx=(4, 2))

        # Navigation buttons  ↑  ↓
        _icon_btn(find_row, "↑", self.find_prev, width=2).pack(side="left", padx=1)
        _icon_btn(find_row, "↓", self.find_next, width=2).pack(side="left", padx=1)

        # Close button
        _icon_btn(find_row, "✕", self.hide, width=2).pack(side="left", padx=(4, 0))

        # ── Row 1: replace row (initially hidden) ─────────────────────────────
        self._replace_row = tk.Frame(self, bg=_BG)
        # Not packed yet — shown by _toggle_replace()

        # Indent spacer (aligns with find entry, accounting for chevron width)
        tk.Frame(self._replace_row, bg=_BG, width=26).pack(side="left")

        self.replace_entry = _styled_entry(self._replace_row, self.replace_var, width=26)
        self.replace_entry._frame.pack(side="left", padx=(0, 4))

        _icon_btn(
            self._replace_row, "Replace", self.replace, width=8
        ).pack(side="left", padx=(0, 4))

        _icon_btn(
            self._replace_row, "Replace All", self.replace_all, width=11
        ).pack(side="left")

        # ── Global key bindings ───────────────────────────────────────────────
        self.find_entry.bind("<Return>",       lambda _: self.find_next())
        self.find_entry.bind("<Shift-Return>", lambda _: self.find_prev())
        self.find_entry.bind("<Escape>",       lambda _: self.hide())
        self.replace_entry.bind("<Escape>",    lambda _: self.hide())
        self.bind("<Escape>", lambda _: self.hide())

    # ── Chevron / replace-row toggle ─────────────────────────────────────────

    def _toggle_replace(self) -> None:
        self._replace_visible = not self._replace_visible
        self._chevron_btn.config(text="▾" if self._replace_visible else "▸")
        if self._replace_visible:
            self._replace_row.pack(fill="x", side="top", pady=(4, 0))
        else:
            self._replace_row.pack_forget()

    # ── Public API ────────────────────────────────────────────────────────────

    def show(self, codeview) -> None:
        """Place the bar and focus the find entry.

        If the codeview has a selection, pre-fill it as the search term.
        Accepts either the legacy `CodeView` (tk.Text) or the new
        `CanvasCodeView` — the bar reads its content + cursor through
        the `_full_text`/`_selected_text` adapters above.
        """
        self._cv = codeview

        sel = _selected_text(codeview)
        if sel and "\n" not in sel:
            self.find_var.set(sel)

        # Place in the top-right of the master frame; lift above everything
        self.place(relx=1.0, rely=0.0, anchor="ne", x=-2, y=2)
        self.lift()

        self.find_entry.focus_set()
        self.find_entry.selection_range(0, "end")

        # Run an immediate search so highlights appear right away
        self._update()

    def hide(self) -> None:
        """Hide the bar and remove all highlights."""
        self._clear_tags()
        self.place_forget()
        if self._cv:
            try:
                self._cv.focus_set()
            except tk.TclError:
                pass

    # ── Search internals ─────────────────────────────────────────────────────

    def _schedule_update(self) -> None:
        if self._after_id:
            self.after_cancel(self._after_id)
        self._after_id = self.after(150, self._update)

    def _make_pattern(self) -> re.Pattern | None:
        term = self.find_var.get()
        if not term:
            return None
        try:
            flags = 0 if self.case_var.get() else re.IGNORECASE
            if self.regex_var.get():
                return re.compile(term, flags)
            escaped = re.escape(term)
            if self.word_var.get():
                escaped = r"\b" + escaped + r"\b"
            return re.compile(escaped, flags)
        except re.error:
            return None

    def _update(self) -> None:
        cv = self._cv
        if cv is None:
            return

        self._clear_tags()
        self._matches = []
        self._current = -1

        pattern = self._make_pattern()
        if not pattern:
            self._count_lbl.config(text="")
            return

        text = _full_text(cv)
        # Internal match storage uses char offsets (engine-agnostic);
        # conversion to index strings / (line,col) tuples happens at
        # the apply step below.
        for m in pattern.finditer(text):
            self._matches.append((m.start(), m.end()))

        self._apply_highlights(text)

        n = len(self._matches)
        if n == 0:
            self._count_lbl.config(text="No results")
        else:
            self._count_lbl.config(text=f'{n} match{"es" if n != 1 else ""}')

    def _apply_highlights(self, text: str) -> None:
        """Push the current `_matches` (char offsets) to the editor as
        visible highlights — Text tags for legacy, canvas rectangles
        for the canvas engine."""
        cv = self._cv
        if cv is None:
            return
        if _is_canvas_cv(cv):
            ranges = _matches_to_ranges(text, self._matches)
            cv.set_find_matches(ranges, self._current)
            return
        for s, e in self._matches:
            cv.tag_add("find_match",
                       cv.index(f"1.0 + {s} chars"),
                       cv.index(f"1.0 + {e} chars"))
        cv.tag_configure("find_match",   background=_MATCH_BG,   foreground=_FG)
        cv.tag_configure("find_current", background=_CURRENT_BG, foreground="white")

    # ── Navigation ────────────────────────────────────────────────────────────

    def find_next(self) -> None:
        if not self._matches:
            self._update()
        if not self._matches:
            return
        self._current = (self._current + 1) % len(self._matches)
        self._highlight_current()

    def find_prev(self) -> None:
        if not self._matches:
            self._update()
        if not self._matches:
            return
        self._current = (self._current - 1) % len(self._matches)
        self._highlight_current()

    def _highlight_current(self) -> None:
        cv = self._cv
        if cv is None:
            return
        s_off, _e_off = self._matches[self._current]
        text = _full_text(cv)
        if _is_canvas_cv(cv):
            ranges = _matches_to_ranges(text, self._matches)
            cv.set_find_matches(ranges, self._current)
            cv.scroll_to_line(_offset_to_lc(text, s_off)[0])
        else:
            cv.tag_remove("find_current", "1.0", "end")
            start = cv.index(f"1.0 + {s_off} chars")
            end   = cv.index(f"1.0 + {self._matches[self._current][1]} chars")
            cv.tag_add("find_current", start, end)
            cv.tag_configure("find_current",
                             background=_CURRENT_BG, foreground="white")
            cv.tag_raise("find_current", "find_match")
            cv.see(start)
        self._count_lbl.config(
            text=f"{self._current + 1} of {len(self._matches)}"
        )

    # ── Replace ───────────────────────────────────────────────────────────────

    def replace(self) -> None:
        """Replace the current match and advance to the next one."""
        if self._current < 0:
            self.find_next()
            return
        cv = self._cv
        if cv is None:
            return
        s_off, e_off = self._matches[self._current]
        replacement = self.replace_var.get()
        if _is_canvas_cv(cv):
            text = _full_text(cv)
            cv.replace_range(_offset_to_lc(text, s_off),
                             _offset_to_lc(text, e_off),
                             replacement)
        else:
            start = cv.index(f"1.0 + {s_off} chars")
            end   = cv.index(f"1.0 + {e_off} chars")
            cv.delete(start, end)
            cv.insert(start, replacement)
        self._update()
        if self._matches:
            self._current = min(self._current, len(self._matches) - 1)
            self._highlight_current()

    def replace_all(self) -> None:
        """Replace every match in the document."""
        self._update()
        if not self._matches:
            return
        cv = self._cv
        if cv is None:
            return
        replacement = self.replace_var.get()
        if _is_canvas_cv(cv):
            # Apply replacements right-to-left so earlier offsets stay
            # valid as we mutate the buffer.
            text = _full_text(cv)
            for s_off, e_off in reversed(self._matches):
                cv.replace_range(_offset_to_lc(text, s_off),
                                 _offset_to_lc(text, e_off),
                                 replacement)
                # `replace_range` mutates the buffer; refresh `text`
                # for the next iteration's offset conversion.
                text = _full_text(cv)
        else:
            for s_off, e_off in reversed(self._matches):
                start = cv.index(f"1.0 + {s_off} chars")
                end   = cv.index(f"1.0 + {e_off} chars")
                cv.delete(start, end)
                cv.insert(start, replacement)
        self._update()

    # ── Cleanup ───────────────────────────────────────────────────────────────

    def _clear_tags(self) -> None:
        cv = self._cv
        if cv is None:
            return
        if _is_canvas_cv(cv):
            cv.clear_find_matches()
            return
        try:
            cv.tag_remove("find_match",   "1.0", "end")
            cv.tag_remove("find_current", "1.0", "end")
        except tk.TclError:
            pass
