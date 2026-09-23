"""Who is signed in, and for how long.

Sessions live in Postgres rather than in ``st.session_state``. Streamlit's
session state is per-websocket-connection: a reload, a phone backgrounding the
tab long enough to drop the socket, or a container restart all produce a fresh
empty session, and this deployment restarts on every release.

The table stores a HASH of the session token, never the token. A database read
must not yield a working session, for the same reason it must not yield a
password.

Time is injected. Everything here is about expiry, and a test that has to wait
out a real clock either sleeps or asserts nothing.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import text

from bonuschef.portal.passwords import needs_rehash, verify_password

# How long a session survives without being used. Long enough that cooking
# from a phone in a shop does not end in a sign-in form; short enough that a
# borrowed laptop is not indefinite.
IDLE_LIFETIME = timedelta(days=14)

# The sign-in form's answer when it does not want to say. Failure must not
# distinguish an unknown username from a wrong password, or the form becomes a
# way to enumerate who has an account.
_REFUSED = "Gebruikersnaam of wachtwoord klopt niet."


def _now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class Account:
    account_id: int
    username: str
    store_id: int | None
    is_operator: bool
    must_change_password: bool


# Who the pages act for when there is no wall.
#
# Account 0 rather than None, so every reader and writer takes the same shape
# whether or not sign-in is required. It is also the id the verdict backfill
# uses for rows that predate accounts, which keeps a single-user deployment's
# existing decisions attached to the person still making them.
SINGLE_USER = Account(
    account_id=0,
    username="",
    store_id=None,
    is_operator=True,
    must_change_password=False,
)


@dataclass(frozen=True)
class SignInResult:
    """Either a session or a reason, never both."""

    token: str = ""
    account: Account | None = None
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.account is not None


def token_hash(token: str) -> str:
    """SHA-256, not a password hash.

    A session token is 32 bytes of randomness that this system generated, so
    there is nothing to guess and no dictionary to run. The reason to hash it
    is to keep a database read from yielding a usable session - and a slow
    hash here would be paid on every rerun of every page.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


# How many wrong answers before a pause, and how long the pause lasts.
#
# Five is generous for somebody typing their own password and useless for
# anybody working through a list. Fifteen minutes is long enough that a
# dictionary takes years and short enough that a person who mistyped theirs
# five times can go and make tea.
MAX_FAILURES = 5
LOCKOUT = timedelta(minutes=15)

_THROTTLED = "Te veel pogingen. Probeer het over een kwartier opnieuw."


def _recent_failures(conn, username: str, stamp: datetime) -> int:
    return int(
        conn.execute(
            text("""
                SELECT count(*) FROM public.sign_in_attempts
                WHERE lower(username) = lower(:u) AND failed_at > :since
            """),
            {"u": username, "since": stamp - LOCKOUT},
        ).scalar()
        or 0
    )


def _record_failure(conn, username: str, stamp: datetime) -> None:
    conn.execute(
        text(
            "INSERT INTO public.sign_in_attempts (username, failed_at) VALUES (:u, :t)"
        ),
        {"u": username, "t": stamp},
    )


def _clear_failures(conn, username: str) -> None:
    """A correct password ends the lockout.

    Otherwise somebody who mistyped five times and then remembered it would
    still be shut out, which punishes the person the throttle is protecting.
    """
    conn.execute(
        text("DELETE FROM public.sign_in_attempts WHERE lower(username) = lower(:u)"),
        {"u": username},
    )


def sign_in(
    engine, username: str, password: str, *, now: Callable[[], datetime] = _now
) -> SignInResult:
    """Verify a password and open a session.

    Returns the same refusal for an unknown username as for a wrong password,
    and spends the same work on both: an unknown username still runs a
    verification against a dummy hash, so the response time does not reveal
    which accounts exist.
    """
    username = username.strip()
    stamp = now()
    with engine.begin() as conn:
        # Before the password is even looked at, so a throttled attempt costs
        # nothing and a locked account cannot be used as an oracle.
        if _recent_failures(conn, username, stamp) >= MAX_FAILURES:
            return SignInResult(error=_THROTTLED)

        row = conn.execute(
            text("""
                SELECT account_id, username, password_hash, store_id,
                       is_operator, must_change_password
                FROM public.accounts
                WHERE lower(username) = lower(:username)
            """),
            {"username": username},
        ).fetchone()

        if row is None:
            # Deliberate work against a value that cannot match. Returning
            # early here would make an unknown username measurably faster than
            # a wrong password, which is the same leak the uniform message
            # exists to close.
            verify_password(password, _DUMMY_HASH)
            _record_failure(conn, username, stamp)
            return SignInResult(error=_REFUSED)

        if not verify_password(password, row.password_hash):
            _record_failure(conn, username, stamp)
            return SignInResult(error=_REFUSED)

        _clear_failures(conn, username)
        token = secrets.token_urlsafe(32)
        conn.execute(
            text("""
                INSERT INTO public.account_sessions
                    (token_hash, account_id, issued_at, last_seen_at)
                VALUES (:token_hash, :account_id, :stamp, :stamp)
            """),
            {
                "token_hash": token_hash(token),
                "account_id": row.account_id,
                "stamp": stamp,
            },
        )
        conn.execute(
            text(
                "UPDATE public.accounts SET last_sign_in_at = :stamp "
                "WHERE account_id = :account_id"
            ),
            {"stamp": stamp, "account_id": row.account_id},
        )
        return SignInResult(
            token=token,
            account=Account(
                account_id=int(row.account_id),
                username=row.username,
                store_id=None if row.store_id is None else int(row.store_id),
                is_operator=bool(row.is_operator),
                must_change_password=bool(row.must_change_password),
            ),
        )


def account_for_token(
    engine, token: str, *, now: Callable[[], datetime] = _now
) -> Account | None:
    """The account a session token belongs to, or None.

    Idle expiry is enforced here, against the stored row, rather than against
    anything the browser holds. Streamlit reads cookies only when the
    websocket connects, so a cookie is not re-examined on a rerun and an
    expiry encoded in it would never be noticed.
    """
    if not token:
        return None
    stamp = now()
    with engine.begin() as conn:
        row = conn.execute(
            text("""
                SELECT s.account_id, s.last_seen_at, s.revoked_at,
                       a.username, a.store_id, a.is_operator,
                       a.must_change_password
                FROM public.account_sessions AS s
                JOIN public.accounts AS a ON a.account_id = s.account_id
                WHERE s.token_hash = :token_hash
            """),
            {"token_hash": token_hash(token)},
        ).fetchone()
        if row is None or row.revoked_at is not None:
            return None
        if _expired(row.last_seen_at, stamp):
            return None
        conn.execute(
            text(
                "UPDATE public.account_sessions SET last_seen_at = :stamp "
                "WHERE token_hash = :token_hash"
            ),
            {"stamp": stamp, "token_hash": token_hash(token)},
        )
        return Account(
            account_id=int(row.account_id),
            username=row.username,
            store_id=None if row.store_id is None else int(row.store_id),
            is_operator=bool(row.is_operator),
            must_change_password=bool(row.must_change_password),
        )


def sign_out(engine, token: str, *, now: Callable[[], datetime] = _now) -> None:
    """Revoke rather than delete, so a returning token is refused by a row
    that says why rather than by an absent one that cannot."""
    if not token:
        return
    with engine.begin() as conn:
        conn.execute(
            text(
                "UPDATE public.account_sessions SET revoked_at = :stamp "
                "WHERE token_hash = :token_hash AND revoked_at IS NULL"
            ),
            {"stamp": now(), "token_hash": token_hash(token)},
        )


def _expired(last_seen, stamp: datetime) -> bool:
    if last_seen is None:
        return True
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    return (stamp - last_seen) > IDLE_LIFETIME


def password_needs_upgrade(stored: str) -> bool:
    """Re-exported so the sign-in path does not import the hashing module for
    one predicate, and so the reason travels with it: raising the cost can
    only take effect while the plaintext is in hand."""
    return needs_rehash(stored)


# A real hash of a value nobody knows, so an unknown username costs the same
# as a known one. Built once at import; the work is in the verification.
_DUMMY_HASH = (
    "scrypt$32768$8$1$"
    "AAAAAAAAAAAAAAAAAAAAAA==$"
    "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="
)
