"""Add credits to an account's balance.

The portal's "buy a package" only writes a ``pending`` billing row — no
payment provider is wired yet, so it never moves the balance. This is the
local-offline way to settle a purchase (or hand out a support credit) through
the same ledger the pre-dispatch guard reads.

Run by email:    python scripts/grant_credits.py --email you@mail.com --credits 500
Run by user id:  python scripts/grant_credits.py --user-id 2 --credits 500
With a note:     python scripts/grant_credits.py --email you@mail.com --credits 500 \\
                     --reference "support-comp" --amount-usd 25
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.account import billing  # noqa: E402
from app.storage.database import db  # noqa: E402


def resolve_user_id(email: str, user_id: int | None) -> int | None:
    if user_id is not None:
        return int(user_id)
    row = db.fetch_one("SELECT id FROM users WHERE email=?", (email,))
    return int(row["id"]) if row else None


def main() -> None:
    parser = argparse.ArgumentParser(description="Grant KALIMA credits to an account.")
    who = parser.add_mutually_exclusive_group(required=True)
    who.add_argument("--email", help="Account login email.")
    who.add_argument("--user-id", type=int, help="Numeric user id.")
    parser.add_argument("--credits", type=int, required=True, help="Credits to add.")
    parser.add_argument("--reference", default="admin-grant", help="Ledger reference label.")
    parser.add_argument("--amount-usd", type=float, default=0.0, help="USD value to record, for the audit trail only.")
    args = parser.parse_args()

    if args.credits <= 0:
        raise SystemExit("--credits must be positive.")

    uid = resolve_user_id(args.email or "", args.user_id)
    if uid is None:
        raise SystemExit(f"no user found for {args.email!r}")

    result = billing.grant(uid, args.credits, kind="grant",
                           reference_id=args.reference, amount_usd=args.amount_usd)
    print(f"user_id={uid} granted={result['credits']} new_balance={result['balance']}")


if __name__ == "__main__":
    main()
