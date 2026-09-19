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

# Fresh things are sold frozen too, and a recipe asking for fresh spinach is
# not wronged by frozen spinach the way it is by a jar of dried dill.
_FRESH_ENOUGH = frozenset({DEPARTMENT_FRESH, DEPARTMENT_FROZEN})


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
    return bool(ing) and bool(leaf) and ing == leaf


def rank(ingredient_name: str, candidates: list) -> list:
    """Reorder candidates so the taxonomy-named ones come first.

    Only reorders; never drops. A candidate no leaf names is not thereby
    wrong - it usually means the taxonomy is coarser than the ingredient, as
    for "bladpeterselie", whose leaf is the broader "Verse kruiden".

    Stable, so the retailer's own relevance ordering survives underneath.
    """
    return sorted(
        candidates,
        key=lambda c: not leaf_names_ingredient(
            ingredient_name, getattr(c, "taxonomy_leaf", "")
        ),
    )


# Words that describe a product without being what it is. "AH" and
# "Biologisch" appear on half the catalogue; letting them count as content
# makes every own-brand product look more specific than it is.
_QUALIFIERS = frozenset(
    {"ah", "biologisch", "bio", "verse", "vers", "de", "het", "een"}
)

# There is deliberately no confidence floor.
#
# One was tried and measured against the human-confirmed links, and the scores
# do not separate. Products a person confirmed score as low as -1.20
# ("chilivlokken"), while obviously-correct matches that simply were not in the
# confirmed set score 10.00 ("broccoli" -> AH Biologisch Broccoli). Any floor
# that removed a bad answer removed good ones with it: at 0.0 it cost
# arachideolie, bosuitje and chilivlokken their only correct product.
#
# So the score orders candidates and never rejects them. Rejection is left to
# the classification rules, which are about kind rather than degree and can say
# why.


def _content_words(text: str) -> list[str]:
    return [w for w in normalise(text).split() if w not in _QUALIFIERS]


def _same_word(a: str, b: str) -> bool:
    """Whether two Dutch words are the same noun, allowing for plurals.

    Deliberately not a prefix match. Prefix matching made "bloem" (flour) match
    "Bloemkoolrijst" (cauliflower rice), which is how flour came to be
    resolved as a vegetable.
    """
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
    return _same_word(ingredient_words[-1], title_words[-1])


def score(ingredient_name: str, candidate, siblings: list, position: int = 0) -> float:
    """How well a candidate answers an ingredient. Higher is better.

    Every term is explainable on purpose. A person correcting a match should
    be able to see why the system preferred what it did, and a rule nobody can
    explain is a rule nobody can fix.
    """
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

    if head_noun_match(ingredient_name, title):
        total += 3.0

    # Every word the title carries that the ingredient did not ask for is a
    # way the product might be something else.
    asked = set(_content_words(ingredient_name))
    total -= 0.4 * len([w for w in _content_words(title) if w not in asked])

    # The retailer's own ordering, as a tiebreak only.
    total -= 0.3 * position
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
    ordered = sorted(
        range(len(candidates)),
        key=lambda i: -score(ingredient_name, candidates[i], candidates, i),
    )
    best = candidates[ordered[0]]
    key = normalise(getattr(best, "taxonomy_leaf", ""))
    if not key:
        # The best candidate is unclassified, so there is no "same kind" to
        # compare against. Narrowing here would drop candidates on no evidence,
        # which is the one thing every other rule in this module refuses to do.
        return list(candidates)
    return [c for c in candidates if normalise(getattr(c, "taxonomy_leaf", "")) == key]
