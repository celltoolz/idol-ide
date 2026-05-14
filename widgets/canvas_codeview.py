"""CanvasCodeView — canvas-rendered drop-in replacement for CodeView.

Hidden-peer pattern: subclasses `tk.Text` (so every existing `cv.get`/
`cv.index`/`cv.tag_*` callsite in app.py and friends keeps working),
but a `tk.Canvas` sibling is gridded into the same cell and raised on
top, so the user sees the canvas-painted rendering instead of Tk's
native Text rendering.

Why keep the Text widget mapped:
  • `widgets/sticky_scroll.py` calls `cv.index(f"@0,{sticky_h}")` —
    pixel-coord → text-index requires Tk's layout, only available when
    the widget is mapped.
  • `widgets/linenums.py` calls `cv.bbox(...)` for per-line y offsets.
  • The Text widget owns content, marks, tags, undo stack — same
    source of truth the rest of IDOL already trusts. The canvas only
    paints.

Mouse events on the canvas are forwarded to Text via `mark_set` /
`tag_add`; keyboard events route to Text via `focus_set()` on click.
The Tcl command proxy (same pattern as `CodeView._cmd_proxy`) catches
every `insert`/`delete`/`replace`, fires the existing undo snapshot +
`<<ContentChanged>>` logic, and queues a canvas redraw at idle.

Phase 1 paints: tokenized text (via pygments), the insert cursor, the
selection background, the current-line band, and diagnostic
underlines. Bracket-match outline, word-occurrence highlights,
multi-cursor visuals, fold dots, indent guides, and search-match
overlays are deferred — Tk's tag rendering covers them invisibly
behind the canvas today; we'll port them in Phase 1.5 once the basic
drop-in is soaked.
"""
from __future__ import annotations

import inspect
from contextlib import suppress
from pathlib import Path
import tkinter as tk
from tkinter import BaseWidget, Event, Frame, Menu, Misc, TclError, Text
from tkinter.font import Font
from typing import Any, Callable, Type, Union

import pygments
import pygments.lexer
import pygments.lexers
import toml

from .linenums import TkLineNumbers
from .minimap import Minimap
from .scrollbar import HorizontalScrollbar, VerticalScrollbar
from .sticky_scroll import StickyScroll
from utils.schemeparser import _parse_scheme

color_schemes_dir = Path(__file__).parent.parent / "colorschemes"

LexerType = Union[Type[pygments.lexer.Lexer], pygments.lexer.Lexer]

# Non-ASCII whitespace chars that look like spaces but silently break
# Python source. Matches `codeview.py:_BAD_PASTE_CHARS` — kept in sync
# so paste sanitization behaves identically between the two editors
# during the migration soak.
_BAD_PASTE_CHARS = frozenset("\xa0​      ")


class CanvasCodeView(Text):
    """`tk.Text` subclass that paints itself on a sibling `tk.Canvas`."""

    _w: str
    builtin_color_schemes = [
        "ayu-dark",
        "ayu-light",
        "dracula",
        "mariana",
        "monokai",
        "material",
        "rrt",
        "test",
    ]

    def __init__(
        self,
        master: Misc | None = None,
        lexer: LexerType = pygments.lexers.TextLexer,
        color_scheme: dict[str, dict[str, str | int]] | str | None = None,
        tab_width: int = 4,
        linenums_theme: Callable[[], tuple[str, str]] | tuple[str, str] | None = None,
        autohide_scrollbar: bool = True,
        linenums_border: int = 0,
        default_context_menu: bool = False,
        **kwargs,
    ) -> None:
        self._frame = Frame(master, bg="#000000")
        self._frame.grid_rowconfigure(0, weight=1)
        self._frame.grid_columnconfigure(1, weight=1)

        kwargs.setdefault("wrap", "none")
        kwargs.setdefault("font", ("Fira Mono", 10))

        super().__init__(self._frame, **kwargs)
        # Initialize render-state attrs FIRST — `TkLineNumbers.__init__`
        # below sets `textwidget["yscrollcommand"]`, which routes
        # through our `__setitem__` → `configure` → `_queue_redraw`.
        # That redraw path reads these fields, so they must exist.
        self._redraw_after_id: str | None = None
        self._token_colors: dict[str, str] = {}
        self._drag_anchor: str | None = None
        # Grid the Text into col 1 — REQUIRED for `bbox()` / `@x,y` to
        # work. The canvas overlay below renders on top of it.
        super().grid(row=0, column=1, sticky="nswe")

        # Canvas overlay — same cell, painted opaque, raised above the
        # Text widget so the user only sees the canvas rendering.
        self._canvas = tk.Canvas(
            self._frame,
            bg=kwargs.get("background", "#1e1e1e"),
            highlightthickness=0,
            bd=0,
            takefocus=False,
            cursor="xterm",
        )
        self._canvas.grid(row=0, column=1, sticky="nswe")
        # `Canvas.tkraise` is overridden to raise canvas ITEMS; use the
        # raw Tcl `raise` to lift the widget in its sibling stacking
        # order. Same trick as widgets/canvas_editor_sandbox.py.
        self._canvas.tk.call("raise", self._canvas._w)

        self._line_numbers = TkLineNumbers(
            self._frame,
            self,
            justify=kwargs.get("justify", "left"),
            colors=linenums_theme,
            borderwidth=kwargs.get("borderwidth", linenums_border),
        )
        self._vs = VerticalScrollbar(
            self._frame,
            autohide=autohide_scrollbar,
            width=16,
            command=self.yview,
        )
        self._hs = HorizontalScrollbar(
            self._frame,
            autohide=autohide_scrollbar,
            height=16,
            command=self.xview,
        )

        self._line_numbers.grid(row=0, column=0, sticky="ns")
        self._vs.grid(row=0, column=2, sticky="ns")
        self._hs.grid(row=1, column=1, sticky="we")

        super().configure(
            yscrollcommand=self.vertical_scroll,
            xscrollcommand=self.horizontal_scroll,
            tabs=Font(font=kwargs["font"]).measure(" " * tab_width),
        )

        self._context_menu: Menu | None = None
        self._default_context_menu = default_context_menu
        if default_context_menu:
            self.context_menu

        contmand = "Command" if self._windowingsystem == "aqua" else "Control"
        super().bind(f"<{contmand}-c>", self._copy, add=True)
        super().bind(f"<{contmand}-v>", self._paste, add=True)
        super().bind(f"<{contmand}-a>", self._select_all, add=True)
        super().bind(f"<{contmand}-z>", self._undo, add=True)
        super().bind(f"<{contmand}-Shift-Z>", self._redo, add=True)
        super().bind(f"<{contmand}-y>", self._redo, add=True)
        super().bind("<<Undo>>", self._undo, add=True)
        super().bind("<<Redo>>", self._redo, add=True)
        super().bind("<<ContentChanged>>", self.scroll_line_update, add=True)
        super().bind("<Button-1>", self._line_numbers.redraw, add=True)
        super().bind("<Double-Button-1>", self._on_double_click, add=True)
        # Any key event on the Text repaints the canvas — handles arrow
        # keys (cursor moved but no text mutation, so the cmd proxy
        # doesn't fire).
        super().bind("<KeyPress>", self._queue_redraw, add=True)
        super().bind("<KeyRelease>", self._queue_redraw, add=True)

        # ── Command proxy ────────────────────────────────────────────
        # Rename the underlying Tcl widget so we can intercept every
        # mutation. Critical: must happen BEFORE Minimap peer creation
        # so the peer can use the renamed handle.
        self._orig = f"{self._w}_widget"
        self.tk.call("rename", self._w, self._orig)
        self.tk.createcommand(self._w, self._cmd_proxy)

        # Python-level snapshot undo/redo — same as CodeView. Tk's
        # built-in edit-undo is disabled because it loses tag state.
        self._undo_stack: list[tuple[str, str, Any, list | None]] = []
        self._redo_stack: list[tuple[str, str, Any, list | None]] = []
        self._undo_restoring: bool = False
        self._undo_pending_save: bool = False
        self.tk.call(self._orig, "configure", "-undo", False)
        # Host-supplied callbacks (same surface as CodeView).
        self.on_lines_changed: Callable[[int, int], None] | None = None
        self.on_snapshot: Callable[[], Any] | None = None
        self.on_undo_restore: Callable[[Any], None] | None = None
        self.on_copy: Callable[[str], None] | None = None

        self._sticky = StickyScroll(self._frame, self, self._line_numbers)
        self._minimap = Minimap(self._frame, self)
        self._minimap.grid()

        # Canvas font / metrics — derived from the Text widget's font
        # so `bbox()` positions match where the canvas paints. Token
        # colors stay populated from `_setup_tags`; redraw / drag state
        # is initialized at the top of `__init__` (see comment above).
        self._font_obj = Font(font=self.cget("font"))
        self._line_h = self._font_obj.metrics("linespace")
        self._char_w = self._font_obj.measure("0")

        self._set_lexer(lexer)
        self.set_color_scheme(color_scheme)

        # Mouse/wheel input on the canvas — forwarded to the Text below.
        self._bind_canvas_events()
        # First paint once the frame is sized.
        self.after_idle(self._queue_redraw)

    # ────────────────────────────────────────────────────────────────
    # Canvas event forwarding
    # ────────────────────────────────────────────────────────────────

    def _bind_canvas_events(self) -> None:
        c = self._canvas
        c.bind("<Button-1>",          self._on_canvas_press)
        c.bind("<B1-Motion>",         self._on_canvas_drag)
        c.bind("<ButtonRelease-1>",   self._on_canvas_release)
        c.bind("<Double-Button-1>",   self._on_canvas_double_click)
        c.bind("<Triple-Button-1>",   self._on_canvas_triple_click)
        c.bind("<MouseWheel>",        self._on_canvas_wheel)
        c.bind("<Button-4>",          self._on_canvas_wheel)
        c.bind("<Button-5>",          self._on_canvas_wheel)
        c.bind("<Button-3>",          self._on_canvas_right_click)

    def _forward_to_text(self, sequence: str, event) -> None:
        """Re-emit a mouse event on the underlying Text widget so any
        `cv.bind(<MouseEvent>, ...)` callsites in app.py / extensions
        keep working. The canvas absorbs the original event because it
        sits on top of the Text widget in the same grid cell — without
        this forward, only canvas bindings would ever fire."""
        try:
            self.event_generate(
                sequence,
                x=event.x, y=event.y,
                rootx=event.x_root, rooty=event.y_root,
                state=getattr(event, "state", 0),
                when="tail",
            )
        except Exception:
            pass

    def _on_canvas_press(self, event) -> str:
        self.focus_set()
        idx = self.index(f"@{event.x},{event.y}")
        # When the event carries the Alt modifier (state & 0x20000 on
        # Win/Linux, Mod1 on X11) we DON'T clear the selection — Alt
        # is the multi-cursor add modifier and the host binding wants
        # any existing selection preserved.
        is_alt = bool(getattr(event, "state", 0) & 0x20000)
        if not is_alt:
            self.tag_remove("sel", "1.0", "end")
            self.mark_set("insert", idx)
        self._drag_anchor = idx
        self._queue_redraw()
        # Forward to Text so external bindings (LearningManager,
        # plain-click pane activation, multi-cursor Alt+Click) fire.
        self._forward_to_text("<Button-1>", event)
        return "break"

    def _on_canvas_release(self, event) -> str:
        # ButtonRelease fires the host's `_on_click_release` (bracket
        # match + word-occurrence highlight).
        self._forward_to_text("<ButtonRelease-1>", event)
        return "break"

    def _on_canvas_drag(self, event) -> str:
        if self._drag_anchor is None:
            return "break"
        idx = self.index(f"@{event.x},{event.y}")
        if self.compare(idx, "<", self._drag_anchor):
            a, b = idx, self._drag_anchor
        else:
            a, b = self._drag_anchor, idx
        self.tag_remove("sel", "1.0", "end")
        if self.compare(a, "!=", b):
            self.tag_add("sel", a, b)
        self.mark_set("insert", idx)
        self._queue_redraw()
        return "break"

    def _on_canvas_double_click(self, event) -> str:
        self.focus_set()
        idx = self.index(f"@{event.x},{event.y}")
        self.mark_set("insert", idx)
        # Select the word under the cursor — same as Tk Text default.
        try:
            ws = self.index(f"{idx} wordstart")
            we = self.index(f"{idx} wordend")
            self.tag_remove("sel", "1.0", "end")
            self.tag_add("sel", ws, we)
            self.mark_set("insert", we)
        except TclError:
            pass
        self._queue_redraw()
        return "break"

    def _on_canvas_triple_click(self, event) -> str:
        self.focus_set()
        idx = self.index(f"@{event.x},{event.y}")
        line = idx.split(".")[0]
        self.tag_remove("sel", "1.0", "end")
        self.tag_add("sel", f"{line}.0", f"{line}.end")
        self.mark_set("insert", f"{line}.end")
        self._queue_redraw()
        return "break"

    def _on_canvas_wheel(self, event) -> str:
        if getattr(event, "num", 0) == 4:
            self.yview_scroll(-3, "units")
        elif getattr(event, "num", 0) == 5:
            self.yview_scroll(3, "units")
        else:
            self.yview_scroll(-3 if event.delta > 0 else 3, "units")
        return "break"

    def _on_canvas_right_click(self, event) -> str:
        self.focus_set()
        self._forward_to_text("<Button-3>", event)
        return "break"

    # ────────────────────────────────────────────────────────────────
    # Canvas rendering
    # ────────────────────────────────────────────────────────────────

    def _queue_redraw(self, _event=None) -> None:
        """Coalesce redraw requests — at most one paint per idle tick."""
        if self._redraw_after_id is not None:
            return
        self._redraw_after_id = self.after_idle(self._do_redraw)

    def _do_redraw(self) -> None:
        self._redraw_after_id = None
        c = self._canvas
        try:
            cw = c.winfo_width()
            ch = c.winfo_height()
        except Exception:
            return
        if cw < 2 or ch < 2:
            return
        c.delete("all")
        bg = self.cget("background")
        c.configure(bg=bg)

        # Visible row span from yview — convert fractional view to
        # line numbers and add a small overscan so partially-visible
        # rows at top/bottom still paint.
        try:
            first_frac, last_frac = self.yview()
        except Exception:
            return
        try:
            total_lines = int(self.index("end-1c").split(".")[0])
        except Exception:
            return
        if total_lines <= 0:
            return
        first_line = max(1, int(first_frac * total_lines))
        last_line = min(total_lines, int(last_frac * total_lines) + 2)

        # Current-line band — read from the active palette.
        cur_line_bg = None
        try:
            cur_line_bg = self.tag_cget("active_line", "background") or None
        except Exception:
            cur_line_bg = None

        try:
            ins_line = int(self.index("insert").split(".")[0])
        except Exception:
            ins_line = -1

        for line in range(first_line, last_line + 1):
            self._paint_line(line, ins_line, cur_line_bg)

        self._paint_selection()
        self._paint_diagnostics(first_line, last_line)
        self._paint_cursor()

    def _paint_line(self, line: int, ins_line: int,
                    cur_line_bg: str | None) -> None:
        """Paint a single 1-indexed text line on the canvas."""
        c = self._canvas
        try:
            bbox = self.bbox(f"{line}.0")
        except Exception:
            bbox = None
        if not bbox:
            return
        bx, by, _bw, bh = bbox
        cw = c.winfo_width()

        if line == ins_line and cur_line_bg:
            c.create_rectangle(0, by, cw, by + bh,
                               fill=cur_line_bg, outline="")

        try:
            line_text = self.get(f"{line}.0", f"{line}.end")
        except Exception:
            return
        if not line_text:
            return

        # Tokenize via pygments using the active lexer. Same coloring
        # source as CodeView's `highlight_line` — we just draw rather
        # than tag.
        fg = self.cget("foreground")
        x = bx
        for token, text in pygments.lex(line_text, self._lexer):
            if not text:
                continue
            if text == "\n":
                break
            color = self._color_for_token(str(token), fg)
            c.create_text(x, by, text=text, anchor="nw",
                          fill=color, font=self._font_obj)
            x += self._font_obj.measure(text)

    def _color_for_token(self, token_str: str, fallback: str) -> str:
        # Walk parent Token.* names (`Token.Name.Function` →
        # `Token.Name` → `Token`) until a color is found.
        name = token_str
        while name:
            if name in self._token_colors:
                return self._token_colors[name]
            if "." not in name:
                break
            name = name.rsplit(".", 1)[0]
        return fallback

    def _paint_selection(self) -> None:
        c = self._canvas
        try:
            ranges = self.tag_ranges("sel")
        except Exception:
            return
        if not ranges:
            return
        sel_bg = self.cget("selectbackground") or "#264f78"
        cw = c.winfo_width()
        # tag_ranges returns flat (start, end, start, end, ...) pairs;
        # for the editor's primary selection we have exactly one pair.
        for i in range(0, len(ranges), 2):
            start = str(ranges[i])
            end = str(ranges[i + 1])
            self._paint_index_range(start, end, sel_bg, cw)

    def _paint_index_range(self, start: str, end: str,
                           color: str, cw: int) -> None:
        c = self._canvas
        s_line = int(start.split(".")[0])
        e_line = int(end.split(".")[0])
        for line in range(s_line, e_line + 1):
            line_start = start if line == s_line else f"{line}.0"
            line_end = end if line == e_line else f"{line}.end"
            try:
                s_box = self.bbox(line_start)
                e_box = self.bbox(line_end)
            except Exception:
                s_box = e_box = None
            if not s_box:
                continue
            x1, y1, _, h = s_box
            if e_box:
                x2 = e_box[0]
            else:
                # Selection extends past visible width — fill to edge.
                x2 = cw
            # Multi-line selection extends the inner lines to the
            # right edge so the band visually wraps.
            if line < e_line:
                x2 = cw
            if x2 <= x1:
                # Empty-line selection — paint a tiny stub so the user
                # sees the line is selected.
                x2 = x1 + max(2, self._char_w // 2)
            c.create_rectangle(x1, y1, x2, y1 + h,
                               fill=color, outline="")

    def _paint_cursor(self) -> None:
        c = self._canvas
        # Suppress cursor while the widget doesn't hold focus — matches
        # Tk Text's native behavior.
        try:
            focus = self.focus_displayof()
        except Exception:
            focus = None
        if focus is not self:
            return
        try:
            bbox = self.bbox("insert")
        except Exception:
            bbox = None
        if not bbox:
            return
        x, y, _w, h = bbox
        color = self.cget("insertbackground") or "#aeafad"
        # 2-px caret — same as Tk's default insertwidth.
        c.create_line(x, y, x, y + h, fill=color, width=2)

    def _paint_diagnostics(self, first_line: int, last_line: int) -> None:
        """Draw wavy underlines for any `lsp_error`/`lsp_warning`/
        `lsp_info` tag ranges that fall inside the visible window."""
        c = self._canvas
        tag_colors = {
            "lsp_error":   self._diag_color("lsp_error",   "#f14c4c"),
            "lsp_warning": self._diag_color("lsp_warning", "#e5c07b"),
            "lsp_info":    self._diag_color("lsp_info",    "#67d8ef"),
        }
        for tag, color in tag_colors.items():
            try:
                ranges = self.tag_ranges(tag)
            except Exception:
                continue
            for i in range(0, len(ranges), 2):
                start = str(ranges[i])
                end = str(ranges[i + 1])
                s_line = int(start.split(".")[0])
                e_line = int(end.split(".")[0])
                if e_line < first_line or s_line > last_line:
                    continue
                self._paint_squiggly_range(start, end, color)

    def _diag_color(self, tag: str, fallback: str) -> str:
        try:
            color = self.tag_cget(tag, "underlinefg") or self.tag_cget(tag, "foreground")
        except Exception:
            color = None
        return color or fallback

    def _paint_squiggly_range(self, start: str, end: str, color: str) -> None:
        c = self._canvas
        s_line = int(start.split(".")[0])
        e_line = int(end.split(".")[0])
        for line in range(s_line, e_line + 1):
            line_start = start if line == s_line else f"{line}.0"
            line_end = end if line == e_line else f"{line}.end"
            try:
                s_box = self.bbox(line_start)
                e_box = self.bbox(line_end)
            except Exception:
                continue
            if not s_box:
                continue
            x1, y1, _, h = s_box
            x2 = e_box[0] if e_box else x1 + self._char_w
            # Zero-width diagnostic — expand to the word under the start
            # index so the squiggle is visible.
            if x2 <= x1:
                try:
                    we = self.bbox(self.index(f"{line_start} wordend"))
                    if we:
                        x2 = we[0]
                except Exception:
                    pass
            if x2 <= x1:
                x2 = x1 + self._char_w
            self._draw_squiggle(x1, x2, y1 + h - 2, color)

    @staticmethod
    def _build_squiggle_points(x1: float, x2: float, y: float) -> list[float]:
        pts: list[float] = []
        px = x1
        up = True
        while px < x2:
            pts.extend((px, y if up else y - 2))
            px += 2
            up = not up
        pts.extend((x2, y))
        return pts

    def _draw_squiggle(self, x1: float, x2: float, y: float, color: str) -> None:
        if x2 - x1 < 2:
            return
        pts = self._build_squiggle_points(x1, x2, y)
        self._canvas.create_line(*pts, fill=color, width=1)

    # ────────────────────────────────────────────────────────────────
    # Public API — mirrors CodeView 1:1
    # ────────────────────────────────────────────────────────────────

    @property
    def context_menu(self) -> Menu:
        if self._context_menu is None:
            self._context_menu = self._create_context_menu()
        return self._context_menu

    def _create_context_menu(self) -> Menu:
        menu = Menu(self, tearoff=0)
        menu.add_command(label="Cut",   command=self._cut_via_event)
        menu.add_command(label="Copy",  command=lambda: self._copy())
        menu.add_command(label="Paste", command=lambda: self._paste())
        menu.add_separator()
        menu.add_command(label="Select All", command=lambda: self._select_all())
        if self._default_context_menu:
            self.bind("<Button-3>",
                      lambda e: menu.tk_popup(e.x_root, e.y_root), add=True)
        return menu

    def _cut_via_event(self) -> None:
        self.event_generate("<<Cut>>")

    def _on_double_click(self, _event) -> str:
        # Native Text widget double-click triggers default word
        # selection — no extra work needed; just refresh the paint.
        self._queue_redraw()
        return ""

    def _select_all(self, *_) -> str:
        self.tag_add("sel", "1.0", "end-1c")
        self.mark_set("insert", "end-1c")
        self._queue_redraw()
        return "break"

    # ── Undo / redo / token tag snapshot (identical to CodeView) ────

    def _capture_token_tags(self) -> list | None:
        try:
            dumped = self.tk.call(
                self._orig, "dump", "-tag", "1.0", "end"
            )
        except TclError:
            return None
        if not dumped:
            return None
        # `dump -tag` returns a flat list: key1 val1 idx1 key2 val2 idx2 ...
        if isinstance(dumped, str):
            parts = dumped.split()
        else:
            parts = list(dumped)
        out: list[tuple[str, str, str]] = []
        for i in range(0, len(parts) - 2, 3):
            kind = str(parts[i])
            tag = str(parts[i + 1])
            idx = str(parts[i + 2])
            if kind in ("tagon", "tagoff") and tag.startswith("Token"):
                out.append((kind, tag, idx))
        return out

    def _restore_token_tags(self, snap_tags: list) -> None:
        if not snap_tags:
            return
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, "1.0", "end")
        # Replay pairs as tag_add ranges.
        opened: dict[str, str] = {}
        script_parts: list[str] = []
        for kind, tag, idx in snap_tags:
            if kind == "tagon":
                opened[tag] = idx
            elif kind == "tagoff" and tag in opened:
                start = opened.pop(tag)
                script_parts.append(f"{self._orig} tag add {tag} {start} {idx}")
        if script_parts:
            try:
                self.tk.eval("\n".join(script_parts))
            except TclError:
                pass

    def _undo(self, _event: Event | None = None) -> str:
        if not self._undo_stack:
            return "break"
        snap = self._undo_stack.pop()
        cur_text   = self.tk.call(self._orig, "get", "1.0", "end-1c")
        cur_cursor = self.tk.call(self._orig, "index", "insert")
        cur_extra  = self.on_snapshot() if self.on_snapshot else None
        cur_tags   = self._capture_token_tags()
        self._redo_stack.append((cur_text, cur_cursor, cur_extra, cur_tags))
        self._undo_restoring = True
        try:
            self.tk.call(self._orig, "delete", "1.0", "end")
            self.tk.call(self._orig, "insert", "1.0", snap[0])
            self.tk.call(self._orig, "mark", "set", "insert", snap[1])
            self.see("insert")
            if snap[3] is not None:
                self._restore_token_tags(snap[3])
            else:
                self.highlight_all()
            if self.on_undo_restore and len(snap) >= 3:
                self.on_undo_restore(snap[2])
        finally:
            self._undo_restoring = False
        self.event_generate("<<ContentChanged>>", when="tail")
        self._queue_redraw()
        return "break"

    def _redo(self, _event: Event | None = None) -> str:
        if not self._redo_stack:
            return "break"
        snap = self._redo_stack.pop()
        cur_text   = self.tk.call(self._orig, "get", "1.0", "end-1c")
        cur_cursor = self.tk.call(self._orig, "index", "insert")
        cur_extra  = self.on_snapshot() if self.on_snapshot else None
        cur_tags   = self._capture_token_tags()
        self._undo_stack.append((cur_text, cur_cursor, cur_extra, cur_tags))
        self._undo_restoring = True
        try:
            self.tk.call(self._orig, "delete", "1.0", "end")
            self.tk.call(self._orig, "insert", "1.0", snap[0])
            self.tk.call(self._orig, "mark", "set", "insert", snap[1])
            self.see("insert")
            if snap[3] is not None:
                self._restore_token_tags(snap[3])
            else:
                self.highlight_all()
            if self.on_undo_restore and len(snap) >= 3:
                self.on_undo_restore(snap[2])
        finally:
            self._undo_restoring = False
        self.event_generate("<<ContentChanged>>", when="tail")
        self._queue_redraw()
        return "break"

    def _clear_undo_pending(self) -> None:
        self._undo_pending_save = False

    def edit_reset(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    # ── Clipboard ───────────────────────────────────────────────────

    def _paste(self, *_):
        try:
            text = self.clipboard_get()
        except TclError:
            return "break"
        # Strip non-ASCII whitespace lookalikes — same scrubbing CodeView
        # does (workaround for invisible-char paste from web/PDF).
        cleaned = "".join(ch for ch in text if ch not in _BAD_PASTE_CHARS)
        try:
            sel = self.tag_ranges("sel")
            if sel:
                self.delete(sel[0], sel[1])
        except TclError:
            pass
        self.insert("insert", cleaned)
        self.see("insert")
        return "break"

    def _copy(self, *_):
        try:
            sel = self.tag_ranges("sel")
            if not sel:
                return "break"
            text = self.get(sel[0], sel[1])
        except TclError:
            return "break"
        self.clipboard_clear()
        self.clipboard_append(text)
        if self.on_copy:
            self.on_copy(text)
        return "break"

    # ── Tcl command proxy — fires undo, content events, and redraws ─

    def _cmd_proxy(self, command: str, *args) -> Any:
        try:
            _deleted_newlines = 0
            if command in {"insert", "delete", "replace"}:
                start_line = int(
                    str(self.tk.call(self._orig, "index", args[0])).split(".")[0]
                )
                end_line = start_line
                if len(args) == 3:
                    end_line = (
                        int(
                            str(self.tk.call(self._orig, "index", args[1])).split(".")[0]
                        )
                        - 1
                    )
                if not self._undo_restoring:
                    self._redo_stack.clear()
                    if not self._undo_pending_save:
                        snap_text = self.tk.call(self._orig, "get", "1.0", "end-1c")
                        snap_cursor = self.tk.call(self._orig, "index", "insert")
                        snap_extra = self.on_snapshot() if self.on_snapshot else None
                        snap_tags = self._capture_token_tags()
                        self._undo_stack.append(
                            (snap_text, snap_cursor, snap_extra, snap_tags)
                        )
                        if len(self._undo_stack) > 200:
                            self._undo_stack.pop(0)
                        self._undo_pending_save = True
                        self.after_idle(self._clear_undo_pending)
                if command in {"delete", "replace"} and self.on_lines_changed:
                    try:
                        end_idx = args[1] if len(args) >= 2 else f"{args[0]}+1c"
                        _deleted_newlines = self.tk.call(
                            self._orig, "get", args[0], end_idx
                        ).count("\n")
                    except Exception:
                        pass
            result = self.tk.call(self._orig, command, *args)
        except TclError as e:
            error = str(e)
            if (
                'tagged with "sel"' in error
                or "nothing to" in error
                or "bad text index" in error
            ):
                return ""
            raise e from None

        if command == "insert":
            lines = args[1].count("\n")
            if lines == 1:
                self.highlight_line(f"{start_line}.0")
            else:
                self.highlight_area(start_line, start_line + lines)
            self.event_generate("<<ContentChanged>>", when="tail")
            self.after(0, self.scroll_line_update)
            if lines and self.on_lines_changed:
                self.on_lines_changed(start_line, lines)
        elif command in {"replace", "delete"}:
            if start_line == end_line:
                self.highlight_line(f"{start_line}.0")
            else:
                self.highlight_area(start_line, end_line)
            self.event_generate("<<ContentChanged>>", when="tail")
            self.after(0, self.scroll_line_update)
            if command == "replace":
                inserted = args[2].count("\n") if len(args) >= 3 else 0
                net = inserted - _deleted_newlines
                if net and self.on_lines_changed:
                    self.on_lines_changed(start_line, net)
            elif _deleted_newlines and self.on_lines_changed:
                self.on_lines_changed(start_line, -_deleted_newlines)

        # Only queue a repaint for MUTATING commands. Read-only ops
        # (`tag names`, `tag ranges`, `tag cget`, `mark names`, …) are
        # invoked inside `_do_redraw` itself; queueing on them would
        # cascade into an infinite redraw loop.
        if command in {"insert", "delete", "replace"}:
            self._queue_redraw()
        elif command == "tag" and args and args[0] in {
            "add", "remove", "delete", "configure", "raise", "lower",
        }:
            self._queue_redraw()
        elif command == "mark" and args and args[0] in {
            "set", "unset", "gravity",
        }:
            self._queue_redraw()
        return result

    # ── Tokenizing helpers — same as CodeView ───────────────────────

    def _setup_tags(self, tags: dict[str, str]) -> None:
        # Mirror tags onto the Text widget (so any existing code that
        # iterates `tag_names()` keeps working) AND cache the color
        # table for the canvas paint path.
        self._token_colors = {}
        for key, value in tags.items():
            if isinstance(value, str):
                tag_name = f"Token.{key}"
                self.tag_configure(tag_name, foreground=value)
                self._token_colors[tag_name] = value

    def highlight_line(self, index: str) -> None:
        line_num = int(self.index(index).split(".")[0])
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, f"{line_num}.0", f"{line_num}.end")
        line_text = self.get(f"{line_num}.0", f"{line_num}.end").rstrip("\n")
        start_col = 0
        for token, text in pygments.lex(line_text, self._lexer):
            token = str(token)
            end_col = start_col + len(text)
            if text == "\n":
                break
            if token not in {"Token.Text.Whitespace", "Token.Text", "active_line"}:
                self.tag_add(token, f"{line_num}.{start_col}",
                             f"{line_num}.{end_col}")
            start_col = end_col
        self.tag_raise("sel")
        if "mc_cursor" in self.tag_names():
            self.tag_raise("mc_cursor")

    def highlight_all(self) -> None:
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, "1.0", "end")
        lines = self.get("1.0", "end")
        win_offsets = []
        for wname in self.window_names():
            with suppress(TclError):
                win_offsets.append(
                    int(self.tk.call(self._orig, "count", "-chars", "1.0", wname))
                )
        for offset in sorted(win_offsets):
            lines = lines[:offset] + " " + lines[offset:]
        line_offset = lines.count("\n") - lines.lstrip().count("\n")
        start_index = str(
            self.tk.call(self._orig, "index", f"1.0 + {line_offset} lines")
        )
        for token, text in pygments.lex(lines, self._lexer):
            token = str(token)
            end_index = self.index(f"{start_index} + {len(text)} chars")
            if token not in {"Token.Text.Whitespace", "Token.Text"}:
                self.tag_add(token, start_index, end_index)
            start_index = end_index
        self.tag_raise("sel")
        if "mc_cursor" in self.tag_names():
            self.tag_raise("mc_cursor")

    def highlight_area(self, start_line: int | None = None,
                       end_line: int | None = None) -> None:
        for tag in self.tag_names(index=None):
            if tag.startswith("Token"):
                self.tag_remove(tag, f"{start_line}.0", f"{end_line}.end")
        text = self.get(f"{start_line}.0", f"{end_line}.end")
        line_offset = text.count("\n") - text.lstrip().count("\n")
        start_index = str(
            self.tk.call(self._orig, "index",
                         f"{start_line}.0 + {line_offset} lines")
        )
        for token, text in pygments.lex(text, self._lexer):
            token = str(token)
            end_index = self.index(f"{start_index} + {len(text)} indices")
            if token not in {"Token.Text.Whitespace", "Token.Text"}:
                self.tag_add(token, start_index, end_index)
            start_index = end_index
        self.tag_raise("sel")
        if "mc_cursor" in self.tag_names():
            self.tag_raise("mc_cursor")

    def set_color_scheme(self,
                         color_scheme: dict[str, dict[str, str | int]] | str | None
                         ) -> None:
        if isinstance(color_scheme, str) and color_scheme in self.builtin_color_schemes:
            color_scheme = toml.load(color_schemes_dir / f"{color_scheme}.toml")
        elif color_scheme is None:
            color_scheme = toml.load(color_schemes_dir / "dracula.toml")
        assert isinstance(color_scheme, dict), (
            "Must be a dictionary or a built-in color scheme"
        )
        config, tags = _parse_scheme(color_scheme)
        self.configure(**config)
        self._setup_tags(tags)
        self.highlight_all()
        self._frame.configure(bg=self["background"])
        self._sticky.apply_colors(
            bg=self["background"],
            fg=self["foreground"],
            sep="#44475a",
            font=self.cget("font"),
        )
        self._minimap.apply_colors(
            bg=self["background"],
            fg=self["foreground"],
        )
        self._canvas.configure(bg=self["background"])
        # Font may have changed via config — re-derive metrics.
        self._font_obj = Font(font=self.cget("font"))
        self._line_h = self._font_obj.metrics("linespace")
        self._char_w = self._font_obj.measure("0")
        self._queue_redraw()

    def _set_lexer(self, lexer: LexerType) -> None:
        self._lexer = lexer() if inspect.isclass(lexer) else lexer
        self.highlight_all()
        if hasattr(self, "_sticky"):
            self._sticky._sync_tags()
        self._queue_redraw()

    def __setitem__(self, key: str, value) -> None:
        self.configure(**{key: value})

    def __getitem__(self, key: str) -> Any:
        return self.cget(key)

    def configure(self, **kwargs) -> None:
        lexer = kwargs.pop("lexer", None)
        color_scheme = kwargs.pop("color_scheme", None)
        if lexer is not None:
            self._set_lexer(lexer)
        if color_scheme is not None:
            self.set_color_scheme(color_scheme)
        super().configure(**kwargs)
        if "font" in kwargs:
            self._font_obj = Font(font=self.cget("font"))
            self._line_h = self._font_obj.metrics("linespace")
            self._char_w = self._font_obj.measure("0")
            if hasattr(self, "_minimap"):
                self._minimap.apply_colors(self["background"], self["foreground"])
        if "background" in kwargs:
            self._canvas.configure(bg=kwargs["background"])
        self._queue_redraw()

    config = configure

    # ── Geometry forwarders — operate on the outer frame ────────────

    def pack(self, *args, **kwargs) -> None:
        self._frame.pack(*args, **kwargs)

    def grid(self, *args, **kwargs) -> None:
        self._frame.grid(*args, **kwargs)

    def place(self, *args, **kwargs) -> None:
        self._frame.place(*args, **kwargs)

    def pack_forget(self) -> None:
        self._frame.pack_forget()

    def grid_forget(self) -> None:
        self._frame.grid_forget()

    def place_forget(self) -> None:
        self._frame.place_forget()

    def destroy(self) -> None:
        for widget in self._frame.winfo_children():
            BaseWidget.destroy(widget)
        BaseWidget.destroy(self._frame)

    # ── Scroll callbacks — also kick the canvas redraw ──────────────

    def horizontal_scroll(self, first: str | float, last: str | float) -> None:
        self._hs.set(first, last)
        self._queue_redraw()

    def show_minimap(self) -> None:
        self._minimap.grid()

    def hide_minimap(self) -> None:
        self._minimap.grid_remove()

    def vertical_scroll(self, first: str | float, last: str | float) -> None:
        self._vs.set(first, last)
        self._line_numbers.redraw()
        self._sticky.refresh()
        if hasattr(self, "_minimap"):
            self._minimap.on_scroll()
        self._queue_redraw()

    def scroll_line_update(self, event: Event | None = None) -> None:
        self.horizontal_scroll(*self.xview())
        self.vertical_scroll(*self.yview())
