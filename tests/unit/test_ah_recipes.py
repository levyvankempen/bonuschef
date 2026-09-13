"""The AH recipe client: search, adopt, and the three ways AH can let us down.

Network-free throughout. The pure parsing layer needs no stub at all, which is
where most of the value is: the shape checks are what stop a half-understood
document becoming a recipe that looks fine and costs wrong forever.
"""

from __future__ import annotations

import time

import pytest

from bonuschef.utils.ah_auth import AHTokenManager, TokenBundle, TokenStore
from bonuschef.utils.ah_recipes import (
    CANARY_RECIPE_ID,
    AHRecipeNotFound,
    AHRecipeShapeError,
    AHRecipeUnavailable,
    _parse_recipe,
    fetch_recipe,
    search_recipes,
)
from tests.conftest import FakeResponse


@pytest.fixture
def manager(tmp_path) -> AHTokenManager:
    """A manager whose token is already fresh, so nothing tries to refresh.

    Without it every test would need a queued refresh response first, and a
    stray HTTP call would read as a client bug rather than a fixture one.
    """
    store = TokenStore(tmp_path / "t.json")
    now = time.time()
    store.save(TokenBundle("tok", "refresh", now + 3600, now, now))
    return AHTokenManager(store)


@pytest.fixture(autouse=True)
def _no_pacing(monkeypatch):
    """The 250ms politeness gate is real in production and pointless in tests."""
    monkeypatch.setattr("bonuschef.utils.ah_recipes._MIN_INTERVAL_S", 0)


def _ingredient(**over):
    base = {
        "id": 1853,
        "quantity": 3,
        "text": "3 courgettes",
        "quantityUnit": {"singular": "", "plural": None},
        "name": {"singular": "courgette", "plural": "courgettes"},
    }
    return {**base, **over}


def _recipe(**over):
    base = {
        "id": 1302811,
        "title": "Quinoabowl",
        "href": "/allerhande/recept/R-R1302811/quinoabowl",
        "servings": {"number": 4, "type": "personen"},
        "images": [{"url": "https://static.ah.nl/a.jpg", "width": 220, "height": 162}],
        "cookTime": 30,
        "ingredients": [_ingredient()],
    }
    return {**base, **over}


def _ok(recipe):
    return FakeResponse(
        200, {"data": {"recipe": recipe, "canary": {"id": CANARY_RECIPE_ID}}}
    )


# --- the unit comes from the API, not from parsing text ---------------------


def test_the_unit_is_read_from_the_api():
    """quantityUnit is a field. The alternative - stripping the name and the
    number off `text` - rests on a formatting invariant that holds today and
    would break silently the day AH changes it."""
    recipe = _parse_recipe(
        _recipe(
            ingredients=[
                _ingredient(),
                _ingredient(
                    id=3200,
                    quantity=1.5,
                    text="1½ el milde olijfolie",
                    quantityUnit={"singular": "el", "plural": None},
                    name={"singular": "milde olijfolie", "plural": None},
                ),
                _ingredient(
                    id=4730,
                    quantity=310,
                    text="310 g verse zalmfilet",
                    quantityUnit={"singular": "g", "plural": "g"},
                    name={"singular": "verse zalmfilet", "plural": None},
                ),
            ]
        )
    )
    assert [(i.concept_id, i.quantity, i.unit) for i in recipe.ingredients] == [
        (1853, 3.0, ""),  # empty unit means countable
        (3200, 1.5, "el"),  # fractional quantity: 1½
        (4730, 310.0, "g"),
    ]


def test_html_entities_in_the_raw_text_are_unescaped():
    recipe = _parse_recipe(
        _recipe(ingredients=[_ingredient(text="1&#189; courgette", quantity=1.5)])
    )
    assert recipe.ingredients[0].raw_text == "1½ courgette"


# --- refusing a shape we do not understand ----------------------------------


@pytest.mark.parametrize(
    "broken",
    [
        pytest.param({"ingredients": []}, id="no-ingredients"),
        pytest.param({"servings": {"number": 0}}, id="zero-servings"),
        pytest.param({"servings": None}, id="no-servings"),
        pytest.param({"title": ""}, id="no-title"),
        pytest.param({"ingredients": [_ingredient(id=None)]}, id="no-concept-id"),
        pytest.param({"ingredients": [_ingredient(quantity=0)]}, id="zero-quantity"),
        pytest.param({"ingredients": [_ingredient(quantity=None)]}, id="no-quantity"),
        pytest.param(
            {"ingredients": [_ingredient(name={"singular": "", "plural": None})]},
            id="no-name",
        ),
    ],
)
def test_a_changed_shape_fails_rather_than_adopting_a_partial_recipe(broken):
    with pytest.raises(AHRecipeShapeError):
        _parse_recipe(_recipe(**broken))


def test_a_missing_unit_is_countable_not_an_error():
    """An absent quantityUnit is how AH spells "pieces"; it must not refuse."""
    recipe = _parse_recipe(_recipe(ingredients=[_ingredient(quantityUnit=None)]))
    assert recipe.ingredients[0].unit == ""


# --- telling AH's two identical answers apart -------------------------------


def test_fetch_sends_a_canary_alongside_the_recipe(http_post, manager):
    http_post.queue(_ok(_recipe()))
    fetch_recipe(1302811, manager=manager)
    _, kwargs = http_post.last
    assert kwargs["json"]["variables"] == {"id": 1302811, "canary": CANARY_RECIPE_ID}


def test_a_null_recipe_beside_a_live_canary_is_not_found(http_post, manager):
    http_post.queue(
        FakeResponse(
            200,
            {
                "data": {"recipe": None, "canary": {"id": CANARY_RECIPE_ID}},
                "errors": [{"message": "Subgraph errors redacted"}],
            },
        )
    )
    with pytest.raises(AHRecipeNotFound):
        fetch_recipe(999_999_999, manager=manager)


def test_a_null_canary_means_the_catalogue_is_down(http_post, manager):
    """AH sends the same body for both cases. The canary is the only signal."""
    http_post.queue(
        FakeResponse(
            200,
            {
                "data": {"recipe": None, "canary": None},
                "errors": [{"message": "Subgraph errors redacted"}],
            },
        )
    )
    with pytest.raises(AHRecipeUnavailable):
        fetch_recipe(1302811, manager=manager)


def test_a_recipe_returned_with_errors_is_refused(http_post, manager):
    http_post.queue(
        FakeResponse(
            200,
            {
                "data": {"recipe": _recipe(), "canary": {"id": CANARY_RECIPE_ID}},
                "errors": [{"message": "partial"}],
            },
        )
    )
    with pytest.raises(AHRecipeUnavailable):
        fetch_recipe(1302811, manager=manager)


def test_an_http_failure_is_unavailable_not_not_found(http_post, manager):
    http_post.queue(FakeResponse(503, None, text="upstream unavailable"))
    with pytest.raises(AHRecipeUnavailable):
        fetch_recipe(1302811, manager=manager)


# --- search -----------------------------------------------------------------


def test_no_results_is_a_value_not_an_exception(http_post, manager):
    http_post.queue(
        FakeResponse(200, {"data": {"recipeSearch": {"page": {"total": 0}, "result": []}}})
    )
    page = search_recipes("zzqqzz", manager=manager)
    assert (page.total, page.hits) == (0, ())


def test_search_clamps_size_because_ah_silently_returns_ten_above_a_hundred(
    http_post, manager
):
    http_post.queue(
        FakeResponse(200, {"data": {"recipeSearch": {"page": {"total": 5}, "result": []}}})
    )
    search_recipes("pasta", size=500, manager=manager)
    assert http_post.last[1]["json"]["variables"]["size"] == 100


def test_search_returns_the_total_not_the_page_length(http_post, manager):
    http_post.queue(
        FakeResponse(
            200,
            {
                "data": {
                    "recipeSearch": {
                        "page": {"total": 1157},
                        "result": [
                            {"id": 1, "title": "A", "images": []},
                            {"id": 2, "title": "B", "images": []},
                        ],
                    }
                }
            },
        )
    )
    page = search_recipes("courgette", manager=manager)
    assert page.total == 1157
    assert [h.recipe_id for h in page.hits] == [1, 2]


def test_search_transport_failure_is_unavailable(http_post, manager):
    http_post.queue(FakeResponse(500, None, text="boom"))
    with pytest.raises(AHRecipeUnavailable):
        search_recipes("pasta", manager=manager)


def test_the_search_document_declares_the_custom_page_scalar():
    """`size` is a PageSize, not an Int. Declaring it Int fails AH's validation
    with "PageSize cannot represent value" - a 400 that surfaces as the whole
    catalogue being unreachable, which is a confusing way to learn about a
    type name."""
    from bonuschef.utils.ah_recipes import _SEARCH_QUERY

    assert "$size: PageSize" in _SEARCH_QUERY
    assert "$size: Int" not in _SEARCH_QUERY
