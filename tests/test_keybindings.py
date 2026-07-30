"""No two application shortcuts may claim the same chord.

Tk stores `<Control-G>` and `<Control-Shift-G>` as two separate binding-table
entries, but they describe the *same* chord — a capital letter detail already
implies Shift. Press it and Tk fires only the more specific entry, silently.
Two shipped shortcuts were lost that way:

- **Ctrl+Shift+G** — Source Control (`<Control-G>`) lost to the designer's
  Generate Code (`<Control-Shift-G>`), while both menus advertised the key.
- **F10** — Step Over lost to Zen Mode, which was simply bound later.

Neither raises, neither logs, and both menus keep showing the accelerator, so
the only symptom is a shortcut that does nothing. That is worth a build failure
rather than a bug report, hence this test.

Structural: `_bind_shortcuts` runs against a live `tk.Tk`, so the bindings are
read out of the AST instead. Only `self.bind(...)` counts — a binding on some
other widget is a different binding table and cannot collide.
"""
from __future__ import annotations

import ast
import collections
from pathlib import Path

import pytest


def _chord(seq: str) -> tuple[frozenset[str], str]:
    """Normalize a Tk sequence so equivalent spellings compare equal.

    `<Control-G>` and `<Control-Shift-G>` both become `({Control, Shift}, 'g')`.
    """
    parts = seq.strip("<>").split("-")
    key, mods = parts[-1], set(parts[:-1])
    if len(key) == 1 and key.isalpha() and key.isupper():
        mods.add("Shift")
        key = key.lower()
    mods.discard("KeyPress")
    return frozenset(mods), key


@pytest.fixture(scope="module")
def app_shortcuts(repo_root: Path) -> dict:
    """{chord: [(lineno, sequence)]} for every `self.bind` in `_bind_shortcuts`."""
    tree = ast.parse((repo_root / "app.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "IDOL")
    fn = next(n for n in cls.body
              if isinstance(n, ast.FunctionDef) and n.name == "_bind_shortcuts")

    found = collections.defaultdict(list)
    for node in ast.walk(fn):
        if not (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "bind"
                and isinstance(node.func.value, ast.Name)
                and node.func.value.id == "self"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            continue
        seq = node.args[0].value
        if seq.startswith("<"):
            found[_chord(seq)].append((node.lineno, seq))
    return dict(found)


def test_bind_shortcuts_was_found(app_shortcuts):
    """A rename that empties the fixture would make every test below vacuous."""
    assert len(app_shortcuts) > 20


def test_no_chord_is_claimed_twice(app_shortcuts):
    clashes = {c: v for c, v in app_shortcuts.items() if len(v) > 1}
    assert not clashes, "\n".join(
        "chord %s+%s claimed at %s — Tk fires only one of them" % (
            "+".join(sorted(chord[0])) or "(no modifier)",
            chord[1],
            ", ".join(f"app.py:{ln} {seq}" for ln, seq in sites),
        )
        for chord, sites in clashes.items()
    )


def test_shifted_letters_spell_shift_out(app_shortcuts):
    """`<Control-S>` works, but `<Control-Shift-S>` is the spelling that makes a
    collision visible on the page — which is what nobody saw for Ctrl+Shift+G."""
    implicit = [
        (ln, seq) for sites in app_shortcuts.values() for ln, seq in sites
        if (lambda p: len(p[-1]) == 1 and p[-1].isupper() and "Shift" not in p)(
            seq.strip("<>").split("-"))
    ]
    assert not implicit, (
        "write Shift out explicitly: "
        + ", ".join(f"app.py:{ln} {seq}" for ln, seq in implicit)
    )


# ── the two chords that were lost, pinned individually ───────────────────────

def test_ctrl_shift_g_is_source_control(app_shortcuts):
    sites = app_shortcuts.get((frozenset({"Control", "Shift"}), "g"))
    assert sites and len(sites) == 1
    src = (Path(__file__).resolve().parent.parent / "app.py").read_text(encoding="utf-8")
    assert "view_source_control" in src.splitlines()[sites[0][0] - 1]


def test_f10_is_a_single_dispatcher(app_shortcuts):
    """Step Over and Zen Mode share F10, so exactly one binding routes both."""
    sites = app_shortcuts.get((frozenset(), "F10"))
    assert sites and len(sites) == 1, "F10 must be bound once, not once per feature"

    import app as app_mod
    import inspect

    body = inspect.getsource(app_mod.IDOL._f10)
    assert "_debug_step_over" in body and "view_zen_mode" in body
    assert "active" in body, "must branch on a live debug session, not merely _debugger"


def test_menu_accelerators_match_the_bindings(repo_root: Path):
    """The accelerator text is the only thing most users ever read. Both menus
    said Ctrl+Shift+G while only one of them got the key."""
    menubar = (repo_root / "menus" / "menubar.py").read_text(encoding="utf-8")
    assert menubar.count('accelerator="Ctrl+Shift+G"') == 1, (
        "Ctrl+Shift+G is Source Control's; nothing else may advertise it"
    )
    assert 'accelerator="Ctrl+Shift+B"' in menubar, "Generate Code's key"
