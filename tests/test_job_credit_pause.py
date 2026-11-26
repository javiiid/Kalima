"""A job that runs out of credit must pause, not fail.

The ledger is empty, so every further chunk would be an unpaid provider call.
The job still has to stop, but as a *resumable pause* with an actionable
message and a structured event, not a generic "failed" that a resume cannot
recover from.
"""
from __future__ import annotations

import json

import app.web as web
from app.account.billing import InsufficientCredit


def _job(tmp_path) -> web.Job:
    source = tmp_path / "book.epub"
    source.write_bytes(b"x")
    return web.Job(
        "credit-1", "book.epub", source, "epub", 1,
        {"from_lang": "EN", "to_lang": "FA", "model": "m", "mode": "fast", "prompt": "", "debug": "true"},
        "EN", "FA", "m", "fast",
    )


def test_run_job_pauses_when_credit_is_exhausted(tmp_path, monkeypatch):
    monkeypatch.setattr(web, "JOB_META_DIR", tmp_path / "jobs")
    monkeypatch.setattr(web, "JOBS", {})
    monkeypatch.setattr(web, "user_output_dir", lambda user_id: tmp_path)
    job = _job(tmp_path)
    job.progress["completed"] = 542
    job.progress["total"] = 587
    web.JOBS[job.id] = job

    def exhausted(**kwargs):
        raise InsufficientCredit("اعتبار حساب کافی نیست.")

    monkeypatch.setattr(web, "translate", exhausted)
    web._run_job(job)

    assert job.status == "paused"
    assert "اعتبار" in (job.error or "")
    assert "542" in job.error and "45" in job.error

    events = web.db.fetch_all(
        "SELECT * FROM job_events WHERE job_id=? ORDER BY timestamp", (job.id,)
    )
    paused = [event for event in events if event["event"] == "paused"]
    assert paused, events
    assert paused[-1]["level"] == "WARNING"
    data = json.loads(paused[-1]["data_json"])
    assert data["error_code"] == "insufficient_credit"
    assert data["action"] == "top_up_and_resume"
    assert data["remaining"] == 45


def test_friendly_error_explains_credit_exhaustion():
    message = web._friendly_error(InsufficientCredit("اعتبار حساب کافی نیست."))
    assert "اعتبار" in message
    assert "ادامه" in message


def test_unknown_error_message_is_not_opaque():
    message = web._friendly_error(RuntimeError("provider exploded"))
    assert "provider exploded" in message
