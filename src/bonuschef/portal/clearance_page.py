"""Laatste kans page — store-specific clearance (reduced-to-clear) items."""

from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st
from dagster import DagsterRunStatus
from sqlalchemy.exc import ProgrammingError

from bonuschef.portal.dagster_client import (
    MARKDOWNS_REFRESH_JOB,
    DagsterTriggerError,
    trigger_job,
    wait_for_run,
)
from bonuschef.portal.db import get_engine, read_last_scrape_time, read_store_clearance

_MARKDOWN_LABELS = {
    "EXPIRATION": "Bijna over datum",
    "OUT_OF_ASSORTMENT": "Uit het assortiment",
}
_LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
_REFRESH_TIMEOUT_S = 180
_REFRESHED_KEY = "clearance_refreshed_at"
_SNAPSHOT_BEFORE_KEY = "clearance_snapshot_before"
# Mirrors the markdowns_refresh cron "0 11-20 * * *": before the first scrape of
# the day there is legitimately no data for today, which is a different fact
# from the pipeline being broken.
_FIRST_SCRAPE_HOUR = 11


def _load(engine) -> pd.DataFrame | None:
    """Read clearance data, returning None if the mart isn't built yet."""
    try:
        return read_store_clearance(engine)
    except ProgrammingError:  # relation does not exist → job never ran
        return None


def _latest_snapshot(df: pd.DataFrame) -> pd.Timestamp:
    """Most recent scrape time, converted to Dutch local time."""
    return pd.to_datetime(df["scraped_at"], utc=True).max().tz_convert(_LOCAL_TZ)


def _now() -> pd.Timestamp:
    """Current instant in Dutch local time. Test seam: monkeypatched in tests."""
    return pd.Timestamp.now(tz=_LOCAL_TZ)


def _is_current(snapshot: pd.Timestamp | None, now: pd.Timestamp) -> bool:
    """True when the snapshot falls on the current trading day in Amsterdam.

    Clock distance is the wrong measure: 19:00 yesterday is worthless at 09:00
    (14h later) while 09:00 today is still the best data available at 23:00
    (also 14h later). What matters is whether the store has restocked and
    re-marked since.

    Both sides are converted rather than assumed local. Comparing UTC dates
    would silently misclassify every snapshot between 22:00 and midnight local
    in summer, when the local date has already rolled over and the UTC one has
    not. A missing snapshot is never current.
    """
    if snapshot is None or pd.isna(snapshot):
        return False
    return snapshot.tz_convert(_LOCAL_TZ).date() == now.tz_convert(_LOCAL_TZ).date()


def _describe_age(snapshot: pd.Timestamp, now: pd.Timestamp) -> str:
    """Coarse, glanceable age. Precision below the decision is noise."""
    hours = (now - snapshot).total_seconds() / 3600
    if hours < 1:
        return "minder dan een uur oud"
    if hours < 48:
        count = round(hours)
        return f"{count} uur oud" if count == 1 else f"{count} uur oud"
    days = round(hours / 24)
    if days < 60:
        return "1 dag oud" if days == 1 else f"{days} dagen oud"
    return f"{round(days / 30)} maanden oud"


def _format_local(snapshot: pd.Timestamp | None) -> str:
    """Timestamp for the caption, or a word when there is none."""
    if snapshot is None:
        return "een onbekend moment"
    return f"{snapshot.tz_convert(_LOCAL_TZ):%Y-%m-%d %H:%M}"


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


def _run_refresh(before: pd.Timestamp | None = None) -> None:
    """Trigger the markdowns job in Dagster and block until it finishes."""
    try:
        run_id = trigger_job(MARKDOWNS_REFRESH_JOB)
    except DagsterTriggerError as exc:
        st.error(f"{exc}\n\nIs the Dagster webserver running and reachable?")
        return

    with st.spinner("De winkel wordt gescand…"):
        try:
            status = wait_for_run(run_id, timeout_s=_REFRESH_TIMEOUT_S)
        except DagsterTriggerError as exc:
            st.error(str(exc))
            return

    if status == DagsterRunStatus.SUCCESS:
        read_store_clearance.clear()
        read_last_scrape_time.clear()
        st.session_state[_REFRESHED_KEY] = _now()
        # Kept so the banner can check the snapshot actually moved. A Dagster
        # run that succeeds having scraped nothing new is still a SUCCESS.
        st.session_state[_SNAPSHOT_BEFORE_KEY] = before
        st.rerun()
    elif status in (DagsterRunStatus.FAILURE, DagsterRunStatus.CANCELED):
        st.error(
            f"Het ophalen is mislukt (run {run_id[:8]}, status {status.value}). "
            "Kijk in Dagster; meestal is het een verlopen AH-token."
        )
    else:
        st.warning(
            f"Het ophalen loopt nog ({run_id[:8]}) na "
            f"{_REFRESH_TIMEOUT_S // 60} minuten. Laad de pagina zo opnieuw."
        )


def _render_refresh_banner(latest: pd.Timestamp | None) -> None:
    """One-shot outcome banner. A green tick must mean the data actually moved.

    The job succeeding is not the same as the snapshot advancing: a scrape that
    returns nothing new still exits SUCCESS, and dbt still rebuilds the mart
    from unchanged rows. Claiming freshness we did not verify is worse than the
    staleness this page now guards against.
    """
    refreshed = st.session_state.pop(_REFRESHED_KEY, None)
    before = st.session_state.pop(_SNAPSHOT_BEFORE_KEY, None)
    if refreshed is None:
        return
    moved = before is None or (latest is not None and latest > before)
    if moved:
        st.success(f"Opgehaald om {refreshed:%H:%M}.")
    else:
        st.warning(
            f"Om {refreshed:%H:%M} is er opgehaald, maar de scan is nog steeds die van "
            f"{_format_local(before)} — er was niets nieuwers."
        )


def _render_refresh_control(caption: str, latest: pd.Timestamp | None) -> None:
    """Snapshot age caption plus a button to re-scrape on demand."""
    col_caption, col_button = st.columns([4, 1])
    with col_caption:
        st.caption(caption)
        _render_refresh_banner(latest)
    with col_button:
        clicked = st.button(
            "Nu ophalen",
            help=("Haal de koopjes van dit moment op. Duurt ongeveer een minuut."),
            width="stretch",
        )
    if clicked:
        _run_refresh(latest)


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


def render_clearance() -> None:
    """Render the Laatste kans (store clearance) page."""
    st.title("Laatste kans koopjes")
    st.caption(
        "Afgeprijsde artikelen in jouw Albert Heijn. Kortingen lopen door de dag "
        "op en de voorraad is snel weg."
    )

    try:
        engine = get_engine()
        df = _load(engine)
        last_scrape = read_last_scrape_time(engine) if df is not None else None
    except Exception as exc:
        st.error(f"Geen verbinding met de database: {exc}")
        return

    if df is None:
        st.info("Nog geen koopjes opgehaald. Druk op **Nu ophalen**.")
        _render_refresh_control("Er is nog nooit een scan gedaan.", None)
        return

    now = _now()
    latest = _resolve_snapshot(last_scrape, df)

    if latest is None or not _is_current(latest, now):
        _render_refresh_control(f"Gescand om {_format_local(latest)}.", latest)
        _render_stale(len(df), latest, now)
        return

    _render_refresh_control(
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
