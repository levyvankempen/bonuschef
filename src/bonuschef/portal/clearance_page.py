"""Laatste kans page — store-specific clearance (reduced-to-clear) items."""

import pandas as pd
import streamlit as st
from dagster import DagsterRunStatus
from sqlalchemy.exc import ProgrammingError

from bonuschef.portal.dagster_client import (
    MARKDOWNS_REFRESH_JOB,
    TERMINAL_STATUSES,
    DagsterTriggerError,
    get_run_progress,
    trigger_job,
)
from bonuschef.portal import freshness
from bonuschef.portal.accounts import SINGLE_USER, Account
from bonuschef.portal.db import (
    read_store_scrape_lag,
    store_for,
    store_name,
    get_engine,
    read_last_scrape_time,
    read_store_clearance,
)

_MARKDOWN_LABELS = {
    "EXPIRATION": "Bijna over datum",
    "OUT_OF_ASSORTMENT": "Uit het assortiment",
}
_LOCAL_TZ = freshness.LOCAL_TZ
_REFRESHED_KEY = "clearance_refreshed_at"
# The run being watched. An id survives a session reset; a pending wait does not.
_RUN_KEY = "clearance_refresh_run"
_FAILED_KEY = "clearance_refresh_failed"
# Two seconds: the job takes about twenty, so this is ten updates rather than
# a spinner that tells you nothing, and it stops the moment the run ends.
_POLL_SECONDS = 2
_SNAPSHOT_BEFORE_KEY = "clearance_snapshot_before"
_FIRST_SCRAPE_HOUR = freshness.FIRST_SCRAPE_HOUR


# Beyond this, the shop is being skipped rather than merely scraped in a
# different order within the hour.
_LAG_HOURS_WORTH_SAYING = 3.0


def _render_store_lag(engine, store_id: int) -> None:
    """Say when this shop is falling behind the others.

    The scrape fans out over every shop an account uses, and a shop that fails
    is a warning rather than a run failure - so a green run no longer means
    this shop was scraped. Nothing else on the page would say so.
    """
    try:
        lag = read_store_scrape_lag(engine, store_id)
    except ProgrammingError:
        return
    if lag is None or lag < _LAG_HOURS_WORTH_SAYING:
        return
    st.warning(
        f"Deze winkel is {int(lag)} uur geleden voor het laatst gescand, "
        "terwijl andere winkels sindsdien wel zijn bijgewerkt.",
        icon=":material/sync_problem:",
    )


def _load(engine, store_id: int) -> pd.DataFrame | None:
    """Read clearance data, returning None if the mart isn't built yet."""
    try:
        return read_store_clearance(engine, store_id)
    except ProgrammingError:  # relation does not exist → job never ran
        return None


def _latest_snapshot(df: pd.DataFrame) -> pd.Timestamp:
    """Most recent scrape time, converted to Dutch local time."""
    return pd.to_datetime(df["scraped_at"], utc=True).max().tz_convert(_LOCAL_TZ)


# These four were this page's own; a second page now needs the same judgement,
# and two pages deciding separately what "current" means is how two surfaces
# come to disagree about the same snapshot. The definitions live in
# portal.freshness; the names stay here so the page reads unchanged.
_now = freshness.now
_is_current = freshness.is_current
_describe_age = freshness.describe_age
_format_local = freshness.format_local


def _resolve_snapshot(last_scrape, df: pd.DataFrame) -> pd.Timestamp | None:
    """When the data on screen was captured, or None if that is unknowable.

    Prefers the scrape history, which is dated even when the scrape found
    nothing. Normalises NaT to None here so nothing downstream has to: pandas
    cannot strftime a NaT, and that was a live crash in the caption.
    """
    for candidate in (last_scrape, _latest_snapshot(df) if not df.empty else None):
        if candidate is not None and not pd.isna(candidate):
            return candidate
    return None


def _start_refresh(before: pd.Timestamp | None = None) -> None:
    """Ask Dagster to scrape, and return immediately.

    This used to block on wait_for_run behind a spinner, which failed three
    ways at once. It could not tell a queued run from a running one, so it said
    "de winkel wordt gescand" for three minutes while the run sat 44th in a
    queue. Backgrounding a phone tab drops Streamlit's websocket, so the session
    and its pending wait died together leaving no result and no error. And the
    caches were cleared only by the session that did the waiting.

    The run id is the state now. It is what survives a session reset; a pending
    network wait is precisely what does not.
    """
    try:
        run_id = trigger_job(MARKDOWNS_REFRESH_JOB)
    except DagsterTriggerError as exc:
        # Failing to *start* is synchronous and needs no run id.
        st.error(f"{exc}\n\nDraait de Dagster-webserver en is die bereikbaar?")
        return
    st.session_state[_RUN_KEY] = run_id
    # Kept so the banner can check the snapshot actually moved. A Dagster run
    # that succeeds having scraped nothing new is still a SUCCESS.
    st.session_state[_SNAPSHOT_BEFORE_KEY] = before
    st.rerun()


@st.fragment(run_every=_POLL_SECONDS)
def _render_refresh_progress() -> None:
    """Show how far the scrape has got, and keep showing it without being asked.

    A fragment rather than a full rerun: only this block re-executes every two
    seconds, so the page is not rebuilt underneath someone reading it, and the
    polling stops the moment the parent stops calling this.

    The phase comes from the run's own step stats. A bar advancing on elapsed
    time would be a decoration - and it would have read "almost done" through
    the three minutes a queued run once spent doing nothing whatsoever.
    """
    run_id = st.session_state.get(_RUN_KEY)
    if not run_id:
        return
    try:
        progress = get_run_progress(run_id)
    except DagsterTriggerError:
        # Losing sight of the run is not an error: the scrape either happened or
        # it did not, and the freshness caption reads the snapshot itself.
        st.session_state.pop(_RUN_KEY, None)
        return

    if progress.status not in TERMINAL_STATUSES:
        st.progress(progress.fraction, text=progress.label)
        return

    st.session_state.pop(_RUN_KEY, None)
    if progress.status == DagsterRunStatus.SUCCESS:
        # Cleared by whichever session observes completion, not by whichever one
        # waited. st.cache_data.clear() is global, which is the point: a phone
        # that slept through the run must not keep serving a stale mart.
        read_store_clearance.clear()
        read_last_scrape_time.clear()
        st.session_state[_REFRESHED_KEY] = _now()
    else:
        st.session_state.pop(_SNAPSHOT_BEFORE_KEY, None)
        st.session_state[_FAILED_KEY] = (str(run_id)[:8], progress.status.value)
    # scope="app": the whole page has to redraw, because the data behind it
    # changed. Without this only the fragment would update and the list would
    # still be the old one.
    st.rerun(scope="app")


def _render_refresh_failure() -> None:
    """Report a failed run once, after the rerun that cleared it."""
    failed = st.session_state.pop(_FAILED_KEY, None)
    if not failed:
        return
    run_id, status = failed
    st.error(
        f"Het ophalen is mislukt (run {run_id}, status {status}). "
        "Kijk in Dagster; meestal is het een verlopen AH-token."
    )


def _render_refresh_banner(latest: pd.Timestamp | None) -> None:
    """One-shot outcome banner. A green tick must mean the data actually moved.

    The job succeeding is not the same as the snapshot advancing: a scrape that
    returns nothing new still exits SUCCESS, and dbt still rebuilds the mart
    from unchanged rows. Claiming freshness we did not verify is worse than the
    staleness this page now guards against.
    """
    refreshed = st.session_state.pop(_REFRESHED_KEY, None)
    if refreshed is None:
        # Crucially without touching _SNAPSHOT_BEFORE_KEY. It is set when the
        # run starts and read when it finishes, which is several renders later;
        # popping it on every render destroyed the comparison and made every
        # refresh claim success, including ones that found nothing new.
        return
    before = st.session_state.pop(_SNAPSHOT_BEFORE_KEY, None)
    moved = before is None or (latest is not None and latest > before)
    if moved:
        st.success(f"Opgehaald om {refreshed:%H:%M}.")
    else:
        st.warning(
            f"Om {refreshed:%H:%M} is er opgehaald, maar de scan is nog steeds die van "
            f"{_format_local(before)} — er was niets nieuwers."
        )


def _render_refresh_control(account, caption: str, latest: pd.Timestamp | None) -> None:
    """Snapshot age caption plus a button to re-scrape on demand."""
    col_caption, col_button = st.columns([4, 1])
    with col_caption:
        st.caption(caption)
        _render_refresh_banner(latest)
        _render_refresh_failure()
        # Only while something is running: a fragment with run_every keeps
        # polling for as long as it is rendered.
        if st.session_state.get(_RUN_KEY):
            _render_refresh_progress()
    with col_button:
        # Operators only. The run queue holds one slot on purpose, and the
        # hourly clearance scrape is the thing it protects - a scrape missed
        # at 17:00 cannot be backfilled, because the shelf has been cleared by
        # 18:00. Four people pressing this during the evening window is a
        # self-inflicted outage on the one job that cannot wait.
        if not account.is_operator:
            st.caption(
                ":gray[Alleen de beheerder kan nu ophalen.]",
                help="De scan draait elk uur vanzelf.",
            )
            return
        clicked = st.button(
            "Nu ophalen",
            help=("Haal de koopjes van dit moment op. Duurt ongeveer een minuut."),
            width="stretch",
        )
    if clicked:
        _start_refresh(latest)


def _render_stale(
    item_count: int, latest: pd.Timestamp | None, now: pd.Timestamp
) -> None:
    """Say what the snapshot is, and deliberately show none of it.

    Two explanations, one gate. Before the day's first scrape the page is stale
    by construction every single morning — that is "not yet", not "broken", and
    a user at 09:00 can tell those apart only if the page does.
    """
    age = "van onbekende ouderdom" if latest is None else _describe_age(latest, now)
    if now.hour < _FIRST_SCRAPE_HOUR:
        st.info(
            f"De koopjes van vandaag zijn er nog niet — de eerste scan is om "
            f"{_FIRST_SCRAPE_HOUR}:00 uur. We tonen liever niets dan de "
            f"{item_count} artikelen van gisteren, die {age}."
        )
        return
    st.warning(
        f"Deze scan is {age} en niet van vandaag. Er stonden {item_count} "
        "artikelen in, die we niet tonen: prijzen en voorraad veranderen per uur, "
        "dus je zou voor niets naar de winkel gaan. Druk op **Nu ophalen**."
    )


def _render_summary(df: pd.DataFrame) -> None:
    """One line, not a metric row.

    "Matched to tracked" used to sit here — a join-coverage statistic about the
    pipeline, shown to someone deciding what to buy.
    """
    headline = f"### {len(df)} koopjes"
    if df["markdown_percentage"].notna().any():
        headline += f" · tot −{df['markdown_percentage'].max():.0f}%"
    st.markdown(headline)


def _expiry_note(value, today) -> str | None:
    """Days until the item must be eaten, which is half the decision."""
    if value is None or pd.isna(value):
        return None
    expires = pd.to_datetime(value, errors="coerce")
    if pd.isna(expires):
        return None
    days = (expires.date() - today).days
    if days <= 0:
        return "THT vandaag"
    return f"THT over {days} dag" + ("en" if days != 1 else "")


def _render_items(df: pd.DataFrame, today) -> None:
    """One card per item.

    This was a ten-column dataframe: a spreadsheet widget with sort arrows, a
    resize handle and a horizontal scrollbar, for a shopping list read on a
    phone while standing in the shop. The product image was already being
    queried and then thrown away.
    """
    for _, row in df.iterrows():
        with st.container(border=True, horizontal=True, vertical_alignment="center"):
            if row.get("image_url") and not pd.isna(row["image_url"]):
                st.image(row["image_url"], width=64)
            with st.container():
                st.markdown(f"**{row['product_name']}**")
                detail = " · ".join(
                    str(part)
                    for part in (row.get("brand"), row.get("sales_unit_size"))
                    if part and not pd.isna(part)
                )
                if detail:
                    st.caption(detail)
                # Urgency before anything else: low stock and a same-day expiry
                # are what make an item worth acting on now rather than later.
                if row.get("stock") is not None and not pd.isna(row["stock"]):
                    if row["stock"] <= 3:
                        st.badge(
                            f"nog {int(row['stock'])}",
                            color="orange",
                            icon=":material/inventory_2:",
                        )
                note = _expiry_note(row.get("markdown_expiration_date"), today)
                if note:
                    st.badge(note, color="orange")
                reason = _MARKDOWN_LABELS.get(row.get("markdown_type"))
                if reason:
                    st.caption(reason)
            with st.container(horizontal_alignment="right"):
                st.markdown(f"### €{row['price_now']:.2f}")
                if row.get("price_was") and not pd.isna(row["price_was"]):
                    was = f"~~€{row['price_was']:.2f}~~"
                    if not pd.isna(row.get("markdown_percentage")):
                        was += f"  −{row['markdown_percentage']:.0f}%"
                    st.caption(was)


def render_clearance(account: Account | None = None) -> None:
    """Render the Laatste kans (store clearance) page."""
    account = account or SINGLE_USER
    st.title("Laatste kans koopjes")

    try:
        engine = get_engine()
        store_id = store_for(account)
        # Named, not implied. "jouw Albert Heijn" was an unverifiable claim:
        # somebody who picked the wrong shop out of 1,199 had nothing on the
        # page that would tell them.
        shop = store_name(engine, store_id)
        st.caption(
            f"Afgeprijsde artikelen in {shop or 'jouw Albert Heijn'}. Kortingen "
            "lopen door de dag op en de voorraad is snel weg."
        )
        _render_store_lag(engine, store_id)
        df = _load(engine, store_id)
        last_scrape = (
            read_last_scrape_time(engine, store_id) if df is not None else None
        )
    except Exception as exc:
        st.error(f"Geen verbinding met de database: {exc}")
        return

    if df is None:
        st.info("Nog geen koopjes opgehaald. Druk op **Nu ophalen**.")
        _render_refresh_control(account, "Er is nog nooit een scan gedaan.", None)
        return

    now = _now()
    latest = _resolve_snapshot(last_scrape, df)

    if latest is None or not _is_current(latest, now):
        _render_refresh_control(account, f"Gescand om {_format_local(latest)}.", latest)
        _render_stale(len(df), latest, now)
        return

    _render_refresh_control(
        account,
        f"Gescand om {_format_local(latest)} · {_describe_age(latest, now)}.",
        latest,
    )

    if df.empty:
        st.info("Geen koopjes in de laatste scan.")
        return

    _render_summary(df)

    categories = sorted(c for c in df["category_title"].dropna().unique())
    chosen = st.multiselect("Filter op categorie", categories, default=[])
    if chosen:
        df = df[df["category_title"].isin(chosen)]

    _render_items(df, now.date())
