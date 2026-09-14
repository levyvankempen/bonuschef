"""Tests for recipe builder helpers (validation, saving, image scraping)."""

from contextlib import contextmanager
from io import BytesIO

from bonuschef.portal import manual_recipe as recipe_builder
from bonuschef.portal.manual_recipe import (
    _fetch_product_image,
    _save_recipe,
    _validate,
)


class TestValidate:
    def test_collects_all_problems(self, monkeypatch):
        monkeypatch.setattr(
            recipe_builder, "existing_recipe_names", lambda e: {"Pasta"}
        )
        errors = _validate(object(), "  ", {})
        assert errors == [
            "Geef het recept een naam.",
            "Kies minstens één product.",
        ]

    def test_duplicate_name(self, monkeypatch):
        monkeypatch.setattr(
            recipe_builder, "existing_recipe_names", lambda e: {"Pasta"}
        )
        errors = _validate(object(), " Pasta ", {"Melk": 1})
        assert errors == ["Er bestaat al een recept met de naam 'Pasta'."]

    def test_valid(self, monkeypatch):
        monkeypatch.setattr(recipe_builder, "existing_recipe_names", lambda e: set())
        assert _validate(object(), "Soep", {"Melk": 1}) == []


def test_save_recipe_inserts_rows_and_images(monkeypatch):
    calls: dict[str, list] = {"recipe": [], "ingredients": [], "images": []}
    monkeypatch.setattr(recipe_builder, "next_recipe_id", lambda e: 9)
    monkeypatch.setattr(
        recipe_builder, "insert_recipe", lambda e, *a: calls["recipe"].append(a)
    )
    monkeypatch.setattr(
        recipe_builder,
        "insert_ingredients",
        lambda e, *a: calls["ingredients"].append(a),
    )
    monkeypatch.setattr(
        recipe_builder, "upsert_product_image", lambda e, *a: calls["images"].append(a)
    )
    monkeypatch.setattr(
        recipe_builder,
        "_fetch_product_image",
        lambda url: "https://img/melk" if "melk" in url else None,
    )

    recipe_id = _save_recipe(
        object(),
        "Pasta",
        4,
        {"Melk": 2, "Kaas": 1},
        {"Melk": "1/melk", "Kaas": "2/kaas"},
        {"Melk": "https://ah.nl/melk", "Kaas": "https://ah.nl/kaas"},
    )
    assert recipe_id == 9
    assert calls["recipe"] == [(9, "Pasta", 4)]
    assert calls["ingredients"] == [(9, [("Melk", "1/melk", 2), ("Kaas", "2/kaas", 1)])]
    assert calls["images"] == [("1/melk", "https://img/melk")]


class TestFetchProductImage:
    @staticmethod
    def _serve(monkeypatch, html: str | None):
        @contextmanager
        def fake_urlopen(req, timeout):
            if html is None:
                raise OSError("offline")
            yield BytesIO(html.encode())

        monkeypatch.setattr(recipe_builder, "urlopen", fake_urlopen)

    def test_prefers_400x400_variant(self, monkeypatch):
        self._serve(
            monkeypatch,
            '<meta property="og:image" content="https://cdn/a_200x200.jpg">'
            '<meta property="og:image" content="https://cdn/a_400x400.jpg?x=1&amp;y=2">',
        )
        assert (
            _fetch_product_image("https://ah.nl/p/1")
            == "https://cdn/a_400x400.jpg?x=1&y=2"
        )

    def test_falls_back_to_first_match(self, monkeypatch):
        self._serve(
            monkeypatch, '<meta property="og:image" content="https://cdn/only.jpg">'
        )
        assert _fetch_product_image("https://ah.nl/p/2") == "https://cdn/only.jpg"

    def test_no_match_is_none(self, monkeypatch):
        self._serve(monkeypatch, "<html></html>")
        assert _fetch_product_image("https://ah.nl/p/3") is None

    def test_network_error_is_none(self, monkeypatch):
        self._serve(monkeypatch, None)
        assert _fetch_product_image("https://ah.nl/p/4") is None
