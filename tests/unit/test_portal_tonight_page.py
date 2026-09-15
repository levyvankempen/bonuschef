"""AppTest coverage for Vanavond, with the degraded states as first-class cases.

With 3 recipes and nothing discounted, the degraded states *are* the initial
experience rather than edge cases, so they get at least as much attention here
as the happy path.
"""

import pandas as pd
import pytest
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError

from bonuschef.portal import freshness
from bonuschef.portal import tonight_page as page
from tests.conftest import run_app

SCRAPED_AT = "2026-09-07T12:00:00Z"  # 14:00 local
FRESH_NOW = pd.Timestamp("2026-09-07 16:00", tz=freshness.LOCAL_TZ)
NEXT_DAY = pd.Timestamp("2026-09-08 09:00", tz=freshness.LOCAL_TZ)


def _opportunity(**overrides) -> pd.DataFrame:
    base = {
        "store_id": ["1876", "1876"],
        "clearance_scraped_at": [SCRAPED_AT] * 2,
        "clearance_is_current": [True, True],
        "recipe_id": [1, 2],
        "recipe_name": ["Zuurkoolstamppot", "Quiche met broccoli"],
        "servings": [4, 4],
        "source_kind": ["pool", "manual"],
        "image_url": [None, None],
        "url": ["https://ah.nl/x", None],
        "is_rankable": [True, True],
        "exclusion_reason": [None, "no_discount_today"],
        "opportunity_rank": [1.0, None],
        "cost_ordinary": [18.70, 10.60],
        "cost_today": [15.30, 10.60],
        "cost_today_bonus_only": [17.20, 10.60],
        "saving_total": [3.40, 0.0],
        "saving_bonus_only": [1.50, 0.0],
        "conditional_saving": [0.0, 0.0],
        "advertised_saving_total": [4.00, 0.0],
        "saving_is_lower_bound": [False, False],
        "saving_covers_whole_packs": [True, True],
        "saving_pct": [18.2, 0.0],
        "cost_today_per_serving": [3.83, 2.65],
        "items_total": [9, 6],
        "items_priced": [9, 6],
        "items_unresolved": [0, 0],
        "items_discounted": [2, 0],
        "items_discounted_clearance": [1, 0],
        "items_offer_withheld_stale": [0, 0],
        "items_conditional_offer": [0, 0],
        "min_stock_remaining": [2.0, None],
        "clearance_items_stock_unknown": [0, 0],
        "earliest_expiry": [pd.NaT, pd.NaT],
        "clearance_items_expiry_unknown": [0, 0],
        "has_insufficient_stock": [False, False],
        "rating_average": [4.6, None],
        "rating_count": [128, None],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _items() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "item_key": ["c:1", "c:2"],
            "item_label": ["zuurkool", "aardappel"],
            "product_name": ["AH Zuurkool", "AH Aardappels"],
            "ordinary_product_link": ["/a", "/b"],
            "offer_product_link": ["/a", None],
            "units": [1, 1],
            "sales_unit_size": ["500 g", None],
            "price_ordinary": [1.59, 2.29],
            "price_today": [0.79, 2.29],
            "item_cost_ordinary": [1.59, 2.29],
            "item_cost_today": [0.79, 2.29],
            "item_saving": [0.80, 0.0],
            "item_conditional_saving": [None, None],
            "item_advertised_saving": [0.90, None],
            "offer_kind": ["clearance", None],
            "offer_price": [0.79, None],
            "bonus_mechanism": [None, None],
            "conditional_mechanism": [None, None],
            "stock": [2.0, None],
            "expires_on": [pd.NaT, pd.NaT],
            "is_discounted": [True, False],
            "is_unresolved": [False, False],
            "reference_is_comparable": [True, True],
            "offer_withheld_stale_reference": [False, False],
            "ordinary_price_age_days": [3, 3],
        }
    )


@pytest.fixture
def wired(monkeypatch):
    """Patch every database call the page makes; nothing touches a warehouse."""
    monkeypatch.setattr(page, "get_engine", lambda: object())
    monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: _opportunity())
    monkeypatch.setattr(page, "read_recipe_opportunity_items", lambda e, r: _items())
    monkeypatch.setattr(page, "read_rejected_recipes", lambda e: pd.DataFrame())
    monkeypatch.setattr(page, "read_bonus_feed_loaded_at", lambda e: FRESH_NOW)
    monkeypatch.setattr(page.freshness, "now", lambda: FRESH_NOW)
    return monkeypatch


def _texts(at) -> str:
    """Everything the page rendered, as one string."""
    parts = []
    for block in (at.markdown, at.caption, at.info, at.warning, at.error, at.subheader):
        parts += [el.value for el in block]
    parts += [el.value for el in at.title]
    return "\n".join(str(p) for p in parts)


class TestTheAnswer:
    def test_the_best_recipe_is_named_with_its_saving(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body
        assert "€3.40 goedkoper" in body

    def test_the_ingredient_responsible_is_named(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "zuurkool" in body
        assert "€0.79" in body and "€1.59" in body

    def test_a_pack_saving_says_it_covers_the_pack(self, wired):
        """100 g of a 500 g pack is costed and saved at the whole pack, which
        would otherwise read as money saved on the meal."""
        at = run_app(page.render_tonight).run()
        assert "hele verpakking" in _texts(at)

    def test_the_rating_is_shown_with_its_vote_count(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "4.6" in body and "128" in body

    def test_runners_up_are_listed_without_competing(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        df.loc[1, "saving_total"] = 0.90
        df.loc[1, "exclusion_reason"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        assert "Ook de moeite waard" in _texts(at)


class TestLowerBounds:
    def test_a_partial_saving_says_minstens(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "saving_is_lower_bound"] = True
        df.loc[0, "items_priced"] = 6
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        assert "minstens €3.40 goedkoper" in _texts(at)

    def test_no_total_is_shown_for_a_partially_priced_recipe(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "saving_is_lower_bound"] = True
        df.loc[0, "items_priced"] = 6
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "totaalprijs blijft onbekend" in body
        assert "in plaats van" not in body


class TestDegradedStates:
    def test_stale_clearance_withdraws_it_and_says_so(self, wired, monkeypatch):
        """Not a blank page. Promotions are national and week-scoped, so they
        have not aged out just because the store scan has."""
        monkeypatch.setattr(page.freshness, "now", lambda: NEXT_DAY)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "niet van vandaag" in body
        # Re-ranked on the bonus-only figure, which is smaller.
        assert "€1.50 goedkoper" in body
        assert "€3.40" not in body

    def test_a_stale_bonus_feed_is_reported_on_its_own_clock(self, wired, monkeypatch):
        """The feed is weekly; judging it by clearance's daily rule would call
        the page stale six days out of seven."""
        monkeypatch.setattr(
            page,
            "read_bonus_feed_loaded_at",
            lambda e: FRESH_NOW - pd.Timedelta(days=20),
        )
        at = run_app(page.render_tonight).run()
        assert "bonusfolder" in _texts(at)

    def test_a_weekly_feed_a_few_days_old_is_not_called_stale(self, wired, monkeypatch):
        monkeypatch.setattr(
            page,
            "read_bonus_feed_loaded_at",
            lambda e: FRESH_NOW - pd.Timedelta(days=5),
        )
        at = run_app(page.render_tonight).run()
        assert "bonusfolder" not in _texts(at)

    def test_nothing_discounted_is_an_answer_not_a_failure(self, wired, monkeypatch):
        df = _opportunity()
        df["opportunity_rank"] = None
        df["saving_total"] = 0.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "geen van je recepten goedkoper" in body
        # An empty page is a dead end; the cheapest to make is still useful.
        assert "voordeligst om te maken" in body

    def test_no_recipes_at_all_offers_the_action_that_would_help(
        self, wired, monkeypatch
    ):
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: pd.DataFrame())
        at = run_app(page.render_tonight).run()
        assert "Toevoegen" in _texts(at)

    def test_an_unbuilt_mart_is_distinct_from_a_broken_database(
        self, wired, monkeypatch
    ):
        def _raise(_):
            raise ProgrammingError("select", {}, Exception("no such relation"))

        monkeypatch.setattr(page, "read_recipe_opportunity", _raise)
        at = run_app(page.render_tonight).run()
        assert "nog niet gedraaid" in _texts(at)
        assert not at.error

    def test_an_unreachable_warehouse_says_so_in_the_portal_s_own_terms(
        self, wired, monkeypatch
    ):
        def _raise(_):
            raise SQLAlchemyError("connection refused")

        monkeypatch.setattr(page, "read_recipe_opportunity", _raise)
        at = run_app(page.render_tonight).run()
        assert "Geen verbinding met de database" in _texts(at)


class TestHonestyAboutCoverage:
    def test_pool_size_and_rankable_count_are_both_visible(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "Berekend over 2 recept(en)" in body
        assert "1 daarvan" in body

    def test_unresolved_ingredients_point_at_the_work_that_helps(
        self, wired, monkeypatch
    ):
        """Resolutions are keyed on AH's concept id, so confirming one counts
        for every recipe that uses it. That compounding is why the review queue
        is the action offered here rather than "add more recipes"."""
        df = _opportunity()
        df.loc[1, "items_unresolved"] = 3
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        assert "gekoppeld ingrediënt" in _texts(at)
        assert [b for b in at.button if "koppelen" in b.label], (
            "the page names the work but never offers it"
        )

    def test_the_review_is_not_offered_when_there_is_nothing_to_review(self, wired):
        at = run_app(page.render_tonight).run()
        assert not [b for b in at.button if "koppelen" in b.label]

    def test_an_unknown_stock_is_never_shown_as_a_bound(self, wired, monkeypatch):
        """MIN skips NULLs, so all-unknown stock would otherwise read as plenty."""
        df = _opportunity()
        df.loc[0, "clearance_items_stock_unknown"] = 1
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        assert "Nog 2" not in _texts(at)


class TestCuration:
    def test_a_pool_recipe_can_be_rejected(self, wired, monkeypatch):
        calls = []
        monkeypatch.setattr(page, "reject_recipe", lambda e, r: calls.append(r))
        at = run_app(page.render_tonight).run()
        buttons = [b for b in at.button if "Niet voor mij" in b.label]
        assert buttons, "a pool recipe must be dismissable"
        buttons[0].click().run()
        assert calls == [1]

    def test_a_hand_entered_recipe_offers_no_reject(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "source_kind"] = "manual"
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        assert not [b for b in at.button if "Niet voor mij" in b.label]

    def test_a_dismissal_is_reversible(self, wired, monkeypatch):
        rejected = pd.DataFrame(
            {
                "recipe_id": [99],
                "recipe_name": ["Iets met bloemkool"],
                "image_url": [None],
                "rating_average": [4.0],
                "rating_count": [10],
                "decided_at": [FRESH_NOW],
            }
        )
        calls = []
        monkeypatch.setattr(page, "read_rejected_recipes", lambda e: rejected)
        monkeypatch.setattr(page, "reinstate_recipe", lambda e, r: calls.append(r))
        at = run_app(page.render_tonight).run()
        buttons = [b for b in at.button if "Terugzetten" in b.label]
        assert buttons, "a dismissal that cannot be undone is a trap"
        buttons[0].click().run()
        assert calls == [99]


class TestPricesAndIngredients:
    """What it normally costs, what it costs now, and the ingredients folded
    away until asked for."""

    def test_both_prices_are_shown_for_the_lead(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "€15.30" in body, "today's price"
        assert "€18.70" in body, "what it normally costs"

    def test_the_ordinary_price_reads_as_the_old_one(self, wired):
        """Struck through and greyed: two bare numbers side by side do not say
        which is which."""
        at = run_app(page.render_tonight).run()
        assert "~~€18.70~~" in _texts(at)

    def test_the_per_serving_price_is_shown(self, wired):
        at = run_app(page.render_tonight).run()
        assert "p.p." in _texts(at)

    def test_no_prices_when_the_basket_is_incomplete(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        df.loc[0, "items_priced"] = 6
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "totaalprijs blijft onbekend" in body
        assert "~~" not in body, "a struck-through price implies a total we do not have"

    def test_ingredients_are_folded_away_until_asked_for(self, wired):
        """The answer to "what shall I cook" is the recipe and its price. On a
        phone an open ingredient list pushes everything else off the screen."""
        at = run_app(page.render_tonight).run()
        expanders = [e for e in at.expander if "Ingrediënten" in e.label]
        assert expanders, "the ingredient list must be reachable"
        # AppTest's Expander does not surface the open/closed state, so read it
        # from the protobuf the page actually emitted rather than trusting the
        # call site.
        assert all(not e.proto.expanded for e in expanders), "it must start closed"

    def test_the_expander_says_how_many_ingredients(self, wired):
        at = run_app(page.render_tonight).run()
        assert any("(9)" in e.label for e in at.expander)

    def test_runners_up_carry_prices_and_ingredients_too(self, wired, monkeypatch):
        """ "How much is this one" is a question you ask of the alternatives."""
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        df.loc[1, "saving_total"] = 0.90
        df.loc[1, "exclusion_reason"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "€10.60" in body, "the runner-up's own price"
        assert len([e for e in at.expander if "Ingrediënten" in e.label]) == 2
