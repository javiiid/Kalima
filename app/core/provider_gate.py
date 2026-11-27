"""One provider budget shared by every concurrent translation job.

Each job already caps its own worker count. With two jobs that cap multiplies,
so the real number of requests in flight at the provider is
``jobs x max_concurrency``. The gate here is the single place that decides how
many requests may be open across the whole process.

The shared rate limiter is the other half of the same budget: a per-job limiter
would let two jobs each spend the full requests-per-minute allowance and trip
HTTP 429. Both objects are process-wide and rebuilt only when the config value
changes.

Only ``chat.completions.create`` is gated. ``models.list`` and any other
endpoint pass straight through, because they are not the traffic the budget is
about.
"""
from __future__ import annotations

import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

from app.core import usage
from app.core.config import MAX_TRANSLATION_CONCURRENCY, get_translation_config
from app.core.exceptions import TranslationStopped
from app.core.rate_limit import AdaptiveRateLimiter

UTC = timezone.utc


def _failure_status(error: BaseException) -> str:
    """Map an exception to the ledger's ``status`` vocabulary."""
    if isinstance(error, TranslationStopped):
        return "stopped"
    name = type(error).__name__.lower()
    if "ratelimit" in name or "rate_limit" in name or "429" in str(error):
        return "rate_limited"
    if "timeout" in name:
        return "timeout"
    return "error"


class ProviderGate:
    """Cap how many provider requests may be in flight across all jobs."""

    def __init__(self, limit: int = 1) -> None:
        self._limit = max(1, int(limit))
        self._semaphore = threading.BoundedSemaphore(self._limit)
        self._state_lock = threading.Lock()
        self._in_flight = 0

    @property
    def limit(self) -> int:
        return self._limit

    def stats(self) -> dict:
        with self._state_lock:
            return {"limit": self._limit, "in_flight": self._in_flight}

    @contextmanager
    def slot(self, stop_event=None):
        """Hold one provider slot until the block exits.

        Waiting is interruptible: a stop request aborts the wait with
        ``TranslationStopped``, which the pipeline already treats as a safe
        pause rather than a failure.
        """
        while True:
            if self._semaphore.acquire(timeout=0.05):
                break
            if stop_event is not None and stop_event.is_set():
                raise TranslationStopped
        with self._state_lock:
            self._in_flight += 1
        try:
            yield
        finally:
            with self._state_lock:
                self._in_flight -= 1
            self._semaphore.release()


class _GatedCompletions:
    def __init__(self, completions, gate: ProviderGate, stop_event) -> None:
        self._completions = completions
        self._gate = gate
        self._stop_event = stop_event

    def create(self, *args, **kwargs):
        model = kwargs.get("model")
        with self._gate.slot(self._stop_event):
            started_at = datetime.now(UTC)
            started = time.perf_counter()
            try:
                response = self._completions.create(*args, **kwargs)
            except BaseException as error:
                usage.record_failure(
                    model=model,
                    started_at=started_at,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    status=_failure_status(error),
                    error_code=type(error).__name__,
                )
                raise
            usage.record_success(
                model=getattr(response, "model", None) or model,
                started_at=started_at,
                duration_ms=(time.perf_counter() - started) * 1000,
                usage_obj=getattr(response, "usage", None),
                provider_id=getattr(response, "id", None),
            )
            return response

    def __getattr__(self, name):
        return getattr(self._completions, name)


class _GatedChat:
    def __init__(self, chat, gate: ProviderGate, stop_event) -> None:
        self._chat = chat
        self._completions = _GatedCompletions(chat.completions, gate, stop_event)

    @property
    def completions(self):
        return self._completions

    def __getattr__(self, name):
        return getattr(self._chat, name)


class GatedClient:
    """Wrap an OpenAI client so each completion request takes a gate slot."""

    def __init__(self, client, gate: ProviderGate, stop_event=None) -> None:
        self._client = client
        self._gate = gate
        self._chat = _GatedChat(client.chat, gate, stop_event)

    @property
    def chat(self):
        return self._chat

    def __getattr__(self, name):
        return getattr(self._client, name)


_limiter_lock = threading.Lock()
_shared_limiter: AdaptiveRateLimiter | None = None
_shared_signature: tuple | None = None

_gate_lock = threading.Lock()
_shared_gate: ProviderGate | None = None
_shared_gate_limit: int | None = None


def _configured_rpm() -> int | None:
    try:
        configured = get_translation_config().get("requests_per_minute")
    except (OSError, TypeError, ValueError):
        return None
    if configured in (None, "", 0):
        return None
    try:
        rpm = int(configured)
    except (TypeError, ValueError):
        return None
    return rpm if rpm >= 1 else None


def shared_rate_limiter() -> AdaptiveRateLimiter | None:
    """Return the one limiter every web job must share."""
    global _shared_limiter, _shared_signature
    rpm = _configured_rpm()
    if rpm is None:
        return None
    signature = (rpm,)
    with _limiter_lock:
        if _shared_limiter is None or _shared_signature != signature:
            _shared_limiter = AdaptiveRateLimiter(
                max_requests_per_minute=rpm,
                min_requests_per_minute=max(2, rpm // 10),
            )
            _shared_signature = signature
        return _shared_limiter


def _provider_limit() -> int:
    try:
        value = int(get_translation_config().get("max_concurrency", 3))
    except (OSError, TypeError, ValueError):
        value = 3
    return max(1, min(value, MAX_TRANSLATION_CONCURRENCY))


def shared_gate() -> ProviderGate:
    """Return the one gate every web job must share."""
    global _shared_gate, _shared_gate_limit
    limit = _provider_limit()
    with _gate_lock:
        if _shared_gate is None or _shared_gate_limit != limit:
            _shared_gate = ProviderGate(limit)
            _shared_gate_limit = limit
        return _shared_gate


def reset_shared_budget() -> None:
    """Drop the shared objects. Tests use this; the server never does."""
    global _shared_limiter, _shared_signature, _shared_gate, _shared_gate_limit
    with _limiter_lock:
        _shared_limiter = None
        _shared_signature = None
    with _gate_lock:
        _shared_gate = None
        _shared_gate_limit = None
