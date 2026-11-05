"""The quote is cached between UI polls, but never goes stale."""
from __future__ import annotations

import threading

import pytest

from app.calibration import service as service_module
from app.calibration.service import CalibrationService


class FakeStore:
    def __init__(self):
        self.row = {
            "sample_spent": 0, "full_spent": 0, "sample_reserved": 0,
            "full_reserved": 0, "sample_calls": 0, "cost_spent": 0,
            "cost_reserved": 0,
        }

    def budget(self, identifier):
        return dict(self.row)


def make_service():
    svc = CalibrationService.__new__(CalibrationService)
    svc.store = FakeStore()
    svc.user_id = 1
    svc._quote_cache = {}
    svc._quote_lock = threading.Lock()
    return svc


def make_session(identifier="session-1", units=60):
    document_units = [
        {"id": f"chunk-{i}", "source": f"<p>Paragraph number {i} with some words.</p>",
         "plain": f"Paragraph number {i} with some words.", "context": "",
         "chapter": "Chapter", "item": "chapter.xhtml", "pos": i,
         "role": "narrative", "hash": f"hash-{i}"}
        for i in range(units)
    ]
    return {
        "id": identifier,
        "profile": {
            "tone": "modern", "from_lang": "EN", "to_lang": "FA",
            "model": "gpt-4o-mini", "final_model": "gpt-4o-mini",
            "fallback_model": None, "glossary": [], "instructions": "",
            "provider": "provider-hash", "version": "calibration-1",
        },
        "document": {"prepared_hash": "prepared-hash", "units": document_units},
        "selected": ["chunk-0", "chunk-1", "chunk-2"],
        "outputs": ["epub"],
        "approvals": {},
        "results": {},
        "budget_id": "budget-1",
    }


@pytest.fixture
def compiled(monkeypatch):
    calls = []
    original = service_module.compile_request

    def counting(unit, profile, model):
        calls.append(unit["id"])
        return original(unit, profile, model)

    monkeypatch.setattr(service_module, "compile_request", counting)
    return calls


def test_repeated_quote_reuses_the_cached_result(compiled):
    svc = make_service()
    session = make_session()

    first = svc.quote(session)
    calls_after_first = len(compiled)
    second = svc.quote(session)

    assert second is first
    assert len(compiled) == calls_after_first
    assert calls_after_first > 0


def test_new_result_invalidates_the_quote(compiled):
    svc = make_service()
    session = make_session()

    first = svc.quote(session)
    session["results"]["some-key"] = {"translations": []}
    second = svc.quote(session)

    assert second is not first
    assert second["reusable_units"] == first["reusable_units"]


def test_budget_counter_change_invalidates_the_quote(compiled):
    svc = make_service()
    session = make_session()

    first = svc.quote(session)
    svc.store.row["sample_spent"] = 1234
    second = svc.quote(session)

    assert second is not first
    assert second["sample_spent_tokens"] == 1234
    assert second["id"] != first["id"] or second["spent_tokens"] != first["spent_tokens"]


def test_sessions_do_not_share_cached_quotes(compiled):
    svc = make_service()
    first_session = make_session("session-a")
    second_session = make_session("session-b")

    first = svc.quote(first_session)
    second = svc.quote(second_session)

    assert first is not second
    assert first["id"] == second["id"]
