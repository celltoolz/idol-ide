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
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
        return result.stdout if result.returncode == 0 else ""
    except Exception:
        return ""


def _run_git_output(args: list[str], cwd: str, timeout: int = 30) -> str:
    """Run git and return combined stdout+stderr regardless of exit code."""
    try:
        result = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
        return (result.stdout + result.stderr).strip() or "(no output)"
    except Exception as exc:
        return str(exc)


def _parse_staged_unstaged(output: str, root: str) -> tuple[dict[str, str], dict[str, str]]:
    """Parse `git status --porcelain` → (staged_map, unstaged_map).

    Each map is {normcase_abs_path: status_char} where status_char ∈ M A D U.
    """
    staged: dict[str, str] = {}
    unstaged: dict[str, str] = {}
    for line in output.splitlines():
        if len(line) < 4:
            continue
        x, y = line[0], line[1]
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ")[1]
        # Keep real path as key so it can be passed directly to git commands.
        # Callers that need case-insensitive comparison should use os.path.normcase().
        abs_path = os.path.join(root, path.replace("/", os.sep))
        # Index (staged)
        if x not in (" ", "?"):
            staged[abs_path] = "D" if x == "D" else ("A" if x in ("A", "C") else "M")
        # Working tree (unstaged / untracked)
        if x == "?" and y == "?":
            unstaged[abs_path] = "U"
        elif y not in (" ", "?"):
            unstaged[abs_path] = "D" if y == "D" else "M"
    return staged, unstaged


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
        abs_path = os.path.join(root, path.replace("/", os.sep))
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


class CommitInfo:
    """Immutable record for a single git log entry."""
    __slots__ = ("hash", "short", "subject", "author", "rel_time", "abs_time", "refs")

    def __init__(self, hash: str, short: str, subject: str, author: str,
                 rel_time: str, abs_time: str, refs: list) -> None:
        self.hash     = hash
        self.short    = short
        self.subject  = subject
        self.author   = author
        self.rel_time = rel_time
        self.abs_time = abs_time
        self.refs     = refs   # list[str]


def _parse_log(output: str) -> "list[CommitInfo]":
    commits = []
    for line in output.splitlines():
        if not line.strip():
            continue
        parts = line.split("\x00")
        if len(parts) < 7:
            continue
        hash_, short, subject, author, rel_time, abs_time, refs_raw = parts[:7]
        refs = [r.strip() for r in refs_raw.split(",") if r.strip()]
        commits.append(CommitInfo(hash_, short, subject, author,
                                  rel_time, abs_time, refs))
    return commits


class GitManager:
    """Thin async wrapper around git CLI for a single repository root."""

    def __init__(self, root: str, after_fn: Callable) -> None:
        self._root  = root
        self._after = after_fn

    # ── Async ─────────────────────────────────────────────────────────────────

    def is_repo(self, callback: Callable[[bool], None]) -> None:
        def _run() -> None:
            result = bool(_run_git(["rev-parse", "--is-inside-work-tree"], self._root).strip())
            self._after(0, lambda r=result: callback(r))
        threading.Thread(target=_run, daemon=True).start()

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

    def get_full_status(self,
                        callback: Callable[[dict[str, str], dict[str, str]], None]) -> None:
        """Fetch both staged and unstaged status maps in one call."""
        def _run() -> None:
            out = _run_git(["status", "--porcelain", "-u"], self._root)
            staged, unstaged = _parse_staged_unstaged(out, self._root)
            self._after(0, lambda s=staged, u=unstaged: callback(s, u))
        threading.Thread(target=_run, daemon=True).start()

    def get_file_diff(self, path: str, callback: Callable[[str], None]) -> None:
        """Return unified diff for *path* (working tree first, then staged)."""
        def _run() -> None:
            out = _run_git(["diff", "--", path], self._root)
            if not out:
                out = _run_git(["diff", "--cached", "--", path], self._root)
            self._after(0, lambda o=out: callback(o))
        threading.Thread(target=_run, daemon=True).start()

    def stage(self, path: str, callback: Callable[[], None] | None = None) -> None:
        def _run() -> None:
            _run_git(["add", "--", path], self._root)
            if callback:
                self._after(0, callback)
        threading.Thread(target=_run, daemon=True).start()

    def unstage(self, path: str, callback: Callable[[], None] | None = None) -> None:
        def _run() -> None:
            # If HEAD doesn't exist (no commits yet), use rm --cached instead
            has_head = _run_git(["rev-parse", "--verify", "HEAD"], self._root) != ""
            if has_head:
                out = _run_git_output(["restore", "--staged", "--", path], self._root)
            else:
                out = _run_git_output(["rm", "--cached", "--", path], self._root)
            if callback:
                self._after(0, callback)
        threading.Thread(target=_run, daemon=True).start()

    def discard(self, path: str, callback: Callable[[], None] | None = None) -> None:
        def _run() -> None:
            # Use a relative path — git restore can silently fail with absolute
            # paths on some platforms (macOS in particular).
            try:
                rel = os.path.relpath(path, self._root)
            except ValueError:
                rel = path
            _run_git(["restore", "--", rel], self._root)
            if callback:
                self._after(0, callback)
        threading.Thread(target=_run, daemon=True).start()

    def commit(self, message: str, callback: Callable[[str], None] | None = None) -> None:
        def _run() -> None:
            out = _run_git_output(["commit", "-m", message], self._root)
            if callback:
                self._after(0, lambda o=out: callback(o))
        threading.Thread(target=_run, daemon=True).start()

    def push(self, callback: Callable[[str], None] | None = None) -> None:
        def _run() -> None:
            out = _run_git_output(["push"], self._root)
            if callback:
                self._after(0, lambda o=out: callback(o))
        threading.Thread(target=_run, daemon=True).start()

    def pull(self, callback: Callable[[str], None] | None = None) -> None:
        def _run() -> None:
            out = _run_git_output(["pull"], self._root)
            if callback:
                self._after(0, lambda o=out: callback(o))
        threading.Thread(target=_run, daemon=True).start()

    # ── History ───────────────────────────────────────────────────────────────

    def get_log(self, n: int,
                callback: "Callable[[list[CommitInfo]], None]") -> None:
        """Fetch the last *n* commits and return a list of CommitInfo via callback."""
        def _run() -> None:
            fmt = "%H%x00%h%x00%s%x00%an%x00%ar%x00%ai%x00%D"
            out = _run_git(["log", f"--format={fmt}", f"-n{n}"], self._root)
            commits = _parse_log(out)
            self._after(0, lambda c=commits: callback(c))
        threading.Thread(target=_run, daemon=True).start()

    def get_commit_files(self, commit_hash: str,
                         callback: "Callable[[list[tuple[str,str]]], None]") -> None:
        """Return [(status, filepath)] for all files changed in *commit_hash*."""
        def _run() -> None:
            out = _run_git(
                ["show", "--name-status", "--format=", commit_hash], self._root
            )
            files: list[tuple[str, str]] = []
            for line in out.splitlines():
                line = line.strip()
                if not line:
                    continue
                parts = line.split("\t", 1)
                if len(parts) == 2:
                    raw_status, path = parts
                    s = raw_status[0]
                    mapped = {"M": "M", "A": "A", "D": "D",
                              "R": "R", "C": "A"}.get(s, "M")
                    files.append((mapped, path))
            self._after(0, lambda f=files: callback(f))
        threading.Thread(target=_run, daemon=True).start()

    def get_commit_diff(self, commit_hash: str, filepath: str,
                        callback: "Callable[[str], None]") -> None:
        """Return unified diff for *filepath* as it was changed in *commit_hash*."""
        def _run() -> None:
            out = _run_git(
                ["show", commit_hash, "--", filepath], self._root
            )
            self._after(0, lambda o=out: callback(o))
        threading.Thread(target=_run, daemon=True).start()
