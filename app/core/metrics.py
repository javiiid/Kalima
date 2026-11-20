"""In-process request counters behind ``/api/metrics``.

The roadmap's Phase 2 asks for a 5xx-rate dashboard and error alerting. A
single-process ``ThreadingHTTPServer`` only needs atomic counters, so this is
deliberately tiny and dependency-free: no metric pipeline, just enough to
answer "is the server returning errors, and how much?" without grepping logs.

Counters are intentionally bounded: dynamic path segments (job ids, numeric
primary keys) collapse to ``:id`` so a long-lived process cannot grow one
key per request.
"""

from __future__ import annotations

import re
import threading
import time
from datetime import datetime, timezone
from typing import Any

UTC = timezone.utc

#: A segment that is an id: all digits, a long hex blob, or a uuid-ish token.
_ID_SEGMENT = re.compile(r"^(?:\d+|[0-9a-fA-F]{16,}|[0-9a-fA-F-]{20,})$")
_STATUS_CLASSES = ("1xx", "2xx", "3xx", "4xx", "5xx")


def normalize_path(path: str, *, limit: int = 8) -> str:
    """Collapse ids out of a route so the counter map stays bounded."""
    segments = [segment for segment in (path or "/").split("/") if segment]
    if not segments:
        return "/"
    head = "/".join(":id" if _ID_SEGMENT.match(segment) else segment for segment in segments[:limit])
    return "/" + head + ("..." if len(segments) > limit else "")


class Metrics:
    """Thread-safe request counters. One instance per process."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.reset()

    def reset(self) -> None:
        with self._lock:
            self._started = time.time()
            self.total = 0
            self.in_flight = 0
            self.server_errors = 0
            self.total_duration_ms = 0.0
            self.last_error_at: str | None = None
            self.by_status: dict[str, int] = {klass: 0 for klass in _STATUS_CLASSES}
            self.by_method: dict[str, int] = {}
            self.by_route: dict[str, dict[str, int]] = {}

    def record(self, method: str, path: str, status: int, duration_ms: float = 0.0) -> None:
        klass = f"{int(status) // 100}xx"
        route = normalize_path(path)
        with self._lock:
            self.total += 1
            self.total_duration_ms += max(0.0, float(duration_ms))
            self.by_status[klass] = self.by_status.get(klass, 0) + 1
            verb = (method or "?").upper()
            self.by_method[verb] = self.by_method.get(verb, 0) + 1
            entry = self.by_route.setdefault(route, {"total": 0, "5xx": 0})
            entry["total"] += 1
            if klass == "5xx":
                entry["5xx"] += 1
                self.server_errors += 1
                self.last_error_at = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            total = self.total
            errors = self.server_errors
            return {
                "uptime_seconds": round(max(0.0, time.time() - self._started), 1),
                "requests_total": total,
                "requests_in_flight": self.in_flight,
                "server_errors_total": errors,
                "error_rate": round(errors / total, 4) if total else 0.0,
                "avg_latency_ms": round(self.total_duration_ms / total, 2) if total else 0.0,
                "by_status": dict(self.by_status),
                "by_method": dict(self.by_method),
                "routes": {route: dict(counts) for route, counts in sorted(self.by_route.items())},
                "last_error_at": self.last_error_at,
            }


def prometheus_text(
    snapshot: dict[str, Any], job_stats: dict[str, Any] | None = None
) -> str:
    """Render a snapshot in the Prometheus text exposition format.

    ``job_stats`` is the scheduler snapshot (slots, queued, running). It stays
    optional so request counters can be rendered on their own, but when the
    server passes it the scrape also describes queue pressure.
    """
    lines = [
        "# HELP kalima_http_requests_total Total HTTP requests handled.",
        "# TYPE kalima_http_requests_total counter",
    ]
    for klass, count in (snapshot.get("by_status") or {}).items():
        lines.append(f'kalima_http_requests_total{{status_class="{klass}"}} {count}')
    for verb, count in sorted((snapshot.get("by_method") or {}).items()):
        lines.append(f'kalima_http_requests_total{{method="{verb}"}} {count}')
    lines += [
        "# HELP kalima_http_server_errors_total Responses with a 5xx status.",
        "# TYPE kalima_http_server_errors_total counter",
        f'kalima_http_server_errors_total {snapshot.get("server_errors_total", 0)}',
        "# HELP kalima_process_uptime_seconds Seconds since the process started.",
        "# TYPE kalima_process_uptime_seconds gauge",
        f'kalima_process_uptime_seconds {snapshot.get("uptime_seconds", 0)}',
    ]
    if job_stats is not None:
        lines += [
            "# HELP kalima_job_slots Total translation job slots.",
            "# TYPE kalima_job_slots gauge",
            f'kalima_job_slots {job_stats.get("slots", 0)}',
            "# HELP kalima_jobs_running Jobs currently occupying a slot.",
            "# TYPE kalima_jobs_running gauge",
            f'kalima_jobs_running {job_stats.get("running", 0)}',
            "# HELP kalima_jobs_queued Jobs waiting for a slot.",
            "# TYPE kalima_jobs_queued gauge",
            f'kalima_jobs_queued {job_stats.get("queued", 0)}',
        ]
    return "\n".join(lines) + "\n"


#: Process-wide counters; the handler records into this on every response.
METRICS = Metrics()
