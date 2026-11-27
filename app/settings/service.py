"""Typed system settings for the Settings page.

The old ``/api/settings`` route was a generic admin key/value dump: writing a
row there changed nothing the translator read. This module is the opposite
contract -- a small allowlist of keys that actually drive the runtime, each with
a type, a range, a source and a restart requirement.

Storage stays ``config/config.yaml`` because that is the only config source
(``AGENTS.md``). The service never returns the provider API key; it reports
``has_api_key`` instead.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import (
    CONFIG_FILE,
    DEFAULT_BASE_URL,
    MAX_UPLOAD_MB_CEILING,
    MAX_UPLOAD_MB_DEFAULT,
    MAX_PARALLEL_JOBS_DEFAULT,
    MAX_PARALLEL_JOBS_CEILING,
    MAX_TRANSLATION_CONCURRENCY,
    normalize_base_url,
    read_config_safe,
    write_config,
)
from app.core.models import is_supported_model, resolve_default_model
from app.core.paths import ensure_dir


class SettingsError(ValueError):
    """A rejected setting, carrying the dotted key that produced it."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field


@dataclass(frozen=True)
class SettingSpec:
    key: str
    section: str
    kind: str
    default: Any
    minimum: float | None = None
    maximum: float | None = None
    env: str | None = None
    read_only: bool = False
    restart_required: bool = False


# Order is the order the System tab renders: provider, translation, jobs,
# limits, then the read-only storage paths.
SETTING_SPECS: tuple[SettingSpec, ...] = (
    SettingSpec("openai.base_url", "provider", "url", DEFAULT_BASE_URL),
    SettingSpec("translation.default_model", "translation", "model", ""),
    SettingSpec(
        "translation.max_concurrency",
        "translation",
        "int",
        3,
        minimum=1,
        maximum=MAX_TRANSLATION_CONCURRENCY,
    ),
    SettingSpec(
        "translation.max_parallel_jobs",
        "jobs",
        "int",
        2,
        minimum=1,
        maximum=MAX_PARALLEL_JOBS_CEILING,
        env="KALIMA_JOB_SLOTS",
    ),
    SettingSpec(
        "translation.max_jobs_per_user",
        "jobs",
        "int",
        1,
        minimum=1,
        maximum=MAX_PARALLEL_JOBS_CEILING,
        env="KALIMA_JOBS_PER_USER",
    ),
    SettingSpec(
        "translation.max_retries",
        "translation",
        "int",
        5,
        minimum=1,
        maximum=20,
    ),
    SettingSpec(
        "translation.retry_delay",
        "translation",
        "float",
        5.0,
        minimum=0.5,
        maximum=120.0,
    ),
    SettingSpec(
        "translation.max_retry_delay",
        "translation",
        "float",
        80.0,
        minimum=1.0,
        maximum=600.0,
    ),
    SettingSpec(
        "limits.max_upload_mb",
        "limits",
        "int",
        MAX_UPLOAD_MB_DEFAULT,
        minimum=1,
        maximum=MAX_UPLOAD_MB_CEILING,
    ),
    SettingSpec(
        "storage.auto_cleanup",
        "storage",
        "bool",
        False,
    ),
    # Runtime paths are module constants today (``app/core/paths.py`` and the
    # web module's upload/output roots). Exposing them read-only is honest:
    # a field that writes a value nothing reads would be worse than no field.
    SettingSpec(
        "storage.output_dir",
        "storage",
        "string",
        str(ensure_dir("output") / "web"),
        read_only=True,
    ),
    SettingSpec(
        "storage.temp_dir",
        "storage",
        "string",
        str(ensure_dir("temp")),
        read_only=True,
    ),
)

SPEC_BY_KEY = {spec.key: spec for spec in SETTING_SPECS}


def _nested_get(config: dict, key: str) -> Any:
    node: Any = config
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return None
        node = node[part]
    return node


def _nested_set(config: dict, key: str, value: Any) -> None:
    parts = key.split(".")
    node = config
    for part in parts[:-1]:
        child = node.get(part)
        if not isinstance(child, dict):
            child = {}
            node[part] = child
        node = child
    node[parts[-1]] = value


def _env_value(spec: SettingSpec) -> str | None:
    if not spec.env:
        return None
    raw = os.environ.get(spec.env)
    return raw if raw not in (None, "") else None


def _source(spec: SettingSpec, config: dict) -> str:
    if _env_value(spec) is not None:
        return "env"
    if _nested_get(config, spec.key) is not None:
        return "config"
    return "default"


def _coerce(spec: SettingSpec, value: Any) -> Any:
    if spec.kind == "int":
        if isinstance(value, bool):
            raise SettingsError(spec.key, "مقدار باید عدد صحیح باشد.")
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(spec.key, "مقدار باید عدد صحیح باشد.") from exc
        if spec.minimum is not None and parsed < spec.minimum:
            raise SettingsError(spec.key, f"حداقل مقدار {int(spec.minimum)} است.")
        if spec.maximum is not None and parsed > spec.maximum:
            raise SettingsError(spec.key, f"حداکثر مقدار {int(spec.maximum)} است.")
        return parsed
    if spec.kind == "float":
        if isinstance(value, bool):
            raise SettingsError(spec.key, "مقدار باید عدد باشد.")
        try:
            parsed = float(value)
        except (TypeError, ValueError) as exc:
            raise SettingsError(spec.key, "مقدار باید عدد باشد.") from exc
        if spec.minimum is not None and parsed < spec.minimum:
            raise SettingsError(spec.key, f"حداقل مقدار {spec.minimum:g} است.")
        if spec.maximum is not None and parsed > spec.maximum:
            raise SettingsError(spec.key, f"حداکثر مقدار {spec.maximum:g} است.")
        return parsed
    if spec.kind == "bool":
        if isinstance(value, bool):
            return value
        text = str(value).strip().lower()
        if text in {"1", "true", "yes", "on"}:
            return True
        if text in {"0", "false", "no", "off"}:
            return False
        raise SettingsError(spec.key, "مقدار باید بله یا خیر باشد.")
    if spec.kind == "url":
        try:
            return normalize_base_url(value)
        except ValueError as exc:
            raise SettingsError(spec.key, str(exc)) from exc
    if spec.kind == "model":
        text = str(value or "").strip()
        if text and not is_supported_model(text):
            raise SettingsError(spec.key, "این مدل پشتیبانی نمی‌شود.")
        return text
    return str(value or "").strip()


def _item(spec: SettingSpec, config: dict, *, is_admin: bool) -> dict:
    source = _source(spec, config)
    raw = _env_value(spec)
    if raw is None:
        raw = _nested_get(config, spec.key)
    value = spec.default if raw is None else raw
    try:
        value = _coerce(spec, value)
    except SettingsError:
        value = spec.default
    item = {
        "key": spec.key,
        "section": spec.section,
        "type": spec.kind,
        "value": value,
        "default": spec.default,
        "source": source,
        "editable": bool(is_admin and not spec.read_only and source != "env"),
        "restart_required": spec.restart_required,
        "read_only": spec.read_only,
        "min": spec.minimum,
        "max": spec.maximum,
        "env": spec.env,
    }
    if spec.kind == "model" and not value:
        item["effective"] = resolve_default_model()
    return item


def _hosted() -> bool:
    return (os.environ.get("KALIMA_ENV") or "").strip().lower() in {"prod", "production"}


def get_system_settings(db, *, is_admin: bool) -> dict:
    """Return the typed settings, their sources and whether they are writable."""
    config = read_config_safe()
    sections: dict[str, list[dict]] = {"provider": [], "translation": [], "jobs": []}
    for spec in SETTING_SPECS:
        sections.setdefault(spec.section, []).append(_item(spec, config, is_admin=is_admin))

    provider = config.get("openai") or {}
    if not isinstance(provider, dict):
        provider = {}
    sections["provider"].insert(
        1,
        {
            "key": "openai.has_api_key",
            "section": "provider",
            "type": "bool",
            "value": bool(provider.get("api_key")),
            "default": False,
            "source": "config" if provider.get("api_key") else "default",
            "editable": False,
            "restart_required": False,
            "read_only": True,
            "min": None,
            "max": None,
            "env": None,
        },
    )

    updated_at = None
    try:
        updated_at = Path(CONFIG_FILE).stat().st_mtime
    except OSError:
        pass

    return {
        "sections": [
            {"key": key, "items": items}
            for key, items in sections.items()
            if items
        ],
        "meta": {
            "is_admin": bool(is_admin),
            "hosted": _hosted(),
            # A server filesystem path is not useful to a non-admin and is one
            # more local-build detail the hosted target should not leak.
            "config_path": str(CONFIG_FILE) if is_admin else None,
            "updated_at": updated_at,
            "env_overrides": [
                spec.env for spec in SETTING_SPECS if spec.env and _env_value(spec) is not None
            ],
        },
    }


def save_system_settings(db, patch: dict, *, is_admin: bool) -> dict:
    """Validate a flat ``{dotted.key: value}`` patch and persist config.yaml."""
    if not is_admin:
        raise PermissionError("تغییر تنظیمات سرور فقط برای مدیر مجاز است.")
    if not isinstance(patch, dict):
        raise SettingsError("settings", "بدنهٔ درخواست باید یک شیء JSON باشد.")

    config = read_config_safe()
    clean: dict[str, Any] = {}
    for key, value in patch.items():
        spec = SPEC_BY_KEY.get(str(key))
        if spec is None:
            raise SettingsError(str(key), "این تنظیم شناخته نمی‌شود.")
        if spec.read_only:
            raise SettingsError(str(key), "این تنظیم فقط‌خواندنی است.")
        if _env_value(spec) is not None:
            raise SettingsError(str(key), f"این مقدار با متغیر محیطی {spec.env} قفل شده است.")
        clean[spec.key] = _coerce(spec, value)

    merged = dict(config)
    for key, value in clean.items():
        _nested_set(merged, key, value)

    slots_spec = SPEC_BY_KEY["translation.max_parallel_jobs"]
    per_user_spec = SPEC_BY_KEY["translation.max_jobs_per_user"]
    slots = _env_value(slots_spec)
    if slots is None:
        slots = _nested_get(merged, "translation.max_parallel_jobs")
    per_user = _env_value(per_user_spec)
    if per_user is None:
        per_user = _nested_get(merged, "translation.max_jobs_per_user")
    try:
        slots_int = int(slots) if slots is not None else MAX_PARALLEL_JOBS_DEFAULT
        per_user_int = int(per_user) if per_user is not None else 1
    except (TypeError, ValueError):
        slots_int = per_user_int = None
    if slots_int is not None and per_user_int is not None and per_user_int > slots_int:
        raise SettingsError(
            "translation.max_jobs_per_user",
            "سهم هر کاربر نمی‌تواند از تعداد Job هم‌زمان بیشتر باشد.",
        )

    write_config(merged)
    return get_system_settings(db, is_admin=is_admin)
