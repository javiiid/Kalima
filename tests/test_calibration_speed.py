"""Sample generation must translate units concurrently, not one at a time.

The calibration preview is the first thing a user waits on. It used to run the
selected sample units in a serial ``for`` loop, so a three-sample preview cost
three full model round-trips back to back -- a minute or more on a reasoning
model, which reads as "the app is stuck". These tests pin the fix: the units
now go out together, bounded by the configured concurrency.
"""
from __future__ import annotations

import threading
import time

import pytest

from app.calibration import service as service_module
from app.calibration.service import CalibrationService, sample_workers


class FakeStore:
    """The slice of Store that ``_operation`` touches, backed by a dict."""

    def __init__(self, session):
        self.session = session
        self.operations: dict[str, dict] = {}
        self._lock = threading.Lock()

    def update_operation(self, operation):
        with self._lock:
            self.operations[operation["id"]] = dict(operation)

    def operation(self, identifier):
        with self._lock:
            return dict(self.operations.get(identifier, {}))

    def change(self, identifier, action, revision=None):
        with self._lock:
            action(self.session)
            return self.session


def make_service(store):
    service = CalibrationService.__new__(CalibrationService)
    service.store = store
    service.user_id = 1
    service.execution_lock = threading.RLock()
    return service


def make_session(unit_count=3):
    units = [
        {"id": f"unit-{i}", "source": f"<p>Sentence {i}.</p>", "plain": f"Sentence {i}.",
         "context": "", "chapter": "Chapter", "item": "chapter.xhtml", "pos": i,
         "role": "narrative", "hash": f"hash-{i}"}
        for i in range(unit_count)
    ]
    return {
        "id": "session-1",
        "revision": 0,
        "busy": None,
        "selected": [u["id"] for u in units],
        "document": {"units": units},
        "profile": {"model": "gpt-5.6-luna", "final_model": "gpt-5.6-luna"},
        "results": {},
    }


def make_operation():
    return {"id": "op-1", "session_id": "session-1", "action": "generate",
            "status": "queued", "completed": 0, "total": 0, "error": None,
            "cancel_requested": False}


@pytest.fixture(autouse=True)
def wide_concurrency(monkeypatch):
    """Make worker count independent of whatever config.yaml holds."""
    monkeypatch.setattr(service_module, "get_translation_config", lambda: {"max_concurrency": 12})


def test_sample_units_run_concurrently(monkeypatch):
    session = make_session(3)
    service = make_service(FakeStore(session))
    # A barrier of three only releases if all three units are in flight at
    # once. A serial loop would block on the first unit until the barrier times
    # out, so this fails loudly instead of passing by accident.
    barrier = threading.Barrier(3, timeout=5)
    seen = []

    def fake_translate(session, unit, model, phase="sample"):
        seen.append(unit["id"])
        barrier.wait()
        return {"translations": [{"id": "t0", "text": "x"}], "html": "x"}, f"key-{unit['id']}"

    monkeypatch.setattr(service, "translate_unit", fake_translate)
    operation = make_operation()

    service._operation(operation, session, {"final": True})

    assert operation["status"] == "succeeded"
    assert operation["completed"] == 3
    assert sorted(seen) == ["unit-0", "unit-1", "unit-2"]


def test_preview_finishes_in_about_one_round_trip(monkeypatch):
    delay = 0.2
    session = make_session(3)
    service = make_service(FakeStore(session))

    def slow_translate(session, unit, model, phase="sample"):
        time.sleep(delay)
        return {"translations": [{"id": "t0", "text": "x"}], "html": "x"}, f"key-{unit['id']}"

    monkeypatch.setattr(service, "translate_unit", slow_translate)
    operation = make_operation()

    started = time.monotonic()
    service._operation(operation, session, {"final": True})
    elapsed = time.monotonic() - started

    # Serial would be >= 3 * delay (0.6s). Parallel is ~1 * delay; allow slack
    # for thread startup without ever reaching the serial floor.
    assert elapsed < delay * 2.5, f"preview took {elapsed:.2f}s; looks serial"
    assert operation["completed"] == 3


def test_worker_count_is_bounded_by_units_and_ceiling(monkeypatch):
    monkeypatch.setattr(service_module, "get_translation_config", lambda: {"max_concurrency": 50})
    assert sample_workers(3) == 3
    assert sample_workers(100) == 12

    monkeypatch.setattr(service_module, "get_translation_config", lambda: {"max_concurrency": 1})
    assert sample_workers(3) == 1

    def broken():
        raise OSError("no config")

    monkeypatch.setattr(service_module, "get_translation_config", broken)
    assert sample_workers(3) == 3


def test_a_failing_unit_fails_the_operation(monkeypatch):
    session = make_session(3)
    service = make_service(FakeStore(session))

    def flaky(session, unit, model, phase="sample"):
        if unit["id"] == "unit-1":
            raise RuntimeError("provider exploded")
        return {"translations": [{"id": "t0", "text": "x"}], "html": "x"}, f"key-{unit['id']}"

    monkeypatch.setattr(service, "translate_unit", flaky)
    operation = make_operation()

    service._operation(operation, session, {"final": True})

    assert operation["status"] == "failed"
    assert "provider exploded" in operation["error"]
