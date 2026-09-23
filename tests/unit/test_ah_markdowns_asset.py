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
    rows = list(_iter_markdowns(CFG, "2026-09-07T12:00:00Z", CFG.store_id))
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
    (row,) = _iter_markdowns(CFG, "t", CFG.store_id)
    assert row["webshop_id"] is None
    assert row["price_now"] is None
    assert row["store_id"] == 1876


def test_iter_markdowns_handles_empty_feed(monkeypatch):
    _install(monkeypatch, {"bargainItems": None})
    assert list(_iter_markdowns(CFG, "t", CFG.store_id)) == []


def test_source_stamps_one_scraped_at_per_run(monkeypatch):
    _install(
        monkeypatch,
        {"bargainItems": [{"product": {"id": 1}}, {"product": {"id": 2}}]},
    )
    rows = list(ah_markdowns_source(CFG, [CFG.store_id]))
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


# --- one scrape per store an account uses -----------------------------------


class _StoreEngine:
    """Answers the store query and nothing else."""

    def __init__(self, *store_ids):
        self.store_ids = list(store_ids)

    def begin(self):
        from contextlib import contextmanager

        @contextmanager
        def _cm():
            yield self

        return _cm()

    def execute(self, statement, params=None):
        from types import SimpleNamespace

        return SimpleNamespace(fetchall=lambda: [(s,) for s in self.store_ids])


def test_every_account_s_store_is_scraped():
    """Before this, only the configured store was. A friend who chose a
    different shop got no clearance - and, because three models CROSS JOIN
    the store spine, no bonus prices either. An empty application."""
    engine = _StoreEngine(1661, 1876)
    assert module.stores_to_scrape(engine, 1876) == [1661, 1876]


def test_the_configured_store_is_a_floor_not_a_default():
    """A deployment with no accounts, or where nobody has chosen yet, keeps
    working exactly as it did."""
    assert module.stores_to_scrape(_StoreEngine(), 1876) == [1876]


def test_two_accounts_in_one_shop_are_scraped_once():
    """Clearance is store-scoped, so a second account at the same shop is a
    second reader of one answer, not a second request."""
    engine = _StoreEngine(1876, 1876, 1661)
    assert module.stores_to_scrape(engine, 1876) == [1661, 1876]


def test_one_unreachable_store_does_not_stop_the_others(monkeypatch):
    """A friend's shop being briefly unreachable must not stop the rest of
    the household's prices from loading."""

    def flaky(cfg, scraped_at, store_id):
        if store_id == 1661:
            raise RuntimeError("AH said no")
        yield {"store_id": store_id, "webshop_id": 1}

    monkeypatch.setattr(module, "_iter_markdowns", flaky)
    rows = list(ah_markdowns_source(CFG, [1661, 1876]).store_markdowns)
    assert [r["store_id"] for r in rows] == [1876]


def test_every_store_failing_is_a_failure(monkeypatch):
    """One failing is a warning. All of them is the feed being gone, and a
    load that reported success would leave yesterday's prices looking
    current."""

    def broken(cfg, scraped_at, store_id):
        raise RuntimeError("AH said no")
        yield  # pragma: no cover

    monkeypatch.setattr(module, "_iter_markdowns", broken)
    # dlt wraps whatever a resource raises, so the type at the boundary is
    # its own. What matters is that the load fails rather than reporting
    # success over an empty result, and that the reason survives the wrapping.
    with pytest.raises(Exception) as caught:
        list(ah_markdowns_source(CFG, [1661, 1876]).store_markdowns)
    chain = []
    exc: BaseException | None = caught.value
    while exc is not None:
        chain.append(exc)
        exc = exc.__cause__ or exc.__context__
    assert any(isinstance(e, module.AHMarkdownsUnavailable) for e in chain), chain
    assert any("no store could be scraped" in str(e) for e in chain), chain


def test_each_row_carries_the_store_it_came_from(monkeypatch):
    """Not the configured one. Stamping every row with cfg.store_id would
    file one shop's clearance under another's, which is worse than not
    having it."""
    monkeypatch.setattr(
        module,
        "token_manager",
        lambda cfg: type(
            "M",
            (),
            {
                "graphql": staticmethod(
                    lambda q, v: {"bargainItems": [{"product": {"id": 1}}]}
                )
            },
        )(),
    )
    rows = list(module._iter_markdowns(CFG, "2026-01-01T00:00:00Z", 1661))
    assert [r["store_id"] for r in rows] == [1661]
