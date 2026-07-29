"""The preference store, and the migration that stops preferences leaking.

Theme, editor font, minimap and the Ollama URL used to live in the session, and
`session.restore()` applies whatever file it reads — including a project's
`.idol-project`. Opening a project therefore changed the user's theme and font.
These tests pin both the store's behaviour and the one-time move out.
"""
from __future__ import annotations

import ast
import inspect
import json

import pytest

from utils import settings


@pytest.fixture
def store(tmp_path, monkeypatch):
    """Point the store at a temp file and clear its cache around each test."""
    target = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_FILE", target)
    settings.reload()
    yield target
    settings.reload()


# ── Schema ────────────────────────────────────────────────────────────────────

def test_schema_keys_are_unique():
    keys = [s.key for s in settings.schema()]
    assert len(keys) == len(set(keys))


def test_every_setting_declares_a_section_and_label():
    for s in settings.schema():
        assert s.section and s.label, s.key


def test_sections_are_ordered_and_deduplicated():
    secs = settings.sections()
    assert len(secs) == len(set(secs))
    assert secs, "no sections declared"


def test_choice_settings_default_to_one_of_their_choices():
    for s in settings.schema():
        if s.kind == "choice":
            assert s.default in s.choices, s.key


# ── Defaults and reads ────────────────────────────────────────────────────────

def test_unset_key_returns_its_schema_default(store):
    assert settings.get("editor.minimap_visible") is True
    assert settings.get("appearance.theme") == "monokai-bright"


def test_unknown_key_falls_back_to_the_caller_default(store):
    """`interpreter:<root>` and friends predate the schema and still live here."""
    assert settings.get("interpreter:/some/path", "fallback") == "fallback"
    settings.set("interpreter:/some/path", "/usr/bin/python3")
    assert settings.get("interpreter:/some/path") == "/usr/bin/python3"


def test_is_default_tracks_whether_a_value_was_stored(store):
    assert settings.is_default("editor.minimap_visible")
    settings.set("editor.minimap_visible", False)
    assert not settings.is_default("editor.minimap_visible")


def test_reset_restores_the_default(store):
    settings.set("appearance.theme", "dracula")
    assert settings.get("appearance.theme") == "dracula"
    settings.reset("appearance.theme")
    assert settings.get("appearance.theme") == "monokai-bright"
    assert settings.is_default("appearance.theme")


def test_only_changed_values_are_written(store):
    """The file holds overrides, not a dump of every default — otherwise a
    changed default would never reach an existing user."""
    settings.set("appearance.theme", "dracula")
    on_disk = json.loads(store.read_text(encoding="utf-8"))
    assert "appearance.theme" in on_disk
    assert "editor.minimap_visible" not in on_disk


def test_values_survive_a_reload(store):
    settings.set("appearance.theme", "nord")
    settings.reload()
    assert settings.get("appearance.theme") == "nord"


def test_corrupt_file_reads_as_empty(store):
    store.parent.mkdir(parents=True, exist_ok=True)
    store.write_text("{not json", encoding="utf-8")
    settings.reload()
    assert settings.get("appearance.theme") == "monokai-bright"


# ── Change notification ───────────────────────────────────────────────────────

def test_subscribers_are_notified(store):
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append((k, v)))
    try:
        settings.set("appearance.theme", "nord")
        assert seen == [("appearance.theme", "nord")]
    finally:
        unsub()


def test_setting_the_same_value_notifies_nothing(store):
    settings.set("appearance.theme", "nord")
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append(k))
    try:
        settings.set("appearance.theme", "nord")
        assert seen == []
    finally:
        unsub()


def test_reset_notifies_with_the_default(store):
    settings.set("appearance.theme", "nord")
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append((k, v)))
    try:
        settings.reset("appearance.theme")
        assert seen == [("appearance.theme", "monokai-bright")]
    finally:
        unsub()


def test_unsubscribe_stops_delivery(store):
    seen = []
    unsub = settings.subscribe(lambda k, v: seen.append(k))
    unsub()
    settings.set("appearance.theme", "nord")
    assert seen == []


def test_a_broken_listener_does_not_break_the_write(store):
    def boom(_k, _v):
        raise RuntimeError("listener exploded")

    unsub = settings.subscribe(boom)
    try:
        settings.set("appearance.theme", "nord")
        assert settings.get("appearance.theme") == "nord"
    finally:
        unsub()


# ── Editor font helper ────────────────────────────────────────────────────────

def test_editor_font_round_trip(store):
    assert settings.get_editor_font() is None
    settings.set_editor_font("Consolas", 13, "bold", "italic")
    assert settings.get_editor_font() == ("Consolas", 13, "bold", "italic")


def test_editor_font_defaults_the_optional_parts(store):
    settings.set("editor.font", ["Consolas", 12])
    assert settings.get_editor_font() == ("Consolas", 12, "normal", "roman")


@pytest.mark.parametrize("bad", [None, "Consolas", ["Consolas"], [], 42,
                                 ["Consolas", "not-a-size"]])
def test_malformed_editor_font_reads_as_none(store, bad):
    """The file is hand-editable; every caller should not re-validate it."""
    settings.set("editor.font", bad)
    assert settings.get_editor_font() is None


# ── Migration ─────────────────────────────────────────────────────────────────

def _write_session(path, **blocks):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(blocks), encoding="utf-8")


def test_migration_moves_preferences_out_of_the_session(store, tmp_path):
    session = tmp_path / "session.json"
    _write_session(
        session,
        appearance={"theme": "dracula", "font": ["Consolas", 13, "bold", "roman"],
                    "minimap_visible": False},
        layout={"ollama_url": "http://box:11434"},
    )
    assert settings.migrate_from_session(session) is True
    assert settings.get("appearance.theme") == "dracula"
    assert settings.get_editor_font() == ("Consolas", 13, "bold", "roman")
    assert settings.get("editor.minimap_visible") is False
    assert settings.get("ai.ollama_url") == "http://box:11434"


def test_migration_runs_only_once(store, tmp_path):
    session = tmp_path / "session.json"
    _write_session(session, appearance={"theme": "dracula"})
    assert settings.migrate_from_session(session) is True
    # A later session write must not re-migrate over a since-changed value.
    settings.set("appearance.theme", "nord")
    _write_session(session, appearance={"theme": "dracula"})
    assert settings.migrate_from_session(session) is False
    assert settings.get("appearance.theme") == "nord"


def test_migration_never_overwrites_an_existing_preference(store, tmp_path):
    settings.set("appearance.theme", "nord")
    session = tmp_path / "session.json"
    _write_session(session, appearance={"theme": "dracula"})
    settings.migrate_from_session(session)
    assert settings.get("appearance.theme") == "nord"


def test_migration_survives_a_missing_session(store, tmp_path):
    assert settings.migrate_from_session(tmp_path / "nope.json") is False
    assert settings.get("appearance.theme") == "monokai-bright"


def test_migration_survives_a_corrupt_session(store, tmp_path):
    session = tmp_path / "session.json"
    session.parent.mkdir(parents=True, exist_ok=True)
    session.write_text("{not json", encoding="utf-8")
    assert settings.migrate_from_session(session) is False


def test_migration_reads_the_auto_session_only():
    """Migrating from a *project* file would make the last-opened project's
    theme the user's permanently — the leak, inverted."""
    src = inspect.getsource(settings.migrate_from_session)
    assert "session.json" in src
    assert "idol-project" not in src


# ── The session must no longer own these ──────────────────────────────────────

def test_session_no_longer_saves_preferences():
    from utils import session as session_mod

    src = inspect.getsource(session_mod.save)
    tree = ast.parse(f"def _f():\n{_indent(src)}")
    stored = {
        node.slice.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.slice, ast.Constant)
        and isinstance(node.slice.value, str)
    }
    for leaked in ("theme", "font", "minimap_visible", "ollama_url"):
        assert leaked not in stored, (
            f"session.save still writes {leaked!r}; it is a preference and "
            f"belongs in utils/settings.py"
        )


def test_session_no_longer_applies_preferences():
    from utils import session as session_mod

    src = inspect.getsource(session_mod.restore)
    for leaked in ("view_change_theme", "set_font", "view_toggle_minimap",
                   "set_base_url"):
        assert leaked not in src, (
            f"session.restore still applies {leaked}; that is what let a "
            f"project file overwrite a user preference"
        )


def test_app_applies_preferences_at_startup():
    import app as app_mod

    src = inspect.getsource(app_mod.IDOL.__init__)
    assert "migrate_from_session" in src
    assert "_apply_user_preferences" in src
    # Migration reads the old auto-session, so it has to happen before a
    # restore or save can rewrite that file.
    assert src.index("migrate_from_session") < src.index("session_utils.restore")


def _indent(text: str) -> str:
    return "\n".join("    " + line for line in text.splitlines())
