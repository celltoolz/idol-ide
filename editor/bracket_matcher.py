from __future__ import annotations

import re


class BracketMatcher:
    OPEN_TO_CLOSE = {"{": "}", "[": "]", "(": ")"}
    CLOSE_TO_OPEN = {v: k for k, v in OPEN_TO_CLOSE.items()}

    def match(self, event) -> None:
        widget = event.widget
        widget.tag_remove("matching_paren", "1.0", "end")
        marks = ["insert"] + [m for m in widget.mark_names() if m.startswith("_mc")]
        for mark in marks:
            self._match_at(widget, mark)

    def _match_at(self, widget, mark: str) -> None:
        mark_pos = widget.index(mark)
        if mark_pos == "1.0":
            return

        # Spaces around the operator are required — Tk can't parse "3.5-1c" but
        # can parse "3.5 - 1c". CodeView's proxy silently swallows bad-index
        # errors, so missing spaces caused _match_at to bail out invisibly.
        before = widget.index(f"{mark_pos} - 1c")
        if widget.get(f"{before} - 1c", before) == "\\":
            return

        last_char = widget.get(before, f"{before} + 1c")
        cursor_line, cursor_col = map(int, mark_pos.split("."))

        if last_char in self.OPEN_TO_CLOSE:
            text = widget.get(mark_pos, "end - 1c")
            regex = r"(?<!\\)[()\[\]{}]"
            mapping = self.CLOSE_TO_OPEN
            backwards = False
        elif last_char in self.CLOSE_TO_OPEN:
            text = widget.get("1.0", before)[::-1]
            regex = r"[()\[\]{}](?!\\)"
            mapping = self.OPEN_TO_CLOSE
            backwards = True
        else:
            return

        stack = [last_char]
        for m in re.finditer(regex, text):
            char = m.group()
            if char not in mapping:
                stack.append(char)
                continue
            if stack.pop() != mapping[char]:
                return
            if not stack:
                lineno, col = self._calc_pos(backwards, text, m, cursor_line, cursor_col)
                widget.tag_add("matching_paren", before)
                widget.tag_add("matching_paren", f"{lineno}.{col}")
                break

    @staticmethod
    def _calc_pos(backwards, text, match, cursor_line, cursor_col):
        if backwards:
            lineno = 1 + text.count("\n", match.end())
            col = (
                len(text) - match.end()
                if lineno == 1
                else text.index("\n", match.end()) - match.end()
            )
        else:
            lineno = cursor_line + text.count("\n", 0, match.start())
            col = (
                cursor_col + match.start()
                if lineno == cursor_line
                else match.start() - text.rindex("\n", 0, match.start()) - 1
            )
        return lineno, col
