"""Phase 2.3: the request counters behind /api/metrics.

Covers the counter object itself (bounded routes, 5xx accounting) and the live
endpoint the 5xx-rate dashboard scrapes.
"""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.core.metrics import Metrics, normalize_path, prometheus_text
from app.storage.database import Database


def test_metrics_counts_status_classes_and_errors():
    metrics = Metrics()
    metrics.record("GET", "/api/jobs", 200, 12.0)
    metrics.record("GET", "/api/jobs", 404, 3.0)
    metrics.record("POST", "/api/jobs", 500, 50.0)
    snapshot = metrics.snapshot()
    assert snapshot["requests_total"] == 3
    assert snapshot["server_errors_total"] == 1
    assert snapshot["by_status"]["2xx"] == 1
    assert snapshot["by_status"]["4xx"] == 1
    assert snapshot["by_status"]["5xx"] == 1
    assert snapshot["by_method"]["POST"] == 1
    assert snapshot["routes"]["/api/jobs"]["5xx"] == 1
    assert snapshot["error_rate"] == round(1 / 3, 4)
    assert snapshot["last_error_at"]
    assert snapshot["avg_latency_ms"] > 0


def test_normalize_path_collapses_ids_and_bounds_length():
    assert normalize_path("/api/jobs/abcdef1234567890/status") == "/api/jobs/:id/status"
    assert normalize_path("/api/library/42/glossary") == "/api/library/:id/glossary"
    assert normalize_path("/") == "/"
    assert normalize_path("/a/b/c/d/e/f/g/h/i/j") == "/a/b/c/d/e/f/g/h..."
    assert normalize_path("/assets/index-9f2b.js") == "/assets/index-9f2b.js"


def test_prometheus_text_exposes_counters():
    metrics = Metrics()
    metrics.record("GET", "/api/jobs", 200, 1.0)
    metrics.record("GET", "/api/jobs", 503, 2.0)
    text = prometheus_text(metrics.snapshot())
    assert 'kalima_http_requests_total{status_class="5xx"} 1' in text
    assert "kalima_http_server_errors_total 1" in text
    assert text.endswith("\n")


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "metrics.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
    web.METRICS.reset()
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


def _get(server, path):
    connection = HTTPConnection(*server.server_address)
    connection.request("GET", path, None, {})
    response = connection.getresponse()
    body = response.read()
    content_type = response.getheader("Content-Type") or ""
    connection.close()
    return response.status, body, content_type


def test_metrics_endpoint_reports_real_traffic(live):
    status, body, _ = _get(live, "/api/version")
    assert status == 200 and json.loads(body)["version"]
    _get(live, "/api/jobs")
    _get(live, "/api/jobs/nope")

    status, body, content_type = _get(live, "/api/metrics")
    assert status == 200 and content_type.startswith("application/json")
    payload = json.loads(body)
    assert payload["requests_total"] >= 3
    assert payload["by_status"]["4xx"] >= 1
    assert payload["routes"]["/api/jobs"]["total"] >= 1


def test_metrics_prometheus_scrape_format(live):
    _get(live, "/api/jobs")
    status, body, content_type = _get(live, "/api/metrics?format=prometheus")
    assert status == 200 and "text/plain" in content_type
    assert b"kalima_http_requests_total" in body
