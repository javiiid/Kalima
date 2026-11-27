"""Analytics aggregations over the usage ledger.

The dashboard shows nine numbers, four charts and a per-book table. These
tests pin the arithmetic and the scoping: chunks and pages come from the jobs
table, tokens/cost/retries/errors come from ``api_calls``, and one user never
sees another's spend.
"""
from __future__ import annotations

import pytest

from app.analytics import service as analytics


def _job(db, job_id: str, *, user_id: int = 1, filetype: str = "pdf",
         pages_total=None, pages_completed=None, chunks=(2, 4)) -> None:
    db.upsert_job({
        "id": job_id, "user_id": user_id, "filename": f"{job_id}.{filetype}",
        "input_path": f"{job_id}.{filetype}", "filetype": filetype,
        "source_language": "EN", "target_language": "FA",
        "model": "gpt-5.6-luna", "mode": "fast", "status": "completed",
        "progress": {"completed": chunks[0], "total": chunks[1]},
        "pages_total": pages_total, "pages_completed": pages_completed,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
    })


def _call(db, *, user_id=1, job_id="j1", chunk_id="chunk-1", stage="translate",
          attempt=1, status="ok", tokens=(100, 50), cost=0.001,
          price_known=True, started_at="2026-11-01T10:00:00+00:00",
          duration_ms=1000, model="gpt-5.6-luna") -> None:
    db.record_api_call(
        user_id=user_id, job_id=job_id, chunk_id=chunk_id, model=model,
        stage=stage, attempt=attempt, status=status, error_code=None,
        started_at=started_at, duration_ms=duration_ms,
        input_tokens=tokens[0], output_tokens=tokens[1], cached_tokens=0,
        cost_usd=cost, price_known=price_known, provider_id=None,
    )


def test_overview_sums_calls_and_jobs(isolated_db):
    db = isolated_db
    _job(db, "j1", pages_total=2, pages_completed=2, chunks=(4, 4))
    _call(db, chunk_id="chunk-1", tokens=(100, 50), cost=0.001, duration_ms=1000)
    _call(db, chunk_id="chunk-2", tokens=(200, 100), cost=0.002, duration_ms=3000)
    _call(db, chunk_id="chunk-2", attempt=2, status="error", tokens=(0, 0),
          cost=0.0, duration_ms=0)

    result = analytics.overview(db, 1, since="all")
    totals = result["totals"]

    assert totals["requests"] == 3
    assert totals["input_tokens"] == 300
    assert totals["output_tokens"] == 150
    assert totals["cost_usd"] == pytest.approx(0.003)
    assert totals["retries"] == 1
    assert totals["api_errors"] == 1
    assert totals["chunks"] == 4
    assert totals["chunks_total"] == 4
    assert totals["pages"] == 2
    assert totals["pages_total"] == 2
    # chunk-1: 1000ms, chunk-2: 3000 + 0 = 3000ms -> mean 2000ms
    assert totals["avg_chunk_ms"] == 2000


def test_overview_is_scoped_to_the_user(isolated_db):
    db = isolated_db
    _job(db, "mine", user_id=1)
    _job(db, "theirs", user_id=2)
    _call(db, user_id=1, job_id="mine", cost=0.01)
    _call(db, user_id=2, job_id="theirs", cost=0.99)

    mine = analytics.overview(db, 1, since="all")["totals"]
    assert mine["requests"] == 1
    assert mine["cost_usd"] == pytest.approx(0.01)

    everyone = analytics.overview(db, 1, since="all", all_users=True)["totals"]
    assert everyone["requests"] == 2
    assert everyone["cost_usd"] == pytest.approx(1.0)


def test_overview_compares_with_the_previous_window(isolated_db):
    db = isolated_db
    _job(db, "j1")
    _call(db, started_at="2026-11-01T00:00:00+00:00", cost=0.01)
    _call(db, started_at="2026-11-02T00:00:00+00:00", cost=0.03)

    result = analytics.overview(
        db, 1, since="2026-11-02T00:00:00+00:00", until="2026-11-03T00:00:00+00:00",
    )
    assert result["totals"]["cost_usd"] == pytest.approx(0.03)
    assert result["previous"]["cost_usd"] == pytest.approx(0.01)


def test_jobs_rows_carry_per_book_cost_and_sort(isolated_db):
    db = isolated_db
    _job(db, "cheap", chunks=(1, 1))
    _job(db, "dear", chunks=(1, 1))
    _call(db, job_id="cheap", chunk_id="chunk-1", cost=0.01)
    _call(db, job_id="dear", chunk_id="chunk-1", cost=0.50)

    result = analytics.jobs(db, 1, since="all", sort="cost")
    assert [row["job_id"] for row in result["items"]] == ["dear", "cheap"]
    assert result["items"][0]["cost_usd"] == pytest.approx(0.50)


def test_cost_breaks_down_by_model_and_stage(isolated_db):
    db = isolated_db
    _job(db, "j1")
    _call(db, stage="translate", model="gpt-5.6-luna", cost=0.02)
    _call(db, stage="pdf_vision", model="gpt-5.6-terra", cost=0.03, chunk_id=None)

    result = analytics.cost(db, 1, since="all")
    assert result["series"][0]["bucket"] == "2026-11-01"
    assert result["series"][0]["cost_usd"] == pytest.approx(0.05)
    models = {row["model"]: row["cost_usd"] for row in result["by_model"]}
    assert models == {"gpt-5.6-luna": pytest.approx(0.02), "gpt-5.6-terra": pytest.approx(0.03)}
    stages = {row["stage"]: row["cost_usd"] for row in result["by_stage"]}
    assert stages == {"translate": pytest.approx(0.02), "pdf_vision": pytest.approx(0.03)}


def test_unknown_price_calls_are_counted_not_hidden(isolated_db):
    db = isolated_db
    _job(db, "j1")
    _call(db, model="mystery-model", cost=0.0, price_known=False)

    totals = analytics.overview(db, 1, since="all")["totals"]
    assert totals["unknown_price_calls"] == 1
    assert totals["cost_usd"] == 0.0


def test_invalid_since_is_rejected(isolated_db):
    with pytest.raises(ValueError):
        analytics.overview(isolated_db, 1, since="not-a-date")
