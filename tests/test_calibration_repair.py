"""Line breaks stay inside a slot, and one bad answer does not kill the book."""
from __future__ import annotations

import threading

import pytest

from app.calibration import service as service_module
from app.calibration.engine import ModelOutputError, slots_for, validate_result
from app.calibration.service import CalibrationService


class FakeStore:
    def cached(self, key):
        return None

    def cache(self, key, result):
        pass


def make_service():
    service = CalibrationService.__new__(CalibrationService)
    service.store = FakeStore()
    service.user_id = 1
    service._client_lock = threading.Lock()
    service._client_cache = None
    return service


def make_session():
    return {
        "profile": {
            "tone": "modern", "from_lang": "EN", "to_lang": "FA",
            "model": "gpt-5.6-luna", "final_model": "gpt-5.6-luna",
            "fallback_model": None, "glossary": [], "instructions": "",
            "provider": "provider-hash", "version": "calibration-1",
        },
        "results": {},
    }


def make_unit():
    return {"id": "unit-1", "source": "<p>Hello world.</p>", "plain": "Hello world.", "context": ""}


def test_line_breaks_stay_inside_one_slot():
    source = "<p>Line one<br/>Line two<br />Line three</p>"
    parts, slots = slots_for(source)

    assert len(slots) == 1
    assert slots[0]["text"] == "Line one\nLine two\nLine three"

    compiled = {"parts": parts, "slots": slots, "terms": []}
    result = validate_result(compiled, {"translations": [{"id": "t0", "text": "یک\nدو\nسه"}]})
    assert result["html"] == "<p>یک<br/>دو<br/>سه</p>"


def test_model_br_is_normalized_to_a_line_break():
    compiled = {
        "parts": [{"id": "t0", "leading": "", "trailing": ""}],
        "slots": [{"id": "t0", "text": "a\nb"}],
        "terms": [],
    }
    result = validate_result(compiled, {"translations": [{"id": "t0", "text": "x<br/>y"}]})

    assert result["html"] == "x<br/>y"


def test_slot_mismatch_raises_a_repairable_error():
    compiled = {
        "parts": [],
        "slots": [{"id": "t0", "text": "a"}, {"id": "t1", "text": "b"}],
        "terms": [],
    }
    with pytest.raises(ModelOutputError):
        validate_result(compiled, {"translations": [{"id": "t0", "text": "x"}]})


def test_translate_unit_repairs_one_bad_answer(monkeypatch):
    service = make_service()
    session = make_session()
    requests = []

    def fake_call(session, request, phase):
        requests.append(request)
        if len(requests) == 1:
            return {"translations": []}
        return {"translations": [{"id": "t0", "text": "سلام دنیا."}]}

    monkeypatch.setattr(service, "call", fake_call)
    result, _ = service.translate_unit(session, make_unit(), "gpt-5.6-luna", "full")

    assert len(requests) == 2
    assert "previous answer was rejected" in requests[1]["messages"][-1]["content"]
    assert result["translations"][0]["text"] == "سلام دنیا."


def test_translate_unit_gives_up_after_one_repair(monkeypatch):
    service = make_service()
    session = make_session()
    calls = []

    def always_bad(session, request, phase):
        calls.append(request)
        return {"translations": []}

    monkeypatch.setattr(service, "call", always_bad)
    with pytest.raises(ModelOutputError):
        service.translate_unit(session, make_unit(), "gpt-5.6-luna", "full")

    assert len(calls) == 2


def test_http_client_is_reused(monkeypatch):
    service = make_service()
    created = []

    def factory():
        created.append(object())
        return created[-1]

    service.client_factory = factory
    monkeypatch.setattr(service_module, "provider_identity", lambda: "provider-a")

    assert service._client_for() is service._client_for()
    assert len(created) == 1

    monkeypatch.setattr(service_module, "provider_identity", lambda: "provider-b")
    service._client_for()
    assert len(created) == 2
