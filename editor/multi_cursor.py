"""MultiCursor — secondary cursor management for the code editor."""
from __future__ import annotations


class MultiCursor:
    """Tracks one or more secondary cursor positions in a Text widget.

    Secondary cursors are stored as named marks.  On each keypress the same
    edit is applied at every secondary cursor (bottom-to-top so earlier
    insertions don't shift later positions).  A blue background tag shows
    where each secondary cursor sits.
    """

    TAG = "mc_cursor"

    def __init__(self, text_widget, tab_size: int = 4) -> None:
        self._text     = text_widget
        self.tab_size  = tab_size
        self._marks:   list[str] = []
        self._seq      = 0
        text_widget.tag_configure(
            self.TAG,
            background="#569cd6",
            foreground="#1e1e1e",
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
        """Remove all secondary cursors."""
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

        for mark in self._sorted_bottom_first():
            idx = self._text.index(mark)

            if keysym == "BackSpace":
                if self._text.compare(idx, ">", "1.0"):
                    self._text.delete(f"{idx}-1c", idx)

            elif keysym == "Delete":
                if self._text.compare(idx, "<", "end-1c"):
                    self._text.delete(idx)

            elif keysym == "Return":
                line_txt = self._text.get(f"{idx} linestart", f"{idx} lineend")
                indent   = len(line_txt) - len(line_txt.lstrip())
                self._text.insert(idx, f"\n{' ' * indent}")

            elif keysym == "Tab":
                self._text.insert(idx, " " * self.tab_size)

            elif char and char.isprintable():
                self._text.insert(idx, char)

        self._redraw()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _sorted_bottom_first(self) -> list[str]:
        """Return marks sorted from the last line to the first."""
        def _key(m: str) -> tuple[int, int]:
            r, c = self._text.index(m).split(".")
            return (int(r), int(c))
        return sorted(self._marks, key=_key, reverse=True)

    def _redraw(self) -> None:
        """Repaint highlights for all cursors (primary + secondaries)."""
        self._text.tag_remove(self.TAG, "1.0", "end")
        # Include the primary INSERT cursor so everything looks uniform
        all_positions = [self._text.index("insert")] + [
            self._text.index(m) for m in self._marks
        ]
        for idx in all_positions:
            if self._text.compare(idx, ">=", f"{idx} lineend"):
                if self._text.compare(idx, ">", f"{idx} linestart"):
                    self._text.tag_add(self.TAG, f"{idx}-1c", idx)
            else:
                self._text.tag_add(self.TAG, idx, f"{idx}+1c")
