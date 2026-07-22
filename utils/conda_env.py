"""Conda environment helpers — pure path probing and env-dict construction.

Detects conda environments (a `conda-meta/` directory at the env root),
locates conda base installations and the conda executable, and synthesizes
the environment variables a conda python needs to run *without* shell
activation (on Windows an unactivated conda python cannot resolve the DLLs
in `Library\\bin`, which breaks `import ssl`, numpy, and pip itself).

No subprocess calls — path/file checks and string building only.
"""
from __future__ import annotations

import os
import shutil
import sys
from typing import Callable, Mapping


def _has_conda_meta(prefix: str) -> bool:
    return os.path.isdir(os.path.join(prefix, "conda-meta"))


def conda_prefix_for(exe: str) -> str | None:
    """Return the conda env root for an interpreter path, or None.

    Windows layout puts python.exe at the env root; POSIX puts it under
    bin/ — check both walk levels.
    """
    try:
        for prefix in (os.path.dirname(exe),
                       os.path.dirname(os.path.dirname(exe))):
            if prefix and _has_conda_meta(prefix):
                return prefix
    except (OSError, ValueError):
        pass
    return None


def is_conda_env(exe: str) -> bool:
    """True if the interpreter path belongs to a conda environment."""
    return conda_prefix_for(exe) is not None


def python_exe_for(prefix: str) -> str:
    """Return the python executable path inside a conda env prefix."""
    if sys.platform == "win32":
        return os.path.join(prefix, "python.exe")
    return os.path.join(prefix, "bin", "python")


def env_name_for(prefix: str) -> str:
    """Human name for an env prefix: 'base', the envs/<name>, or dir basename."""
    if os.path.isdir(os.path.join(prefix, "condabin")):
        return "base"
    parent = os.path.dirname(prefix)
    if os.path.basename(parent) == "envs":
        return os.path.basename(prefix)
    return os.path.basename(prefix)


def list_conda_env_prefixes() -> list[str]:
    """Env prefixes from ~/.conda/environments.txt, stale entries dropped."""
    registry = os.path.expanduser(os.path.join("~", ".conda", "environments.txt"))
    prefixes: list[str] = []
    seen: set[str] = set()
    try:
        with open(registry, encoding="utf-8") as f:
            for line in f:
                prefix = line.strip()
                if not prefix or not os.path.isdir(prefix):
                    continue
                if not _has_conda_meta(prefix):
                    continue
                norm = os.path.normcase(prefix)
                if norm not in seen:
                    seen.add(norm)
                    prefixes.append(prefix)
    except OSError:
        pass
    return prefixes


def _well_known_base_dirs() -> list[str]:
    home = os.path.expanduser("~")
    names = ("miniconda3", "anaconda3", "miniforge3", "mambaforge")
    dirs = [os.path.join(home, n) for n in names]
    if sys.platform == "win32":
        program_data = os.environ.get("ProgramData", r"C:\ProgramData")
        dirs += [os.path.join(program_data, n) for n in names]
    else:
        dirs += [os.path.join(home, "opt", n) for n in names]
        dirs += [os.path.join("/opt", n) for n in names]
    return dirs


def find_base_prefixes() -> list[str]:
    """Conda base installations: $CONDA_EXE, `conda` on PATH, well-known dirs."""
    candidates: list[str] = []
    conda_exe = os.environ.get("CONDA_EXE", "")
    if conda_exe:
        candidates.append(os.path.dirname(os.path.dirname(conda_exe)))
    on_path = shutil.which("conda")
    if on_path:
        candidates.append(os.path.dirname(os.path.dirname(on_path)))
    candidates.extend(_well_known_base_dirs())

    bases: list[str] = []
    seen: set[str] = set()
    for prefix in candidates:
        if not prefix or not os.path.isdir(prefix):
            continue
        if not (_has_conda_meta(prefix)
                and os.path.isdir(os.path.join(prefix, "condabin"))):
            continue
        norm = os.path.normcase(prefix)
        if norm not in seen:
            seen.add(norm)
            bases.append(prefix)
    return bases


def find_base_for(env_prefix: str) -> str | None:
    """The base installation an env belongs to (itself, envs/ parent, or any)."""
    if os.path.isdir(os.path.join(env_prefix, "condabin")):
        return env_prefix
    parent = os.path.dirname(env_prefix)
    if os.path.basename(parent) == "envs":
        base = os.path.dirname(parent)
        if _has_conda_meta(base):
            return base
    # Standalone -p env: any installed base can operate on it via -p.
    bases = find_base_prefixes()
    return bases[0] if bases else None


def find_conda_exe(prefix: str | None = None) -> str | None:
    """Locate the conda executable for an env prefix (or any base install)."""
    base = find_base_for(prefix) if prefix else None
    bases = [base] if base else find_base_prefixes()
    for b in bases:
        if sys.platform == "win32":
            candidate = os.path.join(b, "Scripts", "conda.exe")
        else:
            candidate = os.path.join(b, "bin", "conda")
        if os.path.isfile(candidate):
            return candidate
    conda_exe = os.environ.get("CONDA_EXE", "")
    if conda_exe and os.path.isfile(conda_exe):
        return conda_exe
    return shutil.which("conda")


def build_env(exe_or_prefix: str,
              base_env: Mapping[str, str] | None = None) -> dict[str, str]:
    """Synthesized activation environment for a conda env (PATH + CONDA_* vars)."""
    prefix = exe_or_prefix
    if os.path.isfile(exe_or_prefix):
        prefix = conda_prefix_for(exe_or_prefix) or os.path.dirname(exe_or_prefix)
    env = dict(base_env if base_env is not None else os.environ)
    if sys.platform == "win32":
        prepend = [
            prefix,
            os.path.join(prefix, "Library", "mingw-w64", "bin"),
            os.path.join(prefix, "Library", "usr", "bin"),
            os.path.join(prefix, "Library", "bin"),
            os.path.join(prefix, "Scripts"),
            os.path.join(prefix, "bin"),
        ]
    else:
        prepend = [os.path.join(prefix, "bin")]
    existing = env.get("PATH", "")
    env["PATH"] = os.pathsep.join(prepend + ([existing] if existing else []))
    env["CONDA_PREFIX"] = prefix
    env["CONDA_DEFAULT_ENV"] = env_name_for(prefix)
    return env


def runtime_env(exe: str,
                base_env: Mapping[str, str] | None = None) -> dict[str, str] | None:
    """build_env() for conda interpreters, None for everything else."""
    if is_conda_env(exe):
        return build_env(exe, base_env)
    return None


def configured_channels() -> list[str]:
    """Channels from ~/.condarc, in priority order; ["defaults"] when unset.

    Minimal line-based parse of the two forms conda writes (block list and
    inline list) — no YAML dependency. Only the top-level `channels:` key is
    read; anything else in the file is ignored.
    """
    rc = os.path.expanduser(os.path.join("~", ".condarc"))
    channels: list[str] = []
    try:
        with open(rc, encoding="utf-8") as f:
            in_channels = False
            for raw in f:
                line = raw.split("#", 1)[0].rstrip()
                if not line.strip():
                    continue
                indented = raw[0] in (" ", "\t")
                if not indented:
                    key, _, value = line.partition(":")
                    in_channels = key.strip() == "channels"
                    value = value.strip()
                    if in_channels and value.startswith("[") and value.endswith("]"):
                        channels += [v.strip().strip("'\"")
                                     for v in value[1:-1].split(",") if v.strip()]
                        in_channels = False
                    continue
                if in_channels and line.strip().startswith("- "):
                    channels.append(line.strip()[2:].strip().strip("'\""))
    except OSError:
        pass
    channels = [c for c in channels if c and c != "nodefaults"]
    return channels or ["defaults"]


def channeldata_urls(channels: list[str]) -> list[tuple[str, str]]:
    """Map channel names/URLs to (display_name, channeldata.json URL) pairs.

    "defaults" resolves to repo.anaconda.com/pkgs/main (the Python package
    channel; pkgs/r and pkgs/msys2 hold R packages and build tooling, which
    the package-manager search doesn't need).
    """
    out: list[tuple[str, str]] = []
    for ch in channels:
        if ch == "defaults":
            out.append(("defaults",
                        "https://repo.anaconda.com/pkgs/main/channeldata.json"))
        elif ch.startswith(("http://", "https://")):
            name = ch.rstrip("/").rsplit("/", 1)[-1]
            out.append((name, ch.rstrip("/") + "/channeldata.json"))
        else:
            out.append((ch, f"https://conda.anaconda.org/{ch}/channeldata.json"))
    return out


def activation_command(prefix: str, shell_name: str,
                       to_msys: Callable[[str], str] | None = None) -> str | None:
    """Shell command that activates a conda env, per shell dialect.

    Sources the hook script explicitly so it works on installs that were
    never `conda init`-ed. Returns None for shells without a supported
    activation form (cmd/sh/dash — parity with venv auto-activation).
    """
    base = find_base_for(prefix)
    if not base:
        return None
    shell = os.path.basename(shell_name).lower().replace(".exe", "")
    if shell in ("pwsh", "powershell"):
        hook = os.path.join(base, "shell", "condabin", "conda-hook.ps1")
        return f'& "{hook}"; conda activate "{prefix}"'
    if shell in ("bash", "zsh"):
        hook = os.path.join(base, "etc", "profile.d", "conda.sh")
        hook_p, prefix_p = hook, prefix
        if to_msys:
            hook_p, prefix_p = to_msys(hook), to_msys(prefix)
        hook_p = hook_p.replace("\\", "/")
        prefix_p = prefix_p.replace("\\", "/")
        return f'. "{hook_p}" && conda activate "{prefix_p}"'
    return None
