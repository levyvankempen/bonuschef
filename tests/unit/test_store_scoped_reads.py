"""Every reader whose answer depends on a store must be told which store.

Before this, `store_id` appeared exactly once in the whole portal layer and
never in a WHERE clause. That was correct only in the sense that there has
only ever been one store in the warehouse: the readers were not store-aware,
they were store-oblivious, and the moment a second store exists they start
answering with whatever happens to sort first.

Two separate failures are guarded here, and they need different guards:

  * the SQL must filter, or one person sees another town's shelf;
  * the store must reach the CACHE KEY, or the SQL filter is irrelevant
    because st.cache_data hands back the frame it built for whoever loaded
    the page first. That cache is shared by every visitor to the process.
"""

import ast
import inspect
from pathlib import Path

import pytest

from bonuschef.portal import db

ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "src" / "bonuschef" / "portal" / "db.py"

# The readers whose answer is a property of one store.
STORE_SCOPED = [
    "read_store_clearance",
    "read_last_scrape_time",
    "read_recipe_opportunity",
    "read_recipe_opportunity_items",
]


def _source(name: str) -> str:
    fn = getattr(db, name)
    return inspect.getsource(getattr(fn, "func", fn))


@pytest.mark.parametrize("name", STORE_SCOPED)
def test_the_reader_takes_a_store(name):
    fn = getattr(db, name)
    params = inspect.signature(getattr(fn, "func", fn)).parameters
    assert "store_id" in params, f"{name} cannot filter on a store it is never given"


@pytest.mark.parametrize("name", STORE_SCOPED)
def test_the_store_reaches_the_cache_key(name):
    """`_store_id` would be excluded from the key by this module's own
    convention, which is right for the engine and catastrophic here: the
    first visitor's frame would be served to everybody."""
    fn = getattr(db, name)
    params = inspect.signature(getattr(fn, "func", fn)).parameters
    assert "_store_id" not in params, (
        f"{name} hides the store behind the underscore convention, so "
        "st.cache_data will serve one account's data to another"
    )


@pytest.mark.parametrize("name", STORE_SCOPED)
def test_the_sql_filters_on_the_store(name):
    source = _source(name)
    assert "store_id = :store_id" in source, (
        f"{name} selects across every store; a filter in the signature that "
        "never reaches the WHERE clause is worse than none, because it reads "
        "as though it were scoped"
    )


@pytest.mark.parametrize("name", STORE_SCOPED)
def test_the_store_is_bound_as_a_parameter(name):
    """Not interpolated. The schema name is an f-string here for reasons that
    do not extend to a value arriving from an account."""
    source = _source(name)
    assert '"store_id": store_id' in source, source[-300:]


def test_freshness_is_not_a_maximum_over_every_store():
    """A MAX over the whole table is a lie the moment there are two stores: a
    store nobody has scraped for weeks inherits the freshness of one that
    scraped this morning, and the page then says clearance is current."""
    source = _source("read_last_scrape_time")
    assert "MAX(scraped_at)" in source
    assert "store_id = :store_id" in source, (
        "an unscoped MAX makes a stale store look fresh"
    )


def test_a_function_given_a_store_either_filters_on_it_or_writes_it():
    """A parameter named store_id that does neither invites the belief that
    the function is scoped when it is not.

    Writers are the other legitimate case and were not covered when this was
    first written: set_account_store takes a store in order to record it, and
    the original rule called that a defect. The rule is not "only readers may
    take a store" - it is that taking one must mean something.
    """
    tree = ast.parse(DB.read_text())
    for node in ast.walk(tree):
        if not isinstance(node, ast.FunctionDef) or node.name in STORE_SCOPED:
            continue
        if not any(a.arg == "store_id" for a in node.args.args):
            continue
        body = ast.get_source_segment(DB.read_text(), node) or ""
        filters = "store_id = :store_id" in body
        writes = "store_id = :s" in body or "WHERE store_id = :s" in body
        assert filters or writes, (
            f"{node.name} takes a store and neither filters nor writes with it"
        )


def test_the_active_store_is_resolved_in_one_place():
    """So that pointing it at an account later is one change rather than a
    search through every page."""
    assert callable(db.active_store_id)
    assert isinstance(db.active_store_id(), int)
