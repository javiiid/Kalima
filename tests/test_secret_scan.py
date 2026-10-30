"""The release-hygiene secret scanner must catch real shapes and ignore code."""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "scan_secrets.py"


@pytest.fixture(scope="module")
def scanner():
    spec = importlib.util.spec_from_file_location("scan_secrets", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_flags_a_fresh_openai_style_key(scanner):
    scanners = scanner
    scanners.ALLOWED = set()
    labels = scanners.matches('const key = "sk-' + "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8S9t0" + '"')
    assert "OpenAI-style API key" in labels


def test_allowlisted_value_is_skipped(scanner):
    scanners = scanner
    value = "sk-" + "Z" * 40
    scanners.ALLOWED = {value}
    assert scanners.matches(f"x = '{value}'") == []
    scanners.ALLOWED = set()
    assert scanners.matches(f"x = '{value}'")


def test_code_expressions_are_not_credentials(scanner):
    scanners = scanner
    scanners.ALLOWED = set()
    # An i18n key and a token *prefix* under construction, not secrets.
    assert scanners.matches("password: 'account.security.method.password',") == []
    assert scanners.matches('token = "jbt_live_"') == []
    assert scanners._looks_secret("account.security.method.password") is False
    assert scanners._looks_secret("jbt_live_") is False
    assert scanners._looks_secret("Xy9k2mNp4qRs7tUv") is True
