import os
import nox
from nox.sessions import Session

nox.options.sessions = [
    "lint_python",
    "lint_sql",
    "format_python",
    "format_sql",
    "mypy",
    # "tests",
]
locations_python = "src", "tests", "noxfile.py"
locations_sql = ["src/bonuschef/sql"]


def _maybe_github_format(extra: list[str]) -> list[str]:
    if os.getenv("GITHUB_ACTIONS"):
        return [*extra, "--output-format=github"]
    return extra


# @nox.session(python=["3.12"], venv_backend="uv")
# def tests(session: Session) -> None:
#     args = session.posargs
#
#     session.run("uv", "sync", "--active", "--dev")
#     session.run("uv", "sync", "--active", external=True)
#     session.run("uv", "run", "--active", "pytest", *args, external=True)


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
    session.run("uv", "run", "--active", "dbt", "deps", "--project-dir", *args)
    session.run(
        "uv",
        "run",
        "--active",
        "dbt",
        "parse",
        "--project-dir",
        *args,
        "--profiles-dir",
        *args,
    )
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
def mypy(session):
    args = session.posargs or locations_python
    session.run("uv", "sync", "--active", "--dev")
    session.run("uv", "run", "--active", "mypy", *args)
