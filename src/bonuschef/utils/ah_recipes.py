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
    modifiedAt
    rating { average count }
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

# One recipe's field selection, reused by the alias-batched fetch. Kept as a
# fragment body rather than duplicated: the batch and the single fetch must
# return the same shape or _parse_recipe would succeed on one and refuse the
# other.
_RECIPE_FIELDS = """
    id title description href courses
    cookTime ovenTime waitTime
    modifiedAt
    rating { average count }
    servings { number type }
    images { url width height }
    ingredients {
      id quantity text
      quantityUnit { singular plural }
      name { singular plural }
    }
"""

# Alias batching caps on a GraphQL lexer token budget, not on an alias count,
# so the ceiling moves whenever the field set changes. It was measured at 238
# before `rating` and `modifiedAt` were added; with them, 160 fails and 150
# passes - the first 200-batch attempted after adding two fields died with
# "parsing error: token limit reached, aborting lexing".
#
# 120 is the operating point: roughly 20% below the measured ceiling, so the
# next field added does not turn a working pool build into a total failure.
# Cost of the headroom is 17 requests per refresh instead of 13.
MAX_BATCH_SIZE = 120

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
    # Both, never just the average: five stars from three votes is not the same
    # claim as five stars from three hundred, and a pool ordered by rating alone
    # would put the former first.
    rating_average: float | None = None
    rating_count: int | None = None
    modified_at: str = ""


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


def _rating_field(payload: dict, key: str) -> float | None:
    """Read one half of the rating, tolerating its absence.

    Deliberately not fatal, unlike the shape checks below. A recipe nobody has
    voted on is a real recipe; refusing it would drop new entries from the pool
    for no better reason than that they are new.
    """
    node = payload.get("rating")
    if not isinstance(node, dict):
        return None
    value = node.get(key)
    return float(value) if isinstance(value, (int, float)) else None


def _rating_count(payload: dict) -> int | None:
    """Votes are a count. Coerced rather than widening the field: a fractional
    vote count reaching the warehouse would be nonsense that nothing rejects."""
    value = _rating_field(payload, "count")
    return None if value is None else int(value)


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
        rating_average=_rating_field(payload, "average"),
        rating_count=_rating_count(payload),
        modified_at=str(payload.get("modifiedAt") or ""),
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


# --------------------------------------------------------------------------
# The pool: the well-regarded recipes, fetched in batches
# --------------------------------------------------------------------------

# recipeSearch refuses start + size > 2000 with "Subgraph errors redacted" -
# the same opaque message a dead subgraph gives, so it must be respected rather
# than discovered. Here that ceiling is the feature: the top 2,000 by rating is
# exactly the bounded pool we want, and it costs 20 search requests.
MAX_SEARCH_OFFSET = 2000


# The pool is curated by construction rather than by anyone approving recipes
# one at a time. Three constraints do that work:
#
#   * main courses only - a ranking full of borrelhapjes and nagerechten does
#     not answer "what shall I cook tonight";
#   * "wat eten we vandaag", AH's own everyday-dinner tag, sorted by rating, so
#     the unloved outliers never enter;
#   * this year's and last year's magazine issues, so the pool is current.
#
# Measured: 908 distinct main courses in 19 search requests, 4.9 seconds.
_MAIN_COURSE = {"group": "menugang", "values": ["hoofdgerecht"]}
_EVERYDAY = {"group": "momenten", "values": ["wat-eten-we-vandaag"]}

# How many of the everyday main courses to take, best-rated first. The magazine
# slice is added on top of this.
EVERYDAY_POOL_SIZE = 600

# Which magazine years count as current.
RECENT_MAGAZINE_YEARS = ("2025-", "2026-")


def _search_all(
    filters: list[dict], limit: int, manager: AHTokenManager
) -> list[RecipeHit]:
    """Page through one filtered search, best-rated first."""
    hits: list[RecipeHit] = []
    seen: set[int] = set()
    start = 0
    limit = min(limit, MAX_SEARCH_OFFSET)
    while start < limit:
        size = min(MAX_SEARCH_SIZE, limit - start)
        page = search_recipes(
            None,
            size=size,
            start=start,
            sort_by="POPULAR",
            filters=filters,
            manager=manager,
        )
        if not page.hits:
            break
        for hit in page.hits:
            if hit.recipe_id not in seen:
                seen.add(hit.recipe_id)
                hits.append(hit)
        start += size
    return hits


def recent_magazine_issues(*, manager: AHTokenManager | None = None) -> list[str]:
    """This year's and last year's Allerhande issues, newest first."""
    manager = manager or manager_from_env()
    return sorted(
        (
            v
            for v in facet_values("allerhande-magazine", manager=manager)
            if v.startswith(RECENT_MAGAZINE_YEARS)
        ),
        reverse=True,
    )


def enumerate_pool(*, manager: AHTokenManager | None = None) -> list[RecipeHit]:
    """The curated pool: popular everyday main courses, plus current magazines.

    One request per magazine issue, which looks wasteful and is not optional:
    **values within a filter group intersect rather than union**. Asking for two
    issues at once returns recipes in *both*, which is 0 - measured, and exactly
    the opposite of what the shape of the argument suggests.
    """
    manager = manager or manager_from_env()

    hits: dict[int, RecipeHit] = {}
    for hit in _search_all([_MAIN_COURSE, _EVERYDAY], EVERYDAY_POOL_SIZE, manager):
        hits[hit.recipe_id] = hit

    for issue in recent_magazine_issues(manager=manager):
        for hit in _search_all(
            [_MAIN_COURSE, {"group": "allerhande-magazine", "values": [issue]}],
            MAX_SEARCH_SIZE,
            manager,
        ):
            hits.setdefault(hit.recipe_id, hit)

    return list(hits.values())


def fetch_recipes(
    recipe_ids: list[int], *, manager: AHTokenManager | None = None
) -> tuple[list[Recipe], list[int]]:
    """Fetch many recipes in alias-batched requests.

    Returns the recipes that parsed and the ids that did not, rather than
    raising on one bad recipe: a single unparseable entry must not cost the
    whole pool. An unreachable AH still raises, because that is not a property
    of any one recipe.

    Measured at 200 aliases: 7,555 recipes in 38 requests, 67 seconds.
    """
    manager = manager or manager_from_env()
    recipes: list[Recipe] = []
    failed: list[int] = []

    for offset in range(0, len(recipe_ids), MAX_BATCH_SIZE):
        chunk = recipe_ids[offset : offset + MAX_BATCH_SIZE]
        aliases = "\n".join(
            f"  r{i}: recipe(id: {int(rid)}) {{{_RECIPE_FIELDS}}}"
            for i, rid in enumerate(chunk)
        )
        query = (
            "query AHRecipeBatch($canary: Int!) {\n"
            f"{aliases}\n"
            "  canary: recipe(id: $canary) { id }\n"
            "}"
        )
        _pace()
        try:
            data, errors = manager.graphql_partial(query, {"canary": CANARY_RECIPE_ID})
        except AHAuthError as exc:
            raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
        except Exception as exc:
            raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc

        # The canary tells a dead subgraph apart from a batch of unknown ids.
        # Without it a broken backend looks exactly like 200 retired recipes.
        if not (data.get("canary") or {}).get("id"):
            raise AHRecipeUnavailable(
                "Albert Heijn answered without the canary recipe; "
                f"the recipe backend is not serving ({len(errors)} errors)"
            )

        for i, rid in enumerate(chunk):
            payload = data.get(f"r{i}")
            if payload is None:
                failed.append(int(rid))
                continue
            try:
                recipes.append(_parse_recipe(payload))
            except AHRecipeShapeError:
                failed.append(int(rid))
    return recipes, failed


# --------------------------------------------------------------------------
# AH's own product search: the mechanism behind "Kies producten"
# --------------------------------------------------------------------------

_PRODUCT_SEARCH_QUERY = """query AHProductSearch($input: SearchProductsInput!) {
  searchProducts(input: $input) {
    products { id title salesUnitSize brand }
  }
}"""

# How many of AH's hits to keep. Their ranking is good but not authoritative -
# "middelgrote ui" returns AH Bosui first, which is a spring onion - so taking
# a few gives the review queue something to choose between rather than one
# confident wrong answer.
PRODUCT_SEARCH_KEEP = 5


@dataclass(frozen=True)
class ProductHit:
    """A product AH's own search offers for a term.

    ``webshop_id`` is what the catalogue crosswalk keys on: AH returns 4164 for
    courgette and our own product_link is ``wi4164/ah-courgette``. That shared
    key is the whole reason this is usable - without it we would have only a
    title to fuzzy-match, which is the problem we were trying to escape.
    """

    webshop_id: int
    title: str
    sales_unit_size: str = ""
    brand: str = ""


def search_products(
    term: str, *, manager: AHTokenManager | None = None
) -> list[ProductHit]:
    """What AH itself offers when someone types this ingredient.

    This is the mechanism behind the "Kies producten" button on an Allerhande
    recipe page, and it resolves things a local name match cannot: "verse platte
    peterselie", "eetrijpe avocado", "gerookte spekreepjes" all land on the
    right product, and none of them appears verbatim in any product name.

    It is a proposal source, never an answer. Measured over 30 of the most-used
    unresolved ingredients it returned a product for all 30, and was wrong on
    roughly one in five - confidently so: "sjalot" returns a Boursin cheese
    spread and "kokend water" returns a kettle.
    """
    cleaned = (term or "").strip()
    if not cleaned:
        return []
    manager = manager or manager_from_env()
    _pace()
    try:
        data, errors = manager.graphql_partial(
            _PRODUCT_SEARCH_QUERY, {"input": {"query": cleaned}}
        )
    except AHAuthError as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    except Exception as exc:
        raise AHRecipeUnavailable(f"Could not reach Albert Heijn: {exc}") from exc
    if errors and not data.get("searchProducts"):
        raise AHRecipeUnavailable(
            f"Albert Heijn could not search for {cleaned!r}: "
            f"{errors[0].get('message', '')}"
        )

    products = (data.get("searchProducts") or {}).get("products") or []
    hits: list[ProductHit] = []
    for payload in products[:PRODUCT_SEARCH_KEEP]:
        if not isinstance(payload, dict):
            continue
        webshop_id, title = payload.get("id"), str(payload.get("title") or "").strip()
        # Both or neither: a hit without an id cannot be joined to anything, and
        # one without a title cannot be reviewed by a person.
        if not isinstance(webshop_id, int) or not title:
            continue
        hits.append(
            ProductHit(
                webshop_id=webshop_id,
                title=title,
                sales_unit_size=str(payload.get("salesUnitSize") or ""),
                brand=str(payload.get("brand") or ""),
            )
        )
    return hits
