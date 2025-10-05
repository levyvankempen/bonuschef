import nox
from nox.sessions import Session

nox.options.sessions = [
    "lint_python",
    "lint_sql",
    "format_python",
    "format_sql",
    "mypy",
    "tests",
]
locations_python = "src", "tests", "noxfile.py"
locations_sql = ["src/bonuschef/sql"]


@nox.session(python=["3.12"], venv_backend="uv")
def tests(session: Session) -> None:
    args = session.posargs

    session.install("ruff", "uv")
    session.run("uv", "sync", "--active", external=True)
    session.run("uv", "run", "--active", "pytest", *args, external=True)


@nox.session(python=["3.12"], venv_backend="uv")
def lint_python(session: Session) -> None:
    """Run ruff code linter."""
    args = session.posargs or locations_python
    session.install("ruff", "uv")
    session.run("uv", "sync")
    session.run("uv", "run", "ruff", "check", *args)
    session.run("uv", "run", "ruff", "format", "--diff", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def lint_sql(session: Session) -> None:
    """Lint using SQLfluff."""
    args = session.posargs or locations_sql
    session.install("ruff", "uv", "sqlfluff")
    session.run("uv", "sync")
    session.run("uv", "run", "dbt", "deps", "--project-dir", *args)
    session.run(
        "uv", "run", "dbt", "parse", "--project-dir", *args, "--profiles-dir", *args
    )
    session.run("uv", "run", "sqlfluff", "lint", "--dialect", "postgres", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def format_python(session: Session) -> None:
    """Run ruff code formatter."""
    args = session.posargs or locations_python
    session.install("ruff", "uv")
    session.run("uv", "sync")
    session.run("uv", "run", "ruff", "check", "--fix", *args)
    session.run("uv", "run", "ruff", "format", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def format_sql(session: Session) -> None:
    """Run SQLfluff fix formatter."""
    args = session.posargs or locations_sql
    session.install("ruff", "uv", "sqlfluff")
    session.run("uv", "sync")
    session.run("uv", "run", "sqlfluff", "fix", "--dialect", "postgres", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def mypy(session):
    args = session.posargs or locations_python
    session.install("ruff", "uv")
    session.run("uv", "sync")
    session.run("uv", "run", "mypy", *args)
