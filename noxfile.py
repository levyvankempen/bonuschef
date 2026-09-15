import os
import nox
from nox.sessions import Session

nox.options.sessions = [
    "lint_python",
    "lint_sql",
    "format_python",
    "format_sql",
    "types",
    "tests",
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
