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
from typing import Callable

from .breadcrumb_bar import BreadcrumbBar
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

_FONT_FAMILY, _FONT_SIZE = "Consolas", 11
# Gutter layout — base values for the default font (Consolas 11).
# At runtime every CanvasCodeView instance computes _compute_gutter()
# so the zones scale with the chosen font size.
_DEBUG_W   = 16
_LINENUM_R = _DEBUG_W + 30
_FOLD_X    = _LINENUM_R + 4
_GUTTER_W  = _FOLD_X + 14
_TEXT_X    = _GUTTER_W + 12
_BREAKPOINT_COLOR       = "#f14c4c"   # bright red, matches IDOL linenums.py
_BREAKPOINT_GHOST_COLOR = "#6b2020"   # dim red — hover preview

# Git-diff gutter stripe palette — mirrors widgets/linenums.py's
# `_GUTTER_COLORS`. Kind names come from `editor/git_manager.py`'s
# hunk-classification: "added" (new lines), "modified" (edited lines),
# "deleted" (lines removed — shown as a marker on the survivor below).
_GIT_HUNK_COLORS = {
    "added":    "#4ec994",
    "modified": "#c5a028",
    "deleted":  "#f14c4c",
}

# A "# ── Name ─────" section marker — foldable like a block opener.
# Matches IDOL/widgets/linenums.py:_SECTION_MARKER.
_SECTION_MARKER = re.compile(r"^\s*# ─{2,}")
# IDOL designer codegen pair markers — fold the entire BEGIN…END block.
_IDOL_BEGIN_RE  = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:BEGIN")
_IDOL_END_RE    = re.compile(r"^\s*# ─{2,}\s+IDOL(?::[^:]+)?:END")
# Lines that sticky-scroll pins: only class/def/async def, mirroring
# IDOL/widgets/sticky_scroll.py:_SCOPE_RE. Generic block openers
# (if/for/while/with) are foldable but not pinned — they'd clutter
# the band on deeply-nested code.
_SCOPE_HEADER_RE = re.compile(r"^(\s*)(?:class\s|def\s|async\s+def\s)")

# Characters that auto-pair when typed. Maps opener → closer.
_PAIRS = {"(": ")", "[": "]", "{": "}", '"': '"', "'": "'"}
# All openers and closers — used for skip-over-closer detection.
_CLOSERS = set(_PAIRS.values())
# Bracket pairs for matching (no quotes — same char on both sides).
_BRACKET_OPEN_TO_CLOSE = {"(": ")", "[": "]", "{": "}"}
_BRACKET_CLOSE_TO_OPEN = {v: k for k, v in _BRACKET_OPEN_TO_CLOSE.items()}
_ALL_BRACKETS = set(_BRACKET_OPEN_TO_CLOSE) | set(_BRACKET_CLOSE_TO_OPEN)
# Identifier char class for word-occurrence highlighting.
_WORD_RE = re.compile(r"\w+")

# Minimap layout — embedded `tk.Text` at font size 1, mirroring IDOL's
# peer-text minimap. Canvas `create_text` can't render legible glyphs
# below ~4-5px; a Text widget rasterizes properly at size 1.
_MINIMAP_W         = 90   # IDOL parity (widgets/minimap.py:WIDTH)
_MINIMAP_FONT_SIZE = 1
_PREVIEW_LINES     = 14   # rows shown in the hover zoom preview
_PREVIEW_W         = 420  # min width of the hover preview Toplevel

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


def _lighten(hex_color: str, amount: int = 18) -> str:
    """Brighten a `#rrggbb` color by *amount* per channel. Used for the
    1-px frame around the minimap hover preview Toplevel."""
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return f"#{min(255, r + amount):02x}{min(255, g + amount):02x}{min(255, b + amount):02x}"
    except Exception:
        return hex_color


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


class CanvasCodeView(tk.Frame):
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
        self.scroll_y = 0
        self._scroll_x = 0
        self.folded.clear()
        self._file_max_w_dirty = True
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
        self._file_max_w_dirty = True
        if self.on_change is not None:
            try:
                self.on_change()
            except Exception:
                pass

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
        """Move the viewport so the (0-indexed) line is visible near
        the top with a small overscan above for context."""
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
        self.scroll_y = max(0, v - 2)  # 2-row top overscan
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
          • `_TEXT_X` — gutter (line numbers + fold markers) on the
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
        instead of `_TEXT_X` for ANY canvas item that should scroll
        horizontally with the buffer (tokens, selection, find-match,
        diagnostics, cursor, indent guides). Gutter / minimap /
        sticky-band positions stay fixed to `_TEXT_X` because they
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

    def _goto_line(self, line: int) -> None:
        """Breadcrumb navigation target — center the given line in the
        viewport. *line* is 1-indexed (matches BreadcrumbBar API)."""
        idx = max(0, min(len(self.lines) - 1, line - 1))
        self.cur_line = idx
        self.cur_col = 0
        self.sel_anchor = None
        self._ensure_visible()
        self.canvas.focus_set()
        self.render()

    def _refresh_breadcrumb(self) -> None:
        pass  # app.py's 25 ms _highlight_active_line loop owns all crumb updates

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _compute_gutter(self) -> None:
        """Recompute font-aware gutter layout. Call after any font change."""
        cw = self._char_w
        self._debug_w   = 16
        # Right edge of line-number column: enough for 4 digits + small margin.
        self._linenum_r = self._debug_w + max(30, cw * 4)
        # Left edge of fold glyph: small gap after line numbers.
        self._fold_x    = self._linenum_r + max(4, cw // 2)
        # Right edge of gutter: fold glyph + one char width of clearance.
        self._gutter_w  = self._fold_x + max(14, cw + 4)
        # Where text begins: small gap after the gutter rectangle.
        self._text_x    = self._gutter_w + max(8, cw)

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
        # ── Host hooks for context-menu items ────────────────────
        # When set, the right-click menu includes the corresponding
        # entry. None → item omitted. Lets the engine ship a richer
        # menu when embedded in IDOL (Go to Def / Find References /
        # Run Line / Run Selection / Find & Replace) but stay
        # minimal in the standalone preview where these don't apply.
        self.on_request_goto_definition = None
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

        # Tokenizer rules. Each rule is (regex, category_name). The category
        # is resolved against the active theme's `tokens` map at render time,
        # so a `set_theme()` recolors without rebuilding rules.
        #
        # Order matters: earlier rules claim text, later rules only see
        # segments still at default fg. Comments and strings MUST come
        # before keywords so words like `if` inside a string don't get
        # keyword-colored.
        self._rules = [
            # Strings BEFORE comments — `#.*` would otherwise eat hex
            # color strings (`bg="#FFFFFF"`) by matching from the `#`
            # to end of line, swallowing the rest of the statement.
            (re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\""), "string"),
            (re.compile(r"#.*"),                                  "comment"),
            (re.compile(r"@\w+(?:\.\w+)*"),                       "decorator"),
            (re.compile(r"(?<=\bclass\s)\w+"),                    "type"),
            # def names — dunders (Python protocol methods like __init__)
            # go to "function" so themes can paint them differently from
            # user-defined methods, which go to "method".
            (re.compile(r"(?<=\bdef\s)__\w+__"),                  "function"),
            (re.compile(r"(?<=\bdef\s)\w+"),                      "method"),
            (re.compile(
                r"\b(class|def|import|from|as|lambda|global|nonlocal)\b"
            ),                                                    "keyword_decl"),
            (re.compile(
                r"\b(if|else|elif|return|for|while|try|except|finally|raise|"
                r"yield|pass|break|continue|with|in|is|not|and|or|async|"
                r"await|assert|del)\b"
            ),                                                    "keyword_flow"),
            (re.compile(r"\b(True|False|None)\b"),                "constant"),
            (re.compile(r"\b(self|cls)\b"),                       "self_cls"),
            (re.compile(
                r"\b(int|str|float|bool|list|dict|set|tuple|bytes|bytearray|"
                r"complex|frozenset|object|type|Exception|BaseException|"
                r"ValueError|TypeError|KeyError|IndexError|AttributeError|"
                r"FileNotFoundError|StopIteration|RuntimeError|"
                r"NotImplementedError|ArithmeticError|ZeroDivisionError|"
                r"OSError|IOError|LookupError|NameError|"
                r"UnicodeDecodeError|UnicodeEncodeError)\b"
            ),                                                    "type"),
            (re.compile(
                r"\b(print|len|range|super|abs|min|max|sum|sorted|reversed|"
                r"enumerate|zip|map|filter|any|all|open|hasattr|getattr|"
                r"setattr|callable|input|format|chr|ord|hex|oct|bin|round|"
                r"divmod|pow|iter|next|repr|isinstance|issubclass|delattr|"
                r"vars|dir|id|globals|locals|exec|eval|compile|"
                r"breakpoint|help|memoryview|slice|staticmethod|classmethod|"
                r"property)\b"
            ),                                                    "function"),
            # Method calls after a dot — dunders (e.g. `__init__` in
            # `super().__init__()`) go to "function", regular method calls
            # (e.g. `self._build_ui()`) go to "method". Mirrors the def-name
            # split so themes can color the two consistently.
            (re.compile(r"(?<=\.)__\w+__(?=\s*\()"),              "function"),
            (re.compile(r"(?<=\.)\w+(?=\s*\()"),                  "method"),
            # Keyword arguments — identifier directly followed by `=`
            # (not `==`, not after `.`). Catches `text=...`, `bg=...`
            # in calls like `tk.Label(text="hi", bg="#fff")`. Skips
            # `x = 1` style assignments because those have spaces
            # around `=` by convention.
            (re.compile(r"(?<!\.)\b\w+(?==(?!=))"),               "parameter"),
            (re.compile(r"\b(?:0[xX][\dA-Fa-f]+|\d+(?:\.\d+)?)\b"), "number"),
            # Punctuation — themes that want a Monokai-style pink can
            # color it via the "punctuation" category. Themes that don't
            # define "punctuation" leave it at default fg.
            (re.compile(r"[(){}\[\],.:;]"),                       "punctuation"),
        ]

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

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 2 or h < 2:
            return

        c.create_rectangle(0, 0, self._gutter_w, h,
                           fill=self._palette["gutter_bg"], outline="")

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
            if (i == self.cur_line and self.sel_anchor is None
                    and self.canvas.focus_get() is self.canvas):
                c.create_rectangle(self._gutter_w, y, w, y + self._line_h,
                                   fill=self._palette["current_line_bg"],
                                   outline="")

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
            # `_TEXT_X` when `_scroll_x > 0`. See the gutter-mask block
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
            for txt, cat in self._tokenize(line):
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

            # Gutter overlay — paints OVER any token / indent guide that
            # scrolled left of `_TEXT_X`, then redraws the gutter content
            # (git stripe, breakpoint, line number, fold marker) on top.
            # Without this, horizontally scrolled long lines bleed the
            # start of each line into the line-number column.
            c.create_rectangle(0, y, self._text_x, y + self._line_h,
                               fill=self._palette["gutter_bg"], outline="")
            git_kind = self._git_hunk_map.get(i)
            if git_kind:
                gcolor = _GIT_HUNK_COLORS.get(git_kind)
                if gcolor:
                    c.create_rectangle(0, y, 3, y + self._line_h,
                                       fill=gcolor, outline="")
            if i in self._breakpoints or i == self._hover_breakpoint_line:
                cy_bp = y + self._line_h // 2
                cx_bp = self._debug_w // 2
                r_bp  = min(self._debug_w // 2 - 1, max(4, self._line_h // 3))
                fill_bp = (_BREAKPOINT_COLOR if i in self._breakpoints
                           else _BREAKPOINT_GHOST_COLOR)
                c.create_oval(cx_bp - r_bp, cy_bp - r_bp,
                              cx_bp + r_bp, cy_bp + r_bp,
                              fill=fill_bp, outline="")
            gut_fg = (self._palette["gutter_fg_active"]
                      if i == self.cur_line else self._palette["gutter_fg"])
            cy = y + self._line_h // 2
            c.create_text(self._linenum_r, cy, text=str(i + 1),
                          anchor="e", fill=gut_fg, font=self._font)
            if self._line_is_foldable(i):
                glyph = "▶" if i in self.folded else "▼"
                c.create_text(self._fold_x, cy, text=glyph, anchor="w",
                              fill=self._palette["gutter_fg"],
                              font=self._font)

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

    # ── Minimap ───────────────────────────────────────────────────────────────
    # The minimap is a real `tk.Text` widget embedded in the canvas via
    # `create_window`. Font size 1 gives the same crisp glyph rasterization
    # IDOL's textbox minimap (widgets/minimap.py) gets — `create_text` on a
    # canvas can't render below ~4-5px. Token tags are mirrored from the
    # active theme so colors match the editor.

    def _build_minimap(self) -> None:
        """Create the embedded minimap Text widget + hover-preview state.
        Called once from `_build_ui`."""
        self._mm_text = tk.Text(
            self.canvas,
            bd=0, highlightthickness=0,
            state="disabled", wrap="none",
            cursor="arrow", takefocus=False,
            font=(_FONT_FAMILY, _MINIMAP_FONT_SIZE),
            padx=2, pady=0,
            spacing1=0, spacing2=0, spacing3=0,
        )
        # `place()` (not create_window) so the canvas's `delete("all")` in
        # render() can't unmap the widget. Track the last place args to
        # avoid redundant geometry calls on every render.
        self._mm_last_place: tuple[int, int, int, int] | None = None
        self._mm_lines_cache: list[str] = []
        self._mm_last_theme: str | None = None
        # Host-toggleable visibility (View → "Show Minimap"). Mirrors
        # the legacy CodeView.show_minimap / hide_minimap contract.
        self._mm_visible: bool = True

        # Hover preview Toplevel — lazily created in `_mm_show_preview`.
        self._mm_preview: tk.Toplevel | None = None
        self._mm_preview_text: tk.Text | None = None
        self._mm_preview_after: str | None = None
        self._mm_last_preview_line: int = -1

        # Elide tag — hides minimap lines that are folded in the editor.
        self._mm_text.tag_configure("mm_elide", elide=True)
        self._mm_last_folded: frozenset = frozenset()

        self._mm_text.bind("<ButtonPress-1>", self._on_mm_press)
        self._mm_text.bind("<B1-Motion>",     self._on_mm_drag)
        self._mm_text.bind("<Motion>",        self._on_mm_hover)
        self._mm_text.bind("<Leave>",         self._on_mm_leave)
        self._mm_text.bind("<MouseWheel>",    self._on_mm_wheel)
        self._mm_text.bind("<Button-4>",      self._on_mm_wheel)
        self._mm_text.bind("<Button-5>",      self._on_mm_wheel)

    def show_minimap(self) -> None:
        """Make the minimap visible. Idempotent."""
        if not self._mm_visible:
            self._mm_visible = True
            self.render()

    def hide_minimap(self) -> None:
        """Hide the minimap and reclaim its column. Idempotent."""
        if self._mm_visible:
            self._mm_visible = False
            self._mm_text.place_forget()
            self._mm_last_place = None
            self.render()

    def _update_minimap(self) -> None:
        """Reposition/resize the embedded widget, rebuild content if the
        buffer changed, refresh tag colors on theme switch, and sync the
        scroll position with the editor viewport. Called from `render`."""
        c = self.canvas
        cw, ch = c.winfo_width(), c.winfo_height()
        mm_x = cw - _MINIMAP_W
        # Hide when the user toggled it off, or when the canvas is too
        # narrow to host both editor + minimap.
        if not self._mm_visible or mm_x < self._text_x + 20 or ch < 2:
            if self._mm_last_place is not None:
                self._mm_text.place_forget()
                self._mm_last_place = None
            return
        cur = (mm_x, 0, _MINIMAP_W, ch)
        if cur != self._mm_last_place:
            self._mm_text.place(x=mm_x, y=0,
                                width=_MINIMAP_W, height=ch)
            self._mm_text.lift()  # ensure widget sits above canvas items
            self._mm_last_place = cur
        if self._mm_last_theme != self._theme_name:
            self._mm_apply_palette()
            self._mm_last_theme = self._theme_name
        # Cheap fast path: if buffer is unchanged, list-compare bails on
        # the first differing entry (or instantly when nothing changed).
        cur_folded = frozenset(self.folded)
        if self._mm_lines_cache != self.lines:
            self._mm_rebuild_content()
            self._mm_apply_folds(cur_folded)
        elif cur_folded != self._mm_last_folded:
            self._mm_apply_folds(cur_folded)
        self._mm_sync_scroll()

    def _mm_apply_palette(self) -> None:
        """Push the active palette + token colors onto the minimap widget."""
        p = self._palette
        bg = p.get("minimap_bg", p["bg"])
        self._mm_text.configure(
            bg=bg, fg=p["fg"],
            insertbackground=bg,
            selectbackground=bg, selectforeground=p["fg"],
        )
        for cat, (color, _italic) in self._token_style.items():
            self._mm_text.tag_configure(f"tok_{cat}", foreground=color)

    def _mm_rebuild_content(self) -> None:
        """Insert every line into the minimap with token tags applied.
        Called only when `self.lines` differs from the cached snapshot."""
        pt = self._mm_text
        pt.configure(state="normal")
        pt.delete("1.0", "end")
        total = len(self.lines)
        for i, line in enumerate(self.lines, start=1):
            col = 0
            for txt, cat in self._tokenize(line):
                pt.insert("end", txt)
                if cat is not None:
                    pt.tag_add(f"tok_{cat}",
                               f"{i}.{col}", f"{i}.{col + len(txt)}")
                col += len(txt)
            if i < total:
                pt.insert("end", "\n")
        pt.configure(state="disabled")
        self._mm_lines_cache = list(self.lines)

    def _mm_apply_folds(self, cur_folded: frozenset) -> None:
        """Elide minimap lines that are hidden by the editor's fold state."""
        pt = self._mm_text
        pt.tag_remove("mm_elide", "1.0", "end")
        if cur_folded:
            skip = None
            for i, line in enumerate(self.lines):
                if skip is not None:
                    if skip == -1:
                        lnum = i + 1
                        pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                        if _IDOL_END_RE.match(line):
                            skip = None
                        continue
                    if skip <= -2:
                        si = -(skip + 2)
                        if line.strip():
                            ind = len(line) - len(line.lstrip())
                            if ind < si or (ind == si and _SECTION_MARKER.match(line)):
                                skip = None  # terminating line is not elided
                            else:
                                lnum = i + 1
                                pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                                continue
                        else:
                            lnum = i + 1
                            pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                            continue
                    else:
                        ind = len(line) - len(line.lstrip())
                        if line.strip() and ind <= skip:
                            skip = None
                        else:
                            lnum = i + 1
                            pt.tag_add("mm_elide", f"{lnum}.0", f"{lnum + 1}.0")
                            continue
                if i in cur_folded:
                    if _IDOL_BEGIN_RE.match(line):
                        skip = -1
                    elif _SECTION_MARKER.match(line):
                        skip = -(len(line) - len(line.lstrip()) + 2)
                    else:
                        skip = len(line) - len(line.lstrip())
        self._mm_last_folded = cur_folded

    def _mm_sync_scroll(self) -> None:
        """Move the minimap's yview so the editor viewport stays centered."""
        n = len(self.lines)
        if n == 0:
            return
        try:
            top_phys = self._visual_to_physical(self.scroll_y) or 0
            frac = top_phys / max(1, n)
            self._mm_text.yview_moveto(max(0.0, min(1.0, frac)))
        except Exception:
            pass

    # ── Minimap interaction ───────────────────────────────────────────────────

    def _on_mm_press(self, event):
        # Focus the canvas so keyboard input still goes to the editor
        # after a minimap click.
        self.canvas.focus_set()
        self._mm_hide_preview()
        self._mm_scroll_to(event.y)
        return "break"

    def _on_mm_drag(self, event):
        self._mm_scroll_to(event.y)
        return "break"

    def _mm_scroll_to(self, widget_y: int) -> None:
        """Translate a y-coord inside the minimap into a main-editor
        scroll position, centering the clicked line in the viewport."""
        try:
            idx = self._mm_text.index(f"@0,{widget_y}")
            phys = max(0, min(len(self.lines) - 1, int(idx.split(".")[0]) - 1))
        except Exception:
            return
        # Convert physical line → visual row (account for folds).
        v = 0
        skip = None
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
            if i == phys:
                break
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            v += 1
        h = self.canvas.winfo_height()
        v_rows = max(1, h // self._line_h)
        self.scroll_y = max(0, v - v_rows // 2)
        self.render()

    def _on_mm_wheel(self, event):
        if getattr(event, "num", 0) == 4:
            self._scroll(-3)
        elif getattr(event, "num", 0) == 5:
            self._scroll(+3)
        else:
            self._scroll(-3 if event.delta > 0 else +3)
        # Refresh preview so the centered line tracks the new scroll pos.
        if self._mm_preview is not None:
            self._mm_last_preview_line = -1
            try:
                idx = self._mm_text.index(f"@0,{event.y}")
                self._mm_show_preview(int(idx.split(".")[0]), event.y_root)
            except Exception:
                pass
        return "break"

    # ── Minimap hover zoom-box ────────────────────────────────────────────────

    def _on_mm_hover(self, event):
        try:
            idx = self._mm_text.index(f"@0,{event.y}")
            line = int(idx.split(".")[0])
        except Exception:
            return
        if line == self._mm_last_preview_line and self._mm_preview is not None:
            self._mm_reposition_preview(event.y_root)
            return
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
        self._mm_preview_after = self.after(
            16, lambda ln=line, y=event.y_root: self._mm_show_preview(ln, y)
        )

    def _on_mm_leave(self, _event):
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
        self._mm_preview_after = self.after(120, self._mm_hide_preview)

    def _mm_show_preview(self, center_line: int, mouse_y_root: int) -> None:
        n = len(self.lines)
        if n == 0:
            return
        half  = _PREVIEW_LINES // 2
        first = max(1, center_line - half)
        last  = min(n, first + _PREVIEW_LINES - 1)
        first = max(1, last - _PREVIEW_LINES + 1)

        if self._mm_preview is None:
            self._mm_preview = tk.Toplevel(self)
            self._mm_preview.overrideredirect(True)
            self._mm_preview.attributes("-topmost", True)
            self._mm_preview.withdraw()
            outer = tk.Frame(self._mm_preview, padx=1, pady=1)
            outer.pack(fill="both", expand=True)
            self._mm_preview_text = tk.Text(
                outer, bd=0, highlightthickness=0,
                state="disabled", wrap="none", takefocus=False,
                padx=8, pady=4,
                font=(_FONT_FAMILY, _FONT_SIZE),
            )
            self._mm_preview_text.pack(fill="both", expand=True)
            self._mm_preview_text.bind("<Enter>", lambda _e: (
                self.after_cancel(self._mm_preview_after)
                if self._mm_preview_after else None
            ))
            self._mm_preview_text.bind("<Leave>", lambda _e: self._mm_hide_preview())
            # Italic variant for comment-like tokens
            self._mm_preview_text_italic_font = tkfont.Font(
                family=_FONT_FAMILY, size=_FONT_SIZE, slant="italic"
            )

        pt = self._mm_preview_text
        p  = self._palette
        pt.configure(
            bg=p["bg"], fg=p["fg"],
            insertbackground=p["bg"],
            selectbackground=p["select_bg"],
        )
        # 1-px frame in a lighter shade of the editor bg
        outer = pt.master  # type: ignore[union-attr]
        outer.configure(bg=_lighten(p["bg"], 35))
        self._mm_preview.configure(bg=_lighten(p["bg"], 35))

        # Apply token tag colors + italic for the categories that want it
        for cat, (color, italic) in self._token_style.items():
            if italic:
                pt.tag_configure(f"tok_{cat}", foreground=color,
                                 font=self._mm_preview_text_italic_font)
            else:
                pt.tag_configure(f"tok_{cat}", foreground=color)

        pt.configure(state="normal", height=_PREVIEW_LINES)
        pt.delete("1.0", "end")
        for ln in range(first, last + 1):
            line = self.lines[ln - 1] if 0 <= ln - 1 < n else ""
            col = 0
            preview_row = ln - first + 1
            for txt, cat in self._tokenize(line):
                pt.insert("end", txt)
                if cat is not None:
                    pt.tag_add(f"tok_{cat}",
                               f"{preview_row}.{col}",
                               f"{preview_row}.{col + len(txt)}")
                col += len(txt)
            if ln < last:
                pt.insert("end", "\n")
        pt.configure(state="disabled")

        # Position to the LEFT of the minimap, vertically centered on mouse.
        cw = self.canvas.winfo_width()
        pw = max(_PREVIEW_W, int(cw * 0.75))
        ph = self._mm_preview.winfo_reqheight() or _PREVIEW_LINES * 16
        mm_x_root = self._mm_text.winfo_rootx()
        px = mm_x_root - pw - 9
        screen_h = self._mm_preview.winfo_screenheight()
        py = max(0, min(mouse_y_root - ph // 2, screen_h - ph))

        self._mm_last_preview_line = center_line
        self._mm_preview.geometry(f"{pw}x{ph}+{px}+{py}")
        self._mm_preview.deiconify()

    def _mm_reposition_preview(self, mouse_y_root: int) -> None:
        if self._mm_preview is None:
            return
        pw = self._mm_preview.winfo_width()
        ph = self._mm_preview.winfo_height()
        px = self._mm_text.winfo_rootx() - pw - 9
        screen_h = self._mm_preview.winfo_screenheight()
        py = max(0, min(mouse_y_root - ph // 2, screen_h - ph))
        self._mm_preview.geometry(f"{pw}x{ph}+{px}+{py}")

    def _mm_hide_preview(self) -> None:
        if self._mm_preview_after:
            self.after_cancel(self._mm_preview_after)
            self._mm_preview_after = None
        self._mm_last_preview_line = -1
        if self._mm_preview is not None:
            self._mm_preview.withdraw()

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
                # Gutter slice
                sc.create_rectangle(
                    0, y, self._gutter_w, y + self._line_h,
                    fill=self._palette["gutter_bg"], outline="",
                )
                sc.create_text(
                    self._linenum_r, y + self._line_h // 2,
                    text=str(hi + 1), anchor="e",
                    fill=self._palette["gutter_fg"], font=self._font,
                )
                # Tokenize + render header line
                x = self._text_x
                fg = self._palette["fg"]
                for txt, cat in self._tokenize(line):
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

    def _line_is_foldable(self, i: int) -> bool:
        """A line opens a foldable block when it is a `# ── …` section
        marker OR ends with a block-opening token (`:`, `(`, `[`, `{`)
        AND has at least one more-indented line directly below.
        Mirrors IDOL/widgets/linenums.py:_get_fold_range first-line
        check — without it we mis-marked any line followed by an
        indented continuation as foldable (chained method calls,
        multi-line expressions, etc.)."""
        if not (0 <= i < len(self.lines)):
            return False
        line = self.lines[i]
        if _IDOL_END_RE.match(line):
            return False
        if _SECTION_MARKER.match(line):
            return True
        if not line.rstrip().endswith((":", "(", "[", "{")):
            return False
        if i + 1 >= len(self.lines):
            return False
        nl = self.lines[i + 1]
        if not nl.strip():
            return False
        ci = len(line) - len(line.lstrip())
        ni = len(nl) - len(nl.lstrip())
        return ni > ci

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

    def _find_bracket_pair(self) -> tuple[tuple[int, int], tuple[int, int]] | None:
        """If the cursor is on (or immediately after) a bracket, return
        ((opener_line, opener_col), (closer_line, closer_col)) for the
        matching pair. Otherwise None."""
        # Look at char AT cursor first, then char immediately BEFORE cursor —
        # matches VS Code-style "cursor on either side of a bracket counts".
        for r, c in self._bracket_candidates():
            ch = self.lines[r][c]
            if ch in _BRACKET_OPEN_TO_CLOSE:
                m = self._scan_forward(r, c, ch, _BRACKET_OPEN_TO_CLOSE[ch])
                if m is not None:
                    return ((r, c), m)
            elif ch in _BRACKET_CLOSE_TO_OPEN:
                m = self._scan_backward(r, c, ch, _BRACKET_CLOSE_TO_OPEN[ch])
                if m is not None:
                    return (m, (r, c))
        return None

    def _bracket_candidates(self) -> list[tuple[int, int]]:
        out = []
        if not (0 <= self.cur_line < len(self.lines)):
            return out
        line = self.lines[self.cur_line]
        # Char AT cursor (if any)
        if 0 <= self.cur_col < len(line) and line[self.cur_col] in _ALL_BRACKETS:
            out.append((self.cur_line, self.cur_col))
        # Char immediately before cursor (more common — cursor sits right
        # after a typed-or-clicked bracket). Guard against cur_col
        # dangling past the end after a destructive edit.
        if 0 < self.cur_col <= len(line) and line[self.cur_col - 1] in _ALL_BRACKETS:
            out.append((self.cur_line, self.cur_col - 1))
        return out

    def _scan_forward(self, r0, c0, opener, closer):
        depth = 0
        for r in range(r0, len(self.lines)):
            line = self.lines[r]
            start = c0 + 1 if r == r0 else 0
            for c in range(start, len(line)):
                ch = line[c]
                if ch == opener:
                    depth += 1
                elif ch == closer:
                    if depth == 0:
                        return (r, c)
                    depth -= 1
        return None

    def _scan_backward(self, r0, c0, closer, opener):
        depth = 0
        for r in range(r0, -1, -1):
            line = self.lines[r]
            end = c0 - 1 if r == r0 else len(line) - 1
            for c in range(end, -1, -1):
                ch = line[c]
                if ch == closer:
                    depth += 1
                elif ch == opener:
                    if depth == 0:
                        return (r, c)
                    depth -= 1
        return None

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

    def _comment_start(self, line: str) -> int | None:
        """Return the index of the first # that opens a real comment.

        Skips # characters that appear inside single- or double-quoted
        strings so `bg="#FFFFFF"` is not misread as a comment while
        `# print(f"hello")` has its entire content treated as a comment."""
        in_str: str | None = None
        i = 0
        while i < len(line):
            ch = line[i]
            if in_str:
                if ch == "\\":
                    i += 2          # skip escaped character
                    continue
                if ch == in_str:
                    in_str = None
            elif ch in ('"', "'"):
                in_str = ch
            elif ch == "#":
                return i
            i += 1
        return None

    def _tokenize(self, line: str):
        """Return a list of (text, category_or_None) segments.

        Category None means default fg. Categories are resolved to actual
        colors at render time so the active theme picks the palette.

        Comments are handled up-front via _comment_start so that string
        tokens inside a comment (e.g. `# print("x")`) are not coloured
        as strings — the whole tail is treated as a comment. Non-comment
        rules run only on the code portion that precedes the `#`."""
        comment_at = self._comment_start(line)
        code_part   = line[:comment_at] if comment_at is not None else line
        segments: list = [(code_part, None)] if code_part else []
        for pat, category in self._rules:
            if category == "comment":
                continue          # handled via _comment_start above
            new_segs = []
            for text, cur_cat in segments:
                if cur_cat is not None:
                    new_segs.append((text, cur_cat))
                    continue
                last = 0
                for m in pat.finditer(text):
                    s, e = m.span()
                    if s > last:
                        new_segs.append((text[last:s], None))
                    new_segs.append((text[s:e], category))
                    last = e
                if last < len(text):
                    new_segs.append((text[last:], None))
            segments = new_segs
        if comment_at is not None:
            segments.append((line[comment_at:], "comment"))
        return [seg for seg in segments if seg[0]]

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _visual_to_physical(self, v_row: int) -> int:
        cur_v = 0
        skip = None
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
            if cur_v == v_row:
                return i
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            cur_v += 1
        return len(self.lines) - 1

    def _visual_row_count(self) -> int:
        n = 0
        skip = None
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
            n += 1
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
        return n

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

    def _hit_fold_dots(self, x: float, y: float) -> int | None:
        """Return the physical line index of the fold-dots indicator at
        the given canvas coords, or None."""
        for x1, y1, x2, y2, row in self._fold_dot_rects:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return row
        return None

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
        """Build & post the editor context menu.

        Always includes Cut/Copy/Paste/Select All + the Theme submenu
        (useful in the standalone preview). When the host wires the
        `on_request_*` hooks (app.py:_new_canvas_tab does this for the
        IDE-integrated tabs), the menu also gets Go to Definition,
        Find References, Find & Replace, Run Line, Run Selection.
        """
        # Move the caret to the click position so word-sensitive items
        # (Go to Def, Find Refs) operate on the right token.
        self.canvas.focus_set()
        try:
            row = self._row_from_y(event.y)
            col = self._col_from_x(row, event.x)
            self.cur_line, self.cur_col = row, col
            self.render()
        except Exception:
            pass

        menu = tk.Menu(self, tearoff=0,
                       bg="#252526", fg="#cccccc",
                       activebackground="#094771", activeforeground="#ffffff",
                       relief="flat", borderwidth=0)

        has_sel = self.sel_anchor is not None and self.sel_anchor != (
            self.cur_line, self.cur_col
        )

        menu.add_command(label="Cut",   command=self._cut,
                         accelerator="Ctrl+X",
                         state="normal" if has_sel else "disabled")
        menu.add_command(label="Copy",  command=self._copy,
                         accelerator="Ctrl+C",
                         state="normal" if has_sel else "disabled")
        menu.add_command(label="Paste", command=self._paste, accelerator="Ctrl+V")
        menu.add_separator()
        menu.add_command(label="Select All", command=self._select_all,
                         accelerator="Ctrl+A")

        # Host-supplied IDE actions — only when wired. `cv` (cursor word
        # state) gates the symbol-sensitive items.
        word = self._cursor_word() or ""
        has_word = bool(word) and len(word) >= 2 and not word[0].isdigit()
        host_section = []
        if self.on_request_goto_definition is not None:
            host_section.append(
                ("Go to Definition", self.on_request_goto_definition,
                 "normal" if has_word else "disabled")
            )
        if self.on_request_find_references is not None:
            host_section.append(
                ("Find References", self.on_request_find_references,
                 "normal" if has_word else "disabled")
            )
        if host_section:
            menu.add_separator()
            for label, cmd, state in host_section:
                menu.add_command(label=label, command=cmd, state=state)

        if self.on_request_find_replace is not None:
            menu.add_separator()
            menu.add_command(label="Find && Replace",
                             accelerator="Ctrl+F",
                             command=self.on_request_find_replace)

        run_section = []
        if self.on_request_run_line is not None:
            run_section.append(("Run Line",
                                self.on_request_run_line, "normal"))
        if self.on_request_run_selection is not None:
            run_section.append(("Run Selection",
                                self.on_request_run_selection,
                                "normal" if has_sel else "disabled"))
        if run_section:
            menu.add_separator()
            for label, cmd, state in run_section:
                menu.add_command(label=label, command=cmd, state=state)

        # Theme submenu — live switch between themes loaded from
        # themes/*.json. Useful in the standalone preview; redundant
        # with View → Theme inside IDOL but harmless.
        menu.add_separator()
        theme_menu = tk.Menu(menu, tearoff=0,
                             bg="#252526", fg="#cccccc",
                             activebackground="#094771",
                             activeforeground="#ffffff",
                             relief="flat", borderwidth=0)
        for name in _list_themes():
            label = ("● " if name == self._theme_name else "   ") + \
                    name.replace("-", " ").title()
            theme_menu.add_command(label=label,
                                   command=lambda n=name: self.set_theme(n))
        menu.add_cascade(label="Theme", menu=theme_menu)
        menu.tk_popup(event.x_root, event.y_root)
        return "break"

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

        # Alt+Up/Down  — move current line / selection block
        # Shift+Alt+Up — duplicate above (cursor stays)
        # Shift+Alt+Down — duplicate below (cursor follows)
        if alt and ks in ("Up", "Down"):
            if shift:
                self._duplicate_lines(cursor_follows=(ks == "Down"))
            else:
                self._move_lines(-1 if ks == "Up" else +1)
            return "break"

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
            self._ensure_visible()
            self.render()
            return "break"

        # Editing
        if ks == "BackSpace":
            self._delete_back(); self._ensure_visible(); self.render()
            # Re-evaluate completions after deletion (narrows or hides).
            self._maybe_show_autocomplete()
            return "break"
        if ks == "Delete":
            self._delete_forward(); self._ensure_visible(); self.render(); return "break"
        if ks == "Return":
            self._insert_newline(); self._ensure_visible(); self.render(); return "break"
        if ks == "Tab":
            self._insert_text("    "); self._ensure_visible(); self.render(); return "break"

        if event.char and event.char.isprintable() and not ctrl:
            self._insert_char_with_pairs(event.char)
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
        # on the next identifier keystroke).
        if self._ac_top is not None and self._ac_top.state() == "normal":
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
        if self.sel_anchor:
            self._delete_selection()
        line = self.lines[self.cur_line]
        head, tail = line[:self.cur_col], line[self.cur_col:]
        indent = " " * (len(line) - len(line.lstrip()))
        if head.rstrip().endswith(":"):
            indent += "    "
        self.lines[self.cur_line] = head
        self.lines.insert(self.cur_line + 1, indent + tail)
        self.cur_line += 1
        self.cur_col = len(indent)
        self._fire_change()

    def _delete_back(self) -> None:
        if self.sel_anchor:
            self._delete_selection()
            return
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
            self.cur_line -= 1
        self._fire_change()

    def _delete_forward(self) -> None:
        if self.sel_anchor:
            self._delete_selection()
            return
        line = self.lines[self.cur_line]
        if self.cur_col < len(line):
            self.lines[self.cur_line] = line[:self.cur_col] + line[self.cur_col + 1:]
        elif self.cur_line + 1 < len(self.lines):
            self.lines[self.cur_line] = line + self.lines[self.cur_line + 1]
            del self.lines[self.cur_line + 1]
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
        self._copy()
        self._delete_selection()
        self._ensure_visible()
        self.render()
        self._fire_change()

    def _paste(self) -> None:
        try:
            text = self.canvas.clipboard_get()
        except tk.TclError:
            return
        if not text:
            return
        self._insert_text(text)
        self._ensure_visible()
        self.render()

    def _select_all(self) -> None:
        self.sel_anchor = (0, 0)
        last = len(self.lines) - 1
        self.cur_line = last
        self.cur_col = len(self.lines[last])
        self._ensure_visible()
        self.render()

    # ── Autocomplete ─────────────────────────────────────────────────────────

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
                bg="#252526", fg="#cccccc",
                selectbackground="#094771", selectforeground="#ffffff",
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

    def _on_canvas_focus_out(self, _event) -> None:
        self.render()
        # Close autocomplete when the editor loses focus (user clicked away,
        # switched tabs, etc.). Use after() so a listbox click can fire
        # _accept_autocomplete before the popup is withdrawn.
        self.after(50, self._ac_dismiss_if_unfocused)

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

    def _visual_row_of(self, line_idx: int) -> int:
        v = 0
        skip = None
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
            if i == line_idx:
                return v
            if i in self.folded:
                if _IDOL_BEGIN_RE.match(line):
                    skip = -1
                elif _SECTION_MARKER.match(line):
                    skip = -(len(line) - len(line.lstrip()) + 2)
                else:
                    skip = len(line) - len(line.lstrip())
            v += 1
        return v

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
        start, end = self._selected_line_range()
        block = [self.lines[i] for i in range(start, end + 1)]
        non_empty = [l for l in block if l.strip()]
        all_commented = bool(non_empty) and all(
            l.lstrip().startswith("#") for l in non_empty
        )
        for i in range(start, end + 1):
            text = self.lines[i]
            ind = len(text) - len(text.lstrip())
            body = text[ind:]
            if all_commented:
                if body.startswith("# "):
                    self.lines[i] = text[:ind] + body[2:]
                elif body.startswith("#"):
                    self.lines[i] = text[:ind] + body[1:]
            else:
                if not body:
                    continue
                self.lines[i] = text[:ind] + "# " + body
        # Clamp cur_col so it doesn't dangle past the modified line.
        self.cur_col = min(self.cur_col, len(self.lines[self.cur_line]))
        self.render()
        self._fire_change()

    def _move_lines(self, delta: int) -> None:
        """Alt+Up/Down — move the selected line block (or current line)
        up or down by one. Selection and cursor follow."""
        start, end = self._selected_line_range()
        if delta < 0 and start == 0:
            return
        if delta > 0 and end == len(self.lines) - 1:
            return
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
