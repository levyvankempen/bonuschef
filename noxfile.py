"""Nox sessions for dbt."""

import nox
from nox.sessions import Session

locations_python = ["main.py"]
nox.options.sessions = ["lint_python"]


@nox.session(python=["3.12"])
def lint_sql(session: Session) -> None:
    """Lint using SQLfluff."""
    args = session.posargs or locations_sql
    session.install(
        "dbt-core",
        "dbt-postgres",
        "sqlfluff",
        "sqlfluff-templater-dbt",
    )
    session.run("dbt", "deps", "--project-dir", *args)
    session.run("sqlfluff", "lint", "--dialect", "postgres", *args)


@nox.session(python=["3.12"])
def lint_python(session: Session) -> None:
    """Lint using flake8."""
    args = session.posargs or locations_python
    session.install(
        "pyproject-flake8",
        "flake8-annotations",
        "flake8-black",
        "flake8-docstrings",
    )
    session.run("pflake8", *args)


@nox.session(python=["3.12"])
def format_sql(session: Session) -> None:
    """Run SQLfluff fix formatter."""
    args = session.posargs or locations_sql
    session.install(
        "dbt-core",
        "dbt-postgres",
        "sqlfluff",
        "sqlfluff-templater-dbt",
    )
    session.run("sqlfluff", "fix", "--dialect", "postgres", "-f", *args)


@nox.session(python=["3.12"])
def format_python(session: Session) -> None:
    """Run black code formatter."""
    args = session.posargs or locations_python
    session.install("black", "isort")
    session.run("black", *args)
    session.run("isort", *args)


@nox.session(python=["3.12"])
def test_python(session: Session) -> None:
    """Run the python tests suite for the API."""
    args = ["portal"]
    session.install("pytest", "portal/.")
    session.run("pytest", *args)
