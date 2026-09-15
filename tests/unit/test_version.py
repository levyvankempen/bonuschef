"""What the deployment claims to be.

The point of this module is that a build from a modified tree must not be
mistakable for the release it resembles, so most of these tests are about the
cases that are *not* a clean release.
"""

import subprocess
from pathlib import Path

import pytest

from bonuschef import version as v

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "version.sh"


@pytest.fixture(autouse=True)
def _clear_stamp(monkeypatch):
    monkeypatch.delenv("BONUSCHEF_VERSION", raising=False)
    monkeypatch.delenv("BONUSCHEF_COMMIT", raising=False)


def test_the_build_stamp_wins_over_package_metadata(monkeypatch):
    """The image is stamped from `git describe`, which knows things the
    packaged version cannot -- how far past a tag it is, and whether the tree
    was clean. Metadata would flatten all of that to one number."""
    monkeypatch.setenv("BONUSCHEF_VERSION", "v9.9.9-3-gdeadbee")
    assert v.get_version() == "v9.9.9-3-gdeadbee"


def test_a_missing_stamp_falls_back_to_the_installed_package():
    """Running outside Docker, where the build argument was never set."""
    assert v.get_version() not in ("", None)


def test_an_unknown_stamp_is_not_taken_at_face_value(monkeypatch):
    """`unknown` is the Dockerfile's ARG default, so it means "not stamped",
    not "the version is literally unknown". Falling through to metadata gives
    a better answer than repeating the placeholder."""
    monkeypatch.setenv("BONUSCHEF_VERSION", "unknown")
    assert v.get_version() != "unknown"


@pytest.mark.parametrize(
    ("stamp", "released"),
    [
        ("v1.3.0", True),
        ("1.3.0", True),
        ("v1.3.0-5-gabc1234", False),  # past the tag
        ("v1.3.0-dirty", False),  # uncommitted changes
        ("v1.3.0-5-gabc1234-dirty", False),  # both
        ("1.3.0-nogit", False),  # built without history
        ("unknown", False),
    ],
)
def test_only_an_exact_tag_counts_as_a_release(stamp, released, monkeypatch):
    monkeypatch.setenv("BONUSCHEF_VERSION", stamp)
    assert v.is_release() is released


def test_a_build_that_is_not_a_release_says_so(monkeypatch):
    """This is the whole point: someone reading the portal footer must be able
    to tell that what is running was never tagged."""
    monkeypatch.setenv("BONUSCHEF_VERSION", "v1.3.0-5-gabc1234-dirty")
    assert "geen release" in v.describe()

    monkeypatch.setenv("BONUSCHEF_VERSION", "v1.3.0")
    assert "geen release" not in v.describe()


def test_describing_a_version_never_raises(monkeypatch):
    """It renders in the portal chrome. A footer that can take the page down
    with it is worse than no footer."""
    for stamp in ("", "unknown", "   ", "v1.3.0", "nonsense-!@#", "-", "v"):
        monkeypatch.setenv("BONUSCHEF_VERSION", stamp)
        assert isinstance(v.describe(), str)
        assert isinstance(v.is_release(), bool)


def test_the_commit_is_unknown_rather_than_empty(monkeypatch):
    assert v.get_commit() == "unknown"
    monkeypatch.setenv("BONUSCHEF_COMMIT", "   ")
    assert v.get_commit() == "unknown"
    monkeypatch.setenv("BONUSCHEF_COMMIT", "abc1234")
    assert v.get_commit() == "abc1234"


# --- the shell side: what gets stamped in ---------------------------------


def _run(root: Path) -> dict[str, str]:
    """Invoke the copy of the script that lives in `root`.

    The script resolves its own directory and works from there, so that
    `scripts/version.sh` reports on the checkout it belongs to no matter where
    it is called from. Running the repository's own copy against a temporary
    directory would therefore measure the repository, not the fixture.
    """
    out = subprocess.run(
        ["bash", str(root / "scripts" / "version.sh")],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.strip().splitlines())


def test_the_script_reports_a_version_and_a_commit():
    got = _run(ROOT)
    assert set(got) == {"version", "commit"}
    assert got["version"]


def test_an_untracked_file_still_marks_the_build_dirty(tmp_path):
    """`git describe --dirty` only notices *tracked* modifications. An
    untracked file would otherwise be stamped as a clean release."""
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "scripts").mkdir()
    (repo / "scripts" / "version.sh").write_text(SCRIPT.read_text())
    (repo / "pyproject.toml").write_text('version = "0.0.1"\n')
    env = {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t", **_git_env()}
    for cmd in (
        ["git", "init", "-q"],
        ["git", "add", "-A"],
        ["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"],
        ["git", "tag", "v0.0.1"],
    ):
        subprocess.run(cmd, cwd=repo, check=True, capture_output=True, env=env)

    assert _run(repo)["version"] == "v0.0.1", "a clean tag should be the bare version"

    (repo / "stray.txt").write_text("untracked")
    assert _run(repo)["version"].endswith("-dirty"), (
        "an untracked file left the build looking like a clean release"
    )


def test_a_checkout_without_history_is_marked_as_such(tmp_path):
    """A tarball or CI archive. The version is a guess at provenance, and
    says so, rather than claiming to be the release it was cut from."""
    plain = tmp_path / "plain"
    (plain / "scripts").mkdir(parents=True)
    (plain / "scripts" / "version.sh").write_text(SCRIPT.read_text())
    (plain / "pyproject.toml").write_text('version = "1.2.3"\n')
    got = _run(plain)
    assert got["version"] == "1.2.3-nogit"
    assert got["commit"] == "unknown"


def _git_env() -> dict[str, str]:
    import os

    return {
        **os.environ,
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
    }


def test_the_portal_renders_the_version():
    """Wiring check, by reading the source rather than booting Streamlit: the
    app module's navigation needs a database, and this suite stays DB-free.

    The version module is tested thoroughly above; what this catches is the
    caption being dropped from the page during an unrelated edit, which would
    silently return the deployment to having no visible provenance.
    """
    import ast

    app = ROOT / "src" / "bonuschef" / "portal" / "app.py"
    tree = ast.parse(app.read_text())
    called = {
        n.func.id
        for n in ast.walk(tree)
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
    }
    assert "describe" in called, "the portal does not show which version it runs"
