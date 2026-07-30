"""Conda channel catalog and channel-list validation.

Two concerns, both pure: reading `data/idol_conda_channels.json` (the catalog of
channels IDOL knows about) and checking an *active* list for the mistakes that
are easy to make and hard to diagnose.

Separate from `conda_env.py` on purpose. That module is path probing and the
`channels:` file format; this one is editorial knowledge — which channels fight
each other, which need another above them, and what to say about it. Keeping the
checks here rather than in the editor widget is what lets the panel, the editor
and the tests all ask the same question and get the same answer.

No subprocess, no widget imports — `utils/` rules apply.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from utils.conda_env import mask_channel

_CATALOG_FILE = Path(__file__).parent.parent / "data" / "idol_conda_channels.json"

#: Issue severities, worst first. Callers order by this, and only "error"
#: should ever block an action.
SEVERITIES = ("error", "warning", "info")


@dataclass(frozen=True)
class ChannelIssue:
    """One problem with an active channel list.

    `message` is the full explanation, for a surface with room to explain and
    act (the editor). `short` is a few words for a surface with one line (the
    channel bar), which shows the worst issue and a count of the rest. `fix`
    names a repair the UI can offer as a single action ("reorder"), or is empty
    when the only sensible response is to tell the user.
    """

    kind: str                          # empty|conflict|order|credential|unindexed
    severity: str                      # one of SEVERITIES
    message: str
    short: str = ""
    specs: tuple[str, ...] = ()
    fix: str = ""


def load_catalog() -> list[dict]:
    """Catalog entries, or [] when the file is missing or malformed.

    A broken catalog must never stop someone editing their channels — every
    consumer degrades to "no editorial knowledge", not to "no channel list".
    """
    try:
        data = json.loads(_CATALOG_FILE.read_text(encoding="utf-8"))
        entries = data.get("channels") or []
        return [e for e in entries if isinstance(e, dict) and e.get("spec")]
    except Exception:
        return []


CATALOG: list[dict] = load_catalog()
BY_SPEC: dict[str, dict] = {e["spec"]: e for e in CATALOG}


def catalog_entry(spec: str) -> dict | None:
    """The catalog record for *spec*, or None for a custom channel."""
    return BY_SPEC.get(spec)


def _field(spec: str, key: str) -> list[str]:
    entry = BY_SPEC.get(spec) or {}
    value = entry.get(key)
    return [str(v) for v in value] if isinstance(value, list) else []


def has_credential(spec: str) -> bool:
    """True when *spec* is a URL carrying a username/token."""
    _, sep, rest = spec.partition("://")
    return bool(sep) and "@" in rest


def order_violations(channels: list[str]) -> list[tuple[str, list[str]]]:
    """`(spec, [requirements searched too late])` for each ordering problem.

    Only requirements that are *present* in the list count. A channel needing
    conda-forge above it when conda-forge is absent entirely is a different
    problem (and not one we invent a warning for — plenty of setups are
    deliberate).
    """
    position = {spec: i for i, spec in enumerate(channels)}
    out: list[tuple[str, list[str]]] = []
    for spec in channels:
        late = [req for req in _field(spec, "requires_order_below")
                if req in position and position[req] > position[spec]]
        if late:
            out.append((spec, late))
    return out


def reorder_for_requirements(channels: list[str]) -> list[str]:
    """*channels* with `requires_order_below` satisfied, order else preserved.

    A stable topological pass: repeatedly take the earliest channel whose
    still-unplaced requirements are all satisfied. Anything left when nothing
    is eligible — a dependency cycle, which the catalog has none of but a
    hand-edited one could — is appended as-is rather than looping forever.
    """
    remaining = list(channels)
    present = set(remaining)
    out: list[str] = []
    while remaining:
        for spec in remaining:
            blocking = [req for req in _field(spec, "requires_order_below")
                        if req in present and req != spec and req in remaining]
            if not blocking:
                out.append(spec)
                remaining.remove(spec)
                break
        else:
            out.extend(remaining)
            break
    return out


def validate(channels: list[str], priority: str = "",
             missing: tuple[str, ...] = ()) -> list[ChannelIssue]:
    """Everything worth saying about an active channel list, worst first.

    *priority* is conda's `channel_priority` (see
    `editor.conda_manager.fetch_channel_config`); *missing* is the channels that
    published no searchable index (`CondaSearchIndex.missing_channels`).

    Ordered by severity so a caller can render the list as-is and block on
    `severity == "error"` alone.
    """
    issues: list[ChannelIssue] = []

    if not channels:
        issues.append(ChannelIssue(
            kind="empty", severity="error",
            short="no channels",
            message="At least one channel is required. conda reads an empty "
                    "channel list as “use defaults”, which is the opposite of "
                    "what an empty list looks like it means."))

    # Mixed-stack conflicts. Under strict priority the higher channel wins
    # outright for any package name, which is the configuration conda's own
    # docs recommend for exactly this reason — so the warning is about
    # flexible/disabled, where the solver may take some packages from one
    # channel and some from the other and mix build stacks.
    if priority != "strict":
        active = set(channels)
        seen: set[frozenset[str]] = set()
        for spec in channels:
            for other in _field(spec, "conflicts_with"):
                pair = frozenset((spec, other))
                if other in active and other != spec and pair not in seen:
                    seen.add(pair)
                    issues.append(ChannelIssue(
                        kind="conflict", severity="warning",
                        short=f"{spec} + {other} may mix build stacks",
                        specs=(spec, other),
                        message=f"{spec} and {other} are built against "
                                f"different compiler and BLAS stacks. With "
                                f"{priority or 'flexible'} priority the solver "
                                f"may take some packages from each, which is a "
                                f"common source of import errors. Prefer one, "
                                f"or use strict priority."))

    for spec, late in order_violations(channels):
        issues.append(ChannelIssue(
            kind="order", severity="warning", specs=(spec, *late), fix="reorder",
            short=f"{spec} should come after {', '.join(late)}",
            message=f"{spec} needs {', '.join(late)} searched before it. "
                    f"As ordered, its packages may resolve against the wrong "
                    f"dependencies."))

    for spec in channels:
        if has_credential(spec):
            issues.append(ChannelIssue(
                kind="credential", severity="warning", specs=(spec,),
                short="a channel URL contains a credential",
                message=f"{mask_channel(spec)} contains a credential, and it "
                        f"is written to environment.yml — a file that is "
                        f"normally committed to git. conda's own guidance is "
                        f"to keep tokenized channels in ~/.condarc instead."))

    for spec in missing:
        if spec in channels:
            issues.append(ChannelIssue(
                kind="unindexed", severity="info", specs=(spec,),
                short=f"{spec} has no searchable index",
                message=f"{spec} publishes no searchable package index, so it "
                        f"contributes nothing to search here. Installing from "
                        f"it still works."))

    issues.sort(key=lambda i: SEVERITIES.index(i.severity))
    return issues


def preview_note_channels(packages: list[tuple[str, str, str]],
                          scope: str, primary: str) -> list[str]:
    """Channels in a dry-run result worth flagging, measured against the right one.

    *packages* is `[(name, version, channel)]` from `CondaManager.dry_run`.

    The baseline is the **scope** when one is set, not the primary channel:
    `-c X --override-channels` guarantees every package comes from X, so
    measuring a scoped preview against the primary would flag X on every single
    run — reporting back the thing the user just asked for, dressed up as a
    warning. Unscoped, the primary is the right baseline, because a package
    arriving from further down the list is the interesting case.
    """
    baseline = scope or primary
    return sorted({channel for _, _, channel in packages} - {baseline})


def blocking(issues: list[ChannelIssue]) -> list[ChannelIssue]:
    """The issues that must stop an action rather than merely warn about it."""
    return [i for i in issues if i.severity == "error"]
