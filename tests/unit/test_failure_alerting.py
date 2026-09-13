"""Run failures reach a phone.

The AH credential died and nobody noticed for two months. These tests pin the
properties that make the alert useful (it carries the reason, not just the step
name) and safe (it never fails a run, and never touches the network when
unconfigured).
"""

from __future__ import annotations

import pytest
from dagster import (
    DagsterInstance,
    build_run_status_sensor_context,
    job,
    op,
)

from bonuschef.dags.defs.sensors import run_failure_alert_sensor
from bonuschef.utils.ah_auth import AHAuthError
from tests.conftest import FakeResponse

TOPIC = "a-long-random-topic"


@op
def _dead_credential() -> None:
    raise AHAuthError(
        "All known AH refresh tokens were rejected — re-run "
        "`python -m bonuschef.utils.ah_login` to obtain a new token"
    )


@job(name="token_heartbeat")
def _failing_job() -> None:
    _dead_credential()


@op
def _fine() -> None:
    return None


@job(name="token_heartbeat_ok")
def _passing_job() -> None:
    _fine()


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as inst:
        yield inst


def _context(instance, result, event):
    return build_run_status_sensor_context(
        sensor_name="run_failure_alert_sensor",
        dagster_instance=instance,
        dagster_run=result.dagster_run,
        dagster_event=event,
    )


@pytest.fixture
def failed(instance):
    return _failing_job.execute_in_process(instance=instance, raise_on_error=False)


def test_it_posts_the_actionable_reason(monkeypatch, instance, failed, http_post):
    """`failure_event.message` only says which steps failed. The alert has to
    carry the exception text, or it tells you nothing you can act on."""
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    http_post.queue(FakeResponse(200, {}))

    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))

    url, kwargs = http_post.last
    assert url == f"https://ntfy.sh/{TOPIC}"
    body = kwargs["data"].decode()
    assert "token_heartbeat" in body
    assert "ah_login" in body, "the alert must name the recovery step"


def test_a_custom_server_is_honoured(monkeypatch, instance, failed, http_post):
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    monkeypatch.setenv("NTFY_SERVER", "https://ntfy.example.org/")
    http_post.queue(FakeResponse(200, {}))

    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))

    assert http_post.last[0] == f"https://ntfy.example.org/{TOPIC}"


def test_it_sends_a_timeout(monkeypatch, instance, failed, http_post):
    """The sensor evaluates in a daemon worker thread; a hanging POST would
    wedge it until the gRPC deadline trips."""
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    http_post.queue(FakeResponse(200, {}))

    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))

    assert http_post.last[1]["timeout"] > 0


def test_unconfigured_sends_nothing(instance, failed, http_post):
    """Alerting is opt-in. Unconfigured is a choice, not an error — and it is
    what keeps this suite off the network."""
    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))
    assert http_post.calls == []


def test_an_empty_topic_counts_as_unconfigured(
    monkeypatch, instance, failed, http_post
):
    """`.env.example` ships `NTFY_TOPIC=` empty, so a copied template must not
    post to a guessable public topic."""
    monkeypatch.setenv("NTFY_TOPIC", "   ")
    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))
    assert http_post.calls == []


def test_it_is_wired_as_a_failure_sensor(instance):
    """Success filtering lives in the daemon, not in the function — invoking it
    directly with a success event still posts. So the property worth asserting
    is that it is registered as a run-failure sensor, which is what makes the
    daemon feed it failures only."""
    from dagster import RunStatusSensorDefinition
    from dagster._core.definitions.sensor_definition import DefaultSensorStatus

    assert isinstance(run_failure_alert_sensor, RunStatusSensorDefinition)
    # And enabled on a fresh deployment, or an unattended host starts silent.
    assert run_failure_alert_sensor.default_status == DefaultSensorStatus.RUNNING


def test_a_delivery_failure_never_fails_the_sensor(
    monkeypatch, instance, failed, http_post
):
    """A raising sensor leaves the daemon cursor uncommitted, so the next tick
    reprocesses the same failure and notifies again. Catching is what makes
    'one notification per failure' actually true."""
    monkeypatch.setenv("NTFY_TOPIC", TOPIC)
    http_post.queue(OSError("ntfy unreachable"))

    run_failure_alert_sensor(_context(instance, failed, failed.get_run_failure_event()))

    assert http_post.calls, "it tried"
