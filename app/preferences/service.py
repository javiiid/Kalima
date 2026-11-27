"""User preferences: one user-scoped contract for the settings page.

Why this module exists
----------------------
Preferences were split across four places with four lifetimes: the theme and
the interface language lived only in ``localStorage``, the translation
defaults only in ``config/config.yaml``, the reader settings in the
``settings`` table, and the account page's own fields in the ``users`` row.
There was no single place a user could look at, and no way for a second
device to inherit any of it.

This module is that single place. ``GET/PUT/DELETE /api/preferences`` are its
only callers.

Storage
-------
Keys live in the existing ``settings`` key/value table with a per-user prefix,
``u{uid}:pref.<section>.<field>`` -- the same shape
:func:`app.preferences.reading.reading_setting_key` already uses for
``reading_*``. A dedicated ``user_preferences(user_id, key, value_json)``
table would be tidier, but it would add a schema migration without changing
the scoping guarantee: both forms are user-scoped from day one, which is the
property ``LAUNCH.md`` Phase A actually needs, and the prefix form migrates in
one script when a real table becomes worth having.

The ``reading`` section is deliberately **not** duplicated here. It is
composed from :func:`app.preferences.reading.reading_settings` and writes go
back through ``reading_setting_key``, so the reader and the settings page can
never disagree about the font size.

Validation
----------
Every field is checked on the server, because the client is a convenience and
not a gate: ``is_supported_model`` rejects an unknown model, ``ZoneInfo`` (or
the fallback list) rejects an unknown zone, and the reading values reuse the
reader's own clamps. Unknown keys are dropped silently, matching the reader's
long-standing behaviour. A rejected value raises :class:`PreferenceError`
carrying the dotted field name so the form can put the message on the control
that produced it.
"""
from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.models import is_supported_model, resolve_default_model
from app.library import shelves as book_shelves
from app.presets.manager import get_preset_names
from app.preferences.reading import (
    clean_reading_settings,
    default_user_id,
    reading_settings,
    reading_setting_key,
)
from app.storage.database import db

UTC = timezone.utc

LANGUAGES = ("fa", "en")
DATE_FORMATS = ("jalali", "gregorian", "iso")
TRANSLATION_MODES = ("fast",)
LANGUAGE_CODES = ("EN", "FA", "DE", "FR", "AR")
APPEARANCE_THEMES = ("light", "dark", "system")
DENSITIES = ("comfortable", "compact")
NOTIFICATION_EVENTS = ("job.completed", "job.failed", "job.stopped", "quota.warning")

# The zones the picker offers. Validation is not limited to this list: any zone
# the platform can resolve is accepted. The list exists so the form has a short
# menu and so validation still works where the tz database is missing -- Windows
# ships none, and ``zoneinfo`` needs the ``tzdata`` package there.
COMMON_TIMEZONES = (
    "Asia/Tehran",
    "UTC",
    "Europe/Istanbul",
    "Asia/Dubai",
    "Asia/Kolkata",
    "Europe/London",
    "Europe/Berlin",
    "America/New_York",
)

LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1", "[::1]"}

PREF_DEFAULTS = {
    "general": {
        "language": "fa",
        "timezone": "Asia/Tehran",
        "date_format": "jalali",
        "resume_last_page": True,
        "show_onboarding": True,
    },
    "translation": {
        # Empty means "the model configured in config.yaml", which is exactly
        # what resolve_default_model() already decides. Nothing is hardcoded.
        "default_model": "",
        "mode": "fast",
        "style_preset": "",
        "auto_glossary": False,
        "preserve_voice": True,
        "from_lang": "EN",
        "to_lang": "FA",
    },
    "appearance": {
        # "system" is a real third choice, not the absence of one: it means
        # "follow the operating system", and useTheme tracks matchMedia for it.
        "theme": "system",
        "density": "comfortable",
        "animations": True,
    },
    "notifications": {
        "email": True,
        "in_app": True,
        "webhook": "",
        "events": ["job.completed", "job.failed"],
    },
}


class PreferenceError(ValueError):
    """A rejected preference value, carrying the dotted field that produced it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


def _now() -> str:
    return datetime.now(UTC).isoformat()


def pref_setting_key(user_id: int, path: str) -> str:
    """The stored key for one preference path (``general.timezone``).

    One function builds every key so a future migration to a real table has a
    single place to change.
    """
    uid = int(user_id)
    key = f"pref.{path}"
    return key if uid == default_user_id() else f"u{uid}:{key}"


def is_valid_timezone(value: str) -> bool:
    """Whether a zone name is one the platform can resolve.

    ``ZoneInfo`` is authoritative, but on Windows without the ``tzdata``
    package it raises for *every* name, valid ones included. The fallback list
    keeps the feature working in that environment instead of rejecting
    Asia/Tehran. Nothing else is accepted.
    """
    text = (value or "").strip()
    if not text or len(text) > 64:
        return False
    try:
        ZoneInfo(text)
        return True
    except (ZoneInfoNotFoundError, ValueError, KeyError, OSError):
        return text in COMMON_TIMEZONES
    except Exception:
        return text in COMMON_TIMEZONES


def _is_loopback_host(host: str) -> bool:
    return (host or "").strip().lower() in LOOPBACK_HOSTS


def _clean_webhook(value) -> str:
    """An empty string disables the webhook; otherwise it must be a real URL.

    Plain ``http`` is accepted only for a loopback host. That exception is
    loopback-justified for the current local build -- a local test receiver on
    127.0.0.1 is a normal thing to point at -- and it dies at launch: the
    hosted build requires ``https``, because a user-supplied ``http://`` URL
    the server posts to is an SSRF primitive.
    """
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) > 500:
        raise PreferenceError("notifications.webhook", "آدرس Webhook بیش از حد بلند است.")
    parsed = urlparse(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise PreferenceError("notifications.webhook", "آدرس Webhook معتبر نیست.")
    if parsed.scheme == "http" and not _is_loopback_host(parsed.hostname or ""):
        raise PreferenceError("notifications.webhook", "در نسخهٔ میزبانی‌شده فقط آدرس https پذیرفته می‌شود.")
    return text


def _require_bool(value, field: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "on"}:
            return True
        if lowered in {"0", "false", "no", "off"}:
            return False
    raise PreferenceError(field, "مقدار باید بله یا خیر باشد.")


def _require_object(value, field: str) -> dict:
    if not isinstance(value, dict):
        raise PreferenceError(field, "این بخش باید یک شیء JSON باشد.")
    return value


def _clean_general(raw: dict) -> dict:
    raw = _require_object(raw, "general")
    out: dict = {}
    if "language" in raw:
        value = str(raw["language"]).strip()
        if value not in LANGUAGES:
            raise PreferenceError("general.language", "زبان رابط پشتیبانی نمی‌شود.")
        out["language"] = value
    if "timezone" in raw:
        value = str(raw["timezone"]).strip()
        if not is_valid_timezone(value):
            raise PreferenceError("general.timezone", "منطقهٔ زمانی شناخته نشد.")
        out["timezone"] = value
    if "date_format" in raw:
        value = str(raw["date_format"]).strip()
        if value not in DATE_FORMATS:
            raise PreferenceError("general.date_format", "قالب تاریخ پشتیبانی نمی‌شود.")
        out["date_format"] = value
    for key in ("resume_last_page", "show_onboarding"):
        if key in raw:
            out[key] = _require_bool(raw[key], f"general.{key}")
    return out


def _clean_translation(raw: dict) -> dict:
    raw = _require_object(raw, "translation")
    out: dict = {}
    if "default_model" in raw:
        value = str(raw["default_model"] or "").strip()
        if value and not is_supported_model(value):
            # No silent fallback: a model the provider does not serve would
            # fail on the first paid chunk of a book.
            raise PreferenceError("translation.default_model", "این مدل پشتیبانی نمی‌شود.")
        out["default_model"] = value
    if "mode" in raw:
        value = str(raw["mode"]).strip()
        if value not in TRANSLATION_MODES:
            raise PreferenceError("translation.mode", "این حالت ترجمه پشتیبانی نمی‌شود.")
        out["mode"] = value
    if "style_preset" in raw:
        value = str(raw["style_preset"] or "").strip()
        if value and value not in get_preset_names():
            raise PreferenceError("translation.style_preset", "این سبک ترجمه شناخته نشد.")
        out["style_preset"] = value
    for key in ("auto_glossary", "preserve_voice"):
        if key in raw:
            out[key] = _require_bool(raw[key], f"translation.{key}")
    for key in ("from_lang", "to_lang"):
        if key in raw:
            value = str(raw[key] or "").strip().upper()
            if value not in LANGUAGE_CODES:
                raise PreferenceError(f"translation.{key}", "این زبان پشتیبانی نمی‌شود.")
            out[key] = value
    return out


def _clean_appearance(raw: dict) -> dict:
    raw = _require_object(raw, "appearance")
    out: dict = {}
    if "theme" in raw:
        value = str(raw["theme"]).strip()
        if value not in APPEARANCE_THEMES:
            raise PreferenceError("appearance.theme", "این تم شناخته نشد.")
        out["theme"] = value
    if "density" in raw:
        value = str(raw["density"]).strip()
        if value not in DENSITIES:
            raise PreferenceError("appearance.density", "این تراکم شناخته نشد.")
        out["density"] = value
    if "animations" in raw:
        out["animations"] = _require_bool(raw["animations"], "appearance.animations")
    return out


def _clean_notifications(raw: dict) -> dict:
    raw = _require_object(raw, "notifications")
    out: dict = {}
    for key in ("email", "in_app"):
        if key in raw:
            out[key] = _require_bool(raw[key], f"notifications.{key}")
    if "webhook" in raw:
        out["webhook"] = _clean_webhook(raw["webhook"])
    if "events" in raw:
        value = raw["events"]
        if not isinstance(value, list):
            raise PreferenceError("notifications.events", "فهرست رویدادها معتبر نیست.")
        unknown = [item for item in value if str(item) not in NOTIFICATION_EVENTS]
        if unknown:
            raise PreferenceError("notifications.events", "رویداد ناشناخته در فهرست.")
        # De-duplicate while keeping the canonical order, so the stored value
        # does not depend on the order the checkboxes were ticked.
        picked = {str(item) for item in value}
        out["events"] = [event for event in NOTIFICATION_EVENTS if event in picked]
    return out


def validate_preferences(patch: dict) -> dict:
    """Allowlist and validate a preference patch; unknown sections are dropped."""
    patch = _require_object(patch, "preferences")
    clean: dict = {}
    for section, cleaner in (
        ("general", _clean_general),
        ("translation", _clean_translation),
        ("appearance", _clean_appearance),
        ("notifications", _clean_notifications),
    ):
        if section in patch:
            clean[section] = cleaner(patch[section])
    if "reading" in patch:
        raw = _require_object(patch["reading"], "reading")
        try:
            # Bookmarks belong to a book and a device; a preferences form has
            # no business rewriting them, so they are not accepted here even
            # though the reader still stores them.
            clean["reading"] = clean_reading_settings(raw, allow_bookmarks=False)
        except ValueError as exc:
            raise PreferenceError("reading", str(exc)) from exc
    return clean


def _stored_rows(user_id: int) -> list[dict]:
    uid = int(user_id)
    if uid == default_user_id():
        return db.fetch_all(
            "SELECT key, value_json, updated_at FROM settings"
            " WHERE (key LIKE 'pref.%' OR key LIKE 'reading_%') AND key NOT LIKE 'u%:%'"
        )
    return db.fetch_all(
        "SELECT key, value_json, updated_at FROM settings WHERE key LIKE ?",
        (f"u{uid}:%",),
    )


def _unprefixed_key(user_id: int, key: str) -> str | None:
    uid = int(user_id)
    if uid == default_user_id():
        if key.startswith("u") and ":" in key:
            return None
        return key
    prefix = f"u{uid}:"
    return key[len(prefix):] if key.startswith(prefix) else None


def get_preferences(user_id: int) -> dict:
    """The effective preferences: defaults, then this user's stored values."""
    values = deepcopy(PREF_DEFAULTS)
    for row in _stored_rows(user_id):
        inner = _unprefixed_key(user_id, row["key"])
        if not inner or not inner.startswith("pref."):
            continue
        parts = inner[len("pref."):].split(".")
        if len(parts) != 2:
            continue
        section, field = parts
        if section not in values or field not in values[section]:
            # A stored key whose field was removed from the contract is
            # ignored rather than resurrected into the response.
            continue
        try:
            values[section][field] = json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            continue
    values["reading"] = reading_settings(user_id)
    return values


def preferences_meta(user_id: int) -> dict:
    """Read-only facts the form needs: real defaults and the option lists.

    ``defaults`` names the value each empty field resolves to, so the UI can
    label an option "default (gpt-5.6-luna)" without hardcoding the model in a
    component. ``options`` keeps the style presets and the zone list on the
    server, where they are already the source of truth.
    """
    updated = None
    for row in _stored_rows(user_id):
        stamp = row.get("updated_at")
        if stamp and (updated is None or stamp > updated):
            updated = stamp
    return {
        "updated_at": updated,
        # The settings page uses this to render the System tab read-only for
        # non-admins. It is the same first-user rule the HTTP handler uses.
        "is_admin": int(user_id) == int(default_user_id()),
        "defaults": {
            "translation.default_model": resolve_default_model(),
        },
        "options": {
            "style_presets": get_preset_names(),
            "timezones": list(COMMON_TIMEZONES),
            "timezone_fallback": not _zoneinfo_available(),
            "notification_events": list(NOTIFICATION_EVENTS),
            "translation_modes": list(TRANSLATION_MODES),
        },
    }


def _zoneinfo_available() -> bool:
    try:
        ZoneInfo("UTC")
        return True
    except Exception:
        return False


def _write(user_id: int, section: str, field: str, value) -> None:
    key = pref_setting_key(user_id, f"{section}.{field}")
    db.execute(
        "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
        (key, json.dumps(value, ensure_ascii=False), _now()),
    )


def save_preferences(user_id: int, patch: dict) -> dict:
    """Validate a patch, store it, and return the merged result."""
    clean = validate_preferences(patch)

    # Cross-field check on the merged state: a webhook with no events is a
    # subscription that can never fire, which looks configured and is not.
    if "notifications" in clean:
        merged = {**get_preferences(user_id)["notifications"], **clean["notifications"]}
        if merged.get("webhook") and not merged.get("events"):
            raise PreferenceError("notifications.events", "با فعال‌بودن Webhook حداقل یک رویداد لازم است.")

    for section, fields in clean.items():
        if section == "reading":
            for field, value in fields.items():
                db.execute(
                    "INSERT INTO settings(key, value_json, updated_at) VALUES (?, ?, ?)"
                    " ON CONFLICT(key) DO UPDATE SET value_json=excluded.value_json, updated_at=excluded.updated_at",
                    (reading_setting_key(user_id, field), json.dumps(value, ensure_ascii=False), _now()),
                )
            continue
        for field, value in fields.items():
            _write(user_id, section, field, value)
    return get_preferences(user_id)


# Position data, not preferences. "Reset settings" that silently loses the
# reader's place in every book -- and their bookmarks -- is a data-loss bug
# wearing a settings label, so the reset deliberately leaves these two alone.
READING_POSITION_KEYS = ("reading_last_location", "reading_bookmarks")


def reset_preferences(user_id: int) -> dict:
    """Drop this user's preference rows and return the defaults."""
    uid = int(user_id)
    for row in _stored_rows(uid):
        inner = _unprefixed_key(uid, row["key"])
        if not inner:
            continue
        if inner.startswith("pref."):
            db.execute("DELETE FROM settings WHERE key=?", (row["key"],))
            continue
        if inner.startswith("reading_") and inner not in READING_POSITION_KEYS:
            db.execute("DELETE FROM settings WHERE key=?", (row["key"],))
    return get_preferences(uid)
