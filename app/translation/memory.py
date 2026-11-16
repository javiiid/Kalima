# ============================================================
# Translation memory read/write for the engine
# ============================================================
"""
Profile-aware exact-match translation memory used by ``translate_chunk``.

Before any provider API call the engine looks the whole chunk up in
``translation_memory``; on a hit the stored translation is served with zero
API cost (repeated sentences, headings, formulas, boilerplate, or a full
re-run of the same book). After every successful chunk translation the pair
is stored back, so each book teaches the memory for the next one.

Matching is deliberately EXACT on the raw chunk text: the chunker is
deterministic, so the same book always produces byte-identical chunks, and
exactness is what makes a no-review auto-apply safe. Fuzzy matching would
need a product decision (thresholds, review UI) and is out of scope.

A hit also requires the same *translation profile*: the same source text
translated with a different style preset, prompt, glossary or model is a
different translation and must not be reused. The profile is collapsed into
``translation_fingerprint`` (``v1:<sha256>``), which is the only column the
lookup and the upsert key on. Rows written before the fingerprint existed
carry a ``legacy:<id>`` fingerprint and are never served, because nobody can
say which profile produced them.

This module imports nothing from ``app`` so ``translator.py`` can use it
without import cycles. ``db`` is any object with ``fetch_one``/``execute``
like ``app.storage.database.Database`` (which is thread-safe).
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

# Bump when the payload shape below changes: old fingerprints stop matching
# and the memory simply re-learns instead of serving a wrong profile.
FINGERPRINT_VERSION = 1
FINGERPRINT_PREFIX = "v1:"
MANUAL_PREFIX = "manual:"
LEGACY_PREFIX = "legacy:"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _canonical(value: Any) -> str:
    """Stable JSON so equal profiles always hash to the same string."""
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sorted_terms(terms: Any) -> list[dict]:
    """Normalise glossary terms into a deterministic, hashable list."""
    cleaned = []
    for term in terms or []:
        if not isinstance(term, dict):
            continue
        cleaned.append({
            "source_term": str(term.get("source_term", "")),
            "target_term": str(term.get("target_term", "")),
            "notes": str(term.get("notes", "")),
            "kind": str(term.get("kind", "")),
        })
    return sorted(
        cleaned,
        key=lambda item: (
            item["source_term"].casefold(),
            item["target_term"],
            item["notes"],
            item["kind"],
        ),
    )


def build_profile(
    *,
    model: str,
    filetype: str = "",
    prompt: str = "",
    prompt_version: int = FINGERPRINT_VERSION,
    style_key: str = "",
    style_preset: Any = None,
    glossary_terms: Any = None,
    glossary_version: int = 0,
) -> dict:
    """Describe everything that can change the output for the same text.

    The model that actually produced the translation is part of the profile,
    so a chunk rescued by a fallback model is never served as if the primary
    model had written it. ``fallback_model`` is deliberately not included:
    merely *configuring* a fallback must not invalidate rows the primary model
    produced.
    """
    return {
        "version": FINGERPRINT_VERSION,
        "model": str(model or ""),
        "filetype": str(filetype or "").lower().lstrip("."),
        "prompt_version": int(prompt_version or 0),
        "prompt_hash": _sha256(str(prompt or "")),
        "style_key": str(style_key or ""),
        "style_hash": _sha256(_canonical(style_preset or {})),
        "glossary_version": int(glossary_version or 0),
        "glossary_hash": _sha256(_canonical(_sorted_terms(glossary_terms))),
    }


def build_fingerprint(
    user_id: int,
    source_text: str,
    from_lang: str,
    to_lang: str,
    profile: dict | None,
) -> str:
    """Collapse owner, text, language pair and profile into one opaque key."""
    payload = {
        "user_id": int(user_id or 1),
        "source_text": str(source_text),
        "source_language": str(from_lang),
        "target_language": str(to_lang),
        "profile": profile or {},
    }
    return FINGERPRINT_PREFIX + _sha256(_canonical(payload))


def manual_fingerprint(
    user_id: int,
    source_text: str,
    from_lang: str,
    to_lang: str,
) -> str:
    """Key for hand-entered/imported rows, which carry no translation profile.

    They stay visible and editable in the memory UI but never match an engine
    lookup: a human pair was written for some unknown style, so serving it for
    a specific profile would be exactly the collision this module prevents.
    """
    payload = {
        "user_id": int(user_id or 1),
        "source_text": str(source_text),
        "source_language": str(from_lang),
        "target_language": str(to_lang),
    }
    return MANUAL_PREFIX + _sha256(_canonical(payload))


def lookup(
    db: Any,
    source_text: str,
    from_lang: str,
    to_lang: str,
    *,
    profile: dict | None,
    user_id: int = 1,
) -> str | None:
    """Return the stored translation for an exact profile match, else ``None``.

    A hit refreshes ``last_used_at`` so the memory UI (ORDER BY last_used_at)
    surfaces what the engine actually reuses. Never raises: a memory failure
    must degrade to a normal API call, never break the job.

    ``user_id`` scopes both the read and the refresh so one account can never
    be served another account's translation.
    """
    uid = int(user_id or 1)
    fingerprint = build_fingerprint(uid, source_text, from_lang, to_lang, profile)
    try:
        row = db.fetch_one(
            "SELECT translated_text FROM translation_memory"
            " WHERE user_id=? AND translation_fingerprint=?",
            (uid, fingerprint),
        )
    except Exception:
        return None
    if row is None or not row.get("translated_text"):
        return None
    try:
        db.execute(
            "UPDATE translation_memory SET last_used_at=?"
            " WHERE user_id=? AND translation_fingerprint=?",
            (_now(), uid, fingerprint),
        )
    except Exception:
        pass
    return row["translated_text"]


def store(
    db: Any,
    source_text: str,
    translated_text: str,
    from_lang: str,
    to_lang: str,
    *,
    profile: dict | None,
    source: str = "auto",
    user_id: int = 1,
) -> None:
    """Remember one engine-produced pair. Upsert; never raises.

    Engine rows are marked ``source='auto'`` (confidence 1.0: they came from
    the same pipeline that would translate them again) so they stay
    distinguishable from hand-entered (``manual``) and bulk (``import``)
    rows in the memory UI. Empty inputs are refused: they can never match.

    The upsert keys on ``UNIQUE(user_id, translation_fingerprint)``, so the
    same text under two profiles becomes two rows and neither can overwrite
    the other.
    """
    if not source_text or not translated_text:
        return
    uid = int(user_id or 1)
    fingerprint = build_fingerprint(uid, source_text, from_lang, to_lang, profile)
    profile_json = _canonical(profile or {})
    profile_version = int((profile or {}).get("version") or 0)
    try:
        db.execute(
            "INSERT INTO translation_memory(user_id, source_text, translated_text,"
            " source_language, target_language, source, confidence, last_used_at,"
            " translation_fingerprint, profile_version, profile_json)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            " ON CONFLICT(user_id, translation_fingerprint)"
            " DO UPDATE SET translated_text=excluded.translated_text,"
            " confidence=excluded.confidence, last_used_at=excluded.last_used_at,"
            " profile_version=excluded.profile_version,"
            " profile_json=excluded.profile_json",
            (uid, source_text, translated_text, from_lang, to_lang, source, 1.0,
             _now(), fingerprint, profile_version, profile_json),
        )
    except Exception:
        pass
