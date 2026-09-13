"""The heartbeat that keeps the AH refresh credential alive between scrapes.

The credential expired twice from disuse because the clearance scrape was the
only thing that ever refreshed it. These tests pin the two properties that make
the heartbeat worth having: it exercises the credential unconditionally, and it
fails the run when the credential is dead so the alert sensor can see it.
"""

from __future__ import annotations

import pytest
from dagster import DagsterInstance, build_op_context

from bonuschef.dags.defs import jobs as jobs_module
from bonuschef.dags.defs.jobs import refresh_ah_credential, token_heartbeat_job
from bonuschef.utils.ah_auth import AHAuthError, RefreshOutcome, TokenBundle

NOW = 1_800_000_000.0


class FakeManager:
    def __init__(
        self,
        outcome: RefreshOutcome | None = None,
        error: Exception | None = None,
    ) -> None:
        self._outcome = outcome
        self._error = error
        self.calls = 0

    def refresh_now(self) -> RefreshOutcome:
        self.calls += 1
        if self._error is not None:
            raise self._error
        assert self._outcome is not None, "FakeManager needs an outcome or an error"
        return self._outcome


def _outcome(rotated=False, age_s=None, fallback=False) -> RefreshOutcome:
    return RefreshOutcome(
        bundle=TokenBundle("a", "r", NOW + 100, NOW, NOW),
        rotated=rotated,
        credential_age_s=age_s,
        used_fallback=fallback,
    )


@pytest.fixture
def instance():
    with DagsterInstance.ephemeral() as inst:
        yield inst


def _run(monkeypatch, instance, manager, raise_on_error=True):
    monkeypatch.setattr(jobs_module, "manager_from_env", lambda: manager)
    return token_heartbeat_job.execute_in_process(
        instance=instance, raise_on_error=raise_on_error
    )


def test_it_exercises_the_credential(monkeypatch, instance):
    manager = FakeManager(_outcome())
    result = _run(monkeypatch, instance, manager)
    assert result.success
    assert manager.calls == 1


def test_it_records_rotation_and_age_as_an_observation(monkeypatch, instance):
    """Indexed by asset key, so the series can be read back later — this is the
    evidence for whether AH's refresh expiry is sliding or absolute."""
    manager = FakeManager(_outcome(rotated=True, age_s=60 * 86_400))
    result = _run(monkeypatch, instance, manager)

    (event,) = result.get_asset_observation_events()
    observation = event.event_specific_data.asset_observation
    assert observation.asset_key.to_user_string() == "ah_refresh_credential"
    metadata = observation.metadata
    assert metadata["rotated"].value is True
    assert metadata["credential_age_days"].value == pytest.approx(60.0)
    assert metadata["used_env_fallback"].value is False


def test_unknown_age_is_reported_as_unknown_not_zero(monkeypatch, instance):
    """A token file predating the issue-time field cannot say how old it is.
    Reporting 0 would look like a freshly rotated credential."""
    manager = FakeManager(_outcome(age_s=None))
    result = _run(monkeypatch, instance, manager)

    (event,) = result.get_asset_observation_events()
    metadata = event.event_specific_data.asset_observation.metadata
    assert metadata["credential_age_days"].value is None


def test_a_dead_credential_fails_the_op(monkeypatch):
    """It must raise, not log-and-continue: a successful run emits no
    RUN_FAILURE, so the alert sensor would never fire and the credential would
    die silently — exactly the original incident.

    Asserted on the op rather than through the job, because the job's retry
    policy is real: driving a failure through it would sleep for two minutes.
    """
    manager = FakeManager(
        error=AHAuthError("All known AH refresh tokens were rejected")
    )
    monkeypatch.setattr(jobs_module, "manager_from_env", lambda: manager)
    with pytest.raises(AHAuthError, match="rejected"):
        refresh_ah_credential(build_op_context())


def test_it_retries_before_giving_up():
    """Required by the scheduling capability: every scheduled pipeline retries,
    so a transient AH 5xx does not skip a cycle. Op-level, so a run that never
    recovers still emits exactly one RUN_FAILURE and so exactly one alert."""
    policy = token_heartbeat_job.op_retry_policy
    assert policy is not None
    assert policy.max_retries >= 1
