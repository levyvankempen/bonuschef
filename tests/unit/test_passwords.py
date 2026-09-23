"""Password storage.

The failure this guards against is silent: a fast hash behaves identically in
every test and differs only when somebody who should not have the database
reads it. So the test that matters is not the round trip - it is the one
asserting the production cost, and it deliberately does no hashing at all.
"""

import pytest

from bonuschef.portal import passwords
from bonuschef.portal.passwords import (
    KdfParams,
    PasswordTooShort,
    hash_password,
    needs_rehash,
    verify_password,
)

# Cheap enough to run hundreds of times. Every test below uses this except the
# ones explicitly about production cost.
CHEAP = KdfParams(n=2**10, r=8, p=1)


@pytest.fixture(autouse=True)
def _fast_hashing(monkeypatch):
    """Run the suite at a low work factor.

    This is the standard resolution of the slow-hash-in-a-fast-suite tension -
    Django does the same thing with PASSWORD_HASHERS. It is safe only because
    the production cost is asserted separately, from the dataclass defaults
    rather than from the value this fixture replaces.
    """
    monkeypatch.setattr(passwords, "DEFAULT_PARAMS", CHEAP)


# --- the assertion that protects the requirement ---------------------------


def test_the_production_cost_is_memory_hard():
    """Reads KdfParams' defaults, not DEFAULT_PARAMS, which the fixture above
    has replaced. A test that read the module global would be asserting the
    test value and would pass at any cost whatsoever."""
    production = KdfParams()
    assert production.n >= 2**15, "below this, a GPU makes short work of the table"
    assert production.r == 8
    assert production.p >= 1


def test_the_production_cost_exceeds_openssl_s_default_cap():
    """hashlib.scrypt would raise ValueError at these parameters, because
    OpenSSL caps scrypt memory at 32 MB. That is the trap this module avoids
    by using cryptography's Scrypt - and the reason is worth a test, because
    the obvious "fix" when somebody hits it is to lower n until it stops."""
    import hashlib

    with pytest.raises(ValueError):
        hashlib.scrypt(b"x", salt=b"y" * 16, n=KdfParams().n, r=8, p=1, dklen=32)


# --- storage ---------------------------------------------------------------


def test_the_password_is_not_in_the_stored_value():
    stored = hash_password("correct horse battery")
    assert "correct horse battery" not in stored


def test_the_same_password_twice_looks_different():
    """A missing salt is invisible until the table is read, at which point it
    reveals which accounts share a password."""
    a = hash_password("correct horse battery")
    b = hash_password("correct horse battery")
    assert a != b
    assert verify_password("correct horse battery", a)
    assert verify_password("correct horse battery", b)


def test_the_right_password_verifies():
    assert verify_password(
        "correct horse battery", hash_password("correct horse battery")
    )


def test_the_wrong_password_does_not():
    assert not verify_password(
        "Correct horse battery", hash_password("correct horse battery")
    )


def test_the_parameters_travel_with_the_hash():
    """So the cost can be raised later without invalidating every password
    set before the change."""
    stored = hash_password("correct horse battery", params=CHEAP)
    scheme, n, r, p, _, _ = stored.split("$")
    assert (scheme, int(n), int(r), int(p)) == ("scrypt", CHEAP.n, CHEAP.r, CHEAP.p)


def test_a_hash_made_at_another_cost_still_verifies():
    """The upgrade path. Verification reads the stored parameters rather than
    the current defaults."""
    stored = hash_password("correct horse battery", params=KdfParams(n=2**11, r=8, p=1))
    assert verify_password("correct horse battery", stored)


# --- failure is an answer, not an exception --------------------------------


@pytest.mark.parametrize(
    "stored",
    ["", "nonsense", "scrypt$notanumber$8$1$c2FsdA==$a2V5", "bcrypt$1$2$3$4$5"],
)
def test_an_unusable_stored_value_is_a_failed_sign_in(stored):
    """The caller is a sign-in form. The answer it needs is no - a traceback
    would turn a corrupt row into a 500 and tell the visitor about it."""
    assert verify_password("correct horse battery", stored) is False


def test_a_short_password_is_refused_rather_than_hashed():
    with pytest.raises(PasswordTooShort):
        hash_password("short")


# --- raising the cost later ------------------------------------------------


def test_a_weaker_hash_is_flagged_for_rehash():
    assert needs_rehash(
        hash_password("correct horse battery", params=KdfParams(n=2**10)),
        params=KdfParams(n=2**15),
    )


def test_a_current_hash_is_not():
    current = KdfParams(n=2**11, r=8, p=1)
    assert not needs_rehash(
        hash_password("correct horse battery", params=current), params=current
    )


def test_an_unreadable_hash_is_flagged():
    """Unknown scheme, unknown cost. Treat it as due for replacement rather
    than as current."""
    assert needs_rehash("bcrypt$whatever")


def test_the_comparison_is_constant_time():
    """A source check, not a behavioural one, and deliberately so.

    Replacing hmac.compare_digest with `==` changes nothing any unit test can
    observe: same answers, same speed at test scale. Verified by mutation -
    the swap passed all sixteen tests above. What it changes is how long a
    mismatch takes to discover, one byte at a time, which is a property of the
    machine rather than of the result.

    So the guard is that the call is present. A test that cannot fail on the
    thing it names would be worse than this.
    """
    import inspect

    source = inspect.getsource(verify_password)
    assert "hmac.compare_digest" in source, source
    assert "==" not in source.split("return")[-1], "an early-exit comparison leaks"
