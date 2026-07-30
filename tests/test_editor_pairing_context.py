"""Auto-pairing and match-highlighting are code-only, and openers skip over.

Two behaviours were wrong and are pinned here.

**Openers never skipped.** Skip-over was gated on `_CLOSERS`, so typing `(`
immediately before an existing `(` fell through to the auto-pair branch — the
"don't pair mid-word" guard only refuses on an alphanumeric next char, and `(`
is not one. `def __init__|(self):` became `def __init__()(self):` while the
mirror-image `)` case behaved correctly.

**Pairing was context-blind.** A `(` in a comment paired, and the apostrophe in
`# don't` became `# don''t`. Same for match highlighting: a bracket in a comment
outlined against real code elsewhere in the file.
"""
from __future__ import annotations

import pytest

from widgets.canvas_codeview import CanvasCodeView
from widgets.canvas_editor.tokenizer import TokenizerMixin

pytestmark = pytest.mark.gui


@pytest.fixture
def cv(tk_root):
    view = CanvasCodeView(tk_root)
    view.pack(fill="both", expand=True)
    view.set_filepath("scratch.py")
    tk_root.update()
    return view


def type_at(view, text: str, line: int, col: int, keys: str) -> str:
    """Put `text` in the buffer, park the cursor, type `keys`, return the line."""
    view.set_text(text)
    view.set_cursor(line, col)
    for ch in keys:
        view._insert_char_with_pairs(ch)
    return view.lines[line]


# ── The reported case: typing `(` in front of an existing `(` ────────────────

DEF_LINE = "    def __init__(self):"
# col 16 is the `(`; col 21 is the `)`  (the report's 1-based Col17 / Col22)


def test_opener_skips_over_an_existing_opener(cv):
    """The bug: this used to produce `    def __init__()(self):`."""
    assert type_at(cv, DEF_LINE, 0, 16, "(") == DEF_LINE
    assert cv.cur_col == 17, "cursor should have stepped past the `(`"


def test_second_opener_inserts_bare_paren_mid_word(cv):
    """After the skip the cursor sits before `self`, so the mid-word guard
    applies and no closer is volunteered."""
    assert type_at(cv, DEF_LINE, 0, 16, "((") == "    def __init__((self):"


def test_closer_still_skips_then_inserts(cv):
    """The behaviour the report used as the reference — unchanged."""
    assert type_at(cv, DEF_LINE, 0, 21, ")") == DEF_LINE
    assert type_at(cv, DEF_LINE, 0, 21, "))") == "    def __init__(self)):"


@pytest.mark.parametrize("opener", ["(", "[", "{"])
def test_every_opener_skips_not_just_paren(cv, opener):
    """The report only dug into parens; braces and brackets shared the bug."""
    line = f"x = {opener}1{ {'(': ')', '[': ']', '{': '}'}[opener] }"
    assert type_at(cv, line, 0, 4, opener) == line


def test_opener_still_pairs_on_open_ground(cv):
    """Skip-over must not have cost us ordinary auto-pairing."""
    assert type_at(cv, "x = ", 0, 4, "(") == "x = ()"
    assert cv.cur_col == 5, "cursor should sit inside the new pair"


# ── Comments are prose, not code ─────────────────────────────────────────────

def test_apostrophe_in_a_comment_stays_single(cv):
    assert type_at(cv, "# don", 0, 5, "'t") == "# don't"


def test_bracket_in_a_comment_does_not_pair(cv):
    assert type_at(cv, "# see ", 0, 6, "(") == "# see ("


def test_comment_does_not_swallow_a_hand_typed_closer(cv):
    """With pairing suppressed nothing here was auto-inserted, so skip-over
    would eat a real keystroke — the same reasoning as the preference-off path."""
    assert type_at(cv, "# a )", 0, 4, ")") == "# a ))"


def test_code_before_the_hash_still_pairs(cv):
    """The caret slot immediately left of the `#` is still code."""
    assert type_at(cv, "x = 1  # note", 0, 7, "(") == "x = 1  ()# note"


# ── Strings and docstrings ───────────────────────────────────────────────────

def test_apostrophe_inside_a_docstring_stays_single(cv):
    cv.set_text('"""\ndon\n"""')
    cv.set_cursor(1, 3)
    for ch in "'t":
        cv._insert_char_with_pairs(ch)
    assert cv.lines[1] == "don't"


def test_bracket_inside_a_string_does_not_pair(cv):
    assert type_at(cv, 'x = "ab"', 0, 7, "(") == 'x = "ab("'


def test_quote_still_skips_out_of_a_string(cv):
    """Suppression must not trap the caret: the closing quote *was*
    auto-inserted, and typing over it is how you leave the string."""
    assert type_at(cv, 'x = "ab"', 0, 7, '"') == 'x = "ab"'
    assert cv.cur_col == 8


def test_triple_quote_completion_survives(cv):
    """`"` three times still opens a docstring — the middle press relies on
    quote skip-over being alive inside the `""` pair."""
    assert type_at(cv, "", 0, 0, '"""') == '""""""'
    assert cv.cur_col == 3, "cursor should be centred in the triple"


# ── Plain-text files ─────────────────────────────────────────────────────────

def test_saved_plain_text_file_does_not_pair(cv):
    cv.set_filepath("notes.txt")
    assert type_at(cv, "", 0, 0, "(") == "("


def test_unsaved_untitled_buffer_still_pairs(cv):
    """`language` is "text" for an Untitled tab too. Pairing has to survive
    there — that is where a new file spends its first minutes."""
    cv.set_filepath(None)
    assert cv.language == "text"
    assert type_at(cv, "", 0, 0, "(") == "()"


# ── Match highlighting ───────────────────────────────────────────────────────

def test_bracket_in_a_comment_does_not_highlight(cv):
    cv.set_text("foo(1)  # (\n")
    cv.set_cursor(0, 11)          # on the `(` inside the comment
    assert cv._find_bracket_pair() is None


def test_real_bracket_still_highlights(cv):
    cv.set_text("foo(1)")
    cv.set_cursor(0, 3)
    assert cv._find_bracket_pair() == ((0, 3), (0, 5))


def test_apostrophe_in_a_string_is_not_a_delimiter(cv):
    """`'` in `"don't"` has string context on both sides, so it never pairs
    with a later stray quote."""
    cv.set_text("""x = "don't" + 'y'""")
    cv.set_cursor(0, 8)           # on the apostrophe
    assert cv._find_bracket_pair() is None


def test_string_delimiters_still_highlight(cv):
    cv.set_text('x = "hi"')
    cv.set_cursor(0, 4)
    assert cv._find_bracket_pair() == ((0, 4), (0, 7))


def test_triple_quote_pairs_outer_to_outer(cv):
    """Filtering to real delimiters fixed the documented parity limitation:
    the opener used to pair with its own neighbour at col 1."""
    cv.set_text('"""abc"""')
    cv.set_cursor(0, 0)
    assert cv._find_bracket_pair() == ((0, 0), (0, 8))


# ── The caret-context scanner ────────────────────────────────────────────────

class _Fake(TokenizerMixin):
    """TokenizerMixin needs only three host attributes — no Tk required."""

    def __init__(self, lines, ml_state=None):
        self.lines = lines
        self.language = "python"
        self._ml_state = (ml_state if ml_state is not None
                          else self._scan_triple_state(lines))


@pytest.mark.parametrize("line,expected", [
    ('x = "hi"',           ".....SSS."),
    ("x = \"it's\"",       ".....SSSSS."),
    ('x = "a\\"b"',        ".....SSSSS."),   # escaped quote stays inside
    ("x = 1  # hi (",      "........######"),
    ('"""abc"""',          ".SSSSSSSS."),
    ('""',                 ".S."),
])
def test_caret_contexts(line, expected):
    got = _Fake([line])._caret_contexts(0)
    assert len(got) == len(line) + 1, "one entry per caret slot, incl. EOL"
    assert "".join({"code": ".", "string": "S", "comment": "#"}[c]
                   for c in got) == expected


@pytest.mark.parametrize("line,ml,expected", [
    ("text (here", ['"'], "SSSSSSSSSSS"),   # mid-docstring continuation line
    ('""" done',   ['"'], "SSS......"),     # the line that closes it
])
def test_caret_contexts_follows_ml_state(line, ml, expected):
    """Docstring bodies are recognised on every line, not just the opener."""
    got = _Fake([line], ml_state=ml)._caret_contexts(0)
    assert "".join({"code": ".", "string": "S", "comment": "#"}[c]
                   for c in got) == expected
