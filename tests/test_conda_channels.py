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
from utils import conda_env


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
