"""Analysis page — product price changes, price history, and bonus price check."""

import altair as alt
import pandas as pd
import streamlit as st

from bonuschef.portal.db import (
    get_engine,
    read_bonus_price_comparison,
    read_price_changes,
)
from bonuschef.portal.ui import display_price_changes


def _render_price_changes_table(changes_df):
    """Display recent price changes in a formatted table."""
    st.subheader("Recente prijswijzigingen")

    display_df = changes_df[
        [
            "product_name",
            "snapshot_timestamp",
            "prev_price",
            "new_price",
            "price_change",
            "pct_change",
        ]
    ].copy()
    display_df = display_df.rename(
        columns={
            "product_name": "Product",
            "snapshot_timestamp": "Datum",
            "prev_price": "Was (\u20ac)",
            "new_price": "Nu (\u20ac)",
            "price_change": "Verschil (\u20ac)",
            "pct_change": "Verschil (%)",
        }
    )

    st.dataframe(
        display_df,
        hide_index=True,
        column_config={
            "Was (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Nu (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Verschil (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Verschil (%)": st.column_config.NumberColumn(format="%.1f%%"),
        },
    )


def _render_price_history(engine, changes_df):
    """Display top movers chart and product price history."""
    st.subheader("Prijsverloop")
    display_price_changes(changes_df, engine=engine)


def _render_bonus_price_check(engine):
    """Show bonus vs tracked price comparison across all products."""
    bonus_df = read_bonus_price_comparison(engine)
    if bonus_df.empty:
        return

    st.subheader("Bonusprijzen gecontroleerd")
    st.caption(
        "Vergelijkt de normale prijs die AH claimt met de prijs die wij zelf "
        'hebben gevolgd, om opgeblazen "van"-prijzen zichtbaar te maken.'
    )

    total = len(bonus_df)
    inflated = bonus_df["is_inflated"].sum()
    inflated_df = bonus_df[bonus_df["is_inflated"]].copy()
    avg_inflation = (
        inflated_df["price_inflation"].mean() if not inflated_df.empty else 0
    )

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Bonusproducten gekoppeld", total)
    with col2:
        st.metric("Opgeblazen van-prijs", f"{inflated} ({100 * inflated / total:.0f}%)")
    with col3:
        st.metric("Gem. opslag", f"\u20ac{avg_inflation:.2f}")

    # Bar chart — top 15 products by price inflation
    if not inflated_df.empty:
        chart_data = inflated_df.nlargest(15, "price_inflation")[
            ["product_name", "price_inflation", "tracked_price", "ah_price"]
        ].copy()
        for col in ["price_inflation", "tracked_price", "ah_price"]:
            chart_data[col] = pd.to_numeric(chart_data[col], errors="coerce")

        chart = (
            alt.Chart(chart_data)
            .mark_bar()
            .encode(
                x=alt.X("price_inflation:Q", title="Opslag op de van-prijs (\u20ac)"),
                y=alt.Y("product_name:N", title="Product", sort="-x"),
                tooltip=[
                    alt.Tooltip("product_name:N", title="Product"),
                    alt.Tooltip(
                        "tracked_price:Q", title="Gevolgde prijs", format=".2f"
                    ),
                    alt.Tooltip("ah_price:Q", title="AH-prijs", format=".2f"),
                    alt.Tooltip("price_inflation:Q", title="Opslag", format=".2f"),
                ],
            )
            .properties(height=max(len(chart_data) * 40, 200))
        )

        st.altair_chart(chart)

    # Full table
    display_df = bonus_df[
        [
            "product_name",
            "tracked_price",
            "ah_price",
            "bonus_price",
            "price_inflation",
            "real_savings",
            "advertised_savings",
            "bonus_mechanism",
            "is_inflated",
        ]
    ].copy()
    display_df = display_df.rename(
        columns={
            "product_name": "Product",
            "tracked_price": "Gevolgd (\u20ac)",
            "ah_price": "AH-prijs (\u20ac)",
            "bonus_price": "Bonus (\u20ac)",
            "price_inflation": "Opslag (\u20ac)",
            "real_savings": "Echte korting (\u20ac)",
            "advertised_savings": "AH claimt (\u20ac)",
            "bonus_mechanism": "Actie",
            "is_inflated": "Opgeblazen?",
        }
    )

    st.dataframe(
        display_df,
        hide_index=True,
        column_config={
            "Gevolgd (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "AH-prijs (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Bonus (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Opslag (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
            "Echte korting (\u20ac)": st.column_config.NumberColumn(
                format="\u20ac%.2f"
            ),
            "AH claimt (\u20ac)": st.column_config.NumberColumn(format="\u20ac%.2f"),
        },
    )


def render_analysis():
    st.title("Prijsanalyse")

    try:
        engine = get_engine()
    except Exception as e:
        st.error(f"Geen verbinding met de database: {e}")
        return

    changes_df = read_price_changes(engine)

    if changes_df.empty:
        st.info("Er zijn nog geen prijswijzigingen vastgelegd.")
        return

    _render_price_changes_table(changes_df)
    _render_price_history(engine, changes_df)
    _render_bonus_price_check(engine)
