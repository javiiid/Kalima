"""Phase 1.1: the v5 migration gives every legacy row an owner.

Before the schema version bump the domain tables had no ``user_id`` and the
uniqueness constraints were global (one glossary name for the whole install).
This builds a real v4 database, opens it with the current ``Database``, and
asserts the rows survive and move to the first user.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from app.storage.database import Database, SCHEMA_VERSION


DOMAIN_TABLES = (
    "jobs",
    "files",
    "library_books",
    "glossaries",
    "glossary_terms",
    "translation_memory",
    "translation_profiles",
    "calibrations",
)


def _legacy_database(path: Path) -> None:
    """Write the pre-Phase-1 (schema v4) shape with one row per domain table."""
    connection = sqlite3.connect(path)
    connection.executescript(
        """
        CREATE TABLE settings (key TEXT PRIMARY KEY, value_json TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE users (id INTEGER PRIMARY KEY AUTOINCREMENT, email TEXT NOT NULL UNIQUE,
            display_name TEXT NOT NULL DEFAULT '', password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE jobs (id TEXT PRIMARY KEY, filename TEXT NOT NULL, input_path TEXT NOT NULL,
            filetype TEXT NOT NULL, source_language TEXT NOT NULL, target_language TEXT NOT NULL,
            model TEXT NOT NULL, mode TEXT NOT NULL, status TEXT NOT NULL,
            progress_completed INTEGER NOT NULL DEFAULT 0, progress_total INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, output_path TEXT, error TEXT,
            estimated_cost REAL NOT NULL DEFAULT 0, input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0, retry_count INTEGER NOT NULL DEFAULT 0,
            archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE files (id INTEGER PRIMARY KEY AUTOINCREMENT, job_id TEXT, path TEXT NOT NULL,
            kind TEXT NOT NULL, size_bytes INTEGER NOT NULL DEFAULT 0, created_at TEXT NOT NULL,
            archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE glossaries (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            description TEXT DEFAULT '', created_at TEXT NOT NULL, updated_at TEXT NOT NULL);
        CREATE TABLE glossary_terms (id INTEGER PRIMARY KEY AUTOINCREMENT, glossary_id INTEGER NOT NULL,
            source_term TEXT NOT NULL, target_term TEXT NOT NULL, notes TEXT DEFAULT '',
            UNIQUE(glossary_id, source_term));
        CREATE TABLE translation_memory (id INTEGER PRIMARY KEY AUTOINCREMENT, source_text TEXT NOT NULL,
            translated_text TEXT NOT NULL, source_language TEXT NOT NULL, target_language TEXT NOT NULL,
            source TEXT DEFAULT 'manual', confidence REAL DEFAULT 1, last_used_at TEXT NOT NULL,
            UNIQUE(source_text, source_language, target_language));
        CREATE TABLE translation_profiles (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
            system_prompt TEXT NOT NULL, temperature REAL DEFAULT 0.2, preserve_html INTEGER DEFAULT 1,
            preserve_quotes INTEGER DEFAULT 1, glossary_id INTEGER, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL);
        CREATE TABLE library_books (id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
            author TEXT DEFAULT '', description TEXT DEFAULT '', cover_path TEXT,
            created_at TEXT NOT NULL, updated_at TEXT NOT NULL, archived INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE calibrations (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, data TEXT NOT NULL);

        INSERT INTO settings VALUES ('schema_version', '4', '2026-01-01T00:00:00+00:00');
        INSERT INTO users VALUES (7, 'legacy@example.com', 'Legacy', 'x',
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00');
        INSERT INTO jobs VALUES ('job1', 'book.epub', '/tmp/book.epub', 'epub', 'EN', 'FA',
            'gpt-5.6-luna', 'fast', 'completed', 1, 1,
            '2026-01-01T00:00:00+00:00', '2026-01-01T00:00:00+00:00', NULL, NULL, 0, 0, 0, 0, 0);
        INSERT INTO files VALUES (1, 'job1', '/tmp/book.epub', 'original', 10,
            '2026-01-01T00:00:00+00:00', 0);
        INSERT INTO glossaries VALUES (1, 'Legacy', '', 'now', 'now');
        INSERT INTO glossary_terms VALUES (1, 1, 'A', 'ب', '');
        INSERT INTO translation_memory VALUES (1, 'Hello', 'سلام', 'EN', 'FA', 'manual', 1, 'now');
        INSERT INTO translation_profiles VALUES (1, 'ادبی', 'p', 0.2, 1, 1, NULL, 'now', 'now');
        INSERT INTO library_books VALUES (1, 'Book', '', '', NULL, 'now', 'now', 0);
        INSERT INTO calibrations VALUES ('cal1', 0, '{}');
        """
    )
    connection.commit()
    connection.close()


def test_legacy_rows_move_to_the_first_user(tmp_path):
    path = tmp_path / "legacy.db"
    _legacy_database(path)

    database = Database(path)

    stored = database.fetch_one("SELECT value_json FROM settings WHERE key='schema_version'")
    assert json.loads(stored["value_json"]) == SCHEMA_VERSION

    for table in DOMAIN_TABLES:
        row = database.fetch_one(f"SELECT user_id FROM {table} LIMIT 1")
        assert row is not None, f"{table} lost its rows"
        assert int(row["user_id"]) == 7, f"{table} not back-filled to the first user"

    # The glossaries unique key is per user now, not global: a second user may
    # reuse a name that is already taken by the first.
    sql = database.fetch_one(
        "SELECT sql FROM sqlite_master WHERE type='table' AND name='glossaries'"
    )["sql"]
    assert "UNIQUE(user_id, name)" in sql
    database.execute(
        "INSERT INTO glossaries(user_id, name, description, created_at, updated_at)"
        " VALUES (8, 'Legacy', '', 'now', 'now')"
    )
    assert database.fetch_one(
        "SELECT COUNT(*) AS n FROM glossaries WHERE name='Legacy'"
    )["n"] == 2


def test_fresh_install_needs_no_legacy_data(tmp_path):
    database = Database(tmp_path / "fresh.db")
    assert database.fetch_one("SELECT COUNT(*) AS n FROM library_books")["n"] == 0
    # The seeded account is usable, so the first job is not blocked at dispatch.
    account = database.fetch_one("SELECT * FROM accounts WHERE id=1")
    assert account is not None
    assert int(account["credit_balance"]) > 0
