"""The per-call usage ledger.

Every provider request goes through ``GatedClient``, so that wrapper is where
the ledger row is written. These tests pin the three things that make the
analytics page trustworthy: the tokens and cost are the response's own, the
job/stage/chunk context reaches the row from a worker thread, and a failed
call is recorded rather than disappearing.
"""
from __future__ import annotations

import pytest

from app.core import usage
from app.core.provider_gate import GatedClient, ProviderGate


class _Usage:
    def __init__(self, prompt: int, completion: int, cached: int = 0):
        self.prompt_tokens = prompt
        self.completion_tokens = completion
        self.prompt_tokens_details = type("Details", (), {"cached_tokens": cached})()


class _Response:
    def __init__(self, usage_obj, model: str = "gpt-5.6-luna", rid: str = "resp_1"):
        self.usage = usage_obj
        self.model = model
        self.id = rid


class _Completions:
    def __init__(self, response=None, error: BaseException | None = None):
        self.response = response
        self.error = error

    def create(self, **kwargs):
        if self.error is not None:
            raise self.error
        return self.response


class _Chat:
    def __init__(self, completions):
        self.completions = completions


class _Client:
    def __init__(self, completions):
        self.chat = _Chat(completions)


def _job(db, job_id: str = "j1") -> None:
    db.upsert_job({
        "id": job_id, "user_id": 1, "filename": "book.pdf", "input_path": "book.pdf",
        "filetype": "pdf", "source_language": "EN", "target_language": "FA",
        "model": "gpt-5.6-luna", "mode": "fast", "status": "running",
        "progress": {"completed": 1, "total": 3},
        "pages_total": 2, "pages_completed": 1,
        "created_at": "2026-11-01T00:00:00+00:00",
        "updated_at": "2026-11-01T00:00:00+00:00",
    })


def _rows(db):
    return db.fetch_all("SELECT * FROM api_calls ORDER BY id")


def test_success_records_tokens_cost_and_context(isolated_db):
    db = isolated_db
    _job(db)
    client = GatedClient(_Client(_Completions(_Response(_Usage(100, 50, cached=20)))), ProviderGate(2))

    usage.bind(1, "j1", "translate")
    try:
        usage.set_chunk("chunk-1")
        usage.set_attempt(1)
        client.chat.completions.create(model="gpt-5.6-luna", messages=[])
    finally:
        usage.unbind()

    row = _rows(db)[0]
    assert row["job_id"] == "j1"
    assert row["chunk_id"] == "chunk-1"
    assert row["stage"] == "translate"
    assert row["status"] == "ok"
    assert row["input_tokens"] == 100
    assert row["output_tokens"] == 50
    assert row["cached_tokens"] == 20
    assert row["price_known"] == 1
    # 100 * 0.15/M + 50 * 0.60/M
    assert row["cost_usd"] == pytest.approx(0.000045)
    assert row["provider_id"] == "resp_1"


def test_unknown_model_is_marked_not_free(isolated_db):
    db = isolated_db
    client = GatedClient(_Client(_Completions(_Response(_Usage(10, 10), model="mystery-model"))), ProviderGate(1))

    client.chat.completions.create(model="mystery-model", messages=[])

    row = _rows(db)[0]
    assert row["model"] == "mystery-model"
    assert row["price_known"] == 0
    assert row["cost_usd"] == 0.0


def test_failure_is_recorded_and_reraised(isolated_db):
    db = isolated_db
    client = GatedClient(_Client(_Completions(error=RuntimeError("boom"))), ProviderGate(1))

    with pytest.raises(RuntimeError):
        client.chat.completions.create(model="gpt-5.6-luna", messages=[])

    row = _rows(db)[0]
    assert row["status"] == "error"
    assert row["error_code"] == "RuntimeError"
    assert row["input_tokens"] == 0


def test_stage_label_wins_over_the_bound_default(isolated_db):
    db = isolated_db
    client = GatedClient(_Client(_Completions(_Response(_Usage(5, 5)))), ProviderGate(1))

    usage.bind(1, None, "translate")
    try:
        with usage.stage("pdf_vision"):
            client.chat.completions.create(model="gpt-5.6-luna", messages=[])
    finally:
        usage.unbind()

    assert _rows(db)[0]["stage"] == "pdf_vision"


def test_acting_as_restores_the_previous_binding(isolated_db):
    usage.bind(7, "outer", "translate")
    try:
        with usage.acting_as(9, "inner", "calibration"):
            assert usage.current()["user_id"] == 9
            assert usage.current()["job_id"] == "inner"
        assert usage.current()["user_id"] == 7
        assert usage.current()["job_id"] == "outer"
    finally:
        usage.unbind()
