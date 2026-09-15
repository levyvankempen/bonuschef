"""The deploy script's guards.

Each guard here corresponds to something that has already gone wrong on the
real host, recorded in docs/deployment.md. The script exists so those lessons
are enforced rather than remembered.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"


def _run(*args, cwd: Path | None = None):
    return subprocess.run(
        ["bash", str(DEPLOY), *args],
        cwd=cwd or ROOT,
        capture_output=True,
        text=True,
    )


def test_the_script_is_syntactically_valid():
    assert subprocess.run(["bash", "-n", str(DEPLOY)]).returncode == 0


def test_it_is_executable():
    assert DEPLOY.stat().st_mode & 0o111, "not executable; deploying would need `bash`"


def test_naming_no_version_is_refused_and_suggests_some():
    """Deploying "whatever is here" is the habit this replaces."""
    r = _run()
    assert r.returncode != 0
    assert "usage" in r.stderr.lower()
    assert "available" in r.stderr.lower(), "refusing without helping is unkind"


@pytest.fixture
def repo(tmp_path):
    """A checkout with one tag and one branch, and no Docker anywhere."""
    import os

    r = tmp_path / "repo"
    (r / "scripts").mkdir(parents=True)
    for s in ("deploy.sh", "version.sh"):
        dst = r / "scripts" / s
        dst.write_text((ROOT / "scripts" / s).read_text())
        dst.chmod(0o755)
    (r / "pyproject.toml").write_text('version = "0.0.1"\n')
    (r / "docker-compose.yml").write_text("services: {}\n")
    env = {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }
    for cmd in (
        ["git", "init", "-q", "-b", "main"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        ["git", "tag", "v0.0.1"],
        # `git fetch origin` must have something to talk to.
        ["git", "remote", "add", "origin", str(r)],
    ):
        subprocess.run(cmd, cwd=r, check=True, capture_output=True, env=env)
    return r


def _deploy(repo: Path, *args):
    return subprocess.run(
        ["bash", str(repo / "scripts" / "deploy.sh"), *args],
        cwd=repo,
        capture_output=True,
        text=True,
    )


def test_a_branch_is_refused(repo):
    """Deploying `main` is how you get back to not knowing what is running:
    it names something different tomorrow, while the image stamp claims to
    describe a fixed thing."""
    r = _deploy(repo, "main")
    assert r.returncode != 0
    assert "not a tag" in r.stderr


def test_a_bare_commit_is_refused(repo):
    sha = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, capture_output=True, text=True
    ).stdout.strip()
    r = _deploy(repo, sha)
    assert r.returncode != 0, "a commit is not a released version"


def test_a_missing_tag_is_refused(repo):
    r = _deploy(repo, "v9.9.9")
    assert r.returncode != 0
    assert "not a tag" in r.stderr


def test_deploying_without_an_env_file_is_refused(repo):
    """The services would start on their defaults -- which for Postgres means
    a well-known password on a database holding everything that cannot be
    rebuilt."""
    r = _deploy(repo, "v0.0.1")
    assert r.returncode != 0
    assert ".env" in r.stderr
    assert "defaults" in r.stderr.lower()


def test_a_valid_tag_gets_past_the_guards(repo):
    """With .env present it proceeds to the build, which is as far as this
    can go without Docker. Reaching that point is the check."""
    (repo / ".env").write_text("PG_USER=x\n")
    r = _deploy(repo, "v0.0.1")
    assert "deploying v0.0.1" in r.stdout, (
        f"stopped before building.\nstdout={r.stdout}\nstderr={r.stderr}"
    )


def test_the_script_refuses_rather_than_guessing(repo):
    """Every refusal above must be a non-zero exit, so a deployment that did
    not happen cannot be mistaken for one that did."""
    for args in ((), ("main",), ("v9.9.9",)):
        assert _deploy(repo, *args).returncode != 0
