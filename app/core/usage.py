"""Per-call provider usage ledger.

Every ``chat.completions.create`` goes through ``GatedClient`` in
``app/core/provider_gate.py``. That single choke point is where a call's real
token usage and wall-clock duration are known, so it is where the ledger row is
written -- one row per call, not one aggregate per job.

The caller's identity (user, job, chunk, stage, attempt) is not passed through
every layer of the pipeline. Instead the job runner binds it to the threads it
owns, the same way ``app/core/job_log.py`` binds a log sink: ``bind()`` on the
job thread, and the ``ThreadPoolExecutor`` initializer binds it again on each
worker. A thread with no binding (CLI, a stray helper) is still recorded, with
``user_id=1`` and ``stage="other"`` -- the documented local-only fallback until
hosted accounts replace it.

Recording must never change translation behaviour: every failure here is
swallowed. Analytics is an observer, not a participant.
"""
from __future__ import annotations

import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any

from app.core.pricing import cost_usd

UTC = timezone.utc

#: Stage names the UI groups by. Keep them short and stable: they are stored
#: verbatim and used as filter values.
STAGES = (
    "translate",
    "fallback",
    "pdf_vision",
    "pdf_fix",
    "quality",
    "glossary_proposal",
    "glossary_auto",
    "calibration",
    "other",
)

_state = threading.local()


def _context() -> dict[str, Any]:
    context = getattr(_state, "context", None)
    if context is None:
        context = {
            "user_id": 1,
            "job_id": None,
            "stage": "translate",
            "chunk_id": None,
            "attempt": 1,
            "bound": False,
        }
        _state.context = context
    return context


def bind(user_id: int = 1, job_id: str | None = None, stage: str = "translate") -> None:
    """Bind the current thread to a job. Overwrites any previous binding."""
    _state.context = {
        "user_id": int(user_id or 1),
        "job_id": job_id,
        "stage": stage if stage in STAGES else "other",
        "chunk_id": None,
        "attempt": 1,
        "bound": True,
    }


def unbind() -> None:
    _state.context = None


def current() -> dict[str, Any]:
    return dict(_context())


def is_bound() -> bool:
    return bool(_context().get("bound"))


@contextmanager
def acting_as(user_id: int, job_id: str | None = None, stage_name: str = "translate"):
    """Bind a job identity for the block, restoring whatever was there before.

    Used by subsystems that own their own threads and client (calibration), so
    their calls are attributed to the right account without leaking the binding
    into the caller's thread.
    """
    previous = getattr(_state, "context", None)
    bind(user_id, job_id, stage_name)
    try:
        yield
    finally:
        _state.context = previous


@contextmanager
def stage(name: str):
    """Label the calls made inside the block with a stage."""
    context = _context()
    previous = context["stage"]
    context["stage"] = name if name in STAGES else "other"
    try:
        yield
    finally:
        context["stage"] = previous


@contextmanager
def chunk(chunk_id: Any):
    """Label the calls made inside the block with a chunk id."""
    context = _context()
    previous = context["chunk_id"]
    context["chunk_id"] = None if chunk_id is None else str(chunk_id)
    try:
        yield
    finally:
        context["chunk_id"] = previous


def set_attempt(attempt: int) -> None:
    """Record which retry attempt the next call belongs to (1-based)."""
    try:
        _context()["attempt"] = max(1, int(attempt))
    except (TypeError, ValueError):
        pass


def set_chunk(chunk_id: Any) -> None:
    """Record which chunk the next call belongs to."""
    _context()["chunk_id"] = None if chunk_id is None else str(chunk_id)


def call_stage(name: str, function, *args, **kwargs):
    """Call ``function`` with the ledger labelled ``name``.

    A one-line alternative to indenting a long request expression inside a
    ``with stage(...)`` block: ``usage.call_stage("pdf_vision", client.chat
    .completions.create, **request)``.
    """
    with stage(name):
        return function(*args, **kwargs)


def _token_fields(usage_obj: Any) -> tuple[int, int, int]:
    """Pull prompt/completion/cached tokens out of an SDK usage object."""
    if usage_obj is None:
        return 0, 0, 0

    def number(name: str) -> int:
        try:
            return max(0, int(getattr(usage_obj, name, 0) or 0))
        except (TypeError, ValueError):
            return 0

    prompt = number("prompt_tokens")
    completion = number("completion_tokens")
    details = getattr(usage_obj, "prompt_tokens_details", None)
    cached = 0
    if details is not None:
        try:
            cached = max(0, int(getattr(details, "cached_tokens", 0) or 0))
        except (TypeError, ValueError):
            cached = 0
    return prompt, completion, cached


def _write(
    *,
    model: str | None,
    started_at: datetime,
    duration_ms: float,
    input_tokens: int,
    output_tokens: int,
    cached_tokens: int,
    status: str,
    error_code: str | None,
    provider_id: str | None,
) -> None:
    try:
        import app.storage.database as database_module

        database = database_module.db
        context = _context()
        amount, price_known = cost_usd(model, input_tokens, output_tokens)
        database.record_api_call(
            user_id=context["user_id"],
            job_id=context["job_id"],
            chunk_id=context["chunk_id"],
            model=str(model or "unknown"),
            stage=context["stage"],
            attempt=context["attempt"],
            status=status,
            error_code=error_code,
            started_at=started_at.isoformat(),
            duration_ms=int(max(0.0, duration_ms)),
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cached_tokens=cached_tokens,
            cost_usd=amount,
            price_known=price_known,
            provider_id=provider_id,
        )
    except Exception:
        # Observability must never break a translation.
        pass


def record_success(
    *,
    model: str | None,
    started_at: datetime,
    duration_ms: float,
    usage_obj: Any,
    provider_id: str | None = None,
) -> None:
    input_tokens, output_tokens, cached_tokens = _token_fields(usage_obj)
    _write(
        model=model,
        started_at=started_at,
        duration_ms=duration_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        status="ok",
        error_code=None,
        provider_id=provider_id,
    )


def record_failure(
    *,
    model: str | None,
    started_at: datetime,
    duration_ms: float,
    status: str = "error",
    error_code: str | None = None,
) -> None:
    _write(
        model=model,
        started_at=started_at,
        duration_ms=duration_ms,
        input_tokens=0,
        output_tokens=0,
        cached_tokens=0,
        status=status,
        error_code=error_code,
        provider_id=None,
    )
