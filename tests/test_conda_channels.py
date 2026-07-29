"""Conda channel configuration — parsing, precedence, and secret hygiene.

Phase 1 of the Conda Channels work (see TODO.md). Everything here is
headless: the `conda config` merge logic is exercised against golden JSON
fixtures rather than a real conda, which is both where the real bugs live and
the only way this can run on CI where conda is absent.
"""
from __future__ import annotations

import json
import os
import threading

import pytest

from editor import conda_manager
from utils import conda_channels, conda_env


# ── channels: block parsing ───────────────────────────────────────────────────

def test_parses_block_list_in_order():
    text = (
        "channels:\n"
        "  - conda-forge\n"
        "  - pytorch\n"
        "  - defaults\n"
        "dependencies:\n"
        "  - python=3.12\n"
    )
    assert conda_env.parse_channels_block(text) == [
        "conda-forge", "pytorch", "defaults"]


def test_parses_inline_list():
    assert conda_env.parse_channels_block(
        "channels: [conda-forge, 'pytorch', \"defaults\"]\n"
    ) == ["conda-forge", "pytorch", "defaults"]


def test_ignores_other_top_level_keys():
    """A `- x` under dependencies must not be read as a channel."""
    text = (
        "name: myproject\n"
        "channels:\n"
        "  - conda-forge\n"
        "dependencies:\n"
        "  - numpy\n"
        "  - pandas\n"
    )
    assert conda_env.parse_channels_block(text) == ["conda-forge"]


def test_strips_comments_and_nodefaults():
    text = (
        "channels:\n"
        "  - conda-forge   # the good one\n"
        "  - nodefaults\n"
        "# - pytorch\n"
    )
    assert conda_env.parse_channels_block(text) == ["conda-forge"]


def test_empty_text_yields_no_channels():
    assert conda_env.parse_channels_block("") == []


# ── project_channels (the store) ──────────────────────────────────────────────

def _write_env_yml(root, body: str) -> None:
    (root / "environment.yml").write_text(body, encoding="utf-8")


def test_project_channels_reads_environment_yml(tmp_path):
    _write_env_yml(tmp_path, "channels:\n  - conda-forge\n  - pytorch\n")
    assert conda_env.project_channels(str(tmp_path)) == ["conda-forge", "pytorch"]


def test_project_channels_none_without_file(tmp_path):
    """No environment.yml is 'unstated', which is not the same as empty."""
    assert conda_env.project_channels(str(tmp_path)) is None


def test_project_channels_none_when_file_has_no_channels_key(tmp_path):
    _write_env_yml(tmp_path, "name: p\ndependencies:\n  - python\n")
    assert conda_env.project_channels(str(tmp_path)) is None


def test_project_channels_none_for_nodefaults_only(tmp_path):
    """`nodefaults` alone leaves nothing searchable — fall back, don't show []."""
    _write_env_yml(tmp_path, "channels:\n  - nodefaults\n")
    assert conda_env.project_channels(str(tmp_path)) is None


def test_project_channels_none_for_empty_root():
    assert conda_env.project_channels("") is None


# ── secret hygiene ────────────────────────────────────────────────────────────

def test_mask_channel_hides_credentials():
    masked = conda_env.mask_channel("https://alex:s3cr3t@example.com/private")
    assert "s3cr3t" not in masked
    assert "alex" not in masked
    assert masked.endswith("example.com/private")


def test_mask_channel_leaves_ordinary_specs_alone():
    for spec in ("conda-forge", "pytorch/label/nightly", "defaults",
                 "https://conda.anaconda.org/conda-forge",
                 "file:///srv/local-channel"):
        assert conda_env.mask_channel(spec) == spec


def test_masked_token_never_reaches_a_rendered_channel_line():
    """The bar formats through mask_channel — assert the whole line is clean."""
    channels = ["conda-forge", "https://u:tok@host/c"]
    line = "   ·   ".join(f"{i} {conda_env.mask_channel(c)}"
                          for i, c in enumerate(channels, 1))
    assert "tok" not in line


# ── conda config --show / --show-sources precedence ───────────────────────────

_SHOWN = {"channels": ["conda-forge", "defaults"], "channel_priority": "flexible"}


def test_channel_config_reads_shown_values():
    cfg = conda_manager.channel_config_from(_SHOWN, {}, None)
    assert cfg.ok is True
    assert cfg.channels == ("conda-forge", "defaults")
    assert cfg.priority == "flexible"


def test_env_vars_outrank_files():
    """conda lets environment variables beat every file; the label must too."""
    home = os.path.expanduser("~")
    sources = {
        os.path.join(home, ".condarc"): {"channels": ["defaults"]},
        "envvars": {"channels": ["conda-forge"]},
    }
    cfg = conda_manager.channel_config_from(_SHOWN, sources, None)
    assert cfg.source == "environment variables"


def test_env_level_condarc_outranks_user_condarc(tmp_path):
    prefix = str(tmp_path / "envs" / "myenv")
    sources = {
        os.path.join(os.path.expanduser("~"), ".condarc"): {"channels": ["defaults"]},
        os.path.join(prefix, ".condarc"): {"channels": ["conda-forge"]},
    }
    cfg = conda_manager.channel_config_from(_SHOWN, sources, prefix)
    assert cfg.source.endswith(".condarc")
    assert "envs" in cfg.source


def test_user_condarc_label_is_home_relative():
    path = os.path.join(os.path.expanduser("~"), ".condarc")
    cfg = conda_manager.channel_config_from(_SHOWN, {path: {"channels": ["x"]}}, None)
    assert cfg.source.startswith("~")


def test_sources_without_a_channels_key_are_ignored():
    sources = {"envvars": {"channel_priority": "strict"},
               "/etc/conda/condarc": {"channels": ["defaults"]}}
    cfg = conda_manager.channel_config_from(_SHOWN, sources, None)
    assert cfg.source == "/etc/conda/condarc"


def test_no_source_reports_no_source():
    cfg = conda_manager.channel_config_from(_SHOWN, {}, None)
    assert cfg.source == ""


def test_malformed_show_output_does_not_raise():
    cfg = conda_manager.channel_config_from({}, {"envvars": "not-a-dict"}, None)
    assert cfg.channels == ()
    assert cfg.priority == ""
    assert cfg.ok is True          # conda answered; it just said nothing useful


def test_default_config_is_not_ok():
    """An unqueried config must be distinguishable from an empty answer."""
    assert conda_manager.ChannelConfig().ok is False


# ── the subprocess seam ───────────────────────────────────────────────────────

class _FakeCompleted:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout
        self.returncode = 0


def test_fetch_channel_config_wires_both_calls(monkeypatch):
    """--show and --show-sources are both issued, with --json, and merged."""
    calls: list[list[str]] = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        if "--show-sources" in cmd:
            return _FakeCompleted(json.dumps({"envvars": {"channels": ["x"]}}))
        return _FakeCompleted(json.dumps(_SHOWN))

    monkeypatch.setattr(conda_manager.subprocess, "run", fake_run)

    done = threading.Event()
    got: list[conda_manager.ChannelConfig] = []

    def after_fn(_delay, fn, *args):
        fn(*args)
        done.set()

    conda_manager.fetch_channel_config("conda", None, after_fn, got.append)
    assert done.wait(timeout=10), "callback never fired"

    assert len(calls) == 2
    assert all("--json" in c for c in calls)
    assert got[0].channels == ("conda-forge", "defaults")
    assert got[0].source == "environment variables"


def test_fetch_channel_config_survives_a_broken_conda(monkeypatch):
    def fake_run(cmd, **kwargs):
        raise OSError("conda not found")

    monkeypatch.setattr(conda_manager.subprocess, "run", fake_run)

    done = threading.Event()
    got: list[conda_manager.ChannelConfig] = []

    def after_fn(_delay, fn, *args):
        fn(*args)
        done.set()

    conda_manager.fetch_channel_config("conda", None, after_fn, got.append)
    assert done.wait(timeout=10), "callback never fired"
    assert got[0].ok is False


# ── writing the store ─────────────────────────────────────────────────────────

def test_render_emits_nodefaults_when_defaults_absent():
    """Removing defaults IS the "don't use Anaconda defaults" switch."""
    assert conda_env.render_channels_block(["conda-forge"]) == [
        "channels:\n", "  - conda-forge\n", "  - nodefaults\n"]


def test_render_omits_nodefaults_when_defaults_present():
    assert conda_env.render_channels_block(["conda-forge", "defaults"]) == [
        "channels:\n", "  - conda-forge\n", "  - defaults\n"]


def test_write_replaces_the_block_and_keeps_everything_else(tmp_path):
    _write_env_yml(tmp_path, (
        "name: myproject\n"
        "channels:\n"
        "  - defaults\n"
        "dependencies:\n"
        "  - python=3.12\n"
        "  - numpy\n"
    ))
    assert conda_env.write_project_channels(str(tmp_path), ["conda-forge"])
    text = (tmp_path / "environment.yml").read_text(encoding="utf-8")
    assert "- defaults\n" not in text
    assert "  - conda-forge\n" in text
    assert "  - nodefaults\n" in text
    # Nothing else may be disturbed — this file is the user's and conda's.
    assert "name: myproject\n" in text
    assert "  - python=3.12\n" in text
    assert "  - numpy\n" in text


def test_write_replaces_an_inline_block(tmp_path):
    _write_env_yml(tmp_path, "channels: [defaults, pytorch]\ndependencies:\n  - numpy\n")
    assert conda_env.write_project_channels(str(tmp_path), ["conda-forge"])
    text = (tmp_path / "environment.yml").read_text(encoding="utf-8")
    assert "[defaults" not in text
    assert conda_env.project_channels(str(tmp_path)) == ["conda-forge"]
    assert "  - numpy\n" in text


def test_write_adds_a_block_when_the_file_has_none(tmp_path):
    _write_env_yml(tmp_path, "name: p\ndependencies:\n  - numpy\n")
    assert conda_env.write_project_channels(str(tmp_path), ["conda-forge"])
    assert conda_env.project_channels(str(tmp_path)) == ["conda-forge"]
    assert "  - numpy\n" in (tmp_path / "environment.yml").read_text(encoding="utf-8")


def test_write_preserves_comments_outside_the_block(tmp_path):
    _write_env_yml(tmp_path, (
        "# hand-written, do not clobber\n"
        "name: p\n"
        "channels:\n"
        "  - defaults\n"
        "dependencies:\n"
    ))
    conda_env.write_project_channels(str(tmp_path), ["conda-forge"])
    text = (tmp_path / "environment.yml").read_text(encoding="utf-8")
    assert "# hand-written, do not clobber\n" in text


def test_write_round_trips(tmp_path):
    _write_env_yml(tmp_path, "name: p\nchannels:\n  - defaults\ndependencies:\n")
    order = ["conda-forge", "pytorch", "nvidia"]
    conda_env.write_project_channels(str(tmp_path), order)
    assert conda_env.project_channels(str(tmp_path)) == order


def test_write_refuses_an_empty_list(tmp_path):
    """conda reads absent-or-empty channels: as [defaults] — the opposite."""
    _write_env_yml(tmp_path, "channels:\n  - conda-forge\ndependencies:\n")
    assert conda_env.write_project_channels(str(tmp_path), []) is False
    assert conda_env.project_channels(str(tmp_path)) == ["conda-forge"]


def test_write_refuses_to_create_the_file(tmp_path):
    """Creating environment.yml is a decision to ask about, not a side effect."""
    assert conda_env.write_project_channels(str(tmp_path), ["conda-forge"]) is False
    assert not (tmp_path / "environment.yml").exists()


def test_create_writes_a_wizard_shaped_file(tmp_path):
    assert conda_env.create_project_environment_yml(
        str(tmp_path), "myproj", ["conda-forge"])
    text = (tmp_path / "environment.yml").read_text(encoding="utf-8")
    assert text.startswith("name: myproj\n")
    assert "  - conda-forge\n" in text
    assert "  - nodefaults\n" in text
    assert text.rstrip().endswith("dependencies:")


def test_create_will_not_overwrite(tmp_path):
    _write_env_yml(tmp_path, "name: original\nchannels:\n  - defaults\n")
    assert conda_env.create_project_environment_yml(
        str(tmp_path), "other", ["conda-forge"]) is False
    assert "original" in (tmp_path / "environment.yml").read_text(encoding="utf-8")


# ── channel → URL resolution ──────────────────────────────────────────────────

def test_channeldata_url_for_a_local_channel():
    """Regression: file:// used to fall through to the bare-name branch."""
    [(name, url)] = conda_env.channeldata_urls(["file:///srv/local-channel"])
    assert url == "file:///srv/local-channel/channeldata.json"
    assert name == "local-channel"
    assert "conda.anaconda.org" not in url


def test_channeldata_url_for_owner_label():
    [(_, url)] = conda_env.channeldata_urls(["pytorch/label/nightly"])
    assert url == "https://conda.anaconda.org/pytorch/label/nightly/channeldata.json"


def test_channel_base_url_expands_defaults_to_the_pkgs_parent():
    """All three defaults expansions must match by prefix."""
    base = conda_env.channel_base_url("defaults")
    for sub in ("main", "r", "msys2"):
        assert f"https://repo.anaconda.com/pkgs/{sub}".startswith(base)


def test_channel_covers_url_matches_defaults_expansions():
    for url in ("https://repo.anaconda.com/pkgs/main",
                "https://repo.anaconda.com/pkgs/r",
                "https://repo.anaconda.com/pkgs/msys2/"):
        assert conda_env.channel_covers_url("defaults", url)


def test_channel_covers_url_is_not_a_substring_match():
    assert not conda_env.channel_covers_url(
        "conda-forge", "https://conda.anaconda.org/conda-forge-evil")
    assert conda_env.channel_covers_url(
        "conda-forge", "https://conda.anaconda.org/conda-forge")


def test_channel_covers_url_rejects_a_different_channel():
    assert not conda_env.channel_covers_url(
        "conda-forge", "https://repo.anaconda.com/pkgs/main")


# ── ToS gate scoping ──────────────────────────────────────────────────────────

_TOS_JSON = json.dumps({
    "https://repo.anaconda.com/pkgs/main": {"text": "Anaconda ToS", "path": "None"},
    "https://repo.anaconda.com/pkgs/r": {"text": "Anaconda ToS", "path": "None"},
    "https://conda.anaconda.org/conda-forge": {"text": "cf", "path": "/accepted"},
})


def _run_tos(monkeypatch, channels):
    def fake_run(cmd, **kwargs):
        return _FakeCompleted(_TOS_JSON)

    monkeypatch.setattr(conda_manager.subprocess, "run", fake_run)
    done = threading.Event()
    got: list[dict] = []

    def after_fn(_delay, fn, *args):
        fn(*args)
        done.set()

    conda_manager.fetch_tos_pending("conda", after_fn, got.append,
                                    channels=channels)
    assert done.wait(timeout=10), "callback never fired"
    return got[0]


def test_tos_gate_is_silent_for_a_conda_forge_only_project(monkeypatch):
    """The bug the channel work would otherwise introduce.

    ~/.condarc still lists defaults, so `conda tos` reports it pending — but
    the install runs with --override-channels and will never touch it.
    """
    assert _run_tos(monkeypatch, ["conda-forge"]) == {}


def test_tos_gate_still_fires_when_defaults_is_active(monkeypatch):
    pending = _run_tos(monkeypatch, ["conda-forge", "defaults"])
    assert set(pending) == {"https://repo.anaconda.com/pkgs/main",
                            "https://repo.anaconda.com/pkgs/r"}


def test_tos_gate_unfiltered_without_a_channel_list(monkeypatch):
    """None means 'don't filter' — the right default for callers with no list."""
    assert len(_run_tos(monkeypatch, None)) == 2


def test_tos_gate_skips_already_accepted_channels(monkeypatch):
    assert "https://conda.anaconda.org/conda-forge" not in _run_tos(
        monkeypatch, ["conda-forge", "defaults"])


# ── -c threading ──────────────────────────────────────────────────────────────

def test_channel_args_preserve_priority_order():
    """`-c A -c B` ranks A above B — the §2a direction property."""
    m = conda_manager.CondaManager(after_fn=lambda *a: None)
    m.set_channels(["conda-forge", "pytorch", "nvidia"], override=True)
    args = m._channel_args()
    assert args == ["-c", "conda-forge", "-c", "pytorch", "-c", "nvidia",
                    "--override-channels"]
    # Round-trip: parsing the flags back out must give the original order.
    assert [a for a, flag in zip(args[1::2], args[0::2]) if flag == "-c"] == [
        "conda-forge", "pytorch", "nvidia"]


def test_no_channels_means_no_flags():
    """Empty list = defer to conda's own config, not an empty search space."""
    m = conda_manager.CondaManager(after_fn=lambda *a: None)
    m.set_channels([], override=True)
    assert m._channel_args() == []


def test_override_is_dropped_without_channels():
    """--override-channels with no -c would leave conda nowhere to look."""
    m = conda_manager.CondaManager(after_fn=lambda *a: None)
    m.set_channels(None, override=True)
    assert "--override-channels" not in m._channel_args()


def test_set_channels_drops_empty_entries():
    m = conda_manager.CondaManager(after_fn=lambda *a: None)
    m.set_channels(["conda-forge", "", None], override=False)
    assert m.channels == ["conda-forge"]


def test_install_command_carries_the_channel_flags(monkeypatch):
    """The flags have to reach the actual argv, not just _channel_args."""
    m = conda_manager.CondaManager(after_fn=lambda _d, fn, *a: fn(*a))
    m._conda_exe, m._prefix = "conda", "/envs/p"
    m.set_channels(["conda-forge"], override=True)
    seen: list[list[str]] = []
    monkeypatch.setattr(m, "_stream",
                        lambda cmd, on_line, env: (seen.append(cmd), 0)[1])
    done = threading.Event()
    m.install("numpy", on_line=lambda _s: None, on_done=done.set)
    assert done.wait(timeout=10), "install never completed"
    cmd = seen[0]
    assert cmd[:5] == ["conda", "install", "-p", "/envs/p", "-y"]
    assert cmd[5:] == ["-c", "conda-forge", "--override-channels", "numpy"]


def test_project_file_wins_over_what_conda_reports(tmp_path):
    _write_env_yml(tmp_path, "channels:\n  - conda-forge\ndependencies:\n")
    channels, stated = conda_env.resolve_channels(
        str(tmp_path), ["defaults", "pytorch"])
    assert channels == ["conda-forge"]
    assert stated is True


def test_conda_config_stands_when_the_project_states_nothing(tmp_path):
    channels, stated = conda_env.resolve_channels(
        str(tmp_path), ["conda-forge", "defaults"])
    assert channels == ["conda-forge", "defaults"]
    assert stated is False


def test_unstated_channels_must_not_be_pinned(tmp_path):
    """The flag that decides whether installs get `-c … --override-channels`.

    A project without environment.yml must behave exactly as it did before this
    work: the list is conda's own config read back, so pinning it would echo
    conda's configuration at conda — no benefit, and a way for an explicit
    `-c defaults` to diverge from however that config expands `defaults`. This
    is the difference between the phase's blast radius matching its promise and
    it silently changing every conda project.
    """
    _, stated = conda_env.resolve_channels(str(tmp_path), ["defaults"])
    assert stated is False
    m = conda_manager.CondaManager(after_fn=lambda *a: None)
    m.set_channels(["defaults"] if stated else [], override=stated)
    assert m._channel_args() == []


def test_resolve_drops_empty_reported_entries(tmp_path):
    channels, _ = conda_env.resolve_channels(str(tmp_path), ["conda-forge", ""])
    assert channels == ["conda-forge"]


def test_edit_action_offers_nothing_without_a_folder():
    """No folder means no environment.yml to write, so promise nothing."""
    assert conda_env.channel_edit_action("", False) == ""
    assert conda_env.channel_edit_action("", True) == ""


def test_edit_action_distinguishes_create_from_edit(tmp_path):
    assert conda_env.channel_edit_action(str(tmp_path), True) == "edit"
    assert conda_env.channel_edit_action(str(tmp_path), False) == "create"


# ── search index keyed by channel set ─────────────────────────────────────────

def test_index_is_not_loaded_for_a_different_channel_set():
    """The project-switch staleness bug: a bare `loaded` flag would miss it."""
    idx = conda_manager.CondaSearchIndex(after_fn=lambda _d, fn, *a: fn(*a))
    idx._loaded_for = ("conda-forge",)
    assert idx.is_loaded_for(["conda-forge"])
    assert not idx.is_loaded_for(["conda-forge", "pytorch"])
    assert not idx.is_loaded_for(["pytorch", "conda-forge"])   # order matters
    assert not idx.is_loaded_for([])


def test_index_starts_not_ready():
    idx = conda_manager.CondaSearchIndex(after_fn=lambda *a: None)
    assert idx.ready is False
    assert idx.missing_channels == ()


def test_index_records_channels_that_publish_no_channeldata(monkeypatch):
    """A 404 channeldata.json must be reported, not silently absorbed."""
    idx = conda_manager.CondaSearchIndex(after_fn=lambda _d, fn, *a: fn(*a))
    monkeypatch.setattr(
        idx, "_load_channel",
        lambda name, url, force: ({"numpy": {"summary": "", "version": "1",
                                             "channel": name, "home": "",
                                             "license": ""}}
                                  if name == "conda-forge" else {}))
    done = threading.Event()
    idx.ensure_loaded(["conda-forge", "obscure"], on_done=lambda _n: done.set())
    assert done.wait(timeout=10), "load never completed"
    assert idx.missing_channels == ("obscure",)
    assert idx.is_loaded_for(["conda-forge", "obscure"])
    assert idx.search("numpy")[0]["name"] == "numpy"


def test_index_first_channel_wins_on_name_clash(monkeypatch):
    """Mirrors conda's channel priority: channel 1 owns the name."""
    idx = conda_manager.CondaSearchIndex(after_fn=lambda _d, fn, *a: fn(*a))

    def fake_load(name, url, force):
        return {"numpy": {"summary": "", "version": "1", "channel": name,
                          "home": "", "license": ""}}

    monkeypatch.setattr(idx, "_load_channel", fake_load)
    done = threading.Event()
    idx.ensure_loaded(["conda-forge", "defaults"], on_done=lambda _n: done.set())
    assert done.wait(timeout=10)
    assert idx.search("numpy")[0]["channel"] == "conda-forge"


# ── guardrails: validate() ────────────────────────────────────────────────────

def _kinds(channels, priority="", missing=()):
    return [i.kind for i in conda_channels.validate(channels, priority, missing)]


def test_a_healthy_list_has_nothing_to_say():
    assert conda_channels.validate(["conda-forge"], "flexible") == []


def test_empty_list_is_an_error_not_a_warning():
    """The only issue that may block Save."""
    [issue] = conda_channels.validate([])
    assert issue.kind == "empty"
    assert issue.severity == "error"
    assert conda_channels.blocking([issue]) == [issue]


def test_mixed_stacks_warn_under_flexible_priority():
    assert "conflict" in _kinds(["conda-forge", "defaults"], "flexible")


def test_mixed_stacks_are_silent_under_strict_priority():
    """Strict priority is the documented fix, so warning about it would be wrong."""
    assert "conflict" not in _kinds(["conda-forge", "defaults"], "strict")


def test_unknown_priority_is_treated_as_flexible():
    """conda's default is flexible, so an unread config must not go quiet."""
    assert "conflict" in _kinds(["conda-forge", "defaults"], "")


def test_a_conflicting_pair_is_reported_once():
    """conflicts_with is declared on both entries; one warning, not two."""
    conflicts = [i for i in conda_channels.validate(["conda-forge", "defaults"])
                 if i.kind == "conflict"]
    assert len(conflicts) == 1


def test_order_violation_is_detected_and_offers_a_fix():
    [issue] = [i for i in conda_channels.validate(["bioconda", "conda-forge"])
               if i.kind == "order"]
    assert issue.fix == "reorder"
    assert set(issue.specs) == {"bioconda", "conda-forge"}


def test_correct_order_is_not_flagged():
    assert "order" not in _kinds(["conda-forge", "bioconda"])


def test_a_missing_requirement_is_not_invented_as_an_issue():
    """bioconda without conda-forge at all is a choice, not an ordering bug."""
    assert "order" not in _kinds(["bioconda"])


def test_credential_in_a_channel_url_warns_and_is_masked_in_the_message():
    [issue] = [i for i in conda_channels.validate(["https://u:s3cr3t@host/c"])
               if i.kind == "credential"]
    assert "s3cr3t" not in issue.message
    assert "s3cr3t" not in issue.short
    assert "environment.yml" in issue.message   # says *why* it matters


def test_unindexed_channel_is_info_and_never_blocks():
    issues = conda_channels.validate(["conda-forge", "obscure"],
                                     missing=("obscure",))
    [issue] = [i for i in issues if i.kind == "unindexed"]
    assert issue.severity == "info"
    assert conda_channels.blocking(issues) == []


def test_missing_channel_not_in_the_list_is_ignored():
    assert "unindexed" not in _kinds(["conda-forge"], missing=("bioconda",))


def test_issues_are_ordered_worst_first():
    issues = conda_channels.validate(
        ["bioconda", "conda-forge", "defaults", "obscure"],
        "flexible", missing=("obscure",))
    ranks = [conda_channels.SEVERITIES.index(i.severity) for i in issues]
    assert ranks == sorted(ranks)


def test_every_issue_carries_a_short_label():
    """The channel bar has one line and renders `short` — none may be blank."""
    issues = conda_channels.validate(
        ["bioconda", "conda-forge", "defaults", "obscure",
         "https://u:t@h/c"], "flexible", missing=("obscure",))
    assert {i.kind for i in issues} == {"conflict", "order", "credential",
                                        "unindexed"}
    assert all(i.short for i in issues)
    assert all(i.message for i in issues)


# ── guardrails: the one-click order fix ───────────────────────────────────────

def test_fix_order_moves_the_requirement_above():
    assert conda_channels.reorder_for_requirements(
        ["bioconda", "conda-forge"]) == ["conda-forge", "bioconda"]


def test_fix_order_leaves_a_correct_list_alone():
    for order in (["conda-forge", "bioconda"], ["conda-forge"], []):
        assert conda_channels.reorder_for_requirements(order) == order


def test_fix_order_preserves_unrelated_positions():
    """Only what has to move, moves — order is the user's configuration."""
    assert conda_channels.reorder_for_requirements(
        ["bioconda", "defaults", "conda-forge", "pytorch"]) == [
            "defaults", "conda-forge", "bioconda", "pytorch"]


def test_fix_order_resolves_every_violation_and_is_idempotent():
    fixed = conda_channels.reorder_for_requirements(
        ["bioconda", "rapidsai", "conda-forge"])
    assert not [i for i in conda_channels.validate(fixed) if i.kind == "order"]
    assert conda_channels.reorder_for_requirements(fixed) == fixed


def test_fix_order_terminates_on_a_dependency_cycle(monkeypatch):
    """The catalog has no cycles; a hand-edited one must not hang the UI."""
    monkeypatch.setitem(conda_channels.BY_SPEC, "a",
                        {"spec": "a", "requires_order_below": ["b"]})
    monkeypatch.setitem(conda_channels.BY_SPEC, "b",
                        {"spec": "b", "requires_order_below": ["a"]})
    assert sorted(conda_channels.reorder_for_requirements(["a", "b"])) == ["a", "b"]


def test_fix_order_ignores_a_self_reference(monkeypatch):
    monkeypatch.setitem(conda_channels.BY_SPEC, "solo",
                        {"spec": "solo", "requires_order_below": ["solo"]})
    assert conda_channels.reorder_for_requirements(["solo"]) == ["solo"]


def test_custom_channels_have_no_catalog_opinions():
    assert conda_channels.catalog_entry("my-private-channel") is None
    assert conda_channels.validate(["my-private-channel"]) == []


# ── the shipped catalog ───────────────────────────────────────────────────────

_REQUIRED_KEYS = {"id", "display_name", "spec", "tier", "description",
                  "companions", "conflicts_with", "requires_order_below",
                  "notes", "url"}
_TIERS = {"mainstream", "domain", "vendor"}


@pytest.fixture
def catalog(repo_root):
    path = repo_root / "data" / "idol_conda_channels.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_catalog_entries_are_complete(catalog):
    assert catalog["schema_version"] == 1
    assert catalog["channels"], "catalog is empty"
    for entry in catalog["channels"]:
        missing = _REQUIRED_KEYS - set(entry)
        assert not missing, f"{entry.get('id')} is missing {missing}"
        assert entry["tier"] in _TIERS, f"{entry['id']} has tier {entry['tier']!r}"


def test_catalog_ids_are_unique(catalog):
    ids = [e["id"] for e in catalog["channels"]]
    assert len(ids) == len(set(ids))


def test_catalog_cross_references_resolve(catalog):
    """companions / conflicts_with / requires_order_below must name real entries."""
    ids = {e["id"] for e in catalog["channels"]}
    for entry in catalog["channels"]:
        for field in ("companions", "conflicts_with", "requires_order_below"):
            unknown = set(entry[field]) - ids
            assert not unknown, f"{entry['id']}.{field} names unknown {unknown}"


def test_catalog_ships_the_recommended_default(catalog):
    ids = {e["id"] for e in catalog["channels"]}
    assert "conda-forge" in ids
    assert "defaults" in ids
