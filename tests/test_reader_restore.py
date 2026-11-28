"""A restarted server must hand a book back to its real owner.

Job snapshots written before jobs became user-scoped carry no ``user_id``.
``restore_jobs`` used to fall back to user 1 for those, so after a restart
every old book was owned by nobody: it stayed listed (the library reads the
DB) but the reader 404'd, which is exactly the "text never loads" report.
These tests drive the real ``Handler`` so the whole path is covered.
"""
from __future__ import annotations

import json
import threading
import zipfile
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.auth import service as auth
from app.storage.database import Database


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "restore.db")
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


def _call(server, method, path, *, token=""):
    connection = HTTPConnection(*server.server_address)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Cookie"] = f"{web.SESSION_COOKIE}={token}"
    connection.request(method, path, None, headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw or b"{}")


def _make_epub(path, title: str) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfile full-path="OEBPS/content.opf"/></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<package><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            f"<html><head><title>{title}</title></head><body><h1>{title}</h1><p>متن</p></body></html>",
        )


def _legacy_snapshot(meta_dir, job_id: str, input_path, output_path) -> None:
    """A pre-user_id job snapshot: no ``user_id``, no ``estimated_cost``."""
    meta_dir.mkdir(parents=True, exist_ok=True)
    (meta_dir / f"{job_id}.json").write_text(
        json.dumps(
            {
                "id": job_id,
                "filename": input_path.name,
                "input_path": str(input_path),
                "filetype": "epub",
                "file_size": input_path.stat().st_size if input_path.exists() else 0,
                "options": {},
                "source_language": "EN",
                "target_language": "FA",
                "model": "gpt-5.6-luna",
                "mode": "fast",
                "status": "completed",
                "created_at": "now",
                "updated_at": "now",
                "paths": None,
                "output_path": str(output_path),
                "progress": {"completed": 1, "total": 1},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _seed_job_row(database, user_id: int, job_id: str, input_path, output_path) -> None:
    database.execute(
        "INSERT INTO jobs(id, user_id, filename, input_path, filetype, source_language,"
        " target_language, model, mode, status, created_at, updated_at, output_path)"
        " VALUES (?, ?, ?, ?, 'epub', 'EN', 'FA', 'gpt-5.6-luna', 'fast', 'completed',"
        " 'now', 'now', ?)",
        (job_id, user_id, input_path.name, str(input_path), str(output_path)),
    )


def test_restored_job_returns_to_its_db_owner(live):
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    other, other_token = _user(database, "other@example.com")
    assert owner != other

    source = web.UPLOAD_DIR / "book.epub"
    output = web.WEB_OUTPUT_DIR / "book.translated.epub"
    source.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    _make_epub(source, "Chapter One")
    _make_epub(output, "فصل اول")
    _legacy_snapshot(web.JOB_META_DIR, "legacy-1", source, output)
    _seed_job_row(database, owner, "legacy-1", source, output)

    web.restore_jobs()

    assert web.JOBS["legacy-1"].user_id == owner
    # The owner is written back so a later restore cannot lose it again.
    stored = json.loads((web.JOB_META_DIR / "legacy-1.json").read_text(encoding="utf-8"))
    assert stored["user_id"] == owner

    status, payload = _call(server, "GET", "/api/jobs", token=owner_token)
    assert status == 200 and payload["total"] == 1
    status, payload = _call(server, "GET", "/api/jobs", token=other_token)
    assert status == 200 and payload["total"] == 0

    status, payload = _call(server, "GET", "/api/reader/legacy-1/chapters", token=owner_token)
    assert status == 200 and payload["items"]
    status, _ = _call(server, "GET", "/api/reader/legacy-1/chapters", token=other_token)
    assert status == 404


def _make_epub_with_meta(path, title: str, author: str) -> None:
    """An EPUB that carries its own Dublin Core title and creator."""
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip", compress_type=zipfile.ZIP_STORED)
        archive.writestr(
            "META-INF/container.xml",
            '<container><rootfile full-path="OEBPS/content.opf"/></container>',
        )
        archive.writestr(
            "OEBPS/content.opf",
            '<package xmlns:dc="http://purl.org/dc/elements/1.1/">'
            f"<metadata><dc:title>{title}</dc:title><dc:creator>{author}</dc:creator></metadata>"
            '<manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/>'
            '</manifest><spine><itemref idref="c1"/></spine></package>',
        )
        archive.writestr(
            "OEBPS/c1.xhtml",
            "<html><head><title>Chapter One</title></head>"
            "<body><h1>Chapter One</h1><p>text</p></body></html>",
        )


def test_chapters_payload_carries_the_books_own_title_and_author(live):
    """The reader header shows the book, not the uploaded filename.

    ``/api/reader/<id>/chapters`` used to return only ``book`` (the filename
    the user uploaded). The header now prefers the source EPUB's Dublin Core
    title and creator, and falls back to the filename when the source has
    been pruned or carries no metadata.
    """
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    source = web.UPLOAD_DIR / "upload_1234.epub"
    output = web.WEB_OUTPUT_DIR / "out.translated.epub"
    source.parent.mkdir(parents=True, exist_ok=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    _make_epub_with_meta(source, "Sample Book", "Some Author")
    _make_epub(output, "Chapter One")
    _legacy_snapshot(web.JOB_META_DIR, "meta-1", source, output)
    _seed_job_row(database, owner, "meta-1", source, output)
    web.restore_jobs()

    status, payload = _call(server, "GET", "/api/reader/meta-1/chapters", token=owner_token)
    assert status == 200
    assert payload["title"] == "Sample Book"
    assert payload["author"] == "Some Author"
    assert payload["book"].endswith(".epub")


def test_restored_owner_falls_back_only_without_any_evidence(live):
    database, _ = live
    owner, _ = _user(database, "owner@example.com")
    source = web.UPLOAD_DIR / "book.epub"
    source.parent.mkdir(parents=True, exist_ok=True)
    _make_epub(source, "Chapter One")
    _seed_job_row(database, owner, "row-only", source, source.parent / "out.epub")

    assert web._restored_job_owner({"id": "legacy-1", "user_id": owner}) == owner
    assert web._restored_job_owner({"id": "row-only"}) == owner
    assert web._restored_job_owner({"id": "unknown"}) == 1


def test_finished_book_stays_readable_after_its_source_is_pruned(live):
    """A completed book must survive losing the uploaded source.

    The reader serves the translated EPUB, so a pruned upload must not drop
    the job -- that is the book the library lists but can never open.
    """
    database, server = live
    owner, owner_token = _user(database, "owner@example.com")
    source = web.UPLOAD_DIR / "gone.epub"
    output = web.WEB_OUTPUT_DIR / "kept.translated.epub"
    output.parent.mkdir(parents=True, exist_ok=True)
    _make_epub(output, "فصل اول")
    _legacy_snapshot(web.JOB_META_DIR, "pruned-1", source, output)  # source never written
    _seed_job_row(database, owner, "pruned-1", source, output)

    web.restore_jobs()

    assert web.JOBS["pruned-1"].user_id == owner
    status, payload = _call(server, "GET", "/api/reader/pruned-1/chapters", token=owner_token)
    assert status == 200 and payload["items"]


def test_pruned_source_is_never_queued_for_resume(live, monkeypatch):
    database, _ = live
    owner, _ = _user(database, "owner@example.com")
    source = web.UPLOAD_DIR / "gone.epub"
    output = web.WEB_OUTPUT_DIR / "half.translated.epub"
    output.parent.mkdir(parents=True, exist_ok=True)
    _make_epub(output, "نیمه")
    _legacy_snapshot(web.JOB_META_DIR, "pruned-2", source, output)
    _seed_job_row(database, owner, "pruned-2", source, output)
    raw = json.loads((web.JOB_META_DIR / "pruned-2.json").read_text(encoding="utf-8"))
    raw.update({"status": "running", "pipeline_job_id": "pipeline-x"})
    (web.JOB_META_DIR / "pruned-2.json").write_text(
        json.dumps(raw, ensure_ascii=False), encoding="utf-8"
    )

    resume_calls: list[str] = []
    monkeypatch.setattr(web, "_run_job", lambda job, **kwargs: resume_calls.append(job.id))
    web.restore_jobs()

    job = web.JOBS["pruned-2"]
    assert job.status == "failed"
    assert "source file is missing" in (job.error or "")
    assert resume_calls == []
