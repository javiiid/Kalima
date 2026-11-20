"""The scheduler's capacity comes from config, with an env escape hatch."""
from __future__ import annotations

from app.core import config


def _settings(monkeypatch, translation=None, env=None):
    monkeypatch.setattr(config, "get_translation_config", lambda: dict(translation or {}))
    for key in ("KALIMA_JOB_SLOTS", "KALIMA_JOBS_PER_USER"):
        monkeypatch.delenv(key, raising=False)
    for key, value in (env or {}).items():
        monkeypatch.setenv(key, value)
    return config.get_scheduler_config()


def test_defaults_are_one_book_per_user_and_two_slots(monkeypatch):
    settings = _settings(monkeypatch)
    assert settings == {"max_parallel_jobs": 2, "max_jobs_per_user": 1}


def test_config_values_are_honored(monkeypatch):
    settings = _settings(
        monkeypatch, {"max_parallel_jobs": 3, "max_jobs_per_user": 2}
    )
    assert settings == {"max_parallel_jobs": 3, "max_jobs_per_user": 2}


def test_slots_are_capped_and_per_user_is_clamped_to_slots(monkeypatch):
    assert _settings(monkeypatch, {"max_parallel_jobs": 99})["max_parallel_jobs"] == (
        config.MAX_PARALLEL_JOBS_CEILING
    )
    settings = _settings(monkeypatch, {"max_parallel_jobs": 1, "max_jobs_per_user": 5})
    assert settings == {"max_parallel_jobs": 1, "max_jobs_per_user": 1}


def test_env_overrides_config(monkeypatch):
    settings = _settings(
        monkeypatch,
        {"max_parallel_jobs": 3, "max_jobs_per_user": 2},
        {"KALIMA_JOB_SLOTS": "4", "KALIMA_JOBS_PER_USER": "1"},
    )
    assert settings == {"max_parallel_jobs": 4, "max_jobs_per_user": 1}


def test_garbage_and_zero_fall_back_to_safe_values(monkeypatch):
    settings = _settings(monkeypatch, {"max_parallel_jobs": "many", "max_jobs_per_user": 0})
    assert settings == {"max_parallel_jobs": 2, "max_jobs_per_user": 1}
