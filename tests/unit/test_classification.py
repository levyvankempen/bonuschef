"""Whether a product plausibly satisfies an ingredient.

Every rule here abstains when it does not know. That asymmetry is the point:
a wrong rejection removes the only candidate for an ingredient and turns a
visibly wrong price into a silently missing one, which is harder to notice and
worse. So the tests care at least as much about what is NOT rejected.
"""

import pytest

from bonuschef.portal.classification import (
    _same_word,
    cohort,
    head_noun_match,
    is_own_brand,
    judge,
    names_a_brand,
    score,
    without_packaging,
    leaf_names_ingredient,
    normalise,
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


# --- normalisation ---------------------------------------------------------


def test_normalise_strips_accents_case_and_punctuation():
    assert normalise("Crème Fraîche!") == "creme fraiche"
    assert normalise("  MELK  ") == "melk"
    assert normalise(None) == ""


# --- scoring and the cohort ------------------------------------------------


def test_the_shallot_case():
    """The one this was built for. AH's search puts "Boursin Sjalot &
    bieslook" - a cream cheese - first for "sjalot", ahead of the actual
    shallots. Neither shallot's leaf is "Sjalot" (both are "Ui"), so the leaf
    preference alone never fired.

    What separates them is that the two real ones agree with each other and
    the Boursin does not.
    """
    cands = [
        hit(1, "Boursin Sjalot & bieslook", "Vers", ("Kaas", "Roomkaas")),
        hit(2, "AH Biologisch Sjalotten", "Vers", ("Groente", "Ui")),
        hit(3, "AH Sjalotten", "Vers", ("Groente", "Ui")),
    ]
    kept = {c.webshop_id for c in cohort("sjalot", cands)}
    assert 1 not in kept, "the cream cheese is still proposed as a shallot"
    assert kept == {2, 3}, "both real shallots must survive - cheapest wins later"


def test_interchangeable_products_are_all_kept():
    """Keeping several is deliberate: which is cheapest changes daily, and
    that is the point of the whole application."""
    cands = [
        hit(1, "AH Gele uien", "Vers", ("Groente", "Ui")),
        hit(2, "AH Rode uien", "Vers", ("Groente", "Ui")),
    ]
    assert len(cohort("ui", cands)) == 2


def test_flour_is_not_cauliflower_rice():
    """A prefix match made "bloem" (flour) match "Bloemkoolrijst" (cauliflower
    rice). Dutch plurals are allowed; prefixes are not."""
    assert _same_word("bloem", "bloemkoolrijst") is False
    assert _same_word("kaas", "kaasblokjes") is False


@pytest.mark.parametrize(
    ("singular", "plural"),
    [
        ("sjalot", "sjalotten"),  # final consonant doubles
        ("ui", "uien"),
        ("aardappel", "aardappelen"),
        ("tomaat", "tomaten"),  # doubled vowel shortens
        ("peer", "peren"),
        ("boon", "bonen"),
        ("kool", "kolen"),
        ("kaas", "kazen"),  # ...and the s voices
        ("roos", "rozen"),
        ("saus", "sauzen"),
        ("brief", "brieven"),  # f voices without the vowel changing
    ],
)
def test_dutch_plurals_of_ordinary_ingredients(singular, plural):
    """Every one of these is something a recipe asks for and AH sells under
    the plural. Missing them means the head-noun signal never fires for half
    the vegetable aisle."""
    assert _same_word(singular, plural) is True


def test_the_head_noun_distinguishes_being_from_mentioning():
    """Dutch puts the head noun last. "AH Sjalotten" is shallots; "Boursin
    Sjalot & bieslook" merely tastes of them."""
    assert head_noun_match("sjalot", "AH Sjalotten") is True
    assert head_noun_match("sjalot", "Boursin Sjalot & bieslook") is False


def test_own_brand_words_do_not_count_as_specificity():
    """ "AH" and "Biologisch" are on half the catalogue. Counting them as
    content would make every own-brand product look more specific."""
    plain = hit(1, "AH Courgette", "Vers", ("Groente", "Courgette"))
    organic = hit(2, "AH Biologisch Courgette", "Vers", ("Groente", "Courgette"))
    assert score("courgette", plain, [plain, organic], 0) == pytest.approx(
        score("courgette", organic, [plain, organic], 0)
    )


def test_an_unclassified_field_does_not_narrow_a_recognisable_winner():
    """Narrowing on no evidence is the one thing every rule here refuses.

    Once the winner is recognisably the ingredient, a missing taxonomy on the
    others is not grounds to drop them - there is no "same kind" to compare
    against, so everything stays.
    """
    cands = [
        hit(1, "AH Dille", "Vers", ("Kruiden", "Verse kruiden")),
        hit(2, "AH Biologisch Dille", "Vers", ("Kruiden", "Verse kruiden")),
    ]
    assert len(cohort("dille", cands)) == 2


def test_nothing_recognisable_proposes_nothing():
    """An unrecognisable best candidate withholds the whole cohort.

    Ranking always produces a winner, even when every candidate is wrong, and
    a cost built on a wrong product is worse than a missing one because it
    looks right. Neither of these is dille by name or by taxonomy.
    """
    cands = [hit(1, "Iets", ""), hit(2, "Iets anders", "")]
    assert cohort("dille", cands) == []


def test_the_floor_withholds_the_matches_that_prompted_it():
    """Both shipped to production and both looked plausible: same department,
    both food, one shared word. Nothing downstream objected, which is exactly
    why the test has to happen here.
    """
    assert (
        cohort(
            "blauwe kaas-blokjes",
            [hit(1, "AH Blauwe bessen", "Vers", ("Fruit", "Blauwe bessen"))],
        )
        == []
    )
    assert (
        cohort(
            "salade-uitjes", [hit(1, "AH Ei salade", "Vers", ("Salades", "Salades"))]
        )
        == []
    )


def test_the_floor_keeps_a_match_named_only_by_its_head_noun():
    """Either evidence suffices. The leaf need not name the ingredient when the
    title does, or this would withhold most of the own-brand range."""
    assert (
        cohort(
            "broccoli",
            [hit(1, "AH Biologisch Broccoli", "Vers", ("Groente", "Broccoli"))],
        )
        != []
    )


def test_a_diminutive_still_finds_the_plain_noun():
    """Recipes are written in diminutives - "uitjes", "tomaatjes" - while the
    shelf label is the plain noun. Without this the floor withholds them."""
    assert (
        cohort("bosuitje", [hit(1, "AH Bosui", "Vers", ("Groente", "Verse kruiden"))])
        != []
    )


def test_a_compound_is_recognised_by_the_general_term():
    """Dutch puts the head of a compound last, so runderbouillon IS a bouillon.
    The leaf is frequently the general term and the recipe the specific one."""
    assert (
        cohort(
            "runderbouillon van tablet",
            [hit(1, "Bouillonblokjes", "Houdbaar", ("Soepen", "Bouillon"))],
        )
        != []
    )


def test_the_cohort_of_nothing_is_nothing():
    assert cohort("dille", []) == []


def test_a_single_candidate_survives():
    cands = [hit(1, "AH Dille", "Vers", ("Kruiden", "Verse kruiden"))]
    assert len(cohort("verse dille", cands)) == 1


# --- packaging, brand and form: cases reported from the running system -----


@pytest.mark.parametrize(
    ("ingredient", "stripped"),
    [
        ("cannellinibonen in blik", "cannellinibonen"),
        ("mierikswortel in pot", "mierikswortel"),
        ("runderbouillon van tablet", "runderbouillon"),
        ("jalapeñoplakjes in pot", "jalapenoplakjes"),
    ],
)
def test_container_words_are_stripped(ingredient, stripped):
    """The container word poisons the retailer's search - it matches the
    packaging rather than the food:

        "cannellinibonen in blik"   -> tuna, corn, pineapple
        "cannellinibonen"           -> AH Terra Cannellini bonen
        "runderbouillon van tablet" -> Ibuprofen, Paracetamol (tabletten)
    """
    assert without_packaging(ingredient) == stripped


@pytest.mark.parametrize(
    "ingredient", ["tonijn in olie", "tonijn in water", "verse dille"]
)
def test_meaningful_qualifiers_are_not_stripped(ingredient):
    """Tuna in oil and tuna in water are different products. Only pure
    containers go; "" means nothing was removed."""
    assert without_packaging(ingredient) == ""


def test_scoring_reads_past_the_container():
    """The head noun of "mierikswortel in pot" is "pot", so every signal that
    reads the last word saw the container and never fired. Kühne Mierikswortel
    lost to two jars of pesto that agreed with each other about being pesto."""
    horseradish = hit(1, "Kühne Mierikswortel", "Houdbaar", ("Conserven", "Gember"))
    pesto_a = hit(2, "AH Groene pesto", "Houdbaar", ("Sauzen", "Pesto in pot"))
    pesto_b = hit(3, "AH Pesto rosso", "Houdbaar", ("Sauzen", "Pesto in pot"))
    cands = [pesto_a, pesto_b, horseradish]
    assert cohort("mierikswortel in pot", cands) == [horseradish]


def test_frozen_is_a_form_an_ingredient_can_ask_for():
    """ "diepvries tuinerwten" means the freezer aisle."""
    assert judge("diepvries tuinerwten", "Diepvries").accepted is True
    assert judge("diepvries tuinerwten", "Houdbaar").accepted is False
    assert judge("diepvries tuinerwten", "Vers").accepted is False


@pytest.mark.parametrize(
    "brand", ["AH", "AH Biologisch", "AH Excellent", "AH Terra", "De Zaanse Hoeve"]
)
def test_the_retailers_own_labels_are_recognised(brand):
    """De Zaanse Hoeve does not say "AH" and is their dairy line: crème
    fraîche is €1.09 there against €2.39 for the Arla that was being
    chosen."""
    assert is_own_brand(brand) is True


@pytest.mark.parametrize("brand", ["Arla", "De Cecco", "Kühne", "Bonduelle"])
def test_other_brands_are_not_own_label(brand):
    assert is_own_brand(brand) is False


def test_the_brand_preference_never_decides_what_kind_to_propose():
    """With brand in the kind decision, an own-brand product of the WRONG kind
    won: "mierikswortel in pot" chose AH Groene pesto over Kühne
    Mierikswortel, and "runderbouillon van tablet" chose a bar of white
    chocolate.

    Constructed so the preference would actually flip the outcome - the two
    candidates differ only on genericness - 0.65 apart, less than the 1.0 the
    brand preference is worth - so neither head-noun matches and the flip is real.
    """
    own_brand_wrong = ProductHit(
        webshop_id=1,
        title="AH Witte chocolade reep",
        brand="AH",
        department="Houdbaar",
        taxonomy_path=("Snoep", "Chocolade"),
    )
    other_brand_right = ProductHit(
        webshop_id=2,
        title="Bouillonblokjes",
        brand="Kleinste Soepfabriek",
        department="Houdbaar",
        taxonomy_path=("Soepen", "Bouillon"),
    )
    pair = [own_brand_wrong, other_brand_right]

    # The preference really would prefer the chocolate...
    assert score("runderbouillon", own_brand_wrong, pair, 0) > score(
        "runderbouillon", other_brand_right, pair, 1
    )
    # ...and the kind decision must ignore it anyway.
    assert [c.webshop_id for c in cohort("runderbouillon van tablet", pair)] == [2]


def test_the_own_brand_preference_applies_within_a_kind():
    """Where two products are the same kind, the own label is preferred -
    which is what was asked for, and it is usually the cheaper one."""
    own = ProductHit(
        webshop_id=1,
        title="AH Excellent Orecchiette bio",
        brand="AH Excellent",
        department="Houdbaar",
        taxonomy_path=("Pasta", "Schelpjes"),
    )
    other = ProductHit(
        webshop_id=2,
        title="De Cecco Orecchiette",
        brand="De Cecco",
        department="Houdbaar",
        taxonomy_path=("Pasta", "Schelpjes"),
    )
    assert score("orecchiette pasta", own, [own, other], 0) > score(
        "orecchiette pasta", other, [own, other], 0
    )


def test_a_recipe_that_names_a_brand_keeps_it():
    """ "Verstegen dille" means Verstegen. Preferring the own label there would
    override something the recipe was explicit about."""
    assert names_a_brand("verstegen dille") is True
    assert names_a_brand("crème fraîche") is False


@pytest.mark.parametrize(
    ("ingredient", "title", "matches"),
    [
        ("cannellinibonen", "AH Terra Cannellini bonen", True),
        ("kipfilet", "AH Kip filet", True),
        ("cannellinibonen", "Statesman Tonijn stukken in water", False),
        ("bladpeterselie", "AH Platte peterselie", False),
        ("room", "AH Slagroom", False),
        ("bloem", "AH Bloemkoolrijst", False),
    ],
)
def test_dutch_compounds_split_across_a_product_name(ingredient, title, matches):
    """Dutch writes compounds as one word where a product name splits them.
    Without this "cannellinibonen" does not match its own name, and a tin of
    tuna outscores the bean.

    The negatives matter as much: joining must not let "room" match
    "Slagroom", which is the prefix mistake in another form.
    """
    assert head_noun_match(ingredient, title) is matches


# --- the floor, measured against what a human confirmed ---------------------

# Every link a human confirmed in production, as of 2026-09-20. The floor
# withholds a product when it cannot recognise it, so the only question that
# decides whether it may ship is how many of these it would have thrown away.
#
# Taxonomy is not stored in the warehouse - it comes from the live search at
# resolution time - so these carry the title only. That makes this a LOWER
# bound: the floor also accepts on the leaf, which rescues at least
# "iets kruimige aardappel" (leaf Aardappelen).
CONFIRMED_LINKS = [
    ("bloem", "AH Tarwebloem"),
    ("friszoete appel", "AH Appels"),
    ("milde olijfolie", "AH Olijfolie mild"),
    ("plantaardige kipbraadworst", "AH Scharrel kipbraadworst 4 stuks"),
    ("plantenmargarine lactosevrij", "AH Terra Plantaardige margarine"),
    ("rozijnen", "AH Rozijnen"),
    ("zuurkool", "AH Zuurkool"),
]


@pytest.mark.parametrize(("ingredient", "title"), CONFIRMED_LINKS)
def test_the_floor_keeps_what_a_human_confirmed(ingredient, title):
    """A human looked at this pairing and said yes. Withholding it is a
    regression no matter how defensible the rule that did it sounds."""
    assert cohort(ingredient, [hit(1, title, "")]) != []


def test_a_synonym_the_floor_cannot_see_is_a_known_loss():
    """ "bospaddenstoelenfond" is a confirmed link to "AH Bouillon paddenstoel",
    and the floor drops it: a fond IS a bouillon, but no spelling of either
    word contains the other, so there is nothing to recognise it by.

    Recorded rather than worked around. Fixing it needs a word-synonym
    mechanism, which this project does not have - ah_ingredient_aliases, which
    sounds like it, maps duplicate concept IDs and would not help. This test
    exists so that the day synonyms arrive, the failure points at the reason.
    """
    assert cohort("bospaddenstoelenfond", [hit(1, "AH Bouillon paddenstoel", "")]) == []


# --- water is not shopping --------------------------------------------------


@pytest.mark.parametrize(
    "ingredient",
    [
        "water",
        "warm water",
        "lauwwarm water",
        "kokend water",
        "kraanwater",
        "ijswater",
    ],
)
def test_water_resolves_to_nothing(ingredient):
    """What a recipe means by water comes out of a tap.

    Two of these were live and absurd: "warm water" and "lauwwarm water" both
    resolved to tinned tuna, because a title like "Statesman Tonijn stukken in
    water" ends on the word "water" and the head-noun rule therefore matched
    perfectly. Both food, both ambient, nothing objected.
    """
    assert cohort(ingredient, [hit(1, "Statesman Tonijn stukken in water", "")]) == []


@pytest.mark.parametrize(
    ("ingredient", "title"),
    [
        ("tonijn in water in blik", "John West Tonijn in water"),
        ("tonijnstukken in water", "Princes Tonijnstukken in water"),
        ("waterkers", "AH Biologisch Waterkers"),
        ("mini-watermeloen", "AH Mini watermeloen"),
    ],
)
def test_a_product_that_merely_mentions_water_is_untouched(ingredient, title):
    """The rule asks whether the ingredient REDUCES to water, not whether it
    says the word. Tuna packed in water is a product."""
    assert cohort(ingredient, [hit(1, title, "")]) != []


# --- an explicit refusal outranks a perfect name match ----------------------


@pytest.mark.parametrize(
    ("ingredient", "title"),
    [
        ("gezouten pinda's", "AH Pinda's ongezouten"),
        ("gezouten cashewnoten", "AH Cashewnoten ongezouten"),
        ("gezouten macadamianoten", "AH Ongezouten macadamiamix"),
        ("geroosterde amandelen", "AH Terra Ongebrande amandelen"),
    ],
)
def test_the_opposite_of_what_was_asked_is_refused(ingredient, title):
    """Six of these were live. The head noun, the leaf and the department all
    matched - it is the same nut - and the packet is the one thing the recipe
    ruled out."""
    assert cohort(ingredient, [hit(1, title, "")]) == []


@pytest.mark.parametrize(
    ("ingredient", "title"),
    [
        ("gepelde ongezouten pistachenoten", "AH Pistachenoten"),
        ("ongesneden snijbonen", "AH Snijbonen"),
        ("ongezouten roomboter", "AH Roomboter ongezouten"),
        ("gezouten pinda's", "AH Pinda's gezouten"),
    ],
)
def test_silence_about_an_attribute_is_not_a_refusal(ingredient, title):
    """Only an explicit opposite counts. Refusing every product that fails to
    mention an attribute would reject most of the catalogue."""
    assert cohort(ingredient, [hit(1, title, "")]) != []


# --- a modifier is not a head ----------------------------------------------


def test_a_compound_is_matched_on_its_head_not_on_any_word():
    """ "salade-ui" is a kind of ui; "salade" is only what kind. Matching on
    any word made "AH Selleriesalade" a specialisation of it, which is how a
    spring onion came to be priced as a tub of celery salad."""
    assert (
        cohort("salade-ui", [hit(1, "AH Selleriesalade", "Vers", ("Salades",))]) == []
    )


def test_the_head_rule_still_admits_a_real_specialisation():
    """The direction exists for "bloem" against "AH Tarwebloem", where the
    shelf is the specific term. That must survive."""
    assert cohort("bloem", [hit(1, "AH Tarwebloem", "")]) != []


def test_ice_is_a_product_and_is_not_withheld():
    """It looks like the same class - you make it from tap water - and AH
    sells it, so this is a correct match the water rule would have thrown
    away. The rule is about ingredients with no product, not about ones
    somebody could make themselves; by that reading it would take stock and
    bread with it.
    """
    assert cohort("ijsblokjes", [hit(1, "AH IJsblokjes", "")]) != []


def test_a_trailing_participle_is_a_qualifier_not_the_head():
    """AH writes the preparation after the noun: "Kaas geraspt", "koriander
    gemalen". A hand-kept list of such words is always one product behind,
    because Dutch builds them productively: "ge" plus a -d, -t or -en ending
    makes a past participle out of any verb. Recognising the shape means the
    list never has to be extended for the next one."""
    assert head_noun_match("geraspte kaas", "AH Kaas geraspt") is True
    assert (
        head_noun_match("gemalen koriander", "Verstegen Strooier koriander gemalen")
        is True
    )
    assert head_noun_match("gesneden sperziebonen", "AH Sperziebonen gesneden") is True


def test_a_participle_shaped_noun_is_still_a_noun():
    """Shape is a heuristic, so it must not eat words that merely start with
    "ge". "Gehakt" and "gerst" are what is being sold, not how it was cut."""
    assert head_noun_match("gehakt", "AH Gehakt") is True
    assert head_noun_match("gerst", "AH Gerst") is True


def test_a_trailing_colour_is_a_qualifier_not_the_head():
    """ "AH Stokbrood wit" is bread, graded by colour. Colours are a closed
    class - unlike the participles above, nobody invents a new one - so they
    are listed rather than recognised by shape."""
    assert (
        head_noun_match("vers stokbrood", "AH Biologisch Frans stokbrood wit") is True
    )
    assert head_noun_match("witlof", "AH Witlof") is True


def test_a_trailing_noun_is_not_a_qualifier_however_late_it_sits():
    """The guard this rule replaced tried to answer positionally: allow the
    head to sit a word or two from the end. That admitted "Boursin Sjalot &
    bieslook" as shallots, because the head is one from the end in the cream
    cheese and in "stokbrood wit" alike. The difference is grammatical, not
    positional: "wit" is an adjective and "bieslook" is a noun."""
    assert head_noun_match("sjalot", "Boursin Sjalot & bieslook") is False
    assert head_noun_match("tomaat", "AH Mozzarella tomaat basilicum") is False


def test_a_leaf_naming_several_things_is_read_as_a_list():
    """Taxonomy leaves are written "Kruiden, specerijen" - two nouns, not a
    compound. Reading the whole string as one name failed to place any
    ingredient under such a leaf, which is most of the seasoning aisle."""
    assert leaf_names_ingredient("koriander", "Kruiden, specerijen") is False
    assert leaf_names_ingredient("specerijen", "Kruiden, specerijen") is True
    assert leaf_names_ingredient("kruiden", "Kruiden, specerijen") is True
