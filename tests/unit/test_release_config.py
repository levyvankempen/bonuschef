"""The release path is the one workflow nobody runs locally, so it is pinned here.

A push to main cuts a version, writes a changelog and publishes a GitHub
release. Everything that decides what version comes out lives in config nobody
looks at until it is wrong.
"""

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
PYPROJECT = ROOT / "pyproject.toml"


def _release_steps() -> list[dict]:
    return yaml.safe_load(RELEASE.read_text())["jobs"]["release"]["steps"]


def test_the_release_checkout_can_see_previous_releases():
    """semantic-release derives the next version from the last tag. The default
    shallow clone fetches one commit and no tags, so it would compute a version
    from nothing - and the failure is a wrong version number, not an error."""
    checkout = _release_steps()[0]
    assert "actions/checkout" in checkout["uses"]
    assert checkout["with"].get("fetch-depth") == 0, "shallow clone hides the tags"
    assert checkout["with"].get("fetch-tags") is True


def test_main_is_verified_before_it_is_released():
    """CI runs on pull requests only. Without a check here, a direct push to
    main - or a merge that broke something no PR exercised - gets tagged and
    published untested."""
    names = [s.get("name", "") for s in _release_steps()]
    verify = next((i for i, n in enumerate(names) if "Verify" in n), None)
    release = next((i for i, n in enumerate(names) if "Semantic version" in n), None)
    assert verify is not None, "nothing verifies main before it is released"
    assert release is not None
    assert verify < release, "verification must precede the release, not follow it"


def test_the_verification_runs_the_same_checks_as_ci():
    """Two definitions of "green" that can drift is worse than one that is
    stricter than needed."""
    step = next(s for s in _release_steps() if "Verify" in s.get("name", ""))
    for session in ("lint_python", "types", "tests"):
        assert session in step["run"], f"release does not run nox -s {session}"


def test_ci_guards_pull_requests_into_main():
    on = yaml.safe_load(CI.read_text())[True]  # YAML parses bare `on:` as True
    assert "main" in on["pull_request"]["branches"]


def test_the_version_lives_in_exactly_one_place():
    """Two version strings drift. semantic-release rewrites pyproject; nothing
    else should claim to know the version."""
    text = PYPROJECT.read_text()
    assert 'version_toml = ["pyproject.toml:project.version"]' in text
    assert 'commit_parser = "conventional"' in text
