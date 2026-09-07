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
from bonuschef.portal.db import get_engine, read_store_clearance

_MARKDOWN_LABELS = {
    "EXPIRATION": "Expiring soon",
    "OUT_OF_ASSORTMENT": "Discontinued",
}
_LOCAL_TZ = ZoneInfo("Europe/Amsterdam")
_REFRESH_TIMEOUT_S = 180
_REFRESHED_KEY = "clearance_refreshed_at"


def _load(engine) -> pd.DataFrame | None:
    """Read clearance data, returning None if the mart isn't built yet."""
    try:
        return read_store_clearance(engine)
    except ProgrammingError:  # relation does not exist → job never ran
        return None


def _latest_snapshot(df: pd.DataFrame) -> pd.Timestamp:
    """Most recent scrape time, converted to Dutch local time."""
    return pd.to_datetime(df["scraped_at"], utc=True).max().tz_convert(_LOCAL_TZ)


def _run_refresh() -> None:
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
        st.session_state[_REFRESHED_KEY] = pd.Timestamp.now(tz=_LOCAL_TZ)
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


def _render_refresh_control(latest: pd.Timestamp | None) -> None:
    """Snapshot age caption plus a button to re-scrape on demand."""
    col_caption, col_button = st.columns([4, 1])
    with col_caption:
        if latest is not None:
            st.caption(f"Latest snapshot: {latest:%Y-%m-%d %H:%M} (local time)")
        else:
            st.caption("No snapshot yet.")
        refreshed = st.session_state.pop(_REFRESHED_KEY, None)
        if refreshed is not None:
            st.success(f"Refreshed at {refreshed:%H:%M}.")
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
        _run_refresh()


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
    except Exception as exc:
        st.error(f"Database connection error: {exc}")
        return

    if df is None:
        st.info(
            "No clearance data yet. Press **Refresh now** or run the "
            "`markdowns_refresh` job in Dagster (needs a member "
            "`AH_REFRESH_TOKEN` — see `bonuschef.utils.ah_login`)."
        )
        _render_refresh_control(None)
        return

    _render_refresh_control(_latest_snapshot(df) if not df.empty else None)

    if df.empty:
        st.info("No clearance items in the latest snapshot.")
        return

    _render_metrics(df)

    categories = sorted(c for c in df["category_title"].dropna().unique())
    chosen = st.multiselect("Filter by category", categories, default=[])
    if chosen:
        df = df[df["category_title"].isin(chosen)]

    _render_table(df)
