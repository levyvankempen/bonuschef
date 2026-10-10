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
    monkeypatch.setattr(page, "read_pipeline_health", lambda e: pd.DataFrame())
    monkeypatch.setattr(page, "count_flagged_concepts", lambda e: 0)


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


class TestTheConsoleMovedHereRatherThanBeingDeleted:
    """Taking the diagnostics off a shopper's page only works if the operator
    can still see them. The spec's argument that this portal is "the only
    surface on which a failure can be noticed" is what makes that a move rather
    than a removal."""

    def test_an_overdue_job_is_named_with_when_it_last_worked(self, wired, monkeypatch):
        health = pd.DataFrame(
            {
                "job_name": ["markdowns_refresh"],
                "last_success": [NOW - pd.Timedelta(hours=9)],
                "failures_today": [0],
                "overdue_h": [9.0],
                "tolerance_h": [3.0],
                "what": ["de laatste kans-koopjes"],
                "is_overdue": [True],
            }
        )
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: health)
        at = run_app(page.render_monitor, OPERATOR).run()
        body = _texts(at) + " ".join(w.value for w in at.warning)
        assert "markdowns_refresh" in body
        assert "9 uur geleden" in body

    def test_a_job_that_has_never_run_says_so(self, wired, monkeypatch):
        health = pd.DataFrame(
            {
                "job_name": ["github_products"],
                "last_success": [pd.NaT],
                "failures_today": [0],
                "overdue_h": [99.0],
                "tolerance_h": [24.0],
                "what": ["de prijsgeschiedenis"],
                "is_overdue": [True],
            }
        )
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: health)
        at = run_app(page.render_monitor, OPERATOR).run()
        assert "nog nooit gelukt" in " ".join(w.value for w in at.warning)

    def test_everything_on_time_is_said_too(self, wired, monkeypatch):
        """A health indicator that only ever appears when broken leaves the
        operator unable to tell "fine" from "not loaded" - which are different
        states and are reported differently."""
        health = pd.DataFrame(
            {
                "job_name": ["markdowns_refresh"],
                "last_success": [NOW],
                "failures_today": [0],
                "overdue_h": [1.0],
                "tolerance_h": [3.0],
                "what": ["de laatste kans-koopjes"],
                "is_overdue": [False],
            }
        )
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: health)
        at = run_app(page.render_monitor, OPERATOR).run()
        assert at.success, "say that the jobs are on time"

    def test_no_data_at_all_is_a_different_state(self, wired):
        """The fixture returns nothing, which is not the same as nothing being
        wrong."""
        at = run_app(page.render_monitor, OPERATOR).run()
        assert not at.success
        assert "Geen gegevens over de jobs" in _texts(at)

    def test_flagged_matches_are_surfaced(self, wired, monkeypatch):
        """A flagged concept already has a price; it is just wrong, which reads
        as nothing being amiss."""
        monkeypatch.setattr(page, "count_flagged_concepts", lambda e: 4)
        at = run_app(page.render_monitor, OPERATOR).run()
        assert any("niet bij hoort" in w.value for w in at.warning)

    def test_the_way_into_the_matcher_is_here(self, wired):
        at = run_app(page.render_monitor, OPERATOR).run()
        assert [b for b in at.button if "nakijken" in b.label]

    def test_a_friend_sees_none_of_it(self, wired):
        """The page refuses as a whole, so the console cannot leak through it."""
        at = run_app(page.render_monitor, FRIEND).run()
        assert at.error
        assert not at.warning
        assert not [b for b in at.button if "nakijken" in b.label]

    def test_an_unreadable_pipeline_does_not_break_the_page(self, wired, monkeypatch):
        def boom(e):
            raise RuntimeError("no run table")

        monkeypatch.setattr(page, "read_pipeline_health", boom)
        at = run_app(page.render_monitor, OPERATOR).run()
        assert not at.exception
        assert "levy" in _texts(at), "the accounts still render"


class TestTheTestEnvironmentPanel:
    """So the test environment is not silently broken.

    It is nobody's production, so a failed copy or a stopped container sits
    there unnoticed until somebody needs it - which is exactly when a broken
    one is most expensive: the change is ready, the operator wants to watch it
    work, and instead they spend the evening fixing the thing that was supposed
    to give them confidence.
    """

    @staticmethod
    def _state(monkeypatch, state):
        monkeypatch.setattr(page, "read_test_environment_state", lambda: state)

    def test_it_is_omitted_when_nothing_is_configured(self, wired, monkeypatch):
        """A deployment with one environment is not broken, and telling it
        something is missing is how a panel gets ignored."""
        self._state(monkeypatch, None)
        at = run_app(page.render_monitor, OPERATOR).run()
        body = _texts(at)
        assert "testomgeving" not in body.lower()
        assert not at.warning

    def test_a_running_environment_says_when_it_was_copied(self, wired, monkeypatch):
        self._state(
            monkeypatch,
            {
                "reachable": True,
                "copied_at": NOW - pd.Timedelta(days=2),
                "source": "bonuschef v1.40.2",
            },
        )
        at = run_app(page.render_monitor, OPERATOR).run()
        body = _texts(at) + " ".join(s.value for s in at.success)
        assert "testomgeving draait" in body
        assert "2 dagen" in body
        assert "v1.40.2" in body

    def test_an_unreachable_environment_is_reported_not_raised(
        self, wired, monkeypatch
    ):
        self._state(monkeypatch, {"reachable": False, "error": "connection refused"})
        at = run_app(page.render_monitor, OPERATOR).run()
        assert not at.exception
        warnings = " ".join(w.value for w in at.warning)
        assert "niet bereikbaar" in warnings
        assert "connection refused" in _texts(at)

    def test_running_but_never_copied_is_a_different_state(self, wired, monkeypatch):
        """The stack is up and nobody has copied anything into it. Reporting
        that as unreachable would send the operator debugging a network."""
        self._state(monkeypatch, {"reachable": True, "copied_at": None, "source": None})
        at = run_app(page.render_monitor, OPERATOR).run()
        body = _texts(at) + " ".join(i.value for i in at.info)
        assert "nog geen gegevens" in body
        assert "copy-to-test.sh" in body
        assert not at.warning, "an empty test environment is not a fault"

    def test_the_three_states_are_distinguishable(self, wired, monkeypatch):
        """Unreachable, running-and-empty, and running-with-a-copy must not
        render the same way: the first needs a fix, the second needs a command,
        the third needs nothing."""
        seen = set()
        for state in (
            {"reachable": False, "error": "x"},
            {"reachable": True, "copied_at": None, "source": None},
            {"reachable": True, "copied_at": NOW, "source": "s"},
        ):
            self._state(monkeypatch, state)
            at = run_app(page.render_monitor, OPERATOR).run()
            seen.add((bool(at.warning), bool(at.info), bool(at.success)))
        assert len(seen) == 3, f"states collapse into {seen}"

    def test_a_reader_that_throws_does_not_break_the_page(self, wired, monkeypatch):
        """The accounts are what this page is for. A diagnostic panel must not
        be able to take them away."""

        def boom():
            raise RuntimeError("no test environment")

        monkeypatch.setattr(page, "read_test_environment_state", boom)
        at = run_app(page.render_monitor, OPERATOR).run()
        # Not just "the accounts rendered": they render before this panel, so
        # that would pass while a traceback sat at the bottom of the page.
        assert not at.exception, "a diagnostic put a traceback on the page"
        assert "levy" in _texts(at), "the accounts must still render"
        assert "niet uitlezen" in _texts(at), "and it says what went wrong"

    def test_a_friend_sees_none_of_it(self, wired, monkeypatch):
        self._state(monkeypatch, {"reachable": True, "copied_at": NOW, "source": "s"})
        at = run_app(page.render_monitor, FRIEND).run()
        assert at.error
        assert "testomgeving" not in _texts(at).lower()


class TestTheReaderOnlyReadsOneWay:
    def test_an_unconfigured_environment_returns_none(self, monkeypatch):
        monkeypatch.delenv("BONUSCHEF_TEST_DATABASE_URL", raising=False)
        from bonuschef.portal.db import read_test_environment_state

        assert read_test_environment_state() is None

    def test_an_empty_variable_is_the_same_as_unset(self, monkeypatch):
        monkeypatch.setenv("BONUSCHEF_TEST_DATABASE_URL", "   ")
        from bonuschef.portal.db import read_test_environment_state

        assert read_test_environment_state() is None

    # The driver the application actually uses. Named once, because getting
    # this wrong is how the test below came to pass for the wrong reason.
    DRIVER = "postgresql+psycopg2"

    def test_the_url_in_these_tests_uses_an_installed_driver(self):
        """This test exists because its absence hid a real bug.

        The unreachability test below named `postgresql+psycopg` - psycopg 3,
        which is not installed. `create_engine` therefore raised
        ModuleNotFoundError before any connection was attempted, the outer
        handler caught it, and the test saw `reachable: False` and passed
        without ever exercising a refused connection. Meanwhile the real code
        reported an unreachable database as *running*.
        """
        import sqlalchemy

        sqlalchemy.create_engine(f"{self.DRIVER}://postgres:x@127.0.0.1:9/x")

    def test_an_unreachable_database_is_reported_as_unreachable(self):
        """Not as "running but empty", which is what it used to say.

        `read_environment_copy` swallows every failure and returns None -
        correct for its own job - so inferring reachability from it reported a
        database that was not listening as reachable and merely empty. The
        Beheer panel then told the operator the test environment was fine.
        """
        from bonuschef.portal.db import read_test_environment_state

        # Port 9 (discard) on loopback: nothing listens, refusal is immediate.
        state = read_test_environment_state(
            f"{self.DRIVER}://postgres:x@127.0.0.1:9/postgres"
        )
        assert state is not None
        assert state["reachable"] is False, (
            f"an unreachable database reported {state}, so the panel would "
            "call a dead environment healthy"
        )
        assert state.get("error"), "it must say what went wrong"

    def test_reachability_is_probed_rather_than_inferred(self):
        """Read the function: the connection must be made here, not deduced
        from whether another reader happened to return a row."""
        import ast
        from pathlib import Path as _Path

        tree = ast.parse(_Path("src/bonuschef/portal/db.py").read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "read_test_environment_state"
        )
        source = ast.unparse(fn)
        assert "SELECT 1" in source, (
            "nothing establishes reachability; it is being inferred from the "
            "copy row, which is None for a database that is simply down"
        )
        assert source.index("SELECT 1") < source.index("read_environment_copy"), (
            "the probe must come before the copy is read"
        )

    def test_the_reader_issues_no_writes(self):
        """Production reads the test environment; data moves the other way
        only, and only through the copy script."""
        import ast
        from pathlib import Path

        tree = ast.parse(Path("src/bonuschef/portal/db.py").read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "read_test_environment_state"
        )
        source = ast.unparse(fn).upper()
        for mutation in ("INSERT", "UPDATE ", "DELETE", "DROP", "CREATE TABLE"):
            assert mutation not in source, f"the reader issues {mutation}"

    def test_it_does_not_wait_long_enough_to_slow_the_page(self):
        """This renders on the page holding the account list, which is what
        that page is for. A test environment that is down must not cost ten
        seconds of it."""
        from bonuschef.portal import db

        assert db._TEST_ENV_TIMEOUT_S <= 5

    def test_the_panel_reads_only_keys_the_reader_can_produce(self):
        """The check that test_portal_readers_against_the_warehouse.py cannot
        make for this panel.

        That guard runs every reader and compares what a page subscripts
        against the columns that came back - the bug it exists for has shipped
        four times. It cannot cover this one: the keys come from a dict built
        in Python, and the reader returns None when no test environment is
        configured, so there is no frame to compare against. The same mistake
        is still possible, so it is checked here against the reader's own
        source instead.
        """
        import ast
        from pathlib import Path

        tree = ast.parse(Path("src/bonuschef/portal/db.py").read_text())
        reader = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef)
            and n.name == "read_test_environment_state"
        )
        # Keys the reader puts into its dicts, plus the ones it forwards from
        # read_environment_copy via `**copy`.
        produced = {
            key.value
            for node in ast.walk(reader)
            if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        forwarded = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "read_environment_copy"
        )
        sql = " ".join(
            n.value
            for n in ast.walk(forwarded)
            if isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and "SELECT" in n.value
        )
        produced |= {
            column for column in ("copied_at", "source", "dump_file") if column in sql
        }

        panel = next(
            n
            for n in ast.parse(Path(page.__file__).read_text()).body
            if isinstance(n, ast.FunctionDef) and n.name == "_render_test_environment"
        )
        consumed = {
            arg.value
            for node in ast.walk(panel)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            for arg in (node.args[0],)
            # A Constant's value is any literal; only the string ones are keys,
            # and narrowing here is what lets them be sorted below.
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str)
        }
        assert consumed, "the panel reads nothing; this guard would pass vacuously"
        assert consumed <= produced, (
            f"the panel reads {sorted(consumed - produced)}, which the reader "
            "never returns - so it would render as absent rather than fail"
        )
