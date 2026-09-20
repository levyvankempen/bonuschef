"""Flagged concepts reaching the person who can fix them.

A concept the automatic system got wrong is worse than one it could not match
at all: the recipe already has a price, so nothing looks amiss. It has to be
raised deliberately or it is never looked at.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "src" / "bonuschef" / "portal" / "db.py"
REVIEW = ROOT / "src" / "bonuschef" / "portal" / "review.py"
TONIGHT = ROOT / "src" / "bonuschef" / "portal" / "tonight_page.py"
RESOLUTION = (
    ROOT
    / "src"
    / "bonuschef"
    / "dags"
    / "defs"
    / "assets"
    / "resolution"
    / "__init__.py"
)


def _sql_of(name: str) -> str:
    """The SQL text of a named function in db.py."""
    tree = ast.parse(DB.read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return ast.get_source_segment(DB.read_text(), node) or ""
    raise AssertionError(f"db.py has no {name}")


def test_a_flagged_concept_returns_to_the_queue():
    """The queue excluded anything with a review row, so a concept a person
    settled once could never come back - which is exactly the case where it is
    now known to be wrong."""
    sql = _sql_of("read_unresolved_concepts")
    assert "ah_ingredient_flags" in sql, "the queue does not consider flags"
    assert re.search(r"r\.concept_id IS NULL OR f\.concept_id IS NOT NULL", sql), (
        "the queue still admits only concepts nobody has looked at"
    )


def test_flagged_concepts_come_first():
    """A wrong match is silently priced into a recipe; a missing one is shown
    as a gap. The wrong one costs more."""
    assert "is_flagged DESC" in _sql_of("read_unresolved_concepts")


def test_the_flag_is_separate_from_the_review_record():
    """ "a person looked at this" and "this needs looking at again" are
    different facts. Expressing the second by deleting the first would lose
    the record of who settled what."""
    source = DB.read_text()
    assert "CREATE TABLE IF NOT EXISTS public.ah_ingredient_flags" in source
    flag_fn = _sql_of("flag_concepts")
    assert "ah_ingredient_review" not in flag_fn, "flagging touches the review record"


def test_confirming_clears_the_flag():
    """Otherwise the concept returns to the head of the queue the person just
    cleared it from."""
    body = REVIEW.read_text()
    assert "clear_flag(engine, concept_id)" in body
    assert body.index("confirm_resolution(engine, concept_id, links)") < body.index(
        "clear_flag(engine, concept_id)"
    ), "the flag is cleared before the resolution is recorded"


def test_the_recheck_persists_flags_rather_than_only_logging_them():
    """A warning in a Dagster run is not somewhere a person looking for work
    will find it."""
    body = RESOLUTION.read_text()
    assert "flag_concepts(engine, flag_rows)" in body


def test_the_page_says_a_wrong_match_is_different_from_a_missing_one():
    """A recipe with a wrong ingredient still shows a price, so "N recepten
    missen nog een ingrediënt" does not cover it."""
    body = TONIGHT.read_text()
    assert "count_flagged_concepts" in body
    assert "niet klopt" in body, "the page does not say the price is wrong"


def test_the_button_appears_for_flagged_concepts_alone():
    """A person may have linked everything and still have wrong links. If the
    button only showed for unlinked ingredients there would be no way in."""
    body = TONIGHT.read_text()
    assert "if unresolved or flagged:" in body, (
        "the review button is still gated on unlinked ingredients only"
    )


def test_the_dialog_says_why_a_concept_came_back():
    """Arriving at a concept you already settled, with no explanation, reads
    as the queue having forgotten your decision."""
    body = REVIEW.read_text()
    assert 'row.get("is_flagged")' in body
    assert 'row.get("flag_reason")' in body


def test_counting_flags_survives_a_database_without_the_table():
    """The portal must render against a database the resolution asset has
    never run on. A missing table is "nothing flagged", not an error page."""
    from bonuschef.portal.db import count_flagged_concepts

    class _Engine:
        def begin(self):
            raise RuntimeError("relation does not exist")

    assert count_flagged_concepts(_Engine()) == 0


# --- what kind of thing each candidate is ---------------------------------


def test_the_dialog_shows_what_kind_each_candidate_is():
    """ "AH Witte kaas 40+" and "AH Truffelsalami parmezaanse kaas" read alike
    in a list of names. One is classified Witte kaas and the other Salami, and
    that is exactly the distinction the person is being asked to make."""
    body = REVIEW.read_text()
    assert "format_func" in body, "candidates are shown as bare names"
    assert "_kinds(" in body


def test_a_failed_lookup_does_not_take_the_dialog_away(monkeypatch):
    """A person who opened this is mid-task. A network error is a reason to
    drop the annotation, not the page."""
    import bonuschef.portal.review as review

    def _boom(ids):
        raise RuntimeError("api down")

    monkeypatch.setattr(review, "fetch_product_taxonomy", _boom)
    assert review._kinds({"AH Dille": "wi123/ah-dille"}) == {}


def test_a_candidate_without_a_webshop_id_is_skipped_not_fatal():
    import bonuschef.portal.review as review

    assert review._kinds({"Iets": "not-a-webshop-link"}) == {}
    assert review._kinds({}) == {}


def test_only_classified_candidates_are_annotated(monkeypatch):
    """A product the retailer declines to classify is shown as a bare name
    rather than with an empty suffix."""
    import bonuschef.portal.review as review
    from bonuschef.utils.ah_recipes import ProductHit

    monkeypatch.setattr(
        review,
        "fetch_product_taxonomy",
        lambda ids: {
            1: ProductHit(
                webshop_id=1, title="a", taxonomy_path=("Kaas", "Witte kaas")
            ),
            2: ProductHit(webshop_id=2, title="b"),
        },
    )
    assert review._kinds({"A": "wi1/a", "B": "wi2/b"}) == {"A": "Witte kaas"}
