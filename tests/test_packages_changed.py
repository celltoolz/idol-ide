"""Installing or uninstalling must tell the rest of the app, not just the tree.

`PackageManagerPanel` is the only surface that changes what is installed, and it
used to finish every operation with `on_done=self._load_installed` — refreshing
its own tree and notifying nobody. The visible casualty was the Designer, whose
memoised `import PIL` probe was invalidated on install and never on uninstall:
remove Pillow and image props kept rendering as healthy until the run died on
`from PIL import Image`.

The asymmetry is what made it read as a regression — installing Pillow *from the
Designer* always cleared the warning correctly, so the mechanism looked wired.
"""
from __future__ import annotations

import pytest

from widgets import designer_properties


class _FakeBackend:
    """Stands in for PipManager/CondaManager — records calls, fires on_done.

    on_done fires unconditionally because the real backends do: neither knows
    whether the operation succeeded, which is why the notification must not be
    conditional on success either.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.installed: dict[str, str] = {"pillow": "10.0.0"}

    def install(self, name, on_line=None, on_done=None, on_error=None,
                only_channel=None) -> None:
        self.calls.append(("install", name))
        self.installed[name] = "1.0"
        if on_done:
            on_done()

    def uninstall(self, name, origin=None, on_line=None, on_done=None,
                  on_error=None) -> None:
        self.calls.append(("uninstall", name))
        self.installed.pop(name, None)
        if on_done:
            on_done()

    def fetch_installed(self, on_done) -> None:
        on_done(dict(self.installed), {})


@pytest.fixture
def panel(tk_root):
    """A panel with both backends stubbed, so no subprocess ever runs."""
    from widgets.package_manager import PackageManagerPanel

    fired: list[str] = []
    p = PackageManagerPanel(tk_root, on_packages_changed=lambda: fired.append("x"))
    backend = _FakeBackend()
    p._pip = p._conda = p._backend = backend
    p.fired = fired
    p.backend = backend
    yield p
    p.destroy()


@pytest.mark.gui
def test_uninstall_notifies(panel):
    """The reported bug: uninstall told nobody."""
    panel._exec_backend_op("uninstall", "pillow")
    assert panel.backend.calls == [("uninstall", "pillow")]
    assert panel.fired == ["x"]


@pytest.mark.gui
def test_install_notifies(panel):
    panel._exec_backend_op("install", "pillow")
    assert panel.backend.calls == [("install", "pillow")]
    assert panel.fired == ["x"]


@pytest.mark.gui
def test_scoped_conda_install_notifies(panel):
    """The third call site — `-c <channel> --override-channels` takes its own
    branch through _exec_backend_op and is easy to miss when wiring on_done."""
    panel._scope_channel = "conda-forge"
    panel._exec_backend_op("install", "numpy")
    assert panel.backend.calls == [("install", "numpy")]
    assert panel.fired == ["x"]


@pytest.mark.gui
def test_the_hub_refreshes_the_panel_not_the_panel_itself(panel):
    """`refresh_installed` is a hub consumer, so `_op_done` must not also do
    its own reload — one operation would then run `conda list` twice.

    Stubs `_load_installed`, not `refresh_installed`: the wrapper is what the
    fix added, so counting calls to it would pass against the old code too.
    """
    reloads = []
    panel._load_installed = lambda: reloads.append(1)
    panel._exec_backend_op("install", "requests")
    assert panel.fired == ["x"], "the hub was not notified"
    assert reloads == [], "panel reloaded itself as well as being notified"


@pytest.mark.gui
def test_panel_refreshes_itself_with_no_listener(tk_root):
    """Standalone fallback: with no host wired, the panel is its own consumer."""
    from widgets.package_manager import PackageManagerPanel

    p = PackageManagerPanel(tk_root)
    p._pip = p._conda = p._backend = _FakeBackend()
    p._exec_backend_op("install", "requests")
    assert "requests" in p._installed
    p.destroy()


@pytest.mark.gui
def test_an_outside_install_refreshes_the_panel(panel):
    """The reported bug, from the panel's side: something else installed a
    package while this panel sat there showing the old answer."""
    panel.backend.installed["numpy"] = "2.5.1"
    panel.refresh_installed()
    assert "numpy" in panel._installed


# ── The listener: DesignerProperties.invalidate_package_cache ────────────────
#
# Bound onto a stand-in rather than a real panel (the house pattern from
# tests/test_project_root.py) — the method under test is the shipped one, only
# its collaborators are stubbed, and these stay headless.

_invalidate = designer_properties.DesignerProperties.invalidate_package_cache


class _Widget:
    def __init__(self, image: str = "") -> None:
        self.props = {"image": image} if image else {}


class _Form:
    def __init__(self, image: str = "") -> None:
        self.image = image


class _Props:
    """Only what invalidate_package_cache touches."""

    def __init__(self, widget=None, form=None, comp_mode=False) -> None:
        self._pil_available = True          # the stale "yes, PIL is here"
        self._pil_gen = 0
        self._comp_mode = comp_mode
        self._current_widget = widget
        self._form = form
        self.rendered: list[str] = []

    def load_widget(self, _d) -> None:
        self.rendered.append("widget")

    def load_form(self, _f) -> None:
        self.rendered.append("form")


def test_cache_is_always_cleared():
    p = _Props()
    _invalidate(p)
    assert p._pil_available is None


def test_widget_view_rerenders_when_it_shows_an_image():
    """Clearing alone is not enough — the stale row is already on screen."""
    p = _Props(widget=_Widget("logo.png"))
    _invalidate(p)
    assert p.rendered == ["widget"]


def test_widget_without_an_image_is_not_rerendered():
    """Nothing on that view probes PIL, so there is no answer to correct."""
    p = _Props(widget=_Widget())
    _invalidate(p)
    assert p.rendered == []
    assert p._pil_available is None


def test_form_view_rerenders_when_the_form_has_an_image():
    p = _Props(form=_Form("splash.png"))
    _invalidate(p)
    assert p.rendered == ["form"]


def test_component_mode_is_not_rerendered():
    """Component view runs no PIL probe on load; the cache still clears."""
    p = _Props(widget=_Widget("logo.png"), comp_mode=True)
    _invalidate(p)
    assert p.rendered == []
    assert p._pil_available is None


def test_invalidating_bumps_the_probe_generation():
    """An uninstall can land while a probe is in flight, and that probe is
    about to report on the environment as it was before."""
    p = _Props(widget=_Widget("logo.png"))
    before = p._pil_gen
    _invalidate(p)
    assert p._pil_gen == before + 1
