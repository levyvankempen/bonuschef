"""Excluding food you do not eat.

The report was two problems in one sentence: "Seeing all recipes on Vanavond
with spekjes since spekjes are in laatste kans is unwanted. Moreover I don't
even like spekjes." Variety fixes the first. Nothing fixes the second except
being able to say it - and after the variety fix three of six cards were still
bacon, under three different labels.
"""

from contextlib import contextmanager
from types import SimpleNamespace

import pandas as pd
import pytest

from bonuschef.portal import db, profile_page, tonight_page as page
from bonuschef.portal.accounts import Account

PERSON = Account(
    account_id=2,
    username="sample",
    store_id=1876,
    is_operator=False,
    must_change_password=False,
)


# --- finding the other names for one food ------------------------------------


class TestOneFoodUnderManyNames:
    """Eight concepts contain "spek" in one shop, so blocking one concept is
    narrower than "no bacon" and would feel broken on first use."""

    SPEK = [
        "biologische spekreepjes",
        "biologische gerookte spekreepjes",
        "magere spekblokjes",
        "ontbijtspek",
        "speklapjes à la minute",
        "spekreepjes",
        "vegaspekreepjes",
        "plantaardige spekreepjes",
    ]

    def test_every_bacon_is_found_from_any_of_them(self):
        """Symmetric, which a prefix test is not: "spek" leads spekreepjes but
        trails ontbijtspek, so a prefix rule would make which one somebody
        happened to tap decide how much it hid."""
        for chosen in self.SPEK:
            found = [other for other in self.SPEK if db.shares_a_run(other, chosen)]
            assert len(found) == len(self.SPEK), (
                f"blocking {chosen!r} found only {found}"
            )

    def test_it_does_not_join_unrelated_food(self):
        for other in ("courgette", "zalmfilet", "bloemkool", "rijst"):
            assert not db.shares_a_run(other, "spekreepjes"), other

    def test_a_short_name_is_matched_exactly(self):
        """Below the run length there is nothing to share, so it must not match
        everything."""
        assert db.shares_a_run("ui", "ui")
        assert not db.shares_a_run("ui", "uien")

    def test_case_does_not_matter(self):
        assert db.shares_a_run("Spekreepjes", "magere SPEKBLOKJES")


# --- the exclusion takes effect ---------------------------------------------


class _Engine:
    """Answers the two queries the filter makes."""

    def __init__(self, blocked: list[tuple[int, str]], recipes: set[int]):
        self.blocked = blocked
        self.recipes = recipes

    @contextmanager
    def begin(self):
        yield self

    def execute(self, statement, params=None):
        sql = " ".join(str(statement).split())
        if "account_ingredient_blocks" in sql:
            return SimpleNamespace(
                fetchall=lambda: [(c, label) for c, label in self.blocked],
                scalar=lambda: len(self.blocked),
            )
        return SimpleNamespace(
            fetchall=lambda: [(r,) for r in self.recipes], scalar=lambda: None
        )


class TestARecipeWithExcludedFoodIsNotRecommended:
    @pytest.fixture
    def wired(self, monkeypatch):
        from tests.unit.test_portal_tonight_page import _items, _opportunity

        monkeypatch.setattr(page, "get_engine", lambda: object())
        # Without this the real withdrawal runs against a month-old clearance
        # stamp, demotes both recipes and sends the page down the
        # "cheapest anyway" path - which is correct behaviour and not what these
        # tests are about.
        monkeypatch.setattr(
            page.offers, "withdraw_stale_clearance", lambda df, now=None: (df, "")
        )
        monkeypatch.setattr(page, "read_marts_built_at", lambda e: "2026-01-01")
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        monkeypatch.setattr(
            page, "read_recipe_opportunity_items", lambda e, r, *_: _items()
        )
        monkeypatch.setattr(
            page, "read_rejected_recipes", lambda e, a, built_at="": pd.DataFrame()
        )
        monkeypatch.setattr(page, "read_rejected_recipe_ids", lambda e, a: set())
        monkeypatch.setattr(page, "is_kept", lambda e, a, r: False)
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: pd.DataFrame())
        monkeypatch.setattr(page, "read_bonus_feed_loaded_at", lambda e: None)
        monkeypatch.setattr(page, "count_flagged_concepts", lambda e: 0)
        monkeypatch.setattr(
            page, "read_discounted_ingredients", lambda e, *_, **__: pd.DataFrame()
        )
        monkeypatch.setattr(
            page, "read_recipes_using_ingredient", lambda e, s, term, *_: ()
        )
        monkeypatch.setattr(
            page,
            "read_driving_ingredients",
            lambda e, s, *_: pd.DataFrame(
                {
                    "recipe_id": [1, 2],
                    "item_label": ["zuurkool", "broccoli"],
                    "item_saving": [0.8, 0.5],
                    "offer_kind": ["clearance", "bonus"],
                }
            ),
        )

    def _run(self, monkeypatch, blocked, recipes):
        from tests.conftest import run_app

        monkeypatch.setattr(
            page, "read_blocked_concepts", lambda e, a: pd.DataFrame(blocked)
        )
        monkeypatch.setattr(page, "read_recipes_with_concepts", lambda e, s, c: recipes)
        return run_app(page.render_tonight, PERSON).run()

    @staticmethod
    def _texts(at) -> str:
        parts = []
        for block in (at.markdown, at.caption, at.info, at.warning, at.error):
            parts.extend(e.value for e in block)
        return " ".join(parts)

    def test_however_cheap_it_is(self, wired, monkeypatch):
        """Recipe 1 is rank 1 and the cheapest. Excluded food outranks a
        bargain."""
        at = self._run(
            monkeypatch,
            {"concept_id": [1], "label_at_block": ["zuurkool"]},
            {1},
        )
        body = self._texts(at)
        assert "Zuurkoolstamppot" not in body
        assert "Quiche met broccoli" in body

    def test_the_page_says_why_the_rest_are_missing(self, wired, monkeypatch):
        at = self._run(
            monkeypatch,
            {"concept_id": [1], "label_at_block": ["zuurkool"]},
            {1},
        )
        assert "niet eet" in self._texts(at)

    def test_excluding_everything_says_so_rather_than_reading_as_no_offers(
        self, wired, monkeypatch
    ):
        at = self._run(
            monkeypatch,
            {"concept_id": [1, 2], "label_at_block": ["zuurkool", "broccoli"]},
            {1, 2},
        )
        assert at.info, "an empty page must say why it is empty"

    def test_nothing_excluded_leaves_the_page_alone(self, wired, monkeypatch):
        at = self._run(monkeypatch, {}, set())
        assert "Zuurkoolstamppot" in self._texts(at)

    def test_an_unreadable_table_does_not_blank_the_page(self, wired, monkeypatch):
        from sqlalchemy.exc import ProgrammingError
        from tests.conftest import run_app

        def boom(e, a):
            raise ProgrammingError("x", {}, Exception("no table"))

        monkeypatch.setattr(page, "read_blocked_concepts", boom)
        monkeypatch.setattr(page, "read_recipes_with_concepts", lambda e, s, c: set())
        at = run_app(page.render_tonight, PERSON).run()
        assert not at.exception
        assert "Zuurkoolstamppot" in self._texts(at)


# --- it is one person's own --------------------------------------------------


def test_the_exclusion_is_recorded_against_one_account():
    """One person's dislike must not reach anybody else's suggestions."""
    import ast
    import inspect
    from pathlib import Path

    tree = ast.parse(Path(db.__file__).read_text())
    for name in ("read_blocked_concepts", "block_ingredients", "unblock_ingredient"):
        fn = next(
            n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == name
        )
        sql = " ".join(
            c.value
            for c in ast.walk(fn)
            if isinstance(c, ast.Constant) and isinstance(c.value, str)
        )
        assert "account_id" in sql, f"{name} must be scoped to the account"
    assert "account_id" in inspect.getsource(db.read_blocked_concepts)


def test_the_filter_is_not_cached():
    """It changes the moment the button is pressed."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(db.__file__).read_text())
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "read_blocked_concepts"
    )
    assert not any("cache_data" in ast.unparse(d) for d in fn.decorator_list)


def test_the_table_cascades_on_the_account():
    """docs/for-people-invited.md promises that deleting an account takes
    everything with it. That should hold structurally, not by anybody
    remembering."""
    from bonuschef.portal import schema

    statement = next(s for s in schema._STATEMENTS if "account_ingredient_blocks" in s)
    assert "ON DELETE CASCADE" in statement


def test_profiel_is_where_it_is_reviewed_and_reversed():
    """A dislike is not a trap, the same contract the dismissal list has."""
    import inspect

    source = inspect.getsource(profile_page)
    assert "read_blocked_concepts" in source
    assert "unblock_ingredient" in source
