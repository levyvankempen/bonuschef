"""Keeping a recipe the page recommended.

The page offered "Niet voor mij" and nothing else, while `_render_verdict_
controls`' own docstring read "Keep it, or never see it again". A person could
dismiss a recipe they disliked and had no way to hold on to one they liked -
and the pool is replaced wholesale every Monday, so a recipe absent from the
new enumeration is simply gone.

These run against a real database, because what is being asserted is that the
rows survive a refresh, and a stub cannot be refreshed.
"""

from __future__ import annotations

import os

import pytest
from sqlalchemy import create_engine, text

from bonuschef.portal.db import (
    ensure_catalogue_tables,
    ensure_verdict_table,
    is_kept,
    keep_recipe,
    reject_recipe,
)

pytestmark = pytest.mark.warehouse


# The account these tests act as. Any id works; what matters is that the same
# one is used to write and to read, because that is the whole point of the
# column.
ACCOUNT = 1


@pytest.fixture
def engine():
    url = (
        f"postgresql+psycopg2://{os.getenv('PG_USER', 'postgres')}:"
        f"{os.getenv('PG_PASSWORD', 'postgres')}@{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('PG_PORT', '5455')}/{os.getenv('PG_DB', 'postgres')}"
    )
    try:
        eng = create_engine(url, pool_pre_ping=True)
        with eng.begin() as conn:
            conn.execute(text("SELECT 1"))
    except Exception as exc:
        if os.getenv("CI"):
            raise AssertionError(f"CI provides a database: {exc}") from exc
        pytest.skip("no database")  # ty: ignore[too-many-positional-arguments]
    ensure_catalogue_tables(eng)
    ensure_verdict_table(eng)
    return eng


RID = 999900001


@pytest.fixture(autouse=True)
def _a_pool_recipe(engine):
    """One pool recipe with two ingredient lines, cleaned up afterwards."""
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM public.ah_recipes WHERE recipe_id = :r"), {"r": RID}
        )
        conn.execute(
            text('DELETE FROM public."ah__pool_recipes" WHERE recipe_id = :r'),
            {"r": RID},
        )
        conn.execute(
            text(
                'DELETE FROM public."ah__pool_recipe_ingredients" WHERE recipe_id = :r'
            ),
            {"r": RID},
        )
        conn.execute(
            text("""INSERT INTO public."ah__pool_recipes"
                    (recipe_id, title, servings, url, image_url, cook_time_min)
                    VALUES (:r, 'Bewaartest', 4, 'u', 'i', 30)"""),
            {"r": RID},
        )
        for line, concept in ((1, 111), (2, 222)):
            conn.execute(
                text("""INSERT INTO public."ah__pool_recipe_ingredients"
                        (recipe_id, line_no, concept_id, concept_name, quantity,
                         unit, raw_text)
                        VALUES (:r, :l, :c, 'iets', 1, '', '')"""),
                {"r": RID, "l": line, "c": concept},
            )
    yield
    with engine.begin() as conn:
        for table in (
            "public.ah_recipe_ingredients",
            "public.ah_recipes",
            'public."ah__pool_recipe_ingredients"',
            'public."ah__pool_recipes"',
            "public.ah_recipe_verdicts",
        ):
            conn.execute(text(f"DELETE FROM {table} WHERE recipe_id = :r"), {"r": RID})


def test_a_kept_recipe_survives_the_pool_being_replaced(engine):
    """The whole point. The pool is loaded with write_disposition=replace, so
    a recipe that falls out of the retailer's listing disappears - unless it
    has been kept."""
    assert keep_recipe(engine, ACCOUNT, RID) is True

    # Monday: the pool is replaced and this recipe is not in the new one.
    with engine.begin() as conn:
        conn.execute(text('DELETE FROM public."ah__pool_recipes"'))
        conn.execute(text('DELETE FROM public."ah__pool_recipe_ingredients"'))

    assert is_kept(engine, ACCOUNT, RID) is True
    with engine.begin() as conn:
        lines = conn.execute(
            text(
                "SELECT count(*) FROM public.ah_recipe_ingredients WHERE recipe_id = :r"
            ),
            {"r": RID},
        ).scalar()
    assert lines == 2, "the recipe survived but its ingredients did not"


def test_keeping_copies_the_ingredients_not_only_the_header(engine):
    """A recipe with no ingredients costs nothing and ranks nowhere - it would
    be kept in name only."""
    keep_recipe(engine, ACCOUNT, RID)
    with engine.begin() as conn:
        rows = (
            conn.execute(
                text(
                    "SELECT concept_id FROM public.ah_recipe_ingredients "
                    "WHERE recipe_id = :r ORDER BY line_no"
                ),
                {"r": RID},
            )
            .scalars()
            .all()
        )
    assert rows == [111, 222]


def test_keeping_twice_is_not_an_error(engine):
    """A second click must not raise, and must not duplicate the lines."""
    assert keep_recipe(engine, ACCOUNT, RID) is True
    assert keep_recipe(engine, ACCOUNT, RID) is False
    with engine.begin() as conn:
        lines = conn.execute(
            text(
                "SELECT count(*) FROM public.ah_recipe_ingredients WHERE recipe_id = :r"
            ),
            {"r": RID},
        ).scalar()
    assert lines == 2


def test_keeping_clears_an_earlier_rejection(engine):
    """Otherwise the recipe is adopted and immediately hidden by a verdict
    nobody remembers leaving."""
    reject_recipe(engine, ACCOUNT, RID)
    keep_recipe(engine, ACCOUNT, RID)
    with engine.begin() as conn:
        verdict = conn.execute(
            text("SELECT verdict FROM public.ah_recipe_verdicts WHERE recipe_id = :r"),
            {"r": RID},
        ).first()
    assert verdict is None


def test_keeping_a_recipe_the_pool_does_not_have_is_refused(engine):
    assert keep_recipe(engine, ACCOUNT, 999999999) is False
