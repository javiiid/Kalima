from app.account import service
from app.account import billing
from app.account.page import account_page
from app.core.web_i18n import inject_language_switcher
from app.storage.database import Database


def _use_temp_database(monkeypatch, tmp_path):
    database = Database(tmp_path / "account.db")
    monkeypatch.setattr(service, "db", database)
    return database


def test_account_portal_database_and_overview(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    overview = service.account_overview()
    assert overview["account"]["plan"] == "free"
    assert overview["counts"]["books"] == 0
    assert len(service.credit_packages()) == 3
    assert len(service.marketplace()) >= 4


def test_api_key_is_returned_once_and_stored_as_hash(monkeypatch, tmp_path):
    database = _use_temp_database(monkeypatch, tmp_path)
    created = service.create_api_key("Production")
    assert created["token"].startswith("jbt_live_")
    stored = database.fetch_one("SELECT * FROM account_api_keys WHERE id=?", (created["id"],))
    assert stored["token_hash"] != created["token"]
    assert "token" not in service.api_keys()[0]
    service.revoke_api_key(created["id"])
    assert service.api_keys()[0]["revoked_at"]


def test_checkout_order_and_business_request(monkeypatch, tmp_path):
    _use_temp_database(monkeypatch, tmp_path)
    checkout = service.start_checkout("credits", "starter")
    assert checkout["status"] == "pending"
    order = service.create_order({"title": "Medical Book", "word_count": 50000})
    assert order["status"] == "submitted"
    request = service.create_business_request({"request_type": "enterprise", "contact_name": "Test", "email": "team@example.com"})
    assert request["status"] == "new"


def test_grant_credits_lifts_balance_and_unblocks_charge(monkeypatch, tmp_path):
    database = _use_temp_database(monkeypatch, tmp_path)
    monkeypatch.setattr(billing, "db", database)
    billing.charge(1, billing.balance(1), "translation", "drain", require_positive=False)
    assert billing.balance(1) == 0

    result = billing.grant(1, 500, reference_id="admin-grant")
    assert result["credits"] == 500
    assert billing.balance(1) == 500

    billing.check_credit(1, 1)
    billing.charge(1, 1, "translation", "job")
    assert billing.balance(1) == 499

    ledger = database.fetch_all(
        "SELECT kind,credits,status FROM billing_transactions WHERE kind='grant'"
    )
    assert len(ledger) == 1
    assert ledger[0]["credits"] == 500 and ledger[0]["status"] == "committed"


def test_account_page_is_bilingual_and_feature_complete():
    page = account_page()
    assert 'data-section="publisher"' in page
    assert 'data-section="marketplace"' in page
    assert 'data-section="orders"' in page
    assert 'data-section="business"' in page
    assert 'data-en="Plans & credits"' in page
    assert "/api/account/portal" in page


def test_global_language_switcher_is_injected_once():
    page = inject_language_switcher("<html><body><p>کتابخانه</p></body></html>")
    assert page.count('id="global-language"') == 1
    assert '"کتابخانه": "Library"' in page
