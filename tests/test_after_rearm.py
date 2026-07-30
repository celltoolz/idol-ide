"""Self-re-arming after() loops must not re-arm against a widget that is gone.

**Read this before assuming the obvious failure mode.** Destroying a widget does
not leave its poll loop raising: `Misc.destroy()` deletes every Tcl command the
widget registered, and `Misc.after()` registers its callback as exactly such a
command. The pending tick therefore invokes a command that no longer exists,
which dies at the Tcl level and never re-enters Python. Both shapes IDOL has
(loop registered on the destroyed widget; loop that touches the widget before
re-arming) were measured: no report_callback_exception, no unraisable exception.
Constructing PackageManagerPanel and OutputPanel and letting the tk_root fixture
destroy them passes with unraisable warnings promoted to errors, unfixed.

The shape that *does* raise is a loop registered on widget A that re-arms
against a different, destroyed widget B — B's commands are gone while A keeps
the loop alive. No site in IDOL has that shape today, and the structural test at
the bottom is what stops one being added: it is the test with teeth here, red
against every unguarded site. The unit tests above it pin `rearm_after`'s
contract, nothing more.

Two shapes are correct: route the re-arm through `rearm_after`, or store the
after-id and cancel it in `destroy()`. The allowlist covers the second kind.
"""
from __future__ import annotations

import ast
import time
import tkinter as tk
from pathlib import Path

import pytest

from utils.thread_safe_after import make_thread_safe_after, rearm_after

pytestmark = pytest.mark.gui


# ── Helpers ──────────────────────────────────────────────────────────────────

def _drain(root, seconds: float = 0.12) -> None:
    """Pump the event loop so due after() ticks actually fire.

    update() only runs timers already due, so a single call proves nothing
    about a 16 ms loop — this has to spend real wall time.
    """
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        root.update()
        time.sleep(0.005)


# ── rearm_after itself ───────────────────────────────────────────────────────

def test_rearm_after_schedules_on_a_live_widget(tk_root):
    frame = tk.Frame(tk_root)
    fired = []
    assert rearm_after(frame, 10, lambda: fired.append(1)) is not None
    _drain(tk_root, 0.08)
    assert fired == [1]


def test_rearm_after_declines_a_destroyed_widget(tk_root):
    frame = tk.Frame(tk_root)
    frame.destroy()
    fired = []
    assert rearm_after(frame, 10, lambda: fired.append(1)) is None
    _drain(tk_root, 0.08)
    assert fired == []


def test_rearm_after_returns_a_cancellable_id(tk_root):
    """Sites that stop on an explicit action need the id, not just a flag.

    bottom_panel's flash and ai_chat's thinking animation both after_cancel()
    what they stored; a bool return would have kept them on bare widget.after.
    """
    frame = tk.Frame(tk_root)
    fired = []
    job = rearm_after(frame, 10, lambda: fired.append(1))
    frame.after_cancel(job)
    _drain(tk_root, 0.08)
    assert fired == []


def test_pump_delivers_while_its_widget_lives(tk_root):
    """make_thread_safe_after still does its actual job after the guard.

    The guard sits in the pump's hot path, so this pins the delivery contract
    rather than the teardown behaviour — which, per the module docstring, is
    not observable from Python anyway.
    """
    frame = tk.Frame(tk_root)
    frame.pack()
    safe_after = make_thread_safe_after(frame)
    got = []
    safe_after(0, lambda v: got.append(v), 7)
    _drain(tk_root, 0.15)
    assert got == [7]


# ── Structural guard ─────────────────────────────────────────────────────────

# (module path, function name) for loops that re-arm bare on purpose because
# they cancel or guard by another correct means. Anything else must use
# rearm_after. Keep the reason with the entry.
_ALLOWED_BARE_REARM = {
    ("widgets/welcome.py", "_show_next_tip"):
        "stores _tip_after_id and after_cancel()s it in destroy()",
    ("widgets/breadcrumb_bar.py", "_hover_poll"):
        "opens with an explicit `if not popup.winfo_exists(): return`",
    ("widgets/breadcrumb_bar.py", "_marquee_step"):
        "same — guards on preview_text.winfo_exists() before doing anything",
}

_SCANNED = ("app.py", "main.py", "widgets", "utils", "editor", "designer", "menus")


def _self_scheduling_calls(tree: ast.AST):
    """Yield (func_name, call) for every call that re-schedules its own function.

    Walks the AST rather than the source text: a comment about a re-arm
    contains the words of a re-arm, and grepping has bitten this suite before.
    """
    for func in ast.walk(tree):
        if not isinstance(func, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for call in ast.walk(func):
            if not isinstance(call, ast.Call):
                continue
            for arg in call.args:
                names = (arg.id if isinstance(arg, ast.Name) else
                         arg.attr if isinstance(arg, ast.Attribute) else None)
                if names == func.name:
                    yield func.name, call


def _is_bare_after(call: ast.Call) -> bool:
    return isinstance(call.func, ast.Attribute) and call.func.attr == "after"


def _python_files(repo_root: Path):
    for target in _SCANNED:
        path = repo_root / target
        if path.is_file():
            yield path
        else:
            yield from sorted(path.rglob("*.py"))


def test_no_unguarded_self_rearming_after_loops(repo_root):
    offenders = []
    for path in _python_files(repo_root):
        rel = path.relative_to(repo_root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for name, call in _self_scheduling_calls(tree):
            if _is_bare_after(call) and (rel, name) not in _ALLOWED_BARE_REARM:
                offenders.append(f"{rel}:{call.lineno} {name}()")
    assert not offenders, (
        "These loops re-arm against a widget that may already be destroyed. "
        "Route the re-arm through utils.thread_safe_after.rearm_after, or "
        "cancel a stored after-id in destroy() and add it to "
        "_ALLOWED_BARE_REARM with the reason:\n  " + "\n  ".join(offenders)
    )


def test_allowlisted_bare_rearms_still_exist(repo_root):
    """Rot guard — a rename would otherwise make the allowlist match nothing."""
    for (rel, name), reason in _ALLOWED_BARE_REARM.items():
        tree = ast.parse((repo_root / rel).read_text(encoding="utf-8"))
        found = [n for n, call in _self_scheduling_calls(tree)
                 if n == name and _is_bare_after(call)]
        assert found, (
            f"{rel}::{name} is allowlisted ({reason}) but no longer re-arms "
            "bare. Remove the entry."
        )
