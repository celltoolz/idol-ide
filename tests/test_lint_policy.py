"""Which ruff rules the Problems panel applies to a given file.

A project that configures ruff gets its own rules; anything else gets IDOL's
explicit baseline rather than whatever ruff's defaults happen to be that
release. Ruff 0.16 widening its defaults from 59 rules to 413 is what made the
same file lint clean on one machine and dirty on another.
"""
from __future__ import annotations

import pytest

from editor import pyflakes_linter as pl


@pytest.fixture
def mkfile(tmp_path):
    def _mk(rel, text=""):
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
        return p
    return _mk


# ── config discovery ─────────────────────────────────────────────────────────

def test_no_config_anywhere(mkfile):
    assert pl._has_own_ruff_config(str(mkfile("plain/app.py"))) is False


@pytest.mark.parametrize("name", ["ruff.toml", ".ruff.toml"])
def test_dedicated_config_files_are_found(mkfile, name):
    f = mkfile(f"cfg_{name.strip('.')}/app.py")
    mkfile(f"cfg_{name.strip('.')}/{name}", "[lint]\nselect = ['F']\n")
    assert pl._has_own_ruff_config(str(f)) is True


def test_discovery_walks_up_to_a_parent(mkfile):
    mkfile("proj/ruff.toml", "[lint]\nselect = ['F']\n")
    deep = mkfile("proj/src/pkg/mod.py")
    assert pl._has_own_ruff_config(str(deep)) is True


def test_pyproject_without_tool_ruff_does_not_count(mkfile):
    """Ruff keeps searching past a pyproject that does not configure it."""
    f = mkfile("py_noruff/app.py")
    mkfile("py_noruff/pyproject.toml", "[project]\nname = 'x'\n")
    assert pl._has_own_ruff_config(str(f)) is False


@pytest.mark.parametrize("section", ["[tool.ruff]\nline-length = 100\n",
                                     "[tool.ruff.lint]\nselect = ['F']\n"])
def test_pyproject_with_tool_ruff_counts(mkfile, section, tmp_path):
    d = f"py_ruff_{abs(hash(section)) % 1000}"
    f = mkfile(f"{d}/app.py")
    mkfile(f"{d}/pyproject.toml", f"[project]\nname = 'x'\n\n{section}")
    assert pl._has_own_ruff_config(str(f)) is True


@pytest.mark.parametrize("bad", ["", "   ", "relative/path.py", "file:///c:/x.py"])
def test_degenerate_paths_are_not_configs(bad):
    """A non-absolute path must not be resolved against the process CWD — that
    is IDOL's launch directory, so a user's file would pick up IDOL's own
    config. `_run_checks` falls back to the raw URI when conversion fails, so
    this is reachable, not theoretical."""
    assert pl._has_own_ruff_config(bad) is False


def test_idols_own_source_finds_the_repo_config(repo_root):
    assert pl._has_own_ruff_config(str(repo_root / "app.py")) is True


# ── end to end through the real subprocess call ──────────────────────────────

def codes_for(source: str, path) -> list[str]:
    diags = pl._run_ruff(source, str(path))
    assert diags is not None, "ruff invocation failed"
    return sorted({d["message"].rsplit("(", 1)[-1].rstrip(")") for d in diags})


UNSORTED = "import tkinter as tk\nimport os\n\nprint(tk, os)\n"


def test_baseline_excludes_isort(mkfile):
    """I001 is what a beginner met on their own freshly written file."""
    assert codes_for(UNSORTED, mkfile("none/app.py")) == []


def test_baseline_still_catches_real_bugs(mkfile):
    assert codes_for("import os\n", mkfile("none/unused.py")) == ["F401"]


def test_project_config_wins(mkfile):
    f = mkfile("isort_proj/app.py")
    mkfile("isort_proj/ruff.toml", '[lint]\nselect = ["I"]\n')
    assert codes_for(UNSORTED, f) == ["I001"]


def test_project_config_is_not_merged_with_the_baseline(mkfile):
    """IDOL must not silently OR its own rules in on top of a deliberate setup."""
    f = mkfile("isort_only/app.py")
    mkfile("isort_only/ruff.toml", '[lint]\nselect = ["I"]\n')
    assert "F401" not in codes_for("import os\n", f)
