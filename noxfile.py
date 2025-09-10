import nox
from nox.sessions import Session

nox.options.sessions = ["lint", "mypy", "tests"]
locations = "src", "tests", "noxfile.py"


@nox.session(python=["3.12"], venv_backend="uv")
def tests(session: Session) -> None:
    args = session.posargs or ["--cov=onboarding_ruud", "-q"]

    session.install("uv")
    session.run("uv", "sync", "--active", external=True)
    session.run("uv", "run", "--active", "pytest", *args, external=True)


@nox.session(python=["3.12"], venv_backend="uv")
def lint(session: Session) -> None:
    """Run ruff code linter."""
    args = session.posargs or locations
    session.install("ruff", "uv")
    session.run("uv", "sync", external=True)
    session.run("uv", "run", "ruff", "check", *args)
    session.run("uv", "run", "ruff", "format", "--diff", *args)


@nox.session(python="3.12", venv_backend="uv")
def format(session: Session) -> None:
    """Run ruff code formatter."""
    args = session.posargs or locations
    session.install("ruff", "uv")
    session.run("uv", "sync")
    session.run("uv", "run", "ruff", "check", "--fix", *args)
    session.run("uv", "run", "ruff", "format", *args)


@nox.session(python=["3.12"], venv_backend="uv")
def mypy(session):
    args = session.posargs or locations
    session.install("uv")
    session.run("uv", "sync")
    session.run("uv", "run", "mypy", *args)
