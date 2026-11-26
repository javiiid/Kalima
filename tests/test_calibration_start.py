"""A calibration session must never point at a job that does not exist.

``claim_start`` writes ``job_id`` before the in-memory job is created. When
the start failed -- or the server restarted first -- the workshop showed only
a link to a monitor page that answered 404. ``recover_missing_job`` puts such
a session back into the calibrated state so the user can start again.
"""
from __future__ import annotations

import threading

from app import web
from app.calibration import routes


class FakeStore:
    def __init__(self, session):
        self.session = session

    def change(self, identifier, action, revision=None):
        action(self.session)
        return self.session


def make_service(session):
    service = type("Service", (), {})()
    service.store = FakeStore(session)
    return service


def make_session(job_id="job-abc"):
    return {"id": "session-1", "revision": 4, "job_id": job_id,
            "state": "FULL_PROCESSING"}


def test_a_dangling_job_id_is_cleared(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path)
    session = make_session()
    service = make_service(session)

    result = routes.recover_missing_job(service, session)

    assert result["job_id"] is None
    assert result["state"] == "CALIBRATED_AND_ESTIMATED"
    assert result["revision"] == 5


def test_a_live_job_is_left_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path)
    session = make_session()
    service = make_service(session)
    web.JOBS.setdefault("job-abc", object())
    try:
        result = routes.recover_missing_job(service, session)
    finally:
        web.JOBS.pop("job-abc", None)

    assert result["job_id"] == "job-abc"
    assert result["state"] == "FULL_PROCESSING"


def test_a_persisted_job_is_left_alone(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path)
    (tmp_path / "job-abc.json").write_text("{}", encoding="utf-8")
    session = make_session()
    service = make_service(session)

    result = routes.recover_missing_job(service, session)

    assert result["job_id"] == "job-abc"


def test_a_session_without_a_job_is_untouched(monkeypatch, tmp_path):
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path)
    session = make_session(job_id=None)
    service = make_service(session)

    result = routes.recover_missing_job(service, session)

    assert result["job_id"] is None
    assert result["state"] == "FULL_PROCESSING"
