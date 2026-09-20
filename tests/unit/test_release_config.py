"""The release path is the one workflow nobody runs locally, so it is pinned here.

A push to main cuts a version, writes a changelog and publishes a GitHub
release. Everything that decides what version comes out lives in config nobody
looks at until it is wrong.
"""

import ast
import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
RELEASE = ROOT / ".github" / "workflows" / "release.yml"
CI = ROOT / ".github" / "workflows" / "ci.yml"
NOXFILE = ROOT / "noxfile.py"
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


def _default_sessions() -> list[str]:
    """nox.options.sessions, read without executing the noxfile."""
    tree = ast.parse(NOXFILE.read_text())
    for node in ast.walk(tree):
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.targets[0], ast.Attribute)
            and node.targets[0].attr == "sessions"
            and isinstance(node.value, (ast.List, ast.Tuple))
        ):
            return [ast.literal_eval(e) for e in node.value.elts]
    raise AssertionError("noxfile.py does not set nox.options.sessions")


def test_the_release_gate_runs_every_default_session():
    """The previous version of this test hardcoded ("lint_python", "types",
    "tests") and, despite its name, never opened ci.yml. So it did not compare
    anything - it pinned the subset in place.

    That subset omitted lint_sql, the session that runs `dbt parse` and writes
    target/manifest.json. The suite imports the Dagster definitions, which need
    that manifest, so `nox -s tests` died during collection and no v1.3.0 was
    ever tagged. CI passed throughout, because CI ran lint_sql first.

    The fix is for the release to name no sessions at all: bare `nox` runs
    nox.options.sessions, so the list cannot be a second, weaker definition of
    green.
    """
    step = next(s for s in _release_steps() if "Verify" in s.get("name", ""))
    run = step["run"]

    invocations = [
        ln.strip() for ln in run.splitlines() if re.match(r"^\s*uvx?\s+nox\b", ln)
    ]
    assert invocations, "the verification step does not run nox at all"
    for line in invocations:
        assert not re.search(r"(^|\s)(-s|--session)(\s|=)", line), (
            f"the release gate names sessions ({line!r}); bare `nox` runs the "
            "default list, so it cannot drift from CI"
        )


def test_ci_and_the_default_list_are_the_same_set():
    """CI names its sessions as separate steps so a red X says which check
    failed. That is a presentation choice over the same list - it must not
    become a second list. A session CI runs but the default list omits would
    never run before a release."""
    ci_steps = yaml.safe_load(CI.read_text())["jobs"]
    runs = [
        step.get("run", "")
        for job in ci_steps.values()
        for step in job.get("steps", [])
    ]
    named = {
        m.group(1)
        for r in runs
        for m in re.finditer(r"nox\s+-s\s+([A-Za-z_][A-Za-z0-9_]*)", r)
    }
    default = set(_default_sessions())
    missing = named - default
    assert not missing, (
        f"CI runs {sorted(missing)}, which nox.options.sessions omits, so they "
        "would not run before a release"
    )

    # And the other direction, which was unguarded and diverged. The release
    # gate runs bare `nox` - the whole default list - while CI named four
    # sessions. Two of the two it did not name REWROTE the tree (`ruff
    # check --fix`, `sqlfluff fix`), so the release gate was modifying the
    # code before checking it, and verifying something other than the commit
    # it was about to release.
    unrun = default - named
    assert not unrun, (
        f"nox.options.sessions includes {sorted(unrun)}, which CI never runs, "
        "so a change can be merged without them ever having passed"
    )


def test_ci_guards_pull_requests_into_main():
    on = yaml.safe_load(CI.read_text())[True]  # YAML parses bare `on:` as True
    assert "main" in on["pull_request"]["branches"]


def test_the_version_lives_in_exactly_one_place():
    """Two version strings drift. semantic-release rewrites pyproject; nothing
    else should claim to know the version."""
    text = PYPROJECT.read_text()
    assert 'version_toml = ["pyproject.toml:project.version"]' in text
    assert 'commit_parser = "conventional"' in text


def test_no_gate_runs_a_session_that_rewrites_the_tree():
    """A gate that modifies the code before checking it verifies something
    other than the commit it is about to release.

    `format_python` and `format_sql` run `ruff check --fix` and `sqlfluff
    fix`. They belong to a developer, not to a gate; their checking
    equivalents (`ruff format --diff`, `sqlfluff lint`) already run.
    """
    import ast

    tree = ast.parse(NOXFILE.read_text())
    mutating = set()
    for node in tree.body:
        if not isinstance(node, ast.FunctionDef):
            continue
        src = ast.get_source_segment(NOXFILE.read_text(), node) or ""
        if '"--fix"' in src or '"fix"' in src:
            mutating.add(node.name)

    assert mutating, "expected to find the formatting sessions"
    overlap = mutating & set(_default_sessions())
    assert not overlap, (
        f"{sorted(overlap)} rewrite the tree and are in the gate's check list"
    )


def test_every_gate_can_run_the_whole_list():
    """The warehouse session needs a database. A gate that runs the list
    without one fails on every change - which is the v1.3.0 failure again,
    from the other direction."""
    needs_db = "warehouse" in _default_sessions()
    if not needs_db:
        return
    for path in (CI, RELEASE):
        doc = yaml.safe_load(path.read_text())
        jobs = doc["jobs"]
        assert any(
            "postgres" in (job.get("services") or {}) for job in jobs.values()
        ), f"{path.name} runs the check list but provides no database for it"
