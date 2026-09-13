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
    "EXPIRATION": "Expiring soon",
    "OUT_OF_ASSORTMENT": "Discontinued",
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
        return "under an hour old"
    if hours < 48:
        count = round(hours)
        return f"{count} hour{'s' * (count != 1)} old"
    days = round(hours / 24)
    if days < 60:
        return f"{days} day{'s' * (days != 1)} old"
    return f"{round(days / 30)} months old"


def _format_local(snapshot: pd.Timestamp | None) -> str:
    """Timestamp for the caption, or a word when there is none."""
    if snapshot is None:
        return "an unknown time"
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

    with st.spinner("Scraping the store and rebuilding clearance tables…"):
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
            f"Refresh run {run_id[:8]} ended with status {status.value}. "
            "Check the run in the Dagster UI (an expired AH_REFRESH_TOKEN is the "
            "usual cause)."
        )
    else:
        st.warning(
            f"Refresh run {run_id[:8]} is still {status.value} after "
            f"{_REFRESH_TIMEOUT_S // 60} minutes. Reload the page in a bit."
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
        st.success(f"Refreshed at {refreshed:%H:%M}.")
    else:
        st.warning(
            f"The refresh ran at {refreshed:%H:%M}, but the snapshot is still "
            f"from {_format_local(before)} — the scrape returned nothing newer."
        )


def _render_refresh_control(caption: str, latest: pd.Timestamp | None) -> None:
    """Snapshot age caption plus a button to re-scrape on demand."""
    col_caption, col_button = st.columns([4, 1])
    with col_caption:
        st.caption(caption)
        _render_refresh_banner(latest)
    with col_button:
        clicked = st.button(
            "Refresh now",
            help=(
                "Scrape the store's current clearance items and rebuild the "
                "tables. Takes about a minute."
            ),
            use_container_width=True,
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
    age = "of unknown age" if latest is None else _describe_age(latest, now)
    if now.hour < _FIRST_SCRAPE_HOUR:
        st.info(
            f"Today's clearance list isn't in yet — the first scrape of the day "
            f"runs at {_FIRST_SCRAPE_HOUR}:00. Showing nothing rather than the "
            f"previous day's {item_count} item(s), which are {age}."
        )
        return
    st.warning(
        f"This snapshot is {age} and is not from today. It held "
        f"{item_count} item(s), not shown: clearance prices and stock change "
        f"within hours, so they would send you to the store for something that "
        f"is gone. Press **Refresh now** for today's."
    )


def _render_metrics(df: pd.DataFrame) -> None:
    col1, col2, col3 = st.columns(3)
    col1.metric("Clearance items", len(df))
    if df["markdown_percentage"].notna().any():
        col2.metric("Max discount", f"{df['markdown_percentage'].max():.0f}%")
    matched = df["real_savings_vs_tracked"].notna().sum()
    col3.metric("Matched to tracked", int(matched))


def _render_table(df: pd.DataFrame) -> None:
    display = df.copy()
    display["markdown_type"] = display["markdown_type"].map(
        lambda t: _MARKDOWN_LABELS.get(t, t)
    )
    display = display[
        [
            "product_name",
            "brand",
            "sales_unit_size",
            "markdown_percentage",
            "price_was",
            "price_now",
            "markdown_amount",
            "stock",
            "markdown_expiration_date",
            "markdown_type",
        ]
    ].rename(
        columns={
            "product_name": "Product",
            "brand": "Brand",
            "sales_unit_size": "Size",
            "markdown_percentage": "Discount",
            "price_was": "Was (€)",
            "price_now": "Now (€)",
            "markdown_amount": "You save (€)",
            "stock": "Stock",
            "markdown_expiration_date": "Expires",
            "markdown_type": "Reason",
        }
    )
    st.dataframe(
        display,
        hide_index=True,
        use_container_width=True,
        column_config={
            "Discount": st.column_config.NumberColumn(format="%.0f%%"),
            "Was (€)": st.column_config.NumberColumn(format="€%.2f"),
            "Now (€)": st.column_config.NumberColumn(format="€%.2f"),
            "You save (€)": st.column_config.NumberColumn(format="€%.2f"),
        },
    )


def render_clearance() -> None:
    """Render the Laatste kans (store clearance) page."""
    st.title("Laatste kans koopjes")
    st.caption(
        "Reduced-to-clear items at your Albert Heijn store. Discounts deepen "
        "through the day and stock sells out fast."
    )

    try:
        engine = get_engine()
        df = _load(engine)
        last_scrape = read_last_scrape_time(engine) if df is not None else None
    except Exception as exc:
        st.error(f"Database connection error: {exc}")
        return

    if df is None:
        st.info(
            "No clearance data yet. Press **Refresh now** or run the "
            "`markdowns_refresh` job in Dagster (needs a member "
            "`AH_REFRESH_TOKEN` — see `bonuschef.utils.ah_login`)."
        )
        _render_refresh_control("No snapshot has ever been taken.", None)
        return

    now = _now()
    latest = _resolve_snapshot(last_scrape, df)

    if latest is None or not _is_current(latest, now):
        _render_refresh_control(
            f"Captured {_format_local(latest)} (local time).", latest
        )
        _render_stale(len(df), latest, now)
        return

    _render_refresh_control(
        f"Captured {_format_local(latest)} (local time) · "
        f"{_describe_age(latest, now)}.",
        latest,
    )

    if df.empty:
        st.info("No clearance items in the latest snapshot.")
        return

    _render_metrics(df)

    categories = sorted(c for c in df["category_title"].dropna().unique())
    chosen = st.multiselect("Filter by category", categories, default=[])
    if chosen:
        df = df[df["category_title"].isin(chosen)]

    _render_table(df)
