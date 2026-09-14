"""Albert Heijn Allerhande recipe reads: search, and adopt.

Lives beside ``ah_auth`` rather than under ``dags/`` because the portal calls it
interactively. A search has to answer a person who is typing, in one round trip;
routing that through a Dagster run would deliver the answer as a run status
seconds later, and adoption is parameterised by recipe id, which assets are not.

AH's recipe interface is unofficial and has already lost one backend
(``/mobile-services/recipes/v1/*`` returns a DNS failure from inside AH's own
gateway). Everything here therefore distinguishes three outcomes a caller must
never conflate: nothing matched, AH is unreachable, and AH answered in a shape
we refuse to guess at.
"""

from __future__ import annotations

import html
import threading
import time
from dataclasses import dataclass

from bonuschef.utils.ah_auth import AHAuthError, AHTokenManager, manager_from_env

RECIPE_URL_BASE = "https://www.ah.nl"

# AH does not error above this - it silently returns 10 results instead.
MAX_SEARCH_SIZE = 100

# A recipe that is reliably present, sent alongside every fetch. AH reports an
# unknown id and a dead subgraph identically (HTTP 200, null field, "Subgraph
# errors redacted"), so a second known-good id in the same document is the only
# way to tell them apart. If AH ever retires it, every fetch reads as
# unavailable - loud, not silent, and a one-line fix.
CANARY_RECIPE_ID = 1302811

# One household reading its own account at human speed. There are no rate-limit
# headers on any response, so the only feedback channel is a ban; pace anyway.
_MIN_INTERVAL_S = 0.25
_last_call = 0.0
_pace_lock = threading.Lock()

_RECIPE_QUERY = """query AHRecipe($id: Int!, $canary: Int!) {
  recipe(id: $id) {
    id title description href courses
    cookTime ovenTime waitTime
    servings { number type }
    images { url width height }
    ingredients {
      id quantity text
      quantityUnit { singular plural }
      name { singular plural }
    }
  }
  canary: recipe(id: $canary) { id }
}"""

# `size` is a custom scalar, not an Int - declaring it Int fails validation
# with "PageSize cannot represent value". `start` really is an Int.
_SEARCH_QUERY = """query AHRecipeSearch(
  $text: String, $size: PageSize, $start: Int,
  $sortBy: RecipeSearchSortOption, $filters: [RecipeSearchQueryFilter!]
) {
  recipeSearch(query: {
    searchText: $text, size: $size, start: $start,
    sortBy: $sortBy, filters: $filters
  }) {
    page { total }
    result { id title images { url width height } }
  }
}"""

_FACETS_QUERY = """query AHRecipeFacets {
  recipeSearch(query: { size: 1 }) {
    filters { name label filters { name label count } }
  }
}"""

# The catalogue accepts exactly these and rejects anything else at request time,
# which surfaces as the whole catalogue being unreachable - the same confusing
# failure the PageSize scalar produced. Reject locally instead.
SORT_OPTIONS = ("NEWEST", "POPULAR", "TRENDING")


class AHRecipeError(RuntimeError):
    """Base for every way the recipe catalogue can let us down."""


class AHRecipeUnavailable(AHRecipeError):
    """AH could not be reached, or answered without answering."""


class AHRecipeNotFound(AHRecipeError):
    """AH answered, and there is no such recipe. A search never raises this."""


class AHRecipeShapeError(AHRecipeError):
    """AH answered in a shape we cannot interpret.

    Deliberately fatal. A recipe adopted from a document we half-understood is a
    recipe with silently missing ingredients, which is worse than no recipe at
    all because it looks fine and costs wrong forever.
    """


@dataclass(frozen=True)
class Ingredient:
    """One line of a recipe, with the unit AH reports rather than one we parsed."""

    concept_id: int
    name: str
    quantity: float  # fractional: "1½ courgette" arrives as 1.5
    unit: str  # "g", "el", "teen"; empty means countable
    raw_text: str


@dataclass(frozen=True)
class Recipe:
    recipe_id: int
    title: str
    servings: int
    ingredients: tuple[Ingredient, ...]
    url: str = ""
    image_url: str = ""
    description: str = ""
    cook_time_min: int | None = None


@dataclass(frozen=True)
class RecipeHit:
    recipe_id: int
    title: str
    image_url: str = ""


@dataclass(frozen=True)
class SearchPage:
    """``total`` is AH's count for the whole query, not ``len(hits)``."""

    total: int
    hits: tuple[RecipeHit, ...]
    start: int = 0


def _pace() -> None:
    global _last_call
    with _pace_lock:
        wait = _MIN_INTERVAL_S - (time.monotonic() - _last_call)
        if wait > 0:
            time.sleep(wait)
        _last_call = time.monotonic()


def _smallest_image(images: object, min_width: int = 200) -> str:
    """A thumbnail. AH returns nine sizes and no field marks one as canonical."""
    if not isinstance(images, list):
        return ""
    usable = [
        i
        for i in images
        if isinstance(i, dict) and isinstance(i.get("width"), int) and i.get("url")
    ]
    if not usable:
        return ""
    big_enough = [i for i in usable if i["width"] >= min_width] or usable
    return str(min(big_enough, key=lambda i: i["width"])["url"])


def _classify(data: dict, errors: list[dict], key: str = "recipe") -> object:
    """Turn AH's one ambiguous answer into two distinguishable ones."""
    payload = data.get(key)
    if payload is not None:
        if errors:
            raise AHRecipeUnavailable(
                f"AH returned a recipe together with errors {errors!r}; refusing "
                "to adopt half an answer"
            )
        return payload
    if data.get("canary") is None:
        raise AHRecipeUnavailable(
            "Albert Heijn's recipe catalogue did not answer - a known-good "
            f"recipe came back empty too. Errors: {errors!r}"
        )
    raise AHRecipeNotFound(f"Albert Heijn has no recipe with that id. {errors!r}")


def _parse_ingredient(payload: object, line_no: int) -> Ingredient:
    if not isinstance(payload, dict):
        raise AHRecipeShapeError(f"ingredient {line_no} is not an object")
    concept_id = payload.get("id")
    if not isinstance(concept_id, int):
        raise AHRecipeShapeError(
            f"ingredient {line_no} has no concept id; without one it cannot be "
            "resolved to a product and nothing can be reused between recipes"
        )
    name = (
        (payload.get("name") or {}) if isinstance(payload.get("name"), dict) else {}
    ).get("singular")
    if not isinstance(name, str) or not name.strip():
        raise AHRecipeShapeError(f"ingredient {line_no} has no name")
    quantity = payload.get("quantity")
    if not isinstance(quantity, int | float) or quantity <= 0:
        raise AHRecipeShapeError(
            f"ingredient {line_no} ({name!r}) reports quantity {quantity!r}"
        )
    unit_node = payload.get("quantityUnit")
    unit = (unit_node or {}).get("singular") if isinstance(unit_node, dict) else ""
    return Ingredient(
        concept_id=concept_id,
        name=name.strip(),
        quantity=float(quantity),
        unit=(unit or "").strip(),
        raw_text=html.unescape(str(payload.get("text") or "")),
    )


def _parse_recipe(payload: object) -> Recipe:
    """Build a Recipe, or refuse.

    Every check here guards a shape that would otherwise be written to the
    warehouse as a plausible recipe and surface much later as a wrong cost
    rather than as an error.
    """
    if not isinstance(payload, dict):
        raise AHRecipeShapeError(
            f"expected a recipe object, got {type(payload).__name__}"
        )
    recipe_id, title = payload.get("id"), str(payload.get("title") or "").strip()
    if not isinstance(recipe_id, int) or not title:
        raise AHRecipeShapeError("recipe is missing an id or a title")
    servings_node = payload.get("servings")
    servings = (
        (servings_node or {}).get("number") if isinstance(servings_node, dict) else None
    )
    if not isinstance(servings, int) or servings < 1:
        raise AHRecipeShapeError(f"recipe {recipe_id} reports servings {servings!r}")
    raw = payload.get("ingredients")
    if not isinstance(raw, list) or not raw:
        # AH has never returned an empty list. If it starts, adopting it would
        # create a recipe that costs nothing and looks complete.
        raise AHRecipeShapeError(f"recipe {recipe_id} carries no ingredients")
    href = str(payload.get("href") or "")
    return Recipe(
        recipe_id=recipe_id,
        title=title,
        servings=servings,
        ingredients=tuple(_parse_ingredient(i, n) for n, i in enumerate(raw)),
        url=f"{RECIPE_URL_BASE}{href}" if href.startswith("/") else href,
        image_url=_smallest_image(payload.get("images")),
        description=str(payload.get("description") or ""),
        cook_time_min=payload.get("cookTime")
        if isinstance(payload.get("cookTime"), int)
        else None,
    )


def fetch_recipe(recipe_id: int, *, manager: AHTokenManager | None = None) -> Recipe:
    """Fetch one recipe, distinguishing "no such recipe" from "AH is down"."""
    manager = manager or manager_from_env()
    _pace()
    try:
        data, errors = manager.graphql_partial(
            _RECIPE_QUERY, {"id": int(recipe_id), "canary": CANARY_RECIPE_ID}
        )
    except AHAuthError as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    except Exception as exc:  # requests raises a zoo of transport errors
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    return _parse_recipe(_classify(data, errors))


def search_recipes(
    text: str | None = None,
    *,
    size: int = 20,
    start: int = 0,
    sort_by: str | None = None,
    filters: list[dict[str, object]] | None = None,
    manager: AHTokenManager | None = None,
) -> SearchPage:
    """Search or browse the catalogue. No results is a value, never an exception.

    With no ``text`` this browses, which is what lets the add-recipe page be
    useful before anything has been typed.
    """
    if sort_by is not None and sort_by not in SORT_OPTIONS:
        # The catalogue rejects an unknown ordering at request time, which
        # surfaces as the whole thing being unreachable - the same confusing
        # failure the PageSize scalar produced. Fail where the mistake is.
        raise ValueError(f"sort_by must be one of {SORT_OPTIONS}, got {sort_by!r}")
    manager = manager or manager_from_env()
    _pace()
    try:
        data = manager.graphql(
            _SEARCH_QUERY,
            {
                "text": text,
                "size": min(int(size), MAX_SEARCH_SIZE),
                "start": int(start),
                "sortBy": sort_by,
                "filters": filters,
            },
        )
    except AHAuthError as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    except Exception as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc

    node = data.get("recipeSearch")
    if not isinstance(node, dict):
        raise AHRecipeShapeError("search returned no result block")
    results = node.get("result")
    if not isinstance(results, list):
        raise AHRecipeShapeError("search returned no result list")
    hits = tuple(
        RecipeHit(
            recipe_id=r["id"],
            title=str(r.get("title") or ""),
            image_url=_smallest_image(r.get("images")),
        )
        for r in results
        if isinstance(r, dict) and isinstance(r.get("id"), int)
    )
    total = (
        (node.get("page") or {}) if isinstance(node.get("page"), dict) else {}
    ).get("total")
    return SearchPage(total=int(total or 0), hits=hits, start=start)


def facet_values(group: str, *, manager: AHTokenManager | None = None) -> list[str]:
    """The values the catalogue itself offers for a facet, e.g. seizoen.

    Read rather than hardcoded: a copy would rot silently the day AH renames a
    season, and offering a season with nothing in it is worse than no filter.
    """
    manager = manager or manager_from_env()
    _pace()
    try:
        data = manager.graphql(_FACETS_QUERY, {})
    except AHAuthError as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    except Exception as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc

    node = data.get("recipeSearch")
    groups = node.get("filters") if isinstance(node, dict) else None
    if not isinstance(groups, list):
        raise AHRecipeShapeError("the catalogue returned no facet groups")
    for entry in groups:
        if isinstance(entry, dict) and entry.get("name") == group:
            values = entry.get("filters")
            if not isinstance(values, list):
                raise AHRecipeShapeError(f"facet {group!r} carries no values")
            return [
                str(v["name"]) for v in values if isinstance(v, dict) and v.get("name")
            ]
    return []
