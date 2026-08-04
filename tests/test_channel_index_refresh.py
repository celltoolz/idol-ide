"""Refreshing the conda channel index by hand.

`CondaSearchIndex` has always accepted `force=True`, and nothing called it — so
the index rebuilt only on its weekly expiry or when the channel set changed. A
package published today could not be searched for until the cache aged out, with
no way to say "look again".

Bound onto a stand-in: the methods touch labels and the index, not the tree.
"""
from __future__ import annotations

import pytest

from widgets import package_manager as pm

_refresh = pm.PackageManagerPanel._refresh_channel_index


class _Label:
    def __init__(self) -> None:
        self.text = ""
        self.history: list[str] = []

    def config(self, text=None, fg=None, **_kw):
        if text is not None:
            self.text = text
            self.history.append(text)


class _Index:
    """Records how ensure_loaded was called; fires on_done when told to."""

    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], bool]] = []
        self._pending = None

    def ensure_loaded(self, channels, on_done=None, force=False):
        self.calls.append((tuple(channels), force))
        self._pending = on_done

    def finish(self, count: int = 1234) -> None:
        cb, self._pending = self._pending, None
        if cb:
            cb(count)


class _Panel:
    def __init__(self, channels=("conda-forge", "defaults"),
                 source="conda", listing="conda", query="") -> None:
        self._channels = list(channels)
        self._chan_refreshing = False
        self._chan_refresh = _Label()
        self._conda_index = _Index()
        self._search_source = source
        self._listing = listing
        self._query = query
        self.notes: list[str] = []
        self.rendered = 0
        self.searches: list[str] = []

    # collaborators
    def _resolve_channels(self):
        return list(self._channels), True

    def _notify(self, text):
        self.notes.append(text)

    def _render_channel_bar(self):
        self.rendered += 1

    def _run_conda_search(self, query):
        self.searches.append(query)

    @property
    def _search_var(self):
        outer = self

        class _V:
            def get(self):
                return outer._query
        return _V()

    _refresh_channel_index = _refresh


def test_forces_a_rebuild_of_the_active_channels():
    p = _Panel()
    p._refresh_channel_index()
    assert p._conda_index.calls == [(("conda-forge", "defaults"), True)]


def test_shows_progress_then_returns_to_idle():
    p = _Panel()
    p._refresh_channel_index()
    assert p._chan_refresh.text == pm._REFRESH_BUSY
    p._conda_index.finish()
    assert p._chan_refresh.text == pm._REFRESH_IDLE


def test_a_second_click_while_running_is_ignored():
    """ensure_loaded would queue the callback behind the running load and
    report done twice for one visible refresh."""
    p = _Panel()
    p._refresh_channel_index()
    p._refresh_channel_index()
    assert len(p._conda_index.calls) == 1


def test_clicking_again_after_it_finishes_works():
    p = _Panel()
    p._refresh_channel_index()
    p._conda_index.finish()
    p._refresh_channel_index()
    assert len(p._conda_index.calls) == 2


def test_nothing_to_refresh_does_nothing():
    p = _Panel(channels=())
    p._refresh_channel_index()
    assert p._conda_index.calls == []
    assert p._chan_refresh.text == ""


def test_repaints_the_bar_afterwards():
    """missing_channels feeds a guardrail on the source line and may have
    changed, so the old verdict must not be left sitting there."""
    p = _Panel()
    p._refresh_channel_index()
    p._conda_index.finish()
    assert p.rendered == 1


def test_reports_what_it_found():
    p = _Panel()
    p._refresh_channel_index()
    p._conda_index.finish(4321)
    assert any("4321 packages" in n for n in p.notes)


def test_re_runs_the_search_that_is_on_screen():
    """A refresh whose result you have to go and ask for again has not
    finished the job."""
    p = _Panel(query="numpy")
    p._refresh_channel_index()
    p._conda_index.finish()
    assert p.searches == ["numpy"]


@pytest.mark.parametrize("source,listing,query", [
    ("pypi", "conda", "numpy"),      # searching PyPI — conda results aren't shown
    ("conda", "installed", "numpy"),  # back on the installed list
    ("conda", "conda", ""),           # no query to re-run
])
def test_does_not_re_run_a_search_that_is_not_showing(source, listing, query):
    p = _Panel(source=source, listing=listing, query=query)
    p._refresh_channel_index()
    p._conda_index.finish()
    assert p.searches == []
