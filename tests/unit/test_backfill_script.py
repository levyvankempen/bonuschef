"""The one-off backfill.

It is the deliberate counterpart to the nightly asset: same logic, no nightly
budget. The things worth checking are that it cannot run away, that it uses
the shipped matching rather than a second copy of it, and that --dry-run
writes nothing.
"""

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "backfill_resolutions.py"


def _tree() -> ast.Module:
    return ast.parse(SCRIPT.read_text())


def test_it_reuses_the_shipped_matching():
    """A second implementation of the matching would drift from the asset's,
    and then the backfill and the nightly run would disagree about what the
    right product is."""
    imported = {
        alias.name
        for node in ast.walk(_tree())
        if isinstance(node, ast.ImportFrom)
        for alias in node.names
    }
    assert "_candidates_for" in imported, "the backfill matches by its own rules"
    assert "replace_proposals" in imported


def test_it_cannot_run_away():
    """An unbounded loop against someone else's API is the failure mode that
    matters here - not a wrong product, a banned credential."""
    source = SCRIPT.read_text()
    assert "SAFETY_STOP" in source
    assert "while spent < SAFETY_STOP" in source, (
        "the loop is not bounded by the safety stop"
    )


def test_a_dry_run_writes_nothing():
    """The whole point of offering --dry-run is that it is safe to point at
    production before committing to it."""
    source = SCRIPT.read_text()
    dry = source.index("if args.dry_run:")
    write = source.index("replace_proposals(engine,")
    assert dry < write, "--dry-run is checked after the write"
    segment = source[dry : dry + 320]
    assert "continue" in segment, "--dry-run does not skip the write"


def test_it_is_safe_to_interrupt_and_rerun():
    """Each concept is its own transaction, and re-deriving one stamps it as
    freshly proposed, so the queue advances rather than restarting."""
    source = SCRIPT.read_text()
    assert "read_stale_concepts" in source
    assert "Safe to interrupt" in source, (
        "the resumability contract is not written down where an operator reads it"
    )


def test_a_dry_run_terminates():
    """Nothing is stamped under --dry-run, so the same batch would be returned
    forever unless the script tracks what it has already seen."""
    source = SCRIPT.read_text()
    assert "seen" in source
    assert 'row["concept_id"] not in seen' in source, (
        "--dry-run would loop on the same batch forever"
    )


def test_a_transient_failure_does_not_end_the_run():
    """A read timeout against the retailer happened 8 concepts into the first
    trial. Over a 25-minute run they are ordinary; stopping on the first would
    make the whole backfill a coin flip."""
    source = SCRIPT.read_text()
    assert "MAX_CONSECUTIVE_FAILURES" in source
    assert "consecutive >= MAX_CONSECUTIVE_FAILURES" in source, (
        "any single failure still ends the run"
    )


def test_it_says_which_kind_of_stop_it_was():
    """ "Run it again" and "something is wrong" are different messages. The
    first version reported the safety limit for a network timeout, which sends
    the operator the wrong way."""
    source = SCRIPT.read_text()
    assert "stopped early:" in source
    assert "stopped at the safety limit" in source
    assert "nothing left to re-derive" in source


def test_a_retried_concept_is_not_counted_as_examined():
    """Otherwise a flaky network inflates the progress numbers and the
    operator thinks it got further than it did."""
    source = SCRIPT.read_text()
    assert 'seen.discard(row["concept_id"])' in source
    assert "examined -= 1" in source
