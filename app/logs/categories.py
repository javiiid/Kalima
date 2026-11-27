"""Event categories shared by the writer and the diagnostics reader.

The category is stored on the row (``job_events.category``) so the diagnostics
page can filter and count without re-deriving the same prefix rules in SQL.
Keeping the mapping in one dependency-free module lets ``Database.record_event``
and ``app.logs.service`` agree on what ``api_error`` means.
"""
from __future__ import annotations

from typing import Any

CATEGORIES = ("api", "pdf", "epub", "crash", "retry", "job")


def category_for(event: object, data: Any = None) -> str:
    """Return one of :data:`CATEGORIES` for an event name.

    ``data["category"]`` wins when a caller already knows the stage. Otherwise
    the prefix convention is the contract: new error sites should emit
    ``api_*``, ``pdf_*``, ``epub_*``, ``retry_*`` or ``job_crash``.
    """
    explicit = ""
    if isinstance(data, dict):
        explicit = str(data.get("category") or "").strip().lower()
    if explicit in CATEGORIES:
        return explicit

    name = str(event or "").strip().lower()
    if name.startswith(("api_", "provider_")) or name in {"rate_limited", "rate_limit"}:
        return "api"
    if name.startswith(("pdf_", "render_", "ocr_")):
        return "pdf"
    if name.startswith(("epub_", "chapter_")):
        return "epub"
    if name.startswith("retry_"):
        return "retry"
    if name in {"job_crash", "crash", "unhandled_exception"}:
        return "crash"
    return "job"
