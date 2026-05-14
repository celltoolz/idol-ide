"""CanvasCodeView — canvas-rendered code editor.

Thin wrapper exposing a stable explicit API on top of the canvas
rendering engine in `canvas_editor_sandbox.py`. The wrapper exists so
that app.py (and the ~400 other call sites) talk to a clean public
surface — `get_text`, `set_cursor`, `set_selection`, etc. — instead
of reaching directly into engine internals (`self.lines`,
`self.cur_line`, ...).

Phase (b) of the canvas-editor migration:
  • Engine: `CanvasEditorSandbox` — `self.lines: list[str]`, regex
    tokenizer, canvas paint. No `tk.Text`, no pygments.
  • Wrapper (this file): adds public API + host-supplied callback
    hooks + a `language` string attribute used in place of pygments
    isinstance checks.

Once Phase (e) cleanup removes the sandbox file and the legacy
`CodeView`, the engine code merges into this file directly and the
wrapper disappears.
"""
from __future__ import annotations

from typing import Callable

from .canvas_editor_sandbox import CanvasEditorSandbox


# File extension → language name. Replaces the pygments lexer
# `isinstance` checks in app.py. Anything unknown reports "text".
# Add new entries here as we wire syntax support for more languages.
_LANGUAGE_BY_EXT = {
    ".py":   "python",
    ".pyw":  "python",
    ".pyi":  "python",
    ".js":   "javascript",
    ".jsx":  "javascript",
    ".ts":   "typescript",
    ".tsx":  "typescript",
    ".json": "json",
    ".html": "html",
    ".htm":  "html",
    ".css":  "css",
    ".md":   "markdown",
    ".markdown": "markdown",
    ".toml": "toml",
    ".yaml": "yaml",
    ".yml":  "yaml",
    ".sh":   "shell",
    ".bash": "shell",
    ".bat":  "batch",
    ".cmd":  "batch",
    ".ps1":  "powershell",
}


def language_from_path(path: str | None) -> str:
    """Return the canonical language id for *path* (or "text")."""
    if not path:
        return "text"
    lower = path.lower()
    for ext, lang in _LANGUAGE_BY_EXT.items():
        if lower.endswith(ext):
            return lang
    return "text"


# Legacy `CodeView` constructor kwargs that the canvas engine doesn't
# implement (they were `tk.Text`/pygments-specific). Silently dropped
# during Phase (c) so existing `_new_tab` call sites keep working
# while we migrate; Phase (d) strips them at every call site.
_LEGACY_KWARGS = frozenset({
    "lexer",
    "color_scheme",
    "tab_width",
    "autohide_scrollbar",
    "linenums_theme",
    "linenums_border",
    "default_context_menu",
    "undo",
    "maxundo",
    "wrap",
})


class CanvasCodeView(CanvasEditorSandbox):
    """Canvas-rendered code editor with an explicit public API.

    Methods read/write buffer state through a stable surface; host
    code should NOT reach into engine internals (`self.lines`,
    `self.cur_line`, `self.sel_anchor`, ...). Direct attribute access
    is reserved for the engine and will be locked down once the
    migration completes.

    Indices follow the same convention throughout: 0-indexed line
    and column. A selection is `((start_line, start_col), (end_line,
    end_col))` with `start <= end` and *end* exclusive.
    """

    def __init__(self, master, **kwargs):
        # Drop the legacy `CodeView` kwargs so existing call sites
        # that still pass `lexer=` / `color_scheme=` / `undo=` etc.
        # don't blow up while we're migrating. Phase (d) removes them
        # at the callers; this guard goes away in Phase (e).
        for legacy in list(kwargs):
            if legacy in _LEGACY_KWARGS:
                kwargs.pop(legacy, None)
        super().__init__(master, **kwargs)

        # ── Host-supplied hooks ──────────────────────────────────────
        # All optional. The engine fires these (where wired) so the
        # host can react without polling. `on_completion_request` is
        # the older async-callback completion hook (already on the
        # engine); the rest are added here for the migration.
        self.on_change: Callable[[], None] | None = None
        self.on_cursor_move: Callable[[], None] | None = None
        self.on_lines_changed: Callable[[int, int], None] | None = None
        self.on_copy: Callable[[str], None] | None = None

        # ── Language attribute ───────────────────────────────────────
        # Replaces the pygments `isinstance(cv._lexer, PythonLexer)`
        # checks scattered across app.py. Set from `filepath` in
        # `set_filepath`; defaults to "text" for untitled buffers.
        self.language: str = "text"

    # ──────────────────────────────────────────────────────────────────
    # Buffer
    # ──────────────────────────────────────────────────────────────────

    def get_line(self, n: int) -> str:
        """Return the n-th line (0-indexed). `""` if out of range."""
        return self.lines[n] if 0 <= n < len(self.lines) else ""

    def line_count(self) -> int:
        return len(self.lines)

    # `get_text` / `set_text` already exist on the engine and behave
    # the way the public API needs (`set_text` resets cursor + folds
    # and triggers a render) — no override needed here.

    # ──────────────────────────────────────────────────────────────────
    # Cursor / selection
    # ──────────────────────────────────────────────────────────────────

    def get_cursor(self) -> tuple[int, int]:
        """Return `(line, col)` — both 0-indexed."""
        return (self.cur_line, self.cur_col)

    def set_cursor(self, line: int, col: int) -> None:
        """Place the cursor at `(line, col)`, clamping to the buffer
        bounds. Clears any active selection and ensures the line is
        visible in the viewport."""
        n = len(self.lines)
        if n == 0:
            self.cur_line = 0
            self.cur_col = 0
        else:
            self.cur_line = max(0, min(n - 1, line))
            self.cur_col = max(0, min(len(self.lines[self.cur_line]), col))
        self.sel_anchor = None
        self._ensure_visible()
        self.render()
        if self.on_cursor_move:
            self.on_cursor_move()

    def get_selection(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """Return `(start, end)` with `start <= end`, or `None` when
        nothing is selected. End is exclusive."""
        if self.sel_anchor is None:
            return None
        a = self.sel_anchor
        b = (self.cur_line, self.cur_col)
        if a == b:
            return None
        return (a, b) if a <= b else (b, a)

    def set_selection(self,
                      start: tuple[int, int],
                      end: tuple[int, int]) -> None:
        """Select the range `[start, end)`. Places the cursor at *end*."""
        self.sel_anchor = start
        self.cur_line, self.cur_col = end
        self._ensure_visible()
        self.render()
        if self.on_cursor_move:
            self.on_cursor_move()

    def clear_selection(self) -> None:
        if self.sel_anchor is not None:
            self.sel_anchor = None
            self.render()

    def selected_text(self) -> str:
        """Return the currently-selected text (empty string if none).
        Multi-line selections include the `\\n` joiners."""
        return self._selected_text()

    # ──────────────────────────────────────────────────────────────────
    # Editing
    # ──────────────────────────────────────────────────────────────────

    def insert(self, text: str) -> None:
        """Insert *text* at the cursor, replacing any active selection.
        Fires `on_change` and `on_lines_changed` if relevant."""
        if not text:
            return
        before_line = self.cur_line
        self._insert_text(text)
        self._ensure_visible()
        self.render()
        added_newlines = text.count("\n")
        if added_newlines and self.on_lines_changed:
            self.on_lines_changed(before_line, added_newlines)
        if self.on_change:
            self.on_change()

    def delete_selection(self) -> None:
        if self.sel_anchor is None:
            return
        # Capture line delta for the lines_changed callback BEFORE the
        # mutation — the selection range tells us how many newlines
        # are about to disappear.
        sel = self.get_selection()
        deleted_newlines = 0
        if sel is not None:
            (sl, _), (el, _) = sel
            deleted_newlines = el - sl
        self._delete_selection()
        self.render()
        if deleted_newlines and self.on_lines_changed:
            self.on_lines_changed(self.cur_line, -deleted_newlines)
        if self.on_change:
            self.on_change()

    def delete_range(self,
                     start: tuple[int, int],
                     end: tuple[int, int]) -> None:
        """Delete characters in `[start, end)`. Cursor lands at *start*."""
        if start == end:
            return
        if start > end:
            start, end = end, start
        # Route through the existing selection-delete to keep all the
        # bracket-pair / paired-quote logic in one place.
        self.sel_anchor = start
        self.cur_line, self.cur_col = end
        self.delete_selection()

    def replace_range(self,
                      start: tuple[int, int],
                      end: tuple[int, int],
                      text: str) -> None:
        """Replace `[start, end)` with *text*. Cursor lands at the end
        of the inserted text."""
        self.delete_range(start, end)
        if text:
            self._insert_text(text)
            self._ensure_visible()
            self.render()
            if self.on_change:
                self.on_change()

    # ──────────────────────────────────────────────────────────────────
    # Viewport / scrolling
    # ──────────────────────────────────────────────────────────────────

    def scroll_to_line(self, line: int) -> None:
        """Move the viewport so the given (0-indexed) line is visible
        near the top with a small overscan above for context."""
        idx = max(0, min(max(0, len(self.lines) - 1), line))
        # Convert physical line index → visual row (folds collapse).
        v = 0
        skip: int | None = None
        for i, txt in enumerate(self.lines):
            if skip is not None:
                ind = len(txt) - len(txt.lstrip())
                if txt.strip() and ind <= skip:
                    skip = None
                else:
                    continue
            if i == idx:
                break
            if i in self.folded:
                skip = len(txt) - len(txt.lstrip())
            v += 1
        self.scroll_y = max(0, v - 2)  # 2-row top overscan
        self.render()

    def ensure_visible(self) -> None:
        """Scroll the viewport (if needed) so the cursor line is in view."""
        self._ensure_visible()
        self.render()

    def visible_range(self) -> tuple[int, int]:
        """Return `(first_visual_row, last_visual_row)` currently painted.
        Both are visual-row indices (so folded ranges count as one row)."""
        h = self.canvas.winfo_height()
        first = self.scroll_y
        last = self.scroll_y + max(1, h // self._line_h) - 1
        return (first, last)

    # ──────────────────────────────────────────────────────────────────
    # Path / language
    # ──────────────────────────────────────────────────────────────────

    def set_filepath(self, path: str | None) -> None:
        """Associate the buffer with a file path AND derive the
        `language` attribute from it. Language-gated host code (LSP,
        debug, ruff, statusbar) reads `editor.language` instead of
        doing pygments `isinstance` checks."""
        super().set_filepath(path)
        self.language = language_from_path(path)
