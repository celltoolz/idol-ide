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
import subprocess
import threading
import time
import urllib.request
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
        """Run *cmd* streaming stdout lines via after_fn; returns the exit code."""
        proc = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, env=env,
        )
        for line in proc.stdout:
            self._after(0, on_line, line)
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

    @property
    def ready(self) -> bool:
        return self._loaded

    def ensure_loaded(self, on_done: Callable[[int], None] | None = None,
                      force: bool = False) -> None:
        """Load (fetching/caching as needed) on a daemon thread.

        Calls on_done(package_count) on the main thread. No-ops if already
        loaded (unless *force*) or currently loading.
        """
        if self._loaded and not force:
            if on_done:
                self._after(0, on_done, len(self._packages))
            return
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
            if on_done:
                self._after(0, on_done, len(packages))

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
