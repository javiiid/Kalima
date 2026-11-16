"""Preferences: the contract the settings page is built on.

These drive ``app.preferences.service`` directly rather than the HTTP handler.
The handler is a thin dispatch layer; the decisions worth pinning down are the
service's, and every one of them is a decision that would otherwise be
discovered as a bug in production:

* an unknown model or zone is refused, never silently replaced;
* two users cannot see each other's preferences;
* the ``reading`` section is the reader's own storage, not a second copy;
* clamping matches what the reader already enforces;
* "reset" does not throw away where the reader was in a book.

``isolated_db`` is the fixture from ``tests/conftest.py``. Direct table access
goes through it rather than through a module-level ``db`` import, because the
singleton is rebound per test and a stale reference would write to the shared
placeholder database instead of this test's file.
"""
from __future__ import annotations

import pytest

from app.preferences.reading import READING_DEFAULTS, reading_settings
from app.preferences.service import (
    PREF_DEFAULTS,
    PreferenceError,
    get_preferences,
    preferences_meta,
    reset_preferences,
    save_preferences,
)

STAMP = "2026-01-01T00:00:00+00:00"


def _add_user(database, email: str) -> int:
    database.execute(
        "INSERT INTO users(email, display_name, password_hash, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
        (email, email, "not-a-real-hash", STAMP, STAMP),
    )
    return int(database.fetch_one("SELECT id FROM users WHERE email=?", (email,))["id"])


def _two_users(database) -> tuple[int, int]:
    """The owner (the install's first user, whose rows are unprefixed) and a
    second account, so a scoping test has two ids that are actually different.
    """
    owner = _add_user(database, "owner@example.com")
    other = _add_user(database, "other@example.com")
    return owner, other


def _stored_pref_keys(database) -> list[str]:
    """Only the keys this contract owns -- ``settings`` also holds bookkeeping."""
    return [
        row["key"]
        for row in database.fetch_all(
            "SELECT key FROM settings WHERE key LIKE '%pref.%' ORDER BY key"
        )
    ]


# ---------------------------------------------------------------- defaults


def test_defaults_are_returned_when_nothing_is_stored(isolated_db):
    values = get_preferences(1)
    assert values["general"]["language"] == "fa"
    assert values["general"]["timezone"] == "Asia/Tehran"
    assert values["appearance"]["theme"] == "system"
    assert values["notifications"]["events"] == ["job.completed", "job.failed"]
    # Empty model means "whatever config.yaml says", so the field must not
    # carry a hardcoded model of its own.
    assert values["translation"]["default_model"] == ""
    assert _stored_pref_keys(isolated_db) == []


def test_the_reading_section_is_the_readers_own_storage():
    values = get_preferences(1)
    assert values["reading"] == reading_settings(1)
    assert values["reading"]["reading_font_size"] == READING_DEFAULTS["reading_font_size"]


def test_meta_names_the_real_default_model_and_the_option_lists():
    meta = preferences_meta(1)
    assert meta["defaults"]["translation.default_model"]
    assert "literary" in meta["options"]["style_presets"]
    assert "Asia/Tehran" in meta["options"]["timezones"]
    assert "job.failed" in meta["options"]["notification_events"]
    assert meta["updated_at"] is None


# --------------------------------------------------------------- validation


def test_an_unsupported_model_is_refused_rather_than_replaced():
    with pytest.raises(PreferenceError) as error:
        save_preferences(1, {"translation": {"default_model": "gpt-nope"}})
    assert error.value.field == "translation.default_model"
    assert get_preferences(1)["translation"]["default_model"] == ""


def test_an_unknown_timezone_is_refused():
    with pytest.raises(PreferenceError) as error:
        save_preferences(1, {"general": {"timezone": "Mars/Olympus"}})
    assert error.value.field == "general.timezone"


def test_a_known_timezone_is_accepted_even_without_the_tz_database():
    # Windows ships no tz database; the fallback list has to keep this working.
    saved = save_preferences(1, {"general": {"timezone": "Europe/Berlin"}})
    assert saved["general"]["timezone"] == "Europe/Berlin"


def test_unknown_sections_and_fields_are_dropped_not_stored(isolated_db):
    saved = save_preferences(1, {"nonsense": {"a": 1}, "general": {"nope": True}})
    assert "nonsense" not in saved
    assert _stored_pref_keys(isolated_db) == []


def test_a_non_boolean_switch_is_refused():
    with pytest.raises(PreferenceError) as error:
        save_preferences(1, {"appearance": {"animations": "maybe"}})
    assert error.value.field == "appearance.animations"


def test_webhook_requires_https_unless_it_is_loopback():
    with pytest.raises(PreferenceError) as error:
        save_preferences(1, {"notifications": {"webhook": "http://evil.example/hook"}})
    assert error.value.field == "notifications.webhook"
    # A local receiver is the normal thing to point at in the local build.
    saved = save_preferences(1, {"notifications": {"webhook": "http://127.0.0.1:9000/hook"}})
    assert saved["notifications"]["webhook"] == "http://127.0.0.1:9000/hook"


def test_a_webhook_with_no_events_is_refused_on_the_merged_state():
    save_preferences(1, {"notifications": {"events": []}})
    with pytest.raises(PreferenceError) as error:
        save_preferences(1, {"notifications": {"webhook": "https://example.com/hook"}})
    assert error.value.field == "notifications.events"


def test_events_are_stored_in_canonical_order_and_deduplicated():
    saved = save_preferences(
        1, {"notifications": {"events": ["job.failed", "job.completed", "job.failed"]}}
    )
    assert saved["notifications"]["events"] == ["job.completed", "job.failed"]


def test_an_unknown_event_is_refused():
    with pytest.raises(PreferenceError):
        save_preferences(1, {"notifications": {"events": ["job.exploded"]}})


# ------------------------------------------------------------------- scoping


def test_two_users_do_not_see_each_others_preferences(isolated_db):
    owner, second = _two_users(isolated_db)
    save_preferences(owner, {"general": {"language": "en"}})
    save_preferences(second, {"general": {"language": "fa"}})

    assert get_preferences(owner)["general"]["language"] == "en"
    assert get_preferences(second)["general"]["language"] == "fa"
    assert any(key.startswith(f"u{second}:pref.") for key in _stored_pref_keys(isolated_db))


def test_a_second_users_reading_settings_do_not_touch_the_first_users(isolated_db):
    owner, second = _two_users(isolated_db)
    save_preferences(owner, {"reading": {"reading_font_size": 24}})
    save_preferences(second, {"reading": {"reading_font_size": 15}})

    assert get_preferences(owner)["reading"]["reading_font_size"] == 24
    assert get_preferences(second)["reading"]["reading_font_size"] == 15
    assert reading_settings(owner)["reading_font_size"] == 24


# ------------------------------------------------------------------- reading


def test_writing_reading_through_preferences_reaches_the_reader():
    save_preferences(1, {"reading": {"reading_font_size": 27, "reading_theme": "sepia"}})
    reader_view = reading_settings(1)
    assert reader_view["reading_font_size"] == 27
    assert reader_view["reading_theme"] == "sepia"


def test_a_value_the_reader_writes_shows_up_in_preferences(isolated_db):
    isolated_db.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
        ("reading_width", "880", STAMP),
    )
    assert get_preferences(1)["reading"]["reading_width"] == 880


def test_reading_values_are_clamped_like_the_reader_clamps_them():
    saved = save_preferences(
        1,
        {"reading": {"reading_font_size": 99, "reading_line_height": 0.1, "reading_width": 10}},
    )
    assert saved["reading"]["reading_font_size"] == 30
    assert saved["reading"]["reading_line_height"] == 1.4
    assert saved["reading"]["reading_width"] == 560


def test_an_unknown_reading_value_falls_back_to_the_default_not_to_junk():
    saved = save_preferences(1, {"reading": {"reading_theme": "neon", "reading_font_size": "abc"}})
    assert saved["reading"]["reading_theme"] == READING_DEFAULTS["reading_theme"]
    assert saved["reading"]["reading_font_size"] == READING_DEFAULTS["reading_font_size"]


def test_bookmarks_are_not_writable_through_preferences(isolated_db):
    isolated_db.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
        ("reading_bookmarks", '[{"chapter": 3}]', STAMP),
    )
    save_preferences(1, {"reading": {"reading_bookmarks": [], "reading_font_size": 20}})
    assert get_preferences(1)["reading"]["reading_bookmarks"] == [{"chapter": 3}]


# --------------------------------------------------------------------- reset


def test_reset_restores_defaults(isolated_db):
    save_preferences(1, {"general": {"language": "en"}, "appearance": {"theme": "dark"}})
    reset = reset_preferences(1)
    assert reset["general"]["language"] == PREF_DEFAULTS["general"]["language"]
    assert reset["appearance"]["theme"] == PREF_DEFAULTS["appearance"]["theme"]
    assert _stored_pref_keys(isolated_db) == []


def test_reset_keeps_where_the_reader_was_and_their_bookmarks(isolated_db):
    # Losing your place in every book is data loss, not a settings reset.
    isolated_db.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
        ("reading_last_location", '{"chapter": 7, "frac": 0.4}', STAMP),
    )
    isolated_db.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)",
        ("reading_bookmarks", '[{"chapter": 7}]', STAMP),
    )
    save_preferences(1, {"reading": {"reading_font_size": 26}})

    reset = reset_preferences(1)
    assert reset["reading"]["reading_font_size"] == READING_DEFAULTS["reading_font_size"]
    assert reset["reading"]["reading_last_location"] == {"chapter": 7, "frac": 0.4}
    assert reset["reading"]["reading_bookmarks"] == [{"chapter": 7}]


def test_reset_only_touches_the_calling_user(isolated_db):
    owner, second = _two_users(isolated_db)
    save_preferences(owner, {"general": {"language": "en"}})
    save_preferences(second, {"general": {"language": "en"}})
    reset_preferences(second)
    assert get_preferences(owner)["general"]["language"] == "en"
    assert get_preferences(second)["general"]["language"] == "fa"