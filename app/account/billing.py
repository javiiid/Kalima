"""Server-side credit ledger and pre-dispatch balance guard.

The account portal used to display a balance that nothing checked. This module
is the one place that spends it: jobs reserve a minimum of one credit before
any provider call, and calibration settles its measured USD cost into the same
ledger. There is deliberately no second budget system here -- the existing
calibration budget guard still owns per-book token/cost caps.
"""
from __future__ import annotations

import math

from app.account.service import ensure_account, now
from app.storage.database import db

CREDIT_USD = 0.05


class InsufficientCredit(ValueError):
    """The caller has no credit left (or not enough for the reservation)."""


def credits_for_usd(amount_usd: float) -> int:
    try:
        amount = max(0.0, float(amount_usd or 0))
    except (TypeError, ValueError):
        amount = 0.0
    if amount <= 0:
        return 0
    return max(1, int(math.ceil(amount / CREDIT_USD)))


def balance(user_id: int = 1) -> int:
    return int(ensure_account(user_id).get("credit_balance") or 0)


def check_credit(user_id: int = 1, credits: int = 1, *, require_positive: bool = True) -> int:
    """Raise ``InsufficientCredit`` when the ledger cannot cover ``credits``."""
    available = balance(user_id)
    needed = max(0, int(credits))
    if (require_positive and available <= 0) or available < needed:
        raise InsufficientCredit("اعتبار حساب کافی نیست. برای ادامه، بستهٔ اعتبار تهیه کنید.")
    return available


def charge(user_id: int, credits: int, kind: str, reference_id: str = "",
           amount_usd: float = 0.0, *, require_positive: bool = True) -> dict:
    """Atomically debit credits and append a ledger row.

    The read/check/update runs under the database lock so two worker threads
    cannot both spend the final credit.
    """
    uid = int(user_id)
    ensure_account(uid)
    needed = max(0, int(credits))
    with db._lock, db.connect() as connection:
        row = connection.execute(
            "SELECT id,credit_balance FROM accounts WHERE user_id=?", (uid,)
        ).fetchone()
        if row is None:
            raise InsufficientCredit("حساب مالی پیدا نشد.")
        available = int(row["credit_balance"] or 0)
        if (require_positive and available <= 0) or available < needed:
            raise InsufficientCredit("اعتبار حساب کافی نیست. برای ادامه، بستهٔ اعتبار تهیه کنید.")
        connection.execute(
            "UPDATE accounts SET credit_balance=?,updated_at=? WHERE user_id=?",
            (available - needed, now(), uid),
        )
        connection.execute(
            "INSERT INTO billing_transactions(account_id,kind,reference_id,amount_usd,credits,status,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (int(row["id"]), kind[:40], str(reference_id)[:120], float(amount_usd or 0),
             -needed, "committed", now()),
        )
    return {"credits": -needed, "balance": available - needed}


def spend_usd(user_id: int, amount_usd: float, kind: str, reference_id: str = "",
              *, minimum_credits: int = 0, require_positive: bool = True) -> dict:
    """Record measured provider spend and debit its credit equivalent.

    ``require_positive=False`` is for *post* provider calls: the money is
    already spent, so the ledger records it instead of raising and losing the
    audit row. Pre-dispatch callers keep the default and are refused up front.
    """
    amount = max(0.0, float(amount_usd or 0))
    credits = max(int(minimum_credits), credits_for_usd(amount))
    return charge(user_id, credits, kind, reference_id, amount_usd=amount,
                  require_positive=require_positive)

def grant(user_id: int, credits: int, kind: str = "grant", reference_id: str = "",
          amount_usd: float = 0.0) -> dict:
    """Credit a balance and append a matching ledger row.

    The only counterpart to ``charge``. Checkout writes a ``pending`` row and
    waits for a payment provider, so nothing could actually add credits until
    one is connected; this is the path an admin script or a payment webhook
    settles a completed purchase through. Atomic for the same reason as
    ``charge``: two concurrent grants must not lose one another's update.
    """
    uid = int(user_id)
    ensure_account(uid)
    added = max(0, int(credits))
    with db._lock, db.connect() as connection:
        row = connection.execute(
            "SELECT id,credit_balance FROM accounts WHERE user_id=?", (uid,)
        ).fetchone()
        if row is None:
            raise InsufficientCredit("حساب مالی پیدا نشد.")
        balance = int(row["credit_balance"] or 0) + added
        connection.execute(
            "UPDATE accounts SET credit_balance=?,updated_at=? WHERE user_id=?",
            (balance, now(), uid),
        )
        connection.execute(
            "INSERT INTO billing_transactions(account_id,kind,reference_id,amount_usd,credits,status,created_at)"
            " VALUES (?,?,?,?,?,?,?)",
            (int(row["id"]), kind[:40], str(reference_id)[:120], float(amount_usd or 0),
             added, "committed", now()),
        )
    return {"credits": added, "balance": balance}
