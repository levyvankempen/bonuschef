"""How a password is stored, so that reading the database does not reveal it.

scrypt, from `cryptography`, at n=2^15, r=8, p=1.

Why that and not the textbook answer: argon2-cffi is the better algorithm and
is not installed, and adding a C extension for four users is a poor trade when
`cryptography` is already in the production image - it arrives through
dagster-dg-cli and provides a memory-hard KDF.

Why not `hashlib.scrypt`, which is in the standard library: OpenSSL caps
scrypt's memory at 32 MB by default, and these parameters exceed it. The call
raises `ValueError: memory limit exceeded` rather than running slower, which
turns "raise the cost" into a production crash - or, worse, into somebody
quietly dropping to n=2^14 to make the error go away. `cryptography`'s Scrypt
has no such cap.

The parameters travel inside the stored value, so the cost can be raised later
without invalidating every existing password.

The cost is a parameter rather than a constant because a deliberately slow
hash in a fast test suite is a real tension, and the resolution is the one
Django uses: run the tests at a low cost and assert the production cost
separately, in a test that does no hashing at all. That assertion is what
protects the requirement. A round-trip test does not - it passes just as
happily at n=2^10.
"""

from __future__ import annotations

import base64
import hmac
import secrets
from dataclasses import dataclass

from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

_SCHEME = "scrypt"
_SALT_BYTES = 16
_KEY_BYTES = 32

# Below this, stop pretending. Anything shorter is a typo or an empty form,
# and both should be rejected before they reach a hash function.
MIN_LENGTH = 8


@dataclass(frozen=True)
class KdfParams:
    """Work factors. The defaults are the production ones.

    Read the defaults, not the module-level DEFAULT_PARAMS, when asserting
    what production uses: the test suite replaces DEFAULT_PARAMS with a cheap
    one, and a test that read it would be asserting the test value.
    """

    n: int = 2**15
    r: int = 8
    p: int = 1


DEFAULT_PARAMS = KdfParams()


class PasswordTooShort(ValueError):
    """Raised rather than hashed, so the rule lives in one place."""


def hash_password(password: str, *, params: KdfParams | None = None) -> str:
    """Return a self-describing hash: scheme, parameters, salt, key.

    The salt is fresh per call, so two people choosing the same password do
    not produce the same stored value - which is what stops a glance at the
    table revealing that they did.
    """
    if len(password) < MIN_LENGTH:
        raise PasswordTooShort(f"at least {MIN_LENGTH} characters")
    params = params or DEFAULT_PARAMS
    salt = secrets.token_bytes(_SALT_BYTES)
    key = _derive(password, salt, params)
    return "$".join(
        (
            _SCHEME,
            str(params.n),
            str(params.r),
            str(params.p),
            _b64(salt),
            _b64(key),
        )
    )


def verify_password(password: str, stored: str) -> bool:
    """Whether the password produces the stored hash.

    Parameters come from the stored value rather than from the current
    defaults, so raising the cost does not lock out everybody who set a
    password before the change.

    A malformed or unknown stored value is a failed verification, not an
    exception. The caller is a sign-in form; the answer it needs is no.
    """
    try:
        scheme, n, r, p, salt, key = stored.split("$")
    except ValueError:
        return False
    if scheme != _SCHEME:
        return False
    try:
        params = KdfParams(n=int(n), r=int(r), p=int(p))
        expected = _unb64(key)
        candidate = _derive(password, _unb64(salt), params, length=len(expected))
    except (ValueError, TypeError):
        return False
    # Constant time: a comparison that returns early leaks how much of the
    # hash matched, one byte at a time.
    return hmac.compare_digest(candidate, expected)


def needs_rehash(stored: str, *, params: KdfParams | None = None) -> bool:
    """Whether a stored hash was made with weaker parameters than current.

    Lets a raised cost take effect on next sign-in, which is the only moment
    the plaintext is available to re-derive from.
    """
    params = params or DEFAULT_PARAMS
    try:
        scheme, n, r, p, _, _ = stored.split("$")
    except ValueError:
        return True
    if scheme != _SCHEME:
        return True
    try:
        return (int(n), int(r), int(p)) != (params.n, params.r, params.p)
    except ValueError:
        return True


def _derive(
    password: str, salt: bytes, params: KdfParams, *, length: int = _KEY_BYTES
) -> bytes:
    kdf = Scrypt(salt=salt, length=length, n=params.n, r=params.r, p=params.p)
    return kdf.derive(password.encode("utf-8"))


def _b64(raw: bytes) -> str:
    return base64.b64encode(raw).decode("ascii")


def _unb64(text: str) -> bytes:
    return base64.b64decode(text.encode("ascii"), validate=True)
