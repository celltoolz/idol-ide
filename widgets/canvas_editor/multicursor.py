"""Multi-cursor support for CanvasCodeView.

Extracted from canvas_codeview.py (P3 decomposition). `MultiCursorMixin`
is inherited by `CanvasCodeView`.

Secondary cursor state is host-owned (`self._mc_cursors`,
`self._mc_anchors`, initialized in CanvasCodeView._init_state); the mixin
operates on it and on the shared buffer `self.lines`. It mirrors the
primary editing operations (insert / delete / newline / tab / bracket-
pair / move) onto every secondary cursor — a parallel implementation that
must stay in sync with the primary paths in canvas_codeview.py.

Not pure logic: `_draw_mc_selections` draws secondary selection highlights
directly on the host canvas (mirrors fold's _hit_fold_dots living with the
fold mixin despite touching render state).
"""
from __future__ import annotations

from .constants import _CLOSERS, _PAIRS


class MultiCursorMixin:
    """Secondary-cursor state + editing, mixed into CanvasCodeView.

    Reads/writes host state: `self._mc_cursors`, `self._mc_anchors`,
    `self.lines`, `self.cur_line`/`self.cur_col`, `self.tab_size`. Calls
    host methods (`_fire_change`, `render`, `_reset_blink`,
    `_coords_from_pixel`) and render attributes for selection drawing."""

    def mc_count(self) -> int:
        """Total cursor count (primary + secondaries). 0 when no secondaries."""
        return len(self._mc_cursors) + 1 if self._mc_cursors else 0

    def _on_alt_click(self, event):
        """Alt+click — add or remove a secondary cursor."""
        self.canvas.focus_set()
        if event.x < self._gutter_w:
            return "break"
        row, col = self._coords_from_pixel(event.x, event.y)
        # Remove if already there
        for i, mc in enumerate(self._mc_cursors):
            if mc == (row, col):
                self._mc_cursors.pop(i)
                self._mc_anchors.pop(i)
                self.render()
                return "break"
        # Don't duplicate the primary cursor
        if (row, col) != (self.cur_line, self.cur_col):
            self._mc_cursors.append((row, col))
            self._mc_anchors.append(None)
        self._reset_blink()
        self.render()
        return "break"

    def _draw_mc_selections(self, line_idx: int, line_text: str,
                            y: int, canvas_w: int) -> None:
        """Draw selection highlight for each secondary cursor that has an anchor."""
        sel_color = self._palette["select_bg"]
        for (mc_l, mc_c), mc_anchor in zip(self._mc_cursors, self._mc_anchors):
            if mc_anchor is None:
                continue
            a, b = mc_anchor, (mc_l, mc_c)
            s, e = (a, b) if a <= b else (b, a)
            if not (s[0] <= line_idx <= e[0]):
                continue
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
                x2 = canvas_w
            if x1 < x2:
                self.canvas.create_rectangle(x1, y, x2, y + self._line_h,
                                             fill=sel_color, outline="")

    def _mc_apply_key(self, keysym: str, char: str,
                      shift: bool, ctrl: bool) -> None:
        """Mirror a keystroke to all secondary cursors, bottom-to-top."""
        if not self._mc_cursors:
            return
        order = sorted(
            range(len(self._mc_cursors)),
            key=lambda i: (-self._mc_cursors[i][0], -self._mc_cursors[i][1]),
        )
        for idx in order:
            mc_l, mc_c = self._mc_cursors[idx]
            mc_anchor  = self._mc_anchors[idx]

            if keysym == "BackSpace":
                if mc_anchor is not None:
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = self._mc_delete_range(s[0], s[1], e[0], e[1])
                    mc_anchor = None
                elif mc_l > 0 or mc_c > 0:
                    ln = self.lines[mc_l]
                    if mc_c > 0:
                        prev_ch = ln[mc_c - 1]
                        next_ch = ln[mc_c] if mc_c < len(ln) else ""
                        if prev_ch in _PAIRS and _PAIRS[prev_ch] == next_ch:
                            self.lines[mc_l] = ln[:mc_c - 1] + ln[mc_c + 1:]
                            mc_c -= 1
                        else:
                            self.lines[mc_l] = ln[:mc_c - 1] + ln[mc_c:]
                            mc_c -= 1
                    else:
                        prev = self.lines[mc_l - 1]
                        mc_c = len(prev)
                        self.lines[mc_l - 1] = prev + self.lines[mc_l]
                        del self.lines[mc_l]
                        mc_l -= 1

            elif keysym == "Delete":
                if mc_anchor is not None:
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = self._mc_delete_range(s[0], s[1], e[0], e[1])
                    mc_anchor = None
                else:
                    ln = self.lines[mc_l]
                    if mc_c < len(ln):
                        self.lines[mc_l] = ln[:mc_c] + ln[mc_c + 1:]
                    elif mc_l + 1 < len(self.lines):
                        self.lines[mc_l] = ln + self.lines[mc_l + 1]
                        del self.lines[mc_l + 1]

            elif keysym == "Return":
                if mc_anchor is not None:
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = self._mc_delete_range(s[0], s[1], e[0], e[1])
                    mc_anchor = None
                ln = self.lines[mc_l]
                indent = " " * (len(ln) - len(ln.lstrip()))
                if ln[:mc_c].rstrip().endswith(":"):
                    indent += "    "
                self.lines[mc_l] = ln[:mc_c]
                self.lines.insert(mc_l + 1, indent + ln[mc_c:])
                mc_l += 1
                mc_c = len(indent)

            elif keysym == "Tab":
                if mc_anchor is not None:
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = self._mc_delete_range(s[0], s[1], e[0], e[1])
                    mc_anchor = None
                ln = self.lines[mc_l]
                sp = " " * self.tab_size
                self.lines[mc_l] = ln[:mc_c] + sp + ln[mc_c:]
                mc_c += self.tab_size

            elif keysym == "char" and char.isprintable():
                if mc_anchor is not None:
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = self._mc_delete_range(s[0], s[1], e[0], e[1])
                    mc_anchor = None
                mc_l, mc_c = self._mc_insert_char(mc_l, mc_c, char)

            elif keysym in ("Left", "Right", "Up", "Down",
                            "Home", "End", "Prior", "Next"):
                if shift:
                    # Extend the secondary selection: drop an anchor on the
                    # first shifted move, then always advance the cursor —
                    # matching the primary path in canvas_codeview._on_key.
                    # (Previously the first shifted move only set the anchor
                    # and never moved, so e.g. Shift+Home appeared dead.)
                    if mc_anchor is None:
                        mc_anchor = (mc_l, mc_c)
                    mc_l, mc_c = self._mc_move(mc_l, mc_c, keysym, ctrl)
                elif mc_anchor is not None and keysym in ("Left", "Right"):
                    # Collapse an existing selection to its near/far edge.
                    s, e = (mc_anchor, (mc_l, mc_c)) if mc_anchor <= (mc_l, mc_c) else ((mc_l, mc_c), mc_anchor)
                    mc_l, mc_c = (s if keysym == "Left" else e)
                    mc_anchor = None
                else:
                    mc_anchor = None
                    mc_l, mc_c = self._mc_move(mc_l, mc_c, keysym, ctrl)

            self._mc_cursors[idx] = (mc_l, max(0, mc_c))
            self._mc_anchors[idx] = mc_anchor

        if keysym not in ("Left", "Right", "Up", "Down",
                          "Home", "End", "Prior", "Next"):
            self._fire_change()

    def _mc_shift_same_line(self, line: int, col_threshold: int, delta: int) -> None:
        """Shift secondary cursor/anchor columns when the primary cursor
        edited the same line. Any secondary position on *line* at column
        >= *col_threshold* is moved by *delta* (positive = insertion,
        negative = deletion). Must be called BEFORE _mc_apply_key so the
        secondary cursors start from the correct post-edit columns."""
        for i in range(len(self._mc_cursors)):
            mc_l, mc_c = self._mc_cursors[i]
            if mc_l == line and mc_c >= col_threshold:
                self._mc_cursors[i] = (mc_l, max(0, mc_c + delta))
            anch = self._mc_anchors[i]
            if anch is not None and anch[0] == line and anch[1] >= col_threshold:
                self._mc_anchors[i] = (anch[0], max(0, anch[1] + delta))

    def _mc_delete_range(self, sl: int, sc: int,
                         el: int, ec: int) -> tuple[int, int]:
        """Delete the range [sl,sc)→[el,ec) from self.lines."""
        if sl == el:
            ln = self.lines[sl]
            self.lines[sl] = ln[:sc] + ln[ec:]
        else:
            head = self.lines[sl][:sc]
            tail = self.lines[el][ec:]
            self.lines[sl] = head + tail
            del self.lines[sl + 1: el + 1]
        return sl, sc

    def _mc_insert_char(self, line: int, col: int,
                        char: str) -> tuple[int, int]:
        """Insert char at (line, col) with bracket pairing. Return new pos."""
        ln = self.lines[line]
        next_ch = ln[col] if col < len(ln) else ""
        if char in _CLOSERS and next_ch == char:
            return line, col + 1
        if char in _PAIRS and not next_ch.isalnum() and next_ch != "_":
            self.lines[line] = ln[:col] + char + _PAIRS[char] + ln[col:]
            return line, col + 1
        self.lines[line] = ln[:col] + char + ln[col:]
        return line, col + 1

    def _mc_move(self, line: int, col: int,
                 keysym: str, ctrl: bool) -> tuple[int, int]:
        """Move a secondary cursor one step. Returns new (line, col)."""
        if keysym == "Left":
            if col > 0:
                col -= 1
            elif line > 0:
                line -= 1
                col = len(self.lines[line])
        elif keysym == "Right":
            if col < len(self.lines[line]):
                col += 1
            elif line + 1 < len(self.lines):
                line += 1
                col = 0
        elif keysym in ("Up", "Prior"):
            line = max(0, line - (1 if keysym == "Up" else 10))
            col = min(col, len(self.lines[line]))
        elif keysym in ("Down", "Next"):
            line = min(len(self.lines) - 1, line + (1 if keysym == "Down" else 10))
            col = min(col, len(self.lines[line]))
        elif keysym == "Home":
            ln = self.lines[line]
            first_nw = len(ln) - len(ln.lstrip())
            col = 0 if col == first_nw else first_nw
        elif keysym == "End":
            col = len(self.lines[line])
        return line, col
