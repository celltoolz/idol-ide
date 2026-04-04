from __future__ import annotations

from tkinter.font import Font


class KeyHandler:
    """Handles smart key press behaviour for a CodeView widget.

    One instance per tab so state (home toggle) is per-editor.
    """

    _PAIRS = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}
    _OPEN_MAP = {"parenleft": "(", "bracketleft": "[", "braceleft": "{"}
    _CLOSE_MAP = {"parenright": ")", "bracketright": "]", "braceright": "}"}
    _QUOTE_MAP = {"apostrophe": "'", "quotedbl": '"'}
    # All bracket/quote open chars for selection-wrap
    _ALL_OPEN = set("([{'\"`")

    def __init__(self, tab_size: int = 4, smart_pairs: bool = True) -> None:
        self.tab_size = tab_size
        self.smart_pairs = smart_pairs
        self._home_toggle = False
        self.overwrite = False   # Insert key toggle

    def handle(self, event, codeview) -> str | None:
        """Process a key event.  Returns 'break' to suppress default handling."""
        codeview.tag_remove("matching_word", "1.0", "end")
        codeview.tag_remove("Token.highlight", "1.0", "end")

        shift = bool(event.state & 0x1)

        match event.keysym:
            case "Tab":
                self._home_toggle = False
                if shift:
                    return self._handle_unindent(codeview)
                # Indent selected lines if multiple lines are selected
                if codeview.tag_ranges("sel"):
                    return self._handle_indent_selection(codeview)
                codeview.insert("insert", " " * self.tab_size)
                return "break"

            case "ISO_Left_Tab":
                # Shift+Tab on Linux/Windows alt keysym
                self._home_toggle = False
                return self._handle_unindent(codeview)

            case "End" | "KP_End":
                self._home_toggle = False
                if shift:
                    # Extend selection to end of line
                    sel = codeview.tag_ranges("sel")
                    anchor = sel[0] if sel else codeview.index("insert")
                    codeview.mark_set("insert", "insert lineend")
                    codeview.tag_remove("sel", "1.0", "end")
                    codeview.tag_add("sel", anchor, "insert")
                else:
                    codeview.mark_set("insert", "insert lineend")
                    codeview.tag_remove("sel", "1.0", "end")
                return "break"

            case "Home" | "KP_Home":
                return self._handle_home(codeview, shift)

            case "Return":
                self._home_toggle = False
                return self._handle_return(codeview)

            case "Next" | "KP_Next" | "Prior" | "KP_Prior":
                self._home_toggle = False
                self._handle_page(event, codeview)

            case "parenleft" | "bracketleft" | "braceleft":
                self._home_toggle = False
                if self.smart_pairs:
                    open_char = self._OPEN_MAP[event.keysym]
                    # Wrap selection if text is selected
                    if codeview.tag_ranges("sel"):
                        return self._wrap_selection(codeview, open_char, self._PAIRS[open_char])
                    codeview.insert("insert", open_char + self._PAIRS[open_char])
                    codeview.mark_set("insert", "insert - 1c")
                    return "break"

            case "apostrophe" | "quotedbl":
                self._home_toggle = False
                if self.smart_pairs:
                    char = self._QUOTE_MAP[event.keysym]
                    # Wrap selection if text is selected
                    if codeview.tag_ranges("sel"):
                        return self._wrap_selection(codeview, char, char)
                    return self._handle_quote(codeview, char)

            case "parenright" | "bracketright" | "braceright":
                self._home_toggle = False
                if self.smart_pairs and codeview.get("insert", "insert+1c") == self._CLOSE_MAP[event.keysym]:
                    codeview.mark_set("insert", "insert+1c")
                    return "break"

            case "BackSpace":
                self._home_toggle = False
                if self.smart_pairs:
                    return self._handle_backspace(codeview)

            case "Insert" | "KP_Insert":
                self._home_toggle = False
                self.overwrite = not self.overwrite
                return "break"

            case _:
                self._home_toggle = False
                # Overwrite mode: replace the char under cursor with the typed char
                if (
                    self.overwrite
                    and event.char
                    and event.char.isprintable()
                    and not (event.state & 0x4)   # not Ctrl
                    and not codeview.tag_ranges("sel")
                ):
                    next_char = codeview.get("insert", "insert+1c")
                    if next_char and next_char != "\n":
                        codeview.delete("insert", "insert+1c")

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_home(self, codeview, shift: bool) -> str:
        line_txt = codeview.get("insert linestart", "insert lineend")
        indent = len(line_txt) - len(line_txt.lstrip())

        if shift:
            # Extend selection toward home
            sel = codeview.tag_ranges("sel")
            anchor = sel[1] if sel else codeview.index("insert")
            if self._home_toggle:
                target = codeview.index("insert linestart")
            else:
                target = codeview.index(f"insert linestart + {indent}c")
            self._home_toggle = not self._home_toggle
            codeview.mark_set("insert", target)
            # Rebuild selection between anchor and new insert
            codeview.tag_remove("sel", "1.0", "end")
            start, end = sorted(
                [codeview.index(anchor), codeview.index(target)],
                key=lambda x: [int(n) for n in x.split(".")]
            )
            codeview.tag_add("sel", start, end)
        else:
            if self._home_toggle:
                codeview.mark_set("insert", "insert linestart")
            else:
                codeview.mark_set("insert", f"insert linestart + {indent}c")
            self._home_toggle = not self._home_toggle
            codeview.tag_remove("sel", "1.0", "end")

        return "break"

    def _handle_return(self, codeview) -> str:
        line_txt = codeview.get("insert linestart", "insert lineend")
        indent = len(line_txt) - len(line_txt.lstrip())
        ends_colon = codeview.get("insert-1c", "insert") == ":"
        extra = "    " if ends_colon else ""
        codeview.insert("insert", f"\n{' ' * indent}{extra}")
        codeview.see("insert")
        return "break"

    def _handle_page(self, event, codeview) -> None:
        current = int(codeview.index("insert").split(".")[0])
        line_h = Font(font=codeview.cget("font")).metrics("linespace")
        page = max(1, codeview.winfo_height() // line_h)
        target = current + page - 1 if event.keysym in ("Next", "KP_Next") else current - page + 1
        target = max(1, target)
        codeview.see(f"{target}.0")
        codeview.mark_set("insert", f"{target}.0")

    def _handle_quote(self, codeview, char: str) -> str:
        if codeview.get("insert", "insert+1c") == char:
            codeview.mark_set("insert", "insert+1c")
            return "break"
        codeview.insert("insert", char + char)
        codeview.mark_set("insert", "insert-1c")
        return "break"

    def _handle_backspace(self, codeview) -> str | None:
        before = codeview.get("insert-1c", "insert")
        after = codeview.get("insert", "insert+1c")
        if before in self._PAIRS and after == self._PAIRS[before]:
            codeview.delete("insert-1c", "insert+1c")
            return "break"

    def _handle_indent_selection(self, codeview) -> str:
        """Indent every selected line by tab_size spaces."""
        sel = codeview.tag_ranges("sel")
        if not sel:
            return "break"
        start_line = int(codeview.index(sel[0]).split(".")[0])
        end_idx = codeview.index(sel[1])
        end_line = int(end_idx.split(".")[0])
        # Don't indent the last line if selection ends at column 0
        if end_idx.endswith(".0"):
            end_line -= 1
        pad = " " * self.tab_size
        for line in range(start_line, end_line + 1):
            codeview.insert(f"{line}.0", pad)
        return "break"

    def _handle_unindent(self, codeview) -> str:
        """Remove up to tab_size leading spaces from every selected line (or current line)."""
        sel = codeview.tag_ranges("sel")
        if sel:
            start_line = int(codeview.index(sel[0]).split(".")[0])
            end_idx = codeview.index(sel[1])
            end_line = int(end_idx.split(".")[0])
            if end_idx.endswith(".0"):
                end_line -= 1
        else:
            start_line = end_line = int(codeview.index("insert").split(".")[0])

        for line in range(start_line, end_line + 1):
            line_text = codeview.get(f"{line}.0", f"{line}.end")
            stripped = line_text.lstrip(" ")
            removed = min(len(line_text) - len(stripped), self.tab_size)
            if removed:
                codeview.delete(f"{line}.0", f"{line}.{removed}")
        return "break"

    def _wrap_selection(self, codeview, open_char: str, close_char: str) -> str:
        """Surround the current selection with open/close characters."""
        sel = codeview.tag_ranges("sel")
        if not sel:
            return "break"
        sel_start = codeview.index(sel[0])
        sel_end   = codeview.index(sel[1])
        selected  = codeview.get(sel_start, sel_end)
        codeview.delete(sel_start, sel_end)
        codeview.insert(sel_start, open_char + selected + close_char)
        # Re-select the inner text
        new_end = codeview.index(f"{sel_start} + {len(selected) + 1}c")
        codeview.tag_remove("sel", "1.0", "end")
        codeview.tag_add("sel", f"{sel_start} + 1c", new_end)
        codeview.mark_set("insert", new_end)
        return "break"
