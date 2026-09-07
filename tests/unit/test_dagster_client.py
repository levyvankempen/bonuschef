"""Tests for the portal's Dagster trigger/poll helpers (no network)."""

import pytest
from dagster import DagsterRunStatus

from bonuschef.config import DagsterConfig
from bonuschef.portal import dagster_client
from bonuschef.portal.dagster_client import (
    DagsterTriggerError,
    get_run_status,
    trigger_job,
    wait_for_run,
)

CFG = DagsterConfig(host="dagster", port=3000)


class FakeClient:
    """Stand-in for DagsterGraphQLClient driven by a scripted status sequence."""

    def __init__(self, statuses=(), submit_error=None):
        self._statuses = list(statuses)
        self._submit_error = submit_error
        self.submitted: list[str] = []
        self.polled = 0

    def submit_job_execution(self, job_name):
        if self._submit_error:
            raise self._submit_error
        self.submitted.append(job_name)
        return "run-abc123"

    def get_run_status(self, run_id):
        self.polled += 1
        if not self._statuses:
            raise ConnectionError("webserver gone")
        return self._statuses.pop(0)


@pytest.fixture
def fake(monkeypatch):
    holder: dict[str, FakeClient] = {}

    def install(client: FakeClient) -> FakeClient:
        monkeypatch.setattr(dagster_client, "_client", lambda cfg=None: client)
        holder["client"] = client
        return client

    return install


def test_trigger_job_returns_run_id(fake):
    client = fake(FakeClient())
    assert trigger_job("markdowns_refresh", CFG) == "run-abc123"
    assert client.submitted == ["markdowns_refresh"]


def test_trigger_job_wraps_transport_errors(fake):
    fake(FakeClient(submit_error=ConnectionError("refused")))
    with pytest.raises(DagsterTriggerError, match="markdowns_refresh"):
        trigger_job("markdowns_refresh", CFG)


def test_get_run_status_wraps_errors(fake):
    fake(FakeClient(statuses=[]))
    with pytest.raises(DagsterTriggerError, match="run-abc1"):
        get_run_status("run-abc123", CFG)


def test_wait_for_run_polls_until_terminal(fake):
    client = fake(
        FakeClient(
            statuses=[
                DagsterRunStatus.QUEUED,
                DagsterRunStatus.STARTED,
                DagsterRunStatus.SUCCESS,
            ]
        )
    )
    sleeps: list[float] = []
    status = wait_for_run(
        "run-abc123",
        timeout_s=60,
        poll_s=2,
        cfg=CFG,
        sleep=sleeps.append,
        clock=lambda: 0,
    )
    assert status == DagsterRunStatus.SUCCESS
    assert client.polled == 3
    assert sleeps == [2, 2]


def test_wait_for_run_returns_last_status_on_timeout(fake):
    fake(FakeClient(statuses=[DagsterRunStatus.STARTED] * 10))
    ticks = iter([0, 0, 50, 100, 200])
    status = wait_for_run(
        "run-abc123",
        timeout_s=90,
        poll_s=1,
        cfg=CFG,
        sleep=lambda _: None,
        clock=lambda: next(ticks),
    )
    assert status == DagsterRunStatus.STARTED


def test_wait_for_run_stops_on_failure(fake):
    client = fake(
        FakeClient(statuses=[DagsterRunStatus.FAILURE, DagsterRunStatus.SUCCESS])
    )
    status = wait_for_run("run-abc123", cfg=CFG, sleep=lambda _: None, clock=lambda: 0)
    assert status == DagsterRunStatus.FAILURE
    assert client.polled == 1
