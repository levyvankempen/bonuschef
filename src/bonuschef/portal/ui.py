"""Streamlit UI helper functions."""

from collections.abc import Callable, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Literal

import pandas as pd
import streamlit as st
import altair as alt

# AH publishes recipe images in exactly two sizes. Probing the CDN on several
# recipes: 220x162 (9 KB) and 440x324 (32 KB) answer 200; 330, 550, 640, 660,
# 700, 800, 880, 1200 and 1320 wide all answer 404. So 440 is not a preference,
# it is the ceiling, and a card that stretched past it would be showing an
# upscale rather than a picture.
IMAGE_CAP_PX = 440

_AH_IMAGE_HOST = "static.ah.nl"
_THUMBNAIL_VARIANT = "_220x162_"
_LARGER_VARIANT = "_440x324_"

# Sizing is done here rather than by Streamlit, and that is the point.
#
# width="stretch" makes the frontend size the <img> from the MEASURED width of
# its parent. When the card is first mounted - and especially when it is
# re-mounted inside a fragment - that measurement can come back before the
# container has been laid out, and the picture paints at its minimum size.
# Clicking it opens Streamlit's fullscreen overlay, and closing that remounts
# the element against a container that now has a real width, which is why the
# image is correct ever after. A max-width alone cannot rescue that: it caps an
# image, it cannot enlarge an under-measured one.
#
# Giving the browser width:100% takes the measurement out of the loop entirely.
# It resolves against the parent's real box at paint time, with no JavaScript
# involved and nothing to race. !important because Streamlit sets its own
# inline width on the element.
#
# Scoped to the container key below rather than applied to every image, so none
# of this can reach the clearance thumbnails.
# The grid reflows on available width rather than on a breakpoint.
#
# st.columns do not stack on a narrow screen - a two-column desktop grid is a
# two-column 170px phone grid - which is why this project rendered one card per
# row and wrote that down as a requirement. The reason was real and the
# conclusion was too strong: a flex row that is allowed to wrap, with a minimum
# column width, gives two columns where two fit and one where they do not. No
# media query and no viewport query, which Streamlit cannot answer anyway.
#
# 320px is the floor: below it the card's own contents start wrapping badly, and
# a phone at 358px therefore gets exactly one column.
_GRID_MIN_PX = 320

_CARD_STYLES = f"""<style>
[class*="st-key-{{key_prefix}}"] img {{{{
  width: 100% !important;
  height: auto !important;
  max-width: {IMAGE_CAP_PX}px;
}}}}
[class*="st-key-{{grid_prefix}}"] [data-testid="stHorizontalBlock"] {{{{
  flex-wrap: wrap;
}}}}
[class*="st-key-{{grid_prefix}}"] [data-testid="stColumn"] {{{{
  flex: 1 1 {_GRID_MIN_PX}px;
  min-width: {_GRID_MIN_PX}px;
}}}}
</style>"""

_GRID_KEY = "bc-card-grid"

_CARD_IMAGE_KEY = "bc-card-image"

# st.badge accepts a fixed set of colour names. Naming it lets the checker
# verify the call rather than trusting a bare string, as tonight_page does.
BadgeColour = Literal["red", "orange", "green", "blue", "violet", "gray"]


@dataclass(frozen=True)
class OfferLine:
    """One discounted ingredient as the card shows it.

    A named tuple of four strings would do, and did; it grew a fifth field and
    the call sites stopped being readable. The prices and the note are
    pre-formatted by the caller because the formatting lives in offers.py, which
    exists so two pages cannot render one price two ways.
    """

    label: str
    saving: str
    colour: BadgeColour
    prices: str = ""
    reference_note: str = ""


_BANNER_STYLES = """<style>
[class*="st-key-bc-environment-banner"] {
  position: sticky;
  top: 0;
  z-index: 1000;
}
</style>"""


def render_environment_banner() -> None:
    """Say which environment this is, before anything else on the page.

    Nothing at all in production. An invited person has one environment and
    labelling it would be noise on every page they ever see, which is the
    second scenario in the requirement rather than an omission.

    At the top and sticky, unlike the version in the footer. The footer is
    right for the version - "a footnote rather than chrome", as app.py puts it,
    because "is the fix live?" is asked occasionally. Which environment you are
    looking at has to be answered *before* you read anything else, or the page
    misinforms you: the two deployments run the same portal, the same recipes
    and a copy of the same data, so a price read off the wrong one is wrong in
    a way nothing on the page reveals.

    The copy's age rides along because it is the other half of the same
    question. A test environment is only trustworthy to the extent its data is
    recent, and "these prices are eight days old" is the difference between a
    defect and a stale copy.

    Never raises, and never takes the page down. It resolves its own engine
    inside a try, so a database that is unreachable or not configured yet
    costs the copy's age and nothing else - app.py renders this before the
    sign-in wall, and resolving an engine unconditionally there once turned a
    missing variable into a blank application.

    The production check comes first, so nothing at all happens on the
    deployment where nothing should.
    """
    from bonuschef.version import get_environment, is_production

    if is_production():
        return

    st.markdown(_BANNER_STYLES, unsafe_allow_html=True)

    copied = _describe_copy(_engine_or_none())
    name = get_environment().upper()
    with st.container(key="bc-environment-banner"):
        st.warning(
            f"**{name}** — dit is niet de echte app. "
            + (copied or "Het is onbekend wanneer deze gegevens zijn gekopieerd."),
            icon=":material/science:",
        )


def _engine_or_none():
    """The warehouse engine, or None if there is not one to be had.

    `get_engine` is cached, so this costs nothing after the first page render.
    """
    from bonuschef.portal.db import get_engine

    try:
        return get_engine()
    except Exception:  # noqa: BLE001 - the banner is not worth a broken page
        return None


def _describe_copy(engine) -> str | None:
    """ "Gegevens gekopieerd ..." for a database that was copied, else None."""
    if engine is None:
        return None
    from bonuschef.portal.db import read_environment_copy
    from bonuschef.portal.freshness import describe_age, now

    try:
        copy = read_environment_copy(engine)
        if not copy or not copy.get("copied_at"):
            return None
        return f"Gegevens gekopieerd {describe_age(copy['copied_at'], now())}."
    except Exception:  # noqa: BLE001 - a banner must not take the page down
        return None


def bigger_image(url: object) -> str:
    """The larger of AH's two recipe-image variants.

    The size is in the path, so this is a rewrite rather than a re-fetch: every
    stored row gains it at once, with no backfill and no pipeline run. Raising
    the min_width in the fetch helper instead would buy the same 440 pixels,
    because there is nothing bigger to ask for.

    Anything not recognised is returned untouched, so an AH naming change
    degrades to today's behaviour rather than to a broken image.
    """
    if not isinstance(url, str) or not url:
        return ""
    if _AH_IMAGE_HOST not in url or _THUMBNAIL_VARIANT not in url:
        return url
    return url.replace(_THUMBNAIL_VARIANT, _LARGER_VARIANT)


def inject_card_styles() -> None:
    """Cap card imagery at the source resolution. Once per page render.

    Streamlit's own reset sets ``img { max-width: none }``, so an image given a
    fixed pixel width overflows a narrower phone column and the page scrolls
    sideways - which the portal spec forbids. Stretching to the column and
    capping here is the combination that satisfies both halves: it fills 358px
    on a phone and stops at 440 on the desktop's centred column.
    """
    st.markdown(
        _CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY, grid_prefix=_GRID_KEY),
        unsafe_allow_html=True,
    )


@contextmanager
def card_grid(columns: int = 2, key: str = "cards"):
    """A row of cards that becomes a column when there is no room for a row.

    Yields the column containers. Use it per row of cards; Streamlit has no
    masonry, so the caller chunks its list and the shortest card sets the row
    height - which is a fair trade for seeing twice as many at once.
    """
    with st.container(key=f"{_GRID_KEY}-{key}"):
        yield st.columns(columns, gap="medium")


def render_recipe_card(
    *,
    key: str,
    title: str,
    image_url: object = None,
    saving: str | None = None,
    lead: bool = False,
    compact: bool = False,
    urgency: tuple[str, BadgeColour] | None = None,
    offers: Sequence[OfferLine] = (),
    more_offers: int = 0,
    price: Callable[[], None] | None = None,
    rating: Callable[[], None] | None = None,
    extra: Callable[[], None] | None = None,
    actions: Callable[[], None] | None = None,
) -> None:
    """One recipe, as a card led by its picture.

    The order is the order the decision is made in: recognise the dish, see what
    it saves, then the price, then why it is cheap. Before this there were four
    near-identical renderers and the saving was a heading in one of them and a
    caption in another - which is how a card came to lead with the total and
    bury the figure the application exists to produce.

    Lead and runner-up differ by type scale and by how much they carry, never by
    image size. A 56-pixel photograph of food is a coloured square.

    ``key`` must be unique on the page; the recipe id is the natural choice.
    """
    with st.container(border=True):
        if image_url:
            # Keyed by the caller, not by the title: two recipes can share a
            # name, and Streamlit raises on a duplicate key.
            with st.container(key=f"{_CARD_IMAGE_KEY}-{key}"):
                # Deliberately NOT width="stretch": that is the measured path
                # described above. Left at its natural width, the image is
                # 440px wide even if the stylesheet never arrives, and the CSS
                # above makes it fluid. The failure mode is a correct-sized
                # picture rather than a tiny one.
                st.image(str(image_url))

        st.markdown(f"### {title}" if lead else f"**{title}**")

        # The largest text on the card, and now the same size on all of them.
        #
        # It used to be one step smaller on a runner-up than on the lead. With
        # the lead gone every card is a runner-up, which left the saving the
        # same size as the price below it - and the requirement is that the
        # saving is the largest thing on the card, because it is the reason to
        # act.
        if saving:
            st.markdown(f"## {saving}")

        if urgency:
            label, colour = urgency
            st.badge(label, color=colour, icon=":material/schedule:")

        if price is not None:
            price()

        _render_offer_badges(offers, more_offers)

        if not compact:
            if rating is not None:
                rating()
            if extra is not None:
                extra()
            if actions is not None:
                actions()
            return

        # Compact: the highlights are above, and everything else is one tap
        # away. A card carrying the coverage caption, the rating, the ingredient
        # list and four buttons is a page that shows one recipe at a time -
        # which is the complaint this answers.
        #
        # In place rather than in a dialog, because the ingredient list can open
        # the correction dialog and Streamlit dialogs do not nest. The toggle is
        # a fragment, so opening one card does not re-run the page or move it.
        _render_details_on_request(key, rating, extra, actions)


@st.fragment
def _render_details_on_request(key, rating, extra, actions) -> None:
    """The rest of the card, and nothing until it is asked for."""
    open_key = f"card_open_{key}"
    opened = bool(st.session_state.get(open_key))
    if st.button(
        "Minder" if opened else "Meer",
        key=f"card_toggle_{key}",
        icon=":material/expand_less:" if opened else ":material/expand_more:",
        width="stretch",
    ):
        opened = not opened
        st.session_state[open_key] = opened
    if not opened:
        return
    if rating is not None:
        # Rendered whatever kind of card this is. It used to be gated on `lead`,
        # and with the lead removed that gate meant no card ever showed a
        # rating - a feature deleted by a condition rather than by a decision.
        rating()
    if extra is not None:
        extra()
    if actions is not None:
        actions()


def _render_offer_badges(offers: Sequence[OfferLine], more_offers: int) -> None:
    """Which ingredients make this cheap, named, with what they cost.

    The card used to say "2x bonus", which is a count: in a shop the person is
    standing in front of one particular discounted thing and the noun is the
    whole answer. Naming it was the first half.

    The second half is the pair of prices. "kipfilet - EUR 2,69" is a difference,
    and a difference cannot be checked against anything in the shop - while
    checking it against the sticker is exactly what somebody is doing when they
    read it. The recipe total cannot be checked either: nobody will ever see
    EUR 12,59 anywhere. So the line carries what the product costs now and what
    it ordinarily costs, which are the two numbers on the shelf.

    Both were already in hand. The row the saving is taken from carries
    price_today and price_ordinary; only the delta was read.
    """
    if not offers and not more_offers:
        return
    for line in offers:
        with st.container(horizontal=True, vertical_alignment="center"):
            st.badge(f"{line.label} {line.saving}", color=line.colour)
            if line.prices:
                st.markdown(f":gray[{line.prices}]")
        if line.reference_note:
            # A "was" price observed a week ago is decorative rather than a
            # comparison, and the page already has the vocabulary for saying so.
            st.caption(f":gray[{line.reference_note}]")
    if more_offers > 0:
        st.badge(f"+{more_offers} meer", color="gray")


def _top_movers(data: pd.DataFrame, n: int = 10) -> list[str]:
    """Return product names with the largest cumulative absolute price change."""
    movers = (
        data.assign(_abs_change=data["price_change"].abs())
        .groupby("product_name")["_abs_change"]
        .sum()
        .sort_values(ascending=False)
    )
    return movers.head(n).index.tolist()


def display_price_changes(df: pd.DataFrame, engine=None):
    """Display top movers with full price history from fct_products."""
    from bonuschef.portal.db import read_product_prices

    required = {"product_name", "snapshot_timestamp", "price_change", "pct_change"}
    if not required.issubset(df.columns):
        return

    changes = df[["product_name", "price_change"]].copy()
    changes["price_change"] = pd.to_numeric(changes["price_change"], errors="coerce")
    changes = changes.dropna()

    if changes.empty:
        return

    top = _top_movers(changes)
    all_products = sorted(changes["product_name"].unique())

    selected = st.multiselect(
        "Producten om te tonen (top 10 sterkste bewegers voorgeselecteerd)",
        options=all_products,
        default=top,
    )

    if not selected:
        st.info("Kies minstens één product om de grafiek te tonen.")
        return

    if engine is None:
        st.warning("Zonder databaseverbinding is de prijsgeschiedenis niet te laden.")
        return

    history = read_product_prices(engine, tuple(selected))

    if history.empty:
        st.info("Voor de gekozen producten is geen prijsgeschiedenis bekend.")
        return

    history["snapshot_timestamp"] = pd.to_datetime(
        history["snapshot_timestamp"], errors="coerce"
    )
    history["price"] = pd.to_numeric(history["price"], errors="coerce")
    history = history.dropna().sort_values(["product_name", "snapshot_timestamp"])

    chart = (
        alt.Chart(history)
        .mark_line(point=True)
        .encode(
            x=alt.X("snapshot_timestamp:T", title="Datum"),
            y=alt.Y("price:Q", title="Prijs (€)"),
            color=alt.Color("product_name:N", title="Product"),
            tooltip=["product_name", "snapshot_timestamp", "price"],
        )
        .properties(height=400)
        .interactive()
    )

    st.altair_chart(chart)
