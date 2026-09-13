"""Streamlit AppTest coverage for the Laatste kans page and its refresh button."""

from typing import Any

import pandas as pd
import pytest
from dagster import DagsterRunStatus
from sqlalchemy.exc import ProgrammingError
from streamlit.testing.v1 import AppTest

from bonuschef.portal import clearance_page as page
from bonuschef.portal.clearance_page import _latest_snapshot, render_clearance
from bonuschef.portal.dagster_client import DagsterTriggerError
from tests.conftest import run_app


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
            "scraped_at": ["2026-09-07T12:00:00Z"] * rows,
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


@pytest.fixture
def stubs(monkeypatch):
    """Wire the page to fakes; returns a dict the test can tweak before running."""
    state: dict[str, Any] = {
        "read": ReadStub(_df()),
        "run_id": "run-1234567890",
        "trigger_error": None,
        "status": DagsterRunStatus.SUCCESS,
        "triggered": [],
    }

    def trigger(job_name):
        if state["trigger_error"]:
            raise state["trigger_error"]
        state["triggered"].append(job_name)
        return state["run_id"]

    monkeypatch.setattr(page, "get_engine", lambda: object())
    monkeypatch.setattr(page, "read_store_clearance", state["read"])
    monkeypatch.setattr(page, "trigger_job", trigger)
    monkeypatch.setattr(page, "wait_for_run", lambda run_id, timeout_s: state["status"])
    return state


def _run(default_timeout=10) -> AppTest:
    return run_app(render_clearance, default_timeout=default_timeout).run()


def test_latest_snapshot_is_amsterdam_local_time():
    ts = _latest_snapshot(_df())
    assert ts.tzinfo is not None
    assert ts.strftime("%Y-%m-%d %H:%M %Z") == "2026-09-07 14:00 CEST"


def test_renders_metrics_table_and_local_caption(stubs):
    at = _run()
    assert not at.exception
    assert at.title[0].value == "Laatste kans koopjes"
    captions = [c.value for c in at.caption]
    assert any("2026-09-07 14:00 (local time)" in c for c in captions)
    metrics = {m.label: m.value for m in at.metric}
    assert metrics["Clearance items"] == "2"
    assert metrics["Max discount"] == "50%"
    assert metrics["Matched to tracked"] == "1"
    table = at.dataframe[0].value
    assert list(table["Reason"]) == ["Expiring soon", "Discontinued"]
    assert at.button[0].label == "Refresh now"


def test_category_filter_narrows_table(stubs):
    at = _run()
    at.multiselect[0].select("Zuivel").run()
    assert list(at.dataframe[0].value["Product"]) == ["Product 1"]


def test_missing_mart_shows_hint_and_button(stubs):
    stubs["read"].outcome = ProgrammingError("SELECT", {}, Exception("no relation"))
    at = _run()
    assert not at.exception
    assert "No clearance data yet" in at.info[0].value
    assert at.button[0].label == "Refresh now"
    assert not at.metric


def test_database_error_is_reported_not_hidden(stubs):
    stubs["read"].outcome = RuntimeError("connection refused")
    at = _run()
    assert "Database connection error" in at.error[0].value
    assert not at.button


def test_empty_snapshot_message(stubs):
    stubs["read"].outcome = _df(0)
    at = _run()
    assert "No clearance items" in at.info[0].value
    assert at.button[0].label == "Refresh now"


def test_refresh_success_reruns_and_clears_cache(stubs):
    at = _run()
    at.button[0].click().run()
    assert not at.exception
    assert stubs["triggered"] == ["markdowns_refresh"]
    assert stubs["read"].cleared == 1
    assert any(s.value.startswith("Refreshed at") for s in at.success)
    # Banner is one-shot: a plain rerun must not show it again.
    at.run()
    assert not at.success


def test_refresh_trigger_failure_shows_error(stubs):
    stubs["trigger_error"] = DagsterTriggerError("Could not start job")
    at = _run()
    at.button[0].click().run()
    assert "Could not start job" in at.error[0].value
    assert "Dagster webserver" in at.error[0].value
    assert stubs["read"].cleared == 0


def test_refresh_run_failure_mentions_run_and_token(stubs):
    stubs["status"] = DagsterRunStatus.FAILURE
    at = _run()
    at.button[0].click().run()
    message = at.error[0].value
    assert "run-1234" in message
    assert "AH_REFRESH_TOKEN" in message
    assert stubs["read"].cleared == 0


def test_refresh_timeout_warns(stubs):
    stubs["status"] = DagsterRunStatus.STARTED
    at = _run()
    at.button[0].click().run()
    assert "still" in at.warning[0].value
    assert stubs["read"].cleared == 0
