"""Contracts between the scripts, which each script's own tests cannot see.

`auto-deploy.sh` calls `deploy.sh` and reads its exit code. In the auto-deploy
tests `deploy.sh` is replaced by a recorder that exits whatever the test asks
for, so the number they agree on is invented by the fixture rather than read
from the thing it stands in for. Both suites pass with the two scripts
disagreeing.

This is the class the spec calls "a check exercises the arrangement production
uses": a fixture may replace a component's EFFECTS - driving Docker, in this
case - but not the interface being relied on.
"""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEPLOY = ROOT / "scripts" / "deploy.sh"
AUTO = ROOT / "scripts" / "auto-deploy.sh"
TESTS = ROOT / "tests" / "unit" / "test_auto_deploy.py"


def _in_flight_exit_code() -> int:
    """The code deploy.sh uses when it refuses because a run is in flight."""
    source = DEPLOY.read_text()
    marker = source.index("run(s) in flight")
    tail = source[marker : marker + 400]
    match = re.search(r"exit (\d+)", tail)
    assert match, "deploy.sh no longer exits with a code when a run is in flight"
    return int(match.group(1))


def _retried_exit_code() -> int:
    """The code auto-deploy.sh treats as 'try again next tick'."""
    source = AUTO.read_text()
    marker = source.index("will retry on the next tick")
    head = source[:marker]
    codes = re.findall(r"^\s*(\d+)\)", head, re.M)
    assert codes, "auto-deploy.sh no longer branches on an exit code"
    return int(codes[-1])


def test_the_two_scripts_agree_on_what_in_flight_means():
    """If they drift, "a Dagster run is in progress" - which happens several
    times a day - stops being a deferral and becomes a hard failure. The timer
    would then report failure daily, be muted within a week, and the real
    failures would be invisible behind it.

    Neither script's own tests can catch this: auto-deploy's fixture replaces
    deploy.sh with a recorder and tells it which code to exit with.
    """
    assert _in_flight_exit_code() == _retried_exit_code(), (
        f"deploy.sh exits {_in_flight_exit_code()} when a run is in flight, but "
        f"auto-deploy.sh retries on {_retried_exit_code()} and would treat it "
        "as a deployment failure"
    )


def test_the_fixture_takes_the_code_from_the_script_it_stands_in_for():
    """A recorder that hardcodes the number cannot notice the number
    changing, which is how the contract came to be untested in the first
    place."""
    body = TESTS.read_text()
    assert "_in_flight_exit_code" in body or "IN_FLIGHT_EXIT" in body, (
        "the auto-deploy tests still invent the exit code rather than reading "
        "it from deploy.sh"
    )


def test_deploy_refusals_are_distinguishable():
    """Every refusal exits with its own code, so a caller can tell "a run is
    in flight" from "that is not a tag". Reusing one would make them
    indistinguishable to auto-deploy.sh, which only defers on one of them."""
    codes = re.findall(r"^\s*exit (\d+)", DEPLOY.read_text(), re.M)
    refusals = [int(c) for c in codes if c != "0"]
    assert len(refusals) == len(set(refusals)), (
        f"deploy.sh reuses an exit code across different refusals: {refusals}"
    )
