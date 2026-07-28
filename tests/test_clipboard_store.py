"""Clipboard history persistence and per-project scoping."""
from __future__ import annotations

import pytest

from utils import clipboard_store as store


@pytest.fixture
def clip_dir(tmp_path, monkeypatch):
    """Redirect storage so the developer's real ~/.idol/clipboard is untouched."""
    d = tmp_path / "clipboard"
    monkeypatch.setattr(store, "CLIP_DIR", d)
    return d


@pytest.fixture
def proj(tmp_path):
    p = tmp_path / "myapp"
    p.mkdir()
    return str(p)


# ── store ────────────────────────────────────────────────────────────────────

def test_caps_differ_by_scope(proj):
    assert store.max_for(None) == store.SCRATCH_MAX == 20
    assert store.max_for(proj) == store.PROJECT_MAX == 50


def test_missing_file_loads_empty(clip_dir, proj):
    assert store.load(proj) == []


def test_round_trip_preserves_pin(clip_dir, proj):
    store.save(proj, [{"text": "a", "source": "x.py", "ts": "", "pinned": True}])
    loaded = store.load(proj)
    assert [e["text"] for e in loaded] == ["a"]
    assert loaded[0]["pinned"] is True


def test_path_key_normalizes_case_and_separators(clip_dir, tmp_path):
    """`C:\\Dev\\App`, `c:/dev/app` and a trailing slash must be one history."""
    a = str(tmp_path / "MyApp")
    b = str(tmp_path / "myapp")
    assert store.path_for(a) == store.path_for(b)


def test_scratch_and_project_are_distinct(clip_dir, proj):
    assert store.path_for(None) != store.path_for(proj)


def test_corrupt_file_reads_as_empty(clip_dir, proj):
    """A broken history is worth losing silently, never worth blocking on."""
    target = store.path_for(proj)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not json", encoding="utf-8")
    assert store.load(proj) == []


def test_malformed_entries_are_dropped(clip_dir, proj):
    store.save(proj, [{"text": ""}, {"nope": 1}, "a string", {"text": "ok"}])
    assert [e["text"] for e in store.load(proj)] == ["ok"]


def test_saving_empty_removes_the_file(clip_dir, proj):
    store.save(proj, [{"text": "x"}])
    assert store.path_for(proj).exists()
    store.save(proj, [])
    assert not store.path_for(proj).exists()


# ── panel ────────────────────────────────────────────────────────────────────

@pytest.fixture
def panel(tk_root):
    from widgets.clipboard_history import ClipboardHistoryPanel
    saves: list[int] = []
    p = ClipboardHistoryPanel(tk_root, on_change=lambda: saves.append(1))
    p.pack(fill="both", expand=True)
    tk_root.update()
    p.saves = saves          # type: ignore[attr-defined]
    return p


def texts(p):
    return [e["text"] for e in p.export_entries()]


@pytest.mark.gui
def test_push_dedupes_and_orders_newest_first(panel):
    panel.push("one", "a.py")
    panel.push("two", "b.py")
    assert texts(panel) == ["two", "one"]
    panel.push("one", "a.py")
    assert texts(panel) == ["one", "two"]


@pytest.mark.gui
def test_push_notifies_host_for_persistence(panel):
    panel.push("one")
    panel.push("two")
    assert len(panel.saves) == 2


@pytest.mark.gui
def test_load_entries_does_not_notify(panel):
    """Loading is the host's own doing; re-entering the save path while loading
    would write the incoming history straight back over itself."""
    panel.push("one")
    before = len(panel.saves)
    panel.load_entries([{"text": "other"}])
    assert len(panel.saves) == before


@pytest.mark.gui
def test_trim_keeps_pins_and_preserves_recency(panel):
    """Overflow must drop the oldest unpinned entries and reorder nothing —
    the old rebuild sorted every pin to the top the moment the ring filled."""
    panel.set_max(3)
    for t in ["p1", "e1", "e2", "e3", "e4"]:
        panel.push(t)
        if t == "p1":
            panel._ring[0].pinned = True
    assert texts(panel) == ["e4", "e3", "p1"]


@pytest.mark.gui
def test_pins_may_exceed_the_cap(panel):
    """An all-pinned ring above the cap is the user's explicit choice."""
    panel.load_entries([{"text": f"p{i}", "pinned": True} for i in range(5)])
    panel.set_max(3)
    assert len(texts(panel)) == 5


@pytest.mark.gui
def test_clear_unpinned_keeps_pins(panel):
    panel.load_entries([{"text": "keep", "pinned": True}, {"text": "drop"}])
    panel.clear_unpinned()
    assert texts(panel) == ["keep"]


@pytest.mark.gui
def test_unparseable_timestamp_does_not_drop_the_entry(panel):
    """The timestamp only drives the row's "3m ago" label."""
    panel.load_entries([{"text": "t", "ts": "not-a-date"}])
    assert texts(panel) == ["t"]


@pytest.mark.gui
def test_scope_swap_clears_a_stale_filter(panel, tk_root):
    panel.load_entries([{"text": "alpha"}, {"text": "beta"}])
    panel._q.set("alpha")
    tk_root.update()
    assert len(panel._visible) == 1
    panel.load_entries([{"text": "gamma"}])
    assert texts(panel) == ["gamma"]
    assert len(panel._visible) == 1


@pytest.mark.gui
def test_project_switch_keeps_histories_separate(panel, clip_dir, proj):
    """The full swap app.py performs: flush outgoing, load incoming, no merge."""
    scope = None
    panel.set_max(store.max_for(scope))
    panel.load_entries(store.load(scope))
    panel.push("scratch-copy")

    store.save(scope, panel.export_entries())          # open a project
    scope = proj
    panel.set_max(store.max_for(scope))
    panel.load_entries(store.load(scope))
    assert texts(panel) == []
    panel.push("proj-copy")

    store.save(scope, panel.export_entries())          # close it
    scope = None
    panel.set_max(store.max_for(scope))
    panel.load_entries(store.load(scope))

    assert texts(panel) == ["scratch-copy"]
    assert "proj-copy" not in texts(panel)
    assert [e["text"] for e in store.load(proj)] == ["proj-copy"]
