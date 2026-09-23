"""AppTest smoke coverage for the recipes, analysis and add-recipe pages."""

from typing import Any

import pandas as pd

from bonuschef.portal import analysis_page, recipes_page
from bonuschef.portal import manual_recipe as recipe_builder

from tests.conftest import run_app


class TestRecipesPage:
    """The dashboard.

    The page it replaced rendered the same rows three times - a list, a
    duplicate bonus block over the same recipes, and a detail pane with a
    selectbox that made you re-find a recipe you were already looking at - so
    these tests are new rather than adapted.
    """

    SAVED = pd.DataFrame(
        {
            "recipe_id": [1, 2],
            "saved_at": pd.to_datetime(["2026-01-01", "2026-01-01"], utc=True),
            "last_made_at": pd.to_datetime([None, "2026-09-01"], utc=True),
            "notes": ["", ""],
        }
    )
    PRICED = pd.DataFrame(
        {
            "recipe_id": [1, 2],
            # Named so the two orders DIFFER: "Zalm" sorts last
            # alphabetically and first by longest-not-made. With names
            # that happened to agree, swapping the default sort for
            # alphabetical passed every test.
            "recipe_name": ["Zalm uit de oven", "Quiche"],
            "image_url": [None, None],
            "cost_today": [4.50, None],
            "cost_ordinary": [6.00, None],
            "partial_cost_today": [None, 7.25],
            "items_priced": [None, 5],
            "items_total": [None, 8],
            "items_discounted": [2, 0],
            "items_discounted_clearance": [1, 0],
            "items_unresolved": [0, 1],
            "clearance_scraped_at": pd.to_datetime(
                ["2026-01-01", "2026-01-01"], utc=True
            ),
            "saving_total": [1.5, 0.0],
            "saving_bonus_only": [1.0, 0.0],
            "cost_today_bonus_only": [5.0, None],
            "partial_cost_today_bonus_only": [None, 7.5],
            "cost_today_per_serving": [1.1, None],
            "cost_today_per_serving_bonus_only": [1.2, None],
            "opportunity_rank": [1, 2],
        }
    )

    def _wire(self, monkeypatch, *, saved=None, priced=None, fresh=True):
        monkeypatch.setattr(recipes_page, "get_engine", lambda: object())
        monkeypatch.setattr(
            recipes_page, "read_marts_built_at", lambda e: "2026-01-01T00:00:00"
        )
        monkeypatch.setattr(recipes_page, "store_for", lambda a: 1876)
        monkeypatch.setattr(
            recipes_page,
            "read_saved_recipes",
            lambda e, a, built_at="": self.SAVED if saved is None else saved,
        )
        monkeypatch.setattr(
            recipes_page,
            "read_recipe_opportunity",
            lambda e, s, built_at="": self.PRICED if priced is None else priced,
        )
        # Clearance current unless a test says otherwise, so the withdrawal is
        # exercised deliberately rather than by accident of the clock.
        monkeypatch.setattr(
            recipes_page.offers,
            "withdraw_stale_clearance",
            lambda df, now=None: (df, "" if fresh else "De winkelscan is oud."),
        )

    def test_a_saved_recipe_is_a_card(self, monkeypatch):
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        rendered = " ".join(m.value for m in at.markdown)
        assert "Zalm uit de oven" in rendered
        assert "Quiche" in rendered

    def test_an_exact_cost_is_shown_exactly(self, monkeypatch):
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        assert any("\u20ac4.50" in m.value for m in at.markdown)

    def test_an_incomplete_cost_says_so(self, monkeypatch):
        """A total over five of eight ingredients is not the price of the
        dish, and printing it bare invites somebody to trust it."""
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        rendered = " ".join(m.value for m in at.markdown)
        captions = " ".join(c.value for c in at.caption)
        assert "\u00b1\u20ac7.25" in rendered
        assert "5 van 8" in captions

    def test_a_recipe_never_made_says_so_rather_than_showing_a_date(self, monkeypatch):
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        assert any("Nog niet gemaakt" in c.value for c in at.caption)

    def test_what_made_it_cheap_is_on_the_card(self, monkeypatch):
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        rendered = " ".join(m.value for m in at.markdown)
        assert "bonus" in rendered and "laatste kans" in rendered

    def test_an_empty_collection_says_where_recipes_come_from(self, monkeypatch):
        """A dead end is the failure here: the old page said "Nog geen
        recepten" and stopped."""
        # Built from an empty dict rather than columns=[...]: the stub types
        # reject a plain list there, and an empty frame with the right columns
        # is what the reader actually returns.
        self._wire(
            monkeypatch,
            saved=pd.DataFrame(
                {"recipe_id": [], "saved_at": [], "last_made_at": [], "notes": []}
            ),
        )
        at = run_app(recipes_page.render_recipes).run()
        # The assertion this test was missing. It checked the copy and not
        # that the page rendered, so a StreamlitPageNotFoundError raised two
        # lines further down passed - on the one screen a new account sees
        # first.
        assert not at.exception, [e.value for e in at.exception]
        rendered = " ".join(m.value for m in at.markdown)
        assert "Vanavond" in rendered and "Toevoegen" in rendered

    def test_stale_clearance_is_said_rather_than_silently_counted(self, monkeypatch):
        self._wire(monkeypatch, fresh=False)
        at = run_app(recipes_page.render_recipes).run()
        assert any("winkelscan" in w.value for w in at.warning)

    def test_the_offer_filter_counts_before_it_is_applied(self, monkeypatch):
        """The count in the label is what stops "nothing on offer" reading as
        a broken page: you can see it would be empty without making it so."""
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        assert any("(1)" in t.label for t in at.toggle), [t.label for t in at.toggle]

    def test_a_never_scraped_shop_is_not_called_stale(self, monkeypatch):
        """Three states, not one. Somebody who has just chosen a shop needs to
        hear "not scanned yet" rather than be told their data is out of
        date."""
        priced = TestRecipesPage.PRICED.assign(clearance_scraped_at=pd.NaT)
        self._wire(monkeypatch, priced=priced)
        at = run_app(recipes_page.render_recipes).run()
        assert any("nog niet gescand" in i.value for i in at.info), [
            i.value for i in at.info
        ]

    def test_the_ingredient_list_is_not_fetched_until_it_is_opened(self, monkeypatch):
        """An expander renders its contents whether or not it is expanded, so
        a hundred saved recipes would each pull their rows on every rerun."""
        calls = []
        self._wire(monkeypatch)
        monkeypatch.setattr(
            recipes_page,
            "read_recipe_opportunity_items",
            lambda e, r, s, b="": calls.append(r) or pd.DataFrame(),
        )
        run_app(recipes_page.render_recipes).run()
        assert calls == [], "nothing should be fetched for a closed card"

    def test_the_default_sort_is_longest_not_made(self, monkeypatch):
        """A collection is usually asked "what have I not had for a while".
        Alphabetical is the order it had and answers nothing."""
        self._wire(monkeypatch)
        at = run_app(recipes_page.render_recipes).run()
        names = [
            m.value
            for m in at.markdown
            if "Zalm uit de oven" in m.value or "Quiche" in m.value
        ]
        assert names and "Zalm uit de oven" in names[0], names


class TestAnalysisPage:
    def test_no_changes_shows_hint(self, monkeypatch):
        monkeypatch.setattr(analysis_page, "get_engine", lambda: object())
        monkeypatch.setattr(
            analysis_page, "read_price_changes", lambda e: pd.DataFrame()
        )
        at = run_app(analysis_page.render_analysis).run()
        assert "prijswijzigingen" in at.info[0].value

    def test_bonus_price_check_metrics(self, monkeypatch):
        monkeypatch.setattr(analysis_page, "get_engine", lambda: object())
        changes = pd.DataFrame(
            {
                "product_link": ["1/a"],
                "product_name": ["A"],
                "prev_snapshot_timestamp": ["2025-01-06"],
                "snapshot_timestamp": ["2025-01-13"],
                "prev_price": [1.0],
                "new_price": [1.2],
                "price_change": [0.2],
                "pct_change": [20.0],
            }
        )
        monkeypatch.setattr(analysis_page, "read_price_changes", lambda e: changes)
        monkeypatch.setattr(
            "bonuschef.portal.db.read_product_prices",
            lambda e, names: pd.DataFrame(
                {
                    "product_name": ["A"],
                    "snapshot_timestamp": ["2025-01-13"],
                    "price": [1.2],
                }
            ),
        )
        comparison = pd.DataFrame(
            {
                "product_link": ["1/a", "2/b"],
                "product_name": ["A", "B"],
                "tracked_price": [1.0, 2.0],
                "ah_price": [1.5, 2.0],
                "bonus_price": [0.9, 1.5],
                "bonus_mechanism": ["x", "y"],
                "bonus_start_date": ["2025-01-06"] * 2,
                "bonus_end_date": ["2025-01-12"] * 2,
                "price_inflation": [0.5, 0.0],
                "real_savings": [0.1, 0.5],
                "advertised_savings": [0.6, 0.5],
                "is_inflated": [True, False],
            }
        )
        monkeypatch.setattr(
            analysis_page, "read_bonus_price_comparison", lambda e: comparison
        )
        at = run_app(analysis_page.render_analysis, default_timeout=10).run()
        assert not at.exception
        metrics = {m.label: m.value for m in at.metric}
        assert metrics["Bonusproducten gekoppeld"] == "2"
        assert metrics["Opgeblazen van-prijs"] == "1 (50%)"
        assert metrics["Gem. opslag"] == "€0.50"


class TestAddRecipePage:
    def test_no_products_warns(self, monkeypatch):
        monkeypatch.setattr(recipe_builder, "get_engine", lambda: object())
        monkeypatch.setattr(recipe_builder, "ensure_recipe_tables", lambda e: None)
        monkeypatch.setattr(
            recipe_builder, "ensure_product_images_table", lambda e: None
        )
        monkeypatch.setattr(recipe_builder, "list_products", lambda e: pd.DataFrame())
        at = run_app(recipe_builder.render_manual_entry).run()
        assert "geen producten" in at.warning[0].value

    def test_search_then_add_ingredient(self, monkeypatch):
        products = pd.DataFrame(
            {
                "product_link": ["1/melk", "2/kaas"],
                "product_url": ["https://ah.nl/1", "https://ah.nl/2"],
                "product_name": ["AH Halfvolle melk", "AH Jonge kaas"],
                "price": [1.09, 4.5],
                # Carried by dim_product now, so the page no longer fetches
                # every product image from ah.nl while rendering.
                "image_url": [None, None],
            }
        )
        monkeypatch.setattr(recipe_builder, "get_engine", lambda: object())
        monkeypatch.setattr(recipe_builder, "ensure_recipe_tables", lambda e: None)
        monkeypatch.setattr(
            recipe_builder, "ensure_product_images_table", lambda e: None
        )
        monkeypatch.setattr(recipe_builder, "list_products", lambda e: products)
        monkeypatch.setattr(recipe_builder, "_fetch_product_image", lambda url: None)

        at = run_app(recipe_builder.render_manual_entry, default_timeout=10)
        at.run()
        assert "voeg minstens één product toe" in at.info[0].value

        at.text_input[0].input("melk").run()
        assert list(at.dataframe[0].value["Product"]) == ["AH Halfvolle melk"]
        at.multiselect[0].select("AH Halfvolle melk")
        at.button[0].click().run()
        assert not at.exception
        assert at.session_state["recipe_ingredients"] == {"AH Halfvolle melk": 1}


class TestAddRecipeCatalogue:
    """Adopting a recipe from AH: three taps and one search term."""

    def _stubs(self, monkeypatch, **over):
        from bonuschef.portal import add_recipe_page as page
        from bonuschef.utils.ah_recipes import Ingredient, Recipe, RecipeHit, SearchPage

        recipe = Recipe(
            recipe_id=1199196,
            title="Zuurkoolstamppot",
            servings=4,
            ingredients=(
                Ingredient(4812, "zuurkool", 520, "g", "520 g zuurkool"),
                Ingredient(3200, "milde olijfolie", 1, "el", "1 el milde olijfolie"),
            ),
        )
        state: dict[str, Any] = {
            "page": page,
            "recipe": recipe,
            "search": SearchPage(
                total=20, hits=(RecipeHit(1199196, "Zuurkoolstamppot"),)
            ),
            "browse": SearchPage(
                total=24803, hits=(RecipeHit(1234, "Uit de Allerhande"),)
            ),
            "search_exc": None,
            "fetch_exc": None,
            "saved": [],
            "rebuilt": [],
            "adopted_already": False,
            "proposals": [
                {"concept_id": 4812, "product_link": "x", "product_name": "Zuurkool"}
            ],
            **over,
        }

        def search(q, size=8):
            if state["search_exc"]:
                raise state["search_exc"]
            return state["search"]

        def fetch(rid):
            if state["fetch_exc"]:
                raise state["fetch_exc"]
            return state["recipe"]

        monkeypatch.setattr(page, "get_engine", lambda: object())
        monkeypatch.setattr(page, "_ensure", lambda e: True)
        monkeypatch.setattr(page, "_search", search)
        # The page browses when nothing has been typed; without these the
        # default state would reach AH.
        monkeypatch.setattr(page, "_browse", lambda sort_by, season: state["browse"])
        monkeypatch.setattr(page, "_seasons", lambda: ["winter", "zomer"])
        monkeypatch.setattr(page, "fetch_recipe", fetch)
        monkeypatch.setattr(page, "is_adopted", lambda e, i: state["adopted_already"])
        monkeypatch.setattr(
            page, "save_adopted_recipe", lambda e, r: state["saved"].append(r.recipe_id)
        )
        monkeypatch.setattr(page, "propose_for", lambda e, c: state["proposals"])
        monkeypatch.setattr(page, "propose_products", lambda e, p: None)
        monkeypatch.setattr(
            page, "start_recipe_rebuild", lambda: state["rebuilt"].append(1) or True
        )
        monkeypatch.setattr(page, "render_manual_entry", lambda: None)
        return state

    def _search(self, at, term="zuurkool"):
        # By label, not by index: the browse controls sit alongside the form and
        # the positions shift whenever the default state changes.
        at.text_input[0].input(term)
        next(b for b in at.button if b.label == "Zoek").click().run()
        return at

    def test_results_are_cards_not_a_grid(self, monkeypatch):
        s = self._stubs(monkeypatch)
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        assert not at.exception
        assert not at.dataframe
        assert any("Zuurkoolstamppot" in m.value for m in at.markdown)

    def test_typing_does_not_call_the_catalogue(self, monkeypatch):
        """A form, not a live input: keystrokes must not hit a third party."""
        calls = []
        s = self._stubs(monkeypatch)
        monkeypatch.setattr(
            s["page"], "_search", lambda q, size=8: calls.append(q) or s["search"]
        )
        at = run_app(s["page"].render_add_recipe, default_timeout=10).run()
        at.text_input[0].input("zuur").run()
        assert calls == []

    def test_unreachable_is_distinct_from_nothing_found(self, monkeypatch):
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable

        s = self._stubs(monkeypatch, search_exc=AHRecipeUnavailable("down"))
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        assert "niet bereikbaar" in at.error[0].value
        assert not at.info

    def test_nothing_found_is_not_an_error(self, monkeypatch):
        from bonuschef.utils.ah_recipes import SearchPage

        s = self._stubs(monkeypatch, search=SearchPage(total=0, hits=()))
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        assert "Geen recepten gevonden" in at.info[0].value
        assert not at.error

    def test_ingredients_are_visible_before_committing(self, monkeypatch):
        s = self._stubs(monkeypatch)
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        next(b for b in at.button if b.label == "Bekijken").click().run()
        text = " ".join(m.value for m in at.markdown)
        assert "zuurkool" in text and "milde olijfolie" in text
        assert s["saved"] == [], "previewing must not adopt"

    def test_adopting_saves_and_starts_the_build_itself(self, monkeypatch):
        s = self._stubs(monkeypatch)
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        next(b for b in at.button if b.label == "Bekijken").click().run()
        next(
            b for b in at.button if b.label == "Voeg toe aan mijn recepten"
        ).click().run()
        assert s["saved"] == [1199196]
        assert s["rebuilt"] == [1], "the portal finishes its own work"
        assert not at.code, "and never asks for a terminal"

    def test_an_unmatched_ingredient_is_visible_not_silent(self, monkeypatch):
        s = self._stubs(monkeypatch, proposals=[])
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        next(b for b in at.button if b.label == "Bekijken").click().run()
        next(
            b for b in at.button if b.label == "Voeg toe aan mijn recepten"
        ).click().run()
        rendered = " ".join(m.value for m in at.markdown)
        assert "orange-badge" in rendered
        assert "2 zonder product" in rendered

    def test_adopting_twice_is_refused(self, monkeypatch):
        s = self._stubs(monkeypatch, adopted_already=True)
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        next(b for b in at.button if b.label == "Bekijken").click().run()
        assert "staat al" in at.info[0].value
        assert not [b for b in at.button if b.label == "Voeg toe aan mijn recepten"]

    def test_recipes_are_shown_before_anything_is_typed(self, monkeypatch):
        """The page used to open on an empty search box, which required knowing
        a dish name before the catalogue was any use."""
        s = self._stubs(monkeypatch)
        at = run_app(s["page"].render_add_recipe, default_timeout=10).run()
        assert not at.exception
        assert any("Uit de Allerhande" in m.value for m in at.markdown)
        assert [b for b in at.button if b.label == "Bekijken"]

    def test_the_ordering_can_be_changed(self, monkeypatch):
        asked = []
        s = self._stubs(monkeypatch)
        monkeypatch.setattr(
            s["page"],
            "_browse",
            lambda sort_by, season: asked.append((sort_by, season)) or s["browse"],
        )
        at = run_app(s["page"].render_add_recipe, default_timeout=10).run()
        assert asked[-1][0] == "NEWEST", "opens on what is new"
        at.radio[0].set_value("Populair").run()
        assert asked[-1][0] == "POPULAR"

    def test_the_season_values_come_from_the_catalogue(self, monkeypatch):
        """Hardcoding them would rot the day AH renames one, and offering a
        season with nothing in it is worse than no filter."""
        s = self._stubs(monkeypatch)
        monkeypatch.setattr(s["page"], "_seasons", lambda: ["herfst", "winter"])
        at = run_app(s["page"].render_add_recipe, default_timeout=10).run()
        assert "herfst" in at.selectbox[0].options
        assert "winter" in at.selectbox[0].options

    def test_searching_replaces_the_browsable_list(self, monkeypatch):
        s = self._stubs(monkeypatch)
        at = self._search(
            run_app(s["page"].render_add_recipe, default_timeout=10).run()
        )
        text = " ".join(m.value for m in at.markdown)
        assert "Zuurkoolstamppot" in text
        assert "Uit de Allerhande" not in text

    def test_an_unreachable_catalogue_on_arrival_says_so(self, monkeypatch):
        """Distinct from an empty catalogue, which would read as there being no
        recipes at all."""
        from bonuschef.utils.ah_recipes import AHRecipeUnavailable

        s = self._stubs(monkeypatch)

        def boom(sort_by, season):
            raise AHRecipeUnavailable("down")

        monkeypatch.setattr(s["page"], "_browse", boom)
        at = run_app(s["page"].render_add_recipe, default_timeout=10).run()
        assert "niet bereikbaar" in at.error[0].value
        assert not at.info
