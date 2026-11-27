"""Diagnostics log service and HTTP routes.

The diagnostics page is only useful if three things hold: a user never sees
another user's events, an admin can deliberately widen the scope, and a
provider error cannot leak a credential through the log viewer. These tests
exercise the service directly and the real ``Handler`` with two sessions.
"""
from __future__ import annotations

import json
import sqlite3
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.auth import service as auth
from app.logs import service as logs
from app.storage.database import DB_NAME, Database


def _job(database, job_id: str, user_id: int = 1) -> None:
    database.execute(
        "INSERT INTO jobs(id, user_id, filename, input_path, filetype, source_language,"
        " target_language, model, mode, status, created_at, updated_at)"
        " VALUES (?, ?, 'book.epub', 'book.epub', 'epub', 'EN', 'FA', 'gpt-5.6-luna',"
        " 'fast', 'failed', '2026-01-01', '2026-01-01')",
        (job_id, user_id),
    )


def _event(
    database,
    job_id: str,
    *,
    level: str = "ERROR",
    category: str = "job",
    event: str = "job_failed",
    message: str = "boom",
    timestamp: str = "2026-01-01T00:00:00+00:00",
    data: dict | None = None,
) -> None:
    database.execute(
        "INSERT INTO job_events(job_id, timestamp, level, category, event, message,"
        " recoverable, data_json) VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
        (
            job_id,
            timestamp,
            level,
            category,
            event,
            message,
            json.dumps(data) if data is not None else None,
        ),
    )


def test_record_event_derives_category_from_the_event_name(tmp_path):
    database = Database(tmp_path / DB_NAME)
    _job(database, "job-1")
    database.record_event("job-1", "ERROR", "pdf_render_failed", "Ghostscript unavailable")
    database.record_event("job-1", "ERROR", "epub_parse_failed", "bad zip")
    database.record_event("job-1", "WARNING", "retry_scheduled", "again")
    database.record_event("job-1", "ERROR", "job_crash", "died")
    database.record_event("job-1", "INFO", "started", "hi")

    rows = database.fetch_all("SELECT event, category FROM job_events ORDER BY id")
    assert {row["event"]: row["category"] for row in rows} == {
        "pdf_render_failed": "pdf",
        "epub_parse_failed": "epub",
        "retry_scheduled": "retry",
        "job_crash": "crash",
        "started": "job",
    }


def test_migration_adds_category_and_backfills_old_rows(tmp_path):
    path = tmp_path / DB_NAME
    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        connection.execute("DROP INDEX idx_job_events_category_time")
        connection.execute("ALTER TABLE job_events DROP COLUMN category")
        connection.execute(
            "INSERT INTO jobs(id, user_id, filename, input_path, filetype,"
            " source_language, target_language, model, mode, status, created_at,"
            " updated_at) VALUES ('old', 1, 'b.epub', 'b.epub', 'epub', 'EN',"
            " 'FA', 'm', 'fast', 'failed', 'now', 'now')"
        )
        connection.execute(
            "INSERT INTO job_events(job_id, timestamp, level, event, message)"
            " VALUES ('old', '2026-01-01', 'ERROR', 'pdf_render_failed', 'x')"
        )
        connection.execute(
            "UPDATE settings SET value_json='6' WHERE key='schema_version'"
        )
        connection.commit()

    Database(path).initialize()
    with sqlite3.connect(path) as connection:
        row = connection.execute(
            "SELECT category FROM job_events WHERE job_id='old'"
        ).fetchone()
        indexes = {
            item[1]
            for item in connection.execute(
                "SELECT * FROM sqlite_master WHERE type='index' AND tbl_name='job_events'"
            )
        }
    assert row == ("pdf",)
    assert "idx_job_events_category_time" in indexes


def test_filters_pagination_and_summary(tmp_path):
    database = Database(tmp_path / DB_NAME)
    _job(database, "job-1")
    _event(database, "job-1", category="api", event="api_error", timestamp="2026-01-01T00:00:00+00:00")
    _event(database, "job-1", category="pdf", event="pdf_render_failed", timestamp="2026-01-02T00:00:00+00:00")
    _event(database, "job-1", category="retry", event="retry_scheduled", level="WARNING", timestamp="2026-01-03T00:00:00+00:00")

    page = logs.list_events(database, 1, limit=2)
    assert [item["event"] for item in page["items"]] == ["retry_scheduled", "pdf_render_failed"]
    assert page["has_more"] is True
    assert page["next_before_id"] == page["items"][-1]["id"]

    rest = logs.list_events(database, 1, limit=2, before_id=page["next_before_id"])
    assert [item["event"] for item in rest["items"]] == ["api_error"]
    assert rest["has_more"] is False

    assert [item["event"] for item in logs.list_events(database, 1, category="pdf")["items"]] == [
        "pdf_render_failed"
    ]
    assert [item["event"] for item in logs.list_events(database, 1, level="WARNING")["items"]] == [
        "retry_scheduled"
    ]
    assert [item["event"] for item in logs.list_events(database, 1, q="render")["items"]] == [
        "pdf_render_failed"
    ]
    assert [
        item["event"]
        for item in logs.list_events(database, 1, since="2026-01-02T00:00:00Z")["items"]
    ] == ["retry_scheduled", "pdf_render_failed"]

    counts = logs.summary(database, 1, since="")
    assert counts["total"] == 3
    assert counts["by_level"] == {"ERROR": 2, "WARNING": 1}
    assert counts["by_category"] == {"api": 1, "pdf": 1, "retry": 1}


def test_unparsable_window_is_a_client_error(tmp_path):
    database = Database(tmp_path / DB_NAME)
    with pytest.raises(ValueError):
        logs.list_events(database, 1, since="yesterday")


def test_messages_and_data_are_redacted(tmp_path):
    database = Database(tmp_path / DB_NAME)
    _job(database, "job-1")
    _event(
        database,
        "job-1",
        message="auth failed: Bearer abcdefghijklmnop api_key=super-secret sk-live-123456789",
        data={
            "url": "https://x.test/?api_key=super-secret",
            "note": "sk-live-123456789",
            "api_key": "super-secret",
        },
    )

    item = logs.list_events(database, 1)["items"][0]
    assert "super-secret" not in item["message"]
    assert "abcdefghijklmnop" not in item["message"]
    assert "sk-live-123456789" not in item["message"]
    assert "super-secret" not in item["data"]["url"]
    assert "sk-live-123456789" not in item["data"]["note"]
    assert item["data"]["api_key"] == "[redacted]"


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "logs.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_DIR", tmp_path / "uploads")
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield database, server
    finally:
        server.shutdown()
        server.server_close()
        worker.join()


def _user(database, email: str) -> tuple[int, str]:
    auth.signup(database, email, "Sup3r-secret-pass", email.split("@")[0])
    user, token = auth.login(database, email, "Sup3r-secret-pass")
    return int(user["id"]), token


def _call(server, method, path, *, token=""):
    connection = HTTPConnection(*server.server_address)
    headers = {}
    if token:
        headers["Cookie"] = f"{web.SESSION_COOKIE}={token}"
    connection.request(method, path, None, headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw or b"{}")


def test_http_routes_scope_events_to_the_owner_and_allow_admin_scope_all(live):
    database, server = live
    admin, admin_token = _user(database, "admin@example.com")
    other, other_token = _user(database, "other@example.com")
    _job(database, "admin-job", admin)
    _job(database, "other-job", other)
    _event(database, "admin-job", category="api", event="api_error")
    _event(database, "other-job", category="pdf", event="pdf_render_failed")

    status, payload = _call(server, "GET", "/api/logs", token=other_token)
    assert status == 200
    assert [item["job_id"] for item in payload["items"]] == ["other-job"]

    status, payload = _call(server, "GET", "/api/logs?scope=all", token=admin_token)
    assert status == 200
    assert {item["job_id"] for item in payload["items"]} == {"admin-job", "other-job"}

    status, _ = _call(server, "GET", "/api/logs?scope=all", token=other_token)
    assert status == 403

    status, payload = _call(
        server,
        "GET",
        "/api/logs/summary?scope=all&since=2025-01-01T00:00:00Z",
        token=admin_token,
    )
    assert status == 200 and payload["total"] == 2

    status, payload = _call(server, "GET", "/api/jobs/other-job/events", token=other_token)
    assert status == 200 and payload["items"][0]["event"] == "pdf_render_failed"

    status, _ = _call(server, "GET", "/api/jobs/other-job/events", token=admin_token)
    assert status == 404

    status, _ = _call(server, "GET", "/api/logs?since=nope", token=admin_token)
    assert status == 400
