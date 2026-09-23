"""Making an account from the page instead of from a shell.

Until now the only way to create one was ssh and a script, which is fine for
the person who owns the server and no good at all for the friends this is
being opened to.

## Why there is still a code

The spec decided invitation-only, and the reason it gave was per-user Albert
Heijn credentials - an open form on an application holding other people's shop
sessions. Those are gone: clearance turned out to be store-scoped, so one
credential serves everybody and no friend's session is stored at all.

What survives that is smaller but real: whoever can reach the page can make an
account. On the tailnet that is people already invited, so today the code buys
little. It is here for the deployment this is heading towards, where the page
is public and the alternative is discovering the problem from the accounts
table.

Loosening this to an open form is deleting one check. Tightening it after a
bot has found the page is not.

## What it deliberately is not

Not a password. It is a shared string that decides who may create an account,
and it is compared in constant time so it cannot be recovered a character at a
time. It does not authenticate anybody and it is not stored against the
account: once the account exists, the code has no further say.
"""

from __future__ import annotations

import hmac
import os
from dataclasses import dataclass

from sqlalchemy import text

from bonuschef.portal.passwords import (
    MIN_LENGTH,
    PasswordTooShort,
    hash_password,
)

_CODE = "BONUSCHEF_INVITE_CODE"

# Usernames a person can tell each other over the phone without spelling.
_MAX_USERNAME = 32
_MIN_USERNAME = 2


@dataclass(frozen=True)
class Registration:
    account_id: int = 0
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.account_id > 0


def registration_open() -> bool:
    """Whether the form is offered at all.

    Off unless a code is configured. A deployment that has not thought about
    who may register does not get an open form by default.
    """
    return bool(os.getenv(_CODE, "").strip())


def code_matches(supplied: str) -> bool:
    """Constant time, so the code cannot be recovered one character at a time
    by watching how long a refusal takes."""
    expected = os.getenv(_CODE, "").strip()
    if not expected:
        return False
    return hmac.compare_digest(supplied.strip(), expected)


def normalise_username(raw: str) -> str:
    return " ".join(raw.split()).strip()


def username_problem(username: str) -> str:
    """Why this username cannot be used, or "".

    Space is allowed inside but not at the edges, because a trailing space is
    invisible in a form and would make two accounts that look identical.
    """
    if len(username) < _MIN_USERNAME:
        return f"Kies een naam van minstens {_MIN_USERNAME} tekens."
    if len(username) > _MAX_USERNAME:
        return f"Kies een naam van hoogstens {_MAX_USERNAME} tekens."
    if any(ch in username for ch in "\t\n\r"):
        return "Gebruik geen regeleinden in je naam."
    return ""


def register(
    engine, username: str, password: str, again: str, code: str
) -> Registration:
    """Create an account, or say why not.

    Order matters. The code is checked first, so a wrong code costs nothing
    and reveals nothing about which usernames are taken - an open form that
    answers "already exists" is a way to enumerate the people using it.
    """
    if not code_matches(code):
        return Registration(error="Die uitnodigingscode klopt niet.")

    username = normalise_username(username)
    if problem := username_problem(username):
        return Registration(error=problem)

    if password != again:
        return Registration(error="De twee wachtwoorden zijn niet gelijk.")

    try:
        stored = hash_password(password)
    except PasswordTooShort:
        return Registration(
            error=f"Kies een wachtwoord van minstens {MIN_LENGTH} tekens."
        )

    with engine.begin() as conn:
        taken = conn.execute(
            text("SELECT 1 FROM public.accounts WHERE lower(username) = lower(:u)"),
            {"u": username},
        ).scalar()
        if taken:
            return Registration(error="Die naam is al in gebruik.")
        account_id = conn.execute(
            text("""
                INSERT INTO public.accounts
                    (username, password_hash, store_id, is_operator,
                     must_change_password)
                VALUES (:u, :h, NULL, FALSE, FALSE)
                RETURNING account_id
            """),
            {"u": username, "h": stored},
        ).scalar()

    # No store, deliberately. The next thing they see is the question of which
    # Albert Heijn they shop at, which is the one setting the app cannot guess
    # and must not default.
    #
    # Not an operator either. Starting pipeline runs and editing the shared
    # catalogue stay with whoever owns the server.
    return Registration(account_id=int(account_id or 0))
