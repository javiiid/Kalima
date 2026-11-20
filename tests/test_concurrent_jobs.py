"""Two users, two books, two jobs at the same time.

This is the acceptance test the ``RUN_LOCK`` removal exists for. It drives the
real ``Handler`` with real sessions and a fake ``_run_job``, so the assertions
are about scheduling -- overlap, waiting time, the per-user cap -- and about
state isolation: each run owns its own state file and its own log buffer.
"""
from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import web
from app.account import billing, service as account_service
from app.auth import service as auth
from app.core import job_log
from app.core.job_log import capture as capture_job_log
from app.jobs.scheduler import JobScheduler
from app.storage.database import Database


class FakePipeline:
    """Stand-in for the translation pipeline: parks each job on an event."""

    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self.running: set[str] = set()
        self.started_at: dict[str, float] = {}
        self.peak = 0
        self._release: dict[str, threading.Event] = {}

    def __call__(self, job, *, resume=False):
        with self._lock:
            self.running.add(job.id)
            self.started_at.setdefault(job.id, time.monotonic())
            self.peak = max(self.peak, len(self.running))
            event = self._release.setdefault(job.id, threading.Event())
        job.status = "running"
        # One state file per job: a shared file would show another job's id.
        (self.state_dir / f"{job.id}.state").write_text(job.id, encoding="utf-8")
        with capture_job_log(job.log):
            print(f"job {job.id} running")
        event.wait(5)
        with self._lock:
            self.running.discard(job.id)
        job.status = "completed"

    def release(self, job_id: str) -> None:
        with self._lock:
            event = self._release.setdefault(job_id, threading.Event())
        event.set()

    def release_all(self) -> None:
        with self._lock:
            events = list(self._release.values())
        for event in events:
            event.set()


def wait_for(predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


@contextmanager
def _router():
    """Install the stdout router for the duration of the block.

    Not done in the fixture: pytest re-binds ``sys.stdout`` between the setup
    and call phases, so a router installed during setup would be bypassed.
    """
    job_log.install()
    try:
        yield
    finally:
        job_log.uninstall()


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "concurrent.db")
    monkeypatch.setattr(web, "db", database)
    # Billing binds the db singleton at import time, so the credit gate would
    # otherwise charge against the session database the conftest placeholder
    # points at, and a second user would fail with "account not found".
    monkeypatch.setattr(billing, "db", database)
    monkeypatch.setattr(account_service, "db", database)
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "UPLOAD_DIR", tmp_path / "uploads")
    monkeypatch.setattr(web, "_ACCESS_LOGGER", False)
    pipeline = FakePipeline(tmp_path / "pipeline")
    monkeypatch.setattr(web, "_run_job", pipeline)
    scheduler = JobScheduler(slots=2, per_user_limit=1, runner=web._dispatch_job)
    monkeypatch.setattr(web, "_SCHEDULER", scheduler)
    server = ThreadingHTTPServer(("127.0.0.1", 0), web.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        yield SimpleNamespace(db=database, server=server, pipeline=pipeline, tmp=tmp_path)
    finally:
        pipeline.release_all()
        server.shutdown()
        server.server_close()
        worker.join()
        scheduler.shutdown()


def _user(database, email: str) -> tuple[int, str]:
    auth.signup(database, email, "Sup3r-secret-pass", email.split("@")[0])
    user, token = auth.login(database, email, "Sup3r-secret-pass")
    return int(user["id"]), token


def _book(env, user_id: int, title: str) -> int:
    book = env.db.execute(
        "INSERT INTO library_books(user_id, title, created_at, updated_at)"
        " VALUES (?, ?, 'now', 'now')",
        (user_id, title),
    )
    source = env.tmp / f"{title}.epub"
    source.write_bytes(b"test source")
    env.db.execute(
        "INSERT INTO files(user_id, book_id, path, kind, display_name, extension, size_bytes, created_at)"
        " VALUES (?, ?, ?, 'original', ?, 'epub', 11, 'now')",
        (user_id, book, str(source), source.name),
    )
    return int(book)


def _translate(server, book: int, token: str):
    connection = HTTPConnection(*server.server_address)
    headers = {
        "Content-Type": "application/json",
        "Cookie": f"{web.SESSION_COOKIE}={token}; {web.CSRF_COOKIE}=tok123456789012345678",
        "X-CSRF-Token": "tok123456789012345678",
    }
    connection.request("POST", f"/api/library/{book}/translate", "{}", headers)
    response = connection.getresponse()
    payload = json.loads(response.read() or b"{}")
    connection.close()
    return response.status, payload


def test_two_users_translate_at_the_same_time(live):
    user_a, token_a = _user(live.db, "a@example.com")
    user_b, token_b = _user(live.db, "b@example.com")
    book_a, book_b = _book(live, user_a, "book-a"), _book(live, user_b, "book-b")

    with _router():
        status_a, payload_a = _translate(live.server, book_a, token_a)
        status_b, payload_b = _translate(live.server, book_b, token_b)
        assert status_a == 201, payload_a
        assert status_b == 201, payload_b

        # Both slots are occupied at the same instant, and neither book waited
        # for a slot it could have had.
        assert wait_for(lambda: live.pipeline.peak == 2)
        assert web._scheduler().stats()["running"] == 2

        job_a = web.JOBS[payload_a["id"]]
        job_b = web.JOBS[payload_b["id"]]
        assert abs(live.pipeline.started_at[job_b.id] - live.pipeline.started_at[job_a.id]) < 1.0

        # Log isolation: two jobs, one router, two buffers.
        assert wait_for(
            lambda: job_a.id in job_a.log.getvalue() and job_b.id in job_b.log.getvalue()
        )
        assert job_b.id not in job_a.log.getvalue()
        assert job_a.id not in job_b.log.getvalue()

    # State isolation: each job owns its own file.
    state_dir = live.tmp / "pipeline"
    assert (state_dir / f"{job_a.id}.state").read_text(encoding="utf-8") == job_a.id
    assert (state_dir / f"{job_b.id}.state").read_text(encoding="utf-8") == job_b.id


def test_second_book_for_one_user_is_refused_while_the_first_runs(live):
    user_a, token_a = _user(live.db, "a@example.com")
    first, second = _book(live, user_a, "first"), _book(live, user_a, "second")

    assert _translate(live.server, first, token_a)[0] == 201
    assert wait_for(lambda: live.pipeline.peak == 1)

    status, payload = _translate(live.server, second, token_a)
    assert status == 409
    assert payload["error"] == "یک ترجمه در حال اجراست."
    assert web._scheduler().stats()["running"] == 1


def test_a_third_user_queues_and_then_runs_when_a_slot_frees(live):
    user_a, token_a = _user(live.db, "a@example.com")
    user_b, token_b = _user(live.db, "b@example.com")
    user_c, token_c = _user(live.db, "c@example.com")
    books = {
        "a": _book(live, user_a, "book-a"),
        "b": _book(live, user_b, "book-b"),
        "c": _book(live, user_c, "book-c"),
    }
    tokens = {"a": token_a, "b": token_b, "c": token_c}

    ids = {}
    for key in ("a", "b", "c"):
        status, payload = _translate(live.server, books[key], tokens[key])
        assert status == 201, payload
        ids[key] = payload["id"]

    assert wait_for(lambda: live.pipeline.peak == 2)
    stats = web._scheduler().stats()
    assert stats["running"] == 2 and stats["queued"] == 1
    # Two slots, one book per user: exactly one user is waiting.
    waiting = [key for key in ids if ids[key] not in live.pipeline.started_at]
    assert len(waiting) == 1

    live.pipeline.release(ids["a"])
    assert wait_for(lambda: ids[waiting[0]] in live.pipeline.started_at)
    assert web._scheduler().stats()["queued"] == 0
