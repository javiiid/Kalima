"""Phase 1.2/1.6: two users never see each other's domain data.

The roadmap's acceptance is behavioural: user B, even knowing user A's ids,
gets an empty list or a clean 404/403 -- never user A's rows. These drive the
real ``Handler`` with two session cookies so the guard is exercised end to end.
"""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.auth import service as auth
from app.storage.database import Database


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "multi.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web, "WEB_OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(web, "COVERS_DIR", tmp_path / "covers")
    monkeypatch.setattr(web, "_run_job", lambda job, **kwargs: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield database, server
    finally:
        server.shutdown()
        server.server_close()


def _user(database, email: str) -> tuple[int, str]:
    auth.signup(database, email, "Sup3r-secret-pass", email.split("@")[0])
    user, token = auth.login(database, email, "Sup3r-secret-pass")
    return int(user["id"]), token


def _call(server, method, path, *, token="", csrf=True, body=None):
    connection = HTTPConnection(*server.server_address)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Cookie"] = f"{web.SESSION_COOKIE}={token}"
        if csrf:
            # Double-submit pair the browser would send back from the cookie
            # the GET minted. Same "value" on both sides is all that is checked.
            headers["Cookie"] += f"; {web.CSRF_COOKIE}=tok123456789012345678"
            headers["X-CSRF-Token"] = "tok123456789012345678"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection.request(method, path, payload, headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw or b"{}")


def _seed_book(database, user_id: int) -> int:
    book = database.execute(
        "INSERT INTO library_books(user_id, title, created_at, updated_at) VALUES (?, 'Book', 'now', 'now')",
        (user_id,),
    )
    database.execute(
        "INSERT INTO files(user_id, book_id, path, kind, display_name, extension, size_bytes, created_at)"
        " VALUES (?, ?, 'demo.epub', 'original', 'demo.epub', 'epub', 10, 'now')",
        (user_id, book),
    )
    return int(book)


def _seed_job(database, user_id: int, job_id: str) -> web.Job:
    database.execute(
        "INSERT INTO jobs(id, user_id, filename, input_path, filetype, source_language,"
        " target_language, model, mode, status, created_at, updated_at)"
        " VALUES (?, ?, 'book.epub', 'book.epub', 'epub', 'EN', 'FA', 'gpt-5.6-luna',"
        " 'fast', 'running', 'now', 'now')",
        (job_id, user_id),
    )
    job = web.Job(job_id, "book.epub", "book.epub", "epub", 10, {}, "EN", "FA",
                  "gpt-5.6-luna", "fast", user_id=user_id)
    web.JOBS[job_id] = job
    return job


def test_jobs_are_scoped_to_the_owner(live):
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    assert owner != other
    _seed_job(database, owner, "job-owner")

    status, payload = _call(server, "GET", "/api/jobs", token=owner_token)
    assert status == 200 and payload["total"] == 1

    status, payload = _call(server, "GET", "/api/jobs", token=other_token)
    assert status == 200 and payload["total"] == 0

    # Guessing the id must not leak the job either.
    status, _ = _call(server, "GET", "/api/jobs/job-owner", token=other_token)
    assert status == 404
    status, _ = _call(server, "GET", "/api/jobs/job-owner", token=owner_token)
    assert status == 200


def test_library_and_glossary_hide_another_users_book(live):
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    book = _seed_book(database, owner)

    status, payload = _call(server, "GET", "/api/library", token=owner_token)
    assert status == 200 and payload["total"] == 1
    status, payload = _call(server, "GET", "/api/library", token=other_token)
    assert status == 200 and payload["total"] == 0

    status, _ = _call(server, "GET", f"/api/library/{book}/glossary", token=other_token)
    assert status == 404
    status, _ = _call(server, "PUT", f"/api/library/{book}/shelf",
                      token=other_token, body={"shelf": "reading"})
    assert status == 404
    status, _ = _call(server, "DELETE", f"/api/library/{book}", token=other_token)
    assert status == 404
    # The owner's copy is untouched.
    assert database.fetch_one("SELECT id FROM library_books WHERE id=?", (book,)) is not None


def test_glossary_and_memory_lists_are_scoped(live):
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    database.execute(
        "INSERT INTO glossaries(user_id, name, created_at, updated_at) VALUES (?, 'Mine', 'now', 'now')",
        (owner,),
    )
    database.execute(
        "INSERT INTO translation_memory(user_id, source_text, translated_text, source_language,"
        " target_language, last_used_at) VALUES (?, 'Hello', 'سلام', 'EN', 'FA', 'now')",
        (owner,),
    )

    status, payload = _call(server, "GET", "/api/glossaries", token=owner_token)
    assert [item["name"] for item in payload["items"]] == ["Mine"]
    status, payload = _call(server, "GET", "/api/glossaries", token=other_token)
    assert payload["items"] == []

    status, payload = _call(server, "GET", "/api/memory/export", token=owner_token)
    assert len(payload["items"]) == 1
    status, payload = _call(server, "GET", "/api/memory/export", token=other_token)
    assert payload["items"] == []


def test_cookie_write_requires_the_csrf_token(live):
    database, server = live
    _, token = _user(database, "owner@example.com")

    # A cookie-authenticated write without the double-submit pair is refused.
    status, _ = _call(server, "POST", "/api/glossaries", token=token, csrf=False,
                      body={"name": "NoToken"})
    assert status == 403
    # With the pair it succeeds.
    status, payload = _call(server, "POST", "/api/glossaries", token=token,
                            body={"name": "WithToken"})
    assert status == 201 and payload["name"] == "WithToken"
