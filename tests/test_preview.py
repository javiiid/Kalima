"""Phase 3: an output can be looked at before it is downloaded.

The point of the preview route is not the bytes -- ``/downloads/`` already
serves those. It is that the bytes arrive *inline*, with a type the browser
can render and a policy that stops somebody else's document from running on
our origin. These tests drive the real handler so the headers are the ones a
browser actually receives.
"""
from __future__ import annotations

import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import fitz
import pytest

from app import web
from app.auth import service as auth
from app.output.docx import write_docx
from app.storage.database import Database


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "preview.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web, "WEB_OUTPUT_DIR", tmp_path / "output")
    monkeypatch.setattr(web, "COVERS_DIR", tmp_path / "covers")
    monkeypatch.setattr(web, "CONVERTS", {})
    monkeypatch.setattr(web, "_run_job", lambda job, **kwargs: None)
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
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


def _get(server, path: str, token: str = ""):
    connection = HTTPConnection(*server.server_address)
    headers = {"Cookie": f"{web.SESSION_COOKIE}={token}"} if token else {}
    connection.request("GET", path, None, headers)
    response = connection.getresponse()
    body = response.read()
    values = {name.lower(): value for name, value in response.getheaders()}
    connection.close()
    return response.status, body, values


def _pdf(path: Path) -> Path:
    document = fitz.open()
    try:
        page = document.new_page()
        page.insert_text((72, 84), "Preview page.", fontsize=12)
        document.save(path)
    finally:
        document.close()
    return path


def _docx(path: Path) -> Path:
    write_docx(
        [{"id": "c1", "chapter": "ch1.html", "target": "متن پیش‌نمایش کتاب."}],
        path,
        title="Preview Book",
        to_lang="FA",
    )
    return path


def _seed(database, user_id: int, job_id: str, assets: dict[str, Path], output: Path | None = None):
    database.execute(
        "INSERT INTO jobs(id, user_id, filename, input_path, filetype, source_language,"
        " target_language, model, mode, status, created_at, updated_at)"
        " VALUES (?, ?, 'book.epub', 'book.epub', 'epub', 'EN', 'FA', 'gpt-5.6-luna',"
        " 'fast', 'completed', 'now', 'now')",
        (job_id, user_id),
    )
    job = web.Job(
        job_id, "book.epub", "book.epub", "epub", 10, {}, "EN", "FA",
        "gpt-5.6-luna", "fast", user_id=user_id,
    )
    job.status = "completed"
    job.assets = {name: str(path) for name, path in assets.items()}
    job.output_path = output
    web.JOBS[job_id] = job
    return job


def test_a_pdf_preview_is_served_inline_and_sandboxed(live):
    database, server = live
    user_id, token = _user(database, "owner@example.com")
    pdf = _pdf(web.user_output_dir(user_id) / "book.pdf")
    _seed(database, user_id, "job-pdf", {"translated_pdf": pdf})

    status, body, headers = _get(server, "/preview/job-pdf/translated_pdf", token)
    assert status == 200
    assert body[:5] == b"%PDF-"
    assert headers["content-type"] == "application/pdf"
    assert headers["content-disposition"].startswith("inline")
    assert headers["x-content-type-options"] == "nosniff"
    assert "sandbox" in headers["content-security-policy"]
    assert headers["cache-control"] == "private, no-store"


def test_a_docx_preview_is_text_not_a_download(live):
    database, server = live
    user_id, token = _user(database, "owner@example.com")
    docx = _docx(web.user_output_dir(user_id) / "book.docx")
    _seed(database, user_id, "job-docx", {"docx": docx})

    status, body, headers = _get(server, "/preview/job-docx/docx", token)
    assert status == 200
    assert headers["content-type"].startswith("text/html")
    page = body.decode("utf-8")
    assert "متن پیش‌نمایش کتاب." in page
    assert "<script" not in page
    assert "default-src 'none'" in headers["content-security-policy"]


def test_the_main_output_previews_too(live):
    database, server = live
    user_id, token = _user(database, "owner@example.com")
    pdf = _pdf(web.user_output_dir(user_id) / "main.pdf")
    _seed(database, user_id, "job-main", {}, output=pdf)

    status, body, headers = _get(server, "/preview/job-main", token)
    assert status == 200 and body[:5] == b"%PDF-"
    assert headers["content-type"] == "application/pdf"


def test_another_users_job_is_not_previewable(live):
    database, server = live
    owner, _owner_token = _user(database, "owner@example.com")
    _other, other_token = _user(database, "other@example.com")
    pdf = _pdf(web.user_output_dir(owner) / "book.pdf")
    _seed(database, owner, "job-private", {"translated_pdf": pdf})

    status, _body, _headers = _get(server, "/preview/job-private/translated_pdf", other_token)
    assert status == 404


def test_an_unknown_asset_or_type_is_refused(live):
    database, server = live
    user_id, token = _user(database, "owner@example.com")
    epub = web.user_output_dir(user_id) / "book.epub"
    epub.write_bytes(b"PK\x03\x04not really")
    _seed(database, user_id, "job-epub", {"translated_epub": epub})

    assert _get(server, "/preview/job-epub/nope", token)[0] == 404
    # An EPUB has no inline renderer; previewing it is the reader's job.
    assert _get(server, "/preview/job-epub/translated_epub", token)[0] == 404
    assert _get(server, "/preview/missing-job", token)[0] == 404


def test_a_quick_conversion_previews(live):
    database, server = live
    user_id, token = _user(database, "owner@example.com")
    folder = web.user_output_dir(user_id) / "convert_abc123"
    folder.mkdir(parents=True)
    pdf = _pdf(folder / "book.pdf")
    web.CONVERTS["abc123"] = {
        "generated": {"translated_pdf": str(pdf)},
        "source": "book.epub",
        "created_at": "now",
        "user_id": user_id,
    }

    status, body, headers = _get(server, "/preview/convert/abc123/translated_pdf", token)
    assert status == 200 and body[:5] == b"%PDF-"
    assert headers["content-type"] == "application/pdf"
