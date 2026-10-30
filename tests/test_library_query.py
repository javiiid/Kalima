"""Library group operations: filters, content search, sort and bulk actions.

``library_summary`` is exercised directly against a throwaway database; the
bulk endpoint drives the real ``Handler`` with session cookies so ownership
isolation is checked end to end rather than by reading the code.
"""
from __future__ import annotations

import io
import json
import threading
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from urllib.parse import urlencode

import pytest

from app import web
from app.auth import service as auth
from app.storage.database import Database


def _book(database, user_id, title, *, updated_at, created_at="2026-01-01T00:00:00", archived=0):
    return int(database.execute(
        "INSERT INTO library_books(user_id, title, created_at, updated_at, archived)"
        " VALUES (?,?,?,?,?)",
        (user_id, title, created_at, updated_at, archived),
    ))


def _job(database, user_id, job_id, *, model="gpt-5.6-luna", status="completed",
         completed=10, total=10, cost=0.0):
    database.execute(
        "INSERT INTO jobs(id, user_id, filename, input_path, filetype, source_language,"
        " target_language, model, mode, status, progress_completed, progress_total,"
        " estimated_cost, created_at, updated_at)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (job_id, user_id, "book.epub", "book.epub", "epub", "EN", "FA", model, "fast",
         status, completed, total, cost, "2026-01-01T00:00:00", "2026-01-01T00:00:00"),
    )


def _variant(database, user_id, book_id, job_id, *, kind="translated", size=100,
             extension="epub", path="demo.epub", display_name="demo.epub"):
    database.execute(
        "INSERT INTO files(user_id, book_id, job_id, path, kind, display_name, extension,"
        " size_bytes, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (user_id, book_id, job_id, path, kind, display_name, extension, size, "2026-01-01T00:00:00"),
    )


def _chunk(database, job_id, chunk_id, translated_text):
    database.execute(
        "INSERT INTO job_chunks(job_id, chunk_id, status, translated_text, updated_at)"
        " VALUES (?,?,?,?,?)",
        (job_id, chunk_id, "completed", translated_text, "2026-01-01T00:00:00"),
    )


@pytest.fixture
def summary_db(tmp_path, monkeypatch):
    import app.web as web_module

    database = Database(tmp_path / "query.db")
    monkeypatch.setattr(web_module, "db", database)
    return database


def test_content_scope_searches_translated_text(summary_db):
    database = summary_db
    nightly = _book(database, 1, "Nightfall", updated_at="2026-02-01T00:00:00")
    _job(database, 1, "job-night")
    _variant(database, 1, nightly, "job-night")
    _chunk(database, "job-night", "c1", "در دل شب رازی نهفته است")
    other = _book(database, 1, "Daylight", updated_at="2026-02-02T00:00:00")
    _job(database, 1, "job-day")
    _variant(database, 1, other, "job-day")
    _chunk(database, "job-day", "c1", "روز روشن بود")

    # Title-only search never looks inside the translated text.
    query = urlencode({"q": "راز"})
    title_hits = web.library_summary(f"{query}&scope=title", 1)
    assert title_hits["total"] == 0

    content_hits = web.library_summary(f"{query}&scope=content", 1)
    assert [item["title"] for item in content_hits["items"]] == ["Nightfall"]

    # A title match is still shown under content scope; content only widens.
    both = web.library_summary(f"{query}&scope=content", 1)
    assert both["total"] == 1
    titled = web.library_summary("q=daylight&scope=content", 1)
    assert [item["title"] for item in titled["items"]] == ["Daylight"]
    assert web.library_summary("q=daylight&scope=title", 1)["total"] == 1


def test_model_filter_and_models_catalogue(summary_db):
    database = summary_db
    luna = _book(database, 1, "Luna", updated_at="2026-02-01T00:00:00")
    _job(database, 1, "job-luna", model="gpt-5.6-luna", cost=1.25)
    _variant(database, 1, luna, "job-luna")
    sol = _book(database, 1, "Sol", updated_at="2026-02-02T00:00:00")
    _job(database, 1, "job-sol", model="gpt-6.1-sol", cost=0.5)
    _variant(database, 1, sol, "job-sol")

    summary = web.library_summary("", 1)
    assert summary["models"] == ["gpt-5.6-luna", "gpt-6.1-sol"]
    item = next(i for i in summary["items"] if i["title"] == "Luna")
    assert item["model"] == "gpt-5.6-luna"
    assert item["cost"] == 1.25
    assert item["variants"][0]["model"] == "gpt-5.6-luna"
    assert item["variants"][0]["cost"] == 1.25

    filtered = web.library_summary("model=gpt-6.1-sol", 1)
    assert [i["title"] for i in filtered["items"]] == ["Sol"]
    assert web.library_summary("model=nope", 1)["total"] == 0


def test_date_range_filter(summary_db):
    database = summary_db
    early = _book(database, 1, "Early", updated_at="2026-01-15T00:00:00")
    _job(database, 1, "job-early")
    _variant(database, 1, early, "job-early")
    late = _book(database, 1, "Late", updated_at="2026-06-15T00:00:00")
    _job(database, 1, "job-late")
    _variant(database, 1, late, "job-late")

    assert [i["title"] for i in web.library_summary("since=2026-03-01", 1)["items"]] == ["Late"]
    assert [i["title"] for i in web.library_summary("until=2026-03-01", 1)["items"]] == ["Early"]
    both = web.library_summary("since=2026-01-01&until=2026-12-31", 1)
    assert both["total"] == 2


def test_sort_keys_cover_the_whole_set(summary_db):
    database = summary_db
    banana = _book(database, 1, "Banana", updated_at="2026-03-01T00:00:00", created_at="2026-01-01T00:00:00")
    _job(database, 1, "job-banana", cost=3.0, completed=5, total=10)
    _variant(database, 1, banana, "job-banana", size=300)
    apple = _book(database, 1, "apple", updated_at="2026-05-01T00:00:00", created_at="2026-02-01T00:00:00")
    _job(database, 1, "job-apple", cost=1.0, completed=10, total=10)
    _variant(database, 1, apple, "job-apple", size=100)
    cherry = _book(database, 1, "Cherry", updated_at="2026-01-01T00:00:00", created_at="2026-03-01T00:00:00")
    _job(database, 1, "job-cherry", cost=2.0, completed=1, total=10)
    _variant(database, 1, cherry, "job-cherry", size=200)

    def order(query):
        return [item["title"] for item in web.library_summary(query, 1)["items"]]

    assert order("sort=title") == ["apple", "Banana", "Cherry"]
    assert order("sort=updated") == ["apple", "Banana", "Cherry"]
    assert order("sort=created") == ["Cherry", "apple", "Banana"]
    assert order("sort=size") == ["Banana", "Cherry", "apple"]
    assert order("sort=cost") == ["Banana", "Cherry", "apple"]
    assert order("sort=progress") == ["apple", "Banana", "Cherry"]
    # An unknown sort key falls back to updated, never to a crash.
    assert order("sort=nonsense") == ["apple", "Banana", "Cherry"]


def test_sort_is_stable_across_pages(summary_db):
    database = summary_db
    for index in range(5):
        book = _book(database, 1, f"T{index}", updated_at=f"2026-0{index + 1}-01T00:00:00")
        _job(database, 1, f"job-{index}")
        _variant(database, 1, book, f"job-{index}", size=index * 10)
    first = web.library_summary("sort=size&page=1&limit=2", 1)
    second = web.library_summary("sort=size&page=2&limit=2", 1)
    assert [i["title"] for i in first["items"]] == ["T4", "T3"]
    assert [i["title"] for i in second["items"]] == ["T2", "T1"]
    assert first["total"] == second["total"] == 5


# --- bulk endpoint ---------------------------------------------------------


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "bulk.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "_run_job", lambda job, **kwargs: None)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield database, server, tmp_path
    finally:
        server.shutdown()
        server.server_close()


def _user(database, email):
    auth.signup(database, email, "Sup3r-secret-pass", email.split("@")[0])
    user, token = auth.login(database, email, "Sup3r-secret-pass")
    return int(user["id"]), token


def _call(server, method, path, *, token="", body=None):
    connection = HTTPConnection(*server.server_address)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Cookie"] = f"{web.SESSION_COOKIE}={token}; {web.CSRF_COOKIE}=tok123456789012345678"
        headers["X-CSRF-Token"] = "tok123456789012345678"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection.request(method, path, payload, headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, raw


def _json_body(raw):
    return json.loads(raw or b"{}")


def test_bulk_delete_archives_owned_books_only(live):
    database, server, _tmp = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    mine = _book(database, owner, "Mine", updated_at="2026-02-01T00:00:00")
    theirs = _book(database, other, "Theirs", updated_at="2026-02-01T00:00:00")

    status, raw = _call(server, "POST", "/api/library/bulk", token=other_token,
                        body={"action": "delete", "ids": [mine, theirs]})
    assert status == 200
    assert _json_body(raw)["deleted"] == 1
    assert database.fetch_one("SELECT archived FROM library_books WHERE id=?", (theirs,))["archived"] == 1
    # The other user's book is untouched, not merely invisible.
    assert database.fetch_one("SELECT archived FROM library_books WHERE id=?", (mine,))["archived"] == 0

    status, raw = _call(server, "POST", "/api/library/bulk", token=owner_token,
                        body={"action": "delete", "ids": [mine]})
    assert _json_body(raw)["deleted"] == 1
    assert database.fetch_one("SELECT archived FROM library_books WHERE id=?", (mine,))["archived"] == 1


def test_bulk_resume_queues_paused_epub_jobs(live):
    database, server, _tmp = live
    owner, token = _user(database, "owner@example.com")
    book = _book(database, owner, "Resume Me", updated_at="2026-02-01T00:00:00")
    _job(database, owner, "job-resume", status="paused")
    _variant(database, owner, book, "job-resume")
    job = web.Job("job-resume", "book.epub", "book.epub", "epub", 10, {}, "EN", "FA",
                  "gpt-5.6-luna", "fast", status="paused", user_id=owner)
    job.pipeline_job_id = "pipeline-1"
    web.JOBS["job-resume"] = job

    notresumable = _book(database, owner, "Finished", updated_at="2026-02-02T00:00:00")
    _job(database, owner, "job-done", status="completed")
    _variant(database, owner, notresumable, "job-done")

    status, raw = _call(server, "POST", "/api/library/bulk", token=token,
                        body={"action": "resume", "ids": [book, notresumable]})
    assert status in {200, 202}
    payload = _json_body(raw)
    assert payload["resumed"] == 1
    assert payload["skipped"] == [{"id": notresumable, "reason": "not_resumable"}]
    assert job.status == "queued"


def test_bulk_download_returns_a_zip_of_translations(live):
    database, server, tmp = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    book = _book(database, owner, "Bundle", updated_at="2026-02-01T00:00:00")
    _job(database, owner, "job-bundle")
    translated = tmp / "bundle-fa.epub"
    translated.write_bytes(b"PK\x03\x04 not really an epub")
    _variant(database, owner, book, "job-bundle", path=str(translated), display_name="bundle-fa.epub")

    # Another user asking for the same id gets nothing to zip.
    status, raw = _call(server, "POST", "/api/library/bulk", token=other_token,
                        body={"action": "download", "ids": [book]})
    assert status == 404

    status, raw = _call(server, "POST", "/api/library/bulk", token=owner_token,
                        body={"action": "download", "ids": [book]})
    assert status == 200
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        names = archive.namelist()
        assert names == ["Bundle/bundle-fa.epub"]
        assert archive.read(names[0]) == b"PK\x03\x04 not really an epub"


def test_bulk_rejects_unknown_action_and_empty_selection(live):
    database, server, _tmp = live
    _owner, token = _user(database, "owner@example.com")
    status, _raw = _call(server, "POST", "/api/library/bulk", token=token,
                         body={"action": "explode", "ids": [1]})
    assert status == 400
    status, _raw = _call(server, "POST", "/api/library/bulk", token=token, body={"action": "delete", "ids": []})
    assert status == 400
