"""The split editor closes only when the user closes it.

An emptied split pane stays open: closing its last tab, dragging that tab back
to main, or switching to Designer are all tab/mode operations, not a request to
dismantle a layout the user chose. The old auto-close also had a way to lose a
split outright — if the last split tab was closed while Designer mode had the
pane hidden, it was destroyed and there was nothing left to restore on the way
back to the editor.

Enforced structurally. The split's behaviour needs a live `IDOL` — a `tk.Tk`
subclass owning notebooks, paned windows and the designer surface — so there is
no practical way to assert "the pane is still there" in a unit test. What *can*
be pinned is which methods are allowed to take the pane down at all, which is
the actual policy and the thing a future change would quietly break.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

TEARDOWN = {"_close_split", "_hide_split", "_dispose_split_pane"}

# Every method permitted to hide or destroy the split pane, and why.
ALLOWED = {
    # The user's own toggle — View > Split Editor / the keybinding.
    "view_split_editor",
    # The × on the split pane's header.  Also the target of that binding.
    "_close_split",
    # Disposes any existing pane before building a fresh one; without it a
    # second split could be added alongside the first.
    "_build_right_pane",
    # Project lifecycle, not a split operation. The split is project-scoped —
    # `utils/session.py` saves and restores `split_tabs` per project — so one
    # project's split files must not carry into the next.
    "_teardown_project",
}


@pytest.fixture(scope="module")
def idol_methods(repo_root: Path) -> dict[str, ast.FunctionDef]:
    tree = ast.parse((repo_root / "app.py").read_text(encoding="utf-8"))
    cls = next(n for n in tree.body
               if isinstance(n, ast.ClassDef) and n.name == "IDOL")
    return {n.name: n for n in cls.body if isinstance(n, ast.FunctionDef)}


def _teardown_calls(fn: ast.FunctionDef) -> set[str]:
    found = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in TEARDOWN):
            found.add(node.func.attr)
        # `lambda _: self._close_split()` inside a bind() is still a call, but
        # a bare `self._close_split` passed as a callback would not be — catch
        # the reference too.
        elif isinstance(node, ast.Attribute) and node.attr in TEARDOWN:
            found.add(node.attr)
    return found


def test_only_the_allowlist_can_take_the_split_down(idol_methods):
    offenders = {
        name: sorted(calls)
        for name, fn in idol_methods.items()
        if name not in ALLOWED and (calls := _teardown_calls(fn))
    }
    assert not offenders, (
        f"These IDOL methods hide or destroy the split pane but are not in the "
        f"allowlist: {offenders}. The split closes only when the user closes "
        f"it — if this is a deliberate new policy, add it to ALLOWED with the "
        f"reason."
    )


@pytest.mark.parametrize("method", sorted(ALLOWED))
def test_allowlisted_methods_still_exist(idol_methods, method):
    """Guards the allowlist against rot — a renamed method would otherwise
    make the test above pass by simply never matching anything."""
    assert method in idol_methods


def test_the_user_toggle_can_still_hide_and_show(idol_methods):
    calls = _teardown_calls(idol_methods["view_split_editor"])
    assert "_hide_split" in calls
    assert "_show_split" in ast.dump(idol_methods["view_split_editor"])


@pytest.mark.parametrize("method", [
    "_close_tab",               # closing the split's last tab
    "_move_to_main",            # dragging the split's last tab back to main
    "_enter_designer_mode",     # Editor -> Designer
    "_enter_editor_mode",       # Designer -> Editor
    "_show_split",              # re-showing an emptied pane
])
def test_former_auto_close_paths_are_clean(idol_methods, method):
    """Each of these used to hide or destroy the pane on its own."""
    assert method in idol_methods, f"{method} was renamed — update this test"
    assert not _teardown_calls(idol_methods[method])


def test_the_designer_restore_state_is_gone(repo_root: Path):
    """`_split_was_shown` only existed to put back what Designer mode hid.

    Nothing hides it now, so a lingering reference means a restore path came
    back — and a half-restored one is how the pane went missing before.
    """
    assert "_split_was_shown" not in (repo_root / "app.py").read_text(
        encoding="utf-8")
