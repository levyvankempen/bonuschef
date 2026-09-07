"""Tests for chart helpers (pure logic plus AppTest guard paths)."""

import pandas as pd

from bonuschef.portal.ui import (
    _top_movers,
    display_cost_breakdown,
    display_total_cost_line,
)
from tests.conftest import run_app


def test_top_movers_ranks_by_cumulative_absolute_change():
    data = pd.DataFrame(
        {
            "product_name": ["a", "a", "b", "c"],
            "price_change": [0.5, -0.5, 0.2, -2.0],
        }
    )
    assert _top_movers(data, n=2) == ["c", "a"]


def test_total_cost_line_reports_missing_columns():
    df = pd.DataFrame({"recipe_name": ["x"], "total": [1.0]})
    at = run_app(
        display_total_cost_line,
        df,
        date_col="date",
        value_col="total",
    ).run()
    assert "Missing required columns" in at.info[0].value


def test_total_cost_line_reports_missing_recipe_column():
    df = pd.DataFrame({"date": ["2025-01-06"], "total": [1.0]})
    at = run_app(
        display_total_cost_line,
        df,
        date_col="date",
        value_col="total",
    ).run()
    assert "Missing recipe column" in at.info[0].value


def test_total_cost_line_with_unparseable_data():
    df = pd.DataFrame({"date": ["nope"], "total": ["x"], "recipe_name": ["r"]})
    at = run_app(
        display_total_cost_line,
        df,
        date_col="date",
        value_col="total",
    ).run()
    assert "No valid data" in at.info[0].value


def test_total_cost_line_renders_chart_for_valid_data():
    df = pd.DataFrame(
        {
            "date": ["2025-01-06", "2025-01-13"],
            "total": [1.0, 1.5],
            "recipe_name": ["r", "r"],
        }
    )
    at = run_app(
        display_total_cost_line,
        df,
        date_col="date",
        value_col="total",
    ).run()
    assert not at.exception
    assert not at.info


def test_cost_breakdown_offers_recipe_selector_when_multiple():
    df = pd.DataFrame(
        {
            "recipe_name": ["A", "B"],
            "product_name": ["x", "y"],
            "item_cost": [1.0, 2.0],
            "cost_pct": [50.0, 50.0],
        }
    )
    at = run_app(display_cost_breakdown, df).run()
    assert not at.exception
    assert at.selectbox[0].options == ["A", "B"]
