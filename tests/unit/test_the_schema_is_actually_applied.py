"""Every table the portal writes to or reads from is one the portal creates.

`ensure_account_tables` was idempotent, safe to run on every start, and called
by nothing. The tables it declares were created by hand during the work that
introduced them, so `account_recipe_lines` - added afterwards - was never
created at all, and the Recepten page raised UndefinedTable on production for
anybody whose card it tried to price.

A migration nobody runs is a migration that does not exist. These tests check
both halves: that the DDL covers every own table the portal touches, and that
something actually applies it.
"""

import ast
import re
from pathlib import Path

from bonuschef.portal import schema

PORTAL = Path("src/bonuschef/portal")

# Tables in public. that belong to something else: the warehouse builds them,
# dlt loads them, or dbt publishes them. The portal reads them and must not
# create them.
NOT_OURS = {
    "int_pool_recipes_available",
    "int_recipe_item_opportunity",
    "int_recipe_items_priced",
    "int_store",
    "ah_recipes",
    "ah_recipe_ingredients",
    "ah__pool_recipes",
    "ah__pool_recipe_ingredients",
    "ah_ingredient_products",
    "ah_ingredient_review",
    "ah_markdowns",
    "ah_bonus",
    "product_images",
    "dagster_runs",
}


def _tables_the_portal_touches() -> set[str]:
    """Every `public.<name>` mentioned in a query anywhere in the portal."""
    found: set[str] = set()
    for path in PORTAL.glob("*.py"):
        for sql in _sql_strings(path):
            found.update(re.findall(r"\bpublic\.([a-z_][a-z0-9_]*)", sql))
    return found - NOT_OURS


def _sql_strings(path: Path) -> list[str]:
    """String literals that look like SQL, read through the AST.

    Not a grep over the file: a docstring mentioning a table name would
    otherwise count as a query, and this test would then pass because of prose.
    """
    tree = ast.parse(path.read_text())
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            upper = node.value.upper()
            if any(
                verb in upper
                for verb in ("SELECT ", "INSERT ", "UPDATE ", "DELETE ", "CREATE ")
            ):
                out.append(node.value)
    return out


_CREATES = re.compile(r"CREATE TABLE IF NOT EXISTS\s+public\.([a-z_][a-z0-9_]*)")


def _tables_the_ddl_creates() -> set[str]:
    """The portal declares its tables in two places, so both are read.

    `schema._STATEMENTS` is the ordered account schema; `db.py` carries its own
    `ensure_*` functions with CREATE TABLE inline. Two homes for one concern is
    a smell, and it is how a table came to be declared in one of them and
    created by nobody - but a test that knew about only one home would report
    four false positives and get itself deleted.
    """
    names: set[str] = set()
    for statement in schema._STATEMENTS:
        names.update(_CREATES.findall(statement))
    for sql in _sql_strings(PORTAL / "db.py"):
        names.update(_CREATES.findall(sql))
    return names


def test_the_ddl_creates_every_table_the_portal_owns():
    """The check that was missing. `account_recipe_lines` was queried by the
    page and created by nobody, and nothing failed until a card needed it."""
    touched = _tables_the_portal_touches()
    created = _tables_the_ddl_creates()
    missing = touched - created
    assert not missing, (
        f"the portal queries {sorted(missing)}, which its own DDL does not "
        "create. Either add the CREATE TABLE to schema._STATEMENTS or, if the "
        "table belongs to dbt or dlt, list it in NOT_OURS here."
    )


def test_the_ddl_is_applied_by_something():
    """It was correct, idempotent and unreachable. That is the whole bug."""
    callers = []
    for path in Path("src/bonuschef").rglob("*.py"):
        if path.name == "schema.py":
            continue
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and "ensure_account_tables" in ast.unparse(
                node.func
            ):
                callers.append(path.name)
    assert callers, "ensure_account_tables must be called by something"


def test_it_is_applied_once_per_process_not_per_interaction():
    """The portal spec forbids schema-changing statements on each interaction,
    so this has to hang off something cached rather than off a render."""
    src = (PORTAL / "db.py").read_text()
    tree = ast.parse(src)
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "get_engine"
    )
    assert any(
        "ensure_account_tables" in ast.unparse(n)
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
    ), "get_engine is the cached once-per-process hook; apply it there"
    decorators = {ast.unparse(d) for d in fn.decorator_list}
    assert any("cache_resource" in d for d in decorators), (
        f"get_engine must stay cached or the DDL runs per interaction: {decorators}"
    )


def test_the_failure_is_not_swallowed():
    """A portal that cannot apply its own schema is broken. Swallowing that
    produces the failure this whole file exists about: pages that mostly work
    until one of them touches the table nobody made."""
    tree = ast.parse((PORTAL / "db.py").read_text())
    fn = next(
        n
        for n in tree.body
        if isinstance(n, ast.FunctionDef) and n.name == "get_engine"
    )
    for handler in (n for n in ast.walk(fn) if isinstance(n, ast.ExceptHandler)):
        body = " ".join(ast.unparse(s) for s in handler.body)
        assert (
            "ensure_account_tables" not in ast.unparse(fn.body[-1])
            or "pass" not in body
        ), "the schema failure must propagate, not be swallowed"
