"""Seed a demo login on a fresh deployment.

Creates a user idempotently and gives it the standard free starting balance, so
a hosted instance can be shown without a real signup and without checkout
existing yet. Pair it with scripts/seed_demo_job.py for sample translation
output; the demo job seeds to the first user, so run this first.

Run: python scripts/seed_demo_user.py
     python scripts/seed_demo_user.py --email demo@example.com --password ...
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.account.service import ensure_account  # noqa: E402
from app.auth.service import signup  # noqa: E402
from app.storage.database import db  # noqa: E402

DEFAULT_EMAIL = "demo@kalima.local"
DEFAULT_PASSWORD = "kalima-demo-pass"
DEFAULT_NAME = "KALIMA Demo"


def seed(email: str, password: str, name: str) -> dict:
    user_id = None
    try:
        user = signup(db, email, password, name)
        user_id = int(user["id"])
        print(f"created demo user {email} (id={user_id})")
    except LookupError:
        row = db.fetch_one("SELECT id FROM users WHERE email=?", (email,))
        user_id = int(row["id"]) if row else None
        print(f"demo user {email} already exists (id={user_id}); leaving credentials as-is")
    if user_id is None:
        raise SystemExit("could not resolve the demo user id")
    account = ensure_account(user_id)
    print(
        f"account id={account['id']} plan={account.get('plan')} "
        f"credit_balance={account.get('credit_balance')}"
    )
    return {"user_id": user_id, "account": account}


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a demo KALIMA account.")
    parser.add_argument("--email", default=DEFAULT_EMAIL)
    parser.add_argument("--password", default=DEFAULT_PASSWORD)
    parser.add_argument("--name", default=DEFAULT_NAME)
    args = parser.parse_args()
    seed(args.email, args.password, args.name)
    print("\nlog in at the site with:")
    print(f"  email:    {args.email}")
    print(f"  password: {args.password}  (change this before any public demo)")


if __name__ == "__main__":
    main()
