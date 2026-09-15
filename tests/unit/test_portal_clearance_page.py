"""Streamlit AppTest coverage for the Laatste kans page and its refresh button."""

from typing import Any, cast

import pandas as pd
import pytest
from dagster import DagsterRunStatus
from sqlalchemy.exc import ProgrammingError
from streamlit.testing.v1 import AppTest

from bonuschef.portal import clearance_page as page
from bonuschef.portal.clearance_page import _latest_snapshot, render_clearance
from bonuschef.portal.dagster_client import (
    REFRESH_PHASES,
    TERMINAL_STATUSES,
    DagsterTriggerError,
    RunProgress,
)
from tests.conftest import run_app


# _df() is scraped at 12:00Z = 14:00 local. Pin "now" to the same trading day so
# the suite exercises the fresh branch by default; stale cases move the clock.
SCRAPED_AT = "2026-09-07T12:00:00Z"
FRESH_NOW = pd.Timestamp("2026-09-07 16:00", tz=page._LOCAL_TZ)


def _df(rows=2) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "product_name": [f"Product {i}" for i in range(rows)],
            "brand": ["AH"] * rows,
            "sales_unit_size": ["500 g"] * rows,
            "category_title": ["Vlees", "Zuivel"][:rows],
            "markdown_type": ["EXPIRATION", "OUT_OF_ASSORTMENT"][:rows],
            "markdown_percentage": [35.0, 50.0][:rows],
            "markdown_expiration_date": ["2026-09-08"] * rows,
            "stock": [3, 1][:rows],
            "price_was": [4.99, 2.0][:rows],
            "price_now": [3.24, 1.0][:rows],
            "markdown_amount": [1.75, 1.0][:rows],
            "tracked_price": [4.5, None][:rows],
            "real_savings_vs_tracked": [1.26, None][:rows],
            "image_url": [None] * rows,
            "scraped_at": [SCRAPED_AT] * rows,
        }
    )


class ReadStub:
    """Mimics the st.cache_data-wrapped query, including ``.clear()``."""

    def __init__(self, outcome):
        self.outcome = outcome
        self.cleared = 0

    def __call__(self, engine):
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome

    def clear(self):
        self.cleared += 1


class ScrapeTimeStub:
    """Mimics read_last_scrape_time, including ``.clear()``.

    ``advance_to`` models a scrape that actually found something newer: the
    page clears the cache and re-queries, so the second read must be able to
    return a different value or the success path can never be exercised.
    """

    def __init__(self, outcome, advance_to=None):
        self.outcome = outcome
        self.advance_to = advance_to
        self.cleared = 0

    def __call__(self, engine):
        return self.outcome

    def clear(self):
        self.cleared += 1
        if self.advance_to is not None:
            self.outcome = self.advance_to


@pytest.fixture
def stubs(monkeypatch):
    """Wire the page to fakes; returns a dict the test can tweak before running."""
    state: dict[str, Any] = {
        "read": ReadStub(_df()),
        "run_id": "run-1234567890",
        "trigger_error": None,
        "status": DagsterRunStatus.SUCCESS,
        "triggered": [],
        "now": FRESH_NOW,
        "last_scrape": ScrapeTimeStub(pd.Timestamp(SCRAPED_AT, tz="UTC")),
    }

    def trigger(job_name):
        if state["trigger_error"]:
            raise state["trigger_error"]
        state["triggered"].append(job_name)
        return state["run_id"]

    monkeypatch.setattr(page, "get_engine", lambda: object())
    monkeypatch.setattr(page, "read_store_clearance", state["read"])
    monkeypatch.setattr(page, "read_last_scrape_time", state["last_scrape"])
    monkeypatch.setattr(page, "_now", lambda: state["now"])
    monkeypatch.setattr(page, "trigger_job", trigger)

    # The refresh no longer waits; it records a run id and reads the run's own
    # progress on each render, which is what survives a dropped phone session.
    def progress(run_id, *a, **kw):
        status = state["status"]
        total = len(REFRESH_PHASES)
        if status == DagsterRunStatus.QUEUED:
            return RunProgress(status, "In de wachtrij…", 0, total)
        if status in TERMINAL_STATUSES:
            return RunProgress(status, "Klaar", total, total)
        return RunProgress(
            status, state.get("phase", "De winkel wordt gescand…"), 0, total
        )

    monkeypatch.setattr(page, "get_run_progress", progress)
    return state


def _run(default_timeout=10) -> AppTest:
    return run_app(render_clearance, default_timeout=default_timeout).run()


def test_latest_snapshot_is_amsterdam_local_time():
    ts = _latest_snapshot(_df())
    assert ts.tzinfo is not None
    assert ts.strftime("%Y-%m-%d %H:%M %Z") == "2026-09-07 14:00 CEST"


def test_renders_items_as_cards_with_a_local_caption(stubs):
    at = _run()
    assert not at.exception
    assert at.title[0].value == "Laatste kans koopjes"
    captions = [c.value for c in at.caption]
    assert any("2026-09-07 14:00" in c for c in captions)

    # A shopping list read on a phone: cards, not a ten-column grid.
    assert not at.dataframe, "items should not render as a spreadsheet widget"
    text = " ".join(m.value for m in at.markdown)
    assert "Product 0" in text and "Product 1" in text
    assert "€3.24" in text and "€1.00" in text

    # A summary line, not a metric row - "Matched to tracked" was a join
    # coverage statistic about the pipeline.
    assert not at.metric
    assert any("2 koopjes" in m.value for m in at.markdown)
    assert any("Bijna over datum" in c for c in captions)
    assert at.button[0].label == "Nu ophalen"


def test_urgency_is_visible_on_the_item(stubs):
    """Low stock and a same-day expiry are the reason to go now rather than
    later, so they belong on the card itself."""
    df = _df()
    df["stock"] = [2, 50]
    df["markdown_expiration_date"] = ["2026-09-07", "2026-12-01"]
    stubs["read"].outcome = df
    at = _run()
    # st.badge renders into the markdown stream as :orange-badge[...].
    rendered = " ".join(m.value for m in at.markdown)
    assert "nog 2" in rendered, "low stock not surfaced"
    assert "THT vandaag" in rendered, "same-day expiry not surfaced"
    assert "orange-badge" in rendered, "urgency should read as urgent"


def test_category_filter_narrows_the_list(stubs):
    at = _run()
    at.multiselect[0].select("Zuivel").run()
    text = " ".join(m.value for m in at.markdown)
    assert "Product 1" in text
    assert "Product 0" not in text


def test_missing_mart_shows_hint_and_button(stubs):
    stubs["read"].outcome = ProgrammingError("SELECT", {}, Exception("no relation"))
    at = _run()
    assert not at.exception
    assert "Nog geen koopjes" in at.info[0].value
    assert at.button[0].label == "Nu ophalen"
    assert not at.metric


def test_database_error_is_reported_not_hidden(stubs):
    stubs["read"].outcome = RuntimeError("connection refused")
    at = _run()
    assert "Geen verbinding met de database" in at.error[0].value
    assert not at.button


def test_empty_snapshot_message(stubs):
    stubs["read"].outcome = _df(0)
    at = _run()
    assert "Geen koopjes" in at.info[0].value
    assert at.button[0].label == "Nu ophalen"


def test_refresh_success_reruns_and_clears_cache(stubs):
    # The scrape finds something newer, so the snapshot genuinely advances.
    stubs["last_scrape"].advance_to = pd.Timestamp("2026-09-07T13:00:00Z", tz="UTC")
    at = _run()
    at.button[0].click().run()
    assert not at.exception
    assert stubs["triggered"] == ["markdowns_refresh"]
    assert stubs["read"].cleared == 1
    assert any(s.value.startswith("Opgehaald om") for s in at.success)
    # Banner is one-shot: a plain rerun must not show it again.
    at.run()
    assert not at.success


def test_a_refresh_that_finds_nothing_new_does_not_claim_freshness(stubs):
    """The Dagster run succeeding is not the snapshot moving. A green tick over
    unchanged data is worse than the staleness this page now guards against."""
    at = _run()
    at.button[0].click().run()
    assert not at.exception
    assert stubs["triggered"] == ["markdowns_refresh"]
    assert not at.success, "claimed a refresh that did not happen"
    assert any("niets nieuwers" in w.value for w in at.warning)


def test_refresh_trigger_failure_shows_error(stubs):
    stubs["trigger_error"] = DagsterTriggerError("Could not start job")
    at = _run()
    at.button[0].click().run()
    assert "Could not start job" in at.error[0].value
    assert "Dagster-webserver" in at.error[0].value
    assert stubs["read"].cleared == 0


def test_refresh_run_failure_mentions_run_and_token(stubs):
    stubs["status"] = DagsterRunStatus.FAILURE
    at = _run()
    at.button[0].click().run()
    message = at.error[0].value
    assert "run-1234" in message
    assert "AH-token" in message
    assert stubs["read"].cleared == 0


def test_a_running_refresh_shows_progress_not_a_timeout(stubs):
    """It no longer blocks, so a run still going is a state the page reports."""
    stubs["status"] = DagsterRunStatus.STARTED
    at = _run()
    at.button[0].click().run()
    bars = at.get("progress")
    assert bars, "a run in flight must show its progress"
    # AppTest exposes the caption on the proto, not on .value (an int percent).
    assert "gescand" in bars[0].proto.text
    assert stubs["read"].cleared == 0, "nothing to clear until it finishes"


def test_a_queued_refresh_is_not_described_as_scanning(stubs):
    """Runs are serialised instance-wide on purpose, so waiting is normal. The
    old spinner said "de winkel wordt gescand" while a run sat 44th in a queue,
    which sent an hour of debugging at the wrong component."""
    stubs["status"] = DagsterRunStatus.QUEUED
    at = _run()
    at.button[0].click().run()
    bars = at.get("progress")
    assert bars and "wachtrij" in bars[0].proto.text
    assert "gescand" not in bars[0].proto.text


def test_the_bar_reflects_the_phase_not_the_clock(stubs):
    """A bar advancing on elapsed time is a decoration, and would have read
    "almost done" through three minutes of a queued run doing nothing."""
    stubs["status"] = DagsterRunStatus.STARTED
    stubs["phase"] = "De prijzen worden bijgewerkt…"
    at = _run()
    at.button[0].click().run()
    bars = at.get("progress")
    assert bars and "prijzen" in bars[0].proto.text


def test_the_outcome_survives_a_session_that_did_no_waiting(stubs):
    """A phone that backgrounded the tab drops its websocket and the session
    resets. The run id is what survives that; a pending wait is not."""
    at = run_app(render_clearance, default_timeout=10)
    at.session_state[page._RUN_KEY] = "run-1234567890"
    at.run()
    assert stubs["read"].cleared == 1, "a finished run must reach a fresh session"


def test_losing_sight_of_the_run_is_not_an_error(stubs, monkeypatch):
    def gone(run_id, *a, **kw):
        raise DagsterTriggerError("no such run")

    monkeypatch.setattr(page, "get_run_progress", gone)
    at = run_app(render_clearance, default_timeout=10)
    at.session_state[page._RUN_KEY] = "run-1234567890"
    at.run()
    assert not at.error, "the scrape either happened or did not; the banner reads it"
    assert page._RUN_KEY not in at.session_state


def _utc(value: str) -> pd.Timestamp:
    """Build fixtures from UTC.

    ``pd.Timestamp("2026-10-25 02:30", tz=_LOCAL_TZ)`` raises AmbiguousTimeError
    on the fall-back day; converting from UTC is always total.
    """
    return cast(pd.Timestamp, pd.Timestamp(value, tz="UTC"))


class TestIsCurrent:
    """The trading-day rule, including the cases a naive implementation gets
    wrong. These need no AppTest — the predicate is pure."""

    def test_same_trading_day(self):
        assert page._is_current(_utc("2026-09-07T07:00"), _utc("2026-09-07T14:00"))

    def test_previous_evening_is_not_current(self):
        # 13 hours, but the store restocked and re-marked in between.
        assert not page._is_current(_utc("2026-09-06T18:00"), _utc("2026-09-07T07:00"))

    def test_months_old_is_not_current(self):
        assert not page._is_current(_utc("2026-07-06T12:22"), _utc("2026-09-13T09:00"))

    def test_utc_date_rollover_is_judged_in_local_time(self):
        """In summer a snapshot at 23:30 local is still 21:30 UTC, and 00:30
        local the next day is still 22:30 UTC — same UTC date, different
        trading days. Comparing UTC dates would call this current."""
        snapshot, now = _utc("2026-09-13T21:30"), _utc("2026-09-13T22:30")
        assert snapshot.date() == now.date(), "precondition: same UTC date"
        assert not page._is_current(snapshot, now)

    def test_spring_forward_does_not_split_the_day(self):
        """01:30+01:00 and 03:30+02:00 are one hour apart and the same date."""
        assert page._is_current(_utc("2026-03-29T00:30"), _utc("2026-03-29T01:30"))

    def test_fall_back_repeated_hour_stays_one_day(self):
        """02:30 happens twice on 2026-10-25; both are the same trading day."""
        assert page._is_current(_utc("2026-10-25T00:30"), _utc("2026-10-25T01:30"))

    def test_missing_snapshot_is_never_current(self):
        assert not page._is_current(None, _utc("2026-09-07T14:00"))


class TestResolveSnapshot:
    """NaT is normalised to None at this boundary, so nothing downstream has to
    guard it — pandas cannot strftime a NaT and that was a live crash."""

    def test_prefers_the_scrape_history(self):
        history = _utc("2026-09-07T15:00")
        assert page._resolve_snapshot(history, _df()) == history

    def test_falls_back_to_the_frame_when_history_is_absent(self):
        assert page._resolve_snapshot(None, _df()) == _utc("2026-09-07T12:00")

    def test_nat_becomes_none(self):
        df = _df()
        df["scraped_at"] = [None, None]
        assert page._resolve_snapshot(pd.NaT, df) is None

    def test_empty_frame_with_no_history_is_unknown(self):
        assert page._resolve_snapshot(None, _df(rows=0)) is None


class TestDescribeAge:
    @pytest.mark.parametrize(
        ("hours", "expected"),
        [
            (0.5, "minder dan een uur oud"),
            (1, "1 uur oud"),
            (13, "13 uur oud"),
            (72, "3 dagen oud"),
            (69 * 24, "2 maanden oud"),
        ],
    )
    def test_wording(self, hours, expected):
        now = _utc("2026-09-13T12:00")
        earlier = cast(pd.Timestamp, now - pd.Timedelta(hours=hours))
        assert page._describe_age(earlier, now) == expected


class TestStaleRendering:
    def test_stale_snapshot_hides_items_and_metrics(self, stubs):
        """The failure mode is driving to the store for something sold weeks
        ago, so a stale table is worse than no table."""
        stubs["now"] = pd.Timestamp("2026-09-09 14:00", tz=page._LOCAL_TZ)
        at = _run()
        assert not at.exception
        assert not at.dataframe, "stale items were rendered"
        assert not at.metric, "stale metrics were rendered"
        assert any("niet van vandaag" in w.value for w in at.warning)
        assert at.button[0].label == "Nu ophalen"

    def test_stale_still_states_the_capture_time_in_local_time(self, stubs):
        stubs["now"] = pd.Timestamp("2026-09-09 14:00", tz=page._LOCAL_TZ)
        at = _run()
        assert any("2026-09-07 14:00" in c.value for c in at.caption)

    def test_before_the_first_scrape_reads_as_not_yet_not_broken(self, stubs):
        """With a trading-day rule the page is stale every morning until 11:00.
        That is normal operation, and must not look like a failure."""
        stubs["now"] = pd.Timestamp("2026-09-08 09:00", tz=page._LOCAL_TZ)
        at = _run()
        assert not at.dataframe
        assert not at.warning, "normal morning state must not warn"
        assert any("nog niet" in i.value for i in at.info)

    def test_an_empty_but_fresh_snapshot_is_not_called_stale(self, stubs):
        """A scrape that succeeded and found nothing has no rows to date, so
        freshness comes from the scrape history. Otherwise 'nothing on
        clearance right now' is indistinguishable from a dead pipeline."""
        stubs["read"].outcome = _df(rows=0)
        at = _run()
        assert not at.exception
        assert not at.warning
        assert any("Geen koopjes" in i.value for i in at.info)

    def test_all_null_scrape_times_do_not_crash_the_page(self, stubs):
        """pd.NaT cannot be strftime'd; the caption used to raise ValueError."""
        df = _df()
        df["scraped_at"] = [None, None]
        stubs["read"].outcome = df
        stubs["last_scrape"].outcome = None
        at = _run()
        assert not at.exception
        assert not at.dataframe
