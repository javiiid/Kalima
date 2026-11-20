"""Queue-aware stop/cancel, the per-user 409, and scheduler gauges.

Step 4 removed the process-wide ``RUN_LOCK``. That means a job can now be
*queued* rather than running, and every route that used to assume "running"
must understand the queue: stopping a queued job must drop it before it ever
touches the provider, and the "one translation at a time" rule must be read
from the scheduler instead of scanning every job ever created.
"""
from __future__ import annotations

import json
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import web
from app.auth import service as auth
from app.jobs.scheduler import JobScheduler
from app.storage.database import Database

ACTIVE_MESSAGE = "یک ترجمه در حال اجراست."


class BlockingRunner:
    """Runner that holds a slot until the test releases it."""

    def __init__(self):
        self._lock = threading.Lock()
        self.started: list[str] = []
        self._release: dict[str, threading.Event] = {}

    def __call__(self, job, *, resume=False):
        with self._lock:
            self.started.append(job.id)
            event = self._release.setdefault(job.id, threading.Event())
        event.wait(5)

    def release(self, job_id: str) -> None:
        with self._lock:
            event = self._release.setdefault(job_id, threading.Event())
        event.set()

    def release_all(self) -> None:
        with self._lock:
            events = list(self._release.values())
        for event in events:
            event.set()


def wait_for(predicate, timeout=2.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "queue.db")
    monkeypatch.setattr(web, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
    runner = BlockingRunner()
    scheduler = JobScheduler(slots=1, per_user_limit=1, runner=runner)
    monkeypatch.setattr(web, "_SCHEDULER", scheduler)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield SimpleNamespace(
            db=database, server=server, runner=runner, scheduler=scheduler, tmp=tmp_path
        )
    finally:
        runner.release_all()
        server.shutdown()
        server.server_close()
        worker.join()
        scheduler.shutdown()


def _user(database, email: str) -> tuple[int, str]:
    auth.signup(database, email, "Sup3r-secret-pass", email.split("@")[0])
    user, token = auth.login(database, email, "Sup3r-secret-pass")
    return int(user["id"]), token


def _call(server, method, path, *, token="", body=None):
    connection = HTTPConnection(*server.server_address)
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Cookie"] = (
            f"{web.SESSION_COOKIE}={token}; {web.CSRF_COOKIE}=tok123456789012345678"
        )
        headers["X-CSRF-Token"] = "tok123456789012345678"
    payload = json.dumps(body).encode("utf-8") if body is not None else None
    connection.request(method, path, payload, headers)
    response = connection.getresponse()
    raw = response.read()
    connection.close()
    return response.status, json.loads(raw or b"{}")


def _get(server, path):
    connection = HTTPConnection(*server.server_address)
    connection.request("GET", path, None, {})
    response = connection.getresponse()
    body = response.read()
    content_type = response.getheader("Content-Type") or ""
    connection.close()
    return response.status, body, content_type


def _job(job_id: str, user_id: int, status: str = "queued") -> web.Job:
    job = web.Job(
        job_id, "book.epub", Path("book.epub"), "epub", 10, {}, "EN", "FA", "model", "fast",
        status=status, user_id=user_id,
    )
    web.JOBS[job_id] = job
    return job


def _occupy_slot(env, user_id: int, job_id: str = "running-job") -> web.Job:
    job = _job(job_id, user_id, status="running")
    env.scheduler.submit(job)
    assert wait_for(lambda: env.runner.started == [job_id])
    return job


def test_stop_drops_a_queued_job_before_it_runs(live):
    user_a, _ = _user(live.db, "a@example.com")
    user_b, token_b = _user(live.db, "b@example.com")
    _occupy_slot(live, user_a)
    queued = _job("queued-job", user_b)
    live.scheduler.submit(queued)
    assert live.scheduler.stats()["queued"] == 1

    status, payload = _call(live.server, "POST", "/api/jobs/queued-job/stop", token=token_b)

    assert status == 200 and payload["ok"] is True
    assert queued.status == "cancelled"
    assert queued.stop_event.is_set()
    assert live.scheduler.stats()["queued"] == 0
    assert "queued-job" not in live.runner.started


def test_cancel_drops_a_queued_job(live):
    user_a, _ = _user(live.db, "a@example.com")
    user_b, token_b = _user(live.db, "b@example.com")
    _occupy_slot(live, user_a)
    queued = _job("queued-job", user_b)
    live.scheduler.submit(queued)
    assert live.scheduler.stats()["queued"] == 1

    status, payload = _call(live.server, "POST", "/api/jobs/queued-job/cancel", token=token_b)

    assert status == 200 and payload["ok"] is True
    assert queued.status == "cancelled"
    assert live.scheduler.stats()["queued"] == 0
    assert "queued-job" not in live.runner.started


def test_stop_on_a_running_job_only_signals_it(live):
    user_a, token_a = _user(live.db, "a@example.com")
    running = _occupy_slot(live, user_a)

    status, payload = _call(live.server, "POST", "/api/jobs/running-job/stop", token=token_a)

    assert status == 200 and payload["ok"] is True
    assert running.stop_event.is_set()
    assert running.status == "running"


def test_stop_rejects_a_finished_job(live):
    user_a, token_a = _user(live.db, "a@example.com")
    _job("done-job", user_a, status="completed")

    status, _ = _call(live.server, "POST", "/api/jobs/done-job/stop", token=token_a)

    assert status == 400


def test_user_has_active_job_reads_the_scheduler(live):
    user_a, _ = _user(live.db, "a@example.com")
    user_b, _ = _user(live.db, "b@example.com")
    running = _occupy_slot(live, user_a)

    assert web._user_has_active_job(user_a) is True
    assert web._user_has_active_job(user_b) is False

    # A job whose runner already wrote a terminal status must not keep the
    # user blocked while the scheduler reaps it.
    running.status = "completed"
    assert web._user_has_active_job(user_a) is False


def test_second_upload_is_rejected_while_a_job_is_queued(live):
    user_a, token_a = _user(live.db, "a@example.com")
    _occupy_slot(live, user_a)
    book = live.db.execute(
        "INSERT INTO library_books(user_id, title, created_at, updated_at)"
        " VALUES (?, 'Book', 'now', 'now')",
        (user_a,),
    )
    source = live.tmp / "book.epub"
    source.write_bytes(b"test source")
    live.db.execute(
        "INSERT INTO files(user_id, book_id, path, kind, display_name, extension, size_bytes, created_at)"
        " VALUES (?, ?, ?, 'original', 'book.epub', 'epub', 11, 'now')",
        (user_a, book, str(source)),
    )

    status, payload = _call(live.server, "POST", f"/api/library/{book}/translate", token=token_a)

    assert status == 409
    assert payload["error"] == ACTIVE_MESSAGE


def test_metrics_expose_scheduler_gauges(live):
    user_a, _ = _user(live.db, "a@example.com")
    _occupy_slot(live, user_a)
    live.scheduler.submit(_job("queued-job", user_a))

    status, body, content_type = _get(live.server, "/api/metrics?format=prometheus")

    assert status == 200 and "text/plain" in content_type
    assert b"kalima_job_slots 1" in body
    assert b"kalima_jobs_running 1" in body
    assert b"kalima_jobs_queued 1" in body

    status, payload = _call(live.server, "GET", "/api/metrics")
    assert status == 200
    assert payload["jobs"]["slots"] == 1
    assert payload["jobs"]["running"] == 1
    assert payload["jobs"]["queued"] == 1
