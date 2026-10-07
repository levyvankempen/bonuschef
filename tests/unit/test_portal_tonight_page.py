"""AppTest coverage for Vanavond, with the degraded states as first-class cases.

With 3 recipes and nothing discounted, the degraded states *are* the initial
experience rather than edge cases, so they get at least as much attention here
as the happy path.
"""

from pathlib import Path
import pandas as pd
import pytest
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError

from bonuschef.portal import freshness
from bonuschef.portal import tonight_page as page
from bonuschef.portal.accounts import Account
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
        "partial_cost_ordinary": [18.70, 10.60],
        "partial_cost_today": [15.30, 10.60],
        "partial_cost_today_bonus_only": [17.20, 10.60],
        "cost_today_per_serving_bonus_only": [4.30, 2.65],
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


def _healthy(**overrides) -> pd.DataFrame:
    base = {
        "job_name": ["markdowns_refresh", "token_heartbeat"],
        "last_success": [FRESH_NOW, FRESH_NOW],
        "failures_today": [0, 0],
        "overdue_h": [1.0, 2.0],
        "tolerance_h": [3.0, 36.0],
        "what": ["de laatste kans-koopjes", "de AH-inlog"],
        "is_overdue": [False, False],
    }
    base.update(overrides)
    return pd.DataFrame(base)


def _items() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "item_key": ["c:1", "c:2"],
            "concept_id": [1, 2],
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
            "item_cost_today_bonus_only": [1.59, 2.29],
            "price_today_bonus_only": [1.59, 2.29],
            "item_saving": [0.80, 0.0],
            "item_saving_bonus_only": [0.0, 0.0],
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
    # The build stamp is the readers' cache key, so they take it as an
    # argument. *_ rather than a named parameter: the fixture should not have
    # to be edited again if another key joins it.
    monkeypatch.setattr(page, "read_marts_built_at", lambda e: "2026-01-01T00:00:00")
    monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: _opportunity())
    monkeypatch.setattr(
        page, "read_recipe_opportunity_items", lambda e, r, *_: _items()
    )
    # The ingredient filter's two readers. Nothing offered by default, so the
    # page without a search term is the case most tests exercise.
    monkeypatch.setattr(
        page, "read_discounted_ingredients", lambda e, *_, **__: pd.DataFrame()
    )
    monkeypatch.setattr(
        page, "read_recipes_using_ingredient", lambda e, s, term, *_: ()
    )
    # Nothing dismissed by default, so the ranking is the case most tests want.
    monkeypatch.setattr(page, "read_rejected_recipe_ids", lambda e, a: set())
    # Nothing excluded by default.
    monkeypatch.setattr(page, "read_blocked_concepts", lambda e, a: pd.DataFrame())
    monkeypatch.setattr(page, "read_recipes_with_concepts", lambda e, s, c: set())
    monkeypatch.setattr(
        page,
        "read_known_concepts",
        lambda e, s, *_: pd.DataFrame({"concept_id": [1, 2], "item_label": ["a", "b"]}),
    )
    monkeypatch.setattr(page, "block_ingredients", lambda e, a, c: len(c))
    # One row per recipe: which discounted ingredient it owes its saving to.
    monkeypatch.setattr(
        page,
        "read_driving_ingredients",
        lambda e, s, *_: pd.DataFrame(
            {
                "recipe_id": [1, 2],
                "item_label": ["zuurkool", "broccoli"],
                "item_saving": [0.80, 0.50],
                "offer_kind": ["clearance", "bonus"],
            }
        ),
    )
    monkeypatch.setattr(
        page, "read_rejected_recipes", lambda e, a, built_at="": pd.DataFrame()
    )
    # Nothing saved by default, so the keep/reject controls are the case a
    # test sees unless it says otherwise.
    monkeypatch.setattr(page, "is_kept", lambda e, a, r: False)
    monkeypatch.setattr(page, "read_bonus_feed_loaded_at", lambda e: FRESH_NOW)
    monkeypatch.setattr(page, "read_pipeline_health", lambda e: _healthy())
    monkeypatch.setattr(page.freshness, "now", lambda: FRESH_NOW)
    return monkeypatch


def _open_card(at, which: int = 0):
    """Open one card's detail.

    Every card is compact since the lead was removed: the highlights are on the
    face and the ingredients, ratings and actions are one tap away.
    """
    more = [b for b in at.button if b.label == "Meer"]
    assert more, "a card must offer its detail"
    return more[which].click().run()


def _open_items(at, which: int = 0):
    """Open a card's ingredient list.

    Two taps now: every card is compact since the lead was removed, so the
    detail - ingredients, ratings, actions - sits behind "Meer", and the list
    behind a second button inside it.

    Both are buttons rather than expanders. Streamlit executes an expander's
    body whether or not it is open, so the list cost a query and ~50 controls
    per render of a page nobody had asked it of.
    """
    more = [b for b in at.button if b.label == "Meer"]
    if more:
        at = more[which].click().run()
    buttons = [b for b in at.button if "Ingrediënten" in b.label]
    assert buttons, "the ingredient list must be reachable"
    return buttons[0].click().run()


def _texts(at) -> str:
    """Everything the page rendered, as one string."""
    parts = []
    for block in (
        at.markdown,
        at.caption,
        at.info,
        at.warning,
        at.error,
        at.success,
        at.subheader,
    ):
        parts += [el.value for el in block]
    parts += [el.value for el in at.title]
    return "\n".join(str(p) for p in parts)


class TestTheAnswer:
    def test_the_best_recipe_is_named_with_its_saving(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body
        assert "€3.40 goedkoper" in body

    def test_the_ingredient_responsible_is_named_on_the_card(self, wired):
        """Not "2x bonus". The person is standing in front of one particular
        discounted thing, and the noun is the whole answer."""
        at = run_app(page.render_tonight).run()
        # st.badge is emitted as markdown, as ":orange-badge[...]".
        badges = " ".join(m.value for m in at.markdown if "-badge[" in m.value)
        assert "zuurkool" in badges, "by name, without opening anything"
        assert "0.80" in badges, "and with what it saves"
        assert "orange" in badges, "orange for a clearance line, as the list uses"

    def test_the_prices_behind_that_saving_are_in_the_list(self, wired):
        at = _open_items(run_app(page.render_tonight).run())
        body = _texts(at)
        assert "€0.79" in body and "€1.59" in body

    def test_a_pack_saving_says_it_covers_the_pack(self, wired):
        """100 g of a 500 g pack is costed and saved at the whole pack, which
        would otherwise read as money saved on the meal."""
        at = _open_items(run_app(page.render_tonight).run())
        assert "hele verpakking" in _texts(at)

    def test_the_rating_is_shown_with_its_vote_count(self, wired):
        at = _open_card(run_app(page.render_tonight).run())
        body = _texts(at)
        assert "4.6" in body and "128" in body

    def test_every_answer_is_presented_alike(self, wired, monkeypatch):
        """There used to be a lead card - full width, bigger type, its own
        picture - with the rest below as alternatives. That made the page show
        one recipe and a hint of others. Rank order already says which is best,
        and cards that look alike are easier to compare, which is the task."""
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        df.loc[1, "saving_total"] = 0.90
        df.loc[1, "exclusion_reason"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body and "Quiche met broccoli" in body
        assert "Ook de moeite waard" not in body, "no lead, so nothing is 'also'"
        assert len([b for b in at.button if b.label == "Meer"]) == 2, (
            "both are compact cards"
        )


class TestLowerBounds:
    def test_a_partial_saving_says_minstens(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "saving_is_lower_bound"] = True
        df.loc[0, "items_priced"] = 6
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert "minstens €3.40 goedkoper" in _texts(at)

    def test_a_partial_basket_still_shows_a_price(self, wired, monkeypatch):
        """The rule changed deliberately.

        Withholding was right when every match was hand-confirmed. Most matches
        in the pool are machine proposals, so most baskets are incomplete, and a
        recipe with a rough price and one doubtful ingredient is more use than a
        recipe with no price at all. The estimate is marked as one.
        """
        df = _opportunity()
        df.loc[0, "saving_is_lower_bound"] = True
        df.loc[0, "items_priced"] = 6
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "±€15.30" in body, "an estimate, and visibly one"
        assert "Schatting over 6 van 9 ingrediënten" in body


class TestDegradedStates:
    def test_stale_clearance_withdraws_it_and_says_so(self, wired, monkeypatch):
        """Not a blank page. Promotions are national and week-scoped, so they
        have not aged out just because the store scan has."""
        monkeypatch.setattr(page.freshness, "now", lambda: NEXT_DAY)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "niet van vandaag" in body
        assert "€1.50 goedkoper" in body

    def test_withdrawing_clearance_reaches_every_figure(self, wired, monkeypatch):
        """The previous version of this test asserted only that "€3.40" was
        absent - a literal the page never prints - so it passed while the
        per-serving price, the estimate and every ingredient line stayed
        clearance-priced under a banner saying clearance did not count."""
        monkeypatch.setattr(page.freshness, "now", lambda: NEXT_DAY)
        at = run_app(page.render_tonight).run()
        body = _texts(at)

        assert "€17.20" in body, "the bonus-only total"
        assert "€15.30" not in body, "the clearance-inclusive total survived"
        assert "€4.30" in body, "per-serving of the bonus-only total"
        assert "€3.83" not in body, "per-serving still derived from clearance"
        assert "€0.79" not in body, "a clearance price on an ingredient line"
        # The badge, not the banner - the banner legitimately says "de laatste
        # kans-koopjes tellen daarom even niet mee".
        assert "laatste kans · nog" not in body, (
            "urgency badge from a scan that is not today's"
        )

    def test_a_partial_basket_also_withdraws_clearance(self, wired, monkeypatch):
        """The estimate is what most of the pool shows, and it had no
        bonus-only twin at all."""
        df = _opportunity()
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        df.loc[0, "items_priced"] = 6
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        monkeypatch.setattr(page.freshness, "now", lambda: NEXT_DAY)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "±€17.20" in body
        assert "±€15.30" not in body

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
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "geen van je recepten goedkoper" in body
        # An empty page is a dead end; the cheapest to make is still useful.
        assert "voordeligst om te maken" in body

    def test_no_recipes_at_all_offers_the_action_that_would_help(
        self, wired, monkeypatch
    ):
        monkeypatch.setattr(
            page, "read_recipe_opportunity", lambda e, *_: pd.DataFrame()
        )
        at = run_app(page.render_tonight).run()
        assert "Toevoegen" in _texts(at)

    def test_an_unbuilt_mart_is_distinct_from_a_broken_database(
        self, wired, monkeypatch
    ):
        def _raise(_, *_unused):
            raise ProgrammingError("select", {}, Exception("no such relation"))

        monkeypatch.setattr(page, "read_recipe_opportunity", _raise)
        at = run_app(page.render_tonight).run()
        assert "nog niet gedraaid" in _texts(at)
        assert not at.error

    def test_an_unreachable_warehouse_says_so_in_the_portal_s_own_terms(
        self, wired, monkeypatch
    ):
        def _raise(_, *_unused):
            raise SQLAlchemyError("connection refused")

        monkeypatch.setattr(page, "read_recipe_opportunity", _raise)
        at = run_app(page.render_tonight).run()
        assert "Geen verbinding met de database" in _texts(at)


class TestHonestyAboutCoverage:
    def test_the_review_is_not_offered_when_there_is_nothing_to_review(self, wired):
        at = run_app(page.render_tonight).run()
        assert not [b for b in at.button if "koppelen" in b.label]

    def test_an_unknown_stock_is_never_shown_as_a_bound(self, wired, monkeypatch):
        """MIN skips NULLs, so all-unknown stock would otherwise read as plenty."""
        df = _opportunity()
        df.loc[0, "clearance_items_stock_unknown"] = 1
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert "Nog 2" not in _texts(at)


class TestCuration:
    def test_a_pool_recipe_can_be_rejected(self, wired, monkeypatch):
        calls = []
        monkeypatch.setattr(page, "reject_recipe", lambda e, a, r: calls.append(r))
        at = _open_card(run_app(page.render_tonight).run())
        buttons = [b for b in at.button if "Niet voor mij" in b.label]
        assert buttons, "a pool recipe must be dismissable"
        buttons[0].click().run()
        assert calls == [1]

    def test_a_hand_entered_recipe_offers_no_reject(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[0, "source_kind"] = "manual"
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
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
        monkeypatch.setattr(
            page, "read_rejected_recipes", lambda e, a, built_at="": rejected
        )
        monkeypatch.setattr(page, "reinstate_recipe", lambda e, a, r: calls.append(r))
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

    def test_an_exact_price_is_never_dressed_as_an_estimate_or_the_reverse(
        self, wired, monkeypatch
    ):
        at = run_app(page.render_tonight).run()
        assert "±" not in _texts(at), "a complete basket needs no hedge"

        df = _opportunity()
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        df.loc[0, "items_priced"] = 6
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert "±" in _texts(at), "an incomplete one must always carry it"

    def test_nothing_priced_at_all_says_so(self, wired, monkeypatch):
        df = _opportunity()
        for col in (
            "cost_today",
            "cost_ordinary",
            "partial_cost_today",
            "partial_cost_ordinary",
        ):
            df.loc[0, col] = None
        df.loc[0, "items_priced"] = 0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert "geen enkel ingrediënt" in _texts(at)

    def test_ingredients_are_folded_away_until_asked_for(self, wired):
        """The answer to "what shall I cook" is the recipe and its price. On a
        phone an open ingredient list pushes everything else off the screen."""
        at = _open_card(run_app(page.render_tonight).run())
        assert [b for b in at.button if "Ingrediënten" in b.label], (
            "the ingredient list must be reachable"
        )
        assert "AH Zuurkool" not in _texts(at), "and closed until it is asked for"

    def test_a_closed_list_registers_none_of_its_controls(self, wired):
        """This was an st.expander, and Streamlit runs an expander's body
        whether or not it is open. Six cards therefore registered a correction
        button per ingredient - around fifty controls streamed over a shop
        connection to show recipes nobody had opened."""
        at = run_app(page.render_tonight).run()
        assert not [b for b in at.button if "Klopt niet" in b.label]
        opened = _open_items(at)
        assert [b for b in opened.button if "Klopt niet" in b.label], (
            "and they appear once it is opened"
        )

    def test_the_ingredient_button_says_how_many(self, wired):
        at = _open_card(run_app(page.render_tonight).run())
        assert any("(9)" in b.label for b in at.button)

    def test_runners_up_carry_prices_and_ingredients_too(self, wired, monkeypatch):
        """ "How much is this one" is a question you ask of the alternatives."""
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        df.loc[1, "saving_total"] = 0.90
        df.loc[1, "exclusion_reason"] = None
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "€10.60" in body, "each card's own price, on its face"
        # Every card is compact now, so the ingredient list is behind "Meer" on
        # all of them rather than inline on one.
        assert not [b for b in at.button if "Ingrediënten" in b.label]
        opened = _open_card(at)
        assert [b for b in opened.button if "Ingrediënten" in b.label], (
            "and reachable once a card is opened"
        )


class TestTheIngredientList:
    """Opening "Ingrediënten (9)" and getting one line reads as broken. The
    list is what people open it for; the discount is an annotation on it."""

    def test_every_ingredient_is_listed_not_only_the_discounted_ones(self, wired):
        at = _open_items(run_app(page.render_tonight).run())
        body = _texts(at)
        assert "zuurkool" in body, "the discounted one"
        assert "aardappel" in body, "and the one that did not move"

    def test_each_line_names_the_product_it_is_matched_to(self, wired):
        """Most matches here were proposed by a machine. The only way to find a
        bad one is to be able to see it."""
        at = _open_items(run_app(page.render_tonight).run())
        body = _texts(at)
        assert "AH Zuurkool" in body
        assert "AH Aardappels" in body

    def test_every_matched_line_can_be_corrected(self, wired, monkeypatch):
        calls = []
        # The account is passed now: the correction applies to every account, so
        # the dialog must be able to establish who is asking.
        monkeypatch.setattr(
            page, "open_single", lambda e, c, n, a=None: calls.append((c, n, a))
        )
        at = _open_items(run_app(page.render_tonight).run())
        buttons = [b for b in at.button if "Klopt niet" in b.label]
        assert len(buttons) == 2, "one per ingredient, not one per discount"
        buttons[0].click().run()
        assert calls, "the correction dialog must open"
        assert calls[0][2] is not None, "and it must know who is asking"

    def test_an_unresolved_line_says_so_rather_than_vanishing(self, wired, monkeypatch):
        items = _items()
        items.loc[1, "is_unresolved"] = True
        items.loc[1, "price_today"] = None
        monkeypatch.setattr(
            page, "read_recipe_opportunity_items", lambda e, r, *_: items
        )
        at = _open_items(run_app(page.render_tonight).run())
        assert "nog geen product gekoppeld" in _texts(at)

    def test_a_recipe_without_ingredients_says_so(self, wired, monkeypatch):
        monkeypatch.setattr(
            page, "read_recipe_opportunity_items", lambda e, r, *_: pd.DataFrame()
        )
        at = _open_items(run_app(page.render_tonight).run())
        assert "geen ingrediënten bekend" in _texts(at)


class TestTheQueriesCarryWhatThePageReads:
    """The gap that let two bugs ship at once.

    The mart grew `partial_cost_today` and `concept_id`, the page read them, and
    the SELECT lists in between were never updated. Nothing failed: pandas
    returns None for a missing column, so the page reported "van geen enkel
    ingrediënt is de prijs bekend" over a fully priced recipe, and the "Klopt
    niet" button silently never rendered.

    AppTest fixtures build DataFrames by hand, so they cannot catch this. These
    compare the fixtures - which are the page's contract - against the real SQL.
    """

    @staticmethod
    def _selected(sql: str) -> str:
        return sql.lower()

    def test_the_opportunity_query_selects_every_column_the_page_uses(self):
        import inspect

        from bonuschef.portal import db

        sql = self._selected(inspect.getsource(db.read_recipe_opportunity))
        missing = [c for c in _opportunity().columns if c.lower() not in sql]
        assert not missing, f"the page reads these but the query omits them: {missing}"

    def test_the_items_query_selects_every_column_the_page_uses(self):
        import inspect

        from bonuschef.portal import db

        sql = self._selected(inspect.getsource(db.read_recipe_opportunity_items))
        missing = [c for c in _items().columns if c.lower() not in sql]
        assert not missing, f"the page reads these but the query omits them: {missing}"

    def test_a_price_is_shown_when_the_partial_columns_arrive(self, wired, monkeypatch):
        """The exact symptom reported: products listed with prices, and a
        heading claiming none were known."""
        df = _opportunity()
        df.loc[0, "cost_today"] = None
        df.loc[0, "cost_ordinary"] = None
        df.loc[0, "items_priced"] = 6
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "geen enkel ingrediënt" not in body
        assert "±€15.30" in body


class TestFeedbackAfterACorrection:
    """Confirming used to be silent. A silent save is indistinguishable from a
    click that never registered, which is how "I added the products but nothing
    happened" comes about."""

    def test_the_outcome_is_reported_on_the_page_not_in_the_dialog(self, wired):
        """st.rerun() closes a dialog, so anything rendered inside it after a
        confirmation is never seen."""
        from bonuschef.portal import review

        at = run_app(page.render_tonight)
        at.session_state[review.RESOLUTION_RESULT_KEY] = {
            "settled": 6,
            "none_exists": 1,
            "run_id": "abc12345",
        }
        at.run()
        body = _texts(at)
        assert "6 ingrediënt(en) gekoppeld" in body
        assert "geen passend product" in body

    def test_a_running_rebuild_is_reported_until_it_finishes(self, wired, monkeypatch):
        from dagster import DagsterRunStatus

        from bonuschef.portal import review

        monkeypatch.setattr(
            review, "get_run_status", lambda r: DagsterRunStatus.STARTED
        )
        at = run_app(page.render_tonight)
        at.session_state[review.REBUILD_RUN_KEY] = "abc12345"
        at.run()
        assert "herberekend" in _texts(at)

    def test_a_queued_rebuild_says_it_is_queued(self, wired, monkeypatch):
        """Runs are serialised instance-wide, so it may genuinely be waiting
        behind a clearance scrape. Calling that "busy" hides a real cause."""
        from dagster import DagsterRunStatus

        from bonuschef.portal import review

        monkeypatch.setattr(review, "get_run_status", lambda r: DagsterRunStatus.QUEUED)
        at = run_app(page.render_tonight)
        at.session_state[review.REBUILD_RUN_KEY] = "abc12345"
        at.run()
        assert "wachtrij" in _texts(at)

    def test_a_finished_rebuild_says_so_once_and_stops(self, wired, monkeypatch):
        from dagster import DagsterRunStatus

        from bonuschef.portal import review

        monkeypatch.setattr(
            review, "get_run_status", lambda r: DagsterRunStatus.SUCCESS
        )
        at = run_app(page.render_tonight)
        at.session_state[review.REBUILD_RUN_KEY] = "abc12345"
        at.run()
        assert "prijzen zijn bijgewerkt" in _texts(at)
        assert review.REBUILD_RUN_KEY not in at.session_state

    def test_a_failed_rebuild_does_not_imply_the_save_was_lost(
        self, wired, monkeypatch
    ):
        from dagster import DagsterRunStatus

        from bonuschef.portal import review

        monkeypatch.setattr(
            review, "get_run_status", lambda r: DagsterRunStatus.FAILURE
        )
        at = run_app(page.render_tonight)
        at.session_state[review.REBUILD_RUN_KEY] = "abc12345"
        at.run()
        assert "koppelingen zijn wel bewaard" in _texts(at)

    def test_losing_sight_of_the_run_is_not_an_error(self, wired, monkeypatch):
        """The write landed and the next scheduled rebuild picks it up."""
        from bonuschef.portal import review
        from bonuschef.portal.dagster_client import DagsterTriggerError

        def gone(run_id):
            raise DagsterTriggerError("no such run")

        monkeypatch.setattr(review, "get_run_status", gone)
        at = run_app(page.render_tonight)
        at.session_state[review.REBUILD_RUN_KEY] = "abc12345"
        at.run()
        assert not at.error


class TestPipelineHealth:
    """With no notification channel subscribed, this page is the only surface
    on which a broken pipeline can be noticed - and the failures that matter
    most emit no event to alert on anyway."""

    def test_nothing_is_shown_while_everything_succeeds(self, wired):
        """A health indicator that is always present is furniture."""
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "sync_problem" not in body
        assert "mogelijk niet bijgewerkt" not in body

    def test_the_credential_is_called_out_separately(self, wired, monkeypatch):
        """Every other failure recovers by re-running a job. This one needs a
        browser behind hCaptcha, and it has already expired twice."""
        health = _healthy(is_overdue=[False, True], overdue_h=[1.0, 50.0])
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: health)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "AH-inlog" in body
        assert "alleen met een browser" in body
        assert at.error, "the credential warrants an error, not a warning"

    def test_an_unreadable_run_table_does_not_break_the_page(self, wired, monkeypatch):
        """A Dagster upgrade that moves the schema must degrade this to what the
        page did before, not replace an answer with an error."""
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: pd.DataFrame())
        at = run_app(page.render_tonight).run()
        assert not at.error
        assert "Zuurkoolstamppot" in _texts(at)


class TestTheCacheFollowsTheData:
    """The portal cached its reads for fifteen minutes on a wall clock, which
    has nothing to do with when the data underneath changed.

    A rebuild triggered from Dagster - which is how the nightly runs - left the
    page showing the previous answer with no way to know. It showed corn for
    an ingredient whose link had already been corrected, and the only remedies
    were to wait or restart the container.
    """

    def test_the_readers_take_the_build_stamp(self):
        """It has to be an argument. Streamlit keys a cached function on its
        arguments, so computing the stamp inside would change nothing."""
        import inspect

        from bonuschef.portal import db

        for name in ("read_recipe_opportunity", "read_recipe_opportunity_items"):
            params = inspect.signature(getattr(db, name)).parameters
            assert "built_at" in params, f"{name} cannot be invalidated by a rebuild"

    def test_the_page_passes_it(self):
        source = Path(page.__file__).read_text() if hasattr(page, "__file__") else ""
        assert "read_marts_built_at(engine)" in source, (
            "the page reads the marts without asking when they were built"
        )

    def test_the_freshness_query_is_not_itself_cached_for_long(self):
        """Fifteen minutes here would reintroduce exactly the problem this
        exists to solve."""
        from bonuschef.portal import db

        assert db._FRESHNESS_TTL_S <= 60, (
            f"the staleness check is itself stale for {db._FRESHNESS_TTL_S}s"
        )
        assert db._FRESHNESS_TTL_S < db._CACHE_TTL_S

    def test_a_warehouse_without_the_column_degrades_rather_than_breaks(self):
        """A portal pointed at a warehouse built before this existed must fall
        back to the old behaviour, not fail to render."""
        from bonuschef.portal import db

        class _Engine:
            def begin(self):
                raise RuntimeError("column built_at does not exist")

        # The reader is cached on `_engine`, and an underscore-prefixed
        # argument is excluded from st.cache_data's key - so a value another
        # test put there would be returned whatever engine is passed here, and
        # this assertion would pass without the fallback existing at all. It
        # did pass that way, for as long as no test in the session could reach
        # a warehouse to populate the cache.
        db.read_marts_built_at.clear()
        assert db.read_marts_built_at(_Engine()) == "unknown"


class TestThePageSaysWhatItKnows:
    """Three figures the system computed and never showed."""

    def test_it_says_nothing_when_every_recipe_is_rankable(self, wired, monkeypatch):
        """A caption that fires on the ordinary case is noise."""
        df = _opportunity()
        df["exclusion_reason"] = [None, None]
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        assert "Niet meegerekend" not in _texts(run_app(page.render_tonight).run())

    def test_an_unknown_reason_is_skipped_rather_than_crashing(
        self, wired, monkeypatch
    ):
        """The mart could grow a fourth reason before the page learns its
        wording. That must not take the page down."""
        df = _opportunity()
        df["exclusion_reason"] = [None, "something_new"]
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert not at.exception


def test_a_saved_recipe_says_so_before_you_click(wired, monkeypatch):
    """is_kept has existed since keeping did and was called by nothing, so
    the page offered "Bewaren" on a recipe already in your collection and
    only admitted it once you pressed."""
    monkeypatch.setattr(page, "is_kept", lambda e, a, r: True)
    at = _open_card(run_app(page.render_tonight).run())
    rendered = _texts(at)
    assert "Bewaard" in rendered
    assert not any("Bewaren" in b.label for b in at.button)


class TestTheCard:
    """A recommendation is recognised before it is read.

    Every card was a paragraph with a 56-96 pixel thumbnail beside it, and the
    saving - the figure the application exists to produce - was bold body text
    on the lead and a caption on the runners-up, below a price rendered as a
    heading. The page read name, then price, then saving. That is the reverse
    of the order the decision is made in.
    """

    @staticmethod
    def _with_images(monkeypatch):
        """Two ranked recipes, both with a stored image."""
        df = _opportunity()
        df["image_url"] = [
            "https://static.ah.nl/static/recepten/img_1_220x162_JPG.jpg",
            "https://static.ah.nl/static/recepten/img_2_220x162_JPG.jpg",
        ]
        df.loc[1, "opportunity_rank"] = 2.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)

    def test_an_alternative_is_led_by_its_picture(self, wired, monkeypatch):
        """Recognising a dish by sight is what makes a row of cards scannable,
        and the alternatives are the cards being scanned."""
        self._with_images(monkeypatch)
        at = run_app(page.render_tonight).run()
        assert at.get("imgs"), "the alternatives must carry their pictures"
        assert [m for m in at.markdown if "Quiche met broccoli" in m.value]

    def test_every_card_carries_its_own_picture(self, wired, monkeypatch):
        """With the lead removed there is no card that is exempt: all of them
        are scanned, so all of them are recognised by sight."""
        self._with_images(monkeypatch)
        at = run_app(page.render_tonight).run()
        urls = " ".join(str(i.proto) for i in at.get("imgs"))
        assert "img_1_" in urls and "img_2_" in urls

    def test_the_image_is_the_larger_variant(self, wired, monkeypatch):
        """220x162 is what is stored and 440x324 is all AH publishes above it."""
        self._with_images(monkeypatch)
        at = run_app(page.render_tonight).run()
        urls = " ".join(str(i.proto) for i in at.get("imgs"))
        assert "440x324" in urls
        assert "220x162" not in urls

    def test_the_saving_is_the_largest_text_on_the_card(self, wired):
        """It is the reason to act, and it was previously smaller than the
        total price sitting above it."""
        at = run_app(page.render_tonight).run()
        saving = next(
            m.value for m in at.markdown if "goedkoper" in m.value and "#" in m.value
        )
        price = next(m.value for m in at.markdown if "€15.30" in m.value)
        # Fewer hashes is a larger heading.
        assert saving.count("#") < price.count("#"), (
            f"saving {saving!r} must outrank price {price!r}"
        )

    def test_a_recipe_without_a_picture_still_renders(self, wired):
        """The fixture carries no image_url, so this is the default case."""
        at = run_app(page.render_tonight).run()
        assert not at.exception
        assert "Zuurkoolstamppot" in _texts(at)

    def test_a_lower_bound_stays_a_lower_bound_when_promoted(self, wired, monkeypatch):
        """Making the saving the largest thing on the card must not turn an
        estimate into a figure. "minstens" is the whole honesty mechanism."""
        df = _opportunity()
        df.loc[0, "saving_is_lower_bound"] = True
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        assert "minstens" in _texts(at)


class TestStartingFromAnIngredient:
    """ "This is discounted, what do I cook with it" is the question asked in a
    shop, and it should cost no typing. Measured on the warehouse: 1,909
    distinct ingredient labels, of which 55 are discounted on a given day - so
    a blank box over the other 1,854 mostly answers "nothing on offer"."""

    def test_todays_discounted_ingredients_are_offered_as_choices(
        self, wired, monkeypatch
    ):
        monkeypatch.setattr(
            page,
            "read_discounted_ingredients",
            lambda e, *_, **__: pd.DataFrame(
                {
                    "item_label": ["kipfilet", "courgette"],
                    "recipes": [20, 5],
                    "offer_kind": ["bonus", "clearance"],
                }
            ),
        )
        at = run_app(page.render_tonight).run()
        # st.pills is a ButtonGroup to AppTest.
        pills = at.get("button_group")
        assert pills, "one tap, no keyboard"
        assert "kipfilet" in str(getattr(pills[0], "options", ""))

    def test_naming_an_ingredient_narrows_the_recipes(self, wired, monkeypatch):
        """Recipe 1 uses it, recipe 2 does not."""
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        monkeypatch.setattr(
            page, "read_recipes_using_ingredient", lambda e, s, term, *_: (1,)
        )
        at = run_app(page.render_tonight)
        at.run()
        at.text_input[0].set_value("zuurkool").run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body
        assert "Quiche met broccoli" not in body, "the one without it is gone"

    def test_an_ingredient_nothing_uses_answers_in_its_own_terms(
        self, wired, monkeypatch
    ):
        """An empty page is a dead end. The page already has this instinct."""
        monkeypatch.setattr(
            page, "read_recipes_using_ingredient", lambda e, s, term, *_: ()
        )
        at = run_app(page.render_tonight)
        at.run()
        at.text_input[0].set_value("zeewier").run()
        assert not at.exception
        assert "zeewier" in _texts(at), "say what was not found, by name"

    def test_asking_for_nothing_leaves_the_page_alone(self, wired):
        at = run_app(page.render_tonight).run()
        assert "Zuurkoolstamppot" in _texts(at)
        assert not at.exception


class TestTheProductComesBeforeThePipeline:
    """The portal spec already required this of every page, and this one put
    an unbounded loop of overdue-job warnings above the answer."""

    def test_a_dead_credential_still_comes_first(self, wired, monkeypatch):
        """It is the one pipeline failure that changes what you should buy:
        it means the prices may be wrong."""
        overdue = _healthy()
        overdue.loc[1, "is_overdue"] = True
        overdue.loc[1, "overdue_h"] = 40.0
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: overdue)
        at = run_app(page.render_tonight).run()
        assert any("AH-inlog" in e.value for e in at.error)


class TestAClosedCardCostsNothingExtra:
    """The expander this replaced executed its body whether or not it was
    open, so the page queried once per card and registered a correction button
    per ingredient to show detail nobody had asked for."""

    def test_a_closed_list_adds_no_query_of_its_own(self, wired, monkeypatch):
        """The badges naming the discounted ingredients read the same rows, and
        the reader is cached per recipe, so the closed list must add nothing on
        top rather than doubling it."""
        calls: list[int] = []

        def counting(engine, recipe_id, *rest):
            calls.append(int(recipe_id))
            return _items()

        monkeypatch.setattr(page, "read_recipe_opportunity_items", counting)
        at = run_app(page.render_tonight).run()
        assert not at.exception
        closed = len(calls)

        calls.clear()
        _open_items(at)
        assert len(calls) > closed, "opening it is what costs the extra read"

    def test_the_fragment_keeps_a_filter_off_the_rest_of_the_page(self):
        """A widget outside the fragment reruns the whole script, rebuilding
        the banners and the coverage block to answer "show me the chicken
        ones". The controls therefore live inside it with the list."""
        # Located by name through the AST, not by "the first @st.fragment":
        # there are two fragments now and that anchor broke the moment the
        # second one was added.
        import ast

        tree = ast.parse(Path(page.__file__).read_text())
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_render_ingredient_answer"
        )
        assert any("st.fragment" in ast.unparse(d) for d in fn.decorator_list), (
            "the filter and its list must rerun as one fragment"
        )
        body = ast.unparse(fn)
        assert "_ingredient_filter(engine)" in body
        assert "_render_answer(" in body


def test_opening_the_ingredient_list_does_not_rerun_the_page():
    """Reported from the shop: tapping "Ingrediënten" moved the page instead of
    staying where the thumb was.

    st.rerun() re-runs the whole script, the page grows by the length of the
    list, and the browser lands somewhere else. A fragment re-runs only that
    block and the toggle takes effect in the same run, so there is nothing to
    scroll. Opening a list is not a reason to move the page.
    """
    import ast

    tree = ast.parse(Path(page.__file__).read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_render_items_on_request"
    )
    assert any("st.fragment" in ast.unparse(d) for d in fn.decorator_list), (
        "it must rerun as a fragment rather than as the whole page"
    )
    calls = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert "st.rerun" not in calls, (
        "st.rerun re-runs the page and loses the reader's place"
    )


class TestAMarkdownThatIsNotCheaper:
    """Reported from the running app: a line badged "laatste kans · nog 2" with
    an unchanged price and no saving.

    The mart was right. AH's markdown on that spitskool was EUR 1.49 against
    the EUR 1.09 we track, so is_discounted is false and item_saving is 0 - it
    declined to call a dearer sticker a discount. The page announced urgency
    anyway, because the badge needed only a clearance offer and a known stock.
    Measured: 116 of 463 clearance lines, 103 of them with the sticker dearer
    than the tracked price.
    """

    @staticmethod
    def _dearer_markdown() -> pd.DataFrame:
        items = _items()
        items.loc[0, "item_label"] = "gesneden spitskool"
        items.loc[0, "product_name"] = "AH Fijngesneden spitskool"
        items.loc[0, "is_discounted"] = False
        items.loc[0, "item_saving"] = 0.0
        items.loc[0, "price_ordinary"] = 1.09
        items.loc[0, "price_today"] = 1.09
        items.loc[0, "offer_price"] = 1.49
        items.loc[0, "offer_kind"] = "clearance"
        items.loc[0, "stock"] = 2.0
        return items

    def _render(self, monkeypatch):
        monkeypatch.setattr(
            page,
            "read_recipe_opportunity_items",
            lambda e, r, *_: self._dearer_markdown(),
        )
        return _open_items(run_app(page.render_tonight).run())

    def test_no_urgency_badge_without_a_saving(self, wired, monkeypatch):
        """Urgency is a reason to act now. Without a saving there is none."""
        at = self._render(monkeypatch)
        badges = " ".join(m.value for m in at.markdown if "-badge[" in m.value)
        assert "laatste kans" not in badges, (
            "a markdown that is not cheaper must not be announced as urgent"
        )

    def test_the_discrepancy_is_stated_where_the_price_is(self, wired, monkeypatch):
        """The portal is required to communicate a retailer's advertised saving
        failing to survive comparison with observed prices, in the place where
        the saving is shown."""
        at = self._render(monkeypatch)
        body = _texts(at)
        assert "afgeprijsd" in body, body[:400]
        assert "1.49" in body, "say what the sticker asks"

    def test_a_bonus_that_is_not_cheaper_is_not_called_a_markdown(
        self, wired, monkeypatch
    ):
        """The two arise for different reasons. A clearance price beats its own
        product's shelf price by definition, so one that looks dearer means our
        reference is stale; a promotion has no such guarantee and simply may not
        beat the price we last saw. All sixteen live cases are the latter, and
        calling them "afgeprijsd" would be wrong twice over."""
        items = self._dearer_markdown()
        items.loc[0, "offer_kind"] = "bonus"
        items.loc[0, "stock"] = None
        items.loc[0, "price_ordinary"] = 4.15
        items.loc[0, "price_today"] = 4.15
        items.loc[0, "offer_price"] = 4.22
        monkeypatch.setattr(
            page, "read_recipe_opportunity_items", lambda e, r, *_: items
        )
        body = _texts(_open_items(run_app(page.render_tonight).run()))
        assert "in de bonus" in body, body[:400]
        assert "afgeprijsd" not in body, "a bonus is not a markdown"
        assert "4.22" in body and "4.15" in body

    def test_a_markdown_that_is_cheaper_still_gets_its_badge(self, wired):
        """The fixture's default clearance line is a real saving, and must not
        lose its urgency to this."""
        at = _open_items(run_app(page.render_tonight).run())
        badges = " ".join(m.value for m in at.markdown if "-badge[" in m.value)
        assert "laatste kans" in badges


class TestADismissalActuallyDismisses:
    """ "Niet voor mij" wrote a row and changed nothing on the page.

    The exclusion used to live in int_pool_recipes_available and was removed
    when accounts arrived, because it was global - one person dismissing hid the
    recipe from everybody. That model's note says it "moved to the portal, which
    knows who is asking", and a reader was written for the purpose. Nothing ever
    called it, so the recipe came back on the very next render while appearing
    in the "Niet voor mij" list - which the spec forbids in as many words.
    """

    def test_a_dismissed_recipe_leaves_the_ranking(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        monkeypatch.setattr(page, "read_rejected_recipe_ids", lambda e, a: {1})
        body = _texts(run_app(page.render_tonight).run())
        assert "Zuurkoolstamppot" not in body, "it must not return"
        assert "Quiche met broccoli" in body, "and the rest still ranks"

    def test_dismissing_everything_is_an_answer_not_a_blank(self, wired, monkeypatch):
        monkeypatch.setattr(page, "read_rejected_recipe_ids", lambda e, a: {1, 2})
        at = run_app(page.render_tonight).run()
        assert not at.exception
        assert at.info, "an empty ranking says so rather than rendering nothing"

    def test_the_filter_is_not_cached(self):
        """A cached answer would mean the button waits a quarter of an hour,
        which is the shape of the bug rather than a fix for it."""
        import ast

        tree = ast.parse(Path("src/bonuschef/portal/db.py").read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "read_rejected_recipe_ids"
        )
        decorators = " ".join(ast.unparse(d) for d in fn.decorator_list)
        assert "cache_data" not in decorators, decorators

    def test_it_hides_dismissals_only_not_what_was_saved(self):
        """read_hidden_recipe_ids also counts adopted recipes. Using it here
        would silently retire the "Bewaard" badge, which exists to say a
        recommendation is already in your collection - and a recipe you saved
        that is cheap today is still worth cooking tonight."""
        import ast

        tree = ast.parse(Path("src/bonuschef/portal/db.py").read_text())
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "read_rejected_recipe_ids"
        )
        sql = " ".join(
            n.value
            for n in ast.walk(fn)
            if isinstance(n, ast.Constant) and isinstance(n.value, str)
        )
        assert "ah_recipe_verdicts" in sql
        assert "account_recipes" not in sql, "adopted recipes are not dismissals"

    def test_an_unreadable_verdict_table_does_not_blank_the_page(
        self, wired, monkeypatch
    ):
        """The ranking is the answer; losing the dismissal list must not lose
        it."""

        def boom(e, a):
            raise ProgrammingError("x", {}, Exception("no table"))

        monkeypatch.setattr(page, "read_rejected_recipe_ids", boom)
        at = run_app(page.render_tonight).run()
        assert not at.exception
        assert "Zuurkoolstamppot" in _texts(at)


class TestTheCorrectionIsNotOfferedToEveryone:
    """It was offered on two shopper-facing pages with nothing gating it.

    A match is keyed on the retailer's concept so one confirmation serves every
    recipe using it - which is what makes the review worth doing, and what made
    an invited friend's guess able to change the price on everybody's card.
    """

    FRIEND = Account(
        account_id=2,
        username="sample",
        store_id=1876,
        is_operator=False,
        must_change_password=False,
    )

    def test_a_friend_is_not_offered_it(self, wired):
        at = _open_items(run_app(page.render_tonight, self.FRIEND).run())
        assert not [b for b in at.button if "Klopt niet" in b.label], (
            "a control that would be refused must not be shown"
        )

    def test_the_ingredient_list_is_still_useful_to_them(self, wired):
        """Removing the control must not remove the information. They still need
        to see which product the price rests on."""
        at = _open_items(run_app(page.render_tonight, self.FRIEND).run())
        body = _texts(at)
        assert "AH Zuurkool" in body
        assert "zuurkool" in body

    def test_an_operator_still_gets_it(self, wired):
        at = _open_items(run_app(page.render_tonight).run())
        assert [b for b in at.button if "Klopt niet" in b.label], (
            "SINGLE_USER is an operator and must keep the control"
        )


def test_the_fixture_patches_every_reader_the_page_calls():
    """Three times now, adding a reader has broken fifty tests at once.

    The page calls its readers by module-level name, so an unpatched one runs
    against the fixture's fake engine, raises AttributeError rather than a
    SQLAlchemy error, and takes the whole render down. The cascade is loud but
    says nothing about which reader is missing, so this names it.
    """
    import ast
    import inspect

    source = Path(page.__file__).read_text()
    tree = ast.parse(source)
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(".db")
        for alias in node.names
    }
    called = {
        ast.unparse(n.func)
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    readers = {n for n in imported & called if n.startswith("read_")}

    patched = set()
    for line in inspect.getsource(wired).splitlines():
        for reader in readers:
            if f'"{reader}"' in line:
                patched.add(reader)

    # These are reached only on paths the fixture deliberately does not take.
    allowed_unpatched = {"read_bonus_feed_loaded_at", "read_marts_built_at"}
    missing = readers - patched - allowed_unpatched
    assert not missing, (
        f"the wired fixture does not patch {sorted(missing)}, so those run "
        "against a fake engine and take every test in this file down at once"
    )


class TestTheAlternativesAreDifferentAnswers:
    """Six cards used to carry one fact.

    Every ranked recipe owes its saving to exactly one discounted ingredient, so
    saving_total is a property of the product: every recipe containing one
    particular bacon scores the same EUR 2.00, ties break on recipe_id, and the
    bacon runs contiguously. Of the top twenty for one shop, eleven were the
    same salmon and five were bacon.
    """

    @staticmethod
    def _ranked(n: int, drivers: list[str]) -> tuple[pd.DataFrame, dict[int, str]]:
        frame = pd.DataFrame(
            {"recipe_id": list(range(1, n + 1)), "opportunity_rank": range(1, n + 1)}
        )
        return frame, dict(enumerate(drivers, start=1))

    def test_one_recipe_per_ingredient_is_preferred(self):
        ranked, drivers = self._ranked(
            6, ["spek", "spek", "spek", "zalm", "zalm", "sinaasappel"]
        )
        shortlist, passed = page._choose_shortlist(ranked, drivers, want=3)
        chosen = [drivers[int(r)] for r in shortlist["recipe_id"]]
        assert chosen == ["spek", "zalm", "sinaasappel"], chosen
        assert passed == {"spek": 2, "zalm": 1}

    def test_the_lead_is_still_the_best_overall(self):
        """Choosing for variety must not demote the best answer."""
        ranked, drivers = self._ranked(4, ["spek", "spek", "zalm", "ui"])
        shortlist, _ = page._choose_shortlist(ranked, drivers, want=3)
        assert int(shortlist.iloc[0]["recipe_id"]) == 1

    def test_a_thin_day_still_fills_the_page(self):
        """Hard one-per-ingredient would show two cards while eight recipes are
        cheaper."""
        ranked, drivers = self._ranked(8, ["spek"] * 4 + ["zalm"] * 4)
        shortlist, _ = page._choose_shortlist(ranked, drivers, want=6)
        assert len(shortlist) == 6, "a thin day is not a two-card page"
        assert list(shortlist["recipe_id"]) == sorted(shortlist["recipe_id"]), (
            "and the fill keeps rank order"
        )

    def test_a_rich_day_is_not_a_nineteen_card_page(self):
        ranked, drivers = self._ranked(19, [f"ing{i}" for i in range(19)])
        shortlist, _ = page._choose_shortlist(ranked, drivers, want=6)
        assert len(shortlist) == 6

    def test_recipes_with_no_known_driver_still_rank(self):
        """If the driver query fails the page falls back to the ranking rather
        than to nothing, so an empty mapping must not empty the page."""
        ranked, _ = self._ranked(5, [""] * 5)
        shortlist, _ = page._choose_shortlist(ranked, {}, want=4)
        assert len(shortlist) == 4

    def test_the_page_shows_different_ingredients_end_to_end(self, wired, monkeypatch):
        df = _opportunity()
        df.loc[1, "opportunity_rank"] = 2.0
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: df)
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "Zuurkoolstamppot" in body and "Quiche met broccoli" in body


class TestThePageSaysWhatItIsNotShowing:
    def test_a_narrower_shortlist_is_disclosed(self, wired, monkeypatch):
        """A count of what was ranked, beside a shorter list, misrepresents the
        page's own selection - which the honesty requirement forbids."""
        base = _opportunity()
        many = pd.concat([base.iloc[[0]]] * 9, ignore_index=True)
        many["recipe_id"] = range(1, 10)
        many["opportunity_rank"] = range(1, 10)
        monkeypatch.setattr(page, "read_recipe_opportunity", lambda e, *_: many)
        # All nine driven by one ingredient, so three are passed over for six.
        monkeypatch.setattr(
            page,
            "read_driving_ingredients",
            lambda e, s, *_: pd.DataFrame(
                {
                    "recipe_id": list(range(1, 10)),
                    "item_label": ["zuurkool"] * 9,
                    "item_saving": [0.8] * 9,
                    "offer_kind": ["clearance"] * 9,
                }
            ),
        )
        at = run_app(page.render_tonight).run()
        captions = " ".join(c.value for c in at.caption)
        assert "één per aanbieding" in captions, captions
        assert [b for b in at.button if "Meer met zuurkool" in b.label], (
            "and the way to the rest is offered"
        )

    def test_the_drill_down_uses_the_control_that_exists(self):
        """The page had two ways to filter by ingredient once already. It is not
        getting a third."""
        import ast

        tree = ast.parse(Path(page.__file__).read_text())
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_render_shortlist_note"
        )
        body = ast.unparse(fn)
        assert "_SEARCH_KEY" in body, "it must drive the existing filter"


class TestTheIngredientControlIsTheTableOfContents:
    def test_the_pills_carry_their_counts(self, wired, monkeypatch):
        """The counts were already fetched and thrown away."""
        monkeypatch.setattr(
            page,
            "read_discounted_ingredients",
            lambda e, *_, **__: pd.DataFrame(
                {
                    "item_label": ["kipfilet", "courgette"],
                    "recipes": [20, 5],
                    "offer_kind": ["bonus", "clearance"],
                }
            ),
        )
        at = run_app(page.render_tonight).run()
        options = str(getattr(at.get("button_group")[0], "options", ""))
        assert "kipfilet (20)" in options, options

    def test_the_pill_maps_back_to_the_bare_label(self):
        """The label carries its count for reading; the filter needs the label.

        Tested on the mapping rather than through the widget: AppTest cannot
        drive a single-select st.pills - set_value iterates the string and
        select passes None - which is the limitation this repo already recorded
        for st.segmented_control.
        """
        frame = pd.DataFrame(
            {
                "item_label": ["kipfilet", "courgette"],
                "recipes": [20, 5],
                "offer_kind": ["bonus", "clearance"],
            }
        )
        mapping = page._pill_labels(frame)
        assert mapping["kipfilet (20)"] == "kipfilet"
        assert mapping["courgette (5)"] == "courgette"

    def test_an_ingredient_without_a_count_is_still_offered(self):
        frame = pd.DataFrame(
            {"item_label": ["kipfilet"], "recipes": [0], "offer_kind": ["bonus"]}
        )
        assert page._pill_labels(frame) == {"kipfilet": "kipfilet"}

    def test_a_name_ending_in_a_bracketed_number_is_not_mangled(self):
        """Which is why this is a mapping rather than a parse."""
        frame = pd.DataFrame(
            {"item_label": ["kaas 48+ (stuk)"], "recipes": [3], "offer_kind": ["bonus"]}
        )
        mapping = page._pill_labels(frame)
        assert mapping["kaas 48+ (stuk) (3)"] == "kaas 48+ (stuk)"

    def test_typing_is_behind_a_popover(self):
        """Its own reader argues one-handed typing in a shop is the interaction
        being removed, and then the page shipped the box as a peer of the pills,
        where it won by being lower and larger."""
        import ast

        tree = ast.parse(Path(page.__file__).read_text())
        fn = next(
            n
            for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef) and n.name == "_ingredient_filter"
        )
        calls = [ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)]
        assert "st.popover" in calls, calls


class TestThePricesAreOnTheCardFace:
    """A saving expressed only as a difference cannot be checked against a
    shelf, and checking it against the shelf is what somebody is doing while
    reading it. The recipe total cannot be checked either - nobody will ever see
    EUR 12,59 anywhere."""

    def test_the_driving_ingredient_shows_both_prices(self, wired):
        at = run_app(page.render_tonight).run()
        body = _texts(at)
        assert "0.79" in body, "what it costs now"
        assert "1.59" in body, "and what it ordinarily costs"

    def test_without_opening_the_ingredient_list(self, wired):
        """The one or two lines needed in the aisle were the hidden ones, while
        the nine not needed were what the tap revealed."""
        at = run_app(page.render_tonight).run()
        assert not [b for b in at.button if "Verbergen" in b.label], (
            "the list is still closed"
        )
        assert "0.79" in _texts(at), "and the prices are already there"

    def test_a_stale_reference_is_marked(self, wired, monkeypatch):
        """ordinary_price_age_days was selected by the reader all along and
        rendered nowhere. It is the difference between a trustworthy "was" price
        and a decorative one."""
        items = _items()
        items.loc[0, "ordinary_price_age_days"] = 9
        monkeypatch.setattr(
            page, "read_recipe_opportunity_items", lambda e, r, *_: items
        )
        body = _texts(run_app(page.render_tonight).run())
        assert "9 dagen geleden" in body, body[:300]

    def test_a_fresh_reference_is_not_remarked_on(self, wired):
        """The fixture's reference is three days old, which is a comparison
        rather than a caveat."""
        assert "dagen geleden" not in _texts(run_app(page.render_tonight).run())

    def test_no_extra_query_is_issued_for_them(self, wired, monkeypatch):
        """Both numbers were already on the row the saving came from. Showing
        them must not cost a read, which the spec forbids."""
        calls: list[int] = []

        def counting(engine, recipe_id, *rest):
            calls.append(int(recipe_id))
            return _items()

        monkeypatch.setattr(page, "read_recipe_opportunity_items", counting)
        run_app(page.render_tonight).run()
        assert len(calls) == len(set(calls)), (
            f"one read per recipe, not one per thing shown: {calls}"
        )


class TestTheConsoleIsNotOnTheShoppersPage:
    """It used to sit below the recipes for every account: job names, overdue
    hours, unresolved counts, flagged matches and a button into the matcher.

    The portal spec says internal diagnostics "MAY remain available, but SHALL
    NOT occupy the primary surfaces", and this is the primary surface for
    somebody in a shop - who can act on none of it, and for whom most of it is
    not even theirs to act on: a resolution applies to every account.
    """

    def test_job_names_are_not_on_it(self, wired, monkeypatch):
        overdue = _healthy()
        overdue.loc[0, "is_overdue"] = True
        overdue.loc[0, "overdue_h"] = 9.0
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: overdue)
        at = run_app(page.render_tonight).run()
        assert "markdowns_refresh" not in _texts(at), (
            "an overdue job name is an operator's business"
        )

    def test_the_matcher_is_not_offered_from_it(self, wired, monkeypatch):
        monkeypatch.setattr(page, "count_flagged_concepts", lambda e: 4)
        at = run_app(page.render_tonight).run()
        assert not [
            b
            for b in at.button
            if "Ingrediënten" in b.label and "koppel" in b.label.lower()
        ]
        assert "niet bij hoort" not in _texts(at)

    def test_but_a_dead_credential_still_is(self, wired, monkeypatch):
        """It is the one failure that changes what a shopper should buy: it means
        the prices may be wrong."""
        overdue = _healthy()
        overdue.loc[1, "is_overdue"] = True
        overdue.loc[1, "overdue_h"] = 40.0
        monkeypatch.setattr(page, "read_pipeline_health", lambda e: overdue)
        at = run_app(page.render_tonight).run()
        assert any("AH-inlog" in e.value for e in at.error)

    def test_and_the_answer_is_still_there(self, wired):
        assert "Zuurkoolstamppot" in _texts(run_app(page.render_tonight).run())
