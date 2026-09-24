"""Streamlit UI helper functions."""

from collections.abc import Callable, Sequence
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

# Scoped to the container key below rather than applied to every image, so the
# cap cannot reach the clearance thumbnails or anything else.
_CARD_STYLES = f"""<style>
[class*="st-key-{{key_prefix}}"] img {{{{ max-width: {IMAGE_CAP_PX}px; }}}}
</style>"""

_CARD_IMAGE_KEY = "bc-card-image"

# st.badge accepts a fixed set of colour names. Naming it lets the checker
# verify the call rather than trusting a bare string, as tonight_page does.
BadgeColour = Literal["red", "orange", "green", "blue", "violet", "gray"]


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
    st.markdown(_CARD_STYLES.format(key_prefix=_CARD_IMAGE_KEY), unsafe_allow_html=True)


def render_recipe_card(
    *,
    key: str,
    title: str,
    image_url: object = None,
    saving: str | None = None,
    lead: bool = False,
    urgency: tuple[str, BadgeColour] | None = None,
    offers: Sequence[tuple[str, str, BadgeColour]] = (),
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
                st.image(str(image_url), width="stretch")

        st.markdown(f"### {title}" if lead else f"**{title}**")

        # The largest text on the card. It is the reason to act, and it was
        # previously bold body text on the lead and a caption on the runners-up.
        if saving:
            st.markdown(f"{'##' if lead else '###'} {saving}")

        if urgency:
            label, colour = urgency
            st.badge(label, color=colour, icon=":material/schedule:")

        if price is not None:
            price()

        _render_offer_badges(offers, more_offers)

        if lead and rating is not None:
            rating()
        if extra is not None:
            extra()
        if actions is not None:
            actions()


def _render_offer_badges(
    offers: Sequence[tuple[str, str, BadgeColour]], more_offers: int
) -> None:
    """Which ingredients make this cheap, by name.

    The card used to say "2x bonus", which is a count. In a shop the person is
    standing in front of one particular discounted thing, and the noun is the
    whole answer. The largest savings are the ones named, so the remainder can
    be a count without hiding the biggest number.
    """
    if not offers and not more_offers:
        return
    with st.container(horizontal=True):
        for label, amount, colour in offers:
            st.badge(f"{label} {amount}", color=colour)
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
