"""Analytics aggregations over ``api_calls``.

Three shapes, one source of truth:

* ``overview`` -- the nine headline numbers, plus the same numbers for the
  immediately preceding window so the UI can show a delta.
* ``jobs`` -- one row per job, so a user can see which book spent the money.
* ``cost`` -- a time series and a breakdown by model and stage.

Every query is scoped to the caller's ``user_id`` unless an admin explicitly
asks for ``all_users`` -- the same rule the log viewer follows.

Chunks and pages come from ``jobs`` (the pipeline's own progress), not from
``api_calls``: a chunk that hit the translation memory made no call, and a PDF
page can be several chunks.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

UTC = timezone.utc

#: Named windows the UI offers. ``all`` means no lower bound.
WINDOWS = {
    "24h": timedelta(hours=24),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
    "90d": timedelta(days=90),
}

_SORT_KEYS = {
    "cost": lambda item: item["cost_usd"],
    "tokens": lambda item: item["input_tokens"] + item["output_tokens"],
    "duration": lambda item: item["avg_chunk_ms"],
    "recent": lambda item: item["created_at"],
}


def _parse_instant(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("invalid timestamp") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC).isoformat()


def resolve_window(since: str | None, until: str | None) -> tuple[str | None, str | None]:
    """Turn ``24h``/``7d``/ISO into ``(since_iso, until_iso)``."""
    upper = _parse_instant(until) if until else None
    if not since or str(since).lower() == "all":
        return None, upper
    key = str(since).lower()
    if key in WINDOWS:
        anchor = datetime.fromisoformat(upper) if upper else datetime.now(UTC)
        return (anchor - WINDOWS[key]).isoformat(), upper
    return _parse_instant(since), upper


def _previous_window(since: str | None, until: str | None) -> tuple[str | None, str | None]:
    """The same-length window immediately before ``since``."""
    if not since:
        return None, None
    start = datetime.fromisoformat(since)
    end = datetime.fromisoformat(until) if until else datetime.now(UTC)
    span = end - start
    return (start - span).isoformat(), start.isoformat()


def _call_filters(
    user_id: int,
    *,
    since: str | None,
    until: str | None,
    job_id: str | None,
    model: str | None,
    stage: str | None,
    all_users: bool,
    until_exclusive: bool = False,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if not all_users:
        clauses.append("user_id=?")
        params.append(int(user_id))
    if since:
        clauses.append("started_at>=?")
        params.append(since)
    if until:
        clauses.append("started_at<?" if until_exclusive else "started_at<=?")
        params.append(until)
    if job_id:
        clauses.append("job_id=?")
        params.append(job_id)
    if model:
        clauses.append("model=?")
        params.append(model)
    if stage:
        clauses.append("stage=?")
        params.append(stage)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _job_filters(
    user_id: int,
    *,
    since: str | None,
    until: str | None,
    job_id: str | None,
    model: str | None,
    all_users: bool,
    until_exclusive: bool = False,
) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if not all_users:
        clauses.append("user_id=?")
        params.append(int(user_id))
    if since:
        clauses.append("created_at>=?")
        params.append(since)
    if until:
        clauses.append("created_at<?" if until_exclusive else "created_at<=?")
        params.append(until)
    if job_id:
        clauses.append("id=?")
        params.append(job_id)
    if model:
        clauses.append("model=?")
        params.append(model)
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    return where, params


def _call_totals(db, where: str, params: list) -> dict:
    row = db.fetch_one(
        "SELECT COUNT(*) AS calls,"
        " COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens,"
        " COALESCE(SUM(cost_usd),0) AS cost_usd,"
        " COALESCE(SUM(CASE WHEN attempt>1 THEN 1 ELSE 0 END),0) AS retries,"
        " COALESCE(SUM(CASE WHEN status<>'ok' THEN 1 ELSE 0 END),0) AS api_errors,"
        " COALESCE(SUM(CASE WHEN price_known=0 THEN 1 ELSE 0 END),0) AS unknown_price_calls"
        f" FROM api_calls{where}",
        tuple(params),
    ) or {}
    average = db.fetch_one(
        "SELECT AVG(total_ms) AS avg_chunk_ms FROM ("
        " SELECT job_id, chunk_id, SUM(duration_ms) AS total_ms FROM api_calls"
        f"{where}{' AND' if where else ' WHERE'} chunk_id IS NOT NULL"
        " GROUP BY job_id, chunk_id)",
        tuple(params),
    ) or {}
    return {
        "requests": int(row.get("calls") or 0),
        "input_tokens": int(row.get("input_tokens") or 0),
        "output_tokens": int(row.get("output_tokens") or 0),
        "cost_usd": round(float(row.get("cost_usd") or 0.0), 6),
        "retries": int(row.get("retries") or 0),
        "api_errors": int(row.get("api_errors") or 0),
        "unknown_price_calls": int(row.get("unknown_price_calls") or 0),
        "avg_chunk_ms": int(round(float(average.get("avg_chunk_ms") or 0.0))),
    }


def _job_totals(db, where: str, params: list) -> dict:
    row = db.fetch_one(
        "SELECT COUNT(*) AS jobs,"
        " COALESCE(SUM(progress_completed),0) AS chunks_completed,"
        " COALESCE(SUM(progress_total),0) AS chunks_total,"
        " COALESCE(SUM(pages_completed),0) AS pages_completed,"
        " COALESCE(SUM(pages_total),0) AS pages_total"
        f" FROM jobs{where}",
        tuple(params),
    ) or {}
    return {
        "jobs": int(row.get("jobs") or 0),
        "chunks": int(row.get("chunks_completed") or 0),
        "chunks_total": int(row.get("chunks_total") or 0),
        "pages": int(row.get("pages_completed") or 0),
        "pages_total": int(row.get("pages_total") or 0),
    }


def overview(
    db,
    user_id: int,
    *,
    since: str | None = "30d",
    until: str | None = None,
    job_id: str | None = None,
    model: str | None = None,
    stage: str | None = None,
    all_users: bool = False,
) -> dict:
    """The nine headline metrics for a window, plus the previous window."""
    start, end = resolve_window(since, until)
    where, params = _call_filters(
        user_id, since=start, until=end, job_id=job_id, model=model,
        stage=stage, all_users=all_users,
    )
    job_where, job_params = _job_filters(
        user_id, since=start, until=end, job_id=job_id, model=model,
        all_users=all_users,
    )
    totals = _call_totals(db, where, params)
    jobs = _job_totals(db, job_where, job_params)
    totals.update(jobs)

    previous = None
    prev_start, prev_end = _previous_window(start, end)
    if prev_start:
        prev_where, prev_params = _call_filters(
            user_id, since=prev_start, until=prev_end, job_id=job_id,
            model=model, stage=stage, all_users=all_users, until_exclusive=True,
        )
        prev_job_where, prev_job_params = _job_filters(
            user_id, since=prev_start, until=prev_end, job_id=job_id,
            model=model, all_users=all_users, until_exclusive=True,
        )
        previous = _call_totals(db, prev_where, prev_params)
        previous.update(_job_totals(db, prev_job_where, prev_job_params))

    return {
        "range": {"since": start, "until": end},
        "totals": totals,
        "previous": previous,
    }


def jobs(
    db,
    user_id: int,
    *,
    since: str | None = "30d",
    until: str | None = None,
    job_id: str | None = None,
    model: str | None = None,
    all_users: bool = False,
    sort: str = "cost",
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """One aggregated row per job, most expensive first by default."""
    start, end = resolve_window(since, until)
    job_where, job_params = _job_filters(
        user_id, since=start, until=end, job_id=job_id, model=model,
        all_users=all_users,
    )
    try:
        limit = max(1, min(int(limit), 200))
    except (TypeError, ValueError):
        limit = 50
    try:
        offset = max(0, int(offset))
    except (TypeError, ValueError):
        offset = 0

    rows = db.fetch_all(
        "SELECT id AS job_id, filename, model, status, filetype,"
        " progress_completed, progress_total, pages_completed, pages_total, created_at"
        f" FROM jobs{job_where}",
        tuple(job_params),
    ) or []
    if not rows:
        return {"items": [], "total": 0, "limit": limit, "offset": offset}

    call_where, call_params = _call_filters(
        user_id, since=start, until=end, job_id=job_id, model=model,
        stage=None, all_users=all_users,
    )
    aggregates = {
        row["job_id"]: row
        for row in (db.fetch_all(
            "SELECT job_id, COUNT(*) AS calls,"
            " COALESCE(SUM(input_tokens),0) AS input_tokens,"
            " COALESCE(SUM(output_tokens),0) AS output_tokens,"
            " COALESCE(SUM(cost_usd),0) AS cost_usd,"
            " COALESCE(SUM(CASE WHEN attempt>1 THEN 1 ELSE 0 END),0) AS retries,"
            " COALESCE(SUM(CASE WHEN status<>'ok' THEN 1 ELSE 0 END),0) AS api_errors"
            f" FROM api_calls{call_where} GROUP BY job_id",
            tuple(call_params),
        ) or [])
    }
    chunk_totals = {
        row["job_id"]: row["total_ms"]
        for row in (db.fetch_all(
            "SELECT job_id, AVG(total_ms) AS total_ms FROM ("
            " SELECT job_id, chunk_id, SUM(duration_ms) AS total_ms FROM api_calls"
            f"{call_where}{' AND' if call_where else ' WHERE'} chunk_id IS NOT NULL"
            " GROUP BY job_id, chunk_id) GROUP BY job_id",
            tuple(call_params),
        ) or [])
    }

    items = []
    for row in rows:
        stats = aggregates.get(row["job_id"]) or {}
        items.append({
            "job_id": row["job_id"],
            "filename": row["filename"],
            "model": row["model"],
            "status": row["status"],
            "filetype": row["filetype"],
            "chunks": int(row["progress_completed"] or 0),
            "chunks_total": int(row["progress_total"] or 0),
            "pages": row["pages_completed"],
            "pages_total": row["pages_total"],
            "created_at": row["created_at"],
            "requests": int(stats.get("calls") or 0),
            "input_tokens": int(stats.get("input_tokens") or 0),
            "output_tokens": int(stats.get("output_tokens") or 0),
            "cost_usd": round(float(stats.get("cost_usd") or 0.0), 6),
            "retries": int(stats.get("retries") or 0),
            "api_errors": int(stats.get("api_errors") or 0),
            "avg_chunk_ms": int(round(float(chunk_totals.get(row["job_id"]) or 0.0))),
        })

    key = _SORT_KEYS.get(sort, _SORT_KEYS["cost"])
    items.sort(key=key, reverse=True)
    total = len(items)
    return {"items": items[offset:offset + limit], "total": total, "limit": limit, "offset": offset}


def cost(
    db,
    user_id: int,
    *,
    since: str | None = "30d",
    until: str | None = None,
    job_id: str | None = None,
    model: str | None = None,
    stage: str | None = None,
    all_users: bool = False,
    bucket: str = "day",
) -> dict:
    """Cost/token series plus breakdowns by model and stage."""
    start, end = resolve_window(since, until)
    where, params = _call_filters(
        user_id, since=start, until=end, job_id=job_id, model=model,
        stage=stage, all_users=all_users,
    )
    if bucket == "week":
        key = "strftime('%Y-%W', started_at)"
    elif bucket == "model":
        key = "model"
    elif bucket == "stage":
        key = "stage"
    else:
        key = "substr(started_at, 1, 10)"

    series = db.fetch_all(
        f"SELECT {key} AS bucket, COUNT(*) AS calls,"
        " COALESCE(SUM(cost_usd),0) AS cost_usd,"
        " COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens"
        f" FROM api_calls{where} GROUP BY bucket ORDER BY bucket",
        tuple(params),
    ) or []
    by_model = db.fetch_all(
        "SELECT model, COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost_usd,"
        " COALESCE(SUM(input_tokens),0) AS input_tokens,"
        " COALESCE(SUM(output_tokens),0) AS output_tokens"
        f" FROM api_calls{where} GROUP BY model ORDER BY cost_usd DESC",
        tuple(params),
    ) or []
    by_stage = db.fetch_all(
        "SELECT stage, COUNT(*) AS calls, COALESCE(SUM(cost_usd),0) AS cost_usd"
        f" FROM api_calls{where} GROUP BY stage ORDER BY cost_usd DESC",
        tuple(params),
    ) or []

    return {
        "range": {"since": start, "until": end, "bucket": bucket},
        "series": [
            {
                "bucket": row["bucket"],
                "calls": int(row["calls"] or 0),
                "cost_usd": round(float(row["cost_usd"] or 0.0), 6),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
            }
            for row in series
        ],
        "by_model": [
            {
                "model": row["model"],
                "calls": int(row["calls"] or 0),
                "cost_usd": round(float(row["cost_usd"] or 0.0), 6),
                "input_tokens": int(row["input_tokens"] or 0),
                "output_tokens": int(row["output_tokens"] or 0),
            }
            for row in by_model
        ],
        "by_stage": [
            {
                "stage": row["stage"],
                "calls": int(row["calls"] or 0),
                "cost_usd": round(float(row["cost_usd"] or 0.0), 6),
            }
            for row in by_stage
        ],
    }
