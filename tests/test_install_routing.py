"""Which backend an Install actually uses, in a conda environment.

Reported: install Pillow from the Designer, uninstall it in the Package
Manager, click Install again — and it comes back from PyPI via pip, complete
with IDOL's own "installing via pip in a conda environment can conflict…"
warning. IDOL believed the user had explicitly asked for PyPI. They had not.

`_selected_src` had two values doing three jobs: "pypi" meant both *the user
picked a PyPI search result* and *we have no conda metadata for this row*.
Everything selected from the installed list took the second meaning and was
routed by the first. The empty third state is the fix.

Selections are driven through the real population + `_on_select` path rather
than by assigning `_selected_src`, because the bug lived in how that value gets
set, not in how it is read.
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.gui


class _Backend:
    def __init__(self, label: str) -> None:
        self.label = label
        self.installs: list[str] = []
        self.uninstalls: list[str] = []
        self.installed = {"pillow": "11.1.0", "requests": "2.31.0"}
        self.origins = {"pillow": "defaults", "requests": "pypi"}

    def install(self, name, on_line=None, on_done=None, on_error=None,
                only_channel=None) -> None:
        self.installs.append(name)
        if on_done:
            on_done()

    def uninstall(self, name, origin=None, on_line=None, on_done=None,
                  on_error=None) -> None:
        self.uninstalls.append(name)
        self.installed.pop(name, None)
        self.origins.pop(name, None)
        if on_done:
            on_done()

    def fetch_installed(self, on_done) -> None:
        on_done(dict(self.installed), dict(self.origins))


@pytest.fixture
def panel(tk_root):
    """A panel whose active backend is conda, with both backends stubbed.

    `_backend is _conda` is the condition every pip-routing branch tests, so
    the fake conda backend has to be the same object in both slots.
    """
    from widgets.package_manager import PackageManagerPanel

    p = PackageManagerPanel(tk_root)
    p.conda = _Backend("conda")
    p.pip = _Backend("pip")
    p._conda = p._backend = p.conda
    p._pip = p.pip
    p._tos_ok_exe = p._conda.conda_exe = None   # skip the ToS gate
    p._load_installed()
    yield p
    p.destroy()


def _select_from_installed(panel, name):
    """Click a row in the INSTALLED tree, the way a user would."""
    panel._pypi_cache[name] = {}          # keep _fetch_pypi off the network
    panel._populate_grouped()
    panel._tree.selection_set(f"pkg:{name}")
    panel._on_select()


def _select_from_pypi_search(panel, name):
    panel._pypi_cache[name] = {}
    panel._search_source = "pypi"
    panel._populate_search([name])
    panel._tree.selection_set(f"pkg:{name}")
    panel._on_select()


def _select_from_conda_search(panel, name):
    panel._search_source = "conda"
    panel._conda_index.search = lambda q, channel=None: [{
        "name": name, "version": "11.1.0", "summary": "imaging",
        "home": "", "license": "", "channel": "conda-forge",
    }]
    panel._run_conda_search(name)
    panel._tree.selection_set(f"pkg:{name}")
    panel._on_select()


# ── The reported bug ─────────────────────────────────────────────────────────

def test_reinstall_after_uninstall_uses_conda(panel):
    """The exact reported sequence: uninstall a conda package, click Install."""
    _select_from_installed(panel, "pillow")
    panel._uninstall_pkg("pillow")
    assert panel.conda.uninstalls == ["pillow"]

    panel._install_pkg("pillow")
    assert panel.conda.installs == ["pillow"], "should reinstall through conda"
    assert panel.pip.installs == [], "must not fall through to pip"


def test_installed_list_selection_is_not_a_source_choice(panel):
    """Selecting from the installed list records no preference at all."""
    _select_from_installed(panel, "pillow")
    assert panel._selected_src == ""


# ── The cases that must keep working ─────────────────────────────────────────

def test_explicit_pypi_result_still_uses_pip(panel):
    _select_from_pypi_search(panel, "somepkg")
    assert panel._selected_src == "pypi"
    panel._install_pkg("somepkg")
    assert panel.pip.installs == ["somepkg"]
    assert panel.conda.installs == []


def test_explicit_conda_result_uses_conda(panel):
    _select_from_conda_search(panel, "pillow")
    assert panel._selected_src == "conda"
    panel._install_pkg("pillow")
    assert panel.conda.installs == ["pillow"]
    assert panel.pip.installs == []


def test_pip_origin_package_reinstalls_with_pip(panel):
    """A package still installed and known to have come from pip stays on pip —
    conda-installing it would swap the product underneath the user."""
    _select_from_installed(panel, "requests")
    assert panel._origins["requests"] == "pypi"
    panel._install_pkg("requests")
    assert panel.pip.installs == ["requests"]
    assert panel.conda.installs == []


def test_conda_origin_package_reinstalls_with_conda(panel):
    _select_from_installed(panel, "pillow")
    panel._install_pkg("pillow")
    assert panel.conda.installs == ["pillow"]
    assert panel.pip.installs == []


def test_non_conda_environment_is_untouched(panel):
    """With a pip backend there is no routing decision to make."""
    panel._backend = panel.pip
    _select_from_installed(panel, "pillow")
    panel._install_pkg("pillow")
    assert panel.pip.installs == ["pillow"]
