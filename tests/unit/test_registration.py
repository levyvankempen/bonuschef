"""Making an account from the page.

The code is not a password and does not authenticate anybody. It decides who
may create an account, which is a different question, and these tests are
mostly about the order things are checked in.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from bonuschef.portal import passwords, registration
from bonuschef.portal.passwords import KdfParams, verify_password
from bonuschef.portal.registration import (
    code_matches,
    register,
    registration_open,
    username_problem,
)

CODE = "kom-maar-binnen"


@pytest.fixture(autouse=True)
def _fast_and_open(monkeypatch):
    monkeypatch.setattr(passwords, "DEFAULT_PARAMS", KdfParams(n=2**10, r=8, p=1))
    monkeypatch.setenv("BONUSCHEF_INVITE_CODE", CODE)


class FakeEngine:
    def __init__(self, taken=False):
        self.taken = taken
        self.statements: list[str] = []
        self.params: list[dict] = []

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        self.statements.append(sql)
        self.params.append(params or {})
        if "SELECT 1 FROM public.accounts" in sql:
            return SimpleNamespace(scalar=lambda: 1 if self.taken else None)
        return SimpleNamespace(scalar=lambda: 7)

    def wrote(self) -> bool:
        return any("INSERT INTO public.accounts" in s for s in self.statements)


# --- the code ---------------------------------------------------------------


def test_registration_is_closed_without_a_code(monkeypatch):
    """A deployment that has not thought about who may register does not get
    an open form by default."""
    monkeypatch.delenv("BONUSCHEF_INVITE_CODE", raising=False)
    assert registration_open() is False
    assert code_matches("") is False
    assert code_matches("anything") is False


def test_a_wrong_code_creates_nothing():
    engine = FakeEngine()
    result = register(engine, "anne", "a-good-password", "a-good-password", "nope")
    assert not result.ok
    assert not engine.wrote()


def test_the_code_is_checked_before_the_username():
    """An open form that answers "that name is taken" to a stranger is a way
    to enumerate the people using it."""
    engine = FakeEngine(taken=True)
    result = register(engine, "levy", "a-good-password", "a-good-password", "nope")
    assert result.error == "Die uitnodigingscode klopt niet."
    assert engine.statements == [], "it should not even look"


def test_the_code_is_compared_in_constant_time():
    """A source check: a byte-at-a-time comparison leaks the code to anybody
    who can time the refusals, and that is not observable in a unit test."""
    import inspect

    assert "hmac.compare_digest" in inspect.getsource(code_matches)


def test_surrounding_space_does_not_break_a_pasted_code():
    assert code_matches(f"  {CODE} ") is True


# --- what gets created ------------------------------------------------------


def test_a_good_registration_creates_an_account():
    engine = FakeEngine()
    result = register(engine, "anne", "a-good-password", "a-good-password", CODE)
    assert result.ok
    assert engine.wrote()


def test_the_password_is_stored_hashed():
    engine = FakeEngine()
    register(engine, "anne", "a-good-password", "a-good-password", CODE)
    written = next(p for p in engine.params if "h" in p)
    assert "a-good-password" not in written["h"]
    assert verify_password("a-good-password", written["h"])


def test_a_new_account_has_no_shop():
    """The next thing they see is which Albert Heijn they shop at - the one
    setting the app cannot guess and must not default."""
    engine = FakeEngine()
    register(engine, "anne", "a-good-password", "a-good-password", CODE)
    insert = next(s for s in engine.statements if "INSERT" in s)
    assert "NULL, FALSE, FALSE" in insert, insert


def test_a_new_account_is_not_an_operator():
    """Starting pipeline runs and editing the shared catalogue stay with
    whoever owns the server."""
    engine = FakeEngine()
    register(engine, "anne", "a-good-password", "a-good-password", CODE)
    insert = next(s for s in engine.statements if "INSERT" in s)
    assert "is_operator" in insert
    assert "TRUE" not in insert


# --- refusals ---------------------------------------------------------------


def test_mismatched_passwords_create_nothing():
    engine = FakeEngine()
    result = register(engine, "anne", "a-good-password", "a-different-one", CODE)
    assert not result.ok
    assert not engine.wrote()


def test_a_short_password_is_refused():
    engine = FakeEngine()
    result = register(engine, "anne", "short", "short", CODE)
    assert not result.ok
    assert not engine.wrote()


def test_a_taken_name_is_refused():
    engine = FakeEngine(taken=True)
    result = register(engine, "levy", "a-good-password", "a-good-password", CODE)
    assert result.error == "Die naam is al in gebruik."
    assert not engine.wrote()


def test_a_name_is_matched_without_regard_to_case():
    """Otherwise Levy and levy are two people who cannot tell each other
    apart."""
    engine = FakeEngine(taken=True)
    register(engine, "LEVY", "a-good-password", "a-good-password", CODE)
    assert any("lower(username) = lower(:u)" in s for s in engine.statements)


@pytest.mark.parametrize("name", ["", " ", "a", "x" * 33])
def test_an_unusable_name_is_refused(name):
    assert username_problem(registration.normalise_username(name))


def test_surrounding_space_is_trimmed_from_a_name():
    """A trailing space is invisible in a form and would make two accounts
    that look identical."""
    engine = FakeEngine()
    register(engine, "  anne  ", "a-good-password", "a-good-password", CODE)
    written = next(p for p in engine.params if "u" in p and "h" in p)
    assert written["u"] == "anne"
