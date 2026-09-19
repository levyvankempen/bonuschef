"""Whether a product plausibly satisfies an ingredient.

Every rule here abstains when it does not know. That asymmetry is the point:
a wrong rejection removes the only candidate for an ingredient and turns a
visibly wrong price into a silently missing one, which is harder to notice and
worse. So the tests care at least as much about what is NOT rejected.
"""

import pytest

from bonuschef.portal.classification import (
    judge,
    leaf_names_ingredient,
    normalise,
    rank,
    wants_ambient,
    wants_fresh,
)
from bonuschef.utils.ah_recipes import ProductHit


def hit(wid, title, dept="", path=()):
    return ProductHit(
        webshop_id=wid, title=title, department=dept, taxonomy_path=tuple(path)
    )


# --- the case this change exists for --------------------------------------


def test_fresh_dill_is_not_satisfied_by_dried_dill():
    """The originating bug. "verse dille" resolved to Verstegen Dille, which is
    dried dill in a glass jar in the spice aisle. AH classifies the two
    differently and always has:

        AH Dille         Vers       ... > Verse kruiden
        Verstegen Dille  Houdbaar   ... > Gedroogde kruiden > Dille
    """
    assert judge("verse dille", "Houdbaar").accepted is False
    assert judge("verse dille", "Vers").accepted is True


def test_an_unqualified_ingredient_accepts_either_form():
    """ "dille" with no adjective has not expressed a preference. Rejecting
    dried dill for it would invent a requirement the recipe never stated."""
    assert judge("dille", "Houdbaar").accepted is True
    assert judge("dille", "Vers").accepted is True


def test_a_napkin_does_not_resolve_a_carrot():
    """ "AH Vormservet wortel" is a carrot-printed paper napkin, and it
    genuinely resolved "wortel" in the live database, because the word appears
    in the product name."""
    assert judge("wortel", "Non Food").accepted is False


@pytest.mark.parametrize(
    "ingredient",
    ["kropje babyromainesla", "runderbouillon van tablet", "wortel", "ei"],
)
def test_no_food_ingredient_accepts_a_non_food_product(ingredient):
    """All three of these were found linked to non-food products in a live
    audit: cough syrup, menstrual painkillers and a napkin."""
    assert judge(ingredient, "Non Food").accepted is False


# --- abstention ------------------------------------------------------------


def test_an_unclassified_product_is_not_rejected():
    """AH does not classify everything. Absence of evidence is not evidence."""
    j = judge("verse dille", "")
    assert j.accepted is True
    assert "not classified" in j.reason


def test_frozen_satisfies_a_request_for_fresh():
    """Frozen spinach is a reasonable answer to fresh spinach in a way that a
    jar of dried dill is not to fresh dill."""
    assert judge("verse spinazie", "Diepvries").accepted is True


def test_a_keeping_form_is_not_satisfied_by_the_fresh_aisle():
    assert judge("gedroogde oregano", "Vers").accepted is False
    assert judge("gedroogde oregano", "Houdbaar").accepted is True


def test_near_food_is_not_rejected():
    """Near Food is a real food department - it is not Non Food, and the rule
    must not collapse the two on a substring."""
    assert judge("kauwgom", "Near Food").accepted is True


def test_a_rejection_says_why():
    """The reason is shown to a person reviewing the queue."""
    assert "fresh" in judge("verse dille", "Houdbaar").reason
    assert "non-food" in judge("wortel", "Non Food").reason


# --- form words ------------------------------------------------------------


@pytest.mark.parametrize("name", ["verse dille", "Verse Dille", "koelverse gyoza"])
def test_fresh_is_recognised_regardless_of_case(name):
    assert wants_fresh(name) is True


def test_a_word_merely_containing_vers_is_not_a_request_for_fresh():
    """ "Verstegen" starts with "vers". Matching on substrings rather than
    words would make the brand name itself a request for fresh produce."""
    assert wants_fresh("Verstegen dille") is False
    assert wants_fresh("diverse kruiden") is False


def test_ambient_words_are_recognised():
    assert wants_ambient("gedroogde tijm") is True
    assert wants_ambient("tomaten uit blik") is True
    assert wants_ambient("verse tijm") is False


# --- the taxonomy leaf -----------------------------------------------------


@pytest.mark.parametrize(
    ("ingredient", "leaf"),
    [
        ("witte kaas", "Witte kaas"),
        ("gerookte zalm", "Gerookte zalm"),
        ("slagroom", "Slagroom"),
        ("crème fraîche", "Creme fraiche"),
    ],
)
def test_the_leaf_names_the_ingredient(ingredient, leaf):
    """AH names its taxonomy leaves the way recipes name ingredients. Accents
    and case must not break the coincidence."""
    assert leaf_names_ingredient(ingredient, leaf) is True


def test_a_broader_leaf_does_not_count_as_naming_it():
    """ "bladpeterselie" sits under "Verse kruiden". The taxonomy is coarser
    than the ingredient, which is not the same as agreeing with it."""
    assert leaf_names_ingredient("bladpeterselie", "Verse kruiden") is False


def test_an_empty_leaf_never_matches():
    assert leaf_names_ingredient("dille", "") is False
    assert leaf_names_ingredient("", "Verse kruiden") is False


# --- ranking ---------------------------------------------------------------


def test_the_named_candidate_is_preferred():
    candidates = [
        hit(1, "AH Mosterd dille saus", "Houdbaar", ("Sauzen", "Mosterd")),
        hit(2, "AH Witte kaas 40+", "Vers", ("Kaas", "Witte kaas")),
    ]
    assert [c.webshop_id for c in rank("witte kaas", candidates)] == [2, 1]


def test_ranking_never_drops_a_candidate():
    """It reorders. A candidate no leaf names is not thereby wrong."""
    candidates = [hit(1, "a", "Vers", ("X",)), hit(2, "b", "Vers", ("Y",))]
    assert len(rank("nothing matches this", candidates)) == 2


def test_ranking_is_stable_when_nothing_is_named():
    """AH's own relevance ordering must survive underneath, or this would
    silently replace a good ranking with an arbitrary one."""
    candidates = [hit(i, f"p{i}", "Vers", ("X",)) for i in range(6)]
    assert [c.webshop_id for c in rank("unrelated", candidates)] == list(range(6))


def test_ranking_preserves_relative_order_among_the_named():
    named = [hit(1, "a", "Vers", ("Dille",)), hit(2, "b", "Vers", ("Dille",))]
    other = [hit(3, "c", "Vers", ("Sauzen",))]
    assert [c.webshop_id for c in rank("dille", other + named)] == [1, 2, 3]


def test_ranking_an_empty_list_is_not_an_error():
    assert rank("dille", []) == []


# --- normalisation ---------------------------------------------------------


def test_normalise_strips_accents_case_and_punctuation():
    assert normalise("Crème Fraîche!") == "creme fraiche"
    assert normalise("  MELK  ") == "melk"
    assert normalise(None) == ""
