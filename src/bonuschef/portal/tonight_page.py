"""Vanavond — which recipe is most worth cooking today, and why.

The question the rest of the application exists to support. Everything on this
page is an answer to it, and everything the data cannot support is said rather
than shown.

Three rules shape the whole file:

* **A saving is a lower bound, not a figure.** An unpriced ingredient makes a
  recipe's *total* unknown; it does not make the *saving* unknown, because an
  ingredient contributing nothing to the difference cannot change it. So a
  partially priced recipe is still ranked, its saving is rendered with a
  leading "minstens", and no total is shown for it at all.
* **Stale clearance withdraws one source; it does not blank the page.**
  Clearance is store-scoped and perishable within the day. Promotions are
  national and week-scoped. Treating them identically would mean that at 09:00,
  when the bonus evidence is entirely sound, the page refuses to answer.
* **What a figure covers is stated.** A discount on a 500 g pack used 100 g of
  is a saving on the pack, not on the meal.
"""

from typing import Literal, cast

import pandas as pd
import streamlit as st
from sqlalchemy.exc import ProgrammingError, SQLAlchemyError

from bonuschef.portal import freshness
from bonuschef.portal.review import open_review, open_single
from bonuschef.portal.db import (
    get_engine,
    read_bonus_feed_loaded_at,
    read_recipe_opportunity,
    read_recipe_opportunity_items,
    read_rejected_recipes,
    reinstate_recipe,
    reject_recipe,
)

# The promotional feed loads weekly, so it ages on a different clock from the
# hourly clearance scrape. Judging it by clearance's rule would call the page
# stale six days out of seven.
_BONUS_FEED_STALE_DAYS = 9

# st.badge accepts a fixed set of colour names; naming it lets the checker
# verify the call instead of trusting a bare string.
_BadgeColour = Literal["red", "orange", "green", "blue", "violet", "gray"]

_EXCLUSION_TEXT = {
    "no_ingredients": "Dit recept heeft geen ingrediënten.",
    "no_priced_ingredient": (
        "Van geen enkel ingrediënt is een prijs bekend, dus er valt niets te "
        "vergelijken."
    ),
    "no_discount_today": "Vandaag is er niets van dit recept in de aanbieding.",
}


def _load(engine):
    """Read the mart, distinguishing "not built yet" from "cannot reach"."""
    try:
        return read_recipe_opportunity(engine), None
    except ProgrammingError:
        return None, "unbuilt"
    except SQLAlchemyError as exc:
        return None, str(exc)


def _clearance_snapshot(df: pd.DataFrame) -> pd.Timestamp | None:
    if df.empty or "clearance_scraped_at" not in df:
        return None
    return freshness.to_local(
        pd.to_datetime(df["clearance_scraped_at"], utc=True).max()
    )


def _euro(value) -> str:
    return f"€{float(value):.2f}"


def _saving_phrase(row) -> str:
    """The sentence the page exists to say.

    "minstens" is the whole honesty mechanism in one word: it is what separates
    a saving computed over a complete basket from one computed over the part we
    could price.
    """
    amount = _euro(row["saving_total"])
    return (
        f"minstens {amount} goedkoper"
        if row["saving_is_lower_bound"]
        else (f"{amount} goedkoper")
    )


def _urgency(row) -> tuple[str, _BadgeColour] | None:
    """Why go now rather than later — or nothing, if there is no reason to."""
    if not int(row.get("items_discounted_clearance") or 0):
        return None
    expiry = row.get("earliest_expiry")
    stock = row.get("min_stock_remaining")
    unknown_stock = int(row.get("clearance_items_stock_unknown") or 0)

    if pd.notna(expiry):
        # Guarded by pd.notna above; the cast is what the guard proves.
        expiry_ts = cast("pd.Timestamp", pd.Timestamp(expiry))
        if expiry_ts.date() <= freshness.now().date():
            return ("Moet vandaag op", "red")
    if pd.notna(stock) and not unknown_stock:
        left = int(stock)
        if left <= 3:
            noun = "stuk" if left == 1 else "stuks"
            return (f"Nog {left} {noun}", "orange")
    return None


def _render_price(row) -> None:
    """Was, and is — as an exact pair when the basket is complete, and as an
    estimate when it is not.

    A withheld price used to be the rule here, on the grounds that a partial sum
    is not a total. For the *cost history* that still holds and has not moved:
    fct_recipe_cost_latest publishes nothing for an incomplete basket, because a
    series has to be comparable with itself.

    For this page it is the wrong trade. Most matches in the pool were proposed
    by a machine, so most baskets are incomplete, and a recipe with a rough
    price and one doubtful ingredient is more use than a recipe with no price at
    all. So the estimate is shown, marked as one, with how many ingredients it
    rests on and a way to correct any of them on the line itself.
    """
    complete = pd.notna(row.get("cost_today")) and pd.notna(row.get("cost_ordinary"))
    today = row.get("cost_today") if complete else row.get("partial_cost_today")
    ordinary = (
        row.get("cost_ordinary") if complete else row.get("partial_cost_ordinary")
    )
    if pd.isna(today) or pd.isna(ordinary):
        st.caption("Van geen enkel ingrediënt is de prijs bekend.")
        return

    with st.container(horizontal=True, vertical_alignment="bottom"):
        # "±" carries the whole caveat in one character, and it is never absent
        # when the basket is incomplete.
        st.markdown(f"### {'±' if not complete else ''}{_euro(today)}")
        if float(ordinary) > float(today):
            st.markdown(f":gray[normaal ~~{_euro(ordinary)}~~]")

    priced, total = int(row["items_priced"]), int(row["items_total"])
    if complete:
        per_serving = row.get("cost_today_per_serving")
        suffix = f" · {_euro(per_serving)} p.p." if pd.notna(per_serving) else ""
        st.caption(f"{int(row['servings'])} personen{suffix}")
    else:
        st.caption(
            f"Schatting over {priced} van {total} ingrediënten · "
            f"{int(row['servings'])} personen"
        )


def _render_lead(engine, row) -> None:
    """The best option, in full, with the ingredients responsible named."""
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            if row.get("image_url"):
                st.image(row["image_url"], width=96)
            with st.container():
                st.markdown(f"### {row['recipe_name']}")
                st.markdown(f"**{_saving_phrase(row)}** dan normaal")
                _render_rating(row)

        urgency = _urgency(row)
        if urgency:
            label, colour = urgency
            st.badge(label, color=colour, icon=":material/schedule:")

        _render_price(row)

        # Folded away by default. The answer to "what shall I cook" is the
        # recipe and its price; the ingredient list is what you open once you
        # have decided, and on a phone it would otherwise push everything else
        # off the screen.
        with st.expander(f"Ingrediënten ({int(row['items_total'])})", expanded=False):
            _render_items(engine, int(row["recipe_id"]), row)

        _render_verdict_controls(engine, row)


def _render_rating(row) -> None:
    """AH's readers' verdict, never without its weight."""
    average = row.get("rating_average")
    count = row.get("rating_count")
    if pd.isna(average) or average is None:
        return
    votes = int(count) if pd.notna(count) and count else 0
    if not votes:
        return
    st.caption(f"★ {float(average):.1f} · {votes} beoordelingen")


def _render_items(engine, recipe_id: int, row) -> None:
    """Every ingredient, not only the discounted ones.

    Showing only what got cheaper made an expander labelled "Ingrediënten (9)"
    render one line, which reads as broken rather than as selective. The list is
    the thing people open it for; the discount is an annotation on it.
    """
    items = read_recipe_opportunity_items(engine, recipe_id)
    if items.empty:
        st.caption("Voor dit recept zijn geen ingrediënten bekend.")
        return

    for _, item in items.iterrows():
        _render_item(engine, recipe_id, item)

    withheld = items[items["offer_withheld_stale_reference"]]
    if not withheld.empty:
        st.caption(
            f"{len(withheld)} aanbieding(en) niet meegeteld: de prijs waarmee we "
            "zouden vergelijken is te oud."
        )


def _render_item(engine, recipe_id: int, item) -> None:
    """One ingredient: what it costs, what it is matched to, and a way to say
    that match is wrong.

    The product name is shown on every line, not only the discounted ones,
    because most matches here were proposed by a machine and the only way to
    find a bad one is to be able to see it.
    """
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            label = str(item["item_label"])
            if item["is_discounted"] and pd.notna(item.get("item_saving")):
                st.markdown(f"**{label}** · :green[− {_euro(item['item_saving'])}]")
            else:
                st.markdown(label)

            if item["is_unresolved"]:
                st.caption("nog geen product gekoppeld")
            else:
                bits = [str(item.get("product_name") or "")]
                if pd.notna(item.get("price_today")):
                    price = _euro(item["price_today"])
                    if item["is_discounted"] and pd.notna(item.get("price_ordinary")):
                        price = f"{price} i.p.v. {_euro(item['price_ordinary'])}"
                    bits.append(price)
                pack = item.get("sales_unit_size")
                if pack and str(pack).strip():
                    # A recipe wanting 100 g of a 500 g pack is costed at the
                    # pack, because that is what has to be bought.
                    bits.append(f"hele verpakking: {pack}")
                st.caption(" · ".join(b for b in bits if b))

            if item.get("offer_kind") == "clearance" and pd.notna(item.get("stock")):
                st.badge(
                    f"laatste kans · nog {int(item['stock'])}",
                    color="orange",
                )
            if pd.notna(item.get("item_conditional_saving")):
                st.caption(
                    f"{item['conditional_mechanism']} — telt niet mee in het bedrag"
                )

        if pd.notna(item.get("concept_id")):
            with st.container(horizontal_alignment="right"):
                # Keyed on recipe AND line: item_key is "c:<concept_id>", so
                # two recipes both containing onions would otherwise produce the
                # same widget key and Streamlit raises on the duplicate.
                if st.button(
                    "Klopt niet",
                    key=f"fix_{recipe_id}_{item['item_key']}",
                    icon=":material/edit:",
                    help="Kies zelf het juiste product voor dit ingrediënt",
                ):
                    open_single(
                        engine, int(item["concept_id"]), str(item["item_label"])
                    )


def _render_brief(engine, row) -> None:
    """A runner-up: enough to choose by, not enough to compete with the lead.

    Same two prices and the same foldable ingredient list, because "how much is
    this one" is the question you ask of the alternatives too - but the whole
    card stays closed until asked, so the ranking still reads as a ranking.
    """
    with st.container(border=True):
        with st.container(horizontal=True, vertical_alignment="center"):
            if row.get("image_url"):
                st.image(row["image_url"], width=56)
            with st.container():
                st.markdown(f"**{row['recipe_name']}**")
                st.caption(_saving_phrase(row))
                _render_rating(row)
            urgency = _urgency(row)
            if urgency:
                with st.container(horizontal_alignment="right"):
                    st.badge(urgency[0], color=urgency[1])

        _render_price(row)

        with st.expander(f"Ingrediënten ({int(row['items_total'])})", expanded=False):
            _render_items(engine, int(row["recipe_id"]), row)

        _render_verdict_controls(engine, row)


def _render_verdict_controls(engine, row) -> None:
    """Keep it, or never see it again."""
    if row.get("source_kind") != "pool":
        return
    recipe_id = int(row["recipe_id"])
    with st.container(horizontal=True):
        if st.button(
            "Niet voor mij", key=f"reject_{recipe_id}", icon=":material/block:"
        ):
            reject_recipe(engine, recipe_id)
            st.rerun()
        if row.get("url"):
            st.link_button("Bekijk bij AH", row["url"])


def _render_rejected(engine) -> None:
    """What was dismissed, and the way back. A dismissal is not a trap."""
    rejected = read_rejected_recipes(engine)
    if rejected.empty:
        return
    with st.expander(f"Niet voor mij ({len(rejected)})"):
        for _, row in rejected.iterrows():
            with st.container(horizontal=True, vertical_alignment="center"):
                st.markdown(row["recipe_name"])
                with st.container(horizontal_alignment="right"):
                    if st.button(
                        "Terugzetten",
                        key=f"reinstate_{int(row['recipe_id'])}",
                        icon=":material/undo:",
                    ):
                        reinstate_recipe(engine, int(row["recipe_id"]))
                        st.rerun()


def _render_coverage(engine, df: pd.DataFrame) -> None:
    """How much the page can see, and the one action that widens it.

    The gap between the two numbers is the honest state of the system, and the
    button is what closes it. Resolutions are keyed on AH's ingredient concept,
    so confirming one counts for every recipe that uses it - which is why this
    is the action offered rather than "add more recipes".
    """
    pool = len(df)
    rankable = int(df["opportunity_rank"].notna().sum())
    unresolved = int((df["items_unresolved"] > 0).sum())

    st.caption(
        f"Berekend over {pool} recept(en); {rankable} daarvan zijn vandaag goedkoper."
    )
    if unresolved:
        st.caption(
            f"{unresolved} recept(en) missen nog een gekoppeld ingrediënt. "
            "Elk ingrediënt dat je koppelt telt meteen mee voor élk recept dat "
            "het gebruikt."
        )
        if st.button("Ingrediënten koppelen", icon=":material/link:"):
            open_review(engine)


def render_tonight() -> None:
    st.title("Vanavond")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    df, problem = _load(engine)
    if problem == "unbuilt":
        st.info(
            "De berekening is nog niet gedraaid. Start de job **recipe_pool_refresh** "
            "of **dbt_models** in Dagster."
        )
        return
    if problem:
        st.error(f"Geen verbinding met de database: {problem}")
        return

    if df is None or df.empty:
        st.info(
            "Er zijn nog geen recepten om mee te rekenen. Voeg er één toe op "
            "**Toevoegen**, dan verschijnt hier wat vandaag het voordeligst is."
        )
        return

    now = freshness.now()
    snapshot = _clearance_snapshot(df)
    clearance_current = freshness.is_current(snapshot, now)

    # Withdraw clearance rather than blanking the page. The bonus evidence is
    # national and week-scoped; it has not aged out just because the store scan
    # has, and at 09:00 you still want to know what to cook.
    if not clearance_current:
        df = df.assign(
            saving_total=df["saving_bonus_only"],
            cost_today=df["cost_today_bonus_only"],
            items_discounted_clearance=0,
        )
        df = df.assign(
            opportunity_rank=df["saving_total"]
            .where(df["saving_total"] > 0)
            .rank(ascending=False, method="min")
        )
        st.warning(
            f"De winkelscan is van {freshness.format_local(snapshot)} en dus niet "
            "van vandaag. De laatste kans-koopjes tellen daarom even niet mee; "
            "hieronder staat alleen wat er in de bonus is."
        )

    bonus_loaded = freshness.to_local(read_bonus_feed_loaded_at(engine))
    if bonus_loaded is not None:
        age_days = (now - bonus_loaded).days
        if age_days > _BONUS_FEED_STALE_DAYS:
            st.warning(
                f"De bonusfolder is {age_days} dagen niet ververst, dus dit "
                "beschrijft mogelijk niet deze week."
            )

    ranked = df[df["opportunity_rank"].notna()].sort_values("opportunity_rank")

    if ranked.empty:
        st.info(
            "Vandaag is geen van je recepten goedkoper dan normaal. Dat is een "
            "antwoord, geen storing."
        )
        _render_cheapest_anyway(df)
        _render_coverage(engine, df)
        _render_rejected(engine)
        return

    _render_lead(engine, ranked.iloc[0])
    if len(ranked) > 1:
        st.subheader("Ook de moeite waard")
        for _, row in ranked.iloc[1:6].iterrows():
            _render_brief(engine, row)

    _render_coverage(engine, df)
    _render_rejected(engine)


def _render_cheapest_anyway(df: pd.DataFrame) -> None:
    """Nothing is a bargain, so offer the next most useful thing.

    An empty page is a dead end. The cheapest fully priced recipe is still the
    answer to "what shall I cook", just for a different reason.
    """
    costed = df[df["cost_today"].notna()].sort_values("cost_today")
    if costed.empty:
        return
    row = costed.iloc[0]
    st.markdown("**Wel het voordeligst om te maken**")
    with st.container(border=True, horizontal=True, vertical_alignment="center"):
        if row.get("image_url"):
            st.image(row["image_url"], width=56)
        with st.container():
            st.markdown(f"**{row['recipe_name']}**")
            st.caption(
                f"{_euro(row['cost_today'])} · "
                f"{_euro(row['cost_today_per_serving'])} p.p."
            )
