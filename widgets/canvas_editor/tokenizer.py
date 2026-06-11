"""Tokenizer for CanvasCodeView — regex-rule syntax highlighting.

Pure, stateless logic extracted from canvas_codeview.py (P3 decomposition).
`TokenizerMixin` is inherited by `CanvasCodeView`; it owns the regex rule
table (`PYTHON_RULES`), the comment/string scanners, and the per-line
triple-quote state scan.

It reaches into the host only for two attributes, both owned and
maintained by `CanvasCodeView`:
  * `self.language`  (str)            — selects the diff vs. python path
  * `self._ml_state` (list[str|None]) — per-line triple-quote continuation

The tokenizer emits category NAMES (e.g. "keyword_flow", "string"); the
renderer resolves them to colors against the active theme, so a theme swap
never rebuilds rules.
"""
from __future__ import annotations

import re


# Tokenizer rules. Each rule is (regex, category_name). The category is
# resolved against the active theme's `tokens` map at render time, so a
# `set_theme()` recolors without rebuilding rules.
#
# Order matters: earlier rules claim text, later rules only see segments
# still at default fg. Comments and strings MUST come before keywords so
# words like `if` inside a string don't get keyword-colored.
PYTHON_RULES = [
    # Strings BEFORE comments — `#.*` would otherwise eat hex
    # color strings (`bg="#FFFFFF"`) by matching from the `#`
    # to end of line, swallowing the rest of the statement.
    # Triple-quoted patterns come first so ''' isn't parsed as
    # '' (empty) + ' (open). The (?:'''|$) close allows the
    # pattern to match unclosed triples on the opening line of
    # a multiline string (continuation lines are handled by
    # _tokenize via _ml_state / _tokenize_in_triple).
    (re.compile(
        r"'''[^'\\]*(?:(?:\\.|'{1,2}(?!'))[^'\\]*)*(?:'''|$)"
        r'|"""[^"\\]*(?:(?:\\.|"{1,2}(?!"))[^"\\]*)*(?:"""|$)'
        r"|'(?:\\.|[^'\\])*'"
        r'|"(?:\\.|[^"\\])*"'
    ), "string"),
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
    # Constructor / class call-sites — any PascalCase (or ALL_CAPS)
    # identifier followed by `(`. Placed before the dot-method rule
    # so `tk.Label(...)` colors `Label` as a type, not a method.
    (re.compile(r"\b[A-Z]\w*(?=\s*\()"),                  "type"),
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


class TokenizerMixin:
    """Regex-rule tokenizer mixed into CanvasCodeView.

    Stateless apart from two host attributes it reads: `self.language`
    (diff vs. python path) and `self._ml_state` (per-line triple-quote
    continuation state). Both are owned by CanvasCodeView."""

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

    _DIFF_META_PREFIXES = ("+++", "---", "diff ", "index ", "new file",
                           "deleted file", "Binary", "similarity",
                           "rename from", "rename to", "old mode", "new mode")

    def _tokenize_diff(self, line: str):
        """Whole-line tokenizer for unified diff / patch files."""
        if line.startswith(self._DIFF_META_PREFIXES):
            return [(line, "diff_meta")]
        if line.startswith("+"):
            return [(line, "diff_add")]
        if line.startswith("-"):
            return [(line, "diff_remove")]
        if line.startswith("@@"):
            m = re.match(r"(@@ [^@]+ @@)(.*)", line)
            if m:
                segs = [(m.group(1), "diff_hunk")]
                if m.group(2):
                    segs.append((m.group(2), "diff_meta"))
                return segs
            return [(line, "diff_hunk")]
        return [(line, None)]

    @staticmethod
    def _scan_triple_state(lines: list[str]) -> list[str | None]:
        """Return a per-line list of triple-quoted string states.

        Each element is None (line starts outside any triple-quoted string)
        or the quote character ("'" or '"') if the line starts inside one.
        Used by _tokenize to colour continuation lines as strings."""
        state: list[str | None] = []
        current: str | None = None  # quote char while inside a triple string
        for line in lines:
            state.append(current)
            i = 0
            n = len(line)
            while i < n:
                ch = line[i]
                if current:
                    if ch == "\\":
                        i += 2
                        continue
                    if line[i:i + 3] == current * 3:
                        current = None
                        i += 3
                        continue
                else:
                    if ch == "#":
                        break  # rest is a comment
                    if ch in ('"', "'") and line[i:i + 3] in ("'''", '"""'):
                        current = ch
                        i += 3
                        continue
                    if ch in ('"', "'"):
                        q = ch
                        i += 1
                        while i < n:
                            c2 = line[i]
                            if c2 == "\\":
                                i += 2
                                continue
                            if c2 == q:
                                i += 1
                                break
                            i += 1
                        continue
                i += 1
        return state

    def _tokenize_in_triple(self, line: str, quote_char: str):
        """Tokenize a line that starts inside a triple-quoted string.

        Colours everything up to (and including) the closing triple-quote
        as "string", then hands the remainder back to _tokenize."""
        triple = quote_char * 3
        end_idx = line.find(triple)
        if end_idx == -1:
            return [(line, "string")] if line else []
        segs: list = [(line[:end_idx + 3], "string")]
        rest = line[end_idx + 3:]
        if rest:
            segs.extend(self._tokenize(rest))
        return [s for s in segs if s[0]]

    def _tokenize(self, line: str, line_idx: int | None = None):
        """Return a list of (text, category_or_None) segments.

        Category None means default fg. Categories are resolved to actual
        colors at render time so the active theme picks the palette.

        Comments are handled up-front via _comment_start so that string
        tokens inside a comment (e.g. `# print("x")`) are not coloured
        as strings — the whole tail is treated as a comment. Non-comment
        rules run only on the code portion that precedes the `#`."""
        if self.language == "diff":
            return self._tokenize_diff(line)
        # Continuation lines of a multiline triple-quoted string.
        if line_idx is not None and line_idx < len(self._ml_state):
            triple_q = self._ml_state[line_idx]
            if triple_q is not None:
                return self._tokenize_in_triple(line, triple_q)
        comment_at = self._comment_start(line)
        code_part   = line[:comment_at] if comment_at is not None else line
        segments: list = [(code_part, None)] if code_part else []
        for pat, category in PYTHON_RULES:
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
