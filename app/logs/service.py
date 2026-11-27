"""Read side of the durable job-event log.

``job_events`` is written by :meth:`app.storage.database.Database.record_event`
and is the only durable source for the diagnostics page. This module owns the
filters, the response shape and the redaction boundary; the HTTP handler stays a
thin dispatcher.

Two properties matter:

* **User scoping.** Every query joins ``jobs`` and filters on ``j.user_id``
  unless an admin explicitly asks for ``scope=all``. A job id alone is not
  authorization.
* **Redaction.** Provider errors can echo a request URL or an API key. Messages
  and structured data are scrubbed before they leave the server, so a
  diagnostics screen never becomes a credential leak.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta, timezone
from typing import Any

from app.logs.categories import CATEGORIES, category_for

UTC = timezone.utc

_SECRET_PATTERNS = (
    re.compile(r"(?i)\b(sk-[a-z0-9][a-z0-9_\-]{6,})\b"),
    re.compile(r"(?i)\b(bearer\s+)[a-z0-9._\-]{8,}"),
    re.compile(r"(?i)\b(api[_-]?key|authorization|access[_-]?token|refresh[_-]?token|secret)\b"
               r"(\s*[:=]\s*)([^\s,;]+)"),
)

_SECRET_KEYS = {
    "api_key",
    "apikey",
    "authorization",
    "access_token",
    "refresh_token",
    "secret",
    "password",
    "token",
}


def redact_text(value: object) -> str:
    """Scrub obvious credentials from a human-readable message."""
    text = str(value or "")
    text = _SECRET_PATTERNS[0].sub("[redacted]", text)
    text = _SECRET_PATTERNS[1].sub(r"\1[redacted]", text)
    text = _SECRET_PATTERNS[2].sub(r"\1\2[redacted]", text)
    return text


def redact_data(value: Any, depth: int = 0) -> Any:
    """Recursively redact strings in structured event data."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if str(key).strip().lower().replace("-", "_") in _SECRET_KEYS
                else redact_data(item, depth + 1)
            )
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact_data(item, depth + 1) for item in value]
    return value


def parse_since(value: object) -> str | None:
    """Turn ``24h``/``7d``/``30d`` or an ISO stamp into a lower bound.

    An unparsable value is a client error, not a silent "all time": a filter
    that quietly widens is how a page shows the wrong window.
    """
    text = str(value or "").strip()
    if not text:
        return None
    match = re.fullmatch(r"(\d+)\s*([hdm])", text.lower())
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        delta = {"h": timedelta(hours=amount), "d": timedelta(days=amount), "m": timedelta(minutes=amount)}[unit]
        return (datetime.now(UTC) - delta).isoformat()
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("بازهٔ زمانی معتبر نیست.") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def _split(value: object) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def _event_data(row: dict) -> dict:
    raw = row.get("data_json")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}


def normalize_event(row: dict) -> dict:
    """One row in the shape the diagnostics UI consumes."""
    data = _event_data(row)
    category = str(row.get("category") or "").strip().lower()
    if category not in CATEGORIES:
        category = category_for(row.get("event"), data)
    job = None
    if row.get("job_id"):
        job = {
            "id": row.get("job_id"),
            "filename": row.get("job_filename"),
            "status": row.get("job_status"),
            "model": row.get("job_model"),
        }
    return {
        "id": row.get("id"),
        "timestamp": row.get("timestamp"),
        "job_id": row.get("job_id"),
        "job": job,
        "level": str(row.get("level") or "INFO").upper(),
        "category": category,
        "event": row.get("event"),
        "message": redact_text(row.get("message")),
        "recoverable": bool(row.get("recoverable", 1)),
        "data": redact_data(data),
    }


def _where(
    *,
    user_id: int,
    all_users: bool,
    level: object = None,
    category: object = None,
    job_id: object = None,
    since: object = None,
    until: object = None,
    q: object = None,
    before_id: object = None,
) -> tuple[list[str], list[Any]]:
    clauses: list[str] = []
    params: list[Any] = []
    if not all_users:
        clauses.append("j.user_id=?")
        params.append(int(user_id))
    if job_id:
        clauses.append("e.job_id=?")
        params.append(str(job_id))
    levels = [item.upper() for item in _split(level)]
    if levels:
        clauses.append("e.level IN (%s)" % ",".join("?" for _ in levels))
        params.extend(levels)
    categories = [item.lower() for item in _split(category)]
    if categories:
        clauses.append("e.category IN (%s)" % ",".join("?" for _ in categories))
        params.extend(categories)
    since_value = parse_since(since)
    if since_value:
        clauses.append("e.timestamp >= ?")
        params.append(since_value)
    until_value = parse_since(until)
    if until_value:
        clauses.append("e.timestamp <= ?")
        params.append(until_value)
    if q:
        needle = f"%{str(q).strip()}%"
        clauses.append("(e.message LIKE ? OR e.event LIKE ?)")
        params.extend([needle, needle])
    if before_id:
        try:
            clauses.append("e.id < ?")
            params.append(int(before_id))
        except (TypeError, ValueError) as exc:
            raise ValueError("شناسهٔ صفحه‌بندی معتبر نیست.") from exc
    return clauses, params


def list_events(
    db,
    user_id: int,
    *,
    level: object = None,
    category: object = None,
    job_id: object = None,
    since: object = None,
    until: object = None,
    q: object = None,
    limit: object = 100,
    before_id: object = None,
    all_users: bool = False,
) -> dict:
    """Newest-first page of events, plus a cursor for the next page."""
    try:
        size = max(1, min(int(limit or 100), 500))
    except (TypeError, ValueError):
        size = 100
    clauses, params = _where(
        user_id=user_id,
        all_users=all_users,
        level=level,
        category=category,
        job_id=job_id,
        since=since,
        until=until,
        q=q,
        before_id=before_id,
    )
    sql = (
        "SELECT e.*, j.filename AS job_filename, j.status AS job_status,"
        " j.model AS job_model FROM job_events e JOIN jobs j ON j.id=e.job_id"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY e.id DESC LIMIT ?"
    params.append(size + 1)
    rows = db.fetch_all(sql, tuple(params))
    has_more = len(rows) > size
    rows = rows[:size]
    return {
        "items": [normalize_event(row) for row in rows],
        "has_more": has_more,
        "next_before_id": rows[-1]["id"] if has_more and rows else None,
    }


def summary(
    db,
    user_id: int,
    *,
    since: object = "24h",
    job_id: object = None,
    all_users: bool = False,
) -> dict:
    """Counts by level and category for the summary cards."""
    clauses, params = _where(
        user_id=user_id,
        all_users=all_users,
        since=since,
        job_id=job_id,
    )
    sql = (
        "SELECT e.level, e.category, COUNT(*) AS count FROM job_events e"
        " JOIN jobs j ON j.id=e.job_id"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " GROUP BY e.level, e.category"
    rows = db.fetch_all(sql, tuple(params))
    by_level: dict[str, int] = {}
    by_category: dict[str, int] = {}
    total = 0
    for row in rows:
        count = int(row.get("count") or 0)
        total += count
        level = str(row.get("level") or "INFO").upper()
        category = str(row.get("category") or "job").lower()
        by_level[level] = by_level.get(level, 0) + count
        by_category[category] = by_category.get(category, 0) + count
    return {
        "total": total,
        "by_level": by_level,
        "by_category": by_category,
        "since": parse_since(since),
    }


def job_events(
    db,
    job_id: object,
    user_id: int,
    *,
    order: str = "asc",
    all_users: bool = False,
) -> dict | None:
    """One job's events, or ``None`` when the job is not the caller's."""
    job_key = str(job_id or "").strip()
    if not job_key:
        return None
    if all_users:
        job = db.fetch_one("SELECT id FROM jobs WHERE id=?", (job_key,))
    else:
        job = db.fetch_one("SELECT id FROM jobs WHERE id=? AND user_id=?", (job_key, int(user_id)))
    if job is None:
        return None
    direction = "ASC" if str(order).lower() != "desc" else "DESC"
    rows = db.fetch_all(
        "SELECT e.*, j.filename AS job_filename, j.status AS job_status,"
        " j.model AS job_model FROM job_events e JOIN jobs j ON j.id=e.job_id"
        f" WHERE e.job_id=? ORDER BY e.timestamp {direction}, e.id {direction}",
        (job_key,),
    )
    return {"items": [normalize_event(row) for row in rows]}
