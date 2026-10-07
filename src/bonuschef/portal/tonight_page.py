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

from bonuschef.portal import freshness, offers
from bonuschef.portal.ui import (
    BadgeColour,
    OfferLine,
    bigger_image,
    inject_card_styles,
    render_recipe_card,
)
from bonuschef.portal.review import (
    open_review,
    open_single,
    render_rebuild_status,
    render_resolution_result,
)
from bonuschef.portal.accounts import SINGLE_USER, Account
from bonuschef.portal.db import (
    active_store_id,
    count_flagged_concepts,
    CREDENTIAL_JOB,
    get_engine,
    read_bonus_feed_loaded_at,
    read_discounted_ingredients,
    read_driving_ingredients,
    read_pipeline_health,
    read_marts_built_at,
    is_kept,
    keep_recipe,
    read_recipe_opportunity,
    read_recipe_opportunity_items,
    read_recipes_using_ingredient,
    read_rejected_recipe_ids,
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
        # The build stamp is the cache key: a rebuild invalidates this read
        # exactly, and a run that changed nothing costs nothing.
        return (
            read_recipe_opportunity(
                engine, active_store_id(), read_marts_built_at(engine)
            ),
            None,
        )
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
    # offers.euro, so the Recepten page cannot format a price differently.
    return offers.euro(value)


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


def _offer_badges(
    engine, recipe_id: int, row, clearance_counts: bool, limit: int = 3
) -> tuple[list[OfferLine], int]:
    """Which ingredients make this recipe cheap, by name.

    The card used to say "2x bonus", which is a count. The person is standing in
    front of one particular discounted thing and the noun is the whole answer.

    The reader is already ordered by saving, so the named ones are the largest
    and the remainder can be a count without burying the biggest number. Nothing
    extra is fetched: this is the same query the ingredient list uses, and it is
    cached per recipe and build.
    """
    if not int(row.get("items_discounted") or 0):
        return [], 0
    items = read_recipe_opportunity_items(
        engine, recipe_id, active_store_id(), read_marts_built_at(engine)
    )
    if items.empty:
        return [], 0

    saving_column = "item_saving" if clearance_counts else "item_saving_bonus_only"
    discounted = items[items["is_discounted"] & items[saving_column].notna()]
    discounted = discounted[discounted[saving_column].astype(float) > 0]
    if discounted.empty:
        return [], 0

    price_column = "price_today" if clearance_counts else "price_today_bonus_only"
    named: list[OfferLine] = []
    for _, item in discounted.head(limit).iterrows():
        # A clearance line is orange and a promotion green, matching the
        # vocabulary the ingredient list below already uses.
        colour: BadgeColour = (
            "orange" if item.get("offer_kind") == "clearance" else "green"
        )
        named.append(
            OfferLine(
                label=str(item["item_label"]),
                saving=f"− {_euro(item[saving_column])}",
                colour=colour,
                # The two numbers on the shelf. Same row the saving came from,
                # so nothing extra is fetched to show them.
                prices=offers.was_now(
                    item.get(price_column), item.get("price_ordinary")
                ),
                reference_note=_reference_note(item.get("ordinary_price_age_days")),
            )
        )
    return named, max(len(discounted) - len(named), 0)


# A "was" price older than this is reported with its age. Chosen to be short:
# the comparison is to what the shop charged recently, and a week-old reference
# is a different claim from a yesterday-old one.
_REFERENCE_FRESH_DAYS = 3


def _reference_note(age_days) -> str:
    """Say how old the ordinary price is, when it is old enough to matter.

    ordinary_price_age_days has been selected by the reader all along and
    rendered nowhere. The difference between a trustworthy "was" price and a
    decorative one is exactly this number, and the page already withholds a
    saving outright when the reference is too stale to compare against - this is
    the same honesty one notch earlier.
    """
    if age_days is None or pd.isna(age_days):
        return ""
    days = int(age_days)
    if days <= _REFERENCE_FRESH_DAYS:
        return ""
    return f"normale prijs van {days} dagen geleden"


@st.fragment
def _render_items_on_request(
    engine, recipe_id: int, row, clearance_counts: bool, account=None
) -> None:
    """The ingredient list, and nothing at all until it is asked for.

    This was an st.expander. Streamlit executes an expander's body whether or
    not it is open, so a single render of this page issued a query per card and
    registered a "Klopt niet" button per ingredient - roughly fifty controls
    streamed over a shop connection to show six recipes.

    A fragment, and with no st.rerun() in it, because the first version of this
    had both problems: st.rerun() re-runs the whole page, the page gets taller
    by the length of the list, and the browser lands somewhere other than where
    the thumb was. Opening a list is not a reason to move the page. A fragment
    re-runs only this block, and the toggle takes effect in the same run, so
    there is nothing to scroll.
    """
    total = int(row["items_total"])
    open_key = f"items_open_{recipe_id}"
    opened = bool(st.session_state.get(open_key))

    if st.button(
        "Verbergen" if opened else f"Ingrediënten ({total})",
        key=f"items_toggle_{recipe_id}",
        icon=":material/expand_less:" if opened else ":material/list:",
        width="stretch",
    ):
        opened = not opened
        st.session_state[open_key] = opened

    if opened:
        _render_items(engine, recipe_id, row, clearance_counts, account)


def _render_lead(engine, account, row, clearance_counts: bool = True) -> None:
    """The best option, in full, with the ingredients responsible named."""
    recipe_id = int(row["recipe_id"])
    offers_named, more = _offer_badges(engine, recipe_id, row, clearance_counts)
    render_recipe_card(
        key=f"lead-{recipe_id}",
        title=str(row["recipe_name"]),
        image_url=bigger_image(row.get("image_url")),
        saving=f"{_saving_phrase(row)} dan normaal",
        lead=True,
        urgency=_urgency(row),
        offers=offers_named,
        more_offers=more,
        price=lambda: _render_price(row),
        rating=lambda: _render_rating(row),
        extra=lambda: _render_items_on_request(
            engine, recipe_id, row, clearance_counts, account
        ),
        actions=lambda: _render_verdict_controls(engine, account, row),
    )


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


def _render_items(
    engine, recipe_id: int, row, clearance_counts: bool = True, account=None
) -> None:
    """Every ingredient, not only the discounted ones.

    Showing only what got cheaper made an expander labelled "Ingrediënten (9)"
    render one line, which reads as broken rather than as selective. The list is
    the thing people open it for; the discount is an annotation on it.
    """
    items = read_recipe_opportunity_items(
        engine, recipe_id, active_store_id(), read_marts_built_at(engine)
    )
    if items.empty:
        st.caption("Voor dit recept zijn geen ingrediënten bekend.")
        return

    for _, item in items.iterrows():
        _render_item(engine, recipe_id, item, clearance_counts, account)

    withheld = items[items["offer_withheld_stale_reference"]]
    if not withheld.empty:
        st.caption(
            f"{len(withheld)} aanbieding(en) niet meegeteld: de prijs waarmee we "
            "zouden vergelijken is te oud."
        )


def _render_item(
    engine, recipe_id: int, item, clearance_counts: bool = True, account=None
) -> None:
    """One ingredient: what it costs, what it is matched to, and a way to say
    that match is wrong.

    The product name is shown on every line, not only the discounted ones,
    because most matches here were proposed by a machine and the only way to
    find a bad one is to be able to see it.
    """
    with st.container(horizontal=True, vertical_alignment="center"):
        with st.container():
            # With clearance withdrawn, a line's saving and price are its
            # bonus-only ones - otherwise the list contradicts the banner
            # above it.
            saving = item.get(
                "item_saving" if clearance_counts else "item_saving_bonus_only"
            )
            shown_price = item.get(
                "price_today" if clearance_counts else "price_today_bonus_only"
            )
            discounted = bool(item["is_discounted"]) and (
                clearance_counts or (pd.notna(saving) and float(saving) > 0)
            )

            label = str(item["item_label"])
            if discounted and pd.notna(saving) and float(saving) > 0:
                st.markdown(f"**{label}** · :green[− {_euro(saving)}]")
            else:
                st.markdown(label)

            if item["is_unresolved"]:
                st.caption("nog geen product gekoppeld")
            else:
                bits = [str(item.get("product_name") or "")]
                if pd.notna(shown_price):
                    price = _euro(shown_price)
                    if discounted and pd.notna(item.get("price_ordinary")):
                        price = f"{price} i.p.v. {_euro(item['price_ordinary'])}"
                    bits.append(price)
                pack = item.get("sales_unit_size")
                if pack and str(pack).strip():
                    # A recipe wanting 100 g of a 500 g pack is costed at the
                    # pack, because that is what has to be bought.
                    bits.append(f"hele verpakking: {pack}")
                st.caption(" · ".join(b for b in bits if b))

            # No "laatste kans" badge when the scan it came from is not
            # today's - and none when the markdown is not actually cheaper.
            #
            # The badge used to need only a clearance offer and a known stock,
            # so it announced urgency on a line whose price had not moved: 116
            # of 463 clearance lines, and on 103 of them the sticker price was
            # DEARER than the price we track. "laatste kans · nog 2" beside an
            # unchanged EUR 1,09 reads as a discount somebody forgot to apply,
            # when in truth the mart looked at the markdown and correctly
            # declined to call it one.
            #
            # Urgency is a reason to act now. Without a saving there is no
            # reason, so the badge goes and the discrepancy is said instead -
            # which is what the portal is required to do wherever a retailer's
            # advertised saving does not survive comparison with observed
            # prices.
            if clearance_counts and item.get("offer_kind") == "clearance":
                if discounted and pd.notna(item.get("stock")):
                    st.badge(
                        f"laatste kans · nog {int(item['stock'])}",
                        color="orange",
                    )
                elif not discounted:
                    _render_offer_that_is_not_cheaper(item)
            elif item.get("offer_kind") == "bonus" and not discounted:
                # The commoner case, and the one the sixteen live examples are:
                # a promotion that does not beat the price we last observed.
                _render_offer_that_is_not_cheaper(item)
            if pd.notna(item.get("item_conditional_saving")):
                st.caption(
                    f"{item['conditional_mechanism']} — telt niet mee in het bedrag"
                )

        # Offered to an operator only. The correction applies to every account,
        # so a non-operator would be shown a control that is refused.
        if pd.notna(item.get("concept_id")) and getattr(account, "is_operator", False):
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
                        engine,
                        int(item["concept_id"]),
                        str(item["item_label"]),
                        account,
                    )


def _render_offer_that_is_not_cheaper(item) -> None:
    """Say that an offer on this product is not a saving, where the price is.

    The wording follows the kind of offer, because the two arise for different
    reasons and the first version of this got it wrong by calling both a
    markdown.

    A *clearance* price is cheaper than its own product's shelf price by
    definition, so a markdown that looks dearer means our reference is out of
    date rather than that the sticker is bad - only four products in the whole
    offer table are in that state, and the tracked price behind them may be up
    to the staleness window old.

    A *bonus* has no such guarantee: a promotion can simply not beat the price
    we last observed, which is every one of the sixteen cases that reach a
    recipe line. Naming it "afgeprijsd" would be wrong twice over.
    """
    offer = item.get("offer_price")
    ordinary = item.get("price_ordinary")
    clearance = item.get("offer_kind") == "clearance"
    noun = "afgeprijsd op" if clearance else "in de bonus voor"

    if pd.isna(offer):
        st.caption(f":gray[{noun} een prijs die niet lager is dan normaal]")
        return
    if pd.notna(ordinary) and float(offer) > float(ordinary):
        tail = (
            "onze prijs is mogelijk verouderd"
            if clearance
            else f"hoger dan de {_euro(ordinary)} die we voor dit product zien"
        )
        st.caption(f":gray[{noun} {_euro(offer)} — {tail}]")
        return
    st.caption(f":gray[{noun} {_euro(offer)} — geen voordeel tegenover normaal]")


def _render_brief(engine, account, row, clearance_counts: bool = True) -> None:
    """A runner-up: enough to choose by, not enough to compete with the lead.

    Same picture at the same width as the lead. The difference is type scale and
    how much the card carries - a runner-up rendered at 56 pixels was not a
    smaller card, it was an unrecognisable one.
    """
    recipe_id = int(row["recipe_id"])
    offers_named, more = _offer_badges(
        engine, recipe_id, row, clearance_counts, limit=1
    )
    render_recipe_card(
        key=f"brief-{recipe_id}",
        title=str(row["recipe_name"]),
        image_url=bigger_image(row.get("image_url")),
        saving=_saving_phrase(row),
        lead=False,
        urgency=_urgency(row),
        offers=offers_named,
        more_offers=more,
        price=lambda: _render_price(row),
        extra=lambda: _render_items_on_request(
            engine, recipe_id, row, clearance_counts, account
        ),
        actions=lambda: _render_verdict_controls(engine, account, row),
    )


def _render_verdict_controls(engine, account, row) -> None:
    """Keep it, or never see it again."""
    if row.get("source_kind") != "pool":
        return
    recipe_id = int(row["recipe_id"])
    # Said before the click rather than only in the toast after it. is_kept
    # has existed since keeping did and was called by nothing, so the page
    # offered "Bewaren" on a recipe already in your collection and only
    # admitted it once you pressed.
    if is_kept(engine, account.account_id, recipe_id):
        with st.container(horizontal=True):
            st.badge("Bewaard", color="green", icon=":material/bookmark_added:")
        return

    with st.container(horizontal=True):
        # Keeping was the missing half. The page could reject a recipe and not
        # hold on to one, so a recommendation a person liked was gone at the
        # next pool refresh - which replaces the pool wholesale every Monday.
        if st.button(
            "Bewaren",
            key=f"keep_{recipe_id}",
            icon=":material/bookmark_add:",
            help="Zet dit recept bij je eigen recepten, zodat het blijft staan",
        ):
            # Say what happened. A kept recipe looks identical on this page
            # until the next pool refresh would have removed it, so without
            # this the click reads as having done nothing.
            if keep_recipe(engine, account.account_id, recipe_id):
                st.toast(
                    "Bewaard bij je eigen recepten", icon=":material/bookmark_added:"
                )
            else:
                st.toast("Stond al bij je eigen recepten", icon=":material/check:")
            st.rerun()
        if st.button(
            "Niet voor mij", key=f"reject_{recipe_id}", icon=":material/block:"
        ):
            reject_recipe(engine, account.account_id, recipe_id)
            st.rerun()
        if row.get("url"):
            st.link_button("Bekijk bij AH", row["url"])


def _render_rejected(engine, account) -> None:
    """What was dismissed, and the way back. A dismissal is not a trap."""
    rejected = read_rejected_recipes(engine, account.account_id)
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
                        reinstate_recipe(
                            engine, account.account_id, int(row["recipe_id"])
                        )
                        st.rerun()


def _render_coverage(engine, df: pd.DataFrame, account=None) -> None:
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

    # Why the rest are not here.
    #
    # The mart has always computed exclusion_reason, the reader has always
    # selected it, and _EXCLUSION_TEXT has always held the three values it can
    # take - and nothing rendered any of it. "Berekend over 900 recepten; 200
    # daarvan zijn vandaag goedkoper" invites exactly one question, and the
    # answer was sitting in the dataframe unread.
    #
    # It distinguishes the two states the caption above conflates: a recipe
    # that COULD be ranked and simply is not cheaper today, and one that could
    # not be ranked at all because nothing in it has a price.
    if "exclusion_reason" in df.columns:
        reasons = df["exclusion_reason"].dropna()
        if not reasons.empty:
            counts = reasons.value_counts()
            parts = [
                f"{int(n)}× {_EXCLUSION_TEXT[reason].rstrip('.').lower()}"
                for reason, n in counts.items()
                if reason in _EXCLUSION_TEXT
            ]
            if parts:
                st.caption("Niet meegerekend: " + "; ".join(parts) + ".")
    # Flagged concepts are a different kind of work from unlinked ones: the
    # recipe already has a price, it is just wrong. That reads as nothing being
    # amiss, so it has to be said out loud or it never gets looked at.
    flagged = count_flagged_concepts(engine)
    if flagged:
        st.warning(
            f"{flagged} ingrediënt(en) zijn aan een product gekoppeld dat er "
            "waarschijnlijk niet bij hoort. Die recepten hebben nu een prijs "
            "die niet klopt.",
            icon=":material/report:",
        )
    if unresolved:
        st.caption(
            f"{unresolved} recept(en) missen nog een gekoppeld ingrediënt. "
            "Elk ingrediënt dat je koppelt telt meteen mee voor élk recept dat "
            "het gebruikt."
        )
    if unresolved or flagged:
        label = "Ingrediënten nakijken" if flagged else "Ingrediënten koppelen"
        if st.button(label, icon=":material/link:"):
            open_review(engine, account)


def _render_pipeline_health(engine, credential_only: bool = False) -> None:
    """Say when the work behind the page has stopped, and nothing otherwise.

    This is the only surface on which a failure can be noticed: alerting is
    deliberately unsubscribed, and the failures that matter most emit no event
    to alert on anyway - a run never launched, a sensor tick that threw, a
    schedule that stopped evaluating.

    Nothing renders while everything is succeeding. A health indicator that is
    always present is furniture, and furniture stops being read.
    """
    health = read_pipeline_health(engine)
    if health.empty:
        return
    overdue = health[health["is_overdue"]]
    if overdue.empty:
        return

    # The credential first and separately: every other failure recovers by
    # re-running a job, and this one needs a browser behind hCaptcha.
    credential = overdue[overdue["job_name"] == CREDENTIAL_JOB]
    if not credential.empty:
        row = credential.iloc[0]
        when = (
            "nog nooit"
            if pd.isna(row["last_success"])
            else f"{int(row['overdue_h'])} uur geleden"
        )
        st.error(
            f"De AH-inlog is {when} voor het laatst ververst. Zonder dat "
            "verloopt hij, en herstellen kan alleen met een browser.",
            icon=":material/key_off:",
        )

    # The credential is the half that changes what you should buy - it means
    # prices may be wrong - so it stays above the answer. Job names and overdue
    # hours are addressed to an operator and belong below it, which is what the
    # portal spec already requires of every page.
    if credential_only:
        return

    rest = overdue[overdue["job_name"] != CREDENTIAL_JOB]
    for _, row in rest.iterrows():
        when = (
            "nog nooit gelukt"
            if pd.isna(row["last_success"])
            else f"{int(row['overdue_h'])} uur geleden voor het laatst gelukt"
        )
        st.warning(
            f"**{row['job_name']}** is {when} — {row['what']} is mogelijk niet "
            "bijgewerkt.",
            icon=":material/sync_problem:",
        )


_SEARCH_KEY = "tonight_ingredient"
_PILL_KEY = "tonight_ingredient_pill"


def _pill_labels(discounted: pd.DataFrame) -> dict[str, str]:
    """What each pill reads, mapped to what the filter needs.

    The label carries its count because that is what makes the row a table of
    contents rather than a list of words; the filter needs the bare label. Kept
    as a mapping rather than parsed back apart, so an ingredient whose own name
    ends in a bracketed number cannot be mangled.

    Pulled out of the widget because AppTest cannot drive a single-select
    st.pills - set_value iterates the string and select passes None - which is
    the same limitation this repo already recorded for st.segmented_control. The
    mapping is the part worth testing, so it is testable without the widget.
    """
    shown: dict[str, str] = {}
    for _, row in discounted.iterrows():
        label = str(row["item_label"])
        count = int(row.get("recipes") or 0)
        shown[f"{label} ({count})" if count else label] = label
    return shown


def _ingredient_filter(engine) -> str:
    """Let a person start from an ingredient, preferably without typing.

    This is the page's table of contents, not a search box. "These nineteen
    things are cheap today, with how many recipes each" is the answer to the
    question actually asked in a shop - "this is on offer, what do I cook with
    it" - and it costs one tap.

    The counts were already being fetched and thrown away. read_discounted_
    ingredients groups ranked recipes per ingredient and orders by how many use
    each, precisely so the most useful choices come first; only the labels were
    read.

    The text field is behind a popover. Its own reader's note argues that typing
    one-handed in a shop "is the interaction being removed", and that free text
    over the other 1,854 labels "mostly answers nothing on offer with that" -
    and then the page shipped it as a peer of the pills, where it won by being
    lower and larger. Recepten already owns search by name.
    """
    store_id = active_store_id()
    built_at = read_marts_built_at(engine)
    try:
        discounted = read_discounted_ingredients(engine, store_id, built_at)
    except (ProgrammingError, SQLAlchemyError):
        discounted = pd.DataFrame()

    chosen = ""
    if not discounted.empty:
        shown = _pill_labels(discounted)
        picked = st.pills(
            "Vandaag in de aanbieding",
            list(shown),
            selection_mode="single",
            key=_PILL_KEY,
        )
        if picked:
            chosen = shown.get(str(picked), str(picked))

    with st.popover("Zoek zelf", icon=":material/search:"):
        typed = st.text_input(
            "Zoek op ingrediënt",
            key=_SEARCH_KEY,
            placeholder="kip, courgette, zalm…",
        )
    # A typed term wins: it is the more deliberate of the two.
    return (typed or chosen or "").strip()


def _apply_ingredient_filter(engine, df: pd.DataFrame, term: str) -> pd.DataFrame:
    """Narrow to recipes using the ingredient, keeping the order they had."""
    if not term:
        return df
    try:
        ids = read_recipes_using_ingredient(
            engine, active_store_id(), term, read_marts_built_at(engine)
        )
    except (ProgrammingError, SQLAlchemyError):
        return df
    return df[df["recipe_id"].astype(int).isin(ids)]


def render_tonight(account: Account | None = None) -> None:
    st.title("Vanavond")
    inject_card_styles()

    # Before anything else: what a just-finished correction did, and how the
    # recalculation it started is getting on. Confirming used to be silent, and
    # a silent save is indistinguishable from one that did not happen.
    render_resolution_result()
    render_rebuild_status()

    try:
        # SINGLE_USER when there is no wall: every reader below takes an
        # account, and giving them a real one keeps the two modes on one path
        # rather than two.
        account = account or SINGLE_USER
        engine = get_engine()
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    # Only the half that changes what you should buy. The job names and overdue
    # hours follow the answer rather than preceding it.
    _render_pipeline_health(engine, credential_only=True)

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

    # The withdrawal lives in offers.py, because the Recepten page needs the
    # same judgement and two pages deciding for themselves what "current"
    # means is how two surfaces come to disagree about one snapshot.
    df, stale_notice = offers.withdraw_stale_clearance(df, now=now)
    if stale_notice:
        st.warning(stale_notice)

    bonus_loaded = freshness.to_local(read_bonus_feed_loaded_at(engine))
    if bonus_loaded is not None:
        age_days = (now - bonus_loaded).days
        if age_days > _BONUS_FEED_STALE_DAYS:
            st.warning(
                f"De bonusfolder is {age_days} dagen niet ververst, dus dit "
                "beschrijft mogelijk niet deze week."
            )

    _render_ingredient_answer(engine, account, df, clearance_current)

    # Below the answer, where an operator's measures belong.
    _render_pipeline_health(engine)
    _render_coverage(engine, df, account)
    _render_rejected(engine, account)


@st.fragment
def _render_ingredient_answer(
    engine, account, df: pd.DataFrame, clearance_current: bool
) -> None:
    """The filter and the recipes it filters, as one independently rerunning
    piece.

    The controls have to live inside the fragment with the list: a widget
    outside it reruns the whole script, which would rebuild the banners, the
    coverage block and the rejected list to answer "show me the chicken ones" -
    on the connection least able to afford it.
    """
    term = _ingredient_filter(engine)
    _render_answer(engine, account, df, term, clearance_current)


_SHORTLIST = 6


def _choose_shortlist(
    ranked: pd.DataFrame, drivers: dict[int, str], want: int = _SHORTLIST
) -> tuple[pd.DataFrame, dict[str, int]]:
    """The alternatives, chosen for being different answers.

    Ordering by saving alone does not rank recipes. Every ranked recipe owes its
    saving to exactly one discounted ingredient, so the sum is a property of the
    product: every recipe containing one particular bacon scores the same
    EUR 2.00, ties break on recipe_id, and the bacon therefore runs contiguously
    down the page. Measured on one shop: of the top twenty, eleven were the same
    salmon and five were bacon. Six cards carried one fact.

    So: walk the ranking in order and take the first recipe for each ingredient
    not yet represented. If that leaves too few - some days only two ingredients
    are discounted - fill up from the largest groups, still in rank order,
    rather than showing a two-card page.

    Soft rather than hard, because hard fails at both ends: one-per-ingredient
    means a nineteen-card page on a good day and a two-card one on a thin day.

    Returns the chosen rows and how many were passed over per ingredient, which
    is what "Meer met zalm (11)" needs and what the page must disclose.
    """
    seen: set[str] = set()
    chosen: list[int] = []
    passed_over: dict[str, int] = {}

    for position, recipe_id in enumerate(ranked["recipe_id"].astype(int)):
        label = drivers.get(recipe_id, "")
        if label in seen:
            passed_over[label] = passed_over.get(label, 0) + 1
            continue
        seen.add(label)
        chosen.append(position)

    if len(chosen) < want:
        # Too few distinct ingredients today. Fill from what was passed over,
        # keeping rank order, so a thin day is still a full page.
        for position, recipe_id in enumerate(ranked["recipe_id"].astype(int)):
            if len(chosen) >= want:
                break
            if position not in chosen:
                chosen.append(position)
                label = drivers.get(recipe_id, "")
                if passed_over.get(label):
                    passed_over[label] -= 1
        chosen.sort()

    return ranked.iloc[chosen[:want]], {k: v for k, v in passed_over.items() if v > 0}


def _render_answer(
    engine, account, df: pd.DataFrame, term: str, clearance_current: bool
) -> None:
    """The recipes themselves, filtered by ingredient if one was named."""
    ranked = df[df["opportunity_rank"].notna()].sort_values("opportunity_rank")

    # "Niet voor mij" wrote a row and changed nothing here.
    #
    # The exclusion used to live in int_pool_recipes_available and was removed
    # when accounts arrived, because it was global - one person dismissing a
    # recipe hid it from everybody. The note there says it "moved to the portal,
    # which knows who is asking", and read_rejected_recipe_ids' sibling was
    # written for exactly this call. Nothing ever made it. So a dismissal
    # produced an entry in the "Niet voor mij" list and the recipe came straight
    # back on the next render, which the spec forbids in as many words: it
    # leaves the ranking immediately and does not return.
    try:
        dismissed = read_rejected_recipe_ids(engine, account.account_id)
    except (ProgrammingError, SQLAlchemyError):
        dismissed = set()
    if dismissed:
        ranked = ranked[~ranked["recipe_id"].astype(int).isin(dismissed)]
    matching = _apply_ingredient_filter(engine, ranked, term)

    if term and matching.empty:
        # Answer in terms of the ingredient rather than showing an empty page,
        # and still offer the cheapest recipe that uses it.
        st.info(f"Geen recept met **{term}** onder de aanbiedingen van vandaag.")
        _render_cheapest_anyway(_apply_ingredient_filter(engine, df, term))
        return

    if matching.empty:
        st.info(
            "Vandaag is geen van je recepten goedkoper dan normaal. Dat is een "
            "antwoord, geen storing."
        )
        _render_cheapest_anyway(df)
        return

    try:
        drivers_frame = read_driving_ingredients(
            engine, active_store_id(), read_marts_built_at(engine)
        )
        drivers = {
            int(r["recipe_id"]): str(r["item_label"])
            for _, r in drivers_frame.iterrows()
        }
    except (ProgrammingError, SQLAlchemyError):
        # Without the drivers the page cannot choose for difference, so it falls
        # back to the ranking as it stands rather than to nothing.
        drivers = {}

    shortlist, passed_over = _choose_shortlist(matching, drivers)

    _render_lead(engine, account, shortlist.iloc[0], clearance_current)
    if len(shortlist) > 1:
        st.subheader("Ook de moeite waard")
        for _, row in shortlist.iloc[1:].iterrows():
            _render_brief(engine, account, row, clearance_current)

    _render_shortlist_note(len(matching), len(shortlist), passed_over)


def _render_shortlist_note(
    ranked: int, shown: int, passed_over: dict[str, int]
) -> None:
    """Say what is not on the page, and offer the way to it.

    The coverage caption below says how many recipes were ranked. Beside a
    shorter list that becomes a misrepresentation of the page's own selection,
    which the honesty requirement does not allow - so the moment the shortlist
    is narrower than the ranking, it has to say so and why.

    The drill-down sets the pill that already exists rather than adding a second
    control. The page had two ways to filter by ingredient once before, and the
    pills lost to the text box; it is not getting a third.
    """
    if shown >= ranked:
        return

    st.caption(
        f"{ranked} recepten zijn vandaag goedkoper; hierboven staan {shown}, "
        "één per aanbieding."
    )
    if not passed_over:
        return

    with st.container(horizontal=True):
        for label, count in sorted(
            passed_over.items(), key=lambda kv: kv[1], reverse=True
        )[:4]:
            if st.button(
                f"Meer met {label} ({count})",
                key=f"more_{label}",
                icon=":material/expand_more:",
            ):
                st.session_state[_SEARCH_KEY] = label
                st.rerun(scope="fragment")


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
