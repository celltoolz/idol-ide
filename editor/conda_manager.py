"""CondaManager — subprocess backend for conda package operations.

Peer backend to PipManager with the same daemon-thread + after_fn
contract, used by the Package Manager panel when the active interpreter
is a conda environment. Install/uninstall route by the search source the
package was picked from (conda packages via conda, explicit PyPI picks
via pip inside the env); uninstall routes by each package's recorded
origin. ``CondaSearchIndex`` provides the conda-side package search:
each configured channel's channeldata.json is cached locally and
fuzzy-searched client-side (mirroring the panel's local PyPI index).

All conda invocations use ``-p <prefix>`` so base, named, and
project-local ``-p`` environments work identically.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from utils import conda_env

# ── Terms of Service helpers ──────────────────────────────────────────────────
# Anaconda's default channels require ToS acceptance (conda-anaconda-tos
# plugin) before conda can download packages. These module-level helpers let
# the wizard and the Package Manager check and accept the ToS with the user's
# consent — acceptance via `conda tos accept` persists in conda itself, so
# the user's own CLI works afterward too.

_TOS_TIMEOUT = 60


def fetch_tos_pending(
    conda_exe: str | None,
    after_fn: Callable,
    on_done: Callable[[dict[str, str]], None],
) -> None:
    """Check which channels still need ToS acceptance, on a daemon thread.

    Calls on_done(pending) on the main thread — {channel_url: tos_text}.
    Empty dict means nothing to accept (all accepted, ToS plugin absent,
    or the check failed — in which case the operation proceeds and any
    real ToS error surfaces from conda itself).
    """
    def _run():
        pending: dict[str, str] = {}
        try:
            result = subprocess.run(
                [conda_exe, "tos", "--json"],
                capture_output=True, text=True, timeout=_TOS_TIMEOUT,
            )
            data = json.loads(result.stdout)
            if isinstance(data, dict):
                for channel, meta in data.items():
                    if not isinstance(meta, dict) or "text" not in meta:
                        continue
                    # "path" points at the local acceptance record once the
                    # ToS has been accepted; "None"/empty means still pending.
                    if meta.get("path") in (None, "", "None"):
                        pending[channel] = meta.get("text", "")
        except Exception:
            pending = {}
        after_fn(0, on_done, pending)

    threading.Thread(target=_run, daemon=True).start()


def accept_tos(
    conda_exe: str | None,
    after_fn: Callable,
    on_done: Callable[[bool, str], None],
) -> None:
    """Run `conda tos accept` (all active channels) on a daemon thread.

    Calls on_done(ok, message) on the main thread.
    """
    def _run():
        try:
            result = subprocess.run(
                [conda_exe, "tos", "accept", "--json"],
                capture_output=True, text=True, timeout=_TOS_TIMEOUT,
            )
            ok = result.returncode == 0
            msg = (result.stderr or result.stdout or "").strip()[-500:]
        except Exception as e:
            ok, msg = False, str(e)
        after_fn(0, on_done, ok, msg)

    threading.Thread(target=_run, daemon=True).start()


# ── Channel configuration (read-only) ─────────────────────────────────────────
# Never parse ~/.condarc to answer "what will conda search?". conda merges a
# system file, the user file, the env's own .condarc, $CONDARC and
# $CONDA_CHANNELS, and **environment variables beat files** — so a panel that
# reports the user's ~/.condarc while an env var overrides it is a panel that
# lies. `conda config --show` gives the effective answer and `--show-sources`
# says which location produced it; both are needed to display it honestly.

_CONFIG_TIMEOUT = 30


@dataclass(frozen=True)
class ChannelConfig:
    """What conda will actually search for one env, and who said so.

    ``ok`` is False when conda could not be queried at all — callers must say
    "could not read" rather than rendering an empty list, which would imply
    conda has no channels configured when it always has at least defaults.
    """

    channels: tuple[str, ...] = ()
    priority: str = ""        # strict | flexible | disabled ("" = not reported)
    source: str = ""          # display label for where `channels` came from
    ok: bool = False


def _source_rank(source: str, prefix: str | None) -> int:
    """Precedence of one `--show-sources` key. Higher wins.

    Ranked rather than trusting the order conda emits, which is not promised.
    Command line beats env vars beats the env's own .condarc beats the user's
    beats anything system-wide.
    """
    if source == "cmd_line":
        return 4
    if source == "envvars":
        return 3
    norm = os.path.normcase(source)
    if prefix and norm.startswith(os.path.normcase(prefix)):
        return 2
    if norm.startswith(os.path.normcase(os.path.expanduser("~"))):
        return 1
    return 0


def _source_label(source: str) -> str:
    """Human label for a `--show-sources` key; home-relative for file paths."""
    if source == "cmd_line":
        return "the command line"
    if source == "envvars":
        return "environment variables"
    home = os.path.expanduser("~")
    if home and os.path.normcase(source).startswith(os.path.normcase(home)):
        return "~" + source[len(home):]
    return source


def channel_config_from(shown: dict, sources: dict,
                        prefix: str | None) -> ChannelConfig:
    """Build a ChannelConfig from parsed `--show` / `--show-sources` output.

    Kept separate from the subprocess call so the merge/precedence logic —
    where the real bugs live — is testable against golden fixtures.
    """
    best_rank, best = -1, ""
    for source, values in (sources or {}).items():
        if not isinstance(values, dict) or "channels" not in values:
            continue
        rank = _source_rank(str(source), prefix)
        if rank > best_rank:
            best_rank, best = rank, str(source)
    raw = (shown or {}).get("channels") or []
    return ChannelConfig(
        channels=tuple(str(c) for c in raw),
        priority=str((shown or {}).get("channel_priority") or ""),
        source=_source_label(best) if best else "",
        ok=True,
    )


def _conda_config_json(conda_exe: str, args: list[str],
                       env: dict[str, str] | None) -> dict:
    result = subprocess.run(
        [conda_exe, "config", *args, "--json"],
        capture_output=True, text=True, timeout=_CONFIG_TIMEOUT, env=env,
    )
    data = json.loads(result.stdout)
    return data if isinstance(data, dict) else {}


def fetch_channel_config(
    conda_exe: str | None,
    prefix: str | None,
    after_fn: Callable,
    on_done: Callable[[ChannelConfig], None],
) -> None:
    """Read *prefix*'s effective channel config on a daemon thread.

    Calls on_done(ChannelConfig) on the main thread; a config with ok=False
    means conda could not be asked (missing exe, timeout, unparseable JSON).

    The subprocess runs with a synthesized activation environment, because
    conda locates the env-level ``$CONDA_PREFIX/.condarc`` from CONDA_PREFIX
    and IDOL never activates — with a bare environment that file is silently
    missed and the reported list is wrong for the selected env.
    """
    def _run():
        try:
            env = conda_env.build_env(prefix) if prefix else None
            shown = _conda_config_json(
                conda_exe, ["--show", "channels", "channel_priority"], env)
            sources = _conda_config_json(conda_exe, ["--show-sources"], env)
            cfg = channel_config_from(shown, sources, prefix)
        except Exception:
            cfg = ChannelConfig()
        after_fn(0, on_done, cfg)

    threading.Thread(target=_run, daemon=True).start()


# ── Output stream cleanup ─────────────────────────────────────────────────────
# Conda writes TTY-oriented output even when piped: spinners drawn with
# backspaces, parallel download bars redrawn via \r + ESC[A cursor-up
# codes, and clear-line runs of spaces. Rendered verbatim in the Output
# panel's Text widget this is unreadable, so _stream routes every line
# through _StreamCleaner first.

_ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[A-Za-z]|\x1b.")

# `pillow-11.1.0        | 902 KB    | ########## | 100% `
_PROGRESS_RE = re.compile(
    r"^(.+?) +\| +[\d.]+ +[KMGTP]?i?B +\|.*\| +(\d+)% *$")

_DOWNLOAD_HEADER = "Downloading and Extracting Packages"


class _StreamCleaner:
    """Per-run line filter that makes conda's TTY output plain-text safe.

    feed(line) returns the cleaned line (newline-terminated) or None when
    the line is redraw noise that should not reach the Output panel:
    backspaces are applied, ANSI escapes stripped, each download bar shown
    only once at 100%, and the cursor-dance blank lines dropped.
    """

    def __init__(self) -> None:
        self._bars_done: set[str] = set()
        self._in_downloads = False
        self._last_blank = False

    def feed(self, line: str) -> str | None:
        line = line.rstrip("\r\n")
        if "\b" in line:
            line = self._apply_backspaces(line)
        line = _ANSI_RE.sub("", line)

        if line.startswith(_DOWNLOAD_HEADER):
            self._in_downloads = True
        elif self._in_downloads and line.strip() and not _PROGRESS_RE.match(line):
            # First real line after the bars ends the download section
            # (drops the dangling clear-line "done" tail on the way out).
            self._in_downloads = False
            if line.strip() == "done":
                return None

        m = _PROGRESS_RE.match(line)
        if m:
            name, pct = m.group(1).strip(), int(m.group(2))
            if pct < 100 or name in self._bars_done:
                return None
            self._bars_done.add(name)
            self._last_blank = False
            return line.rstrip() + "\n"

        if not line.strip():
            # Inside the download section blanks are pure cursor padding;
            # elsewhere collapse runs of blanks to a single one.
            if self._in_downloads or self._last_blank:
                return None
            self._last_blank = True
            return "\n"

        self._last_blank = False
        return line + "\n"

    @staticmethod
    def _apply_backspaces(line: str) -> str:
        out: list[str] = []
        for ch in line:
            if ch == "\b":
                if out:
                    out.pop()
            else:
                out.append(ch)
        return "".join(out)


class CondaManager:
    """Runs conda subprocesses on daemon threads, fires callbacks on the main thread."""

    def __init__(self, after_fn: Callable) -> None:
        self._after = after_fn
        self._python_exe: str = ""
        self._prefix: str | None = None
        self._conda_exe: str | None = None

    def set_python(self, exe: str) -> None:
        """Point the manager at a conda env via its python executable."""
        self._python_exe = exe
        self._prefix = conda_env.conda_prefix_for(exe)
        self._conda_exe = conda_env.find_conda_exe(self._prefix) if self._prefix else None

    @property
    def available(self) -> bool:
        """True when the env prefix and a conda executable were both located."""
        return bool(self._prefix and self._conda_exe)

    @property
    def conda_exe(self) -> str | None:
        """The conda executable serving this env (for the ToS helpers)."""
        return self._conda_exe

    @property
    def prefix(self) -> str | None:
        """The env prefix every conda call is scoped to with `-p`."""
        return self._prefix

    def fetch_installed(
        self,
        on_done: Callable[[dict[str, str], dict[str, str]], None],
    ) -> None:
        """Fetch installed packages via `conda list -p <prefix> --json`.

        Calls on_done(name_to_version, name_to_origin) on the main thread;
        origin is "pypi" for pip-installed packages, "conda" otherwise.
        """
        conda_exe, prefix = self._conda_exe, self._prefix

        def _run():
            installed: dict[str, str] = {}
            origins: dict[str, str] = {}
            try:
                result = subprocess.run(
                    [conda_exe, "list", "-p", prefix, "--json"],
                    capture_output=True, text=True, timeout=30,
                )
                for p in json.loads(result.stdout):
                    installed[p["name"]] = p["version"]
                    origins[p["name"]] = (
                        "pypi" if p.get("channel") == "pypi" else "conda"
                    )
            except Exception:
                installed, origins = {}, {}
            self._after(0, on_done, installed, origins)

        threading.Thread(target=_run, daemon=True).start()

    def install(
        self,
        name: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Install via conda only — *name* must be a conda package name.

        No automatic pip fallback: conda and PyPI use different names for
        the same software (conda's `graphviz` is the C tool, PyPI's is the
        Python bindings), so silently swapping tools installs the wrong
        thing. Explicit PyPI picks go through the panel's pip route instead.
        """
        conda_exe, prefix = self._conda_exe, self._prefix

        def _run():
            try:
                rc = self._stream([conda_exe, "install", "-p", prefix, "-y", name],
                                  on_line, env=None)
                if rc != 0:
                    self._after(0, on_line,
                                f"\nconda could not install '{name}' from your "
                                "configured channels — switch the search source "
                                "to PyPI to install it with pip instead.\n")
            except Exception as e:
                if on_error:
                    self._after(0, on_error, str(e))
                else:
                    self._after(0, on_line, str(e) + "\n")
            self._after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def uninstall(
        self,
        name: str,
        origin: str,
        on_line: Callable[[str], None],
        on_done: Callable[[], None],
        on_error: Callable[[str], None] | None = None,
    ) -> None:
        """Remove via the tool that installed the package (origin routing)."""
        conda_exe, prefix, python = self._conda_exe, self._prefix, self._python_exe
        if origin == "pypi":
            cmd = [python, "-m", "pip", "uninstall", "-y", name]
            env = conda_env.runtime_env(python)
        else:
            cmd = [conda_exe, "remove", "-p", prefix, "-y", name]
            env = None

        def _run():
            try:
                self._stream(cmd, on_line, env=env)
            except Exception as e:
                if on_error:
                    self._after(0, on_error, str(e))
                else:
                    self._after(0, on_line, str(e) + "\n")
            self._after(0, on_done)

        threading.Thread(target=_run, daemon=True).start()

    def _stream(self, cmd: list[str], on_line: Callable[[str], None],
                env: dict[str, str] | None) -> int:
        """Run *cmd* streaming cleaned stdout lines via after_fn; returns the exit code."""
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env,
        )
        cleaner = _StreamCleaner()
        for line in proc.stdout:
            cleaned = cleaner.feed(line)
            if cleaned is not None:
                self._after(0, on_line, cleaned)
        proc.wait()
        return proc.returncode


# ── Conda package search index ────────────────────────────────────────────────

_INDEX_DIR = Path.home() / ".idol" / "conda_index"
_INDEX_MAX_AGE = 7 * 24 * 3600   # refresh cached channeldata weekly


class CondaSearchIndex:
    """Local package search over the user's configured conda channels.

    Downloads each channel's channeldata.json (defaults/main is ~5 MB,
    conda-forge ~22 MB) into ``~/.idol/conda_index/`` and fuzzy-searches it
    in memory — the conda-side mirror of the panel's local PyPI name index.
    Channels come from ``~/.condarc`` (utils.conda_env.configured_channels),
    so search results always match what `conda install` can actually reach.
    The fetch is plain HTTPS — it never goes through conda, so no ToS gate.
    """

    def __init__(self, after_fn: Callable) -> None:
        self._after = after_fn
        self._packages: dict[str, dict] = {}   # name → {summary, version, channel, home, license}
        self._loaded = False
        self._loading = False
        self._pending: list[Callable[[int], None]] = []   # on_done callbacks queued mid-load

    @property
    def ready(self) -> bool:
        return self._loaded

    def ensure_loaded(self, on_done: Callable[[int], None] | None = None,
                      force: bool = False) -> None:
        """Load (fetching/caching as needed) on a daemon thread.

        Calls on_done(package_count) on the main thread. If a load is already
        in flight, on_done is queued and fires when that load completes.
        """
        if self._loaded and not force:
            if on_done:
                self._after(0, on_done, len(self._packages))
            return
        if on_done:
            self._pending.append(on_done)
        if self._loading:
            return
        self._loading = True

        def _run():
            packages: dict[str, dict] = {}
            for chan_name, url in conda_env.channeldata_urls(
                    conda_env.configured_channels()):
                data = self._load_channel(chan_name, url, force)
                # First channel wins on name clashes — mirrors conda's
                # channel priority order.
                for name, meta in data.items():
                    packages.setdefault(name, meta)
            self._packages = packages
            self._loaded = True
            self._loading = False
            pending, self._pending = self._pending, []
            for cb in pending:
                self._after(0, cb, len(packages))

        threading.Thread(target=_run, daemon=True).start()

    def _load_channel(self, chan_name: str, url: str, force: bool) -> dict[str, dict]:
        """Cached channeldata for one channel: {name: meta}."""
        _INDEX_DIR.mkdir(parents=True, exist_ok=True)
        slug = "".join(c if c.isalnum() or c in "-_" else "_" for c in chan_name)
        cache = _INDEX_DIR / f"{slug}.json"
        raw = None
        try:
            fresh = (cache.is_file()
                     and time.time() - cache.stat().st_mtime < _INDEX_MAX_AGE)
            if force or not fresh:
                req = urllib.request.Request(url, headers={"User-Agent": "IDOL-IDE"})
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = resp.read()
                cache.write_bytes(body)
                raw = json.loads(body)
        except Exception:
            raw = None
        if raw is None:
            try:
                raw = json.loads(cache.read_text(encoding="utf-8"))
            except Exception:
                return {}
        out: dict[str, dict] = {}
        for name, meta in (raw.get("packages") or {}).items():
            if not isinstance(meta, dict):
                continue
            out[name] = {
                "summary": (meta.get("summary") or "").strip(),
                "version": str(meta.get("version") or ""),
                "channel": chan_name,
                "home": meta.get("home") or meta.get("doc_url") or "",
                "license": meta.get("license") or "",
            }
        return out

    def search(self, query: str, limit: int = 20) -> list[dict]:
        """Ranked in-memory search: exact > prefix > name-substring > summary hit."""
        q = query.strip().lower()
        if not q or not self._packages:
            return []
        words = q.split()
        exact, prefix, name_hit, summary_hit = [], [], [], []
        for name, meta in self._packages.items():
            lname = name.lower()
            if lname == q:
                exact.append(name)
            elif lname.startswith(q):
                prefix.append(name)
            elif any(w in lname for w in words):
                name_hit.append(name)
            elif meta["summary"] and all(w in meta["summary"].lower() for w in words):
                summary_hit.append(name)
        prefix.sort(key=len)
        name_hit.sort(key=len)
        summary_hit.sort()
        results = []
        for name in exact + prefix + name_hit + summary_hit:
            results.append({"name": name, **self._packages[name]})
            if len(results) >= limit:
                break
        return results
