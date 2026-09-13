"""Proposing products for an ingredient concept."""

from __future__ import annotations

from bonuschef.portal.matching import Candidate, accept


def _c(name: str, extra: int, price: float = 1.0) -> Candidate:
    return Candidate(
        product_link=f"wi/{name}", product_name=name, price=price, extra_words=extra
    )


def test_the_generic_product_wins_over_its_variants():
    """AH names generic products generically, so fewest-extra-words is a decent
    proxy for "this is the ingredient, not a dish containing it"."""
    accepted = accept([_c("AH Courgette", 1), _c("AH Courgette spiraal", 2)])
    assert [c.product_name for c in accepted] == ["AH Courgette"]


def test_several_products_attach_to_one_concept():
    """Which is cheapest changes daily and the cheapest is the point, so the
    whole head group attaches rather than a single winner."""
    accepted = accept([_c("AH Courgette", 1), _c("AH Biologisch Courgette", 1)])
    assert len(accepted) == 2


def test_a_compound_only_match_is_refused():
    """ "Bonduelle pasta pronto fusilli courgette broccoli" contains the word
    but is a different food. An unresolved ingredient is visibly unresolved; a
    wrong one produces a confident wrong price."""
    assert accept([_c("Bonduelle pasta pronto fusilli courgette broccoli", 5)]) == []


def test_matching_a_whole_category_is_refused():
    """Five equally-generic hits means we matched a category, not an item."""
    assert accept([_c(f"AH Kaas {i}", 1) for i in range(5)]) == []


def test_nothing_found_is_not_an_error():
    assert accept([]) == []
