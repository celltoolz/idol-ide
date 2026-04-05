"""TkLineNumbers - Line number widget for tkinter Text widgets, with fold markers."""

from __future__ import annotations

import re
from platform import system
from tkinter import Canvas, Event, Label, Misc, Text, getboolean
from tkinter.font import Font
from typing import Callable, Optional

SYSTEM = system()


def scroll_fix(delta: int, num: bool = False) -> int:
    """Correct scroll delta across platforms."""
    if delta in (4, 5) and num:
        return -3 if delta == 4 else 3
    if SYSTEM == "Darwin":
        return -delta
    return -(delta // 120)


class TkLineNumbers(Canvas):
    """Displays line numbers beside a Text widget and draws fold markers.

    Click a line number to move the cursor there.
    Click the fold marker (the small box) to fold/unfold the block.
    Double-click a line number to select that line.
    """

    def __init__(
        self,
        master: Misc,
        textwidget: Text,
        justify: str = "left",
        colors: Callable[[], tuple[str, str]] | tuple[str, str] | None = None,
        *args,
        **kwargs,
    ) -> None:
        Canvas.__init__(
            self,
            master,
            width=kwargs.pop("width", 40),
            highlightthickness=kwargs.pop("highlightthickness", 0),
            borderwidth=kwargs.pop("borderwidth", 2),
            relief=kwargs.pop("relief", "ridge"),
            *args,
            **kwargs,
        )
        self.textwidget = textwidget
        self.justify = justify
        self.colors = colors
        self.foreground_color: str = "black"
        self.font_size: int = 10
        self.cancellable_after: Optional[str] = None
        self.click_pos: Optional[str] = None
        self.x: Optional[int] = None
        self.y: Optional[int] = None
        self._dots: dict[str, Label] = {}

        # Git gutter: maps line_number → 'added' | 'modified' | 'deleted'
        self._hunk_map: dict[int, str] = {}

        self.config(cursor="right_ptr")
        self.set_colors()

        self.bind("<<ThemeChanged>>", self.set_colors, add=True)
        self.bind("<MouseWheel>", self.mouse_scroll, add=True)
        self.bind("<Button-4>", self.mouse_scroll, add=True)
        self.bind("<Button-5>", self.mouse_scroll, add=True)
        self.bind("<Button-1>", self.click_see, add=True)
        self.bind("<ButtonRelease-1>", self.unclick, add=True)
        self.bind("<Double-Button-1>", self.double_click, add=True)
        self.bind("<Button1-Motion>", self.in_widget_select_mouse_drag, add=True)
        self.bind("<Button1-Leave>", self.mouse_off_screen_scroll, add=True)
        self.bind("<Button1-Enter>", self.stop_mouse_off_screen_scroll, add=True)

        textwidget["yscrollcommand"] = self.redraw
        self.redraw()

    # ── Drawing ───────────────────────────────────────────────────────────────

    def redraw(self, *_) -> None:
        """Redraw all line numbers and fold markers."""
        self.resize()
        self.set_colors()
        self.delete("all")

        first_line = int(self.textwidget.index("@0,0").split(".")[0])
        last_line = int(self.textwidget.index("end").split(".")[0]) - 1

        for lineno in range(first_line, last_line + 1):
            if self._is_elided(lineno):
                continue
            dlineinfo = self.textwidget.dlineinfo(f"{lineno}.0")
            if dlineinfo is None:
                continue
            self._draw_line_number(lineno, dlineinfo)
            fold = self._get_fold_range(lineno, last_line)
            if fold:
                _, end_line = fold
                self._register_fold_tag(lineno, end_line)
                is_folded = self.textwidget.tag_cget(f"fold_{lineno}", "elide") == "1"
                size = self.font_size if self.font_size % 2 == 0 else self.font_size - 1
                self._draw_fold_marker(
                    int(self.winfo_reqwidth()) - (size + 5),
                    dlineinfo[1] + 4,
                    size,
                    is_folded,
                )

    def _is_elided(self, lineno: int) -> bool:
        tags = self.textwidget.tag_names(f"{lineno}.0")
        return any(
            getboolean(self.textwidget.tag_cget(t, "elide") or "false") for t in tags
        )

    def _get_fold_range(self, lineno: int, last_line: int) -> tuple[int, int] | None:
        """Return (lineno, end_lineno) if this line starts a foldable block."""
        line_text = self._line_text(lineno)
        if not line_text.rstrip().endswith((":", "(", "[", "{")):
            return None

        prev_text = self._line_text(lineno - 1)
        indent = (
            len(prev_text) - len(prev_text.lstrip())
            if prev_text.endswith("\\")
            else len(line_text) - len(line_text.lstrip())
        )

        end = lineno
        while end < last_line:
            next_text = self._line_text(end + 1)
            next_indent = len(next_text) - len(next_text.lstrip())
            if next_indent <= indent and next_text.strip():
                break
            end += 1

        # Trim trailing blank lines from the fold range
        while end > lineno and not self._line_text(end).strip():
            end -= 1

        return (lineno, end) if end > lineno else None

    def _line_text(self, lineno: int) -> str:
        return self.textwidget.get(f"{lineno}.0", f"{lineno}.0 lineend")

    def _register_fold_tag(self, lineno: int, end_lineno: int) -> None:
        marker = f"fold_{lineno}"
        self.textwidget.mark_set(marker, f"{lineno}.0 lineend")
        self.textwidget.tag_add(
            marker, f"{lineno}.0 lineend", f"{end_lineno}.0 lineend"
        )

    def set_git_hunks(self, hunks: list[tuple[int, int, str]]) -> None:
        """Update gutter indicators from a list of (start, count, kind) tuples."""
        self._hunk_map = {}
        for start, count, kind in hunks:
            for ln in range(start, start + max(count, 1)):
                self._hunk_map[ln] = kind
        self.redraw()

    def _draw_line_number(self, lineno: int, dlineinfo: tuple) -> None:
        x = {"left": 0, "right": int(self["width"]), "center": int(self["width"]) / 2}[
            self.justify
        ]
        anchor = {"left": "nw", "right": "ne", "center": "n"}[self.justify]
        text = f" {lineno} " if self.justify != "center" else str(lineno)
        self.create_text(
            x,
            dlineinfo[1],
            text=text,
            anchor=anchor,
            font=self.textwidget.cget("font"),
            fill=self.foreground_color,
        )
        # Git gutter strip (3 px wide on the left edge)
        kind = self._hunk_map.get(lineno)
        if kind:
            _GUTTER_COLORS = {
                "added":    "#4ec994",
                "modified": "#c5a028",
                "deleted":  "#f14c4c",
            }
            color = _GUTTER_COLORS.get(kind)
            if color:
                y, h = dlineinfo[1], dlineinfo[3]
                self.create_rectangle(0, y, 3, y + h, fill=color, outline="")

    def _draw_fold_marker(self, x: int, y: int, size: int, is_folded: bool) -> None:
        """Draw a square ⊟ when expanded, ⊞ when folded."""
        fg = self.textwidget["fg"]
        bg = self.textwidget["bg"]
        cx = x + size / 2
        cy = y + size / 2
        arm = size * 0.28

        # Square
        self.create_rectangle(x, y, x + size, y + size, fill=bg, outline=fg, width=1)

        # Horizontal bar (always — the minus part)
        self.create_line(cx - arm, cy, cx + arm + 1, cy, fill=fg, width=1)

        # Vertical bar only when folded (turns - into +)
        if is_folded:
            self.create_line(cx, cy - arm, cx, cy + arm + 1, fill=fg, width=1)

    # ── Sizing & Colors ───────────────────────────────────────────────────────

    def resize(self) -> None:
        end = self.textwidget.index("end").split(".")[0]
        font = Font(font=self.textwidget.cget("font"))
        measure_str = " 1234 ⊞" if int(end) <= 1000 else f" {end}  ⊞"
        self.config(width=font.measure(measure_str))

    def set_colors(self, _: Event | None = None) -> None:
        self.font_size = int(re.findall(r"\d+", self.textwidget.cget("font"))[-1])
        if self.colors is None:
            self.foreground_color = self.textwidget["fg"]
            self["bg"] = self.textwidget["bg"]
        elif isinstance(self.colors, tuple):
            self.foreground_color, self["bg"] = self.colors
        else:
            self.foreground_color, self["bg"] = self.colors()

    # ── Mouse / Scroll ────────────────────────────────────────────────────────

    def mouse_scroll(self, event: Event) -> None:
        self.textwidget.yview_scroll(
            int(
                scroll_fix(event.delta if event.delta else event.num, event.num != "??")
            ),
            "units",
        )
        self.redraw()

    def click_see(self, event: Event) -> None:
        if event.state == 1:
            self.shift_click(event)
            return

        self.textwidget.tag_remove("sel", "1.0", "end")
        line = self.textwidget.index(f"@{event.x},{event.y}").split(".")[0]
        click_pos = f"{line}.0"

        marker = f"fold_{line}"
        in_fold_zone = (
            marker in self.textwidget.mark_names()
            and event.x > self.winfo_reqwidth() - (self.font_size + 5)
        )
        if in_fold_zone:
            if self.textwidget.tag_cget(marker, "elide") in ("0", ""):
                # Fold: hide the block and show ··· inline
                self.textwidget.tag_config(marker, elide=True)
                self._show_dots(line)
            else:
                # Unfold: remove elide tag and destroy the dots label
                self._hide_dots(line)
                self.textwidget.tag_delete(marker)

        self.textwidget.mark_set("insert", click_pos)
        self.textwidget.see("insert")
        self.click_pos = click_pos
        self.redraw()

    def _show_dots(self, line: str) -> None:
        """Embed a ··· label at the end of *line* to indicate a folded block."""
        self._hide_dots(line)  # destroy any stale widget first
        fg = self.textwidget["fg"]
        bg = self.textwidget["bg"]
        font = self.textwidget.cget("font")
        lbl = Label(
            self.textwidget,
            text=" ···",
            font=font,
            fg="#858585",
            bg=bg,
            cursor="hand2",
            bd=0,
            padx=0,
            pady=0,
        )
        lbl.bind("<Button-1>", lambda e, l=line: self._unfold_from_dots(l))
        self.textwidget.window_create(f"{line}.0 lineend", window=lbl)
        self._dots[line] = lbl

    def _hide_dots(self, line: str) -> None:
        """Destroy the dots label for *line* if it exists."""
        lbl = self._dots.pop(line, None)
        if lbl is not None:
            try:
                lbl.destroy()
            except Exception:
                pass

    def _unfold_from_dots(self, line: str) -> None:
        """Clicking the ··· label unfolds the block."""
        marker = f"fold_{line}"
        self._hide_dots(line)
        self.textwidget.tag_delete(marker)
        self.redraw()

    def unclick(self, _: Event) -> None:
        self.click_pos = None

    def double_click(self, _: Event) -> None:
        self.textwidget.tag_remove("sel", "1.0", "end")
        self.textwidget.tag_add("sel", "insert", "insert + 1 line")
        self.redraw()

    def mouse_off_screen_scroll(self, event: Event) -> None:
        self.x = event.x
        self.y = event.y
        self.text_auto_scan(event)

    def text_auto_scan(self, event: Event) -> None:
        if self.click_pos is None:
            return
        if self.y >= self.winfo_height():
            self.textwidget.yview_scroll(1 + self.y - self.winfo_height(), "pixels")
        elif self.y < 0:
            self.textwidget.yview_scroll(-1 + self.y, "pixels")
        elif self.x >= self.winfo_width():
            self.textwidget.xview_scroll(2, "units")
        elif self.x < 0:
            self.textwidget.xview_scroll(-2, "units")
        else:
            return
        self.select_text(self.x - self.winfo_width(), self.y)
        self.cancellable_after = self.after(50, self.text_auto_scan, event)
        self.redraw()

    def stop_mouse_off_screen_scroll(self, _: Event) -> None:
        if self.cancellable_after is not None:
            self.after_cancel(self.cancellable_after)
            self.cancellable_after = None

    def in_widget_select_mouse_drag(self, event: Event) -> None:
        if self.click_pos is None:
            return
        self.x = event.x
        self.y = event.y
        self.select_text(event.x - self.winfo_width(), event.y)
        self.redraw()

    def select_text(self, x: int, y: int) -> None:
        drag_pos = self.textwidget.index(f"@{x},{y}")
        if self.textwidget.compare(drag_pos, ">", self.click_pos):
            start, end = self.click_pos, drag_pos
        else:
            start, end = drag_pos, self.click_pos
        self.textwidget.tag_remove("sel", "1.0", "end")
        self.textwidget.tag_add("sel", start, end)
        self.textwidget.mark_set("insert", drag_pos)

    def shift_click(self, event: Event) -> None:
        start = self.textwidget.index("insert")
        end = self.textwidget.index(f"@0,{event.y}")
        self.textwidget.tag_remove("sel", "1.0", "end")
        if self.textwidget.compare(start, ">", end):
            start, end = end, start
        self.textwidget.tag_add("sel", start, end)
        self.redraw()
