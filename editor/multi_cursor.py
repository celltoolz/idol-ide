"""MultiCursor — secondary cursor management for the code editor."""
from __future__ import annotations


def _pos_key(index: str) -> tuple[int, int]:
    r, c = index.split(".")
    return int(r), int(c)


class MultiCursor:
    """Tracks one or more secondary cursor positions in a Text widget.

    Secondary cursors are stored as named marks.  On each keypress the same
    edit is applied at every secondary cursor (bottom-to-top so earlier
    insertions don't shift later positions).  A blue background tag shows
    where each secondary cursor sits.  Shift+arrow extends an independent
    selection per cursor, stored in mc_sel tags backed by anchor marks.
    """

    TAG     = "mc_cursor"
    SEL_TAG = "mc_sel"

    _PAIRS  = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}
    _OPEN   = set("([{")
    _CLOSE  = set(")]}")
    _QUOTES = set("'\"")

    def __init__(self, text_widget, tab_size: int = 4) -> None:
        self._text     = text_widget
        self.tab_size  = tab_size
        self._marks:   list[str] = []
        self._anchors: dict[str, str] = {}   # mark_name → anchor_mark_name
        self._seq      = 0
        text_widget.tag_configure(
            self.TAG,
            background="#569cd6",
            foreground="#1e1e1e",
            underline=True,
        )
        text_widget.tag_configure(
            self.SEL_TAG,
            background="#264f78",
        )

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def active(self) -> bool:
        return bool(self._marks)

    def count(self) -> int:
        """Total cursor count (primary + secondaries)."""
        return len(self._marks) + 1

    def add(self, index: str) -> None:
        """Add a secondary cursor at *index* (e.g. '@x,y' or '3.5')."""
        name = f"_mc{self._seq}"
        self._seq += 1
        self._text.mark_set(name, index)
        self._text.mark_gravity(name, "right")
        self._marks.append(name)
        self._redraw()

    def clear(self) -> None:
        """Remove all secondary cursors and selections."""
        self._clear_all_anchors()
        for m in self._marks:
            try:
                self._text.mark_unset(m)
            except Exception:
                pass
        self._marks.clear()
        self._text.tag_remove(self.TAG, "1.0", "end")

    def apply_key(self, event) -> None:
        """Mirror a key event at all secondary cursor positions."""
        keysym = event.keysym
        char   = event.char
        shift  = bool(event.state & 0x1)
        ctrl   = bool(event.state & 0x4)

        for mark in self._sorted_bottom_first():
            idx = self._text.index(mark)

            if keysym == "BackSpace":
                sel = self._sel_range(mark)
                if sel:
                    self._text.delete(sel[0], sel[1])
                    self._clear_anchor(mark)
                elif self._text.compare(idx, ">", "1.0"):
                    before = self._text.get(f"{idx} - 1c", idx)
                    after  = self._text.get(idx, f"{idx} + 1c")
                    if before in self._PAIRS and after == self._PAIRS[before]:
                        self._text.delete(f"{idx} - 1c", f"{idx} + 1c")
                    else:
                        self._text.delete(f"{idx} - 1c", idx)

            elif keysym == "Delete":
                sel = self._sel_range(mark)
                if sel:
                    self._text.delete(sel[0], sel[1])
                    self._clear_anchor(mark)
                elif self._text.compare(idx, "<", "end - 1c"):
                    self._text.delete(idx)

            elif keysym == "Return":
                sel = self._sel_range(mark)
                if sel:
                    self._text.delete(sel[0], sel[1])
                    self._clear_anchor(mark)
                    idx = self._text.index(mark)
                line_txt = self._text.get(f"{idx} linestart", f"{idx} lineend")
                indent   = len(line_txt) - len(line_txt.lstrip())
                self._text.insert(idx, f"\n{' ' * indent}")

            elif keysym == "Tab":
                sel = self._sel_range(mark)
                if sel:
                    self._text.delete(sel[0], sel[1])
                    self._clear_anchor(mark)
                    idx = self._text.index(mark)
                self._text.insert(idx, " " * self.tab_size)

            elif keysym in ("Left", "KP_Left", "Right", "KP_Right",
                            "Up", "KP_Up", "Down", "KP_Down",
                            "Home", "KP_Home", "End", "KP_End"):
                if shift:
                    self._shift_nav_mark(mark, idx, keysym, ctrl)
                else:
                    sel = self._sel_range(mark)
                    self._clear_anchor(mark)
                    if sel and keysym in ("Left", "KP_Left"):
                        self._text.mark_set(mark, sel[0])
                    elif sel and keysym in ("Right", "KP_Right"):
                        self._text.mark_set(mark, sel[1])
                    else:
                        self._nav_mark(mark, idx, keysym, ctrl)

            elif char and char.isprintable():
                sel = self._sel_range(mark)
                if sel:
                    self._text.delete(sel[0], sel[1])
                    self._clear_anchor(mark)
                    idx = self._text.index(mark)
                next_ch = self._text.get(idx, f"{idx} + 1c")
                if char in self._CLOSE:
                    if next_ch == char:
                        self._text.mark_set(mark, f"{idx} + 1c")
                    else:
                        self._text.insert(idx, char)
                elif char in self._QUOTES:
                    before = self._text.get(f"{idx} linestart", idx)
                    if before.count(char) % 2 == 1:
                        self._text.insert(idx, char)  # inside string → close it
                    elif next_ch == char:
                        self._text.mark_set(mark, f"{idx} + 1c")
                    elif next_ch and (next_ch.isalnum() or next_ch == "_"):
                        self._text.insert(idx, char)
                    else:
                        self._text.insert(idx, char + char)
                        self._text.mark_set(mark, self._text.index(f"{mark} - 1c"))
                elif char in self._OPEN:
                    if next_ch and (next_ch.isalnum() or next_ch == "_"):
                        self._text.insert(idx, char)
                    else:
                        self._text.insert(idx, char + self._PAIRS[char])
                        self._text.mark_set(mark, self._text.index(f"{mark} - 1c"))
                else:
                    self._text.insert(idx, char)

        # _repaint_sel first so mc_sel is raised above syntax tags,
        # then _redraw raises mc_cursor above mc_sel.
        self._text.after_idle(self._repaint_sel)
        self._text.after_idle(self._redraw)

    # ── Internal ──────────────────────────────────────────────────────────────

    def _shift_nav_mark(self, mark: str, idx: str, keysym: str, ctrl: bool) -> None:
        """Extend the selection for *mark* in *keysym* direction."""
        if mark not in self._anchors:
            anchor_name = f"_mca{mark[3:]}"   # _mc0 → _mca0
            self._text.mark_set(anchor_name, idx)
            self._text.mark_gravity(anchor_name, "left")
            self._anchors[mark] = anchor_name
        self._nav_mark(mark, idx, keysym, ctrl)

    def _sel_range(self, mark: str) -> tuple[str, str] | None:
        """Return (start, end) of the active selection for *mark*, or None."""
        if mark not in self._anchors:
            return None
        anchor_pos = self._text.index(self._anchors[mark])
        mark_pos   = self._text.index(mark)
        if anchor_pos == mark_pos:
            return None
        start, end = sorted([anchor_pos, mark_pos], key=_pos_key)
        return start, end

    def _clear_anchor(self, mark: str) -> None:
        anchor = self._anchors.pop(mark, None)
        if anchor:
            try:
                self._text.mark_unset(anchor)
            except Exception:
                pass

    def _clear_all_anchors(self) -> None:
        for anchor in self._anchors.values():
            try:
                self._text.mark_unset(anchor)
            except Exception:
                pass
        self._anchors.clear()
        self._text.tag_remove(self.SEL_TAG, "1.0", "end")

    def _repaint_sel(self) -> None:
        """Redraw mc_sel highlight ranges for all active selections."""
        self._text.tag_remove(self.SEL_TAG, "1.0", "end")
        for mark, anchor_mark in self._anchors.items():
            try:
                mark_pos   = self._text.index(mark)
                anchor_pos = self._text.index(anchor_mark)
                start, end = sorted([mark_pos, anchor_pos], key=_pos_key)
                if start != end:
                    self._text.tag_add(self.SEL_TAG, start, end)
            except Exception:
                pass
        if self._anchors:
            self._text.tag_raise(self.SEL_TAG)

    def _nav_mark(self, mark: str, idx: str, keysym: str, ctrl: bool) -> None:
        """Move *mark* one step in the direction given by *keysym*."""
        row, col = map(int, idx.split("."))
        if keysym in ("Left", "KP_Left"):
            new = f"{idx} - 1c wordstart" if ctrl else f"{idx} - 1c"
        elif keysym in ("Right", "KP_Right"):
            new = f"{idx} wordend" if ctrl else f"{idx} + 1c"
        elif keysym in ("Up", "KP_Up"):
            new = f"{max(1, row - 1)}.{col}"
        elif keysym in ("Down", "KP_Down"):
            new = f"{row + 1}.{col}"
        elif keysym in ("Home", "KP_Home"):
            line_txt = self._text.get(f"{idx} linestart", f"{idx} lineend")
            indent   = len(line_txt) - len(line_txt.lstrip())
            new = f"{row}.0" if col == indent else f"{row}.{indent}"
        elif keysym in ("End", "KP_End"):
            new = f"{idx} lineend"
        else:
            return
        self._text.mark_set(mark, self._text.index(new))

    def _sorted_bottom_first(self) -> list[str]:
        """Return marks sorted from the last line to the first."""
        return sorted(self._marks, key=lambda m: _pos_key(self._text.index(m)), reverse=True)

    def _redraw(self) -> None:
        """Repaint highlights for all cursors (primary + secondaries)."""
        self._text.tag_remove(self.TAG, "1.0", "end")
        all_positions = [self._text.index("insert")] + [
            self._text.index(m) for m in self._marks
        ]
        for idx in all_positions:
            if (self._text.compare(idx, ">=", f"{idx} lineend")
                    and self._text.compare(idx, ">", f"{idx} linestart")):
                self._text.tag_add(self.TAG, f"{idx} - 1c", idx)
            else:
                self._text.tag_add(self.TAG, idx, f"{idx} + 1c")
        self._text.tag_raise(self.TAG)
