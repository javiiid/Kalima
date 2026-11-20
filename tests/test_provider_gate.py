"""The provider budget is one object shared by every job."""
import threading
import time

from app.core import provider_gate
from app.core.exceptions import TranslationStopped
from app.core.provider_gate import GatedClient, ProviderGate


def test_gate_never_exceeds_its_limit():
    gate = ProviderGate(2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def worker():
        nonlocal active, peak
        with gate.slot():
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    threads = [threading.Thread(target=worker) for _ in range(6)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert peak == 2
    assert gate.stats()["in_flight"] == 0


def test_two_simulated_jobs_share_one_budget():
    gate = ProviderGate(2)
    lock = threading.Lock()
    active = 0
    peak = 0

    def request():
        nonlocal active, peak
        with gate.slot():
            with lock:
                active += 1
                peak = max(peak, active)
            time.sleep(0.01)
            with lock:
                active -= 1

    def job():
        threads = [threading.Thread(target=request) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

    jobs = [threading.Thread(target=job) for _ in range(2)]
    for thread in jobs:
        thread.start()
    for thread in jobs:
        thread.join()

    assert peak <= 2


def test_stop_event_aborts_a_waiting_slot():
    gate = ProviderGate(1)
    entered = threading.Event()
    release = threading.Event()

    def holder():
        with gate.slot():
            entered.set()
            release.wait(2)

    holder_thread = threading.Thread(target=holder)
    holder_thread.start()
    assert entered.wait(1)

    stop = threading.Event()
    outcome = []

    def waiter():
        try:
            with gate.slot(stop):
                outcome.append("entered")
        except TranslationStopped:
            outcome.append("stopped")

    waiter_thread = threading.Thread(target=waiter)
    waiter_thread.start()
    stop.set()
    waiter_thread.join(2)
    release.set()
    holder_thread.join(2)

    assert outcome == ["stopped"]


class _FakeCompletions:
    def __init__(self):
        self.calls = 0

    def create(self, **kwargs):
        self.calls += 1
        return {"ok": True}


class _FakeChat:
    def __init__(self):
        self.completions = _FakeCompletions()


class _FakeModels:
    def list(self):
        return ["model-a"]


class _FakeClient:
    def __init__(self):
        self.chat = _FakeChat()
        self.models = _FakeModels()


def test_gated_client_gates_completions_and_passes_through_the_rest():
    raw = _FakeClient()
    gate = ProviderGate(1)
    client = GatedClient(raw, gate)

    assert client.chat.completions.create(model="m") == {"ok": True}
    assert raw.chat.completions.calls == 1
    assert client.models.list() == ["model-a"]
    assert gate.stats()["in_flight"] == 0


def test_shared_rate_limiter_is_one_object(monkeypatch):
    provider_gate.reset_shared_budget()
    monkeypatch.setattr(
        provider_gate,
        "get_translation_config",
        lambda: {"requests_per_minute": 60},
    )
    try:
        first = provider_gate.shared_rate_limiter()
        second = provider_gate.shared_rate_limiter()
        assert first is not None
        assert first is second

        provider_gate.reset_shared_budget()
        third = provider_gate.shared_rate_limiter()
        assert third is not first
    finally:
        provider_gate.reset_shared_budget()


def test_shared_limiter_is_none_when_pacing_is_disabled(monkeypatch):
    provider_gate.reset_shared_budget()
    monkeypatch.setattr(provider_gate, "get_translation_config", lambda: {})
    try:
        assert provider_gate.shared_rate_limiter() is None
    finally:
        provider_gate.reset_shared_budget()


def test_shared_gate_is_one_object(monkeypatch):
    provider_gate.reset_shared_budget()
    monkeypatch.setattr(
        provider_gate,
        "get_translation_config",
        lambda: {"max_concurrency": 3},
    )
    try:
        first = provider_gate.shared_gate()
        second = provider_gate.shared_gate()
        assert first is second
        assert first.limit == 3
    finally:
        provider_gate.reset_shared_budget()
