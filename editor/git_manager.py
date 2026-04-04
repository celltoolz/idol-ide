"""GitManager — lightweight git integration via subprocess.

All public methods that query git run on a daemon thread and fire
their callbacks back on the main thread via *after_fn* (tkinter's `after`).
"""
from __future__ import annotations

import os
import re
import subprocess
import threading
from typing import Callable

# Matches unified-diff hunk headers: @@ -old[,cnt] +new[,cnt] @@
_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@")

# Status colours (used by explorer / tabs)
STATUS_COLORS = {
    "M": "#e2c08d",   # yellow  — modified
    "A": "#73c991",   # green   — added / staged
    "U": "#cccccc",   # grey    — untracked
    "D": "#f14c4c",   # red     — deleted
}

# Gutter strip colours
GUTTER_COLORS = {
    "added":    "#4ec994",
    "modified": "#c5a028",
    "deleted":  "#f14c4c",
}


def _run_git(args: list[str], cwd: str) -> str:
    """Run git and return stdout, or '' on any failure."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _parse_status(output: str, root: str) -> dict[str, str]:
    """Parse `git status --porcelain` → {normcase_abs_path: status_char}."""
    result: dict[str, str] = {}
    for line in output.splitlines():
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        path = line[3:].strip()
        if " -> " in path:           # renamed — use destination
            path = path.split(" -> ")[1]
        if x == "?" and y == "?":
            status = "U"
        elif x == "D" or y == "D":
            status = "D"
        elif x in ("A", "C"):
            status = "A"
        else:
            status = "M"
        abs_path = os.path.normcase(
            os.path.join(root, path.replace("/", os.sep))
        )
        result[abs_path] = status
    return result


def _parse_hunks(diff_text: str) -> list[tuple[int, int, str]]:
    """Parse unified diff → [(start_line, line_count, kind)].

    kind is one of: 'added', 'modified', 'deleted'
    """
    hunks: list[tuple[int, int, str]] = []
    for line in diff_text.splitlines():
        m = _HUNK_RE.match(line)
        if not m:
            continue
        old_count = int(m.group(2)) if m.group(2) is not None else 1
        new_start = int(m.group(3))
        new_count = int(m.group(4)) if m.group(4) is not None else 1
        if old_count == 0 and new_count > 0:
            hunks.append((new_start, new_count, "added"))
        elif new_count == 0:
            # Deletion: mark one row at the insertion point
            hunks.append((max(1, new_start), 1, "deleted"))
        else:
            hunks.append((new_start, new_count, "modified"))
    return hunks


class GitManager:
    """Thin async wrapper around git CLI for a single repository root."""

    def __init__(self, root: str, after_fn: Callable) -> None:
        self._root  = root
        self._after = after_fn

    # ── Sync ──────────────────────────────────────────────────────────────────

    def is_repo(self) -> bool:
        return bool(_run_git(["rev-parse", "--is-inside-work-tree"], self._root).strip())

    # ── Async ─────────────────────────────────────────────────────────────────

    def get_branch(self, callback: Callable[[str], None]) -> None:
        def _run() -> None:
            branch = _run_git(["branch", "--show-current"], self._root).strip()
            if not branch:
                branch = _run_git(["rev-parse", "--short", "HEAD"], self._root).strip() or "HEAD"
            self._after(0, lambda b=branch: callback(b))
        threading.Thread(target=_run, daemon=True).start()

    def get_status(self, callback: Callable[[dict[str, str]], None]) -> None:
        def _run() -> None:
            out = _run_git(["status", "--porcelain", "-u"], self._root)
            self._after(0, lambda m=_parse_status(out, self._root): callback(m))
        threading.Thread(target=_run, daemon=True).start()

    def get_diff_hunks(self, path: str,
                       callback: Callable[[list[tuple[int, int, str]]], None]) -> None:
        def _run() -> None:
            out   = _run_git(["diff", "--unified=0", "--", path], self._root)
            hunks = _parse_hunks(out)
            self._after(0, lambda h=hunks: callback(h))
        threading.Thread(target=_run, daemon=True).start()
