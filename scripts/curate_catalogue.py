"""Adopt named Allerhande recipes and withdraw ones no longer wanted.

The catalogue held exactly one recipe, which is why "Mijn recepten" reads as
empty rather than as a collection. Adoption is a portal action, so doing this
by hand means clicking through a search for a recipe whose id is already
known; this takes the ids directly.

Idempotent: adopting a recipe already held is a no-op, and withdrawing one
that is already gone is not an error.

    uv run python scripts/curate_catalogue.py --dry-run
    uv run python scripts/curate_catalogue.py
"""

from __future__ import annotations

import argparse
import sys

from sqlalchemy import create_engine, text

from bonuschef.config import DatabaseConfig
from bonuschef.portal.db import save_adopted_recipe
from bonuschef.utils.ah_recipes import AHRecipeUnavailable, fetch_recipe

# https://www.ah.nl/allerhande/recept/R-R1193780/...
ADOPT = {
    1193780: "quiche met broccoli en gerookte zalm",
    1193969: "taco's met kibbeling, rodekool en aiolidressing",
}
WITHDRAW = {1199196: "zuurkoolstamppot met vegan kipbraadworst"}


def _withdraw(engine, recipe_id: int) -> bool:
    """Remove a recipe and the lines that hang off it.

    Ingredient concepts are deliberately left alone: they are shared, and a
    concept resolved once should stay resolved for whatever adopts it next.
    """
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM public.ah_recipe_ingredients WHERE recipe_id = :r"),
            {"r": recipe_id},
        )
        result = conn.execute(
            text("DELETE FROM public.ah_recipes WHERE recipe_id = :r"),
            {"r": recipe_id},
        )
        return bool(result.rowcount)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    engine = create_engine(DatabaseConfig.from_env().url)

    for recipe_id, name in ADOPT.items():
        if args.dry_run:
            print(f"would adopt   {recipe_id}  {name}")
            continue
        try:
            recipe = fetch_recipe(recipe_id)
        except AHRecipeUnavailable as exc:
            print(f"FAILED  {recipe_id}  {name}: {str(exc)[:120]}", file=sys.stderr)
            return 1
        added = save_adopted_recipe(engine, recipe)
        print(
            f"{'adopted ' if added else 'already held'}  {recipe_id}  "
            f"{recipe.title}  ({len(recipe.ingredients)} ingredients)"
        )

    for recipe_id, name in WITHDRAW.items():
        if args.dry_run:
            print(f"would withdraw {recipe_id}  {name}")
            continue
        gone = _withdraw(engine, recipe_id)
        print(f"{'withdrawn' if gone else 'not held'}  {recipe_id}  {name}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
