"""Settling what an ingredient can be bought as.

The SQL half is exercised against the real database because the guarantees that
matter here - a person's decision surviving the matcher, an empty choice being a
valid answer - live in the statements rather than in Python, and a stubbed
engine would assert only that the right strings were sent.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from bonuschef.portal.db import (
    add_resolution_products,
    confirm_resolution,
    ensure_catalogue_tables,
    propose_products,
)

_CONCEPT = 999_000_001
_OTHER = 999_000_002


@pytest.fixture
def engine():
    """A live connection, skipped when there isn't one.

    The suite is network-free by design; this is the local Postgres the whole
    project runs against, and these assertions are about SQL semantics.
    """
    url = (
        f"postgresql+psycopg2://{os.getenv('PG_USER', 'postgres')}:"
        f"{os.getenv('PG_PASSWORD', 'postgres')}@{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('PG_PORT', '5455')}/{os.getenv('PG_DB', 'postgres')}"
    )
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        # ty cannot see through pytest's @_with_exception decorator, so it
        # reads skip() as taking no arguments. Upstream limitation, not ours.
        pytest.skip("no local Postgres")  # ty: ignore[too-many-positional-arguments]
    ensure_catalogue_tables(eng)
    yield eng
    with eng.begin() as conn:
        for cid in (_CONCEPT, _OTHER):
            conn.execute(
                text("DELETE FROM public.ah_ingredient_products WHERE concept_id = :c"),
                {"c": cid},
            )
            conn.execute(
                text("DELETE FROM public.ah_ingredient_review WHERE concept_id = :c"),
                {"c": cid},
            )


def _attached(engine, concept_id):
    with engine.begin() as conn:
        return {
            r[0]: r[1]
            for r in conn.execute(
                text("""SELECT product_link, confirmed_at IS NOT NULL
                        FROM public.ah_ingredient_products WHERE concept_id = :c"""),
                {"c": concept_id},
            )
        }


def _review(engine, concept_id):
    with engine.begin() as conn:
        return conn.execute(
            text(
                "SELECT review_state FROM public.ah_ingredient_review WHERE concept_id = :c"
            ),
            {"c": concept_id},
        ).scalar()


def test_a_decision_survives_the_matcher(engine):
    """The durability guarantee, and the reason it lives in SQL: the matcher
    runs unattended on every adoption, so a guard in a code path someone can
    forget to call is not a guard."""
    propose_products(
        engine,
        [
            {
                "concept_id": _CONCEPT,
                "product_link": "a",
                "product_name": "Olijfolie mild",
            },
            {
                "concept_id": _CONCEPT,
                "product_link": "b",
                "product_name": "Olijfolie extra",
            },
        ],
    )
    confirm_resolution(engine, _CONCEPT, ["a"])
    assert _attached(engine, _CONCEPT) == {"a": True}, "deselected product removed"

    # The matcher runs again, as it does on every adoption.
    propose_products(
        engine,
        [
            {
                "concept_id": _CONCEPT,
                "product_link": "a",
                "product_name": "SOMETHING ELSE",
            },
        ],
    )
    with engine.begin() as conn:
        name = conn.execute(
            text("""SELECT product_name FROM public.ah_ingredient_products
                    WHERE concept_id = :c AND product_link = 'a'"""),
            {"c": _CONCEPT},
        ).scalar()
    assert name == "Olijfolie mild", "the matcher overwrote a decision"


def test_the_matcher_may_still_fill_an_undecided_gap(engine):
    propose_products(
        engine,
        [
            {"concept_id": _OTHER, "product_link": "x", "product_name": "First"},
        ],
    )
    propose_products(
        engine,
        [
            {"concept_id": _OTHER, "product_link": "x", "product_name": "Second"},
        ],
    )
    with engine.begin() as conn:
        name = conn.execute(
            text("""SELECT product_name FROM public.ah_ingredient_products
                    WHERE concept_id = :c"""),
            {"c": _OTHER},
        ).scalar()
    assert name == "Second", "an untouched proposal is not a decision"


def test_choosing_nothing_records_that_nothing_satisfies_it(engine):
    """An ingredient with no purchasable equivalent is an answer, not an
    incomplete form. Without this state it stays outstanding forever and the
    list of work never empties."""
    propose_products(
        engine,
        [
            {"concept_id": _CONCEPT, "product_link": "a", "product_name": "Wrong"},
        ],
    )
    confirm_resolution(engine, _CONCEPT, [])
    assert _attached(engine, _CONCEPT) == {}
    assert _review(engine, _CONCEPT) == "none_exists"


def test_choosing_products_records_it_as_resolved(engine):
    propose_products(
        engine,
        [
            {"concept_id": _CONCEPT, "product_link": "a", "product_name": "Right"},
        ],
    )
    confirm_resolution(engine, _CONCEPT, ["a"])
    assert _review(engine, _CONCEPT) == "resolved"


def test_several_products_can_satisfy_one_ingredient(engine):
    """Which is cheapest changes daily, which is the premise of the project."""
    propose_products(
        engine,
        [
            {"concept_id": _CONCEPT, "product_link": "a", "product_name": "A"},
            {"concept_id": _CONCEPT, "product_link": "b", "product_name": "B"},
        ],
    )
    confirm_resolution(engine, _CONCEPT, ["a", "b"])
    assert _attached(engine, _CONCEPT) == {"a": True, "b": True}


def test_a_person_can_attach_a_product_the_matcher_never_proposed(engine):
    add_resolution_products(
        engine, _CONCEPT, [{"product_link": "z", "product_name": "Found by hand"}]
    )
    confirm_resolution(engine, _CONCEPT, ["z"])
    assert _attached(engine, _CONCEPT) == {"z": True}


class TestAutomaticProposals:
    """The pool is inert without these. 900 recipes priced 3.3% of their
    ingredients and ranked nothing until the matcher ran across them."""

    def test_unresolved_concepts_are_taken_most_used_first(self):
        """Concept frequency is steep - a few hundred cover most ingredient
        lines - so an interrupted run should have done the work that mattered."""
        from bonuschef.dags.defs.assets.resolution import _UNRESOLVED_CONCEPTS

        assert "ORDER BY uses DESC" in _UNRESOLVED_CONCEPTS
        # Only concepts nobody has resolved yet; re-proposing over a decision is
        # what propose_products' WHERE clause exists to prevent, but not asking
        # in the first place is cheaper.
        assert "p.concept_id IS NULL" in _UNRESOLVED_CONCEPTS

    def test_proposals_never_overwrite_a_persons_decision(self):
        """The guard lives in propose_products, and this job depends on it: the
        matcher re-runs whenever the catalogue moves, so without it every
        correction would be reverted on the next product load."""
        import inspect

        from bonuschef.portal.db import propose_products

        source = inspect.getsource(propose_products)
        assert "WHERE p.confirmed_at IS NULL" in source

    def test_the_matcher_needs_no_network(self):
        """It runs against dim_product, not AH. That is what makes it safe to
        re-run freely and what keeps it off the credential budget."""
        import inspect

        from bonuschef.portal import matching

        source = inspect.getsource(matching)
        for network in ("requests", "urllib", "graphql", "manager_from_env"):
            assert network not in source, f"the matcher must not reach {network}"


class TestAHProductSearch:
    """AH's own search is the mechanism behind "Kies producten", and it resolves
    phrasings no local name match can reach - at the cost of being confidently
    wrong about one time in five."""

    def test_it_keeps_several_hits_rather_than_one_winner(self):
        from bonuschef.utils import ah_recipes as R

        assert R.PRODUCT_SEARCH_KEEP > 1, (
            "AH's top hit for 'middelgrote ui' is a spring onion; one confident "
            "wrong answer is worse for review than a short list"
        )

    def test_a_hit_without_a_joinable_id_is_dropped(self, monkeypatch):
        """The webshop id is the only thing that connects AH's answer to a price
        we hold. A hit without one cannot be costed and must not be proposed."""
        from bonuschef.utils import ah_recipes as R

        def fake_post(query, variables):
            return {
                "searchProducts": {
                    "products": [
                        {"id": 4164, "title": "AH Courgette"},
                        {"id": None, "title": "Iets zonder id"},
                        {"id": 99, "title": ""},
                    ]
                }
            }, []

        monkeypatch.setattr(
            R,
            "manager_from_env",
            lambda: type("M", (), {"graphql_partial": staticmethod(fake_post)})(),
        )
        hits = R.search_products("courgette")
        assert [h.webshop_id for h in hits] == [4164]

    def test_an_unreachable_ah_raises_rather_than_returning_nothing(self, monkeypatch):
        """Returning [] would read as "AH sells nothing like this", which would
        park the concept as unresolvable instead of retrying it next run."""
        from bonuschef.utils import ah_recipes as R

        def boom(query, variables):
            raise RuntimeError("connection reset")

        monkeypatch.setattr(
            R,
            "manager_from_env",
            lambda: type("M", (), {"graphql_partial": staticmethod(boom)})(),
        )
        with pytest.raises(R.AHRecipeUnavailable):
            R.search_products("courgette")

    def test_the_lookup_budget_is_bounded(self):
        """A fresh pool has ~1,400 concepts to ask about. Spending that in one
        burst puts the credential every scheduled job depends on at risk, and
        clearance - which cannot be backfilled - has priority."""
        from bonuschef.dags.defs.assets.resolution import MAX_AH_LOOKUPS_PER_RUN

        assert 0 < MAX_AH_LOOKUPS_PER_RUN <= 500

    def test_the_local_matcher_runs_first(self):
        """It is free and conservative, so whatever it settles never costs an
        AH request."""
        # @asset wraps the function in an AssetsDefinition, so read the module
        # source rather than the object.
        from pathlib import Path as _Path

        import bonuschef.dags.defs.assets.resolution as resolution

        source = _Path(resolution.__file__).read_text()
        body = source[source.index("def ah__ingredient_proposals_asset") :]
        assert body.index("propose_for(engine") < body.index("_propose_from_ah(")


class TestAHLookupResilience:
    """A read timeout is not a rejection, and treating them alike cost a whole
    run's budget on the first live pass: 101 lookups in, one request timed out,
    the run gave up - and the same pace managed 40 for 40 minutes later."""

    def test_a_credential_rejection_stops_immediately(self, monkeypatch):
        """Retrying through the auth fallback chain is how a refresh token dies."""
        from dagster import build_asset_context

        from bonuschef.dags.defs.assets import resolution
        from bonuschef.utils.ah_auth import AHAuthError
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable

        calls = []

        def reject(term):
            calls.append(term)
            raise AHRecipeUnavailable("nope") from AHAuthError("401")

        monkeypatch.setattr(resolution, "search_products", reject)
        monkeypatch.setattr(resolution, "_webshop_id_to_product", lambda e: {})
        _, spent, unreachable = resolution._propose_from_ah(
            object(), {1: "ui", 2: "prei", 3: "kaas"}, build_asset_context()
        )
        assert len(calls) == 1, "a rejected credential must not be retried"
        assert spent == 0 and unreachable

    def test_a_transient_timeout_does_not_end_the_run(self, monkeypatch):
        from dagster import build_asset_context

        from bonuschef.dags.defs.assets import resolution
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable, ProductHit

        seen = []

        def flaky(term):
            seen.append(term)
            if len(seen) == 1:
                raise AHRecipeUnavailable("Read timed out")
            return [ProductHit(webshop_id=4164, title="AH Courgette")]

        monkeypatch.setattr(resolution, "search_products", flaky)
        monkeypatch.setattr(
            resolution,
            "_webshop_id_to_product",
            lambda e: {4164: ("/x", "AH Courgette")},
        )
        proposals, spent, unreachable = resolution._propose_from_ah(
            object(), {1: "ui", 2: "prei", 3: "kaas"}, build_asset_context()
        )
        assert not unreachable, "one timeout must not abandon the budget"
        assert spent == 2, "it carried on after the blip"
        assert len(proposals) == 2

    def test_repeated_failures_do_give_up(self, monkeypatch):
        from dagster import build_asset_context

        from bonuschef.dags.defs.assets import resolution
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable

        def always_fail(term):
            raise AHRecipeUnavailable("Read timed out")

        monkeypatch.setattr(resolution, "search_products", always_fail)
        monkeypatch.setattr(resolution, "_webshop_id_to_product", lambda e: {})
        _, spent, unreachable = resolution._propose_from_ah(
            object(), {i: "x" for i in range(10)}, build_asset_context()
        )
        assert unreachable and spent == 0

    def test_a_product_ah_sells_but_we_cannot_price_is_not_proposed(self, monkeypatch):
        """Putting an unpriceable product in front of someone as an answer is
        worse than leaving the ingredient unresolved."""
        from dagster import build_asset_context

        from bonuschef.dags.defs.assets import resolution
        from bonuschef.utils.ah_recipes import ProductHit

        monkeypatch.setattr(
            resolution,
            "search_products",
            lambda term: [
                ProductHit(webshop_id=4164, title="AH Courgette"),
                ProductHit(webshop_id=999999, title="Iets wat wij niet volgen"),
            ],
        )
        monkeypatch.setattr(
            resolution,
            "_webshop_id_to_product",
            lambda e: {4164: ("/x", "AH Courgette")},
        )
        proposals, _, _ = resolution._propose_from_ah(
            object(), {1: "courgette"}, build_asset_context()
        )
        assert [p["product_link"] for p in proposals] == ["/x"]


class TestCorrectingAWrongMatch:
    """The case that needs search most is a proposal that is wrong, not one
    that is missing - and that was the one case the dialog hid it for."""

    def test_search_is_offered_even_when_a_product_was_proposed(self):
        import inspect

        from bonuschef.portal import review

        source = inspect.getsource(review._render_body)
        probe = source.index('key=f"probe_{concept_id}"')
        guard = source.index("if not options:") if "if not options:" in source else -1
        assert guard == -1 or guard > probe, (
            "hiding the search box behind 'no options' leaves someone with a "
            "wrong proposal unable to reach the right product"
        )

    def test_a_search_adds_to_the_proposals_rather_than_replacing_them(self):
        import inspect

        from bonuschef.portal import review

        source = inspect.getsource(review._render_body)
        assert "**options," in source, (
            "replacing would silently deselect a good proposal the moment someone typed"
        )

    def test_every_word_must_appear_but_not_as_a_phrase(self):
        """ "(olijf)olie" as a phrase matches nothing; its words find the olive
        oils. That is the difference between the search being usable with an
        ingredient name and not."""
        import inspect

        from bonuschef.portal.db import search_catalogue_products

        source = inspect.getsource(search_catalogue_products)
        assert "AND" in source and "re.split" in source

    def test_punctuation_does_not_defeat_the_search(self):
        import re

        pattern = r"[^0-9a-zA-ZäëïöüéèáàçñÄËÏÖÜÉÈÁÀÇÑ]+"
        assert [w for w in re.split(pattern, "(olijf)olie") if w] == ["olijf", "olie"]
        assert [w for w in re.split(pattern, "witte kaas 45+") if w] == [
            "witte",
            "kaas",
            "45",
        ]

    def test_a_confirmed_choice_outlives_everything_that_rewrites_the_pool(self):
        """The persistence question, pinned.

        ah_ingredient_products is portal-owned: dbt reads it as a source and
        creates none of it, so --full-refresh cannot touch it. propose_products
        will not write over a confirmed row. And the weekly pool refetch merges
        recipes, never resolutions.
        """
        import inspect

        from bonuschef.portal.db import confirm_resolution, propose_products

        assert "confirmed_at = now()" in inspect.getsource(confirm_resolution)
        assert "WHERE p.confirmed_at IS NULL" in inspect.getsource(propose_products)
