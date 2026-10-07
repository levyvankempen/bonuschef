"""Tests for chart helpers (pure logic plus AppTest guard paths)."""

import ast
from pathlib import Path

import pandas as pd

from bonuschef.portal import ui
from bonuschef.portal.ui import (
    IMAGE_CAP_PX,
    _CARD_IMAGE_KEY,
    _CARD_STYLES,
    _GRID_KEY,
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
    """Streamlit's own reset sets img { max-width: none }, so without a cap a
    440px source would be stretched across a wider desktop column."""
    assert IMAGE_CAP_PX == 440, "440x324 is the largest variant AH publishes"
    styles = _CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY, grid_prefix=_GRID_KEY)
    assert f"max-width: {IMAGE_CAP_PX}px" in styles
    assert _CARD_IMAGE_KEY in styles, "the cap must be scoped to the card"


def test_the_card_image_is_sized_by_css_rather_than_by_measurement():
    """A card image sometimes painted tiny, and clicking it fixed it for good.

    That is the signature of width="stretch": the frontend sizes the <img>
    from the measured width of its parent, and on first mount - especially a
    re-mount inside a fragment - that measurement can arrive before the
    container has been laid out. Opening the fullscreen overlay and closing it
    remounts the element against a container that now has a real width, which
    is why it stayed correct afterwards.

    width:100% resolves against the parent's real box at paint time, so there
    is no measurement to race.
    """
    styles = _CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY, grid_prefix=_GRID_KEY)
    assert "width: 100% !important" in styles, "fluid without being measured"
    assert "height: auto" in styles, "and never distorted"

    # Read the call, not the text around it: the docstring above names
    # "stretch" as the thing being avoided, and a substring check on the
    # source would match that comment and pass no matter what the code did.
    tree = ast.parse(Path(ui.__file__).read_text())
    images = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call) and ast.unparse(node.func) == "st.image"
    ]
    assert images, "the card must render an image"
    for call in images:
        passed = {kw.arg for kw in call.keywords}
        assert "width" not in passed, (
            "stretch is the measured path that rendered the picture tiny"
        )


# --- the pair of prices on the card face ------------------------------------


def test_the_pair_is_one_formatter():
    """It escaped the discipline offers.euro exists for. The same fact was a
    heading with "normaal" on Vanavond, body text with a middot on Recepten, and
    "i.p.v." on an ingredient line - three spellings of "cheaper than usual"."""
    from bonuschef.portal.offers import was_now

    assert was_now(2.19, 4.88) == "€2.19 · ~~€4.88~~"


def test_a_before_price_that_is_not_higher_is_dropped():
    """A strike-through on an equal or larger number claims a saving that is not
    there."""
    from bonuschef.portal.offers import was_now

    assert was_now(2.19, 2.19) == "€2.19"
    assert was_now(2.19, 1.00) == "€2.19"
    assert was_now(2.19, None) == "€2.19"


def test_no_current_price_is_no_string_at_all():
    from bonuschef.portal.offers import was_now

    assert was_now(None, 4.88) == ""


def test_an_offer_line_carries_the_prices_not_only_the_delta():
    """ "kipfilet − €2.69" is a difference, and a difference cannot be checked
    against anything in the shop - which is what somebody is doing when they
    read it."""
    from bonuschef.portal.ui import OfferLine

    line = OfferLine(
        label="kipfilet", saving="− €2.69", colour="green", prices="€2.19 · ~~€4.88~~"
    )
    assert line.prices and "2.19" in line.prices and "4.88" in line.prices


def test_an_offer_line_may_carry_the_reference_age():
    """A "was" price observed a week ago is decorative rather than a
    comparison."""
    from bonuschef.portal.ui import OfferLine

    line = OfferLine(
        label="kipfilet",
        saving="− €2.69",
        colour="green",
        reference_note="normale prijs van 6 dagen geleden",
    )
    assert "6 dagen" in line.reference_note


# --- the grid that reflows ---------------------------------------------------


class TestTwoAcrossWhereTwoFit:
    """st.columns do not stack: a two-column desktop grid is a two-column 170px
    phone grid, which is why this project rendered one card per row and wrote it
    down as a requirement.

    The reason was real; the conclusion was too strong. A flex row allowed to
    wrap, with a minimum column width, gives two columns where two fit and one
    where they do not - without a media query, and without asking Streamlit for
    a viewport width it cannot report.
    """

    @staticmethod
    def _styles() -> str:
        return _CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY, grid_prefix=_GRID_KEY)

    def test_the_row_is_allowed_to_wrap(self):
        assert "flex-wrap: wrap" in self._styles()

    def test_a_column_has_a_floor_so_a_phone_gets_one(self):
        """Below the floor the card's own contents wrap badly, so a 358px phone
        must fall to a single column rather than halving the image."""
        styles = self._styles()
        assert "min-width: 320px" in styles
        assert "flex: 1 1 320px" in styles

    def test_the_grid_rules_are_scoped_to_the_grid(self):
        """Streamlit lays every horizontal container out as a flex row. Unscoped,
        these rules would reflow the action rows and the price rows too."""
        styles = self._styles()
        for rule in ("flex-wrap", "min-width: 320px"):
            line = next(ln for ln in styles.splitlines() if rule in ln)
            block = styles[: styles.index(line)]
            assert _GRID_KEY in block.rsplit("[class*=", 1)[-1] or _GRID_KEY in block

    def test_the_card_image_cap_still_applies(self):
        """Both rule sets share one stylesheet; adding the grid must not drop
        the cap that keeps a 440px source from being stretched."""
        assert f"max-width: {IMAGE_CAP_PX}px" in self._styles()


def test_a_compact_card_puts_the_rest_behind_one_tap():
    """A card carrying the coverage caption, the rating, the ingredient list and
    four buttons shows one recipe at a time, which is the complaint this
    answers."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(ui.__file__).read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "render_recipe_card"
    )
    body = ast.unparse(fn)
    assert "if not compact:" in body, "full cards keep everything inline"
    assert "_render_details_on_request" in body


def test_the_detail_toggle_is_a_fragment_without_a_rerun():
    """Opening a card must not re-run the page or move it, the same rule the
    ingredient list already follows."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(ui.__file__).read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_render_details_on_request"
    )
    assert any("st.fragment" in ast.unparse(d) for d in fn.decorator_list)
    calls = {ast.unparse(n.func) for n in ast.walk(fn) if isinstance(n, ast.Call)}
    assert "st.rerun" not in calls


def test_the_detail_is_not_a_dialog():
    """The ingredient list can open the correction dialog, and Streamlit dialogs
    do not nest - which this repo has already been bitten by."""
    import ast
    from pathlib import Path

    tree = ast.parse(Path(ui.__file__).read_text())
    fn = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.FunctionDef) and n.name == "_render_details_on_request"
    )
    assert not any("dialog" in ast.unparse(d) for d in fn.decorator_list)
