"""User preferences: the settings page's contract with the backend.

Everything the settings page reads and writes goes through
:mod:`app.preferences.service`; the reading half of that contract is shared
with the reader through :mod:`app.preferences.reading`.
"""
from app.preferences.service import (
    PREF_DEFAULTS,
    PreferenceError,
    get_preferences,
    preferences_meta,
    reset_preferences,
    save_preferences,
)

__all__ = [
    "PREF_DEFAULTS",
    "PreferenceError",
    "get_preferences",
    "preferences_meta",
    "reset_preferences",
    "save_preferences",
]