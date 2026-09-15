"""Every column a page reads must be one its query actually selects.

This bug has now shipped four times: a mart grows a column, the page reads it,
and the SELECT list in between is never updated. Nothing fails — pandas returns
None for a column that was not selected — so the page renders confidently wrong
output. It has produced "Van geen enkel ingrediënt is de prijs bekend" over six
priced products, star ratings that never appeared, a correction button that
never rendered, and "€nan per stuk" on an unresolved ingredient.

The two page-specific guards that existed only covered the queries they were
written for. This walks every portal module instead: it collects the column
names each page reads out of a dataframe row, and checks the reader function
asks for them.
"""

import ast
import inspect
import re
from pathlib import Path

import pytest

from bonuschef.portal import db

PORTAL = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "portal"

# Which reader feeds which page module. A page may read from several.
PAGE_READERS: dict[str, tuple[str, ...]] = {
    "tonight_page.py": ("read_recipe_opportunity", "read_recipe_opportunity_items"),
    "recipes_page.py": (
        "read_recipe_summary",
        "read_recipe_breakdown_bonus",
        "read_recipe_bonus_summary",
    ),
    "clearance_page.py": ("read_store_clearance",),
    "analysis_page.py": ("read_bonus_price_comparison", "read_price_changes"),
    # Reads the AH catalogue over the network, not a warehouse query, so it has
    # no SELECT list to fall out of step with. Listed so the coverage check
    # below cannot be satisfied by simply forgetting a page.
    "add_recipe_page.py": (),
}

# Names that look like column reads but are not: session-state keys, widget
# keys, and dict lookups on things that are not dataframe rows.
NOT_COLUMNS = frozenset(
    {
        "text",
        "label",
        "value",
        "key",
        "icon",
        "color",
        "help",
        "type",
        "width",
        "format",
        "options",
        "index",
        "data",
        "columns",
        "name",
    }
)


def _columns_read(path: Path) -> set[str]:
    """String literals used as `row[...]` or `row.get(...)` subscripts."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        # row["col"] and item["col"]
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                found.add(node.slice.value)
        # row.get("col")
        elif (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and node.func.attr == "get"
            and node.args
            and isinstance(node.args[0], ast.Constant)
            and isinstance(node.args[0].value, str)
        ):
            found.add(node.args[0].value)
    return {c for c in found if c not in NOT_COLUMNS and not c.startswith("_")}


def _selected_by(readers: tuple[str, ...]) -> set[str]:
    """Every identifier a page's queries actually SELECT.

    Only the SELECT clause, and only whole identifiers. Three weaker forms were
    tried and each stopped biting:

    * substring over the function source — `url` hides inside `image_url`, so
      deleting it left the guard green while the "Bekijk bij AH" link silently
      stopped rendering;
    * the same with comments stripped — a comment naming the column it was
      added for still satisfied the check after the column was deleted;
    * whole identifiers over the function source — the JOIN conditions mention
      `concept_id` and `item_key`, so removing them from the SELECT changed
      nothing the guard could see. That is exactly the shipped bug: the joins
      were there and selected nothing.
    """
    names: set[str] = set()
    for reader in readers:
        source = inspect.getsource(getattr(db, reader))
        code = "\n".join(
            line.split("--", 1)[0]
            for line in source.splitlines()
            if not line.lstrip().startswith("#")
        )
        # Each SELECT ... FROM region, so JOIN conditions and WHERE clauses
        # cannot vouch for a column the query does not return.
        for clause in re.findall(r"\bselect\b(.*?)\bfrom\b", code, re.S | re.I):
            names.update(re.findall(r"[A-Za-z_][A-Za-z0-9_]*", clause))
    return {n.lower() for n in names}


@pytest.mark.parametrize(
    "page_file",
    sorted(p for p, r in PAGE_READERS.items() if r),
    ids=lambda p: p,
)
def test_every_column_a_page_reads_is_selected(page_file):
    readers = PAGE_READERS[page_file]
    selected = _selected_by(readers)
    read = _columns_read(PORTAL / page_file)
    missing = sorted(c for c in read if c.lower() not in selected)

    assert not missing, (
        f"{page_file} reads columns none of its queries select: {missing}. "
        "pandas returns None for these, so the page renders wrong output "
        "rather than failing."
    )


def test_the_guard_covers_every_page_that_reads_a_dataframe():
    """A page added without an entry here is a page this cannot protect."""
    pages = {p.name for p in PORTAL.glob("*_page.py")}
    assert pages <= set(PAGE_READERS), (
        f"pages with no reader mapping: {sorted(pages - set(PAGE_READERS))}"
    )
