"""Does this product plausibly satisfy this ingredient?

Resolution has until now compared names. A name says what a product is
called; the retailer's taxonomy says what it *is*, and the two disagree often
enough to matter:

    verse dille  ->  Verstegen Dille   dried, in a jar, in the spice aisle
    wortel       ->  AH Vormservet wortel   a carrot-printed paper napkin

Everything here is a pure function over a product's classification and an
ingredient's name. No network, no database: this runs inside the resolution
asset, and it must be testable without either.

The rules are deliberately timid. Each one abstains when it does not know,
because a wrong rejection removes the only candidate for an ingredient and
turns a visibly wrong price into a silently missing one, which is worse.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from bonuschef.utils.ah_recipes import (
    DEPARTMENT_FRESH,
    DEPARTMENT_FROZEN,
    DEPARTMENT_NON_FOOD,
)

# Words by which a recipe states the form it wants. Only these two directions
# are checked, because they are the two the departments actually distinguish.
_WANTS_FRESH = ("verse", "vers", "koelverse", "koelvers", "rauwe")
_WANTS_AMBIENT = ("gedroogde", "gedroogd", "gemalen", "gepoederd", "blik", "pot")
_WANTS_FROZEN = ("diepvries", "diepvriesgroente", "bevroren")

# Fresh things are sold frozen too, and a recipe asking for fresh spinach is
# not wronged by frozen spinach the way it is by a jar of dried dill.
_FRESH_ENOUGH = frozenset({DEPARTMENT_FRESH, DEPARTMENT_FROZEN})

# Words naming the container rather than the food. Stripping them is the
# single most effective thing in this module, because the retailer's search
# matches them: "cannellinibonen in blik" returns tuna, corn and pineapple,
# while "cannellinibonen" returns AH Terra Cannellini bonen. "runderbouillon
# van tablet" returns Ibuprofen and Paracetamol - both sold as tabletten.
#
# Only pure containers. "in olie" and "in water" stay, because tuna in oil and
# tuna in water are different products and a recipe asking for one means it.
_PACKAGING = (
    "in blik",
    "uit blik",
    "in een blik",
    "blikje",
    "in pot",
    "uit pot",
    "in een pot",
    "potje",
    "van tablet",
    "in tablet",
    "tabletten",
    "in zakje",
    "zakje",
    "in pak",
    "pakje",
    "uit de diepvries",
)


@dataclass(frozen=True)
class Judgement:
    """Why a candidate was kept or rejected, in words a person can read."""

    accepted: bool
    reason: str = ""


def normalise(text: str | None) -> str:
    """Casefold, strip accents and punctuation, collapse whitespace."""
    folded = unicodedata.normalize("NFKD", (text or "").casefold())
    stripped = "".join(c for c in folded if not unicodedata.combining(c))
    return re.sub(r"[^a-z0-9]+", " ", stripped).strip()


def _words(text: str) -> set[str]:
    return set(normalise(text).split())


def wants_fresh(ingredient_name: str) -> bool:
    return bool(_words(ingredient_name) & set(_WANTS_FRESH))


def wants_ambient(ingredient_name: str) -> bool:
    return bool(_words(ingredient_name) & set(_WANTS_AMBIENT))


def wants_frozen(ingredient_name: str) -> bool:
    return bool(_words(ingredient_name) & set(_WANTS_FROZEN))


def without_packaging(ingredient_name: str) -> str:
    """The ingredient with any container words removed.

    Returns "" when nothing was removed, so a caller can tell whether a second
    search is worth spending a request on.
    """
    text = normalise(ingredient_name)
    stripped = text
    for phrase in _PACKAGING:
        stripped = re.sub(rf"\b{re.escape(phrase)}\b", " ", stripped)
    stripped = re.sub(r"\s+", " ", stripped).strip()
    return "" if stripped == text or not stripped else stripped


def judge(ingredient_name: str, department: str) -> Judgement:
    """Whether a product from this department can satisfy this ingredient.

    Abstains - accepts - whenever the department is unknown or the ingredient
    states no form. Silence is not a requirement: "dille" unqualified should
    still match dried dill, because the recipe did not ask for otherwise.
    """
    dept = (department or "").strip()
    if not dept:
        return Judgement(True, "not classified")

    if dept == DEPARTMENT_NON_FOOD:
        return Judgement(False, "non-food product cannot satisfy a food ingredient")

    if wants_fresh(ingredient_name) and dept not in _FRESH_ENOUGH:
        return Judgement(False, f"ingredient asks for fresh; product is {dept}")

    if wants_frozen(ingredient_name) and dept != DEPARTMENT_FROZEN:
        return Judgement(False, f"ingredient asks for frozen; product is {dept}")

    if wants_ambient(ingredient_name) and dept == DEPARTMENT_FRESH:
        return Judgement(
            False, f"ingredient asks for a keeping form; product is {dept}"
        )

    return Judgement(True, "")


def leaf_names_ingredient(ingredient_name: str, taxonomy_leaf: str) -> bool:
    """Whether the taxonomy calls this product the thing the recipe asked for.

    The surprise of the investigation: AH names its taxonomy leaves the way
    recipes name ingredients - "Witte kaas", "Gerookte zalm", "Slagroom". Where
    they coincide it is a far better signal than a title substring, because a
    title containing "witte kaas" may be a dressing or a salami.
    """
    ing, leaf = normalise(ingredient_name), normalise(taxonomy_leaf)
    if not ing or not leaf:
        return False
    if ing == leaf:
        return True

    # AH writes a leaf as a list of the names a thing goes by: "Koriander,
    # ketoembar", "Afbakbroodjes wit, mix", "Bleekselderij, selderij". Demanding
    # the whole string match throws that away - "gemalen koriander" against a
    # leaf that says koriander in so many words was being refused.
    #
    # Each part is matched as a name in its own right, head noun and all, so
    # "gemalen koriander" reaches "koriander" the same way it would reach a
    # one-word leaf. Split the raw leaf, not the normalised one: normalise()
    # drops punctuation, so splitting afterwards finds no comma left to split
    # on and silently reads "Bleekselderij, selderij" as one two-word name.
    parts = [normalise(part) for part in taxonomy_leaf.split(",")]
    parts = [part for part in parts if part]
    if len(parts) > 1:
        return any(_names_the_same_thing(ing, part) for part in parts)
    return _names_the_same_thing(ing, leaf)


def _names_the_same_thing(ingredient_name: str, leaf: str) -> bool:
    """Whether one taxonomy name is what this ingredient is called.

    The ingredient's head noun against the leaf's, so "gemalen koriander" is
    koriander and "verse tijm" is tijm. Not a substring test: that would make
    "bloem" a "bloemkool" again, which is the bug the prefix ban exists for.
    """
    if ingredient_name == leaf:
        return True
    ing_head = _head_noun(ingredient_name)
    leaf_words = _content_words(leaf)
    if not ing_head or not leaf_words:
        return False
    return _same_word(ing_head, _title_head(leaf_words))


# Words that describe a product without being what it is. "AH" and
# "Biologisch" appear on half the catalogue; letting them count as content
# makes every own-brand product look more specific than it is.
_QUALIFIERS = frozenset(
    {"ah", "biologisch", "bio", "verse", "vers", "de", "het", "een"}
)

# There is deliberately no confidence floor *on the score*.
#
# One was tried and measured against the human-confirmed links, and the scores
# do not separate. Products a person confirmed score as low as -1.20
# ("chilivlokken"), while obviously-correct matches that simply were not in the
# confirmed set score 10.00 ("broccoli" -> AH Biologisch Broccoli). Any floor
# that removed a bad answer removed good ones with it: at 0.0 it cost
# arachideolie, bosuitje and chilivlokken their only correct product.
#
# So the score orders candidates and never rejects them. Rejection lives in
# recognisable(), which asks whether a candidate is the same THING as the
# ingredient rather than how good a match it is - a question naming can answer
# and a number cannot.


def _content_words(text: str) -> list[str]:
    return [w for w in normalise(text).split() if w not in _QUALIFIERS]


# Dutch diminutive endings, longest first so "bosuitje" loses "tje" and not
# just "je". The plural forms are here too: a recipe writes "uitjes" far more
# often than "uitje".
_DIMINUTIVES = (
    "etjes",
    "etje",
    "tjes",
    "tje",
    "pjes",
    "pje",
    "kjes",
    "kje",
    "jes",
    "je",
)


def _undiminutive(word: str) -> set[str]:
    """The noun a Dutch diminutive was built from, if it is one.

    Recipes are written in diminutives constantly - "uitjes", "worstjes",
    "tomaatjes" - while the shelf label is the plain noun. Without this,
    "bosuitje" does not match "Bosui" and a correct product is withheld.

    Returns a set because the shortening is ambiguous: "bolletje" gives both
    "boll" and, after collapsing the doubled consonant, "bol". Let the caller
    try both rather than guess here.
    """
    stems: set[str] = set()
    for ending in _DIMINUTIVES:
        if not word.endswith(ending):
            continue
        stem = word[: -len(ending)]
        # Every ending is tried, never just the longest: the -t- in "tomaatje"
        # belongs to the stem, so stripping "tje" gives the fragment "tomaa"
        # and only stripping "je" gives "tomaat". Which one is real depends on
        # the word, so keep both and let the comparison decide.
        #
        # Two characters, not three: "uitje" -> "ui" and "eitje" -> "ei" are
        # the cases this function exists for. Over-generating is safe because
        # the caller tests the stems for equality, never as a prefix.
        if len(stem) < 2:
            continue
        stems.add(stem)
        # Dutch doubles the consonant before -etje: bonnetje -> bon.
        if len(stem) > 3 and stem[-1] == stem[-2]:
            stems.add(stem[:-1])
    return stems


def _base_forms(word: str) -> set[str]:
    return {word} | _undiminutive(word)


def _same_word(a: str, b: str) -> bool:
    """Whether two Dutch words are the same noun, allowing for plurals.

    Deliberately not a prefix match. Prefix matching made "bloem" (flour) match
    "Bloemkoolrijst" (cauliflower rice), which is how flour came to be
    resolved as a vegetable.
    """
    return any(_same_stem(x, y) for x in _base_forms(a) for y in _base_forms(b))


def _same_stem(a: str, b: str) -> bool:
    """The plural rules, applied to two words already stripped of diminutives."""
    if a == b:
        return True
    for suffix in ("en", "s", "n", "es"):
        if b == a + suffix or a == b + suffix:
            return True
    # sjalot/sjalotten: Dutch doubles a final consonant before -en.
    if len(a) > 3 and b == a + a[-1] + "en":
        return True
    if len(b) > 3 and a == b + b[-1] + "en":
        return True
    # peer/peren, boon/bonen, kool/kolen: a doubled vowel shortens before -en.
    # All three are ordinary ingredients, so this is not an edge case.
    if b in _dutch_plurals(a) or a in _dutch_plurals(b):
        return True
    if b == _voiced_plural(a) or a == _voiced_plural(b):
        return True
    return False


# Final s and f voice in the plural: kaas -> kazen, brief -> brieven. Both are
# ordinary ingredients, so this is not an edge case.
_VOICING = {"s": "z", "f": "v"}


def _dutch_plurals(word: str) -> set[str]:
    """Plurals of a word whose doubled vowel shortens: peer -> peren.

    Returns a set because the shortening and the voicing combine: kaas is
    ka+s, which shortens to "kasen" and voices to "kazen".
    """
    match = re.fullmatch(r"(.*?)(aa|ee|oo|uu)([bcdfghjklmnpqrstvwxz]+)", word)
    if not match:
        return set()
    stem, vowels, tail = match.groups()
    short = f"{stem}{vowels[0]}{tail}"
    forms = {short + "en"}
    if tail in _VOICING:
        forms.add(f"{stem}{vowels[0]}{_VOICING[tail]}en")
    return forms


def _voiced_plural(word: str) -> str:
    """brief -> brieven: the final consonant voices without the vowel changing."""
    if len(word) > 3 and word[-1] in _VOICING:
        return word[:-1] + _VOICING[word[-1]] + "en"
    return ""


def head_noun_match(ingredient_name: str, title: str) -> bool:
    """Whether the title *is* the ingredient rather than merely mentioning it.

    Dutch puts the head noun last. "AH Sjalotten" ends on it; "Boursin Sjalot
    & bieslook" uses the same word as a flavour qualifier in the middle, and
    is a cream cheese.
    """
    title_words, ingredient_words = (
        _content_words(title),
        _content_words(ingredient_name),
    )
    if not title_words or not ingredient_words:
        return False
    # The ingredient carries trailing qualifiers too - a recipe writes
    # "plantenmargarine lactosevrij" - so its head is found the same way.
    head = _title_head(ingredient_words)
    if _same_word(head, _title_head(title_words)):
        return True
    # Dutch writes compounds as one word where a product name splits them:
    # "cannellinibonen" against "AH Terra Cannellini bonen". Without this the
    # bean does not match its own name, and a tin of tuna outscores it.
    return _matches_compound(head, title_words)


# Words AH puts AFTER the noun, where Dutch would normally end the phrase:
# a grade ("Olijfolie mild"), a pack count ("kipbraadworst 4 stuks"), a
# production claim ("Tomaten bio"). Taking the last word as the head reads
# these as the product, so "milde olijfolie" failed to match "AH Olijfolie
# mild" - six of the nine human-confirmed links were lost this way.
_TRAILING_QUALIFIERS = frozenset(
    {
        "mild",
        "milde",
        "pittig",
        "pittige",
        "zacht",
        "zachte",
        "extra",
        "bio",
        "biologisch",
        "biologische",
        "vers",
        "verse",
        "naturel",
        "grof",
        "grove",
        "fijn",
        "fijne",
        "halfvol",
        "halfvolle",
        "mager",
        "magere",
        "vol",
        "volle",
        "licht",
        "lichte",
        "zoet",
        "zoete",
        "zout",
        "zoute",
        "ongezouten",
        "gezouten",
        "stuks",
        "stuk",
        "gram",
        "ml",
        "cl",
        "liter",
        "l",
        "kg",
        "g",
        "pak",
        "zak",
        "bos",
        "plakken",
        # Colours and grades: a closed class, unlike the participles that
        # _is_qualifier recognises by their shape.
        "wit",
        "witte",
        "bruin",
        "bruine",
        "rood",
        "rode",
        "groen",
        "groene",
        "geel",
        "gele",
        "zwart",
        "zwarte",
        "blond",
        "blonde",
        "naturel",
    }
)


def _is_qualifier(word: str) -> bool:
    """Whether a trailing word grades the noun rather than being it.

    Position alone cannot answer this, which an earlier attempt here got
    wrong: in "AH Biologisch Frans stokbrood wit" and "Boursin Sjalot &
    bieslook" the head sits one word from the end either way, and the
    difference is that "wit" is an adjective and "bieslook" is a noun. A
    positional window admitted the cream cheese as shallots.

    So, morphology first. A Dutch past participle - "ge" plus a -d, -t or -en
    ending - is a qualifier by its shape: gemalen, gesneden, gedroogd,
    geraspt, gerookt, and every one of their kind, without anybody listing
    them. That is the half of this that grows on its own, and it is the half
    that was costing real matches - "Verstegen Strooier koriander gemalen" was
    being refused for ending on a participle nobody had thought to enumerate.

    Then a closed class for the rest. Colours and grades genuinely are finite
    in a product title, unlike the participles.
    """
    if word in _TRAILING_QUALIFIERS or word.isdigit():
        return True
    return len(word) > 4 and word.startswith("ge") and word.endswith(("en", "d", "t"))


def _title_head(title_words: list[str]) -> str:
    """The title's head noun, looking past any trailing qualifiers.

    Stops at the first word from the end that names something rather than
    grading it. Never strips everything: a title that is nothing but
    qualifiers keeps its last word, because guessing further would be worse
    than the original rule.
    """
    words = list(title_words)
    while len(words) > 1 and _is_qualifier(words[-1]):
        words.pop()
    return words[-1]


def _matches_compound(head: str, title_words: list[str]) -> bool:
    """Whether a run of title words ending the title, joined, is the head word.

    Only runs that end the title: the head noun comes last, and a match in the
    middle is the flavour-qualifier case this exists to reject.
    """
    return any(
        _same_word(head, "".join(title_words[start:]))
        for start in range(len(title_words))
    )


# The retailer's own labels, including the ones that do not say "AH": De
# Zaanse Hoeve is their dairy line and is routinely the cheapest thing on the
# shelf - crème fraîche is €1.09 there against €2.39 for the Arla the system
# had been choosing.
_OWN_BRANDS = ("ah", "de zaanse hoeve", "perekop", "delicata", "smaakt")


def is_own_brand(brand: str) -> bool:
    """Whether a product is the retailer's own label."""
    normalised = normalise(brand)
    return any(normalised == b or normalised.startswith(b + " ") for b in _OWN_BRANDS)


def names_a_brand(ingredient_name: str) -> bool:
    """Whether the recipe asked for a particular brand.

    "Verstegen dille" means Verstegen. Preferring the own label there would
    override something the recipe was explicit about.
    """
    words = _words(ingredient_name)
    return any(all(part in words for part in b.split()) for b in _OWN_BRANDS) or bool(
        words & {"verstegen", "knorr", "honig", "maggi", "conimex"}
    )


def score(
    ingredient_name: str,
    candidate,
    siblings: list,
    position: int = 0,
    *,
    prefer_own_brand: bool = True,
) -> float:
    """How well a candidate answers an ingredient. Higher is better.

    Every term is explainable on purpose. A person correcting a match should
    be able to see why the system preferred what it did, and a rule nobody can
    explain is a rule nobody can fix.
    """
    # Score against what the ingredient IS, not how it is packaged. The head
    # noun of "mierikswortel in pot" is "pot", so every signal that reads the
    # last word saw the container and never fired.
    ingredient_name = without_packaging(ingredient_name) or ingredient_name
    leaf = getattr(candidate, "taxonomy_leaf", "")
    title = getattr(candidate, "title", "")
    total = 0.0

    if leaf_names_ingredient(ingredient_name, leaf):
        total += 5.0

    # Agreement between candidates. When three hits share a taxonomy leaf and
    # one does not, the odd one out is usually the mistake - which is exactly
    # the shape of "sjalot": two shallots under "Ui", one Boursin under
    # "Roomkaas".
    if leaf:
        agreeing = sum(
            1
            for s in siblings
            if normalise(getattr(s, "taxonomy_leaf", "")) == normalise(leaf)
        )
        if agreeing > 1:
            total += 2.0

    # Weighted above leaf consensus on purpose. A product whose head noun IS
    # the ingredient is stronger evidence than two other candidates agreeing
    # with each other: "mierikswortel" lost to two jars of pesto that agreed
    # they were pesto.
    if head_noun_match(ingredient_name, title):
        total += 4.0

    # Every word the title carries that the ingredient did not ask for is a
    # way the product might be something else.
    asked = set(_content_words(ingredient_name))
    total -= 0.4 * len([w for w in _content_words(title) if w not in asked])

    # Prefer the retailer's own label when the recipe did not name a brand.
    # Weaker than the taxonomy signals on purpose: it is a tiebreak between
    # products that are already the same kind of thing, not a reason to pick
    # the wrong kind.
    if (
        prefer_own_brand
        and not names_a_brand(ingredient_name)
        and is_own_brand(getattr(candidate, "brand", ""))
    ):
        total += 1.0

    # The retailer's own ordering, as a tiebreak only - and a weak one,
    # because candidates are merged from more than one query and a hit's index
    # in the combined list says nothing about the query it came from.
    total -= 0.15 * position
    return total


def cohort(ingredient_name: str, candidates: list) -> list:
    """The candidates worth proposing: the best, and those of the same kind.

    Proposing all of a search's hits is what lets a wrong one poison a cost,
    because downstream the cheapest candidate wins. Measured over the
    human-confirmed links, the hits carried 4.0 candidates per ingredient and
    this keeps 3.0 while still retaining a confirmed product for 95% of them.

    Same *kind* means the same taxonomy leaf. "AH Sjalotten" and "AH
    Biologisch Sjalotten" are interchangeable and cheapest-of-the-day is the
    whole point of keeping both; "Boursin Sjalot & bieslook" is a cream cheese.
    """
    if not candidates:
        return []
    # Which KIND of thing to propose is decided without the brand preference.
    # With it, an own-brand product of the wrong kind outranks a correctly
    # matched one from another brand: "mierikswortel in pot" chose AH Groene
    # pesto over Kühne Mierikswortel, and "runderbouillon van tablet" chose a
    # bar of white chocolate. Brand is a tiebreak between products that are
    # already the right thing, never a reason to pick the wrong thing.
    ordered = sorted(
        range(len(candidates)),
        key=lambda i: -score(
            ingredient_name, candidates[i], candidates, i, prefer_own_brand=False
        ),
    )
    best = candidates[ordered[0]]

    # If the best candidate is not recognisably the same thing as the
    # ingredient, propose nothing at all.
    #
    # Ranking always produces a winner, even when every candidate is wrong.
    # That is how "blauwe kaas-blokjes" came to be priced as AH Blauwe bessen
    # and "salade-uitjes" as AH Ei salade: both share a word with the
    # ingredient, both are food, both are Vers, so nothing downstream objected.
    # A cost built on those is worse than no cost, because it looks right.
    #
    # The test is the cohort winner's, not each candidate's: the winner decides
    # whether this ingredient was understood at all. Either evidence suffices -
    # the taxonomy leaf names the ingredient, or the head nouns agree - so
    # "broccoli" -> AH Biologisch Broccoli still passes on the head noun alone.
    if not recognisable(ingredient_name, best):
        return []

    key = normalise(getattr(best, "taxonomy_leaf", ""))
    if not key:
        # The best candidate is unclassified, so there is no "same kind" to
        # compare against. Narrowing here would drop candidates on no evidence,
        # which is the one thing every other rule in this module refuses to do.
        return list(candidates)
    return [c for c in candidates if normalise(getattr(c, "taxonomy_leaf", "")) == key]


# Water, however it is described. What a recipe means by it comes out of a
# tap, and no shopping list should carry it.
#
# The failure this prevents was not subtle: "warm water" and "lauwwarm water"
# both resolved to tinned tuna, because a title like "Statesman Tonijn stukken
# in water" has "water" as its last word, and the head-noun rule therefore
# matched perfectly. Every other check passed too - both food, both ambient.
_WATER_QUALIFIERS = frozenset(
    {
        "warm",
        "warme",
        "lauwwarm",
        "lauw",
        "heet",
        "hete",
        "koud",
        "koude",
        "kokend",
        "kokende",
        "gekookt",
        "gekookte",
        "kraan",
        "ijs",
        "ijskoud",
        "ijskoude",
        "bruisend",
        "bruisende",
        "plat",
        "platte",
    }
)

# Ice deliberately is NOT here. It looks like the same class - you make it
# from tap water - and AH sells it, so "ijsblokjes" against "AH IJsblokjes" is
# a correct match that this rule would have thrown away. The rule is about
# ingredients with no product, not about ingredients somebody could make
# themselves; by that second reading it would take stock and bread with it.


# Words that mean the opposite of each other without sharing a stem, so the
# "on-" rule below cannot see it. Nuts are roosterd in a recipe and gebrand on
# a packet; "ongebrand" is therefore a refusal of "geroosterd".
_OPPOSITES = {
    "geroosterd": "ongebrand",
    "geroosterde": "ongebrande",
    "gebrand": "ongeroosterd",
    "gebrande": "ongeroosterde",
}


def contradicts(ingredient_name: str, title: str) -> bool:
    """Whether the product explicitly refuses what the ingredient asked for.

    Dutch negates with "on-", so a recipe asking for gezouten pinda's against
    a packet named "AH Pinda's ongezouten" is not a near miss - it is the one
    thing the recipe said not to buy. Six such pairs were live: salted nuts of
    five kinds resolved to their unsalted versions, and the head nouns matched
    perfectly every time, which is why nothing else caught them.

    Only an explicit refusal counts. A plain "AH Pistachenoten" against
    "ongezouten pistachenoten" says nothing about salt and stays acceptable -
    the alternative is refusing every product that fails to mention an
    attribute, which would reject most of the catalogue.
    """
    asked = set(normalise(ingredient_name).split())
    offered = set(normalise(title).split())
    for word in asked:
        if _OPPOSITES.get(word) in offered:
            return True
        if not word.startswith("on") and f"on{word}" in offered:
            return True
        if word.startswith("on") and word[2:] in offered:
            return True
    return False


def comes_from_the_tap(ingredient_name: str) -> bool:
    """Whether this ingredient is water, and therefore not a thing to buy.

    Deliberately narrow. "tonijn in water" is a product and must not be
    caught: this asks whether the ingredient REDUCES to water once the
    temperature and source words are removed, not whether it mentions water.
    """
    words = [w for w in normalise(ingredient_name).split() if w]
    if not words:
        return False
    # Single-word compounds: kraanwater, ijswater.
    if len(words) == 1 and words[0].endswith("water"):
        return words[0][: -len("water")] in _WATER_QUALIFIERS | {""}
    remaining = [w for w in words if w not in _WATER_QUALIFIERS]
    return remaining == ["water"]


def recognisable(ingredient_name: str, candidate) -> bool:
    """Whether a candidate is identifiably the ingredient, by either evidence.

    Deliberately not a score threshold. Scores were measured against the
    human-confirmed links and did not separate: confirmed products scored as
    low as -1.20 while correct-but-unconfirmed ones scored 10.00, so any cut
    that removed the wrong matches removed good ones too. Naming does separate,
    because it asks a different question - not "how good is this?" but "is this
    the same thing?"
    """
    # Water is not shopping. Checked before anything else, because every
    # other rule here is about whether a candidate is the right THING and
    # these have no right thing - the answer is no product at all.
    if comes_from_the_tap(ingredient_name):
        return False

    # An explicit refusal outranks every positive signal below. "gezouten
    # pinda's" against "AH Pinda's ongezouten" matches on the head noun, the
    # leaf and the department - and is the one packet the recipe ruled out.
    if contradicts(ingredient_name, getattr(candidate, "title", "") or ""):
        return False

    # The packaging comes off first. A shelf label says "Kuhne Mierikswortel",
    # never "mierikswortel in pot", so comparing the raw ingredient text finds
    # no agreement and withholds a correct product.
    # without_packaging() returns "" to mean "nothing was stripped", which is a
    # signal to its other caller and not a name. Fall back to the original.
    name = without_packaging(ingredient_name) or ingredient_name
    leaf = getattr(candidate, "taxonomy_leaf", "") or ""
    if leaf_names_ingredient(name, leaf) or leaf_names_ingredient(
        ingredient_name, leaf
    ):
        return True
    title = getattr(candidate, "title", "") or ""
    if head_noun_match(name, title) or head_noun_match(ingredient_name, title):
        return True
    # Both directions. The recipe is usually the specific term and the shelf
    # the general one ("runderbouillon" for a Bouillon), but AH inverts it as
    # often: the recipe says "bloem" and the shelf says "AH Tarwebloem".
    #
    # The reverse direction compares against the ingredient's HEAD, not its
    # words. Dutch compounds name their head last, so "salade-ui" is a kind
    # of ui and "salade" is only what kind - and matching on any word made
    # "AH Selleriesalade" a specialisation of "salade-ui", which is how a
    # spring onion came to be priced as a tub of celery salad.
    #
    # Suffix matching stays safe in both directions once the head is the
    # thing being matched: a tarwebloem is a bloem, and a bloemkool, which
    # does not end in "bloem", is still not one.
    head = _head_noun(name)
    return (
        _specialises(name, leaf)
        or _specialises(leaf, head)
        or _specialises(name, title)
        or _specialises(title, head)
    )


def _head_noun(text: str) -> str:
    """The word a Dutch compound is a kind of: the last content word."""
    words = _content_words(text)
    return _title_head(words) if words else ""


def _specialises(ingredient_name: str, text: str) -> bool:
    """Whether the ingredient is a compound ending in one of the other's words.

    Dutch puts the head of a compound last, so "runderbouillon" IS a bouillon
    and "arachideolie" IS an oil, even though neither equals the leaf that
    names it. Without this the floor withholds them, which is a real loss: the
    leaf is frequently the general term and the recipe the specific one.

    Matching the suffix rather than the prefix is the whole point, and is why
    this does not reintroduce the bug the prefix ban exists for: "bloem" is not
    a "bloemkool" because flour is not a kind of cauliflower, and "bloemkool"
    does not end in "bloem".

    Four characters minimum, so that short heads like "ei" or "ui" cannot make
    every word that happens to end in them a match.
    """
    words = {w for w in normalise(text).split() if len(w) >= 4}
    return any(
        w != head and head.endswith(w)
        for head in normalise(ingredient_name).split()
        for w in words
    )
