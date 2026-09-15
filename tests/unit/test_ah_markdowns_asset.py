"""Tests for the AH store markdowns ("laatste kans") dlt source."""

from pathlib import Path

import pytest

from bonuschef.config import AHMarkdownConfig
from bonuschef.dags.defs.assets.dlt import ah_markdowns as module
from bonuschef.dags.defs.assets.dlt.ah_markdowns import (
    _BARGAIN_ITEMS_QUERY,
    _iter_markdowns,
    _to_float,
    ah_markdowns_source,
    token_manager,
)

CFG = AHMarkdownConfig(store_id=1876, refresh_token="r", token_file=Path("/tmp/x.json"))


def test_to_float_coerces_strings_and_tolerates_junk():
    assert _to_float("0.99") == 0.99
    assert _to_float(2) == 2.0
    assert _to_float(None) is None
    assert _to_float("n/a") is None


def test_token_manager_is_wired_to_config(tmp_path):
    cfg = AHMarkdownConfig(
        store_id=1, refresh_token="boot", token_file=tmp_path / "t.json"
    )
    mgr = token_manager(cfg)
    assert mgr.store.path == tmp_path / "t.json"
    assert mgr.bootstrap_refresh_token == "boot"
    assert mgr.client_id == "appie"


class FakeManager:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def graphql(self, query, variables):
        self.calls.append((query, variables))
        return self.data


def _install(monkeypatch, data):
    mgr = FakeManager(data)
    monkeypatch.setattr(module, "token_manager", lambda cfg: mgr)
    return mgr


def test_iter_markdowns_maps_fields(monkeypatch):
    mgr = _install(
        monkeypatch,
        {
            "bargainItems": [
                {
                    "product": {
                        "id": 42,
                        "title": "Kip",
                        "brand": "AH",
                        "salesUnitSize": "500 g",
                    },
                    "categoryTitle": "Vlees",
                    "markdown": {
                        "markdownType": "EXPIRATION",
                        "markdownPercentage": 35,
                        "markdownExpirationDate": "2026-09-08",
                    },
                    "stock": 3,
                    "bargainPrice": {"priceWas": "4.99", "priceNow": "3.24"},
                }
            ]
        },
    )
    rows = list(_iter_markdowns(CFG, "2026-09-07T12:00:00Z"))
    assert rows == [
        {
            "store_id": 1876,
            "webshop_id": 42,
            "title": "Kip",
            "brand": "AH",
            "sales_unit_size": "500 g",
            "image_url": None,
            "category_title": "Vlees",
            "markdown_type": "EXPIRATION",
            "markdown_percentage": 35,
            "markdown_expiration_date": "2026-09-08",
            "stock": 3,
            "price_was": 4.99,
            "price_now": 3.24,
            "scraped_at": "2026-09-07T12:00:00Z",
        }
    ]
    assert mgr.calls == [(_BARGAIN_ITEMS_QUERY, {"storeId": "1876"})]


def test_iter_markdowns_tolerates_missing_subobjects(monkeypatch):
    _install(monkeypatch, {"bargainItems": [{"product": None, "markdown": None}]})
    (row,) = _iter_markdowns(CFG, "t")
    assert row["webshop_id"] is None
    assert row["price_now"] is None
    assert row["store_id"] == 1876


def test_iter_markdowns_handles_empty_feed(monkeypatch):
    _install(monkeypatch, {"bargainItems": None})
    assert list(_iter_markdowns(CFG, "t")) == []


def test_source_stamps_one_scraped_at_per_run(monkeypatch):
    _install(
        monkeypatch,
        {"bargainItems": [{"product": {"id": 1}}, {"product": {"id": 2}}]},
    )
    rows = list(ah_markdowns_source(CFG))
    assert [r["webshop_id"] for r in rows] == [1, 2]
    stamps = {r["scraped_at"] for r in rows}
    assert len(stamps) == 1
    assert stamps.pop().endswith("Z")


class TestImagePack:
    """AH returns the product image with the clearance item itself.

    The shape is undocumented, so every step degrades to None rather than
    raising: a missing picture must never fail a scrape, and the card already
    renders without one.
    """

    def test_the_medium_size_is_taken(self):
        from bonuschef.dags.defs.assets.dlt.ah_markdowns import _image_url

        url = _image_url(
            {"imagePack": [{"medium": {"url": "https://static.ah.nl/m.jpg"}}]}
        )
        assert url == "https://static.ah.nl/m.jpg"

    def test_another_size_is_used_when_medium_is_absent(self):
        from bonuschef.dags.defs.assets.dlt.ah_markdowns import _image_url

        assert (
            _image_url(
                {"imagePack": [{"small": {"url": "https://static.ah.nl/s.jpg"}}]}
            )
            == "https://static.ah.nl/s.jpg"
        )

    @pytest.mark.parametrize(
        "product",
        [
            pytest.param({}, id="no-pack"),
            pytest.param({"imagePack": None}, id="null-pack"),
            pytest.param({"imagePack": []}, id="empty-pack"),
            pytest.param({"imagePack": [{}]}, id="entry-without-sizes"),
            pytest.param({"imagePack": [{"medium": None}]}, id="null-size"),
            pytest.param({"imagePack": [{"medium": {}}]}, id="size-without-url"),
            pytest.param({"imagePack": "not-a-list"}, id="wrong-type"),
        ],
    )
    def test_anything_unexpected_degrades_to_no_image(self, product):
        from bonuschef.dags.defs.assets.dlt.ah_markdowns import _image_url

        assert _image_url(product) is None
