"""Tests for chart helpers (pure logic plus AppTest guard paths)."""

import pandas as pd

from bonuschef.portal.ui import (
    _top_movers,
)


def test_top_movers_ranks_by_cumulative_absolute_change():
    data = pd.DataFrame(
        {
            "product_name": ["a", "a", "b", "c"],
            "price_change": [0.5, -0.5, 0.2, -2.0],
        }
    )
    assert _top_movers(data, n=2) == ["c", "a"]
