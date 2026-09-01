#!/usr/bin/env python
"""Start the API.

    python run.py                # http://127.0.0.1:8000/api  (empty install)
    python run.py --reload       # auto-restart on edit
    python run.py --demo         # fill an empty database with showroom data
    python run.py --empty        # wipe everything back to one owner account
    python run.py --set-password --owner-email you@x.com --owner-password "..."
    python run.py --set-password --owner-email old@x.com --new-email you@real.com --owner-password "..."
    python run.py --port 9000

A fresh database comes up EMPTY: one owner account, no campaigns, no contacts.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def main() -> int:
    ap = argparse.ArgumentParser(description="MailPilot API")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--reload", action="store_true")
    ap.add_argument("--demo", action="store_true",
                    help="wipe and fill with showroom data (never use on a customer install)")
    ap.add_argument("--empty", action="store_true",
                    help="wipe everything back to a single owner account")
    ap.add_argument("--owner-email", default="", help="owner address for --empty / --set-password")
    ap.add_argument("--owner-password", default="", help="owner password for --empty / --set-password")
    ap.add_argument("--set-password", action="store_true",
                    help="reset one account's password without touching anything else")
    ap.add_argument("--new-email", default="",
                    help="also change the account's sign-in email (with --set-password)")
    args = ap.parse_args()

    # Resetting a forgotten password. Deliberately its own path: it changes ONE
    # row and never calls reset_db, so the mailbox connection, the API keys and
    # every campaign survive. Whoever can run this already owns the server, so
    # there is no privilege to escalate — but there is a lot to not destroy.
    if args.set_password:
        from app import db
        from app.security import hash_password
        if not args.owner_password:
            print("give --owner-password")
            return 2
        db.init_db()
        target = args.owner_email.strip().lower()
        row = (db.one("SELECT id, email FROM users WHERE lower(email) = ?", (target,))
               if target else
               db.one("SELECT id, email FROM users WHERE role = 'owner' ORDER BY created_at LIMIT 1"))
        if row is None:
            print(f"no such user: {args.owner_email or '(no owner found)'}")
            return 1
        changes = {"password_hash": hash_password(args.owner_password)}
        new_email = args.new_email.strip().lower()
        if new_email and new_email != row["email"].lower():
            # email is UNIQUE, so refuse a collision rather than letting the
            # write fail with a raw constraint error
            clash = db.one("SELECT 1 FROM users WHERE lower(email) = ? AND id != ?",
                           (new_email, row["id"]))
            if clash:
                print(f"another account already uses {new_email}")
                return 1
            changes["email"] = new_email
        db.update("users", row["id"], changes)
        who = changes.get("email", row["email"])
        print(f"password reset for {who}" + (" (email changed)" if "email" in changes else ""))
        return 0

    if args.demo and args.empty:
        print("--demo and --empty ask for opposite things; pick one")
        return 2

    if args.demo:
        from app.seed import seed
        seed(force=True)
        print("database filled with demo data")
    elif args.empty:
        from app import db
        from app.seed import bootstrap
        db.init_db()
        db.reset_db()
        bootstrap(args.owner_email, args.owner_password)
        print("database reset to an empty installation")

    import uvicorn
    uvicorn.run("app.main:app", host=args.host, port=args.port, reload=args.reload, log_level="info")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
