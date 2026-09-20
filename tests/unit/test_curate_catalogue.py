"""The catalogue curation script.

It writes to production and deletes recipes, so the parts that decide WHAT it
touches are pinned here even though the parts that do the touching need a
database.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "curate_catalogue.py"


def test_it_names_the_recipes_the_owner_asked_for():
    """The ids come from the Allerhande URLs: R-R1193780 and R-R1193969."""
    from scripts.curate_catalogue import ADOPT, WITHDRAW

    assert set(ADOPT) == {1193780, 1193969}
    assert set(WITHDRAW) == {1199196}


def test_adopting_and_withdrawing_do_not_overlap():
    """A recipe in both sets would be adopted and immediately deleted, and the
    script would report success for both."""
    from scripts.curate_catalogue import ADOPT, WITHDRAW

    assert not set(ADOPT) & set(WITHDRAW)


def test_withdrawing_leaves_ingredient_concepts_alone():
    """Concepts are shared and expensively resolved - roughly 1900 of them, each
    having cost an AH search. Deleting the ones belonging to a withdrawn recipe
    would throw away work that whatever is adopted next would have to redo."""
    body = SCRIPT.read_text()
    deletes = [line for line in body.splitlines() if "DELETE FROM" in line.upper()]
    assert deletes, "the script is supposed to delete something"
    assert not any("ah_recipe_concepts" in d or "concept" in d for d in deletes), (
        f"withdrawal must not touch shared concepts: {deletes}"
    )


def test_it_offers_a_dry_run():
    """It writes to production. Being able to see what it would do first is the
    difference between a script and a loaded gun."""
    assert "--dry-run" in SCRIPT.read_text()
