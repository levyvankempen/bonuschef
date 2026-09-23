"""Two people, one catalogue, separate decisions.

Against real Postgres, because every claim here is about what a second row in
a table does to the first person's view, and a fake engine answers whatever it
is told to.

Before this, all three of these were global: adopting a recipe removed it from
everybody's suggestions, one "Niet voor mij" hid it from all of them, and
is_kept answered "has anybody adopted this" rather than "have you".
"""

import pytest
from sqlalchemy import text

from bonuschef.portal.db import (
    is_kept,
    read_hidden_recipe_ids,
    reinstate_recipe,
    reject_recipe,
)
from bonuschef.portal.schema import ensure_account_tables

pytestmark = pytest.mark.warehouse

ANNE, BRAM = 8001, 8002
RECIPE = 998001


@pytest.fixture
def two_people(warehouse):
    ensure_account_tables(warehouse)
    with warehouse.begin() as conn:
        for account_id in (ANNE, BRAM):
            conn.execute(
                text("DELETE FROM public.ah_recipe_verdicts WHERE account_id = :a"),
                {"a": account_id},
            )
            conn.execute(
                text("DELETE FROM public.account_recipes WHERE account_id = :a"),
                {"a": account_id},
            )
            conn.execute(
                text("DELETE FROM public.accounts WHERE account_id = :a"),
                {"a": account_id},
            )
            conn.execute(
                text("""
                    INSERT INTO public.accounts (account_id, username, store_id)
                    VALUES (:a, :u, 1876)
                """),
                {"a": account_id, "u": f"person_{account_id}"},
            )
    yield warehouse
    with warehouse.begin() as conn:
        for account_id in (ANNE, BRAM):
            conn.execute(
                text("DELETE FROM public.ah_recipe_verdicts WHERE account_id = :a"),
                {"a": account_id},
            )
            conn.execute(
                text("DELETE FROM public.account_recipes WHERE account_id = :a"),
                {"a": account_id},
            )
            conn.execute(
                text("DELETE FROM public.accounts WHERE account_id = :a"),
                {"a": account_id},
            )


def test_one_persons_rejection_does_not_hide_it_from_another(two_people):
    """The failure this change exists for. One "Niet voor mij" used to hide a
    recipe from everybody, permanently."""
    reject_recipe(two_people, ANNE, RECIPE)
    assert RECIPE in read_hidden_recipe_ids(two_people, ANNE)
    assert RECIPE not in read_hidden_recipe_ids(two_people, BRAM)


def test_two_people_can_reject_the_same_recipe(two_people):
    """The verdict table was keyed on recipe_id alone, so the second rejection
    overwrote the first rather than sitting beside it."""
    reject_recipe(two_people, ANNE, RECIPE)
    reject_recipe(two_people, BRAM, RECIPE)
    assert RECIPE in read_hidden_recipe_ids(two_people, ANNE)
    assert RECIPE in read_hidden_recipe_ids(two_people, BRAM)


def test_rejecting_twice_is_not_an_error(two_people):
    reject_recipe(two_people, ANNE, RECIPE)
    reject_recipe(two_people, ANNE, RECIPE)
    with two_people.begin() as conn:
        count = conn.execute(
            text(
                "SELECT count(*) FROM public.ah_recipe_verdicts "
                "WHERE account_id = :a AND recipe_id = :r"
            ),
            {"a": ANNE, "r": RECIPE},
        ).scalar()
    assert count == 1


def test_reinstating_affects_only_the_person_who_asked(two_people):
    reject_recipe(two_people, ANNE, RECIPE)
    reject_recipe(two_people, BRAM, RECIPE)
    reinstate_recipe(two_people, ANNE, RECIPE)
    assert RECIPE not in read_hidden_recipe_ids(two_people, ANNE)
    assert RECIPE in read_hidden_recipe_ids(two_people, BRAM), "not theirs to undo"


def test_a_saved_recipe_is_saved_by_one_person(two_people):
    """is_kept used to ask the catalogue, which answers "has anybody adopted
    this" - so a recipe a friend saved showed as already yours."""
    with two_people.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO public.account_recipes (account_id, recipe_id) "
                "VALUES (:a, :r)"
            ),
            {"a": ANNE, "r": RECIPE},
        )
    assert is_kept(two_people, ANNE, RECIPE) is True
    assert is_kept(two_people, BRAM, RECIPE) is False


def test_a_saved_recipe_stops_being_suggested_to_that_person_only(two_people):
    with two_people.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO public.account_recipes (account_id, recipe_id) "
                "VALUES (:a, :r)"
            ),
            {"a": ANNE, "r": RECIPE},
        )
    assert RECIPE in read_hidden_recipe_ids(two_people, ANNE)
    assert RECIPE not in read_hidden_recipe_ids(two_people, BRAM)
