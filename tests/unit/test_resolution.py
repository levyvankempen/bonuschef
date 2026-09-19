"""Settling what an ingredient can be bought as.

The SQL half is exercised against the real database because the guarantees that
matter here - a person's decision surviving the matcher, an empty choice being a
valid answer - live in the statements rather than in Python, and a stubbed
engine would assert only that the right strings were sent.
"""

from __future__ import annotations

from typing import Any, cast

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


def test_confirming_drops_every_cache_the_change_invalidates():
    """A correction that takes fifteen minutes to appear reads as a correction
    that did not save.

    The opportunity reads were missing from this list: the write landed, the
    rebuild ran, and Vanavond kept serving its cache showing the old product.
    """
    import inspect

    from bonuschef.portal import review

    source = inspect.getsource(review._clear_reads)
    for reader in (
        "read_unresolved_concepts",
        "read_concept_resolution",
        "search_catalogue_products",
        "read_recipe_opportunity",
        "read_recipe_opportunity_items",
    ):
        assert reader in source, f"{reader} survives a confirmation"


class TestClassificationFiltersProposals:
    """The classification checks, exercised through the asset rather than the
    pure functions - the filter is only worth anything if it is actually in
    the path that writes proposals."""

    def _run(self, monkeypatch, concept_name, hits):
        from bonuschef.dags.defs.assets.resolution import _propose_from_ah

        monkeypatch.setattr(
            "bonuschef.dags.defs.assets.resolution.search_products",
            lambda term: hits,
        )
        monkeypatch.setattr(
            "bonuschef.dags.defs.assets.resolution._webshop_id_to_product",
            lambda engine: {
                h.webshop_id: (f"wi{h.webshop_id}/x", h.title) for h in hits
            },
        )

        class _Log:
            def debug(self, *a, **k):
                pass

            def info(self, *a, **k):
                pass

            def warning(self, *a, **k):
                pass

        class _Ctx:
            log = _Log()

        # Duck-typed stand-ins: _propose_from_ah touches only the crosswalk
        # (monkeypatched) and context.log.
        proposals, _spent, _down = _propose_from_ah(
            cast(Any, object()), {1: concept_name}, cast(Any, _Ctx())
        )
        return [p["product_name"] for p in proposals]

    def test_dried_dill_is_not_proposed_for_fresh_dill(self, monkeypatch):
        """The originating bug, through the real code path."""
        from bonuschef.utils.ah_recipes import ProductHit

        names = self._run(
            monkeypatch,
            "verse dille",
            [
                ProductHit(
                    webshop_id=2,
                    title="Verstegen Dille",
                    department="Houdbaar",
                    taxonomy_path=("Kruiden", "Gedroogde kruiden", "Dille"),
                ),
                ProductHit(
                    webshop_id=1,
                    title="AH Dille",
                    department="Vers",
                    taxonomy_path=("Groente", "Verse kruiden"),
                ),
            ],
        )
        assert "Verstegen Dille" not in names
        assert names == ["AH Dille"]

    def test_a_non_food_product_is_not_proposed(self, monkeypatch):
        from bonuschef.utils.ah_recipes import ProductHit

        names = self._run(
            monkeypatch,
            "wortel",
            [
                ProductHit(
                    webshop_id=9,
                    title="AH Vormservet wortel",
                    department="Non Food",
                    taxonomy_path=("Huishouden",),
                ),
                ProductHit(
                    webshop_id=8,
                    title="AH Winterpeen",
                    department="Vers",
                    taxonomy_path=("Groente", "Wortel"),
                ),
            ],
        )
        assert names == ["AH Winterpeen"]

    def test_an_unqualified_ingredient_still_gets_both(self, monkeypatch):
        """Abstention, through the asset. "dille" did not ask for fresh, so
        nothing may be rejected on that basis."""
        from bonuschef.utils.ah_recipes import ProductHit

        names = self._run(
            monkeypatch,
            "dille",
            [
                ProductHit(
                    webshop_id=2, title="Verstegen Dille", department="Houdbaar"
                ),
                ProductHit(webshop_id=1, title="AH Dille", department="Vers"),
            ],
        )
        assert set(names) == {"Verstegen Dille", "AH Dille"}

    def test_an_unclassified_hit_is_still_proposed(self, monkeypatch):
        """Products AH declines to classify must not disappear from
        resolution - that would be a silent loss of coverage."""
        from bonuschef.utils.ah_recipes import ProductHit

        names = self._run(
            monkeypatch,
            "verse dille",
            [ProductHit(webshop_id=1, title="Onbekend dille", department="")],
        )
        assert names == ["Onbekend dille"]

    def test_the_taxonomy_named_candidate_is_proposed_first(self, monkeypatch):
        from bonuschef.utils.ah_recipes import ProductHit

        names = self._run(
            monkeypatch,
            "witte kaas",
            [
                ProductHit(
                    webshop_id=3,
                    title="AH Truffelsalami parmezaanse kaas",
                    department="Vers",
                    taxonomy_path=("Vleeswaren", "Salami"),
                ),
                ProductHit(
                    webshop_id=4,
                    title="AH Witte kaas 40+",
                    department="Vers",
                    taxonomy_path=("Kaas", "Witte kaas"),
                ),
            ],
        )
        assert names[0] == "AH Witte kaas 40+"


class TestRecheckingExistingLinks:
    """The pass that fixes what is already in the database.

    This is the only operation in the resolution path that deletes, so the
    tests here are mostly about what it refuses to do.
    """

    def _run(self, monkeypatch, links, classified):
        import bonuschef.dags.defs.assets.resolution as mod

        removed: list[tuple] = []
        monkeypatch.setattr(mod, "read_linked_products", lambda engine: links)
        monkeypatch.setattr(mod, "fetch_product_taxonomy", lambda ids: classified)
        monkeypatch.setattr(
            mod,
            "withdraw_proposals",
            lambda engine, pairs: (removed.extend(pairs), len(pairs))[1],
        )

        class _Log:
            def __init__(self):
                self.warnings = []

            def debug(self, *a, **k):
                pass

            def info(self, *a, **k):
                pass

            def warning(self, msg, *a):
                self.warnings.append(msg % a if a else msg)

        class _Ctx:
            log = _Log()

        ctx = _Ctx()
        stats = mod.recheck_existing_links(cast(Any, object()), cast(Any, ctx))
        return stats, removed, ctx.log.warnings

    @staticmethod
    def _link(cid, name, wid, pname, confirmed=False):
        return {
            "concept_id": cid,
            "concept_name": name,
            "product_link": f"wi{wid}/x",
            "product_name": pname,
            "confirmed": confirmed,
        }

    @staticmethod
    def _hit(wid, title, dept):
        from bonuschef.utils.ah_recipes import ProductHit

        return ProductHit(webshop_id=wid, title=title, department=dept)

    def test_a_contradicting_proposal_is_withdrawn(self, monkeypatch):
        links = [
            self._link(1, "verse dille", 2, "Verstegen Dille"),
            self._link(1, "verse dille", 3, "AH Dille"),
        ]
        classified = {
            2: self._hit(2, "Verstegen Dille", "Houdbaar"),
            3: self._hit(3, "AH Dille", "Vers"),
        }
        stats, removed, _ = self._run(monkeypatch, links, classified)
        assert removed == [(1, "wi2/x")]
        assert stats["withdrawn"] == 1

    def test_a_confirmed_link_is_never_withdrawn(self, monkeypatch):
        """A person decided this. No rule here outranks that."""
        links = [
            self._link(1, "verse dille", 2, "Verstegen Dille", confirmed=True),
            self._link(1, "verse dille", 3, "AH Dille"),
        ]
        classified = {
            2: self._hit(2, "Verstegen Dille", "Houdbaar"),
            3: self._hit(3, "AH Dille", "Vers"),
        }
        _stats, removed, _ = self._run(monkeypatch, links, classified)
        assert removed == []

    def test_the_last_candidate_is_never_removed(self, monkeypatch):
        """Removing it would turn a visibly wrong price into a silently
        missing one, and silence is the worse failure."""
        links = [self._link(1, "verse dille", 2, "Verstegen Dille")]
        classified = {2: self._hit(2, "Verstegen Dille", "Houdbaar")}
        stats, removed, warnings = self._run(monkeypatch, links, classified)
        assert removed == []
        assert stats["flagged"] == 1
        assert any("verse dille" in w for w in warnings), (
            "emptying was avoided but nobody was told"
        )

    def test_a_product_ah_no_longer_classifies_is_left_alone(self, monkeypatch):
        """Delisted, or simply unclassified. Unknown is not wrong, and
        withdrawing on no evidence would quietly shrink coverage."""
        links = [
            self._link(1, "verse dille", 2, "Iets ouds"),
            self._link(1, "verse dille", 3, "AH Dille"),
        ]
        classified = {3: self._hit(3, "AH Dille", "Vers")}
        _stats, removed, _ = self._run(monkeypatch, links, classified)
        assert removed == []

    def test_a_correct_existing_link_survives(self, monkeypatch):
        """ "gedroogde dille" -> Verstegen Dille is right, and a change that
        broke it would be worse than the bug it fixes."""
        links = [self._link(1, "gedroogde dille", 2, "Verstegen Dille")]
        classified = {2: self._hit(2, "Verstegen Dille", "Houdbaar")}
        stats, removed, _ = self._run(monkeypatch, links, classified)
        assert removed == []
        assert stats["flagged"] == 0

    def test_being_unable_to_reach_ah_changes_nothing(self, monkeypatch):
        import bonuschef.dags.defs.assets.resolution as mod
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable

        def _boom(ids):
            raise AHRecipeUnavailable("down")

        monkeypatch.setattr(
            mod,
            "read_linked_products",
            lambda engine: [self._link(1, "verse dille", 2, "Verstegen Dille")],
        )
        monkeypatch.setattr(mod, "fetch_product_taxonomy", _boom)
        removed = []
        monkeypatch.setattr(
            mod,
            "withdraw_proposals",
            lambda engine, pairs: (removed.extend(pairs), len(pairs))[1],
        )

        class _Ctx:
            class log:
                @staticmethod
                def warning(*a, **k):
                    pass

                @staticmethod
                def info(*a, **k):
                    pass

        stats = mod.recheck_existing_links(cast(Any, object()), cast(Any, _Ctx()))
        assert removed == []
        assert stats.get("unreachable") is True
