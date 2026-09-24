"""The operator's view of the accounts, and who is allowed to see it.

This page shows other people's collections, so the access tests here matter
more than the rendering ones. A page that is private only because nothing
links to it is one refactor away from being public.
"""

import ast
from pathlib import Path

import pandas as pd
import pytest

from bonuschef.portal import monitor_page as page
from bonuschef.portal.accounts import Account
from tests.conftest import run_app

OPERATOR = Account(
    account_id=1,
    username="levy",
    store_id=1876,
    is_operator=True,
    must_change_password=False,
)
FRIEND = Account(
    account_id=2,
    username="sample",
    store_id=1234,
    is_operator=False,
    must_change_password=False,
)

NOW = pd.Timestamp("2026-09-24 18:00", tz="Europe/Amsterdam")


def _overview(**overrides) -> pd.DataFrame:
    base = {
        "account_id": [1, 2, 3, 4],
        "username": ["levy", "sample", "nooit", "geenwinkel"],
        "is_operator": [True, False, False, False],
        "created_at": [NOW - pd.Timedelta(days=30)] * 4,
        "last_sign_in_at": [
            NOW - pd.Timedelta(days=20),
            NOW - pd.Timedelta(days=6),
            pd.NaT,
            NOW - pd.Timedelta(days=1),
        ],
        "must_change_password": [False, False, False, False],
        "store_id": [1876, 1234, None, None],
        "store_name": [
            "Eindhoven Torenallee",
            "Eindhoven Kamperfoelielaan",
            None,
            None,
        ],
        "last_seen_at": [
            NOW - pd.Timedelta(minutes=5),
            NOW - pd.Timedelta(days=6),
            pd.NaT,
            NOW - pd.Timedelta(days=1),
        ],
        "saved_count": [3, 0, 0, 0],
        "last_made_at": [NOW - pd.Timedelta(days=2), pd.NaT, pd.NaT, pd.NaT],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _saved() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "recipe_id": [10, 11],
            "saved_at": [NOW - pd.Timedelta(days=9), NOW - pd.Timedelta(days=3)],
            "last_made_at": [NOW - pd.Timedelta(days=2), pd.NaT],
            "notes": [None, None],
            "recipe_name": ["Zuurkoolstamppot", "Quiche met broccoli"],
        }
    )


@pytest.fixture
def wired(monkeypatch):
    monkeypatch.setattr(page, "get_engine", lambda: object())
    monkeypatch.setattr(page, "read_account_overview", lambda e: _overview())
    monkeypatch.setattr(page, "read_account_saved_recipes", lambda e, a: _saved())
    monkeypatch.setattr(page, "freshness_now", lambda: NOW)


def _texts(at) -> str:
    parts = []
    for block in (at.markdown, at.caption, at.info, at.warning, at.error, at.title):
        parts.extend(e.value for e in block)
    return " ".join(parts)


# --- who may look ------------------------------------------------------------


class TestOnlyTheOperator:
    def test_a_friend_calling_it_directly_is_refused(self, wired):
        """The navigation does not offer this page to them, but the navigation
        decides what is listed and not what is allowed."""
        at = run_app(page.render_monitor, FRIEND).run()
        assert at.error, "it must refuse rather than render"
        body = _texts(at)
        assert "sample" not in body or "alleen voor de beheerder" in body
        assert "Zuurkoolstamppot" not in body, "and leak nothing while refusing"
        assert "Torenallee" not in body

    def test_the_refusal_does_not_describe_what_it_withheld(self, wired):
        at = run_app(page.render_monitor, FRIEND).run()
        body = _texts(at)
        for leak in ("3", "Kamperfoelielaan", "nooit", "geenwinkel"):
            assert leak not in body.replace("beheerder", ""), f"leaked {leak!r}"

    def test_the_operator_gets_in(self, wired):
        at = run_app(page.render_monitor, OPERATOR).run()
        assert not at.error
        assert "levy" in _texts(at)

    def test_the_check_is_in_the_page_not_only_in_the_navigation(self):
        """Read the function, not the file: the module docstring explains the
        rule, and a substring search would match that prose and pass whatever
        the code did."""
        tree = ast.parse(Path(page.__file__).read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "render_monitor"
        )
        names = {
            ast.unparse(n)
            for n in ast.walk(fn)
            if isinstance(n, (ast.Attribute, ast.Call))
        }
        assert any("is_operator" in n for n in names), (
            "render_monitor must check is_operator itself"
        )


# --- what it shows -----------------------------------------------------------


class TestWhatTheOperatorSees:
    def test_every_account_is_listed(self, wired):
        body = _texts(run_app(page.render_monitor, OPERATOR).run())
        for name in ("levy", "sample", "nooit", "geenwinkel"):
            assert name in body

    def test_each_shop_is_named_rather_than_numbered(self, wired):
        """1876 tells the operator nothing about whether somebody picked the
        right shop out of 1,199."""
        body = _texts(run_app(page.render_monitor, OPERATOR).run())
        assert "Eindhoven Torenallee" in body
        assert "Eindhoven Kamperfoelielaan" in body

    def test_an_account_that_never_signed_in_says_so(self, wired):
        """Not a blank. It is one of the two shapes of "this person got
        stuck", which is the thing worth catching."""
        body = _texts(run_app(page.render_monitor, OPERATOR).run())
        assert "nog nooit aangemeld" in body

    def test_an_account_with_no_shop_says_so(self, wired):
        body = _texts(run_app(page.render_monitor, OPERATOR).run())
        assert "nog geen winkel gekozen" in body

    def test_saved_recipes_are_named_with_when(self, wired):
        at = run_app(page.render_monitor, OPERATOR).run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body
        assert "Quiche met broccoli" in body
        assert "bewaard" in body

    def test_an_account_with_nothing_saved_says_so(self, wired):
        body = _texts(run_app(page.render_monitor, OPERATOR).run())
        assert "Nog geen recepten bewaard" in body

    def test_no_credential_appears_anywhere(self, wired):
        """The readers do not select password_hash, and the page must not
        acquire a way to show one."""
        body = _texts(run_app(page.render_monitor, OPERATOR).run()).lower()
        for secret in ("password", "hash", "wachtwoordhash", "scrypt", "$"):
            assert secret not in body.replace("wachtwoord nog wijzigen", "")

    def test_it_survives_a_database_that_is_not_there(self, monkeypatch):
        def boom():
            raise RuntimeError("no database")

        monkeypatch.setattr(page, "get_engine", boom)
        at = run_app(page.render_monitor, OPERATOR).run()
        assert not at.exception, "an unreachable database is reported, not raised"
        assert at.error


# --- the readers -------------------------------------------------------------


class TestTheReadersCarryWhatThePageNeeds:
    @staticmethod
    def _sql(fn_name: str) -> str:
        tree = ast.parse(Path("src/bonuschef/portal/db.py").read_text())
        fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == fn_name
        )
        return " ".join(
            n.value
            for n in ast.walk(fn)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and "SELECT" in n.value
        )

    def test_neither_reader_selects_the_password_hash(self):
        """Excluded from the query rather than merely unrendered, so a later
        change to the page cannot leak a column it never fetched."""
        for fn in ("read_account_overview", "read_account_saved_recipes"):
            assert "password_hash" not in self._sql(fn), fn

    def test_last_opened_comes_from_the_sessions_not_the_sign_in_column(self):
        """Somebody who signed in six weeks ago and has used it every day since
        has a six-week-old sign-in and a session touched this morning.
        Reporting the sign-in would call an active person dormant."""
        sql = self._sql("read_account_overview")
        assert "account_sessions" in sql
        assert "last_seen_at" in sql

    def test_the_overview_covers_every_account(self):
        sql = self._sql("read_account_overview")
        assert "FROM public.accounts" in sql
        assert "WHERE" not in sql.split("ORDER BY")[0].split("FROM public.accounts")[1]
