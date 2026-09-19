"""Does this product plausibly satisfy this ingredient?

Resolution has until now compared names. A name says what a product is
called; the retailer's taxonomy says what it *is*, and the two disagree often
enough to matter:

    verse dille  ->  Verstegen Dille   dried, in a jar, in the spice aisle
    wortel       ->  AH Vormservet wortel   a carrot-printed paper napkin

Everything here is a pure function over a product's classification and an
ingredient's name. No network, no database: this runs inside the resolution
asset, and it must be testable without either.

The rules are deliberately timid. Each one abstains when it does not know,
because a wrong rejection removes the only candidate for an ingredient and
turns a visibly wrong price into a silently missing one, which is worse.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from bonuschef.utils.ah_recipes import (
    DEPARTMENT_FRESH,
    DEPARTMENT_FROZEN,
    DEPARTMENT_NON_FOOD,
)

# Words by which a recipe states the form it wants. Only these two directions
# are checked, because they are the two the departments actually distinguish.
_WANTS_FRESH = ("verse", "vers", "koelverse", "koelvers", "rauwe")
_WANTS_AMBIENT = ("gedroogde", "gedroogd", "gemalen", "gepoederd", "blik", "pot")

# Fresh things are sold frozen too, and a recipe asking for fresh spinach is
# not wronged by frozen spinach the way it is by a jar of dried dill.
_FRESH_ENOUGH = frozenset({DEPARTMENT_FRESH, DEPARTMENT_FROZEN})


@dataclass(frozen=True)
class Judgement:
    """Why a candidate was kept or rejected, in words a person can read."""

    accepted: bool
    reason: str = ""


def normalise(text: str | None) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace."""
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _words(text: str) -> set[str]:
    return set(normalise(text).split())


def wants_fresh(ingredient_name: str) -> bool:
    return bool(_words(ingredient_name) & set(_WANTS_FRESH))


def wants_ambient(ingredient_name: str) -> bool:
    return bool(_words(ingredient_name) & set(_WANTS_AMBIENT))


def judge(ingredient_name: str, department: str) -> Judgement:
    """Whether a product from this department can satisfy this ingredient.

    Abstains - accepts - whenever the department is unknown or the ingredient
    states no form. Silence is not a requirement: "dille" unqualified should
    still match dried dill, because the recipe did not ask for otherwise.
    """
    dept = (department or "").strip()
    if not dept:
        return Judgement(True, "not classified")

    if dept == DEPARTMENT_NON_FOOD:
        return Judgement(False, "non-food product cannot satisfy a food ingredient")

    if wants_fresh(ingredient_name) and dept not in _FRESH_ENOUGH:
        return Judgement(False, f"ingredient asks for fresh; product is {dept}")

    if wants_ambient(ingredient_name) and dept == DEPARTMENT_FRESH:
        return Judgement(
            False, f"ingredient asks for a keeping form; product is {dept}"
        )

    return Judgement(True, "")


def leaf_names_ingredient(ingredient_name: str, taxonomy_leaf: str) -> bool:
    """Whether the taxonomy calls this product the thing the recipe asked for.

    The surprise of the investigation: AH names its taxonomy leaves the way
    recipes name ingredients - "Witte kaas", "Gerookte zalm", "Slagroom". Where
    they coincide it is a far better signal than a title substring, because a
    title containing "witte kaas" may be a dressing or a salami.
    """
    ing, leaf = normalise(ingredient_name), normalise(taxonomy_leaf)
    return bool(ing) and bool(leaf) and ing == leaf


def rank(ingredient_name: str, candidates: list) -> list:
    """Reorder candidates so the taxonomy-named ones come first.

    Only reorders; never drops. A candidate no leaf names is not thereby
    wrong - it usually means the taxonomy is coarser than the ingredient, as
    for "bladpeterselie", whose leaf is the broader "Verse kruiden".

    Stable, so the retailer's own relevance ordering survives underneath.
    """
    return sorted(
        candidates,
        key=lambda c: not leaf_names_ingredient(
            ingredient_name, getattr(c, "taxonomy_leaf", "")
        ),
    )
