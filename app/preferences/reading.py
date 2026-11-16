"""Reading preferences: one source of truth for the reader and the settings page.

These lived in ``app/web.py`` until the settings page needed to write the same
values. Two writers holding two copies of the defaults is how a reader and a
settings page start disagreeing, so the defaults, the reader, the writer and
the clamps now live here and both callers use them.

Storage is the ``settings`` key/value table. An authenticated user's rows are
namespaced ``u{uid}:reading_*``; the first user (the local build's single
user) keeps the unprefixed keys, so nothing written before this module existed
is lost. ``resolve_user_id``'s fallback is loopback-justified for the current
local build and dies at Phase A.
"""
from __future__ import annotations

import json

from app.library import shelves as book_shelves
from app.storage.database import db

READING_DEFAULTS = {
    "study_night_mode": False,
    "reading_theme": "light",
    # Approved product default: a reader with no stored value opens on the
    # paired view, matching the React reader's own fallback. Only users with no
    # stored `reading_mode` see this value; an existing choice is untouched.
    "reading_mode": "bilingual",
    "reading_font_size": 18,
    "reading_line_height": 1.9,
    "reading_width": 760,
    "reading_direction": "auto",
    "reading_last_location": None,
    "reading_bookmarks": [],
    "reading_glossary": True,
}

# The bounds the reader's and the settings page's sliders are allowed to offer.
# The server re-clamps everything; these only keep a client from asking for a
# value that would be refused.
READING_NUMBER_LIMITS = {
    "reading_font_size": (14, 30),
    "reading_line_height": (1.4, 2.6),
    "reading_width": (560, 1000),
}

READING_ENUMS = {
    "reading_direction": ("auto", "rtl", "ltr"),
    "reading_theme": ("light", "sepia", "night", "contrast"),
    "reading_mode": ("translation", "bilingual", "columns", "original"),
}


def default_user_id() -> int:
    """The user the unprefixed settings rows belong to."""
    return int(book_shelves.resolve_user_id(db))


def reading_settings(user_id: int | None = None) -> dict:
    uid = int(user_id if user_id is not None else default_user_id())
    values = dict(READING_DEFAULTS)
    prefix = "" if uid == default_user_id() else f"u{uid}:"
    if prefix:
        rows = db.fetch_all(
            "SELECT key, value_json FROM settings WHERE key LIKE ? OR key=?",
            (prefix + "reading_%", prefix + "study_night_mode"),
        )
    else:
        rows = db.fetch_all(
            "SELECT key, value_json FROM settings WHERE (key LIKE 'reading_%' OR key='study_night_mode')"
            " AND key NOT LIKE 'u%:%'"
        )
    for row in rows:
        key = row["key"][len(prefix):] if prefix else row["key"]
        try:
            values[key] = json.loads(row["value_json"])
        except (TypeError, json.JSONDecodeError):
            continue
    return values


def reading_setting_key(user_id: int, key: str) -> str:
    uid = int(user_id)
    return key if uid == default_user_id() else f"u{uid}:{key}"


def clean_reading_settings(
    patch: dict,
    *,
    clean_bookmarks=None,
    allow_bookmarks: bool = True,
) -> dict:
    """Allowlist and clamp a reading-settings patch.

    ``PUT /api/reader/settings`` and the settings page both land here, so the
    two can never clamp differently. Unknown keys are dropped rather than
    rejected: that is the contract the reader has always had, and a client
    that knows a newer key must not fail against an older server.

    A number that cannot be read is dropped instead of raising. The old
    handler called ``int()`` on the raw value, so ``{"reading_font_size":
    "abc"}`` raised out of the request handler; dropping it is the same
    forgiveness the rest of this function already applies.

    ``allow_bookmarks`` is False for the settings page: bookmarks belong to a
    book and to a device, and a preferences form has no business rewriting
    them. ``clean_bookmarks`` is the reader service's sanitiser, passed in by
    the caller that owns it so this module stays free of reader imports.
    """
    if not isinstance(patch, dict):
        raise ValueError("reading settings must be an object")
    allowed = set(READING_DEFAULTS)
    clean: dict = {}
    for key, value in patch.items():
        if key not in allowed or key == "reading_bookmarks":
            continue
        if key in READING_NUMBER_LIMITS:
            low, high = READING_NUMBER_LIMITS[key]
            try:
                number = float(value)
            except (TypeError, ValueError):
                continue
            number = min(high, max(low, number))
            clean[key] = int(number) if isinstance(READING_DEFAULTS[key], int) else float(number)
            continue
        if key in READING_ENUMS:
            text = str(value)
            clean[key] = text if text in READING_ENUMS[key] else READING_DEFAULTS[key]
            continue
        if key in {"reading_glossary", "study_night_mode"}:
            clean[key] = bool(value)
            continue
        clean[key] = value
    if allow_bookmarks and clean_bookmarks is not None and "reading_bookmarks" in patch:
        clean["reading_bookmarks"] = clean_bookmarks(patch["reading_bookmarks"])
    return clean
