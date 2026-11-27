"""Typed system settings: the allowlist, the ranges and the write boundary.

The System tab is admin-writable and everyone-readable. These tests pin the
three properties that make that safe: a non-admin can read but not write, a
value outside its declared range is rejected with the field name, and the
provider key is reported as a boolean rather than returned.
"""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest

from app import web
from app.auth import service as auth
from app.settings import service as settings
from app.storage.database import Database


@pytest.fixture
def config(tmp_path, monkeypatch):
    """An in-memory config.yaml the service reads and writes."""
    state = {"value": {"openai": {"api_key": "sk-live-super-secret"}}}
    writes: list[dict] = []

    def read():
        return json.loads(json.dumps(state["value"]))

    def write(value):
        writes.append(json.loads(json.dumps(value)))
        state["value"] = json.loads(json.dumps(value))

    monkeypatch.setattr(settings, "read_config_safe", read)
    monkeypatch.setattr(settings, "write_config", write)
    monkeypatch.delenv("KALIMA_JOB_SLOTS", raising=False)
    monkeypatch.delenv("KALIMA_JOBS_PER_USER", raising=False)
    return state, writes


def _item(payload, key):
    for section in payload["sections"]:
        for item in section["items"]:
            if item["key"] == key:
                return item
    raise AssertionError(f"{key} missing from {payload}")


def test_non_admin_reads_everything_but_cannot_edit(config):
    state, _ = config
    payload = settings.get_system_settings(None, is_admin=False)
    assert payload["meta"]["is_admin"] is False
    assert payload["meta"]["config_path"] is None
    assert _item(payload, "translation.max_concurrency")["editable"] is False
    assert _item(payload, "storage.auto_cleanup")["editable"] is False
    assert _item(payload, "storage.output_dir")["read_only"] is True
    assert state["value"]["openai"]["api_key"] not in json.dumps(payload)


def test_non_admin_cannot_write(config):
    with pytest.raises(PermissionError):
        settings.save_system_settings(None, {"translation.max_retries": 3}, is_admin=False)


def test_unknown_key_is_rejected_with_its_field(config):
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(None, {"nope.key": 1}, is_admin=True)
    assert caught.value.field == "nope.key"


def test_out_of_range_int_is_rejected(config):
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(
            None, {"translation.max_concurrency": 999}, is_admin=True
        )
    assert caught.value.field == "translation.max_concurrency"


def test_per_user_slots_cannot_exceed_total(config):
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(
            None,
            {
                "translation.max_parallel_jobs": 2,
                "translation.max_jobs_per_user": 3,
            },
            is_admin=True,
        )
    assert caught.value.field == "translation.max_jobs_per_user"


def test_per_user_slots_are_checked_against_the_default_total(config):
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(
            None, {"translation.max_jobs_per_user": 3}, is_admin=True
        )
    assert caught.value.field == "translation.max_jobs_per_user"


def test_admin_write_persists_only_the_allowlisted_values(config):
    state, writes = config
    payload = settings.save_system_settings(
        None,
        {
            "translation.max_retries": 7,
            "translation.retry_delay": 2.5,
            "storage.auto_cleanup": True,
            "limits.max_upload_mb": 2048,
        },
        is_admin=True,
    )
    assert writes[-1]["translation"]["max_retries"] == 7
    assert writes[-1]["translation"]["retry_delay"] == 2.5
    assert writes[-1]["storage"]["auto_cleanup"] is True
    assert writes[-1]["limits"]["max_upload_mb"] == 2048
    assert writes[-1]["openai"]["api_key"] == "sk-live-super-secret"
    assert _item(payload, "translation.max_retries")["value"] == 7
    assert state["value"]["limits"]["max_upload_mb"] == 2048


def test_read_only_paths_are_not_writable(config):
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(
            None, {"storage.output_dir": "/tmp/x"}, is_admin=True
        )
    assert caught.value.field == "storage.output_dir"


def test_env_override_locks_the_value(config, monkeypatch):
    monkeypatch.setenv("KALIMA_JOB_SLOTS", "3")
    payload = settings.get_system_settings(None, is_admin=True)
    item = _item(payload, "translation.max_parallel_jobs")
    assert item["source"] == "env"
    assert item["editable"] is False
    assert payload["meta"]["env_overrides"] == ["KALIMA_JOB_SLOTS"]
    with pytest.raises(settings.SettingsError) as caught:
        settings.save_system_settings(
            None, {"translation.max_parallel_jobs": 2}, is_admin=True
        )
    assert caught.value.field == "translation.max_parallel_jobs"


def test_unknown_model_is_rejected_and_empty_model_reports_the_effective_one(
    config, monkeypatch
):
    with pytest.raises(settings.SettingsError):
        settings.save_system_settings(
            None, {"translation.default_model": "not-a-model"}, is_admin=True
        )
    monkeypatch.setattr(settings, "resolve_default_model", lambda: "gpt-5.6-luna")
    payload = settings.get_system_settings(None, is_admin=True)
    assert _item(payload, "translation.default_model")["effective"] == "gpt-5.6-luna"


@pytest.fixture
def live(tmp_path, monkeypatch):
    database = Database(tmp_path / "settings.db")
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


def test_http_get_is_readable_and_put_is_admin_only(live, config):
    database, server = live
    admin, admin_token = _user(database, "admin@example.com")
    _other, other_token = _user(database, "other@example.com")

    status, payload = _call(server, "GET", "/api/settings", token=other_token)
    assert status == 200
    assert payload["meta"]["is_admin"] is False
    assert _item(payload, "translation.max_retries")["editable"] is False

    status, _ = _call(
        server,
        "PUT",
        "/api/settings",
        token=other_token,
        body={"translation.max_retries": 3},
    )
    assert status == 403

    status, payload = _call(
        server,
        "PUT",
        "/api/settings",
        token=admin_token,
        body={"translation.max_retries": 3},
    )
    assert status == 200
    assert _item(payload, "translation.max_retries")["value"] == 3

    status, payload = _call(
        server,
        "PUT",
        "/api/settings",
        token=admin_token,
        body={"translation.max_retries": 999},
    )
    assert status == 400
    assert payload["field"] == "translation.max_retries"
