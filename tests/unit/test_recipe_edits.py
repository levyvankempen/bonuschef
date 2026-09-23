"""Editing a saved recipe.

The overlay is deliberately narrow: only the multiplier changes. Which
product, which offer, whether a clearance unit was already claimed - all of
that stays in dbt where it is tested, because recomputing it in Python is
what made two marts disagree about one offer before.
"""

from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import text

from bonuschef.portal import recipes_page
from bonuschef.portal.db import read_recipe_lines_override, save_recipe_line_overrides
from bonuschef.portal.schema import ensure_account_tables

PAGE = Path("src/bonuschef/portal/recipes_page.py")


def _uncached(fn):
    """Call a cached reader directly.

    st.cache_data wraps differently depending on whether a Streamlit runtime
    is running, so `.func` is not always there. Everything else in this repo
    that bypasses the cache uses getattr with a fallback for the same reason.
    """
    return getattr(fn, "func", fn)


ITEMS = pd.DataFrame(
    {
        "item_key": ["c:1", "c:2"],
        "item_label": ["ui", "boter"],
        "price_today": [2.00, 3.00],
        "item_saving": [0.50, 0.00],
        "concept_id": [1, 2],
    }
)


# --- the overlay ------------------------------------------------------------


def test_no_edits_leaves_every_line_alone():
    out = recipes_page._apply_overrides(ITEMS, pd.DataFrame())
    assert list(out["price_today"]) == [2.00, 3.00]
    assert not out["hidden"].any()


def test_a_factor_scales_the_line():
    override = pd.DataFrame({"item_key": ["c:1"], "factor": [0.5], "hidden": [False]})
    out = recipes_page._apply_overrides(ITEMS, override)
    assert list(out["price_today"]) == [1.00, 3.00]


def test_a_hidden_line_is_gone():
    override = pd.DataFrame({"item_key": ["c:2"], "factor": [1.0], "hidden": [True]})
    out = recipes_page._apply_overrides(ITEMS, override)
    assert list(out["item_label"]) == ["ui"]


def test_the_saving_is_scaled_with_the_price():
    """Halving an ingredient halves what it saves. Leaving the saving alone
    would make the card claim a discount on an amount nobody is buying."""
    override = pd.DataFrame({"item_key": ["c:1"], "factor": [0.5], "hidden": [False]})
    out = recipes_page._apply_overrides(ITEMS, override)
    assert out.loc[out["item_key"] == "c:1", "item_saving"].iloc[0] == 0.25


def test_the_overlay_does_not_reprice_anything():
    """A source check. The hard part - which product, which offer, the stock
    claim - is tested in dbt, and reimplementing it here is what made two
    marts give two answers for one offer."""
    body = PAGE.read_text()
    overlay = body[
        body.index("def _apply_overrides") : body.index("def _render_edit_result")
    ]
    for forbidden in ("LEAST", "offer_price", "price_ordinary", "stock"):
        assert forbidden not in overlay, overlay


# --- the dialog -------------------------------------------------------------


def test_the_dialog_is_opened_from_session_state():
    """A full-script rerun re-evaluates `if st.button(...)` as False, and the
    dialog vanishes with whatever was typed in it."""
    body = PAGE.read_text()
    assert "if st.session_state.get(_EDIT_KEY):" in body
    opener = body[body.index('if st.button(\n                "Bewerken"') :][:400]
    assert "_EDIT_KEY" in opener and "st.rerun()" in opener


def test_the_outcome_is_reported_on_the_page_not_in_the_dialog():
    """st.rerun() closes a dialog, so a message rendered inside one is never
    seen - which review.py already records having learned."""
    body = PAGE.read_text()
    assert body.index("_render_edit_result()") < body.index("def _open_edit")
    result = body[body.index("def _render_edit_result") : body.index("def _open_edit")]
    assert "st.success" in result


# --- storage, against real Postgres -----------------------------------------


@pytest.mark.warehouse
class TestEditsAreStoredPerAccount:
    ANNE, BRAM, RECIPE = 7101, 7102, 991001

    @pytest.fixture
    def two(self, warehouse):
        ensure_account_tables(warehouse)
        with warehouse.begin() as conn:
            for account_id in (self.ANNE, self.BRAM):
                conn.execute(
                    text("DELETE FROM public.accounts WHERE account_id = :a"),
                    {"a": account_id},
                )
                conn.execute(
                    text(
                        "INSERT INTO public.accounts (account_id, username) "
                        "VALUES (:a, :u)"
                    ),
                    {"a": account_id, "u": f"edits_{account_id}"},
                )
        yield warehouse
        with warehouse.begin() as conn:
            for account_id in (self.ANNE, self.BRAM):
                conn.execute(
                    text("DELETE FROM public.accounts WHERE account_id = :a"),
                    {"a": account_id},
                )

    def test_one_persons_edit_is_invisible_to_another(self, two):
        save_recipe_line_overrides(two, self.ANNE, self.RECIPE, {"c:1": (0.5, False)})
        mine = _uncached(read_recipe_lines_override)(two, self.ANNE, self.RECIPE)
        theirs = _uncached(read_recipe_lines_override)(two, self.BRAM, self.RECIPE)
        assert list(mine["item_key"]) == ["c:1"]
        assert theirs.empty

    def test_saving_replaces_rather_than_merges(self, two):
        """The form shows every line, so what it submits is the whole answer.
        A merge would leave a line somebody just reset still overridden."""
        save_recipe_line_overrides(
            two, self.ANNE, self.RECIPE, {"c:1": (0.5, False), "c:2": (2.0, False)}
        )
        save_recipe_line_overrides(two, self.ANNE, self.RECIPE, {"c:1": (0.5, False)})
        stored = _uncached(read_recipe_lines_override)(two, self.ANNE, self.RECIPE)
        assert list(stored["item_key"]) == ["c:1"]

    def test_a_line_back_to_normal_is_not_stored(self, two):
        """Keeping it would make "edited" true for a recipe nobody changed."""
        save_recipe_line_overrides(
            two, self.ANNE, self.RECIPE, {"c:1": (1.0, False), "c:2": (1.0, False)}
        )
        assert _uncached(read_recipe_lines_override)(two, self.ANNE, self.RECIPE).empty

    def test_deleting_an_account_takes_its_edits(self, two):
        save_recipe_line_overrides(two, self.ANNE, self.RECIPE, {"c:1": (0.5, False)})
        with two.begin() as conn:
            conn.execute(
                text("DELETE FROM public.accounts WHERE account_id = :a"),
                {"a": self.ANNE},
            )
            left = conn.execute(
                text(
                    "SELECT count(*) FROM public.account_recipe_lines "
                    "WHERE account_id = :a"
                ),
                {"a": self.ANNE},
            ).scalar()
        assert left == 0
