"""Create an account and set its password.

There is no sign-up form and there will not be one: an open registration page
on an application holding other people's shop data is a liability with no
upside at four users. Accounts are made here, by the operator, and the person
is told their password directly.

This exists BEFORE the sign-in gate on purpose. The accounts table defaults
password_hash to an empty string, and an empty hash verifies against nothing -
so a gate deployed before any account has a usable password locks everybody
out of the application, including whoever would have to fix it.

    uv run python scripts/manage_account.py list
    uv run python scripts/manage_account.py create levy --operator
    uv run python scripts/manage_account.py set-password levy
    uv run python scripts/manage_account.py set-store levy 1876

The password is read from a prompt, never from an argument. An argument ends
up in shell history and in the process list, where anyone on the box can read
it.
"""

from __future__ import annotations

import argparse
import getpass
import secrets
import sys

from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig
from bonuschef.portal.passwords import MIN_LENGTH, PasswordTooShort, hash_password
from bonuschef.portal.schema import ensure_account_tables


def _read_password(username: str) -> str:
    """Twice, because a typo here is locked in and only the operator can undo
    it. An empty answer generates one instead, which is the better default for
    an account whose owner will be told to change it anyway."""
    first = getpass.getpass(f"Password for {username} (blank to generate): ")
    if not first:
        generated = secrets.token_urlsafe(12)
        print(f"  generated: {generated}")
        return generated
    if first != getpass.getpass("Again: "):
        raise SystemExit("passwords did not match")
    return first


def _set_password(conn, username: str, *, must_change: bool) -> None:
    try:
        stored = hash_password(_read_password(username))
    except PasswordTooShort:
        raise SystemExit(f"password must be at least {MIN_LENGTH} characters") from None
    updated = conn.execute(
        text("""
            UPDATE public.accounts
            SET password_hash = :hash, must_change_password = :must_change
            WHERE lower(username) = lower(:username)
        """),
        {"hash": stored, "must_change": must_change, "username": username},
    ).rowcount
    if not updated:
        raise SystemExit(f"no account named {username!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("list", help="every account, without anything secret")

    create = sub.add_parser("create", help="make an account and set its password")
    create.add_argument("username")
    create.add_argument(
        "--operator",
        action="store_true",
        help="may start pipeline runs and edit the shared catalogue",
    )
    create.add_argument("--store-id", type=int, default=None)

    change = sub.add_parser("set-password", help="replace an account's password")
    change.add_argument("username")
    change.add_argument(
        "--no-force-change",
        action="store_true",
        help="do not require the owner to change it on first use",
    )

    store = sub.add_parser(
        "set-store", help="choose which Albert Heijn store an account reads"
    )
    store.add_argument("username")
    store.add_argument("store_id", type=int)

    args = parser.parse_args()
    engine = create_engine(DatabaseConfig.from_env().url)
    ensure_account_tables(engine)

    with engine.begin() as conn:
        if args.command == "list":
            rows = conn.execute(
                text("""
                    SELECT a.account_id, a.username, a.store_id, a.is_operator,
                           a.must_change_password, a.password_hash <> '' AS has_password,
                           s.name
                    FROM public.accounts AS a
                    LEFT JOIN public.ah_stores AS s ON s.store_id = a.store_id
                    ORDER BY a.account_id
                """)
            ).fetchall()
            if not rows:
                print("no accounts yet")
                return 0
            for r in rows:
                flags = []
                if r.is_operator:
                    flags.append("operator")
                if not r.has_password:
                    flags.append("NO PASSWORD - cannot sign in")
                if r.must_change_password:
                    flags.append("must change password")
                shop = f"AH {r.name}" if r.name else (r.store_id or "no store")
                print(
                    f"  {r.account_id:>3}  {r.username:<16} {shop!s:<34} "
                    f"{', '.join(flags)}"
                )
            return 0

        if args.command == "create":
            exists = conn.execute(
                text("SELECT 1 FROM public.accounts WHERE lower(username) = lower(:u)"),
                {"u": args.username},
            ).scalar()
            if exists:
                raise SystemExit(f"{args.username!r} already exists")
            conn.execute(
                text("""
                    INSERT INTO public.accounts (username, store_id, is_operator)
                    VALUES (:u, :s, :op)
                """),
                {"u": args.username, "s": args.store_id, "op": args.operator},
            )
            _set_password(conn, args.username, must_change=True)
            print(f"created {args.username!r}")
            return 0

        if args.command == "set-password":
            _set_password(conn, args.username, must_change=not args.no_force_change)
            print(f"password set for {args.username!r}")
            return 0

        if args.command == "set-store":
            name = conn.execute(
                text("SELECT name FROM public.ah_stores WHERE store_id = :s"),
                {"s": args.store_id},
            ).scalar()
            if name is None:
                raise SystemExit(
                    f"no store {args.store_id} in the directory; "
                    "run scripts/refresh_store_directory.py first"
                )
            updated = conn.execute(
                text(
                    "UPDATE public.accounts SET store_id = :s "
                    "WHERE lower(username) = lower(:u)"
                ),
                {"s": args.store_id, "u": args.username},
            ).rowcount
            if not updated:
                raise SystemExit(f"no account named {args.username!r}")
            print(f"{args.username!r} now reads AH {name}")
            return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
