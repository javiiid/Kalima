# ============================================================
# Translation memory engine tests
# ============================================================
#
# Before any provider API call the engine exact-matches the chunk in
# translation_memory; on a hit the stored translation is served with zero
# API cost. After every successful chunk the pair is stored back.
#
# A hit requires the same translation profile (model, prompt, style, glossary),
# so the same source text under two different profiles must never collide.
#
# No real API request is sent. No API tokens are consumed.
#
# ============================================================

from app.storage.database import Database
from app.translation import memory
from app.translation import translator
from app.translation.translator import (
    process_translations,
    translate_chunk,
)


# ============================================================
# FAKES
# ============================================================

class FakeMessage:
    def __init__(self, content):
        self.content = content


class FakeChoice:
    def __init__(self, content):
        self.message = FakeMessage(content)


class FakeResponse:
    def __init__(self, content):
        self.choices = [FakeChoice(content)]


class FakeCompletions:
    """Count every API call; always succeed with fixed Persian text."""

    def __init__(self):
        self.calls = 0
        self.messages = []

    def create(self, model, messages, temperature, **kwargs):
        self.calls += 1
        self.messages.append(messages)
        return FakeResponse("متن ترجمه‌شده")


class FakeChat:
    def __init__(self, completions):
        self.completions = completions


class FakeClient:
    def __init__(self, completions):
        self.chat = FakeChat(completions)


def make_client():
    completions = FakeCompletions()
    return FakeClient(completions), completions


def make_database(tmp_path):
    return Database(tmp_path / "memory.db")


def make_paths(tmp_path):
    return {
        "job_dir": tmp_path,
        "translations_file": tmp_path / "translations.json",
    }


def profile(**overrides):
    """A hand-built profile for direct lookup/store tests."""
    values = dict(
        model="gpt-5.6-luna",
        filetype="epub",
        prompt="Translate faithfully.",
        prompt_version=1,
        style_key="literary",
        style_preset={"prompt_insert": "[STYLE: LITERARY]"},
        glossary_terms=[],
        glossary_version=0,
    )
    values.update(overrides)
    return memory.build_profile(**values)


def engine_profile(**overrides):
    """The exact profile ``translate_chunk`` computes for the test defaults."""
    values = dict(
        model="gpt-5.6-luna",
        filetype="epub",
        system_prompt_text=None,
        style_preset=None,
        text="Hello world.",
        glossary_snapshot=None,
        from_lang="EN",
        to_lang="FA",
    )
    values.update(overrides)
    return translator._memory_profile(**values)


# ============================================================
# LOOKUP / STORE
# ============================================================

def test_lookup_miss_returns_none(tmp_path):
    database = make_database(tmp_path)
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) is None
    # A miss writes nothing.
    assert database.fetch_all("SELECT * FROM translation_memory") == []


def test_store_then_lookup_hit_refreshes_last_used(tmp_path):
    database = make_database(tmp_path)
    memory.store(database, "Hello world.", "سلام دنیا.", "EN", "FA", profile=profile())
    row = database.fetch_one("SELECT source, confidence, profile_version FROM translation_memory")
    assert row["source"] == "auto"
    assert row["confidence"] == 1.0
    assert row["profile_version"] == 1
    database.execute("UPDATE translation_memory SET last_used_at='2000-01-01T00:00:00+00:00'")
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) == "سلام دنیا."
    refreshed = database.fetch_one("SELECT last_used_at FROM translation_memory")
    assert refreshed["last_used_at"] != "2000-01-01T00:00:00+00:00"


def test_lookup_is_scoped_by_language_pair(tmp_path):
    database = make_database(tmp_path)
    memory.store(database, "Hello world.", "سلام دنیا.", "EN", "FA", profile=profile())
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) == "سلام دنیا."
    assert memory.lookup(database, "Hello world.", "EN", "DE", profile=profile()) is None
    assert memory.lookup(database, "Hello world.", "DE", "FA", profile=profile()) is None


def test_store_upsert_updates_translation_on_conflict(tmp_path):
    database = make_database(tmp_path)
    memory.store(database, "Hello world.", "سلام دنیا.", "EN", "FA", profile=profile())
    memory.store(database, "Hello world.", "سلام دنیا!", "EN", "FA", profile=profile())
    rows = database.fetch_all("SELECT translated_text FROM translation_memory")
    assert [row["translated_text"] for row in rows] == ["سلام دنیا!"]
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) == "سلام دنیا!"


def test_store_refuses_empty_inputs(tmp_path):
    database = make_database(tmp_path)
    memory.store(database, "", "سلام.", "EN", "FA", profile=profile())
    memory.store(database, "Hello.", "", "EN", "FA", profile=profile())
    assert database.fetch_all("SELECT * FROM translation_memory") == []


def test_lookup_failure_is_a_miss_not_a_crash(tmp_path):
    class BrokenDb:
        def fetch_one(self, sql, params=()):
            raise RuntimeError("disk gone")

        def execute(self, sql, params=()):
            raise RuntimeError("disk gone")

    assert memory.lookup(BrokenDb(), "Hello world.", "EN", "FA", profile=profile()) is None
    # And storing into it must not raise either.
    memory.store(BrokenDb(), "Hello world.", "سلام دنیا.", "EN", "FA", profile=profile())


# ============================================================
# PROFILE ISOLATION
# ============================================================

def test_same_text_different_style_does_not_collide(tmp_path):
    database = make_database(tmp_path)
    literary = profile(style_key="literary", style_preset={"prompt_insert": "literary"})
    technical = profile(style_key="technical", style_preset={"prompt_insert": "technical"})
    memory.store(database, "Hello world.", "سلام ادبی.", "EN", "FA", profile=literary)
    memory.store(database, "Hello world.", "سلام فنی.", "EN", "FA", profile=technical)
    assert database.fetch_one("SELECT COUNT(*) AS n FROM translation_memory")["n"] == 2
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=literary) == "سلام ادبی."
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=technical) == "سلام فنی."


def test_same_text_different_model_does_not_collide(tmp_path):
    database = make_database(tmp_path)
    primary = profile(model="gpt-5.6-luna")
    fallback = profile(model="gpt-5.6-terra")
    memory.store(database, "Hello world.", "سلام لونا.", "EN", "FA", profile=primary)
    memory.store(database, "Hello world.", "سلام ترا.", "EN", "FA", profile=fallback)
    assert database.fetch_one("SELECT COUNT(*) AS n FROM translation_memory")["n"] == 2
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=primary) == "سلام لونا."
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=fallback) == "سلام ترا."


def test_same_text_different_prompt_does_not_collide(tmp_path):
    database = make_database(tmp_path)
    first = profile(prompt="Translate literally.")
    second = profile(prompt="Translate freely.")
    memory.store(database, "Hello world.", "سلام یک.", "EN", "FA", profile=first)
    memory.store(database, "Hello world.", "سلام دو.", "EN", "FA", profile=second)
    assert database.fetch_one("SELECT COUNT(*) AS n FROM translation_memory")["n"] == 2
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=first) == "سلام یک."
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=second) == "سلام دو."


def test_same_text_different_glossary_does_not_collide(tmp_path):
    database = make_database(tmp_path)
    plain = profile(glossary_terms=[], glossary_version=0)
    glossed = profile(
        glossary_terms=[{"source_term": "Hello", "target_term": "درود"}],
        glossary_version=1,
    )
    memory.store(database, "Hello world.", "سلام دنیا.", "EN", "FA", profile=plain)
    memory.store(database, "Hello world.", "درود دنیا.", "EN", "FA", profile=glossed)
    assert database.fetch_one("SELECT COUNT(*) AS n FROM translation_memory")["n"] == 2
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=plain) == "سلام دنیا."
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=glossed) == "درود دنیا."


def test_fingerprint_is_stable_and_order_independent(tmp_path):
    terms = [
        {"source_term": "B", "target_term": "ب"},
        {"source_term": "A", "target_term": "ا"},
    ]
    first = profile(glossary_terms=terms)
    second = profile(glossary_terms=list(reversed(terms)))
    assert memory.build_fingerprint(1, "text", "EN", "FA", first) == \
        memory.build_fingerprint(1, "text", "EN", "FA", second)
    # A different owner must never share a fingerprint.
    assert memory.build_fingerprint(1, "text", "EN", "FA", first) != \
        memory.build_fingerprint(2, "text", "EN", "FA", first)


def test_legacy_rows_are_never_served(tmp_path):
    database = make_database(tmp_path)
    database.execute(
        "INSERT INTO translation_memory(user_id, source_text, translated_text,"
        " source_language, target_language, source, confidence, last_used_at,"
        " translation_fingerprint, profile_version, profile_json)"
        " VALUES (1, 'Hello world.', 'سلام قدیمی.', 'EN', 'FA', 'auto', 1, 'now',"
        " 'legacy:1', 0, '{\"legacy\":true}')"
    )
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) is None


def test_manual_rows_are_never_served(tmp_path):
    database = make_database(tmp_path)
    fingerprint = memory.manual_fingerprint(1, "Hello world.", "EN", "FA")
    database.execute(
        "INSERT INTO translation_memory(user_id, source_text, translated_text,"
        " source_language, target_language, source, confidence, last_used_at,"
        " translation_fingerprint, profile_version, profile_json)"
        " VALUES (1, 'Hello world.', 'سلام دستی.', 'EN', 'FA', 'manual', 1, 'now',"
        " ?, 0, '{\"manual\":true}')",
        (fingerprint,),
    )
    assert memory.lookup(database, "Hello world.", "EN", "FA", profile=profile()) is None


# ============================================================
# TRANSLATE_CHUNK
# ============================================================

def test_translate_chunk_serves_from_memory_with_zero_api_calls(tmp_path):
    database = make_database(tmp_path)
    memory.store(
        database, "Hello world.", "سلام دنیا.", "EN", "FA",
        profile=engine_profile(),
    )
    client, completions = make_client()
    record = []
    result = translate_chunk(
        client=client,
        text="Hello world.",
        chunk_id="chunk-0",
        from_lang="EN",
        to_lang="FA",
        model="gpt-5.6-luna",
        filetype="epub",
        memory_db=database,
        memory_record=record,
    )
    assert result == "سلام دنیا."
    assert completions.calls == 0
    assert record == ["chunk-0"]


def test_translate_chunk_writes_back_after_api_success(tmp_path):
    database = make_database(tmp_path)
    client, completions = make_client()
    result = translate_chunk(
        client=client,
        text="Hello world.",
        chunk_id="chunk-0",
        from_lang="EN",
        to_lang="FA",
        model="gpt-5.6-luna",
        filetype="epub",
        memory_db=database,
    )
    assert result == "متن ترجمه‌شده"
    assert completions.calls == 1
    assert memory.lookup(
        database, "Hello world.", "EN", "FA", profile=engine_profile()
    ) == "متن ترجمه‌شده"


def test_translate_chunk_profile_mismatch_pays_again(tmp_path):
    database = make_database(tmp_path)
    client, completions = make_client()

    def run(style):
        return translate_chunk(
            client=client,
            text="Hello world.",
            chunk_id="chunk-0",
            from_lang="EN",
            to_lang="FA",
            model="gpt-5.6-luna",
            filetype="epub",
            style_preset=style,
            memory_db=database,
        )

    run("literary")
    assert completions.calls == 1
    run("technical")
    assert completions.calls == 2
    # The literary row is still there and is served without another call.
    run("literary")
    assert completions.calls == 2


def test_test_mode_never_touches_memory(tmp_path):
    database = make_database(tmp_path)
    client, completions = make_client()
    result = translate_chunk(
        client=client,
        text="Hello world.",
        chunk_id="chunk-0",
        from_lang="EN",
        to_lang="FA",
        model="gpt-5.6-luna",
        filetype="epub",
        test_translations={"chunk-0": "ترجمهٔ آزمایشی"},
        memory_db=database,
    )
    assert result == "ترجمهٔ آزمایشی"
    assert completions.calls == 0
    assert database.fetch_all("SELECT * FROM translation_memory") == []


# ============================================================
# END TO END
# ============================================================

def test_memory_bypass_pays_for_fresh_and_writes_nothing(tmp_path):
    database = make_database(tmp_path)
    memory.store(database, "Hello world.", "سلام دنیا.", "EN", "FA", profile=engine_profile())
    client, completions = make_client()
    result = translate_chunk(
        client=client,
        text="Hello world.",
        chunk_id="chunk-0",
        from_lang="EN",
        to_lang="FA",
        model="gpt-5.6-luna",
        filetype="epub",
        memory_db=False,
    )
    assert result == "متن ترجمه‌شده"
    assert completions.calls == 1
    translate_chunk(
        client=client,
        text="Brand new sentence.",
        chunk_id="chunk-1",
        from_lang="EN",
        to_lang="FA",
        model="gpt-5.6-luna",
        filetype="epub",
        memory_db=False,
    )
    assert completions.calls == 2
    assert memory.lookup(
        database, "Brand new sentence.", "EN", "FA",
        profile=engine_profile(text="Brand new sentence."),
    ) is None


def test_second_run_of_same_chunks_costs_zero_api_calls(tmp_path):
    database = make_database(tmp_path)
    from app.storage import database as database_module

    # Route the engine's lazy singleton at this test's database.
    previous, database_module.db = database_module.db, database
    try:
        client, completions = make_client()
        chunks = [(f"chunk-{i}", f"Repeated heading {i}.") for i in range(2)]
        first, _, _ = process_translations(
            client, chunks, {}, "resume", "EN", "FA",
            make_paths(tmp_path), model="gpt-5.6-luna", filetype="epub",
        )
        assert completions.calls == 2
        second, _, _ = process_translations(
            client, chunks, {}, "resume", "EN", "FA",
            make_paths(tmp_path), model="gpt-5.6-luna", filetype="epub",
        )
        assert completions.calls == 2
        assert second == first
    finally:
        database_module.db = previous


def test_concurrent_path_uses_memory(monkeypatch, tmp_path):
    database = make_database(tmp_path)
    from app.storage import database as database_module

    previous, database_module.db = database_module.db, database
    monkeypatch.setattr(translator, "_translation_concurrency", lambda: 4)
    monkeypatch.setattr(translator, "_build_rate_limiter", lambda concurrency: None)
    try:
        memory.store(
            database, "Repeated heading.", "تیتر تکراری.", "EN", "FA",
            profile=engine_profile(text="Repeated heading."),
        )
        client, completions = make_client()
        chunks = [
            ("chunk-0", "Repeated heading."),
            ("chunk-1", "Fresh sentence one."),
            ("chunk-2", "Fresh sentence two."),
        ]
        translations, _, _ = process_translations(
            client, chunks, {}, "fast", "EN", "FA",
            make_paths(tmp_path), model="gpt-5.6-luna", filetype="epub",
        )
        assert completions.calls == 2
        assert translations["chunk-0"] == "تیتر تکراری."
        assert translations["chunk-1"] == "متن ترجمه‌شده"
        assert translations["chunk-2"] == "متن ترجمه‌شده"
    finally:
        database_module.db = previous


def test_concurrent_path_applies_style_preset(monkeypatch, tmp_path):
    database = make_database(tmp_path)
    from app.storage import database as database_module

    previous, database_module.db = database_module.db, database
    monkeypatch.setattr(translator, "_translation_concurrency", lambda: 4)
    monkeypatch.setattr(translator, "_build_rate_limiter", lambda concurrency: None)
    try:
        client, completions = make_client()
        process_translations(
            client, [("chunk-0", "Fresh sentence.")], {}, "fast", "EN", "FA",
            make_paths(tmp_path), model="gpt-5.6-luna", filetype="epub",
            style_preset="technical",
        )
        assert completions.calls == 1
        system_messages = [
            message["content"]
            for messages in completions.messages
            for message in messages
            if message["role"] == "system"
        ]
        assert any("[STYLE: TECHNICAL]" in content for content in system_messages)
    finally:
        database_module.db = previous
