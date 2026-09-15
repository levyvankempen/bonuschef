"""Tests for the AH bonus products dlt source (pricing rules, pagination, dedupe)."""

from typing import cast

import pytest
from supermarktconnector.ah import AHConnector

from bonuschef.dags.defs.assets.dlt import ah as ah_module
from bonuschef.dags.defs.assets.dlt.ah import (
    _compute_bonus_price,
    _iter_search_bonus_products,
    ah_bonus_source,
)


class TestComputeBonusPrice:
    def test_current_price_wins(self):
        assert _compute_bonus_price({"currentPrice": 1.5, "priceBeforeBonus": 3}) == 1.5

    def test_no_labels_is_none(self):
        assert _compute_bonus_price({"priceBeforeBonus": 2.0}) is None
        assert _compute_bonus_price({"discountLabels": [{"code": "X"}]}) is None

    @pytest.mark.parametrize(
        "label, price_before, expected",
        [
            ({"code": "DISCOUNT_FIXED_PRICE", "price": 0.99}, 2.0, 0.99),
            ({"code": "DISCOUNT_X_FOR_Y", "price": 3.0, "count": 2}, 2.0, 1.5),
            ({"code": "DISCOUNT_ONE_FREE", "count": 2}, 2.0, 1.0),
            ({"code": "DISCOUNT_ONE_FREE", "count": 3}, 3.0, 2.0),
            ({"code": "DISCOUNT_ONE_HALF_PRICE"}, 2.0, 1.5),
            ({"code": "DISCOUNT_X_PLUS_Y_FREE", "count": 2, "freeCount": 1}, 3.0, 2.0),
            ({"code": "DISCOUNT_WEIGHT", "price": 0.99}, 2.0, 0.99),
            ({"code": "DISCOUNT_UNKNOWN"}, 2.0, None),
        ],
    )
    def test_mechanisms(self, label, price_before, expected):
        product = {"priceBeforeBonus": price_before, "discountLabels": [label]}
        assert _compute_bonus_price(product) == expected

    def test_tiered_prefers_single_unit_tier(self):
        product = {
            "priceBeforeBonus": 5.0,
            "discountLabels": [
                {"code": "DISCOUNT_TIERED_PRICE", "count": 3, "price": 10.0},
                {"code": "DISCOUNT_TIERED_PRICE", "count": 1, "price": 4.0},
            ],
        }
        assert _compute_bonus_price(product) == 4.0

    def test_tiered_without_single_tier_falls_back_to_first(self):
        product = {
            "priceBeforeBonus": 5.0,
            "discountLabels": [
                {"code": "DISCOUNT_TIERED_PRICE", "count": 2, "price": 8.0}
            ],
        }
        assert _compute_bonus_price(product) == 8.0


class FakeConnector:
    def __init__(self, pages, fail_on_page=None):
        self.pages = pages
        self.fail_on_page = fail_on_page
        self.requested: list[int] = []

    def search_products(self, query, page, size):
        self.requested.append(page)
        if page == self.fail_on_page:
            raise RuntimeError("AH 500")
        products = self.pages[page] if page < len(self.pages) else []
        return {"products": products, "page": {"totalPages": len(self.pages)}}


def _p(webshop_id, bonus=True, **extra):
    return {
        "webshopId": webshop_id,
        "isBonus": bonus,
        "title": f"P{webshop_id}",
        **extra,
    }


class TestIterSearchBonusProducts:
    def test_filters_bonus_and_stops_at_last_page(self):
        connector = FakeConnector([[_p(1), _p(2, bonus=False)], [_p(3)]])
        items = list(_iter_search_bonus_products(cast(AHConnector, connector)))
        assert [i["webshopId"] for i in items] == [1, 3]
        assert connector.requested == [0, 1]

    def test_stops_on_empty_page(self):
        connector = FakeConnector([[_p(1)], []])
        assert [
            i["webshopId"]
            for i in _iter_search_bonus_products(cast(AHConnector, connector))
        ] == [1]

    def test_stops_quietly_on_api_error(self):
        connector = FakeConnector([[_p(1)], [_p(2)], [_p(3)]], fail_on_page=1)
        assert [
            i["webshopId"]
            for i in _iter_search_bonus_products(cast(AHConnector, connector))
        ] == [1]


class TestBonusSource:
    def test_dedupes_and_maps_fields(self, monkeypatch):
        pages = [
            [
                _p(
                    1,
                    priceBeforeBonus=2.0,
                    currentPrice=1.0,
                    bonusStartDate="2025-01-06",
                    bonusEndDate="2025-01-12",
                    discountLabels=[
                        {
                            "code": "DISCOUNT_FIXED_PRICE",
                            "defaultDescription": "nu 1.00",
                        }
                    ],
                ),
                _p(1),  # duplicate
                {"isBonus": True},  # no id → skipped
            ]
        ]
        monkeypatch.setattr(ah_module, "AHConnector", lambda: FakeConnector(pages))
        rows = list(ah_bonus_source())
        assert len(rows) == 1
        row = rows[0]
        assert row["webshop_id"] == 1
        assert row["bonus_price"] == 1.0
        assert row["price_before_bonus"] == 2.0
        assert row["bonus_mechanism"] == "nu 1.00"
        assert row["is_bonus"] is True
        assert row["loaded_at"].endswith("Z")
