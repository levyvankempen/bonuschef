"""The nox sessions, checked for the ordering dependency that broke a release.

The suite imports the Dagster definitions, whose asset graph is built from
`target/manifest.json`. Nothing in the repository generates that file at
import time, so a session that needs it must produce it.
"""

import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NOXFILE = ROOT / "noxfile.py"


def _session(name: str) -> ast.FunctionDef:
    tree = ast.parse(NOXFILE.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"noxfile.py has no {name} session")


def _calls(fn: ast.FunctionDef) -> set[str]:
    return {
        n.func.id
        for n in ast.walk(fn)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }


def test_the_tests_session_generates_the_manifest_it_needs():
    """`nox -s tests` on a clean checkout used to fail during collection with
    DagsterDbtManifestNotFoundError. The manifest appeared only because
    lint_sql had run first and left it behind -- an order recorded nowhere.

    The release workflow ran the sessions in a different order and v1.3.0 was
    never cut.
    """
    assert "_dbt_parse" in _calls(_session("tests")), (
        "the tests session does not generate target/manifest.json, so it "
        "depends on another session having run first"
    )


def test_both_sessions_use_the_same_generation_step():
    """Two copies of `dbt deps && dbt parse` drift the same way two gates do."""
    for name in ("tests", "lint_sql"):
        assert "_dbt_parse" in _calls(_session(name)), (
            f"{name} does not use the shared helper"
        )


def test_generating_the_manifest_needs_no_database():
    """`dbt parse` resolves refs and writes the manifest without connecting.
    `dbt run`, `build` or `compile` would open a connection, and the suite is
    required to stay DB-free and network-free."""
    body = ast.get_source_segment(NOXFILE.read_text(), _session_helper()) or ""
    verbs = set(re.findall(r'"dbt",\s*\n?\s*"([a-z]+)"', body))
    assert verbs, "could not find the dbt invocations in the helper"
    assert verbs <= {"deps", "parse"}, (
        f"the helper runs {sorted(verbs - {'deps', 'parse'})}, which needs a database"
    )


def _session_helper() -> ast.FunctionDef:
    tree = ast.parse(NOXFILE.read_text())
    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name == "_dbt_parse":
            return node
    raise AssertionError("noxfile.py has no _dbt_parse helper")


def test_warehouse_backed_tests_run_in_exactly_one_session():
    """They need the marts, and `tests` runs before `warehouse` builds them.

    Encoding that as session ORDER is fragile - CI listed its steps
    independently and ran `tests` first, so the checks errored on a database
    with no marts in it. The dependency is a prerequisite, so it is expressed
    as a marker: `tests` deselects it, `warehouse` selects it after building.

    The danger of a marker is a test that belongs to neither selection and
    quietly runs nowhere, so both halves are pinned here.
    """
    source = NOXFILE.read_text()
    tests_body = ast.get_source_segment(source, _session("tests")) or ""
    warehouse_body = ast.get_source_segment(source, _session("warehouse")) or ""

    assert '"not warehouse"' in tests_body, (
        "the tests session would run checks that need marts it has not built"
    )
    assert '"warehouse"' in warehouse_body and '"pytest"' in warehouse_body, (
        "nothing runs the warehouse-backed checks after the build"
    )


def test_the_marker_is_declared():
    """An undeclared marker is a typo away from selecting nothing, and pytest
    does not complain by default."""
    import tomllib

    config = tomllib.loads((ROOT / "pyproject.toml").read_text())
    markers = config["tool"]["pytest"]["ini_options"]["markers"]
    assert any(m.startswith("warehouse:") for m in markers), markers
