"""Laatste kans page — store-specific clearance (reduced-to-clear) items."""

import pandas as pd
import streamlit as st

from bonuschef.portal.db import get_engine, read_store_clearance

_MARKDOWN_LABELS = {
    "EXPIRATION": "Expiring soon",
    "OUT_OF_ASSORTMENT": "Discontinued",
}


def _load(engine) -> pd.DataFrame | None:
    """Read clearance data, returning None if the mart isn't built yet."""
    try:
        return read_store_clearance(engine)
    except Exception:
        return None


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

    engine = get_engine()
    df = _load(engine)

    if df is None:
        st.info(
            "No clearance data yet. Run the `markdowns_refresh` job in Dagster "
            "(needs a member `AH_REFRESH_TOKEN` — see `bonuschef.utils.ah_login`)."
        )
        return
    if df.empty:
        st.info("No clearance items in the latest snapshot.")
        return

    scraped = pd.to_datetime(df["scraped_at"]).max()
    st.caption(f"Latest snapshot: {scraped:%Y-%m-%d %H:%M} UTC")

    _render_metrics(df)

    categories = sorted(c for c in df["category_title"].dropna().unique())
    chosen = st.multiselect("Filter by category", categories, default=[])
    if chosen:
        df = df[df["category_title"].isin(chosen)]

    _render_table(df)
