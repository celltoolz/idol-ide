"""CanvasCodeView — canvas-rendered code editor.

Sole editor engine in IDOL. Renders text by drawing on a tk.Canvas
(no tk.Text widget, no pygments) so theme swaps are a palette dict
swap, syntax highlighting is a regex-rule pass, and adding a new
language is one entry in the rule table.

The public API (`get_text`, `set_text`, `get_cursor`, `set_cursor`,
`insert`, `delete_selection`, `set_diagnostics`, `set_breakpoints`,
`set_git_hunks`, `set_runtime_error_line`, `set_debug_line`, ...) is
the stable surface app.py and side widgets talk to. Engine internals
(`self.lines`, `self.cur_line`, `self.sel_anchor`, ...) are private —
host code should not reach in directly.
"""
from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont

from .breadcrumb_bar import BreadcrumbBar
from .canvas_editor.constants import (
    _CLOSERS,
    _FONT_FAMILY,
    _FONT_SIZE,
    _MINIMAP_W,
    _PAIRS,
)
from .canvas_editor.tokenizer import TokenizerMixin
from .canvas_editor.fold import (
    FoldMixin,
    _IDOL_BEGIN_RE,
    _IDOL_END_RE,
    _SECTION_MARKER,
)
from .canvas_editor.gutter import GutterMixin
from .canvas_editor.multicursor import MultiCursorMixin
from .canvas_editor.bracket_matcher import BracketMatcherMixin
from .canvas_editor.minimap import MinimapMixin
from .canvas_editor.autocomplete import AutocompleteMixin
from .scrollbar import HorizontalScrollbar, VerticalScrollbar


# ── Language detection ───────────────────────────────────────────────────────
# Filename extension → canonical language id. Used by `set_filepath`
# to populate `self.language`, which the host reads in place of the
# old pygments isinstance checks. Add new languages here as we wire
# syntax rules for them.
_LANGUAGE_BY_EXT = {
    ".py":      "python",
    ".pyw":     "python",
    ".pyi":     "python",
    ".js":      "javascript",
    ".jsx":     "javascript",
    ".ts":      "typescript",
    ".tsx":     "typescript",
    ".json":    "json",
    ".html":    "html",
    ".htm":     "html",
    ".css":     "css",
    ".md":      "markdown",
    ".markdown":"markdown",
    ".toml":    "toml",
    ".yaml":    "yaml",
    ".yml":     "yaml",
    ".sh":      "shell",
    ".bash":    "shell",
    ".bat":     "batch",
    ".cmd":     "batch",
    ".ps1":     "powershell",
    ".diff":    "diff",
    ".patch":   "diff",
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


# ── Themes ────────────────────────────────────────────────────────────────────
# Theme data lives in `themes/<theme-id>.json` at the project root and
# is loaded via `utils.theme_loader`. Each theme has a `palette`
# (UI colors) and a `tokens` map (category → (color, italic)). The
# tokenizer emits category NAMES; the renderer resolves them at draw
# time, so swapping themes is a one-call recolor.

from utils.theme_loader import list_themes as _list_themes, load_theme as _load_theme

_DEFAULT_THEME = "monokai-bright"

# Lines that sticky-scroll pins: only class/def/async def, mirroring
# IDOL/widgets/sticky_scroll.py:_SCOPE_RE. Generic block openers
# (if/for/while/with) are foldable but not pinned — they'd clutter
# the band on deeply-nested code.
_SCOPE_HEADER_RE = re.compile(r"^(\s*)(?:class\s|def\s|async\s+def\s)")

# Right-side breathing room for the text viewport. `_font.measure()`
# returns advance width, not visible-glyph width — italics + some
# Unicode glyphs paint a few pixels past their advance, so without
# padding the last char of a fully-scrolled long line gets clipped
# by the canvas edge (minimap hidden) or hidden under the minimap
# (minimap visible). 8px is enough for either case.
_TEXT_RIGHT_PAD = 8

# Matches a string literal whose contents are a CSS-style hex color.
_HEX_COLOR_RE = re.compile(
    r"""^(['"])#([0-9a-fA-F]{3}|[0-9a-fA-F]{6})\1$"""
)


def _extract_hex_color(token_text: str) -> str | None:
    """If *token_text* is a quoted hex-color literal (e.g. `"#FF00AA"`),
    return the hex color as `#RRGGBB`. Otherwise None."""
    m = _HEX_COLOR_RE.match(token_text)
    if not m:
        return None
    digits = m.group(2)
    if len(digits) == 3:                 # expand #RGB → #RRGGBB
        digits = "".join(ch * 2 for ch in digits)
    return f"#{digits}"


class CanvasCodeView(TokenizerMixin, FoldMixin, GutterMixin, MultiCursorMixin, BracketMatcherMixin, MinimapMixin, AutocompleteMixin, tk.Frame):
    """Canvas-rendered code editor.

    Indices follow the same convention throughout: 0-indexed line and
    column. A selection is `((start_line, start_col), (end_line,
    end_col))` with `start <= end` and *end* exclusive.
    """

    def __init__(self, master, theme: str = _DEFAULT_THEME, **kw):
        available = set(_list_themes())
        resolved = theme if theme in available else _DEFAULT_THEME
        if resolved not in available:
            # No themes on disk at all — fall back to a synthesized
            # minimal palette so the editor at least starts up.
            self._theme_name = "fallback"
            self._palette = {
                "bg": "#1e1e1e", "fg": "#d4d4d4", "caret": "#aeafad",
                "select_bg": "#264f78", "current_line_bg": "#2a2d2e",
                "guide": "#404040", "guide_active": "#707070",
                "gutter_bg": "#1e1e1e", "gutter_fg": "#858585",
                "gutter_fg_active": "#c6c6c6",
                "bracket_match": "#888888", "word_occurrence": "#2e3942",
                "fold_dots": "#858585",
                "sticky_bg": "#252526", "sticky_border": "#3e3e3e",
                "diag_error": "#f14c4c", "diag_warning": "#dcdcaa",
                "diag_info": "#75beff",
                "find_match": "#623f00", "find_current": "#ffa500",
                "minimap_bg": "#1e1e1e", "minimap_viewport": "#37373d",
            }
            self._token_style = {}
        else:
            self._theme_name = resolved
            data = _load_theme(self._theme_name)
            self._palette = data["palette"]
            self._token_style = data["tokens"]
        super().__init__(master, bg=self._palette["bg"], **kw)
        self._build_ui()
        self._init_state()
        self._wire_events()
        self.after(500, self._blink_cursor)
        self.after_idle(self.render)

    # ── Font switching ───────────────────────────────────────────────────────

    def set_font(self, family: str, size: int,
                 weight: str = "normal", slant: str = "roman") -> None:
        """Change the editor font globally. Reconfigures the tkfont objects
        in place so every canvas draw call picks up the new face immediately."""
        self._font.configure(family=family, size=size, weight=weight, slant=slant)
        self._font_italic.configure(family=family, size=size,
                                    weight=weight, slant="italic")
        self._char_w  = self._font.measure("W")
        self._line_h  = self._font.metrics("linespace") + 2
        self._compute_gutter()
        # Invalidate all pixel-width caches — measurements change with the font.
        self._file_max_w_dirty = True
        self._content_w_cache  = 0
        self._mm_lines_cache   = []   # force minimap content rebuild
        if self._ac_listbox is not None:
            self._ac_listbox.configure(font=(family, max(8, size - 1)))
        self.render()

    # ── Theme switching ──────────────────────────────────────────────────────

    def set_theme(self, name: str) -> None:
        """Swap the active theme. Re-derives palette + token colors and
        triggers a full redraw. No tokenizer rebuild — rules emit category
        names that resolve against the active theme at draw time."""
        if name == self._theme_name or name not in _list_themes():
            return
        self._theme_name = name
        data = _load_theme(name)
        self._palette = data["palette"]
        self._token_style = data["tokens"]
        self.configure(bg=self._palette["bg"])
        self.canvas.configure(bg=self._palette["bg"])
        self.render()

    # ── Public hooks ─────────────────────────────────────────────────────────

    def set_runtime_error_line(self, lineno: int | None) -> None:
        """Mark *lineno* (1-indexed, or None to clear) as the line where
        the most recent traceback fired. Renders a dim amber background
        on that row so the user can find the crash site."""
        self._runtime_error_line = (lineno - 1) if lineno else None
        self.render()

    def set_debug_line(self, lineno: int | None) -> None:
        """Mark *lineno* (1-indexed) as the currently-paused line under
        a debug session. Renders a yellow row band so the user can see
        where execution stopped. None clears the highlight."""
        self._debug_line = (lineno - 1) if lineno else None
        self.render()

    def set_breakpoints(self, lines) -> None:
        """Sync the breakpoint-dot set from the host. *lines* is a
        collection of 0-indexed physical line numbers. The engine
        DOES NOT own breakpoint state when a host is wired — it just
        renders whatever the host pushes via this method."""
        self._breakpoints = set(int(ln) for ln in lines)
        self.render()

    def set_git_hunks(self, hunks) -> None:
        """Sync git-diff gutter stripes from the host. *hunks* is a
        list of `(start_line_1, count, kind)` tuples — same shape
        `git_manager` produces for the legacy linenums widget. `kind`
        is "added" | "modified" | "deleted". Stored as a 0-indexed
        line → kind map and rendered as a 3 px stripe at the far-left
        of the gutter."""
        self._git_hunk_map = {}
        for start, count, kind in (hunks or []):
            # Legacy hunks use 1-indexed line numbers; canvas engine
            # uses 0-indexed. Width is `max(count, 1)` so deletions
            # (count=0 in the diff sense) still get a single-line
            # marker.
            for ln in range(start, start + max(count, 1)):
                self._git_hunk_map[ln - 1] = kind
        self.render()

    def set_diagnostics(self, diags: list[dict]) -> None:
        """Replace the diagnostics list and re-render. Each entry:
        `{"line": int, "col_start": int, "col_end": int,
          "severity": "error"|"warning"|"info", "message": str}`."""
        self._diagnostics = list(diags)
        self.render()

    def set_text(self, text: str) -> None:
        """Replace buffer contents (newline-separated) and re-render."""
        self.lines = text.split("\n")
        self.cur_line = 0
        self.cur_col = 0
        self.sel_anchor = None
        self._undo_stack.clear()
        self._redo_stack.clear()
        self._undo_op = ""
        self.scroll_y = 0
        self._scroll_x = 0
        self.folded.clear()
        self._file_max_w_dirty = True
        self._ml_state = self._scan_triple_state(self.lines)
        # Invalidate the content-width cache BEFORE render so the
        # horizontal scrollbar fractions reflect the new line set on
        # the very first paint.
        self.render()
        self._fire_change()

    def get_text(self) -> str:
        return "\n".join(self.lines)

    def _fire_change(self) -> None:
        """Notify the host that the buffer changed. Called from every
        editing path that mutates `self.lines` (keystroke insert/
        delete, line move/duplicate, comment toggle, paste, cut, etc.)
        so app.py can mark the tab dirty, schedule LSP didChange, and
        refresh the outline without polling."""
        self._ml_state = self._scan_triple_state(self.lines)
        self._file_max_w_dirty = True
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:
                pass

    # ── Undo / Redo ───────────────────────────────────────────────────────────

    _UNDO_LIMIT = 200

    def _push_undo(self, op: str = "") -> None:
        """Snapshot the buffer before a mutation.

        op is a short tag used for coalescing: consecutive pushes with
        the same non-empty op (e.g. "insert_char") collapse into one
        undo entry so the user undoes whole words, not single chars.
        Any cursor movement or different op breaks the chain.
        """
        self._redo_stack.clear()
        if op and op == self._undo_op:
            return  # coalesce — reuse existing snapshot
        self._undo_stack.append(
            (list(self.lines), self.cur_line, self.cur_col, self.sel_anchor)
        )
        if len(self._undo_stack) > self._UNDO_LIMIT:
            del self._undo_stack[0]
        self._undo_op = op

    def _undo(self) -> None:
        if not self._undo_stack:
            return
        self._redo_stack.append(
            (list(self.lines), self.cur_line, self.cur_col, self.sel_anchor)
        )
        lines, cl, cc, sa = self._undo_stack.pop()
        self.lines = lines
        self.cur_line = cl
        self.cur_col  = min(cc, len(lines[cl]))
        self.sel_anchor = sa
        self._undo_op = ""
        self._file_max_w_dirty = True
        self._fire_change()
        self.render()

    def _redo(self) -> None:
        if not self._redo_stack:
            return
        self._undo_stack.append(
            (list(self.lines), self.cur_line, self.cur_col, self.sel_anchor)
        )
        lines, cl, cc, sa = self._redo_stack.pop()
        self.lines = lines
        self.cur_line = cl
        self.cur_col  = min(cc, len(lines[cl]))
        self.sel_anchor = sa
        self._undo_op = ""
        self._file_max_w_dirty = True
        self._fire_change()
        self.render()

    @property
    def can_undo(self) -> bool:
        return bool(self._undo_stack)

    @property
    def can_redo(self) -> bool:
        return bool(self._redo_stack)

    def set_filepath(self, path: str | None) -> None:
        """Associate the buffer with a file path. Updates `self.language`
        (LSP / lint targeting) and refreshes the breadcrumb."""
        self.filepath = path
        self.language = language_from_path(path)
        self._refresh_breadcrumb()

    # ── Public buffer API ─────────────────────────────────────────────────────

    def get_line(self, n: int) -> str:
        """Return the n-th line (0-indexed). `""` if out of range."""
        return self.lines[n] if 0 <= n < len(self.lines) else ""

    def line_count(self) -> int:
        return len(self.lines)

    # ── Public cursor / selection API ────────────────────────────────────────

    def get_cursor(self) -> tuple[int, int]:
        """Return `(line, col)` — both 0-indexed."""
        return (self.cur_line, self.cur_col)

    def set_cursor(self, line: int, col: int) -> None:
        """Place the cursor at `(line, col)`, clamping to the buffer.
        Clears any active selection and ensures the line is visible."""
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
        """Return `(start, end)` with `start <= end`, or `None`. End is
        exclusive."""
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
        """Select `[start, end)`. Places the cursor at *end*."""
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
        """Return the currently-selected text (empty if none).
        Multi-line selections include the `\\n` joiners."""
        return self._selected_text()

    # ── Public editing API ───────────────────────────────────────────────────

    def insert(self, text: str) -> None:
        """Insert *text* at the cursor, replacing any active selection."""
        if not text:
            return
        before_line = self.cur_line
        self._insert_text(text)
        self._ensure_visible()
        self.render()
        added_newlines = text.count("\n")
        if added_newlines and self.on_lines_changed:
            self.on_lines_changed(before_line, added_newlines)

    def delete_selection(self) -> None:
        if self.sel_anchor is None:
            return
        sel = self.get_selection()
        deleted_newlines = 0
        if sel is not None:
            (sl, _), (el, _) = sel
            deleted_newlines = el - sl
        self._delete_selection()
        self.render()
        if deleted_newlines and self.on_lines_changed:
            self.on_lines_changed(self.cur_line, -deleted_newlines)
        # `_delete_selection` doesn't fire change itself — the host
        # callers (replace_range, delete_range) rely on the per-method
        # fire in `_insert_text` / etc. to land that side effect.

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

    # ── Public viewport API ──────────────────────────────────────────────────

    def scroll_to_line(self, line: int) -> None:
        """Move the viewport so the (0-indexed) line is centered vertically."""
        idx = max(0, min(max(0, len(self.lines) - 1), line))
        v = 0
        skip: int | None = None
        for i, txt in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(txt):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if txt.strip():
                        ind = len(txt) - len(txt.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(txt)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(txt) - len(txt.lstrip())
                    if txt.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            if i == idx:
                break
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(txt):
                    skip = -1
                elif _SECTION_MARKER.match(txt):
                    skip = -(len(txt) - len(txt.lstrip()) + 2)
                else:
                    skip = len(txt) - len(txt.lstrip())
            v += 1
        visible_rows = max(1, self.canvas.winfo_height() // self._line_h)
        self.scroll_y = max(0, v - visible_rows // 2)
        self.render()

    def ensure_visible(self) -> None:
        """Scroll if needed so the cursor line is in view."""
        self._ensure_visible()
        self.render()

    def visible_range(self) -> tuple[int, int]:
        """Return `(first_visual_row, last_visual_row)` currently painted."""
        h = self.canvas.winfo_height()
        first = self.scroll_y
        last = self.scroll_y + max(1, h // self._line_h) - 1
        return (first, last)

    # ── Scrollbar protocol ────────────────────────────────────────────────────
    # The custom VerticalScrollbar / HorizontalScrollbar widgets call
    # the bound `command` with either ("moveto", frac) or ("scroll",
    # delta, "units"|"pages"). They expect `set(first, last)` to be
    # called back whenever the scroll position changes.

    def yview(self, *args) -> tuple[float, float] | None:
        if not args:
            return self._yview_fractions()
        op = args[0]
        total = max(1, self._visual_row_count())
        visible = max(1, self.canvas.winfo_height() // self._line_h)
        if op == "moveto":
            frac = float(args[1])
            self.scroll_y = max(0, min(total - 1,
                                       int(frac * total)))
        elif op == "scroll":
            delta = int(args[1])
            unit = args[2] if len(args) > 2 else "units"
            step = delta * (visible if unit == "pages" else 1)
            self.scroll_y = max(0, min(max(0, total - 1),
                                       self.scroll_y + step))
        self.render()
        return None

    def yview_moveto(self, fraction: float) -> None:
        self.yview("moveto", fraction)

    def xview(self, *args) -> tuple[float, float] | None:
        if not args:
            return self._xview_fractions()
        op = args[0]
        content_w = max(self._content_width(), self._file_max_w)
        visible_w = self._visible_text_width()
        max_scroll = max(0, content_w - visible_w)
        if op == "moveto":
            frac = float(args[1])
            self._scroll_x = max(0, min(max_scroll, int(frac * content_w)))
        elif op == "scroll":
            delta = int(args[1])
            unit = args[2] if len(args) > 2 else "units"
            if unit == "pages":
                step = max(self._char_w, visible_w - self._char_w * 2)
            else:
                # Match the vertical wheel: one notch = ~3 character widths.
                step = self._char_w * 3
            self._scroll_x = max(0, min(max_scroll,
                                        self._scroll_x + delta * step))
        self.render()
        return None

    def _yview_fractions(self) -> tuple[float, float]:
        total = max(1, self._visual_row_count())
        visible = max(1, self.canvas.winfo_height() // self._line_h)
        first = self.scroll_y / total
        last = min(1.0, (self.scroll_y + visible) / total)
        return (max(0.0, first), max(first, last))

    def _xview_fractions(self) -> tuple[float, float]:
        content_w = max(self._content_width(), self._file_max_w)
        if content_w == 0:
            return (0.0, 1.0)
        visible_w = self._visible_text_width()
        if content_w <= visible_w:
            return (0.0, 1.0)
        first = self._scroll_x / content_w
        last = min(1.0, (self._scroll_x + visible_w) / content_w)
        return (max(0.0, first), max(first, last))

    def _visible_text_width(self) -> int:
        """Width of the text-area viewport in pixels — what
        horizontal-scroll math + caret-into-view clamping should
        compare against.

        Subtracts:
          • `_text_x` — gutter (line numbers + fold markers) on the
            left, never available for text.
          • `_MINIMAP_W` — minimap strip on the right, but ONLY when
            the minimap is currently visible. With it hidden, the
            full right side of the canvas is fair game for text.
          • `_TEXT_RIGHT_PAD` — small safety margin so the last char
            of a fully-scrolled long line isn't clipped by the
            canvas edge or hidden under the minimap.

        Does NOT subtract the vertical scrollbar width — `_vs` is a
        sibling grid column, not a canvas overlay, so the canvas's
        own `winfo_width()` doesn't include it. Returns at least 1
        so divisions stay safe."""
        cw = self.canvas.winfo_width()
        minimap_reserve = _MINIMAP_W if getattr(
            self, "_mm_visible", True
        ) else 0
        return max(1, cw - self._text_x - minimap_reserve - _TEXT_RIGHT_PAD)

    def _content_width(self) -> int:
        """Maximum line width across the VISIBLE rows, in pixels.

        Drives the horizontal scrollbar's range + clamping. We
        deliberately measure only what's on-screen — using the file-
        wide max would size the scrollbar for a line that may be
        scrolled out of view vertically, so the user drags H-scroll
        right and sees empty canvas because their *current* line
        already fits.

        Set in `render()` from the actual draw-time cumulative-x of
        each visible row's token loop, so italics, hex-preview
        squares, and folded "···" indicators are all accounted for —
        max_scroll always lines up with what was actually drawn."""
        return self._content_w_cache

    @property
    def _text_x0(self) -> int:
        """Text-area x origin with horizontal scroll applied. Use this
        instead of `_text_x` for ANY canvas item that should scroll
        horizontally with the buffer (tokens, selection, find-match,
        diagnostics, cursor, indent guides). Gutter / minimap /
        sticky-band positions stay fixed to `_text_x` because they
        aren't part of the scrollable text region."""
        return self._text_x - self._scroll_x

    def _push_scroll_fractions(self) -> None:
        """Push the current scroll state to both scrollbar widgets.
        Also self-heals `_scroll_x` if a previous code path left it
        past `content_width - viewport_width` — that's how text used
        to bleed into the gutter after tab switches."""
        try:
            # Recompute file-wide max width when dirty (any edit or set_text).
            # Pre-filter with cheap font.measure; only call the accurate
            # _measure_to_col (italic + color-swatch aware) on lines that
            # are actually long enough to overflow the viewport. This keeps
            # the scrollbar range stable before a long line scrolls into view.
            if self._file_max_w_dirty:
                vw = self._visible_text_width()
                min_chars = max(1, vw // max(1, self._char_w))
                max_w = 0
                for l in self.lines:
                    if len(l) < min_chars:
                        continue
                    w = self._measure_to_col(l, len(l))
                    if w > max_w:
                        max_w = w
                self._file_max_w = max_w
                self._file_max_w_dirty = False
            visible_w = self._visible_text_width()
            content_w = max(self._content_width(), self._file_max_w)
            if visible_w >= self._char_w:
                if content_w <= visible_w:
                    self._scroll_x = 0
                else:
                    max_scroll = max(0, content_w - visible_w)
                    if self._scroll_x > max_scroll:
                        self._scroll_x = max_scroll
            self._vs.set(*self._yview_fractions())
            self._hs.set(*self._xview_fractions())
        except Exception:
            pass
        if self.on_scroll is not None:
            self.on_scroll(*self._yview_fractions())

    def _goto_line(self, line: int) -> None:
        """Breadcrumb navigation target — center the given line in the
        viewport. *line* is 1-indexed (matches BreadcrumbBar API)."""
        idx = max(0, min(len(self.lines) - 1, line - 1))
        self.cur_line = idx
        self.cur_col = 0
        self.sel_anchor = None
        self.scroll_to_line(idx)  # centers viewport; also calls render()
        self.canvas.focus_set()

    def _refresh_breadcrumb(self) -> None:
        pass  # app.py's 25 ms _highlight_active_line loop owns all crumb updates

    # ── Setup ─────────────────────────────────────────────────────────────────
    # `_compute_gutter` (gutter layout math) lives in GutterMixin.

    def _build_ui(self) -> None:
        self._font = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE)
        self._font_italic = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE,
                                        slant="italic")
        self._char_w = self._font.measure("W")
        self._line_h = self._font.metrics("linespace") + 2
        self._compute_gutter()

        # ── Grid layout ──────────────────────────────────────────────
        #   row 0 — breadcrumb bar (full width)
        #   row 1 — find/replace bar (full width, hidden by default)
        #   row 2 — canvas (col 0) + vertical scrollbar (col 1)
        #   row 3 — horizontal scrollbar (col 0)
        # Content row + canvas column expand; everything else hugs.
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        # Breadcrumb — passes through `get_line` and a highlight_fn that
        # tokenizes with the canvas engine so the locals preview uses the
        # active theme's colours.
        def _crumb_highlight(text: str) -> list[tuple[str, str]]:
            fg = self._palette.get("fg", "#cccccc")
            result = []
            for tok_text, cat in self._tokenize(text):
                if not tok_text:
                    continue
                spec = self._token_style.get(cat) if cat else None
                result.append((tok_text, spec[0] if spec else fg))
            return result

        self.breadcrumb = BreadcrumbBar(
            self,
            on_navigate=self._goto_line,
            get_line=lambda ln: (self.lines[ln - 1]
                                 if 0 < ln <= len(self.lines) else ""),
            highlight_fn=_crumb_highlight,
        )
        self.breadcrumb.grid(row=0, column=0, columnspan=2, sticky="ew")

        # Row 1 reserved for a future find/replace strip — the engine's
        # original internal bar was removed in favor of IDOL's shared
        # `FindReplaceBar` (Ctrl+F handler in `_new_canvas_tab`). Grid
        # row stays empty; row 2 is the editor content.

        self.canvas = tk.Canvas(
            self, bg=self._palette["bg"], highlightthickness=0,
            takefocus=True, cursor="xterm",
        )
        self.canvas.grid(row=2, column=0, sticky="nswe")

        # Scrollbars — same custom widgets the rest of IDOL uses, wired
        # to the editor's row-based scroll model via yview/xview below.
        # autohide=True keeps the tracks out of the way when content
        # fits (mirrors the CodeView treatment).
        self._vs = VerticalScrollbar(self, autohide=True, width=16,
                                     command=self.yview)
        self._vs.grid(row=2, column=1, sticky="ns")
        self._hs = HorizontalScrollbar(self, autohide=True, height=16,
                                       command=self.xview)
        self._hs.grid(row=3, column=0, sticky="we")
        # Horizontal scroll offset (pixels). Pairs with
        # `_content_w_cache` (the widest visible line, set by render)
        # to drive the H-scrollbar's range; both start at 0 so the
        # very-first paint doesn't see an unset cache.
        self._scroll_x: int = 0
        self._content_w_cache: int = 0
        # Sticky-scroll band lives on its OWN embedded canvas so the main
        # canvas's `delete("all")` in render() can't wipe it on every
        # wheel tick (that was the source of the scroll-flicker). We only
        # redraw its content when the visible header set or theme changes;
        # plain scrolls within the same scope are zero-cost for sticky.
        self._sticky_canvas = tk.Canvas(
            self.canvas, bg=self._palette.get("sticky_bg", self._palette["bg"]),
            highlightthickness=0, bd=0, takefocus=False,
        )
        self._sticky_canvas.place_forget()
        self._sticky_last_headers: tuple[int, ...] = ()
        self._sticky_last_theme: str | None = None
        self._sticky_last_place: tuple[int, int, int, int] | None = None
        self._build_minimap()

    # (Removed: the legacy internal find/replace bar — `_build_find_bar`,
    # `show_find_bar`/`hide_find_bar`, `_find_recompute`, `_find_step`,
    # `_find_jump_to`, `_replace_one`, `_replace_all`. Replaced by IDOL's
    # shared `widgets/find_replace.py:FindReplaceBar`, wired through
    # `app.py:_new_canvas_tab` on Ctrl+F. `_find_matches` /
    # `_find_current_idx` (set by the shared bar via
    # `set_find_matches`) now live in `_init_state` as the only
    # find-state attrs the engine still owns.)

    def _init_state(self) -> None:
        self.lines: list[str] = [""]
        self.cur_line: int = 0
        self.cur_col: int = 0
        self.sel_anchor: tuple[int, int] | None = None
        self._mc_cursors: list[tuple[int, int]] = []   # secondary cursor positions
        self._mc_anchors: list[tuple[int, int] | None] = []  # selection anchor per cursor
        self.cursor_visible: bool = True
        self.folded: set[int] = set()
        self._breakpoints: set[int] = set()
        self._hover_breakpoint_line: int | None = None
        # Host hook — fires when the user clicks the debug gutter on a
        # line. Receives the 0-indexed physical line. When set, the
        # engine does NOT toggle `_breakpoints` itself — the host owns
        # the canonical store and calls back via `set_breakpoints` to
        # sync the dot rendering. When None (standalone preview), the
        # engine falls back to local toggle so the dots still work.
        self.on_breakpoint_toggle = None
        # Git diff stripe map — 0-indexed line → kind
        # ("added"/"modified"/"deleted"). Populated by `set_git_hunks`,
        # rendered as a 3 px colored bar in the far-left of the
        # gutter. Mirrors the legacy `TkLineNumbers._hunk_map`.
        self._git_hunk_map: dict[int, str] = {}
        # Runtime-error line — set by `set_runtime_error_line` when a
        # subprocess run crashes. 0-indexed; None when no error.
        # Renders as an amber row-background on the affected line.
        self._runtime_error_line: int | None = None
        # Debugger paused line — set by `set_debug_line` when the
        # debugger stops at a breakpoint or after a step. Yellow row.
        self._debug_line: int | None = None
        # Active-line highlight controls — set by the host at runtime.
        # highlight_active_line=False suppresses the band entirely.
        # active_line_color overrides the theme's current_line_bg when set.
        self.tab_size: int = 4
        self._undo_stack: list = []   # (lines, cur_line, cur_col, sel_anchor)
        self._redo_stack: list = []
        self._undo_op: str = ""       # last push type — drives coalescing
        self.highlight_active_line: bool = True
        self._active_line_color: str | None = None
        # ── Host hooks for context-menu items ────────────────────
        # When set, the right-click menu includes the corresponding
        # entry. None → item omitted. Lets the engine ship a richer
        # menu when embedded in IDOL (Go to Def / Find References /
        # Run Line / Run Selection / Find & Replace) but stay
        # minimal in the standalone preview where these don't apply.
        self.on_request_goto_definition = None
        self.on_can_goto_definition = lambda: True   # overridden by host to gate on LSP
        self.on_request_find_references = None
        self.on_request_find_replace = None
        self.on_request_run_line = None
        self.on_request_run_selection = None
        # Hit-test rectangles for the "···" indicators drawn after each
        # folded line. Rebuilt every render. Each entry is
        # (x1, y1, x2, y2, physical_line_index).
        self._fold_dot_rects: list[tuple[float, float, float, float, int]] = []
        # Diagnostics — list of dicts: {"line": int, "col_start": int,
        # "col_end": int, "severity": "error"|"warning"|"info",
        # "message": str}. Render draws a squiggly underline; eventual
        # LSP integration calls set_diagnostics() to update.
        self._diagnostics: list[dict] = []
        # Find/Replace highlights — populated by `set_find_matches`.
        # Each entry is `((start_line, start_col), (end_line, end_col))`
        # with 0-indexed positions. `_find_current_idx` (>=0) marks the
        # currently-focused match and renders in a brighter color.
        self._find_matches: list[tuple[tuple[int, int], tuple[int, int]]] = []
        self._find_current_idx: int = -1
        # Host callback hooks — wired by `CanvasCodeView` consumers
        # (app.py for the editor tab path). Fired from `_fire_change`
        # after every buffer mutation so dirty tracking, outline
        # refresh, and LSP didChange notifications can fan out.
        self.on_change = None
        self.on_cursor_move = None
        self.on_lines_changed = None
        self.on_copy = None
        self.on_bad_paste = None
        # Autocomplete provider — async callback the host wires to a
        # completion source (LSP, jedi, etc.). Signature:
        #     callable(prefix: str, trigger_char: str|None,
        #              callback: Callable[[list[str]], None]) -> None
        # The host fires the request and invokes `callback(items)` when
        # the response arrives. None means use the synchronous
        # buffer-word fallback. A sequence number guards against stale
        # responses overwriting a fresher request (mirrors IDOL's
        # _completion_seq in app.py).
        self.on_completion_request = None
        self._ac_seq: int = 0
        # Scroll hook — fired from _push_scroll_fractions after each render.
        # Signature: callable(first: float, last: float) -> None
        self.on_scroll = None
        # File path the buffer is backed by — passed to LSP via the host.
        # `None` means scratch buffer / unsaved.
        self.filepath: str | None = None
        # Autocomplete popup state.
        self._ac_top: tk.Toplevel | None = None
        self._ac_listbox: tk.Listbox | None = None
        self._ac_items: list[str] = []
        self._ac_prefix: str = ""
        self.scroll_y: int = 0           # first visible visual row
        # File-wide max line width (pixels, regular font). Updated via
        # dirty flag in _fire_change / set_text; used by _xview_fractions
        # so the H-scrollbar stays visible whenever any line is long,
        # even when that line isn't currently in the viewport.
        self._file_max_w: int = 0
        self._file_max_w_dirty: bool = True
        # Per-line triple-quote state: None = line starts outside any triple-
        # quoted string; "'" or '"' = line starts inside one with that quote char.
        self._ml_state: list[str | None] = []

    def _wire_events(self) -> None:
        c = self.canvas
        c.bind("<Configure>",        lambda _: self.render())
        c.bind("<Motion>",           self._on_motion)
        c.bind("<Leave>",            self._on_leave)
        c.bind("<Button-1>",         self._on_click)
        c.bind("<B1-Motion>",        self._on_drag)
        c.bind("<Double-Button-1>",  self._on_double_click)
        c.bind("<Triple-Button-1>",  self._on_triple_click)
        c.bind("<Shift-Button-1>",   self._on_shift_click)
        c.bind("<Alt-Button-1>",     self._on_alt_click)
        c.bind("<Button-3>",         self._on_right_click)
        c.bind("<MouseWheel>",        self._on_mousewheel)
        c.bind("<Button-4>",          lambda _: (self._scroll(-3), "break")[1])
        c.bind("<Button-5>",          lambda _: (self._scroll(+3), "break")[1])
        # Shift+wheel — horizontal scroll. Same delta convention as
        # vertical (positive delta → "natural" left scroll).
        c.bind("<Shift-MouseWheel>",  self._on_shift_mousewheel)
        c.bind("<Shift-Button-4>",
               lambda _: (self.xview("scroll", -1, "units"), "break")[1])
        c.bind("<Shift-Button-5>",
               lambda _: (self.xview("scroll", +1, "units"), "break")[1])
        c.bind("<Key>",              self._on_key)
        c.bind("<FocusIn>",          lambda _: self.render())
        c.bind("<FocusOut>",         self._on_canvas_focus_out)
        # Virtual events fired by app.edit_undo/redo and the right-click
        # context menu so menu-triggered undo/redo reaches our stack.
        self.bind("<<Undo>>", lambda _: self._undo())
        self.bind("<<Redo>>", lambda _: self._redo())

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 2 or h < 2:
            return

        self._draw_gutter_background(c, h)

        # Fresh per-render hit-test list for the clickable "···"
        # indicators drawn after each folded line.
        self._fold_dot_rects = []
        # Track the actual rightmost rendered x across visible rows —
        # this becomes `_content_w_cache` at the end of render() and
        # drives horizontal scrollbar range. Measuring at draw time
        # (rather than from `font.measure(line)` over the whole file)
        # means italics, hex-preview squares, and folded "···"
        # indicators are all accounted for, AND the scrollbar's range
        # tracks what's actually on screen rather than the longest
        # line anywhere in the file.
        max_drawn_x = 0

        # Tier-2 per-render computations — bracket pair under cursor and
        # the word to highlight occurrences of.
        bracket_pair = self._find_bracket_pair()
        hi_word = self._cursor_word()
        word_pat = re.compile(rf"\b{re.escape(hi_word)}\b") if hi_word else None

        # Precompute per-line "effective indent" for guide-drawing. Blank
        # lines inherit min(prev_non_blank_indent, next_non_blank_indent)
        # so guides connect across blank lines INSIDE a block, but stop
        # when the block ends. Matches VS Code's indent-guide behavior.
        eff_indent = self._effective_indents()

        # Active indent guide — highlight only the segment that belongs to
        # the cursor's direct containing block, not every guide line at the
        # same column across the whole file.
        cur_text = self.lines[self.cur_line] if self.lines else ""
        cur_indent = len(cur_text) - len(cur_text.lstrip())
        active_level = cur_indent // 4
        # Vertical bounds of the containing block so the highlight doesn't
        # bleed into sibling or unrelated blocks at the same indent column.
        _guide_block_top    = 0
        _guide_block_bottom = len(self.lines) - 1
        if self.lines and active_level > 0:
            # Scan up: first non-blank line with indent < cur_indent is the opener.
            _opener_indent = 0
            for _j in range(self.cur_line - 1, -1, -1):
                _ln = self.lines[_j]
                if not _ln.strip():
                    continue
                _ind = len(_ln) - len(_ln.lstrip())
                if _ind < cur_indent:
                    _guide_block_top = _j
                    _opener_indent   = _ind
                    break
            # Scan down: first non-blank line with indent <= opener's indent
            # marks where the block closes; highlight ends just before it.
            for _j in range(self.cur_line + 1, len(self.lines)):
                _ln = self.lines[_j]
                if not _ln.strip():
                    continue
                if len(_ln) - len(_ln.lstrip()) <= _opener_indent:
                    _guide_block_bottom = _j - 1
                    break

        visible_rows = h // self._line_h + 1
        v_row = 0
        rendered = 0
        i = 0
        skip_indent: int | None = None
        skip_close_char: str | None = None
        while i < len(self.lines):
            line = self.lines[i]
            # Fold skip
            if skip_indent is not None:
                if skip_indent == -1:
                    # IDOL BEGIN…END fold: consume everything up to and
                    # including the matching END marker.
                    if _IDOL_END_RE.match(line):
                        skip_indent = None
                    i += 1
                    continue
                if skip_indent <= -2:
                    # Section fold: skip until next same-indent section
                    # header or a line at a lower indent level.
                    si = -(skip_indent + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip_indent = None  # fall through to render this line
                        else:
                            i += 1
                            continue
                    else:
                        i += 1
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip_indent:
                        # Pull a closing bracket / brace line INTO the fold
                        # (matches IDOL's _get_fold_range bracket inclusion).
                        if (skip_close_char is not None
                                and line.lstrip().startswith(skip_close_char)):
                            skip_indent = None
                            skip_close_char = None
                            i += 1
                            continue
                        skip_indent = None
                        skip_close_char = None
                    else:
                        i += 1
                        continue

            # Skip rows above scroll
            if v_row < self.scroll_y:
                v_row += 1
                if i in self.folded:
                    if _IDOL_BEGIN_RE.match(line):
                        skip_indent = -1
                        skip_close_char = None
                    elif _SECTION_MARKER.match(line):
                        skip_indent = -(len(line) - len(line.lstrip()) + 2)
                        skip_close_char = None
                    else:
                        skip_indent = len(line) - len(line.lstrip())
                        last = line.rstrip()[-1:] if line.rstrip() else ""
                        skip_close_char = (
                            {"(": ")", "[": "]", "{": "}"}.get(last)
                        )
                i += 1
                continue
            if rendered >= visible_rows:
                break

            y = (v_row - self.scroll_y) * self._line_h

            # Current-line highlight (only when no selection)
            try:
                _focused = self.canvas.focus_get()
            except KeyError:
                _focused = None
            if (self.highlight_active_line
                    and i == self.cur_line and self.sel_anchor is None
                    and _focused is self.canvas):
                hl_color = self._active_line_color or self._palette["current_line_bg"]
                c.create_rectangle(self._gutter_w, y, w, y + self._line_h,
                                   fill=hl_color, outline="")

            # Runtime-error row (amber band — paints OVER the current-
            # line highlight when both apply, so the crash site stands
            # out even when the caret is on it).
            if self._runtime_error_line == i:
                c.create_rectangle(self._gutter_w, y, w, y + self._line_h,
                                   fill="#3d2500", outline="")

            # Debugger paused row (yellow band — set while the debug
            # session is stopped at this line).
            if self._debug_line == i:
                c.create_rectangle(self._gutter_w, y, w, y + self._line_h,
                                   fill="#2d2d00", outline="")

            # Selection
            self._draw_selection(i, line, y, w)
            self._draw_mc_selections(i, line, y, w)

            # Find/Replace match highlights — drawn under tokens so the
            # text reads on top. Iterates all matches and paints only
            # the ones that intersect the current line (cheap; a file
            # with thousands of matches still draws each line in O(M)
            # which is fine for typical search counts).
            self._draw_find_matches_on_line(i, line, y)

            # Indent guides — drive off effective indent so guides span
            # blank lines within the same block. Highlight the guide that
            # matches the cursor's containing block. Each guide is drawn
            # at the LEFT edge of its indent level (level 1 at col 0,
            # level 2 at col 4, etc.). Use font.measure on the literal
            # space prefix so the x-coordinate is EXACTLY what
            # font.measure(line[:col]) gives for the caret — keeps the
            # caret pixel-aligned with the guide regardless of subtle
            # font-metric rounding between "W" and " ".
            guide_dim = self._palette["guide"]
            guide_hi  = self._palette.get("guide_active", guide_dim)
            text_x0 = self._text_x0  # cache for the per-line draw loops below
            for level in range(1, eff_indent[i] // 4 + 1):
                gx = text_x0 + self._font.measure(" " * ((level - 1) * 4))
                color = (guide_hi
                         if level == active_level
                         and _guide_block_top <= i <= _guide_block_bottom
                         else guide_dim)
                c.create_line(gx, y, gx, y + self._line_h, fill=color)

            # Gutter content (breakpoint, git stripe, line number, fold
            # marker) is drawn AT THE END of this row block — after the
            # tokens — so it overpaints any glyph that scrolled left of
            # `_text_x` when `_scroll_x > 0`. See the gutter-mask block
            # near the caret draw at the bottom of the row loop.

            # Find/Replace match highlights are painted by
            # `_draw_find_matches_on_line` (called earlier in this
            # row's draw block). The sandbox's legacy inline-render
            # path was removed when we switched to the IDOL Find/
            # Replace bar — `self._find_matches` now uses the nested-
            # tuple format set by `set_find_matches`.

            # Word-occurrence highlights — dim backgrounds on every
            # other instance of the word currently under the cursor.
            # Drawn BEFORE tokens so the text reads on top.
            if word_pat is not None:
                cur_match_col = (
                    self._cursor_word_start_col() if i == self.cur_line else None
                )
                wo_color = self._palette.get(
                    "word_occurrence", self._palette["current_line_bg"]
                )
                for m in word_pat.finditer(line):
                    if cur_match_col == m.start():
                        continue   # skip the one the cursor's on
                    x1 = text_x0 + self._measure_to_col(line, m.start())
                    x2 = text_x0 + self._measure_to_col(line, m.end())
                    c.create_rectangle(x1, y, x2, y + self._line_h,
                                       fill=wo_color, outline="")

            # Tokens — resolve each category against the active theme,
            # using the italic font when the category specifies it.
            x = text_x0
            fg = self._palette["fg"]
            for txt, cat in self._tokenize(line, i):
                if cat is None:
                    color, italic = fg, False
                else:
                    color, italic = self._token_style.get(cat, (fg, False))
                font = self._font_italic if italic else self._font
                # Color preview square BEFORE hex-color string literals.
                # Small square (line_h - 10) so it reads as an indicator,
                # not a label.
                hex_color = _extract_hex_color(txt) if cat == "string" else None
                if hex_color:
                    sq = max(6, self._line_h - 10)
                    sx = x + 1
                    sy = y + (self._line_h - sq) // 2
                    c.create_rectangle(sx, sy, sx + sq, sy + sq,
                                       fill=hex_color, outline=fg)
                    x += sq + 3
                c.create_text(x, y + 1, text=txt, anchor="nw",
                              fill=color, font=font)
                x += font.measure(txt)

            # Subtract text_x0 so the cached width is scroll-independent
            # (the value that `_content_width()` compares against).
            line_drawn_w = x - text_x0
            if line_drawn_w > max_drawn_x:
                max_drawn_x = line_drawn_w

            # Bracket-match outline — drawn AFTER tokens so it overlays.
            if bracket_pair is not None:
                for (r, col) in bracket_pair:
                    if r != i:
                        continue
                    bx1 = text_x0 + self._measure_to_col(line, col)
                    bx2 = text_x0 + self._measure_to_col(line, col + 1)
                    c.create_rectangle(
                        bx1, y + 1, bx2, y + self._line_h - 1,
                        outline=self._palette.get("bracket_match", fg),
                        fill="",
                    )

            # Diagnostic squigglies — drawn AFTER tokens so the wave
            # sits under the text.
            for diag in self._diagnostics:
                if diag.get("line") != i:
                    continue
                cs = diag.get("col_start", 0)
                ce = diag.get("col_end", len(line))
                sev = diag.get("severity", "error")
                key = f"diag_{sev}"
                dcolor = self._palette.get(key, self._palette.get("diag_error", "#f14c4c"))
                sx = text_x0 + self._measure_to_col(line, cs)
                ex = text_x0 + self._measure_to_col(line, ce)
                self._draw_squiggly(sx, ex, y + self._line_h - 2, dcolor)

            # Folded "···" indicator after the line's tokens. Clickable
            # to unfold — record its hit-test rect.
            if i in self.folded:
                dots_x = x + 6
                c.create_text(
                    dots_x, y + self._line_h // 2, text="···", anchor="w",
                    fill=self._palette.get("fold_dots",
                                           self._palette["gutter_fg"]),
                    font=self._font,
                )
                dots_w = self._font.measure("···")
                self._fold_dot_rects.append(
                    (dots_x - 2, y, dots_x + dots_w + 4, y + self._line_h, i)
                )

            # Caret
            if (i == self.cur_line and self.cursor_visible
                    and self.sel_anchor is None):
                cx = text_x0 + self._measure_to_col(line, self.cur_col)
                c.create_line(cx, y + 1, cx, y + self._line_h - 1,
                              fill=self._palette["caret"], width=1)

            # Secondary carets (multi-cursor) — same blinking | as primary
            if self.cursor_visible and self._mc_cursors:
                for mc_l, mc_c in self._mc_cursors:
                    if mc_l == i:
                        mcx = text_x0 + self._measure_to_col(
                            line, min(mc_c, len(line)))
                        c.create_line(mcx, y + 1, mcx, y + self._line_h - 1,
                                      fill=self._palette["caret"], width=1)

            # Gutter content (overlay mask, git stripe, breakpoint, line
            # number, fold marker) — drawn AFTER the tokens so it overpaints
            # any glyph that scrolled left of `_text_x` when `_scroll_x > 0`.
            self._draw_gutter_row(c, i, y)

            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip_indent = -1
                    skip_close_char = None
                elif _SECTION_MARKER.match(line):
                    skip_indent = -(len(line) - len(line.lstrip()) + 2)
                    skip_close_char = None
                else:
                    skip_indent = len(line) - len(line.lstrip())
                    last = line.rstrip()[-1:] if line.rstrip() else ""
                    skip_close_char = (
                        {"(": ")", "[": "]", "{": "}"}.get(last)
                    )
            v_row += 1
            rendered += 1
            i += 1

        # Minimap on the right edge — an embedded `tk.Text` placed via
        # `create_window`. The widget always renders on top of canvas
        # items, so sticky-scroll can no longer paint over it (which is
        # the IDOL behavior too — minimap stays visible).
        self._update_minimap()

        # Sticky scroll overlay — ancestor block-header lines pinned at
        # top of the viewport so context is visible while scrolled into
        # a nested block. Drawn LAST so it covers the regular rows.
        self._draw_sticky_headers()

        # Stash the measured visible-rows width so `_content_width()`
        # (called by the scrollbar push below) returns the value that
        # matches what was actually painted this frame.
        self._content_w_cache = max_drawn_x

        # Sync chrome widgets — scrollbars track scroll_y, breadcrumb
        # tracks cur_line. Both are cheap when state hasn't changed
        # (scrollbar widgets compare-and-redraw; breadcrumb has its
        # own key-based cache in update_crumbs).
        self._push_scroll_fractions()
        self._refresh_breadcrumb()

    def _draw_sticky_headers(self) -> None:
        """Update the embedded sticky-scroll canvas. Only redraws content
        when the header set or theme changes — typical scroll-within-block
        is a no-op, which kills the flicker the canvas-item version had."""
        headers = self._sticky_headers()
        sc = self._sticky_canvas
        if not headers:
            if self._sticky_last_place is not None:
                sc.place_forget()
                self._sticky_last_place = None
                self._sticky_last_headers = ()
            return
        cw = self.canvas.winfo_width()
        # Stop the band before the minimap (mirrors the main canvas's
        # rendering clip).
        sw = cw - _MINIMAP_W if cw - _MINIMAP_W >= self._text_x + 20 else cw
        bar_h = len(headers) * self._line_h
        sticky_border = self._palette.get(
            "sticky_border", self._palette.get("guide", "#404040")
        )

        hdr_tuple = tuple(headers)
        if (hdr_tuple, self._theme_name) != (
                self._sticky_last_headers, self._sticky_last_theme):
            sc.delete("all")
            sc.configure(
                bg=self._palette.get("sticky_bg", self._palette["bg"])
            )
            for idx, hi in enumerate(headers):
                y = idx * self._line_h
                line = self.lines[hi]
                # Gutter slice — background fill + shared line-number draw.
                sc.create_rectangle(
                    0, y, self._gutter_w, y + self._line_h,
                    fill=self._palette["gutter_bg"], outline="",
                )
                self._draw_gutter_number(sc, y, hi)
                # Tokenize + render header line
                x = self._text_x
                fg = self._palette["fg"]
                for txt, cat in self._tokenize(line, hi):
                    if cat is None:
                        color, italic = fg, False
                    else:
                        color, italic = self._token_style.get(cat, (fg, False))
                    font = self._font_italic if italic else self._font
                    sc.create_text(x, y + 1, text=txt, anchor="nw",
                                   fill=color, font=font)
                    x += font.measure(txt)
            sc.create_line(0, bar_h, sw, bar_h, fill=sticky_border, width=1)
            self._sticky_last_headers = hdr_tuple
            self._sticky_last_theme = self._theme_name

        # Place / resize. The +1 covers the bottom border line.
        cur = (0, 0, sw, bar_h + 1)
        if cur != self._sticky_last_place:
            sc.place(x=0, y=0, width=sw, height=bar_h + 1)
            # `Canvas.lift` / `Canvas.tkraise` are both overridden to act
            # on canvas ITEMS, not on the widget's stacking order. Invoke
            # the raw Tcl `raise` to put the band above sibling widgets.
            sc.tk.call('raise', sc._w)
            self._sticky_last_place = cur

    # ── Find/Replace highlight rendering ─────────────────────────────────────
    # Matches are stored as `((start_line, start_col), (end_line, end_col))`
    # tuples. `_find_current_idx` (>=0) marks the currently-focused match
    # and renders in the brighter `find_current` palette color.

    def set_find_matches(self,
                         matches: list[tuple[tuple[int, int], tuple[int, int]]],
                         current_idx: int = -1) -> None:
        """Replace the set of highlighted find matches and request a
        repaint. Pass `[]` to clear."""
        self._find_matches = list(matches)
        self._find_current_idx = current_idx
        self.render()

    def clear_find_matches(self) -> None:
        self.set_find_matches([], -1)

    def _draw_find_matches_on_line(self, line_idx: int,
                                   line_text: str, y: int) -> None:
        if not self._find_matches:
            return
        c = self.canvas
        match_bg = self._palette.get("find_match", "#623f00")
        cur_bg = self._palette.get("find_current", "#ffa500")
        text_x0 = self._text_x0
        for idx, ((sl, sc), (el, ec)) in enumerate(self._find_matches):
            if line_idx < sl or line_idx > el:
                continue
            c1 = sc if line_idx == sl else 0
            c2 = ec if line_idx == el else len(line_text)
            if c1 == c2:
                continue
            x1 = text_x0 + self._font.measure(line_text[:c1])
            x2 = text_x0 + self._font.measure(line_text[:c2])
            color = cur_bg if idx == self._find_current_idx else match_bg
            c.create_rectangle(x1, y, x2, y + self._line_h,
                               fill=color, outline="")

    def _draw_squiggly(self, x1: float, x2: float, y: float, color: str) -> None:
        """Draw a wavy underline from x1..x2 at y."""
        if x2 - x1 < 2:
            return
        pts: list[float] = []
        px = x1
        up = True
        while px < x2:
            pts.extend((px, y if up else y - 2))
            px += 2
            up = not up
        pts.extend((x2, y))
        self.canvas.create_line(*pts, fill=color, width=1)

    def _sticky_headers(self) -> list[int]:
        """Physical-line indices of the enclosing class/def scopes to
        pin at the top of the viewport (outermost first).

        Mirrors IDOL/widgets/sticky_scroll.py:_find_scope_lines:
          • Only class / def / async def are pinned (not if/for/with
            and similar — they'd clutter deeply-nested code).
          • Section markers (`# ── Foo ──`) are skipped.
          • `top_phys` is offset by the *previous* frame's band height
            so band-covered rows are treated as scrolled off. This
            introduces a 1-frame lag when the band size changes (e.g.
            entering or leaving a scope), which is what IDOL accepts
            in exchange for stability — earlier iteration approaches
            oscillated when sibling defs at the same indent were
            adjacent.
          • Walk is EXCLUSIVE of top_phys, with `offset = max(1, ...)`
            so on the first scroll (no previous headers) we still see
            one row past `scroll_y` — otherwise a def at the very top
            of the viewport would be missed on bootstrap.
        """
        if self.scroll_y == 0 or not self.lines:
            return []
        offset = max(1, len(self._sticky_last_headers))
        top_visual = self.scroll_y + offset
        top_phys = self._visual_to_physical(top_visual)
        if top_phys is None or top_phys < 0:
            return []

        headers: list[int] = []
        min_indent: float = float("inf")
        for i in range(top_phys - 1, -1, -1):
            line = self.lines[i]
            if not line.strip():
                continue
            if _SECTION_MARKER.match(line):
                continue
            if not _SCOPE_HEADER_RE.match(line):
                continue
            indent = len(line) - len(line.lstrip())
            if indent < min_indent:
                headers.insert(0, i)
                min_indent = indent
                if indent == 0:
                    break
        return headers

    def _cursor_word_start_col(self) -> int | None:
        """Return the start column of the word the cursor is on, or
        None if the cursor isn't on/adjacent to a word."""
        line = self.lines[self.cur_line]
        if not line:
            return None
        c = self.cur_col
        if c < len(line) and (line[c].isalnum() or line[c] == "_"):
            pass
        elif c > 0 and (line[c - 1].isalnum() or line[c - 1] == "_"):
            c -= 1
        else:
            return None
        while c > 0 and (line[c - 1].isalnum() or line[c - 1] == "_"):
            c -= 1
        return c

    def _cursor_word(self) -> str | None:
        """If the cursor is sitting on or right after a word character,
        return that word. Used by word-occurrence highlighting."""
        line = self.lines[self.cur_line]
        if not line:
            return None
        # Pick the column on the word side of the cursor.
        c = self.cur_col
        if c < len(line) and (line[c].isalnum() or line[c] == "_"):
            pass
        elif c > 0 and (line[c - 1].isalnum() or line[c - 1] == "_"):
            c -= 1
        else:
            return None
        start = c
        while start > 0 and (line[start - 1].isalnum() or line[start - 1] == "_"):
            start -= 1
        end = c
        while end < len(line) and (line[end].isalnum() or line[end] == "_"):
            end += 1
        word = line[start:end]
        # Ignore very short words and pure numerics — too noisy.
        if len(word) < 2 or word.isdigit():
            return None
        return word

    def _effective_indents(self) -> list[int]:
        """Per-line indent (in chars) for guide-drawing purposes.

        Non-blank lines use their actual leading-space count. Blank /
        whitespace-only lines inherit `min(prev_non_blank_indent,
        next_non_blank_indent)` so guide lines connect across blank
        rows WITHIN a block but stop where the block ends. Matches
        VS Code's indent-guide behavior — no per-line "stub" lines."""
        n = len(self.lines)
        if n == 0:
            return []
        prev_ind = [0] * n
        last = 0
        for i, line in enumerate(self.lines):
            if line.strip():
                last = len(line) - len(line.lstrip())
            prev_ind[i] = last
        next_ind = [0] * n
        nxt = 0
        for i in range(n - 1, -1, -1):
            line = self.lines[i]
            if line.strip():
                nxt = len(line) - len(line.lstrip())
            next_ind[i] = nxt
        out: list[int] = []
        for i, line in enumerate(self.lines):
            if line.strip():
                out.append(len(line) - len(line.lstrip()))
            else:
                out.append(min(prev_ind[i], next_ind[i]))
        return out

    def _draw_selection(self, line_idx: int, line_text: str,
                        y: int, canvas_w: int) -> None:
        if self.sel_anchor is None:
            return
        a = self.sel_anchor
        b = (self.cur_line, self.cur_col)
        s, e = (a, b) if a <= b else (b, a)
        if not (s[0] <= line_idx <= e[0]):
            return
        if s[0] == e[0]:
            c1, c2 = s[1], e[1]
        elif line_idx == s[0]:
            c1, c2 = s[1], len(line_text)
        elif line_idx == e[0]:
            c1, c2 = 0, e[1]
        else:
            c1, c2 = 0, len(line_text)
        x1 = self._text_x0 + self._font.measure(line_text[:c1])
        x2 = self._text_x0 + self._font.measure(line_text[:c2])
        if s[0] < line_idx < e[0]:
            x2 = canvas_w   # middle of multi-line selection: full row
        if x1 < x2:
            self.canvas.create_rectangle(x1, y, x2, y + self._line_h,
                                         fill=self._palette["select_bg"],
                                         outline="")

    def _measure_to_col(self, line: str, col: int) -> int:
        """Pixel width of *line* up to character index *col*, accounting
        for italic tokens and hex-color preview squares."""
        x = 0
        c = 0
        for txt, cat in self._tokenize(line):
            if c >= col:
                break
            end = c + len(txt)
            if cat is not None:
                _, italic = self._token_style.get(cat, (None, False))
                font = self._font_italic if italic else self._font
            else:
                font = self._font
            # Mirror the color-preview square the render loop inserts
            # before hex-color string literals (e.g. "#ff0000").
            if cat == "string" and _extract_hex_color(txt):
                sq = max(6, self._line_h - 10)
                x += sq + 3
            if end <= col:
                x += font.measure(txt)
                c = end
            else:
                x += font.measure(txt[:col - c])
                c = col
                break
        return x

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _row_from_y(self, y: int) -> int:
        v_row = self.scroll_y + max(0, y // self._line_h)
        return self._visual_to_physical(v_row)

    def _col_from_x(self, line_idx: int, x: int) -> int:
        if not (0 <= line_idx < len(self.lines)):
            return 0
        line = self.lines[line_idx]
        # `x` is canvas-relative; add back the horizontal scroll offset
        # to get the pixel into the rendered text. Without this, clicks
        # always land on the leftmost visible character when the buffer
        # is scrolled right.
        eff_x = x + self._scroll_x
        if eff_x <= self._text_x:
            return 0
        target = eff_x - self._text_x
        best, best_d = 0, target
        cum = 0
        for col, ch in enumerate(line, start=1):
            cum += self._font.measure(ch)
            d = abs(cum - target)
            if d < best_d:
                best, best_d = col, d
            if cum > target + self._char_w:
                break
        return best

    def _coords_from_pixel(self, x: int, y: int) -> tuple[int, int]:
        row = self._row_from_y(y)
        col = self._col_from_x(row, x)
        return row, col

    # ── Cursor & blink ────────────────────────────────────────────────────────

    def _blink_cursor(self) -> None:
        self.cursor_visible = not self.cursor_visible
        self.render()
        self.after(500, self._blink_cursor)

    def _reset_blink(self) -> None:
        self.cursor_visible = True

    def _ensure_visible(self) -> None:
        # Scroll so cur_line is in view. Convert cur_line to visual row.
        cur_v = 0
        skip = None
        target_v = 0
        for i, line in enumerate(self.lines):
            if skip is not None:
                if skip == -1:
                    if _IDOL_END_RE.match(line):
                        skip = None
                    continue
                if skip <= -2:
                    si = -(skip + 2)
                    if line.strip():
                        ind = len(line) - len(line.lstrip())
                        if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                            skip = None
                        else:
                            continue
                    else:
                        continue
                else:
                    ind = len(line) - len(line.lstrip())
                    if line.strip() and ind <= skip:
                        skip = None
                    else:
                        continue
            if i == self.cur_line:
                target_v = cur_v
                break
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            cur_v += 1
        h = self.canvas.winfo_height()
        visible_rows = max(1, h // self._line_h)
        if target_v < self.scroll_y:
            self.scroll_y = target_v
        elif target_v >= self.scroll_y + visible_rows - 1:
            self.scroll_y = target_v - visible_rows + 2

        # Horizontal — keep the caret's column inside the viewport.
        # Pixel position of the caret in the current line, BEFORE the
        # horizontal scroll offset is applied (so we can decide how far
        # to scroll to bring it into view).
        if 0 <= self.cur_line < len(self.lines):
            line = self.lines[self.cur_line]
            caret_px = self._measure_to_col(line, self.cur_col)
            visible_w = self._visible_text_width()
            # Bail when the canvas isn't laid out yet (viewport too
            # narrow for meaningful math). Without this, comparing the
            # real caret pixel against a near-zero viewport pushes
            # scroll_x past max and text bleeds into the gutter.
            if visible_w < self._char_w * 4:
                return
            content_w = self._content_width()
            margin = self._char_w * 4  # keep 4 chars of context past the caret
            # At EOL there is no text after the caret, so use no right-margin:
            # the caret should sit at the viewport edge, not 4 chars inside it.
            at_eol = self.cur_col >= len(line)
            right_margin = 0 if at_eol else margin
            # Use max(content_w, caret_px) so a stale _content_w_cache (set by
            # the previous render) can't cap max_scroll below where the caret
            # actually is — e.g. when typing a char that makes this line the
            # new longest visible line.
            true_content_w = max(content_w, caret_px)
            if true_content_w <= visible_w:
                # Whole buffer fits — never scroll horizontally.
                self._scroll_x = 0
            elif caret_px < self._scroll_x:
                self._scroll_x = max(0, caret_px - margin)
            elif caret_px > self._scroll_x + visible_w - margin:
                max_scroll = max(0, true_content_w - visible_w)
                self._scroll_x = min(max_scroll,
                                     max(0, caret_px - visible_w + right_margin))

    # ── Mouse handlers ────────────────────────────────────────────────────────

    def _on_click(self, event):
        self.canvas.focus_set()
        self._hide_autocomplete()
        if self._mc_cursors:
            self._mc_cursors.clear()
            self._mc_anchors.clear()
        if event.x < self._gutter_w:
            row = self._row_from_y(event.y)
            if event.x < self._debug_w:
                # Debug zone — toggle breakpoint
                if 0 <= row < len(self.lines):
                    if self.on_breakpoint_toggle is not None:
                        # Host owns the canonical store. It calls back
                        # via `set_breakpoints` to update our dot set.
                        try:
                            self.on_breakpoint_toggle(row)
                        except Exception:
                            pass
                    else:
                        # Standalone fallback (preview window): toggle
                        # locally so the dot still appears.
                        if row in self._breakpoints:
                            self._breakpoints.discard(row)
                        else:
                            self._breakpoints.add(row)
                        self.render()
            elif event.x >= self._fold_x:
                # Fold zone — toggle fold on lines that have children
                if row in self.folded:
                    self.folded.discard(row)
                elif self._line_is_foldable(row):
                    self.folded.add(row)
                self.render()
            # Line-number zone (between debug and fold) is intentionally
            # a no-op for now; keeps accidental clicks from doing anything.
            return "break"
        # Click on a fold-dots indicator unfolds that line.
        dots_row = self._hit_fold_dots(event.x, event.y)
        if dots_row is not None:
            self.folded.discard(dots_row)
            self.render()
            return "break"
        self.cur_line, self.cur_col = self._coords_from_pixel(event.x, event.y)
        self._undo_op = ""       # click moved cursor — break coalescing
        self.sel_anchor = None
        self._reset_blink()
        self.render()
        return "break"

    def _on_drag(self, event):
        if self.sel_anchor is None:
            self.sel_anchor = (self.cur_line, self.cur_col)
        self.cur_line, self.cur_col = self._coords_from_pixel(event.x, event.y)
        self._reset_blink()
        self.render()
        return "break"

    def _on_motion(self, event):
        """Per-zone cursor swap + breakpoint ghost-dot tracking.

        Debug zone   → hand2 cursor, ghost-dot preview on the hovered line
        Linenum/fold → right_ptr arrow (matches IDOL's gutter)
        Text area    → xterm I-beam, except over a "···" fold indicator
                       where the cursor becomes hand2 (clickable to unfold).
        """
        if event.x < self._debug_w:
            self.canvas.configure(cursor="hand2")
            row = self._row_from_y(event.y)
            new_hover = row if 0 <= row < len(self.lines) else None
            if new_hover != self._hover_breakpoint_line:
                self._hover_breakpoint_line = new_hover
                self.render()
        elif event.x < self._gutter_w:
            self.canvas.configure(cursor="right_ptr")
            if self._hover_breakpoint_line is not None:
                self._hover_breakpoint_line = None
                self.render()
        else:
            # Minimap zone is owned by the embedded tk.Text widget, which
            # sets its own arrow cursor and consumes events directly.
            over_dots = self._hit_fold_dots(event.x, event.y) is not None
            self.canvas.configure(cursor="hand2" if over_dots else "xterm")
            if self._hover_breakpoint_line is not None:
                self._hover_breakpoint_line = None
                self.render()

    def _on_leave(self, _event):
        self.canvas.configure(cursor="xterm")
        if self._hover_breakpoint_line is not None:
            self._hover_breakpoint_line = None
            self.render()

    def _on_shift_click(self, event):
        self.canvas.focus_set()
        if self.sel_anchor is None:
            self.sel_anchor = (self.cur_line, self.cur_col)
        self.cur_line, self.cur_col = self._coords_from_pixel(event.x, event.y)
        self._reset_blink()
        self.render()
        return "break"

    def _on_double_click(self, event):
        row, col = self._coords_from_pixel(event.x, event.y)
        line = self.lines[row] if 0 <= row < len(self.lines) else ""
        if not line:
            return "break"
        is_word = lambda ch: ch.isalnum() or ch == "_"
        start = min(col, len(line) - 1) if col >= len(line) else col
        end = start
        while start > 0 and is_word(line[start - 1]):
            start -= 1
        while end < len(line) and is_word(line[end]):
            end += 1
        if end > start:
            self.sel_anchor = (row, start)
            self.cur_line, self.cur_col = row, end
            self._reset_blink()
            self.render()
        return "break"

    def _on_triple_click(self, event):
        row = self._row_from_y(event.y)
        if 0 <= row < len(self.lines):
            self.sel_anchor = (row, 0)
            self.cur_line, self.cur_col = row, len(self.lines[row])
            self._reset_blink()
            self.render()
        return "break"

    def _on_right_click(self, event):
        self.canvas.focus_set()
        # Only move the cursor when there is no active selection — with a
        # selection we preserve it so Copy/Cut act on the right range.
        if self.sel_anchor is None:
            try:
                row = self._row_from_y(event.y)
                col = self._col_from_x(row, event.x)
                self.cur_line, self.cur_col = row, col
                self.render()
            except Exception:
                pass

        has_sel = self.sel_anchor is not None and self.sel_anchor != (
            self.cur_line, self.cur_col
        )
        word = self._cursor_word() or ""
        has_word = bool(word) and len(word) >= 2 and not word[0].isdigit()

        # items: (name, shortcut, command, enabled) or None for separator
        items: list = [
            ("Cut",        "Ctrl+X", self._cut,        has_sel),
            ("Copy",       "Ctrl+C", self._copy,       has_sel),
            ("Paste",      "Ctrl+V", self._paste,      True),
            None,
            ("Select All", "Ctrl+A", self._select_all, True),
        ]

        host_section = []
        if self.on_request_goto_definition is not None:
            lsp_ready = self.on_can_goto_definition()
            host_section.append((
                "Go to Definition", "F12",
                self.on_request_goto_definition,
                has_word and lsp_ready,
            ))
        if self.on_request_find_references is not None:
            host_section.append((
                "Find References", "",
                self.on_request_find_references,
                has_word,
            ))
        if host_section:
            items.append(None)
            items.extend(host_section)

        if self.on_request_find_replace is not None:
            items.append(None)
            items.append(("Find & Replace", "Ctrl+F",
                           self.on_request_find_replace, True))

        run_section = []
        if self.on_request_run_line is not None:
            run_section.append(("Run Line", "", self.on_request_run_line, True))
        if self.on_request_run_selection is not None:
            run_section.append((
                "Run Selection", "", self.on_request_run_selection, has_sel,
            ))
        if run_section:
            items.append(None)
            items.extend(run_section)

        self._show_ctx_overlay(event.x_root, event.y_root, items)
        return "break"

    def _show_ctx_overlay(self, x_root: int, y_root: int, items: list) -> None:
        dismiss_fn = getattr(self, "_ctx_overlay_dismiss", None)
        if dismiss_fn:
            dismiss_fn()

        top = self.winfo_toplevel()
        rel_x = x_root - top.winfo_rootx()
        rel_y = y_root - top.winfo_rooty()

        overlay = tk.Frame(top, bg="#2d2d2d",
                           highlightthickness=1, highlightbackground="#007acc")
        self._ctx_overlay = overlay
        top_bid: list = []

        def _dismiss():
            self._ctx_overlay = None
            self._ctx_overlay_dismiss = None
            try:
                overlay.destroy()
            except Exception:
                pass
            if top_bid:
                try:
                    top.unbind("<ButtonRelease-1>", top_bid[0])
                except Exception:
                    pass

        self._ctx_overlay_dismiss = _dismiss

        def _global_click(e):
            w = e.widget
            while w is not None:
                if w is overlay:
                    return
                try:
                    w = w.master
                except AttributeError:
                    break
            _dismiss()

        for item in items:
            if item is None:
                sep = tk.Frame(overlay, bg="#3d3d3d", height=1)
                sep.pack(fill="x", padx=6, pady=2)
                continue
            name, shortcut, cmd, enabled = item
            fg  = "#cccccc" if enabled else "#555555"
            sfg = "#888888" if enabled else "#444444"

            row = tk.Frame(overlay, bg="#2d2d2d")
            row.pack(fill="x")
            name_lbl = tk.Label(row, text=name, bg="#2d2d2d", fg=fg,
                                font=(_FONT_FAMILY, 9), anchor="w",
                                padx=12, pady=3)
            name_lbl.pack(side="left")
            if shortcut:
                sc_lbl = tk.Label(row, text=shortcut, bg="#2d2d2d", fg=sfg,
                                  font=(_FONT_FAMILY, 9), anchor="e",
                                  padx=12, pady=3)
                sc_lbl.pack(side="right")
            else:
                sc_lbl = None

            if enabled:
                all_widgets = [row, name_lbl] + ([sc_lbl] if sc_lbl else [])
                def _enter(e, ws=all_widgets):
                    for w in ws:
                        w.config(bg="#094771")
                    ws[1].config(fg="#ffffff")
                    if len(ws) > 2:
                        ws[2].config(fg="#ffffff")
                def _leave(e, ws=all_widgets):
                    for w in ws:
                        w.config(bg="#2d2d2d")
                    ws[1].config(fg="#cccccc")
                    if len(ws) > 2:
                        ws[2].config(fg="#888888")
                def _click(e, c=cmd):
                    _dismiss()
                    c()
                for w in all_widgets:
                    w.bind("<Enter>",           _enter)
                    w.bind("<Leave>",           _leave)
                    w.bind("<ButtonRelease-1>", _click)

        overlay.update_idletasks()
        ow = overlay.winfo_reqwidth()
        oh = overlay.winfo_reqheight()
        sw = top.winfo_width()
        sh = top.winfo_height()
        if rel_x + ow > sw:
            rel_x = max(0, sw - ow)
        if rel_y + oh > sh:
            rel_y = max(0, sh - oh)

        overlay.place(x=rel_x, y=rel_y)
        overlay.lift()
        top_bid.append(top.bind("<ButtonRelease-1>", _global_click, add=True))

    def _on_mousewheel(self, event):
        if event.delta:
            steps = -3 if event.delta > 0 else 3
        else:
            steps = 3
        self._scroll(steps)
        return "break"

    def _on_shift_mousewheel(self, event):
        steps = -1 if event.delta > 0 else 1
        self.xview("scroll", steps, "units")
        return "break"

    def _scroll(self, lines: int) -> None:
        max_scroll = max(0, self._visual_row_count() - 1)
        new_y = max(0, min(max_scroll, self.scroll_y + lines))
        if new_y != self.scroll_y:
            self.scroll_y = new_y
            self.render()

    # ── Keyboard ──────────────────────────────────────────────────────────────

    def _on_key(self, event):
        self._reset_blink()
        ks = event.keysym
        ctrl = bool(event.state & 0x0004)
        shift = bool(event.state & 0x0001)
        alt = bool(event.state & 0x20000)   # Mod1 on X11, Alt on Windows

        # Autocomplete popup capture — when open, Up/Down navigate,
        # Tab/Enter accepts, Esc dismisses. Anything else falls through.
        if self._ac_top is not None and self._ac_top.state() == "normal":
            if ks == "Up":
                self._ac_select(-1); return "break"
            if ks == "Down":
                self._ac_select(+1); return "break"
            if ks in ("Tab", "Return"):
                self._accept_autocomplete(); return "break"
            if ks == "Escape":
                self._hide_autocomplete(); return "break"

        if ks == "Escape" and self._mc_cursors:
            self._mc_cursors.clear()
            self._mc_anchors.clear()
            self.render()
            return "break"

        # Alt+Up/Down  — move current line / selection block
        # Shift+Alt+Up — duplicate above (cursor stays)
        # Shift+Alt+Down — duplicate below (cursor follows)
        if alt and ks in ("Up", "Down"):
            if shift:
                self._duplicate_lines(cursor_follows=(ks == "Down"))
            else:
                self._move_lines(-1 if ks == "Up" else +1)
            return "break"

        if ctrl and ks.lower() == "z":
            self._undo(); return "break"
        if ctrl and ks.lower() == "y":
            self._redo(); return "break"

        # Ctrl+/  — toggle line comment
        if ctrl and ks in ("slash", "question"):   # question = Shift+/ on some kbd
            self._toggle_comment(); return "break"

        # Ctrl+F — open Find/Replace bar
        # Ctrl+F intentionally NOT handled here — the host (app.py)
        # binds it to IDOL's `FindReplaceBar` in `_new_canvas_tab`.
        # Falling through lets that binding fire.

        # Movement keys manage selection based on Shift
        if ks in ("Left", "Right", "Up", "Down",
                  "Home", "End", "Prior", "Next"):
            if shift and self.sel_anchor is None:
                self.sel_anchor = (self.cur_line, self.cur_col)
            elif not shift:
                self.sel_anchor = None

        # (Removed: Ctrl+<digit> theme-switch shortcut was test-only.
        # Use the right-click Theme submenu in the standalone preview,
        # or the View → Theme menu once it's wired to the canvas
        # engine in the final cleanup pass.)

        # Ctrl shortcuts
        if ctrl and ks.lower() == "a":
            self._select_all(); return "break"
        if ctrl and ks.lower() == "c":
            self._copy(); return "break"
        if ctrl and ks.lower() == "x":
            self._cut(); return "break"
        if ctrl and ks.lower() == "v":
            self._paste(); return "break"
        if ctrl and ks == "Home":
            self.cur_line = 0; self.cur_col = 0
            self._ensure_visible(); self.render(); return "break"
        if ctrl and ks == "End":
            self.cur_line = len(self.lines) - 1
            self.cur_col = len(self.lines[self.cur_line])
            self._ensure_visible(); self.render(); return "break"


        # Movement
        moved = False
        if ks == "Left":
            self._move_left(ctrl); moved = True
        elif ks == "Right":
            self._move_right(ctrl); moved = True
        elif ks == "Up":
            self._move_vertical(-1); moved = True
        elif ks == "Down":
            self._move_vertical(+1); moved = True
        elif ks == "Home":
            # Smart Home — position-based, no state needed: if already
            # at the first non-whitespace col, jump to col 0; else
            # jump to the first non-whitespace col.
            line = self.lines[self.cur_line]
            first_nw = len(line) - len(line.lstrip())
            self.cur_col = 0 if self.cur_col == first_nw else first_nw
            moved = True
        elif ks == "End":
            self.cur_col = len(self.lines[self.cur_line])
            moved = True
        elif ks == "Prior":
            self._move_vertical(-10); moved = True
        elif ks == "Next":
            self._move_vertical(+10); moved = True

        if moved:
            self._undo_op = ""   # cursor moved — break coalescing chain
            self._mc_apply_key(ks, "", shift, ctrl)
            self._ensure_visible()
            self.render()
            return "break"

        # Editing
        if ks == "BackSpace":
            _pl, _pc = self.cur_line, self.cur_col
            _llen = len(self.lines[_pl])
            self._delete_back()
            if self._mc_cursors and self.cur_line == _pl and _pc > 0:
                _delta = len(self.lines[_pl]) - _llen  # -1 or -2
                if _delta:
                    self._mc_shift_same_line(_pl, _pc, _delta)
            self._mc_apply_key("BackSpace", "", shift, ctrl)
            self._ensure_visible(); self.render()
            self._maybe_show_autocomplete()
            return "break"
        if ks == "Delete":
            _pl, _pc = self.cur_line, self.cur_col
            _llen = len(self.lines[_pl])
            self._delete_forward()
            if self._mc_cursors and self.cur_line == _pl:
                _delta = len(self.lines[_pl]) - _llen  # -1 or -2
                if _delta:
                    self._mc_shift_same_line(_pl, _pc + 1, _delta)
            self._mc_apply_key("Delete", "", shift, ctrl)
            self._ensure_visible(); self.render(); return "break"
        if ks == "Return":
            self._insert_newline()
            self._mc_apply_key("Return", "", shift, ctrl)
            self._ensure_visible(); self.render(); return "break"
        if ks == "Tab":
            if shift:
                self._unindent(); self._ensure_visible(); return "break"
            if self.sel_anchor is not None:
                self._indent(); self._ensure_visible(); return "break"
            self._push_undo(""); self._insert_text(" " * self.tab_size)
            self._mc_apply_key("Tab", "", shift, ctrl)
            self._ensure_visible(); self.render(); return "break"

        if event.char and event.char.isprintable() and not ctrl:
            _pl, _pc, _llen = self.cur_line, self.cur_col, len(self.lines[self.cur_line])
            self._insert_char_with_pairs(event.char)
            if self._mc_cursors and self.cur_line == _pl:
                _delta = len(self.lines[_pl]) - _llen  # 1 or 2 (auto-pair)
                if _delta:
                    self._mc_shift_same_line(_pl, _pc, _delta)
            self._mc_apply_key("char", event.char, shift, ctrl)
            self._ensure_visible()
            self.render()
            # Recompute completions after identifier-ish chars, including
            # `.` so member access opens the popup (matches IDOL
            # CodeView; see app.py:_on_key around line 1522).
            if event.char.isalnum() or event.char in ("_", "."):
                self._maybe_show_autocomplete()
            else:
                self._hide_autocomplete()
            return "break"
        # Any movement / editing key dismisses the popup (it's reopened
        # on the next identifier keystroke). Pure modifier keys (Shift,
        # Ctrl, Alt, Meta) have no char and should not dismiss it.
        if self._ac_top is not None and self._ac_top.state() == "normal":
            if not ks.startswith(("Shift_", "Control_", "Alt_", "Meta_",
                                   "Super_", "Hyper_", "Caps_Lock", "Num_Lock")):
                self._hide_autocomplete()
        return None

    # ── Movement helpers ──────────────────────────────────────────────────────

    def _move_left(self, by_word: bool) -> None:
        if by_word:
            line = self.lines[self.cur_line]
            i = self.cur_col
            while i > 0 and not (line[i-1].isalnum() or line[i-1] == "_"):
                i -= 1
            while i > 0 and (line[i-1].isalnum() or line[i-1] == "_"):
                i -= 1
            if i == self.cur_col and self.cur_line > 0:
                self.cur_line -= 1
                self.cur_col = len(self.lines[self.cur_line])
            else:
                self.cur_col = i
        else:
            if self.cur_col > 0:
                self.cur_col -= 1
            elif self.cur_line > 0:
                self.cur_line -= 1
                self.cur_col = len(self.lines[self.cur_line])

    def _move_right(self, by_word: bool) -> None:
        line = self.lines[self.cur_line]
        if by_word:
            i = self.cur_col
            while i < len(line) and (line[i].isalnum() or line[i] == "_"):
                i += 1
            while i < len(line) and not (line[i].isalnum() or line[i] == "_"):
                i += 1
            if i == self.cur_col and self.cur_line + 1 < len(self.lines):
                self.cur_line += 1
                self.cur_col = 0
            else:
                self.cur_col = i
        else:
            if self.cur_col < len(line):
                self.cur_col += 1
            elif self.cur_line + 1 < len(self.lines):
                self.cur_line += 1
                self.cur_col = 0

    def _move_vertical(self, delta: int) -> None:
        # Work in visual rows so movement skips over folded blocks.
        v_total = self._visual_row_count()
        v_cur   = self._visual_row_of(self.cur_line)
        v_new   = max(0, min(v_total - 1, v_cur + delta))
        self.cur_line = self._visual_to_physical(v_new)
        self.cur_col  = min(self.cur_col, len(self.lines[self.cur_line]))

    # ── Edit helpers ──────────────────────────────────────────────────────────

    # ── Auto-pair brackets / quotes ───────────────────────────────────────────

    def _insert_char_with_pairs(self, ch: str) -> None:
        """Smart insert for a single typed character: auto-pair brackets
        and quotes, skip over an already-present closer, and avoid
        pairing when typing into the middle of a word."""
        line = self.lines[self.cur_line]
        next_ch = line[self.cur_col] if self.cur_col < len(line) else ""

        # Skip over an already-present closing char (e.g. typed `)` when
        # the cursor is already sitting on the auto-inserted `)`).
        if not self.sel_anchor and ch in _CLOSERS and next_ch == ch:
            self.cur_col += 1
            return

        # Snapshot before any state mutation.  Plain single-char typing
        # uses "insert_char" so consecutive keystrokes coalesce; anything
        # with a selection or auto-pair breaks the chain.
        _plain = (not self.sel_anchor and
                  not (ch in _PAIRS and not next_ch.isalnum() and next_ch != "_"))
        self._push_undo("insert_char" if _plain else "")

        # Auto-pair when typing an opener — but only if the cursor is at
        # end-of-line, before whitespace, or before a closer. Don't pair
        # when typing into the middle of a word (e.g. typing `(` between
        # `fo` and `o` in `foo`).
        if ch in _PAIRS and not next_ch.isalnum() and next_ch != "_":
            if self.sel_anchor:
                # Wrap selection in the pair instead of replacing it.
                wrapped_text = self._selected_text()
                self._delete_selection()
                self._insert_text(ch + wrapped_text + _PAIRS[ch])
                # Move cursor back to just past the closing char so further
                # typing extends inside the pair.
                self.cur_col -= 1
                return
            # Don't double-pair quotes when one is right behind us (e.g.
            # typing the closing `"` of a string the user explicitly
            # opened character-by-character).
            prev_ch = line[self.cur_col - 1] if self.cur_col > 0 else ""
            if ch in ("'", '"') and prev_ch == ch:
                # Triple-quote completion: user typed the 3rd consecutive quote.
                # Produce '''|''' (or """|""") with cursor centered.
                if self.cur_col >= 2 and line[self.cur_col - 2] == ch:
                    cur_line_text = self.lines[self.cur_line]
                    after = cur_line_text[self.cur_col] if self.cur_col < len(cur_line_text) else ""
                    if after == ch:
                        # Remove the auto-paired closer before inserting the triple.
                        self.lines[self.cur_line] = (
                            cur_line_text[:self.cur_col] + cur_line_text[self.cur_col + 1:]
                        )
                    self._insert_text(ch + ch + ch + ch)
                    self.cur_col -= 3
                    return
                self._insert_text(ch)
                return
            self._insert_text(ch + _PAIRS[ch])
            self.cur_col -= 1
            return

        if self.sel_anchor:
            self._delete_selection()
        self._insert_text(ch)

    # ── Edit helpers ──────────────────────────────────────────────────────────

    def _insert_text(self, text: str) -> None:
        if self.sel_anchor:
            self._delete_selection()
        parts = text.split("\n")
        line = self.lines[self.cur_line]
        head, tail = line[:self.cur_col], line[self.cur_col:]
        if len(parts) == 1:
            self.lines[self.cur_line] = head + parts[0] + tail
            self.cur_col += len(parts[0])
        else:
            new = [head + parts[0]] + list(parts[1:-1]) + [parts[-1] + tail]
            self.lines[self.cur_line:self.cur_line + 1] = new
            self.cur_line += len(parts) - 1
            self.cur_col = len(parts[-1])
        self._fire_change()

    def _insert_newline(self) -> None:
        self._push_undo("")
        if self.sel_anchor:
            self._delete_selection()
        line = self.lines[self.cur_line]
        head, tail = line[:self.cur_col], line[self.cur_col:]
        indent = " " * (len(line) - len(line.lstrip()))
        if head.rstrip().endswith(":"):
            indent += "    "
        # When the cursor is on a folded line, insert after the fold so the
        # new line appears below the collapsed block, not inside it.
        if self.cur_line in self.folded:
            self.folded.discard(self.cur_line)
            self.lines[self.cur_line] = head
            self.lines.insert(self.cur_line + 1, indent + tail)
            self._shift_folds(self.cur_line)
            self.cur_line += 1
            self.cur_col = len(indent)
        else:
            self.lines[self.cur_line] = head
            self.lines.insert(self.cur_line + 1, indent + tail)
            self._shift_folds(self.cur_line)
            self.cur_line += 1
            self.cur_col = len(indent)
        self._fire_change()

    def _delete_back(self) -> None:
        if self.sel_anchor:
            self._push_undo("")
            self._delete_selection()
            return
        if self.cur_col == 0 and self.cur_line == 0:
            return
        op = "delete_back" if self.cur_col > 0 else ""
        self._push_undo(op)
        if self.cur_col > 0:
            line = self.lines[self.cur_line]
            prev_ch = line[self.cur_col - 1]
            next_ch = line[self.cur_col] if self.cur_col < len(line) else ""
            # Empty bracket-pair: backspacing inside `()` removes both.
            if prev_ch in _PAIRS and _PAIRS[prev_ch] == next_ch:
                self.lines[self.cur_line] = (
                    line[:self.cur_col - 1] + line[self.cur_col + 1:]
                )
                self.cur_col -= 1
                self._fire_change()
                return
            self.lines[self.cur_line] = line[:self.cur_col - 1] + line[self.cur_col:]
            self.cur_col -= 1
        elif self.cur_line > 0:
            prev = self.lines[self.cur_line - 1]
            curr = self.lines[self.cur_line]
            self.cur_col = len(prev)
            self.lines[self.cur_line - 1] = prev + curr
            del self.lines[self.cur_line]
            self.folded.discard(self.cur_line)
            self._shift_folds(self.cur_line, -1)
            self.cur_line -= 1
        self._fire_change()

    def _delete_forward(self) -> None:
        if self.sel_anchor:
            self._push_undo("")
            self._delete_selection()
            return
        line = self.lines[self.cur_line]
        at_end_of_file = (self.cur_col >= len(line) and
                          self.cur_line + 1 >= len(self.lines))
        if at_end_of_file:
            return
        op = "delete_fwd" if self.cur_col < len(line) else ""
        self._push_undo(op)
        if self.cur_col < len(line):
            self.lines[self.cur_line] = line[:self.cur_col] + line[self.cur_col + 1:]
        elif self.cur_line + 1 < len(self.lines):
            self.lines[self.cur_line] = line + self.lines[self.cur_line + 1]
            del self.lines[self.cur_line + 1]
            self.folded.discard(self.cur_line + 1)
            self._shift_folds(self.cur_line + 1, -1)
        self._fire_change()

    def _delete_selection(self) -> None:
        if not self.sel_anchor:
            return
        a, b = self.sel_anchor, (self.cur_line, self.cur_col)
        s, e = (a, b) if a <= b else (b, a)
        if s[0] == e[0]:
            line = self.lines[s[0]]
            self.lines[s[0]] = line[:s[1]] + line[e[1]:]
        else:
            head = self.lines[s[0]][:s[1]]
            tail = self.lines[e[0]][e[1]:]
            self.lines[s[0]] = head + tail
            del self.lines[s[0] + 1:e[0] + 1]
        self.cur_line, self.cur_col = s
        self.sel_anchor = None

    # ── Clipboard ─────────────────────────────────────────────────────────────

    def _selected_text(self) -> str:
        if not self.sel_anchor:
            return ""
        a, b = self.sel_anchor, (self.cur_line, self.cur_col)
        s, e = (a, b) if a <= b else (b, a)
        if s[0] == e[0]:
            return self.lines[s[0]][s[1]:e[1]]
        parts = [self.lines[s[0]][s[1]:]]
        for i in range(s[0] + 1, e[0]):
            parts.append(self.lines[i])
        parts.append(self.lines[e[0]][:e[1]])
        return "\n".join(parts)

    def _copy(self) -> None:
        text = self._selected_text()
        if text:
            self.canvas.clipboard_clear()
            self.canvas.clipboard_append(text)
            # Notify the host so the clipboard-history ring picks the
            # copy up. Mirrors `CodeView._copy` calling `cv.on_copy`.
            if self.on_copy is not None:
                try:
                    self.on_copy(text)
                except Exception:
                    pass

    # User-facing action methods are SELF-RENDERING so they work the same
    # whether called from the keyboard, the right-click menu, or
    # programmatically. Without this, right-click → Paste inserted text
    # but never re-tokenized/redrew, so the pasted content appeared
    # unstyled until the next keystroke.

    def _cut(self) -> None:
        if not self.sel_anchor:
            return
        self._push_undo("")
        self._copy()
        self._delete_selection()
        self._ensure_visible()
        self.render()
        self._fire_change()

    _BAD_PASTE_CHARS = frozenset("\xa0​           　")

    def _paste(self) -> None:
        try:
            text = self.canvas.clipboard_get()
        except tk.TclError:
            return
        if not text:
            return
        self._push_undo("")
        self._insert_text(text)
        self._ensure_visible()
        self.render()
        if self.on_bad_paste and any(c in self._BAD_PASTE_CHARS for c in text):
            try:
                self.on_bad_paste()
            except Exception:
                pass

    def _select_all(self) -> None:
        self.sel_anchor = (0, 0)
        last = len(self.lines) - 1
        self.cur_line = last
        self.cur_col = len(self.lines[last])
        self._ensure_visible()
        self.render()

    def _on_canvas_focus_out(self, _event) -> None:
        self.render()
        # Close autocomplete when the editor loses focus (user clicked away,
        # switched tabs, etc.). Use after() so a listbox click can fire
        # _accept_autocomplete before the popup is withdrawn.
        self.after(50, self._ac_dismiss_if_unfocused)

    # ── Tier 1 multi-line actions ─────────────────────────────────────────────

    def _selected_line_range(self) -> tuple[int, int]:
        """Return (start_line, end_line) inclusive. Uses selection if
        present, otherwise just the cursor's line."""
        if self.sel_anchor is None:
            return self.cur_line, self.cur_line
        a, b = self.sel_anchor, (self.cur_line, self.cur_col)
        s, e = (a, b) if a <= b else (b, a)
        # If selection ends at col 0 of a line, that line isn't really
        # included visually — don't pull it in. Matches VS Code.
        end_line = e[0] - 1 if e[1] == 0 and e[0] > s[0] else e[0]
        return s[0], end_line

    def _toggle_comment(self) -> None:
        """Ctrl+/ — toggle `# ` prefix on the selected lines, or the
        cursor line. If every non-blank line is already commented,
        un-comment them all; otherwise add `# ` after each line's
        existing indent. Mirrors app.py:_toggle_comment."""
        self._push_undo("")
        start, end = self._selected_line_range()
        block = [self.lines[i] for i in range(start, end + 1)]
        non_empty = [l for l in block if l.strip()]
        all_commented = bool(non_empty) and all(
            l.lstrip().startswith("#") for l in non_empty
        )
        # Use the minimum indent of all non-empty lines so every # lines up
        # in a straight column (VS Code style).
        min_ind = min((len(l) - len(l.lstrip()) for l in non_empty), default=0)
        for i in range(start, end + 1):
            text = self.lines[i]
            if not text.strip():
                continue  # leave blank lines untouched
            body = text[min_ind:]
            if all_commented:
                if body.startswith("# "):
                    self.lines[i] = text[:min_ind] + body[2:]
                elif body.startswith("#"):
                    self.lines[i] = text[:min_ind] + body[1:]
            else:
                self.lines[i] = text[:min_ind] + "# " + text[min_ind:]
        # Clamp cur_col so it doesn't dangle past the modified line.
        self.cur_col = min(self.cur_col, len(self.lines[self.cur_line]))
        self.render()
        self._fire_change()

    def _indent(self) -> None:
        """Tab with selection — add tab_size spaces to the start of each selected line."""
        self._push_undo("")
        start, end = self._selected_line_range()
        spaces = " " * self.tab_size
        for i in range(start, end + 1):
            self.lines[i] = spaces + self.lines[i]
            if i == self.cur_line:
                self.cur_col += self.tab_size
        if self.sel_anchor is not None:
            al, ac = self.sel_anchor
            if start <= al <= end:
                self.sel_anchor = (al, ac + self.tab_size)
        self.cur_col = min(self.cur_col, len(self.lines[self.cur_line]))
        self._fire_change()
        self.render()

    def _unindent(self) -> None:
        """Shift+Tab — remove up to tab_size leading spaces from each selected line."""
        self._push_undo("")
        start, end = self._selected_line_range()
        for i in range(start, end + 1):
            line = self.lines[i]
            removed = min(len(line) - len(line.lstrip(" ")), self.tab_size)
            self.lines[i] = line[removed:]
            if i == self.cur_line:
                self.cur_col = max(0, self.cur_col - removed)
        self.cur_col = min(self.cur_col, len(self.lines[self.cur_line]))
        self._fire_change()
        self.render()

    def _move_lines(self, delta: int) -> None:
        """Alt+Up/Down — move the selected line block (or current line)
        up or down by one. Selection and cursor follow."""
        start, end = self._selected_line_range()
        if delta < 0 and start == 0:
            return
        if delta > 0 and end == len(self.lines) - 1:
            return
        self._push_undo("")
        block = self.lines[start:end + 1]
        if delta < 0:
            above = self.lines[start - 1]
            self.lines[start - 1:end + 1] = block + [above]
        else:
            below = self.lines[end + 1]
            self.lines[start:end + 2] = [below] + block
        self.cur_line += delta
        if self.sel_anchor is not None:
            sl, sc = self.sel_anchor
            self.sel_anchor = (sl + delta, sc)
        self._ensure_visible()
        self.render()
        self._fire_change()

    def _duplicate_lines(self, cursor_follows: bool) -> None:
        """Shift+Alt+Down — duplicate selection (or current line) below
        the original. Shift+Alt+Up — same, but cursor stays on the
        original copy. Matches IDOL's Alt+Shift up/down behavior."""
        self._push_undo("")
        start, end = self._selected_line_range()
        block = self.lines[start:end + 1]
        self.lines[end + 1:end + 1] = list(block)
        if cursor_follows:
            span = end - start + 1
            self.cur_line += span
            if self.sel_anchor is not None:
                sl, sc = self.sel_anchor
                self.sel_anchor = (sl + span, sc)
        self._ensure_visible()
        self.render()
        self._fire_change()
