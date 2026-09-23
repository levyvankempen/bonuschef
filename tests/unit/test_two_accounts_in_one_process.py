"""One Streamlit process, two people.

st.cache_data is shared across every browser session hitting the process, so
a reader whose key omits the account or the store serves the first arrival's
data to everybody - and it looks right, which is what makes it dangerous.

These tests run the real cached readers against real Postgres, twice, with
different stores, and check the answers differ.
"""

import pytest
from sqlalchemy import text

from bonuschef.portal.db import (
    read_hidden_recipe_ids,
    read_last_scrape_time,
    read_store_clearance,
    read_store_directory,
    store_for,
)
from bonuschef.portal.schema import ensure_account_tables

pytestmark = pytest.mark.warehouse

HERE, THERE = 1876, 1661


@pytest.fixture
def two_shops(warehouse):
    ensure_account_tables(warehouse)
    with warehouse.begin() as conn:
        for store_id, name in (
            (HERE, "Eindhoven Torenallee"),
            (THERE, "Eindhoven Kamperfoelielaan"),
        ):
            conn.execute(
                text("""
                    INSERT INTO public.ah_stores (store_id, name) VALUES (:i, :n)
                    ON CONFLICT (store_id) DO UPDATE SET name = EXCLUDED.name
                """),
                {"i": store_id, "n": name},
            )
    return warehouse


def _call(fn, *args):
    """Through the cache decorator's wrapped function.

    `.func` steps around Streamlit's cache; calling it twice with different
    arguments is exactly what a second person in the same process does, and
    the point is that the argument reaches the query rather than only the key.
    """
    return getattr(fn, "func", fn)(*args)


def test_two_stores_get_different_clearance(two_shops):
    here = _call(read_store_clearance, two_shops, HERE)
    there = _call(read_store_clearance, two_shops, THERE)
    if here.empty and there.empty:
        pytest.skip("neither store has clearance in this warehouse")
    assert not here.equals(there), (
        "two shops returned identical clearance, which means the store never "
        "reached the query"
    )


def test_freshness_is_per_store(two_shops):
    """A MAX over the whole table is a lie the moment there are two: a store
    nobody has scraped inherits the freshness of one scraped this morning, and
    the page then says clearance is current when it is not."""
    with two_shops.begin() as conn:
        conn.execute(
            text("DELETE FROM public.ah__store_markdowns WHERE store_id = :s"),
            {"s": 999997},
        )
    never = _call(read_last_scrape_time, two_shops, 999997)
    assert never is None, "a store nobody has scraped has no scrape time"


def test_the_store_directory_is_shared_on_purpose(two_shops):
    """The one reader that SHOULD ignore who is asking: it is the list you
    pick from, not a thing that depends on you."""
    import inspect

    params = inspect.signature(
        getattr(read_store_directory, "func", read_store_directory)
    ).parameters
    assert "store_id" not in params
    assert "account_id" not in params


def test_two_people_hide_different_recipes(two_shops):
    """The account has to reach the query, not merely the cache key."""
    ensure_account_tables(two_shops)
    with two_shops.begin() as conn:
        conn.execute(
            text(
                "DELETE FROM public.ah_recipe_verdicts WHERE account_id IN (9001, 9002)"
            )
        )
        conn.execute(
            text(
                "INSERT INTO public.ah_recipe_verdicts (account_id, recipe_id, verdict) "
                "VALUES (9001, 771, 'rejected')"
            )
        )
    try:
        assert 771 in read_hidden_recipe_ids(two_shops, 9001)
        assert 771 not in read_hidden_recipe_ids(two_shops, 9002)
    finally:
        with two_shops.begin() as conn:
            conn.execute(
                text(
                    "DELETE FROM public.ah_recipe_verdicts WHERE account_id IN (9001, 9002)"
                )
            )


def test_an_account_without_a_shop_falls_back_rather_than_guessing(two_shops):
    """The fallback exists for the wall-down case. A signed-in person is asked
    for a shop before they are let past, so this is not a way to guess on
    somebody's behalf."""
    from types import SimpleNamespace

    assert store_for(SimpleNamespace(store_id=THERE)) == THERE
    assert store_for(SimpleNamespace(store_id=None)) == store_for(
        SimpleNamespace(store_id=0)
    )
