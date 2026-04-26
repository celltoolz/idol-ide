"""Beginner-friendly descriptions for common ruff diagnostic codes.

Each entry is (short_name, description).  Unknown codes return None so callers
can fall back to the raw message text.
"""
from __future__ import annotations

_RULES: dict[str, tuple[str, str]] = {
    # ── Syntax / parse errors ─────────────────────────────────────────────────
    "E999":          ("Syntax error",
                      "Python can't parse this file at all. There's likely a missing "
                      "colon, bracket, or quote somewhere on or before the flagged line."),
    "invalid-syntax":("Syntax error",
                      "Python can't parse this file at all. There's likely a missing "
                      "colon, bracket, or quote somewhere on or before the flagged line."),

    # ── Undefined / unresolved names ──────────────────────────────────────────
    "F821":          ("Undefined name",
                      "A variable, function, or class is used here but was never defined "
                      "or imported. Check for typos or a missing import at the top of the file."),
    "undefined-name":("Undefined name",
                      "A variable, function, or class is used here but was never defined "
                      "or imported. Check for typos or a missing import at the top of the file."),
    "F822":          ("Undefined name in __all__",
                      "A name listed in __all__ doesn't actually exist in this module. "
                      "Either define it or remove it from __all__."),
    "F823":          ("Local variable referenced before assignment",
                      "This variable is used before it's been assigned a value in the "
                      "current function. Make sure it's assigned before the line that uses it."),
    "F811":          ("Redefinition of unused name",
                      "A name was imported or defined, and then immediately redefined "
                      "without ever being used. The first definition is wasted — remove it."),

    # ── Imports ───────────────────────────────────────────────────────────────
    "F401":          ("Unused import",
                      "This module was imported but never used anywhere in the file. "
                      "Remove the import to keep the code clean, or use the name somewhere."),
    "unused-import": ("Unused import",
                      "This module was imported but never used anywhere in the file. "
                      "Remove the import to keep the code clean, or use the name somewhere."),
    "F403":          ("Star import used",
                      "'from module import *' imports everything, making it hard to know "
                      "where names come from. Import only what you need by name instead."),
    "F405":          ("Name may come from star import",
                      "This name might have come from a 'import *' — it's ambiguous. "
                      "Import the module explicitly so the source is clear."),

    # ── Unused variables ──────────────────────────────────────────────────────
    "F841":          ("Unused variable",
                      "A value was assigned to this variable but the variable was never "
                      "read afterward. Either use it or remove the assignment."),
    "unused-variable":("Unused variable",
                      "A value was assigned to this variable but the variable was never "
                      "read afterward. Either use it or remove the assignment."),
    "unused-local":  ("Unused variable",
                      "A value was assigned to this variable but the variable was never "
                      "read afterward. Either use it or remove the assignment."),

    # ── Exception handling ────────────────────────────────────────────────────
    "F841":          ("Unused variable",
                      "A value was assigned to this variable but the variable was never "
                      "read afterward. Either use it or remove the assignment."),
    "E722":          ("Bare except clause",
                      "'except:' with no exception type catches everything, including "
                      "keyboard interrupts. Use 'except Exception:' or a specific type instead."),
    "B001":          ("Do not use bare 'except'",
                      "Catching all exceptions silently can hide real bugs. "
                      "Specify the exception type you expect, e.g. 'except ValueError:'."),
    "B904":          ("Raise without 'from' inside except",
                      "When raising a new exception inside an except block, use "
                      "'raise NewError(...) from e' so the original traceback is preserved."),

    # ── Comparisons ───────────────────────────────────────────────────────────
    "E711":          ("Comparison to None",
                      "Use 'is' or 'is not' when comparing to None, not '==' or '!='. "
                      "Example: 'if x is None:' instead of 'if x == None:'."),
    "E712":          ("Comparison to True/False",
                      "Use 'if x:' or 'if not x:' instead of 'if x == True:' or "
                      "'if x == False:'. It's cleaner and more Pythonic."),
    "E721":          ("Type comparison",
                      "Use 'isinstance(x, int)' instead of 'type(x) == int'. "
                      "isinstance also handles subclasses correctly."),

    # ── Invalid escape sequences ──────────────────────────────────────────────
    "W605":          ("Invalid escape sequence",
                      "A backslash sequence like \\p or \\d isn't recognised as a valid "
                      "escape. Use a raw string r'...' or double the backslash '\\\\'."),

    # ── Mutable defaults / common bugs ───────────────────────────────────────
    "B006":          ("Mutable default argument",
                      "Using a list, dict, or set as a default argument is a classic Python "
                      "trap — it's shared across all calls. Use None and create it inside "
                      "the function instead."),
    "B007":          ("Loop variable not used in loop body",
                      "The loop variable is never used inside the loop. If you just need "
                      "to repeat something N times, name it '_' by convention."),
    "B008":          ("Function call in default argument",
                      "Calling a function as a default argument value is evaluated once at "
                      "definition time, not each call. Move the call inside the function body."),
    "B012":          ("Return/continue inside finally",
                      "A return or continue inside a finally block swallows any exception "
                      "that was being propagated. This is almost always a bug."),

    # ── String / formatting ───────────────────────────────────────────────────
    "F-string":      ("f-string without placeholders",
                      "This f-string has no {} placeholders, so the 'f' prefix does nothing. "
                      "Remove the 'f' to make it a plain string."),
    "F601":          ("'in' with a list literal",
                      "Checking 'x in [a, b, c]' creates a list every time. "
                      "Use a tuple 'x in (a, b, c)' — it's faster and signals the values are fixed."),

    # ── Shadowing / scoping ───────────────────────────────────────────────────
    "A001":          ("Variable shadows a built-in",
                      "A variable here has the same name as a Python built-in like 'list', "
                      "'input', or 'id'. Rename it to avoid hard-to-spot bugs."),
    "A002":          ("Argument shadows a built-in",
                      "A function parameter here has the same name as a Python built-in. "
                      "Rename it to avoid accidentally hiding the built-in inside the function."),

    # ── Return / yield ────────────────────────────────────────────────────────
    "B015":          ("Pointless comparison",
                      "The result of this comparison is computed but never used. "
                      "Did you mean to use it in an if statement or assignment?"),

    # ── Style (common enough to explain) ─────────────────────────────────────
    "E501":          ("Line too long",
                      "This line exceeds the recommended length (usually 79 or 88 characters). "
                      "Break it across multiple lines for readability."),
    "W291":          ("Trailing whitespace",
                      "There are extra spaces at the end of this line. "
                      "Most editors can remove these automatically on save."),
    "W293":          ("Whitespace before comment",
                      "There are extra spaces on a blank line. "
                      "Blank lines should be completely empty."),
    "E302":          ("Expected 2 blank lines",
                      "Top-level functions and classes should be separated by two blank lines. "
                      "Add an extra blank line before this definition."),
    "E303":          ("Too many blank lines",
                      "There are more blank lines here than the style guide recommends (max 2 "
                      "between top-level definitions, max 1 inside a function)."),
    "E401":          ("Multiple imports on one line",
                      "'import os, sys' should be two separate lines: 'import os' and "
                      "'import sys'. One import per line is easier to read and diff."),
}


def lookup(code: str) -> tuple[str, str] | None:
    """Return (short_name, description) for *code*, or None if unknown."""
    return _RULES.get(code)
