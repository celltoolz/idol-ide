"""Canvas-based code editor sandbox.

A self-contained prototype of the canvas-rendered editor that will eventually
replace `tk.Text` / `CodeView`. Lives in its own Toplevel so we can iterate on
rendering, input, and behavior without touching production code.

Opened via View → Canvas Editor (Preview).
"""
from __future__ import annotations

import re
import tkinter as tk
import tkinter.font as tkfont


# ── Themes ────────────────────────────────────────────────────────────────────
# Each theme has a `palette` (UI colors) and a `tokens` map (category →
# (color, italic)). Tokenization rules emit category NAMES; the renderer
# resolves them at draw time, so swapping themes is a one-call recolor.
# Hardcoded for now; will move to colorschemes/*.toml when we wire the
# sandbox into the production scheme system.

THEMES: dict[str, dict] = {
    # Monokai syntax palette wearing Dark+'s structural look with the
    # role-coloring flipped to match Pylance/semantic-token behavior:
    # class names go green, callables (def names, built-in funcs, method
    # calls, decorators) go cyan-blue, self goes orange, punctuation
    # pink. Comments italic.
    "monokai-bright": {
        "palette": {
            "bg":               "#272822",
            "fg":               "#f8f8f2",
            "caret":            "#f8f8f0",
            "select_bg":        "#49483e",
            "current_line_bg":  "#3e3d32",
            "guide":            "#3b3a32",
            "guide_active":     "#6f6e5f",
            "gutter_bg":        "#272822",
            "gutter_fg":        "#90908a",
            "gutter_fg_active": "#c2c2bf",
        },
        # category: (color, italic)
        "tokens": {
            "comment":      ("#75715e", True),
            "string":       ("#e6db74", False),
            "number":       ("#ae81ff", False),
            "keyword_flow": ("#f92672", False),
            "keyword_decl": ("#f92672", False),
            "constant":     ("#ae81ff", False),
            "self_cls":     ("#fd971f", False),
            "type":         ("#a6e22e", False),       # class names: green
            "function":     ("#66d9ef", False),       # builtins + dunders: blue
            "method":       ("#a6e22e", False),       # user methods: green
            "decorator":    ("#66d9ef", False),
            "punctuation":  ("#f92672", False),       # ( ) , . : ; [ ] { }
        },
    },
    "dark-plus": {
        "palette": {
            "bg":               "#1e1e1e",
            "fg":               "#d4d4d4",
            "caret":            "#aeafad",
            "select_bg":        "#264f78",
            "current_line_bg":  "#2a2d2e",
            "guide":            "#404040",
            "guide_active":     "#707070",
            "gutter_bg":        "#1e1e1e",
            "gutter_fg":        "#858585",
            "gutter_fg_active": "#c6c6c6",
        },
        "tokens": {
            "comment":      ("#6a9955", True),
            "string":       ("#ce9178", False),
            "number":       ("#b5cea8", False),
            "keyword_flow": ("#c586c0", False),
            "keyword_decl": ("#569cd6", False),
            "constant":     ("#569cd6", False),
            "self_cls":     ("#569cd6", False),
            "type":         ("#4ec9b0", False),
            "function":     ("#dcdcaa", False),
            "method":       ("#dcdcaa", False),
            "decorator":    ("#dcdcaa", False),
        },
    },
}

_DEFAULT_THEME = "monokai-bright"

_FONT_FAMILY, _FONT_SIZE = "Consolas", 11
# Gutter layout (left → right): debug column, line numbers, fold markers.
_DEBUG_W   = 16              # breakpoint column on the far left
_LINENUM_R = _DEBUG_W + 30   # right edge of line-number text (anchor "ne")
_FOLD_X    = _LINENUM_R + 4  # left edge of fold marker (anchor "nw")
_GUTTER_W  = _FOLD_X + 14    # total gutter width
_TEXT_X    = _GUTTER_W + 12
_BREAKPOINT_COLOR = "#e51400"

_SAMPLE = """\
class IDOL_IDE:
    def __init__(self):
        if True:
            self.status = 'Ready'
            print('Indents are back!')

    def run(self):
        return True
"""


class CanvasEditorSandbox(tk.Frame):
    """Canvas-rendered editor prototype."""

    def __init__(self, master, theme: str = _DEFAULT_THEME, **kw):
        self._theme_name = theme if theme in THEMES else _DEFAULT_THEME
        self._palette = THEMES[self._theme_name]["palette"]
        self._token_style = THEMES[self._theme_name]["tokens"]
        super().__init__(master, bg=self._palette["bg"], **kw)
        self._build_ui()
        self._init_state()
        self._wire_events()
        self.after(500, self._blink_cursor)
        self.after_idle(self.render)

    # ── Theme switching ──────────────────────────────────────────────────────

    def set_theme(self, name: str) -> None:
        """Swap the active theme. Re-derives palette + token colors and
        triggers a full redraw. No tokenizer rebuild — rules emit category
        names that resolve against the active theme at draw time."""
        if name not in THEMES or name == self._theme_name:
            return
        self._theme_name = name
        self._palette = THEMES[name]["palette"]
        self._token_style = THEMES[name]["tokens"]
        self.configure(bg=self._palette["bg"])
        self.canvas.configure(bg=self._palette["bg"])
        self.render()

    # ── Setup ─────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._font = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE)
        self._font_italic = tkfont.Font(family=_FONT_FAMILY, size=_FONT_SIZE,
                                        slant="italic")
        self._char_w = self._font.measure("W")
        self._line_h = self._font.metrics("linespace") + 2

        self.canvas = tk.Canvas(
            self, bg=self._palette["bg"], highlightthickness=0,
            takefocus=True, cursor="xterm",
        )
        self.canvas.pack(fill="both", expand=True)

    def _init_state(self) -> None:
        self.lines: list[str] = _SAMPLE.rstrip("\n").split("\n")
        self.cur_line: int = 0
        self.cur_col: int = 0
        self.sel_anchor: tuple[int, int] | None = None
        self.cursor_visible: bool = True
        self.folded: set[int] = set()
        self._breakpoints: set[int] = set()
        self.scroll_y: int = 0           # first visible visual row

        # Tokenizer rules. Each rule is (regex, category_name). The category
        # is resolved against the active theme's `tokens` map at render time,
        # so a `set_theme()` recolors without rebuilding rules.
        #
        # Order matters: earlier rules claim text, later rules only see
        # segments still at default fg. Comments and strings MUST come
        # before keywords so words like `if` inside a string don't get
        # keyword-colored.
        self._rules = [
            (re.compile(r"#.*"),                                  "comment"),
            (re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\""), "string"),
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
            (re.compile(r"\b(?:0[xX][\dA-Fa-f]+|\d+(?:\.\d+)?)\b"), "number"),
            # Punctuation — themes that want a Monokai-style pink can
            # color it via the "punctuation" category. Themes that don't
            # define "punctuation" leave it at default fg.
            (re.compile(r"[(){}\[\],.:;]"),                       "punctuation"),
        ]

    def _wire_events(self) -> None:
        c = self.canvas
        c.bind("<Configure>",        lambda _: self.render())
        c.bind("<Button-1>",         self._on_click)
        c.bind("<B1-Motion>",        self._on_drag)
        c.bind("<Double-Button-1>",  self._on_double_click)
        c.bind("<Triple-Button-1>",  self._on_triple_click)
        c.bind("<Shift-Button-1>",   self._on_shift_click)
        c.bind("<Button-3>",         self._on_right_click)
        c.bind("<MouseWheel>",       self._on_mousewheel)
        c.bind("<Button-4>",         lambda _: (self._scroll(-3), "break")[1])
        c.bind("<Button-5>",         lambda _: (self._scroll(+3), "break")[1])
        c.bind("<Key>",              self._on_key)
        c.bind("<FocusIn>",          lambda _: self.render())
        c.bind("<FocusOut>",         lambda _: self.render())

    # ── Rendering ─────────────────────────────────────────────────────────────

    def render(self) -> None:
        c = self.canvas
        c.delete("all")
        w, h = c.winfo_width(), c.winfo_height()
        if w < 2 or h < 2:
            return

        c.create_rectangle(0, 0, _GUTTER_W, h,
                           fill=self._palette["gutter_bg"], outline="")

        # Precompute per-line "effective indent" for guide-drawing. Blank
        # lines inherit min(prev_non_blank_indent, next_non_blank_indent)
        # so guides connect across blank lines INSIDE a block, but stop
        # when the block ends. Matches VS Code's indent-guide behavior.
        eff_indent = self._effective_indents()

        # Active indent guide — the one corresponding to the cursor's
        # containing block. The cursor's own line indent N maps to the
        # guide at level N // 4 (the column just left of where the
        # content starts). active_level == 0 means top-level → no
        # active guide.
        cur_text = self.lines[self.cur_line] if self.lines else ""
        active_level = (len(cur_text) - len(cur_text.lstrip())) // 4

        visible_rows = h // self._line_h + 1
        v_row = 0
        rendered = 0
        i = 0
        skip_indent: int | None = None
        while i < len(self.lines):
            line = self.lines[i]
            # Fold skip
            if skip_indent is not None:
                ind = len(line) - len(line.lstrip())
                if line.strip() and ind <= skip_indent:
                    skip_indent = None
                else:
                    i += 1
                    continue

            # Skip rows above scroll
            if v_row < self.scroll_y:
                v_row += 1
                if i in self.folded:
                    skip_indent = len(line) - len(line.lstrip())
                i += 1
                continue
            if rendered >= visible_rows:
                break

            y = (v_row - self.scroll_y) * self._line_h

            # Current-line highlight (only when no selection)
            if (i == self.cur_line and self.sel_anchor is None
                    and self.canvas.focus_get() is self.canvas):
                c.create_rectangle(_GUTTER_W, y, w, y + self._line_h,
                                   fill=self._palette["current_line_bg"],
                                   outline="")

            # Selection
            self._draw_selection(i, line, y, w)

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
            for level in range(1, eff_indent[i] // 4 + 1):
                gx = _TEXT_X + self._font.measure(" " * ((level - 1) * 4))
                color = guide_hi if level == active_level else guide_dim
                c.create_line(gx, y, gx, y + self._line_h, fill=color)

            # Breakpoint dot (debug zone, far left)
            if i in self._breakpoints:
                cy = y + self._line_h // 2
                c.create_oval(_DEBUG_W // 2 - 4, cy - 4,
                              _DEBUG_W // 2 + 4, cy + 4,
                              fill=_BREAKPOINT_COLOR, outline="")

            # Line number — active line gets brighter color
            gut_fg = (self._palette["gutter_fg_active"]
                      if i == self.cur_line else self._palette["gutter_fg"])
            c.create_text(_LINENUM_R, y + 1, text=str(i + 1),
                          anchor="ne", fill=gut_fg, font=self._font)

            # Fold marker — to the right of the line number, only on
            # lines that introduce an indented child block.
            if self._line_has_children(i):
                glyph = "▶" if i in self.folded else "▼"
                c.create_text(_FOLD_X, y + 1, text=glyph, anchor="nw",
                              fill=self._palette["gutter_fg"],
                              font=self._font)

            # Tokens — resolve each category against the active theme,
            # using the italic font when the category specifies it.
            x = _TEXT_X
            fg = self._palette["fg"]
            for txt, cat in self._tokenize(line):
                if cat is None:
                    color, italic = fg, False
                else:
                    color, italic = self._token_style.get(cat, (fg, False))
                font = self._font_italic if italic else self._font
                c.create_text(x, y + 1, text=txt, anchor="nw",
                              fill=color, font=font)
                x += font.measure(txt)

            # Caret
            if (i == self.cur_line and self.cursor_visible
                    and self.sel_anchor is None):
                cx = _TEXT_X + self._font.measure(line[:self.cur_col])
                c.create_line(cx, y + 1, cx, y + self._line_h - 1,
                              fill=self._palette["caret"], width=1)

            if i in self.folded:
                skip_indent = indent
            v_row += 1
            rendered += 1
            i += 1

    def _line_has_children(self, i: int) -> bool:
        if i + 1 >= len(self.lines):
            return False
        ci = len(self.lines[i]) - len(self.lines[i].lstrip())
        nl = self.lines[i + 1]
        ni = len(nl) - len(nl.lstrip())
        return bool(nl.strip()) and ni > ci

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
        x1 = _TEXT_X + self._font.measure(line_text[:c1])
        x2 = _TEXT_X + self._font.measure(line_text[:c2])
        if s[0] < line_idx < e[0]:
            x2 = canvas_w   # middle of multi-line selection: full row
        if x1 < x2:
            self.canvas.create_rectangle(x1, y, x2, y + self._line_h,
                                         fill=self._palette["select_bg"],
                                         outline="")

    def _tokenize(self, line: str):
        """Return a list of (text, category_or_None) segments.

        Category None means default fg. Categories are resolved to actual
        colors at render time so the active theme picks the palette."""
        segments: list = [(line, None)]
        for pat, category in self._rules:
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
        return [seg for seg in segments if seg[0]]

    # ── Coordinate helpers ────────────────────────────────────────────────────

    def _visual_to_physical(self, v_row: int) -> int:
        cur_v = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                ind = len(line) - len(line.lstrip())
                if line.strip() and ind <= skip:
                    skip = None
                else:
                    continue
            if cur_v == v_row:
                return i
            if i in self.folded:
                skip = len(line) - len(line.lstrip())
            cur_v += 1
        return len(self.lines) - 1

    def _visual_row_count(self) -> int:
        n = 0
        skip = None
        for i, line in enumerate(self.lines):
            if skip is not None:
                ind = len(line) - len(line.lstrip())
                if line.strip() and ind <= skip:
                    skip = None
                else:
                    continue
            n += 1
            if i in self.folded:
                skip = len(line) - len(line.lstrip())
        return n

    def _row_from_y(self, y: int) -> int:
        v_row = self.scroll_y + max(0, y // self._line_h)
        return self._visual_to_physical(v_row)

    def _col_from_x(self, line_idx: int, x: int) -> int:
        if not (0 <= line_idx < len(self.lines)):
            return 0
        line = self.lines[line_idx]
        if x <= _TEXT_X:
            return 0
        target = x - _TEXT_X
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
                ind = len(line) - len(line.lstrip())
                if line.strip() and ind <= skip:
                    skip = None
                else:
                    continue
            if i == self.cur_line:
                target_v = cur_v
                break
            if i in self.folded:
                skip = len(line) - len(line.lstrip())
            cur_v += 1
        h = self.canvas.winfo_height()
        visible_rows = max(1, h // self._line_h)
        if target_v < self.scroll_y:
            self.scroll_y = target_v
        elif target_v >= self.scroll_y + visible_rows - 1:
            self.scroll_y = target_v - visible_rows + 2

    # ── Mouse handlers ────────────────────────────────────────────────────────

    def _on_click(self, event):
        self.canvas.focus_set()
        if event.x < _GUTTER_W:
            row = self._row_from_y(event.y)
            if event.x < _DEBUG_W:
                # Debug zone — toggle breakpoint
                if 0 <= row < len(self.lines):
                    if row in self._breakpoints:
                        self._breakpoints.discard(row)
                    else:
                        self._breakpoints.add(row)
                    self.render()
            elif event.x >= _FOLD_X:
                # Fold zone — toggle fold on lines that have children
                if row in self.folded:
                    self.folded.discard(row)
                elif self._line_has_children(row):
                    self.folded.add(row)
                self.render()
            # Line-number zone (between debug and fold) is intentionally
            # a no-op for now; keeps accidental clicks from doing anything.
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
        menu = tk.Menu(self, tearoff=0,
                       bg="#252526", fg="#cccccc",
                       activebackground="#094771", activeforeground="#ffffff",
                       relief="flat", borderwidth=0)
        has_sel = self.sel_anchor is not None and self.sel_anchor != (self.cur_line, self.cur_col)
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
        menu.add_separator()
        # Theme submenu — live switch between registered themes
        theme_menu = tk.Menu(menu, tearoff=0,
                             bg="#252526", fg="#cccccc",
                             activebackground="#094771",
                             activeforeground="#ffffff",
                             relief="flat", borderwidth=0)
        for name in THEMES:
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

        # Movement keys manage selection based on Shift
        if ks in ("Left", "Right", "Up", "Down",
                  "Home", "End", "Prior", "Next"):
            if shift and self.sel_anchor is None:
                self.sel_anchor = (self.cur_line, self.cur_col)
            elif not shift:
                self.sel_anchor = None

        # Ctrl+<digit> → switch theme by index (Ctrl+1 = first theme, etc.)
        if ctrl and ks.isdigit() and len(ks) == 1 and ks != "0":
            names = list(THEMES.keys())
            idx = int(ks) - 1
            if 0 <= idx < len(names):
                self.set_theme(names[idx])
            return "break"

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
            self.cur_col = 0; moved = True
        elif ks == "End":
            self.cur_col = len(self.lines[self.cur_line]); moved = True
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
            self._delete_back(); self._ensure_visible(); self.render(); return "break"
        if ks == "Delete":
            self._delete_forward(); self._ensure_visible(); self.render(); return "break"
        if ks == "Return":
            self._insert_newline(); self._ensure_visible(); self.render(); return "break"
        if ks == "Tab":
            self._insert_text("    "); self._ensure_visible(); self.render(); return "break"

        if event.char and event.char.isprintable() and not ctrl:
            if self.sel_anchor:
                self._delete_selection()
            self._insert_text(event.char)
            self._ensure_visible()
            self.render()
            return "break"
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
        self.cur_line = max(0, min(len(self.lines) - 1, self.cur_line + delta))
        self.cur_col = min(self.cur_col, len(self.lines[self.cur_line]))

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

    def _delete_back(self) -> None:
        if self.sel_anchor:
            self._delete_selection()
            return
        if self.cur_col > 0:
            line = self.lines[self.cur_line]
            self.lines[self.cur_line] = line[:self.cur_col - 1] + line[self.cur_col:]
            self.cur_col -= 1
        elif self.cur_line > 0:
            prev = self.lines[self.cur_line - 1]
            curr = self.lines[self.cur_line]
            self.cur_col = len(prev)
            self.lines[self.cur_line - 1] = prev + curr
            del self.lines[self.cur_line]
            self.cur_line -= 1

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
