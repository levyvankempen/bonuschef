import os
import nox
from nox.sessions import Session

# The canonical check list. Every gate runs exactly this, and nothing names a
# subset of it - that is what broke the v1.3.0 release.
#
# format_python and format_sql are deliberately NOT here. They REWRITE the
# tree (`ruff check --fix`, `sqlfluff fix`), and a gate that modifies the code
# before checking it verifies something other than the commit it is about to
# release. Their checking equivalents already run: lint_python ends with
# `ruff format --diff` and lint_sql with `sqlfluff lint`. Both remain
# available as `nox -s format_python` for local use.
nox.options.sessions = [
    "lint_python",
    "lint_sql",
    "types",
    "tests",
    "warehouse",
]
locations_python = "src", "tests", "noxfile.py"
locations_sql = ["src/bonuschef/sql"]


def _maybe_github_format(extra: list[str]) -> list[str]:
    if os.getenv("GITHUB_ACTIONS"):
        return [*extra, "--output-format=github"]
    return extra


def _dbt_parse(session: Session) -> None:
    """Produce `target/manifest.json`.

    The test suite imports the Dagster definitions, which build their asset
    graph from this manifest, so the suite cannot even be collected without
    it. It used to appear only because `lint_sql` happened to run first --
    an ordering written down nowhere, which broke the v1.3.0 release the
    moment a workflow ran the sessions in a different order.

    `dbt parse` resolves refs and writes the manifest. It opens no
    connection, so calling it here keeps the suite DB-free and network-free.
    It is safe to run twice; any session may be the one that runs first.
    """
    session.run("uv", "run", "--active", "dbt", "deps", "--project-dir", *locations_sql)
    session.run(
        "uv",
        "run",
        "--active",
        "dbt",
        "parse",
        "--project-dir",
        *locations_sql,
        "--profiles-dir",
        *locations_sql,
    )


@nox.session(python=["3.12"], venv_backend="uv")
def warehouse(session: Session) -> None:
    """Execute the SQL, rather than deciding it looks plausible.

    `dbt parse` does not read SQL grammar - it is a Jinja and graph
    operation. Verified: a model containing `selec 1 as a,, from x` parses
    clean and exits 0. sqlfluff catches the grammar but not a broken `ref()`,
    because with the jinja templater `ref` is stubbed to a placeholder string.

    Between them they cover neither of the two things that have actually
    broken here: SQL that renders to nonsense (`> i.{{ var(...) }}` becoming
    `> i.45`, which lints clean and parses clean because Jinja renders to text
    that LOOKS valid), and a model that stops producing a column something
    downstream selects.

    Only a database answers those, and it answers them on an EMPTY database -
    the statements are executed either way. So this needs a Postgres, and
    needs no fixture data to earn its place.

    It also runs the 134 data tests and 6 singular tests in the project, not
    one of which has ever executed in CI.
    """
    session.run("uv", "sync", "--active", "--dev")
    _dbt_parse(session)
    session.run("uv", "run", "--active", "python", "scripts/seed_warehouse_sources.py")
    session.run(
        "uv",
        "run",
        "--active",
        "dbt",
        "build",
        "--project-dir",
        *locations_sql,
        "--profiles-dir",
        *locations_sql,
        env={
            # Defaults matching the service container in ci.yml. Overridable so
            # the same session runs against a local database.
            "PG_HOST": os.getenv("PG_HOST", "localhost"),
            "PG_PORT": os.getenv("PG_PORT", "5432"),
            "PG_USER": os.getenv("PG_USER", "postgres"),
            "PG_PASSWORD": os.getenv("PG_PASSWORD", "postgres"),
            "PG_DB": os.getenv("PG_DB", "postgres"),
            "ENVIRONMENT": os.getenv("ENVIRONMENT", "default"),
        },
    )
    # Now that it is built, check what reads from it. These live here rather
    # than in `tests` because they need the marts, and `tests` runs first.
    session.run(
        "uv",
        "run",
        "--active",
        "pytest",
        "-m",
        "warehouse",
        env={
            "PG_HOST": os.getenv("PG_HOST", "localhost"),
            "PG_PORT": os.getenv("PG_PORT", "5432"),
            "PG_USER": os.getenv("PG_USER", "postgres"),
            "PG_PASSWORD": os.getenv("PG_PASSWORD", "postgres"),
            "PG_DB": os.getenv("PG_DB", "postgres"),
            "CI": os.getenv("CI", ""),
        },
    )


@nox.session(python=["3.12"], venv_backend="uv")
def tests(session: Session) -> None:
    args = session.posargs

    session.run("uv", "sync", "--active", "--dev")
    session.run("uv", "sync", "--active", external=True)
    _dbt_parse(session)
    session.run(
        "uv",
        "run",
        "--active",
        "pytest",
        # The warehouse-backed checks run in that session, after the build.
        "-m",
        "not warehouse",
        "--cov",
        "--cov-report=term-missing",
        *args,
        external=True,
    )


@nox.session(python=["3.12"], venv_backend="uv")
def lint_python(session: Session) -> None:
    """Run ruff code linter."""
    args = session.posargs or locations_python
    session.run("uv", "sync", "--active", "--dev")
    session.run("uv", "run", "--active", "ruff", "check", *args)
    session.run("uv", "run", "--active", "ruff", "format", "--diff", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def lint_sql(session: Session) -> None:
    """Lint using SQLfluff."""
    args = session.posargs or locations_sql
    session.run("uv", "sync", "--active", "--dev")
    _dbt_parse(session)
    session.run(
        "uv", "run", "--active", "sqlfluff", "lint", "--dialect", "postgres", *args
    )


@nox.session(python=["3.12"], venv_backend="uv")
def format_python(session: Session) -> None:
    """Run ruff code formatter."""
    args = session.posargs or locations_python
    session.run("uv", "sync", "--active", "--dev")
    session.run("uv", "run", "--active", "ruff", "check", "--fix", *args)
    session.run("uv", "run", "--active", "ruff", "format", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def format_sql(session: Session) -> None:
    """Run SQLfluff fix formatter."""
    args = session.posargs or locations_sql
    session.run("uv", "sync", "--active", "--dev")
    session.run(
        "uv", "run", "--active", "sqlfluff", "fix", "--dialect", "postgres", *args
    )


@nox.session(python=["3.12"], venv_backend="uv")
def types(session: Session) -> None:
    """Type check with ty (Astral's checker; replaced mypy)."""
    args = session.posargs or locations_python
    session.run("uv", "sync", "--active", "--dev")
    session.run("uv", "run", "--active", "ty", "check", *args)
