"""AppTest smoke coverage for the recipes, analysis and add-recipe pages."""

from typing import Any

import pandas as pd

from bonuschef.portal import analysis_page, recipes_page
from bonuschef.portal import manual_recipe as recipe_builder

from tests.conftest import run_app


class TestRecipesPage:
    def _wire(self, monkeypatch, summary):
        monkeypatch.setattr(recipes_page, "get_engine", lambda: object())
        monkeypatch.setattr(recipes_page, "read_recipe_summary", lambda e: summary)
        monkeypatch.setattr(
            recipes_page,
            "read_recipe_bonus_summary",
            lambda e: pd.DataFrame(
                {
                    "recipe_id": [1],
                    "recipe_name": ["Pasta"],
                    "bonus_count": [1],
                    "total_ingredients": [2],
                    "total_real_savings": [0.5],
                    "total_advertised_savings": [1.0],
                }
            ),
        )
        monkeypatch.setattr(
            recipes_page,
            "read_recipe_breakdown_bonus",
            lambda e, rid: pd.DataFrame(
                {
                    "recipe_id": [1, 1],
                    "recipe_name": ["Pasta", "Pasta"],
                    "product_name": ["Pasta", "Saus"],
                    "product_link": ["1/pasta", "2/saus"],
                    "quantity": [1, 1],
                    "price": [1.0, 2.0],
                    "item_cost": [1.0, 2.0],
                    "cost_pct": [33.3, 66.7],
                    "is_on_bonus": [False, True],
                    "bonus_mechanism": [None, "25% korting"],
                    "price_before_bonus": [None, 2.5],
                    "bonus_price": [None, 1.5],
                    "advertised_savings": [0.0, 1.0],
                    "real_savings": [0.0, 0.5],
                    "product_url": ["https://ah.nl/1", "https://ah.nl/2"],
                    "image_url": [None, None],
                }
            ),
        )

    def test_empty_summary_shows_hint(self, monkeypatch):
        self._wire(monkeypatch, pd.DataFrame())
        at = run_app(recipes_page.render_recipes).run()
        assert "Nog geen recepten" in at.info[0].value

    def test_full_page_renders(self, monkeypatch):
        summary = pd.DataFrame(
            {
                "recipe_id": [1],
                "recipe_name": ["Pasta"],
                "servings": [4],
                "total_cost": [3.0],
                "cost_per_serving": [0.75],
            }
        )
        self._wire(monkeypatch, summary)
        at = run_app(recipes_page.render_recipes, default_timeout=10).run()
        assert not at.exception
        # "Recipe Cost History" is gone: it plotted weekly totals for two
        # recipes, which changed no decision.
        assert [s.value for s in at.subheader] == [
            "Mijn recepten",
            "Deze week in de bonus",
            "Recept",
        ]
        assert at.selectbox[0].value == "Pasta"
        assert "bespaart" in at.success[0].value
        # The bonus marker is a badge now, which renders into the markdown
        # stream as :green-badge[...].
        assert any("green-badge" in m.value for m in at.markdown)

    def test_db_error_is_shown(self, monkeypatch):
        def boom():
            raise RuntimeError("no db")

        monkeypatch.setattr(recipes_page, "get_engine", boom)
        at = run_app(recipes_page.render_recipes).run()
        assert "Geen verbinding met de database" in at.error[0].value


class TestAnalysisPage:
    def test_no_changes_shows_hint(self, monkeypatch):
        monkeypatch.setattr(analysis_page, "get_engine", lambda: object())
        monkeypatch.setattr(
            analysis_page, "read_price_changes", lambda e: pd.DataFrame()
        )
        at = run_app(analysis_page.render_analysis).run()
        assert "No price changes" in at.info[0].value

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
        assert metrics["Bonus products matched"] == "2"
        assert metrics["Inflated pricing"] == "1 (50%)"
        assert metrics["Avg. inflation"] == "€0.50"


class TestAddRecipePage:
    def test_no_products_warns(self, monkeypatch):
        monkeypatch.setattr(recipe_builder, "get_engine", lambda: object())
        monkeypatch.setattr(recipe_builder, "ensure_recipe_tables", lambda e: None)
        monkeypatch.setattr(
            recipe_builder, "ensure_product_images_table", lambda e: None
        )
        monkeypatch.setattr(recipe_builder, "list_products", lambda e: pd.DataFrame())
        at = run_app(recipe_builder.render_manual_entry).run()
        assert "No products found" in at.warning[0].value

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
        assert "Search and add at least one product" in at.info[0].value

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
        at.text_input[0].input(term)
        at.button[0].click().run()
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
