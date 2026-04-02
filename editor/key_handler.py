from __future__ import annotations

from tkinter.font import Font


class KeyHandler:
    """Handles smart key press behaviour for a CodeView widget.

    One instance per tab so state (home toggle) is per-editor.
    """

    _PAIRS = {"(": ")", "[": "]", "{": "}", "'": "'", '"': '"'}
    _OPEN_MAP = {"parenleft": "(", "bracketleft": "[", "braceleft": "{"}
    _SKIP_MAP = {"parenright": ")", "bracketright": "]", "braceright": "}"}

    def __init__(self, tab_size: int = 4) -> None:
        self.tab_size = tab_size
        self._home_toggle = False

    def handle(self, event, codeview) -> str | None:
        """Process a key event.  Returns 'break' to suppress default handling."""
        codeview.tag_remove("matching_word", "1.0", "end")
        codeview.tag_remove("Token.highlight", "1.0", "end")

        match event.keysym:
            case "Tab":
                codeview.insert("insert", " " * self.tab_size)
                return "break"

            case "End" | "KP_End":
                codeview.mark_set("insert", "insert lineend")
                self._home_toggle = False
                return "break"

            case "Home" | "KP_Home":
                return self._handle_home(codeview)

            case "Return":
                self._home_toggle = False
                return self._handle_return(codeview)

            case "Next" | "KP_Next" | "Prior" | "KP_Prior":
                self._home_toggle = False
                self._handle_page(event, codeview)

            case "parenleft" | "bracketleft" | "braceleft":
                open_char = self._OPEN_MAP[event.keysym]
                codeview.insert("insert", open_char + self._PAIRS[open_char])
                codeview.mark_set("insert", "insert - 1c")
                self._home_toggle = False
                return "break"

            case "apostrophe":
                self._home_toggle = False
                return self._handle_quote(codeview, "'")

            case "quotedbl":
                self._home_toggle = False
                return self._handle_quote(codeview, '"')

            case "parenright" | "bracketright" | "braceright":
                self._home_toggle = False
                if codeview.get("insert", "insert+1c") == self._SKIP_MAP[event.keysym]:
                    codeview.mark_set("insert", "insert+1c")
                    return "break"

            case "BackSpace":
                self._home_toggle = False
                return self._handle_backspace(codeview)

            case _:
                self._home_toggle = False

    # ── Handlers ─────────────────────────────────────────────────────────────

    def _handle_home(self, codeview) -> str:
        line_txt = codeview.get("insert linestart", "insert lineend")
        indent = len(line_txt) - len(line_txt.lstrip())
        if self._home_toggle:
            codeview.mark_set("insert", "insert linestart")
        else:
            codeview.mark_set("insert", f"insert linestart + {indent}c")
        self._home_toggle = not self._home_toggle
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
