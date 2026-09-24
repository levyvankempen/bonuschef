"""Tests for chart helpers (pure logic plus AppTest guard paths)."""

import pandas as pd

from bonuschef.portal.ui import (
    IMAGE_CAP_PX,
    _CARD_IMAGE_KEY,
    _CARD_STYLES,
    _top_movers,
    bigger_image,
)


def test_top_movers_ranks_by_cumulative_absolute_change():
    data = pd.DataFrame(
        {
            "product_name": ["a", "a", "b", "c"],
            "price_change": [0.5, -0.5, 0.2, -2.0],
        }
    )
    assert _top_movers(data, n=2) == ["c", "a"]


# --- Recipe imagery -------------------------------------------------------
#
# AH publishes recipe images in two sizes and no more. Probing the CDN on
# several recipes: 220x162 and 440x324 answer 200; 330, 550, 640, 660, 700,
# 800, 880, 1200 and 1320 wide all answer 404. Every stored row holds the 220,
# which is why a card led with a coloured square.

_STORED = "https://static.ah.nl/static/recepten/img_122541_220x162_JPG.jpg"
_LARGER = "https://static.ah.nl/static/recepten/img_122541_440x324_JPG.jpg"


def test_a_recipe_image_is_upgraded_to_the_larger_variant():
    """The size is in the path, so this is a rewrite and not a re-fetch: all
    908 stored recipes gain it without a backfill or a pipeline run."""
    assert bigger_image(_STORED) == _LARGER


def test_an_image_the_rewrite_does_not_recognise_is_left_alone():
    """It fails open. A change to AH's naming degrades to today's picture
    rather than to a broken one."""
    unknown = "https://static.ah.nl/static/recepten/img_1_999x999_JPG.jpg"
    assert bigger_image(unknown) == unknown
    elsewhere = "https://example.com/img_122541_220x162_JPG.jpg"
    assert bigger_image(elsewhere) == elsewhere


def test_a_missing_image_stays_missing():
    """A card renders without a picture rather than with a broken one."""
    assert bigger_image(None) == ""
    assert bigger_image("") == ""
    assert bigger_image(float("nan")) == ""


def test_the_card_never_asks_for_more_pixels_than_the_source_has():
    """Streamlit's own reset sets img { max-width: none }, so a fixed pixel
    width overflows a narrow phone column and scrolls the page sideways. The
    image stretches to the column and is capped here instead, which is the
    only combination that satisfies both halves."""
    assert IMAGE_CAP_PX == 440, "440x324 is the largest variant AH publishes"
    styles = _CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY)
    assert f"max-width: {IMAGE_CAP_PX}px" in styles
    assert _CARD_IMAGE_KEY in styles, "the cap must be scoped to the card"
