"""Every column a page reads must be one its query actually returns.

This bug has shipped four times: a mart grows a column, the page reads it, and
the SELECT list in between is never updated. Nothing fails - pandas returns
None for a column that was not selected - so the page renders confidently
wrong output. It has produced "Van geen enkel ingrediënt is de prijs bekend"
over six priced products, star ratings that never appeared, a correction
button that never rendered, and "€nan per stuk" on an unresolved ingredient.

It replaces a regex over the SQL text, whose own docstring recorded three
earlier forms that each stopped biting:

  * substring over the function source - `url` hides inside `image_url`;
  * the same with comments stripped - a comment naming the column still
    satisfied the check after the column was deleted;
  * whole identifiers over the function source - the JOIN conditions mention
    `concept_id`, so removing it from the SELECT changed nothing the guard
    could see. Which is exactly the shipped bug: the joins were there and
    selected nothing.

A fifth regex would have been the wrong investment. With a built warehouse the
question has an exact answer: run the query, look at what came back.

An EMPTY warehouse is enough. pandas returns the column names of a result set
with no rows in it, so this needs the schema and not the data.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from bonuschef.portal import db

# Needs the marts to exist, so it runs in the `warehouse` session after the
# build - not in `tests`, which runs first and would find nothing there.
pytestmark = pytest.mark.warehouse

PORTAL = Path(__file__).resolve().parents[2] / "src" / "bonuschef" / "portal"

# The store the fixture's rows belong to. A store-scoped reader has to be told
# which store, and told the RIGHT one: passing an arbitrary id here would make
# every query return nothing, and a test that asserts on the columns of an
# empty frame passes without checking anything.
FIXTURE_STORE_ID = 1876

# Readers the fixture is known to populate. Asserting these come back
# non-empty is what stops the column checks below from passing vacuously.
# Deliberately not every reader: some legitimately have nothing to say about
# the seeded rows, and demanding rows from those would be a false alarm.
MUST_RETURN_ROWS = frozenset(
    {
        "read_recipe_opportunity",
        "read_store_clearance",
        "read_recipe_summary",
    }
)

# Which reader feeds which page, and what it needs to be called with. A page
# may read from several.
PAGE_READERS: dict[str, tuple[tuple[str, tuple], ...]] = {
    "tonight_page.py": (
        ("read_recipe_opportunity", (FIXTURE_STORE_ID,)),
        ("read_recipe_opportunity_items", (1, FIXTURE_STORE_ID)),
        ("read_pipeline_health", ()),
    ),
    "recipes_page.py": (
        ("read_recipe_summary", ()),
        ("read_recipe_breakdown_bonus", (1,)),
        ("read_recipe_bonus_summary", ()),
    ),
    "clearance_page.py": (("read_store_clearance", (FIXTURE_STORE_ID,)),),
    "analysis_page.py": (
        ("read_bonus_price_comparison", ()),
        ("read_price_changes", ()),
    ),
    # Reads the retailer's catalogue over the network, not a warehouse query,
    # so it has no result set to fall out of step with. Listed so the coverage
    # check below cannot be satisfied by forgetting a page.
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


@pytest.fixture(scope="module")
def warehouse():
    """A built warehouse, or a skip - except in CI, where it is a failure.

    CI provides one. A skip there is a green check that proves nothing, which
    is the thing this whole capability exists to stop.
    """
    url = (
        f"postgresql+psycopg2://{os.getenv('PG_USER', 'postgres')}:"
        f"{os.getenv('PG_PASSWORD', 'postgres')}@{os.getenv('PG_HOST', 'localhost')}:"
        f"{os.getenv('PG_PORT', '5455')}/{os.getenv('PG_DB', 'postgres')}"
    )
    try:
        engine = create_engine(url, pool_pre_ping=True)
        with engine.begin() as conn:
            conn.execute(
                text("SELECT 1 FROM public_marts.fct_recipe_opportunity LIMIT 0")
            )
    except Exception as exc:
        if os.getenv("CI"):
            raise AssertionError(
                f"CI builds the warehouse and these checks must run against it: {exc}"
            ) from exc
        pytest.skip("no built warehouse")  # ty: ignore[too-many-positional-arguments]
    return engine


def _columns_read(path: Path) -> set[str]:
    """String literals used as `row[...]` or `row.get(...)` subscripts."""
    found: set[str] = set()
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant):
            if isinstance(node.slice.value, str):
                found.add(node.slice.value)
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


def _columns_returned(engine, readers: tuple[tuple[str, tuple], ...]) -> set[str]:
    """What the readers actually hand back, by running them.

    `.func` steps around Streamlit's cache decorator - outside a Streamlit
    runtime the cache is an unwanted variable, and this wants the query.
    """
    names: set[str] = set()
    for reader, args in readers:
        fn = getattr(db, reader)
        fn = getattr(fn, "func", fn)
        frame = fn(engine, *args)
        if reader in MUST_RETURN_ROWS:
            # A frame with no rows still has columns, so every assertion
            # downstream passes on it. Proved by mutation: pointing the
            # store-scoped readers at store 999999 emptied all of them and
            # the whole warehouse suite stayed green.
            #
            # That matters most for exactly the readers that gained a store
            # filter, because "the filter excludes everything" is the way a
            # store filter fails.
            assert not frame.empty, (
                f"{reader} returned no rows, so every column assertion about "
                "it passes without checking anything. Either the fixture no "
                "longer covers it or its filter excludes everything."
            )
        names.update(str(c).lower() for c in frame.columns)
    return names


@pytest.mark.parametrize(
    "page_file",
    sorted(p for p, r in PAGE_READERS.items() if r),
    ids=lambda p: p,
)
def test_a_page_reads_only_columns_its_queries_return(page_file, warehouse):
    read = _columns_read(PORTAL / page_file)
    returned = _columns_returned(warehouse, PAGE_READERS[page_file])
    missing = {c for c in read if c.lower() not in returned}
    assert not missing, (
        f"{page_file} reads {sorted(missing)}, which none of its queries "
        f"return. pandas yields None for these rather than raising, so the "
        f"page renders confidently wrong output."
    )


def test_every_portal_page_is_covered():
    """A page can never be silently outside the guard."""
    pages = {p.name for p in PORTAL.glob("*_page.py")}
    assert pages == set(PAGE_READERS), (
        f"not classified: {sorted(pages - set(PAGE_READERS))}"
    )


def test_the_readers_are_actually_executed(warehouse):
    """The point of this file over the regex it replaces. If a reader raised,
    the parametrised checks above would error rather than pass quietly."""
    returned = _columns_returned(warehouse, PAGE_READERS["tonight_page.py"])
    assert "recipe_id" in returned and "opportunity_rank" in returned, (
        "the opportunity reader did not come back with its own key columns"
    )


def test_every_reader_of_a_rebuilt_mart_takes_the_build_stamp():
    """Only the two Vanavond readers took it. The Recepten page cached its
    costs on a wall clock, so after a SCHEDULED rebuild - which is how the
    nightly runs - it served the previous answer for up to fifteen minutes
    with nothing to indicate it.

    That is the same defect the build stamp was introduced to fix, left in
    place on the other page.
    """
    import inspect

    from bonuschef.portal import db

    for name in (
        "read_recipe_opportunity",
        "read_recipe_opportunity_items",
        "read_recipe_summary",
        "read_recipe_breakdown_bonus",
        "read_recipe_bonus_summary",
        "read_recipe_cost_history",
    ):
        params = inspect.signature(getattr(db, name)).parameters
        assert "built_at" in params, f"{name} cannot be invalidated by a rebuild"


def test_both_pages_pass_the_stamp():
    for page in ("tonight_page.py", "recipes_page.py"):
        body = (PORTAL / page).read_text()
        assert "read_marts_built_at(engine)" in body, (
            f"{page} reads the marts without asking when they were built"
        )
