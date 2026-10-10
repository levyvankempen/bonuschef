"""Which environment am I looking at.

The two deployments run the same portal, the same recipes and a copy of the
same data. A price read off the wrong one is wrong in a way nothing else on the
page reveals, and an operator who believes they are in the test environment
will eventually act on production.

So the question has to be answered before anything else on the page is read -
which is the opposite of where the version lives, and deliberately so. The
version is a footnote: "is the fix live?" is asked occasionally. This is not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pandas as pd
import pytest

from bonuschef.portal import ui
from bonuschef.version import get_environment, is_production
from tests.conftest import run_app

APP = Path("src/bonuschef/portal/app.py")
NOW = pd.Timestamp("2026-10-10 09:00", tz="Europe/Amsterdam")


@pytest.fixture
def production(monkeypatch):
    monkeypatch.delenv("BONUSCHEF_ENVIRONMENT", raising=False)


@pytest.fixture
def test_environment(monkeypatch):
    monkeypatch.setenv("BONUSCHEF_ENVIRONMENT", "test")


def _banner_text(at) -> str:
    return " ".join(w.value for w in at.warning)


# --- what the environment is --------------------------------------------


class TestWhichEnvironmentThisIs:
    def test_nothing_set_means_production(self, production):
        assert get_environment() == "production"
        assert is_production()

    def test_an_empty_value_means_production(self, monkeypatch):
        """What an env file with a bare `BONUSCHEF_ENVIRONMENT=` produces."""
        monkeypatch.setenv("BONUSCHEF_ENVIRONMENT", "")
        assert is_production()

    def test_whitespace_means_production(self, monkeypatch):
        monkeypatch.setenv("BONUSCHEF_ENVIRONMENT", "   ")
        assert is_production()

    def test_it_is_case_insensitive(self, monkeypatch):
        monkeypatch.setenv("BONUSCHEF_ENVIRONMENT", "TEST")
        assert get_environment() == "test"
        assert not is_production()

    def test_production_is_the_default_deliberately(self, production):
        """Both failure directions are bad and one is worse.

        A test environment that believes it is production shows no banner,
        which is quiet and fixable by reading a config file. Production
        believing it is a test environment puts a banner in front of every
        invited person, which is a page they are all looking at. Production is
        also the deployment that sets nothing, so absence meaning production
        is the honest reading rather than a convenient one.
        """
        assert is_production()


# --- the banner ---------------------------------------------------------


class TestTheBanner:
    def test_it_appears_in_a_test_environment(self, test_environment):
        at = run_app(ui.render_environment_banner).run()
        assert at.warning, "nothing says which environment this is"
        assert "TEST" in _banner_text(at)

    def test_it_says_this_is_not_the_real_app(self, test_environment):
        """The name alone assumes the reader knows what "test" implies about
        the prices in front of them."""
        at = run_app(ui.render_environment_banner).run()
        assert "niet de echte app" in _banner_text(at)

    def test_it_is_absent_in_production(self, production):
        """An invited person has one environment; labelling it is noise on
        every page they will ever see."""
        at = run_app(ui.render_environment_banner).run()
        assert not at.warning, f"production shows a banner: {_banner_text(at)}"
        assert not at.error
        assert not at.info

    def test_it_draws_nothing_at_all_in_production(self, production):
        """Not merely no text: no stylesheet either. A sticky-positioned
        element with nothing in it is still an element."""
        at = run_app(ui.render_environment_banner).run()
        assert not [m for m in at.markdown if "sticky" in m.value]

    def test_an_unnamed_environment_still_says_something(self, monkeypatch):
        """Any value other than production means somewhere that must say so,
        including a name nobody planned for."""
        monkeypatch.setenv("BONUSCHEF_ENVIRONMENT", "scratch")
        at = run_app(ui.render_environment_banner).run()
        assert "SCRATCH" in _banner_text(at)

    def test_it_survives_a_database_that_is_not_there(
        self, test_environment, monkeypatch
    ):
        """It renders before the sign-in wall, which is before the engine is
        otherwise touched. A banner that can take the page down with it is
        worse than no banner."""

        def boom():
            raise RuntimeError("no database")

        monkeypatch.setattr("bonuschef.portal.db.get_engine", boom)
        at = run_app(ui.render_environment_banner).run()
        assert not at.exception
        assert "TEST" in _banner_text(at)

    def test_it_is_pinned_to_the_top(self, test_environment):
        """Sticky, so scrolling a long page of recipes does not leave somebody
        looking at prices with no idea which environment produced them."""
        at = run_app(ui.render_environment_banner).run()
        styles = " ".join(m.value for m in at.markdown)
        assert "sticky" in styles
        assert "top: 0" in styles


class TestTheCopysAge:
    def _with_copy(self, monkeypatch, copy):
        monkeypatch.setattr("bonuschef.portal.db.get_engine", lambda: object())
        monkeypatch.setattr("bonuschef.portal.db.read_environment_copy", lambda e: copy)
        monkeypatch.setattr("bonuschef.portal.freshness.now", lambda: NOW)

    def test_it_reports_when_the_data_was_copied(self, test_environment, monkeypatch):
        """The other half of the same question. A test environment is only
        trustworthy to the extent its data is recent, and "these prices are
        eight days old" is the difference between a defect and a stale copy.
        """
        self._with_copy(
            monkeypatch,
            {
                "copied_at": NOW - pd.Timedelta(days=8),
                "source": "bonuschef v1.40.2",
                "dump_file": "production-x.dump",
            },
        )
        at = run_app(ui.render_environment_banner).run()
        text = _banner_text(at)
        assert "gekopieerd" in text
        assert "8 dagen" in text or "dagen" in text

    def test_a_database_that_was_never_copied_says_so(
        self, test_environment, monkeypatch
    ):
        """Rather than a blank. An unknown copy age and a fresh copy are
        different states, and only one of them is fine."""
        self._with_copy(monkeypatch, None)
        at = run_app(ui.render_environment_banner).run()
        assert "onbekend" in _banner_text(at)

    def test_a_row_with_no_timestamp_is_treated_as_unknown(
        self, test_environment, monkeypatch
    ):
        self._with_copy(
            monkeypatch, {"copied_at": None, "source": None, "dump_file": None}
        )
        at = run_app(ui.render_environment_banner).run()
        assert "onbekend" in _banner_text(at)

    def test_production_is_not_asked(self, production, monkeypatch):
        """The production check comes first, so nothing happens - including no
        query - on the deployment where nothing should."""
        asked = []
        monkeypatch.setattr(
            "bonuschef.portal.db.get_engine", lambda: asked.append(1) or object()
        )
        run_app(ui.render_environment_banner).run()
        assert not asked, "production resolved an engine to render no banner"


class TestTheReader:
    def test_it_returns_none_rather_than_raising(self):
        from bonuschef.portal.db import read_environment_copy

        class Unreachable:
            def begin(self):
                raise RuntimeError("no database")

        assert read_environment_copy(Unreachable()) is None

    def test_the_table_is_in_the_portals_own_ddl(self):
        """The portal queries it, so the portal must create it - the rule that
        `account_recipe_lines` broke by being queried and created by nobody."""
        from bonuschef.portal import schema

        assert any(
            "public.environment_copy" in statement for statement in schema._STATEMENTS
        )

    def test_the_table_can_hold_only_one_row(self):
        """Two rows would mean two answers to "when was this copied", and the
        reader would return whichever came first."""
        from bonuschef.portal import schema

        ddl = next(s for s in schema._STATEMENTS if "public.environment_copy" in s)
        assert "PRIMARY KEY" in ddl
        assert "CHECK (only_row)" in ddl


# --- the version did not move ------------------------------------------


class TestTheVersionStaysWhereItWas:
    """The footer placement was a decision with its reasoning in the code: a
    footnote rather than chrome competing with the answer. Adding a banner is
    not an excuse to relocate it."""

    def _module(self) -> ast.Module:
        return ast.parse(APP.read_text())

    def test_the_version_is_still_rendered(self):
        src = APP.read_text()
        assert "describe()" in src and "get_commit()" in src

    def test_the_banner_is_not_the_versions_new_home(self):
        """Read the function, not the file: ui.py's prose discusses the version
        and the footer, so a substring search would match the explanation."""
        tree = ast.parse(Path("src/bonuschef/portal/ui.py").read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "render_environment_banner"
        )
        # The exact callee name, not a substring of the unparsed call: the
        # banner's own helper is `_describe_copy`, which contains "describe"
        # and is not the version.
        called = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
        assert "describe" not in called, "the version moved into the banner"
        assert "get_commit" not in called

    def test_the_version_caption_is_still_after_the_page_runs(self):
        """`pg.run()` then the caption. Moving the caption above it would make
        it chrome."""
        src = APP.read_text()
        assert src.index("pg.run()") < src.rindex("BonusChef {describe()}")

    def test_the_banner_is_rendered_before_the_wall(self):
        """A sign-in page is a page. Somebody typing a password into the test
        environment believing it to be the real one is exactly the confusion
        this prevents, and it happens before any page function runs."""
        src = APP.read_text()
        assert src.index("render_environment_banner()") < src.index(
            "if gate.sign_in_required():"
        )

    def test_the_banner_is_rendered_exactly_once(self):
        """Two calls stack two banners, and the second would sit between the
        navigation and the page where it reads as part of the content."""
        tree = self._module()
        calls = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.Call)
            and ast.unparse(node.func) == "render_environment_banner"
        ]
        assert len(calls) == 1, f"{len(calls)} banner calls in app.py"
