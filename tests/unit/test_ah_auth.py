"""Tests for AH member auth: raw calls, token persistence, auto-refresh."""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path

import pytest

from bonuschef.utils import ah_auth
from bonuschef.utils.ah_auth import (
    AUTH_BASE,
    EXPIRY_MARGIN_S,
    GRAPHQL_URL,
    MAX_ACCESS_TOKEN_AGE_S,
    AHAuthError,
    AHTokenManager,
    TokenBundle,
    TokenStore,
    default_token_file,
    exchange_code,
    graphql,
    refresh_access_token,
    refresh_tokens,
)
from tests.conftest import FakeResponse

NOW = 1_800_000_000.0


# ---------------------------------------------------------------------------
# Raw HTTP helpers
# ---------------------------------------------------------------------------


class TestExchangeCode:
    def test_posts_code_and_returns_body(self, http_post):
        http_post.queue(FakeResponse(200, {"access_token": "a", "refresh_token": "r"}))
        body = exchange_code("the-code", client_id="appie")
        assert body["refresh_token"] == "r"
        url, kwargs = http_post.last
        assert url == f"{AUTH_BASE}/token"
        assert kwargs["json"] == {"clientId": "appie", "code": "the-code"}
        assert kwargs["headers"]["x-application"] == "AHWEBSHOP"

    def test_failure_raises_with_status(self, http_post):
        http_post.queue(FakeResponse(400, text="bad code"))
        with pytest.raises(AHAuthError, match="HTTP 400") as exc:
            exchange_code("x")
        assert exc.value.status == 400


class TestRefreshTokens:
    def test_success_returns_full_body(self, http_post):
        http_post.queue(
            FakeResponse(
                200, {"access_token": "a", "refresh_token": "r2", "expires_in": 5}
            )
        )
        body = refresh_tokens("r1")
        assert body["refresh_token"] == "r2"
        assert http_post.last[1]["json"] == {"clientId": "appie", "refreshToken": "r1"}

    def test_refresh_access_token_returns_only_access(self, http_post):
        http_post.queue(FakeResponse(200, {"access_token": "a"}))
        assert refresh_access_token("r1") == "a"

    def test_http_error_mentions_login(self, http_post):
        http_post.queue(FakeResponse(401, text='{"reason":"INVALID_TOKEN"}'))
        with pytest.raises(AHAuthError, match="ah_login") as exc:
            refresh_tokens("dead")
        assert exc.value.status == 401

    def test_missing_access_token_raises(self, http_post):
        http_post.queue(FakeResponse(200, {"refresh_token": "r"}))
        with pytest.raises(AHAuthError, match="no access_token"):
            refresh_tokens("r")


class TestGraphql:
    def test_returns_data_block_with_bearer(self, http_post):
        http_post.queue(FakeResponse(200, {"data": {"bargainItems": []}}))
        data = graphql("tok", "query", {"storeId": "1"})
        assert data == {"bargainItems": []}
        url, kwargs = http_post.last
        assert url == GRAPHQL_URL
        assert kwargs["headers"]["Authorization"] == "Bearer tok"
        assert kwargs["json"] == {"query": "query", "variables": {"storeId": "1"}}

    def test_http_error_carries_status(self, http_post):
        http_post.queue(FakeResponse(401, text="nope"))
        with pytest.raises(AHAuthError) as exc:
            graphql("tok", "q", {})
        assert exc.value.status == 401

    def test_graphql_level_errors_raise(self, http_post):
        http_post.queue(FakeResponse(200, {"errors": [{"message": "redacted"}]}))
        with pytest.raises(AHAuthError, match="GraphQL errors") as exc:
            graphql("tok", "q", {})
        assert exc.value.status is None

    def test_missing_data_is_empty_dict(self, http_post):
        http_post.queue(FakeResponse(200, {}))
        assert graphql("tok", "q", {}) == {}


# ---------------------------------------------------------------------------
# Token bundle / file / default path
# ---------------------------------------------------------------------------


class TestTokenBundle:
    def test_is_fresh_respects_margin(self):
        bundle = TokenBundle("a", "r", access_expires_at=NOW + 1000, refreshed_at=NOW)
        assert bundle.is_fresh(NOW)
        assert not bundle.is_fresh(NOW + 1000 - EXPIRY_MARGIN_S)
        assert not bundle.is_fresh(NOW + 5000)


class TestDefaultTokenFile:
    def test_env_override_wins(self, monkeypatch, tmp_path):
        monkeypatch.setenv("AH_TOKEN_FILE", str(tmp_path / "custom.json"))
        monkeypatch.setenv("DAGSTER_HOME", str(tmp_path / "dh"))
        assert default_token_file() == tmp_path / "custom.json"

    def test_dagster_home_when_set(self, monkeypatch, tmp_path):
        monkeypatch.delenv("AH_TOKEN_FILE")
        monkeypatch.setenv("DAGSTER_HOME", str(tmp_path / "dh"))
        assert default_token_file() == tmp_path / "dh" / "ah_tokens.json"

    def test_home_fallback(self, monkeypatch):
        monkeypatch.delenv("AH_TOKEN_FILE")
        monkeypatch.delenv("DAGSTER_HOME", raising=False)
        assert default_token_file() == Path.home() / ".bonuschef" / "ah_tokens.json"


class TestTokenStore:
    def test_round_trip_and_private_permissions(self, tmp_path):
        store = TokenStore(tmp_path / "nested" / "tokens.json")
        bundle = TokenBundle("a", "r", NOW + 10, NOW)
        store.save(bundle)
        assert store.load() == bundle
        mode = stat.S_IMODE(os.stat(store.path).st_mode)
        assert mode == 0o600
        assert not list((tmp_path / "nested").glob(".ah_tokens-*")), "temp file left"

    def test_missing_file_is_none(self, tmp_path):
        assert TokenStore(tmp_path / "missing.json").load() is None

    @pytest.mark.parametrize("content", ["not json", "{}", '{"access_token": 1}'])
    def test_corrupt_file_is_none(self, tmp_path, content):
        path = tmp_path / "tokens.json"
        path.write_text(content)
        assert TokenStore(path).load() is None

    def test_legacy_file_without_refreshed_at(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text(
            json.dumps(
                {"access_token": "a", "refresh_token": "r", "access_expires_at": 5}
            )
        )
        loaded = TokenStore(path).load()
        assert loaded is not None
        assert loaded.refreshed_at == 0


# ---------------------------------------------------------------------------
# Token manager (auto refresh)
# ---------------------------------------------------------------------------


class FakeRefresher:
    """Scripted refresh endpoint: maps refresh token -> response or error."""

    def __init__(self, **outcomes):
        self.outcomes = outcomes
        self.calls: list[str] = []

    def __call__(self, refresh_token: str, client_id: str):
        self.calls.append(refresh_token)
        outcome = self.outcomes.get(refresh_token)
        if outcome is None:
            raise AHAuthError(f"rejected {refresh_token}", status=401)
        return dict(outcome)


def _manager(tmp_path, refresher, bootstrap="", now=NOW):
    return AHTokenManager(
        TokenStore(tmp_path / "tokens.json"),
        bootstrap_refresh_token=bootstrap,
        refresh=refresher,
        now=lambda: now,
    )


class TestAHTokenManager:
    def test_uses_cached_access_token_without_refreshing(self, tmp_path):
        refresher = FakeRefresher()
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("cached", "r", NOW + 3600, NOW))
        assert mgr.get_access_token() == "cached"
        assert refresher.calls == []

    def test_refreshes_when_expired_and_persists(self, tmp_path):
        refresher = FakeRefresher(r1={"access_token": "new", "expires_in": 604800})
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("old", "r1", NOW - 1, NOW - 10))
        assert mgr.get_access_token() == "new"
        saved = mgr.store.load()
        assert saved is not None
        assert saved.access_token == "new"
        assert saved.refresh_token == "r1", "no rotation → keep the token we used"
        # AH says 7 days, we cap at a day so the refresh token stays in use.
        assert saved.access_expires_at == NOW + MAX_ACCESS_TOKEN_AGE_S
        assert saved.refreshed_at == NOW

    def test_short_expires_in_is_kept(self, tmp_path):
        refresher = FakeRefresher(r1={"access_token": "new", "expires_in": 120})
        mgr = _manager(tmp_path, refresher, bootstrap="r1")
        mgr.get_access_token()
        assert mgr.store.load().access_expires_at == NOW + 120

    def test_rotated_refresh_token_is_persisted(self, tmp_path):
        refresher = FakeRefresher(
            r1={"access_token": "new", "refresh_token": "r2", "expires_in": 100}
        )
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("old", "r1", NOW - 1, NOW - 10))
        mgr.get_access_token()
        assert mgr.store.load().refresh_token == "r2"

    def test_bootstrap_used_when_no_file(self, tmp_path):
        refresher = FakeRefresher(env={"access_token": "a", "expires_in": 100})
        mgr = _manager(tmp_path, refresher, bootstrap="env")
        assert mgr.get_access_token() == "a"
        assert refresher.calls == ["env"]
        assert mgr.store.load().refresh_token == "env"

    def test_falls_back_to_bootstrap_when_stored_token_dead(self, tmp_path):
        refresher = FakeRefresher(fresh={"access_token": "a", "expires_in": 100})
        mgr = _manager(tmp_path, refresher, bootstrap="fresh")
        mgr.store.save(TokenBundle("old", "dead", NOW - 1, NOW - 10))
        assert mgr.get_access_token() == "a"
        assert refresher.calls == ["dead", "fresh"]
        assert mgr.store.load().refresh_token == "fresh"

    def test_picks_up_token_rotated_by_another_process(self, tmp_path):
        """Loaded token A, but a concurrent run already rotated the file to B."""
        refresher = FakeRefresher(B={"access_token": "a", "expires_in": 100})
        mgr = _manager(tmp_path, refresher, bootstrap="env")
        stale = TokenBundle("old", "A", NOW - 1, NOW - 10)
        mgr.store.save(TokenBundle("other", "B", NOW - 1, NOW - 5))
        assert mgr._refresh_and_store(stale).bundle.access_token == "a"
        assert refresher.calls == ["A", "B"], "on-disk token tried before env"

    def test_all_tokens_rejected_raises_login_hint(self, tmp_path):
        refresher = FakeRefresher()
        mgr = _manager(tmp_path, refresher, bootstrap="env")
        mgr.store.save(TokenBundle("old", "dead", NOW - 1, NOW - 10))
        with pytest.raises(AHAuthError, match="ah_login") as exc:
            mgr.get_access_token()
        assert exc.value.status == 401
        assert refresher.calls == ["dead", "env"]
        # Both halves of the instruction. This is read by someone on an
        # unattended host who has just been told their credentials are gone,
        # and "re-run the login" is half an answer if they cannot see what it
        # will overwrite - the path is configurable, so it cannot be inferred.
        assert str(mgr.store.path) in str(exc.value), (
            "the message says how to recover but not where the credentials are"
        )

    def test_no_tokens_anywhere_raises_clear_error(self, tmp_path):
        mgr = _manager(tmp_path, FakeRefresher())
        with pytest.raises(AHAuthError, match="AH_REFRESH_TOKEN"):
            mgr.get_access_token()

    def test_force_refresh_bypasses_cache(self, tmp_path):
        refresher = FakeRefresher(r={"access_token": "forced", "expires_in": 100})
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("cached", "r", NOW + 3600, NOW))
        assert mgr.get_access_token(force_refresh=True) == "forced"

    def test_adopt_requires_a_refresh_token(self, tmp_path):
        mgr = _manager(tmp_path, FakeRefresher())
        with pytest.raises(AHAuthError, match="no refresh token"):
            mgr.adopt({"access_token": "a"})

    def test_adopt_defaults_expiry_when_missing(self, tmp_path):
        mgr = _manager(tmp_path, FakeRefresher())
        bundle = mgr.adopt({"access_token": "a", "refresh_token": "r"})
        assert bundle.access_expires_at == NOW + MAX_ACCESS_TOKEN_AGE_S


class TestManagerGraphql:
    def _mgr(self, tmp_path, monkeypatch, responses):
        calls: list[str] = []

        def fake_graphql(token, query, variables):
            calls.append(token)
            outcome = responses.pop(0)
            if isinstance(outcome, Exception):
                raise outcome
            return outcome

        monkeypatch.setattr(ah_auth, "graphql", fake_graphql)
        refresher = FakeRefresher(r={"access_token": "fresh", "expires_in": 100})
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("cached", "r", NOW + 3600, NOW))
        return mgr, calls, refresher

    def test_happy_path_uses_cached_token(self, tmp_path, monkeypatch):
        mgr, calls, refresher = self._mgr(tmp_path, monkeypatch, [{"ok": 1}])
        assert mgr.graphql("q", {}) == {"ok": 1}
        assert calls == ["cached"]
        assert refresher.calls == []

    def test_retries_once_with_forced_refresh_on_401(self, tmp_path, monkeypatch):
        mgr, calls, refresher = self._mgr(
            tmp_path, monkeypatch, [AHAuthError("expired", status=401), {"ok": 1}]
        )
        assert mgr.graphql("q", {}) == {"ok": 1}
        assert calls == ["cached", "fresh"]
        assert refresher.calls == ["r"]

    def test_non_auth_error_is_not_retried(self, tmp_path, monkeypatch):
        mgr, calls, _ = self._mgr(
            tmp_path, monkeypatch, [AHAuthError("GraphQL errors: redacted")]
        )
        with pytest.raises(AHAuthError, match="redacted"):
            mgr.graphql("q", {})
        assert calls == ["cached"]

    def test_second_401_propagates(self, tmp_path, monkeypatch):
        mgr, calls, _ = self._mgr(
            tmp_path,
            monkeypatch,
            [AHAuthError("expired", status=401), AHAuthError("still", status=401)],
        )
        with pytest.raises(AHAuthError, match="still"):
            mgr.graphql("q", {})
        assert calls == ["cached", "fresh"]


class TestCredentialAge:
    """The refresh credential's age is the evidence that settles whether AH's
    expiry is sliding (extends on use) or absolute (a fixed maximum life).

    It must be measured from when a token *value* first appeared. ``refreshed_at``
    is stamped on every refresh, so measuring from it would report one heartbeat
    interval forever and prove nothing.
    """

    def test_issue_time_is_carried_forward_when_the_credential_is_unchanged(
        self, tmp_path
    ):
        refresher = FakeRefresher(A={"access_token": "a2", "expires_in": 100})
        mgr = _manager(tmp_path, refresher)
        # Credential A has been in service for 60 days already.
        issued = NOW - 60 * 86_400
        mgr.store.save(TokenBundle("old", "A", NOW - 1, NOW - 43_200, issued))

        outcome = mgr.refresh_now()

        assert outcome.rotated is False
        assert outcome.bundle.refresh_token_issued_at == issued, (
            "an unchanged credential must keep its original issue time"
        )
        assert outcome.credential_age_s == 60 * 86_400
        assert mgr.store.load().refresh_token_issued_at == issued

    def test_rotation_restarts_the_clock(self, tmp_path):
        refresher = FakeRefresher(
            A={"access_token": "a2", "refresh_token": "B", "expires_in": 100}
        )
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("old", "A", NOW - 1, NOW - 10, NOW - 5 * 86_400))

        outcome = mgr.refresh_now()

        assert outcome.rotated is True
        assert outcome.credential_age_s == 5 * 86_400, "age is of the credential used"
        assert outcome.bundle.refresh_token == "B"
        assert outcome.bundle.refresh_token_issued_at == NOW

    def test_unknown_issue_time_stays_unknown(self, tmp_path):
        """A file written before the field existed cannot say how old it is, and
        guessing would understate the age."""
        refresher = FakeRefresher(A={"access_token": "a2", "expires_in": 100})
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("old", "A", NOW - 1, NOW - 10))  # issued_at = 0.0

        outcome = mgr.refresh_now()

        assert outcome.credential_age_s is None
        assert outcome.bundle.refresh_token_issued_at == 0.0

    def test_legacy_file_without_issue_time_still_loads(self, tmp_path):
        path = tmp_path / "tokens.json"
        path.write_text(
            json.dumps(
                {
                    "access_token": "a",
                    "refresh_token": "r",
                    "access_expires_at": NOW + 100,
                    "refreshed_at": NOW,
                }
            )
        )
        bundle = TokenStore(path).load()
        assert bundle is not None
        assert bundle.refresh_token_issued_at == 0.0
        assert bundle.credential_age_s(NOW) is None

    def test_env_fallback_is_not_reported_as_rotation(self, tmp_path):
        """The stored credential is dead and .env's is used. That is a fallback,
        not AH rotating — conflating them would poison the evidence."""
        refresher = FakeRefresher(env={"access_token": "a", "expires_in": 100})
        mgr = _manager(tmp_path, refresher, bootstrap="env")
        mgr.store.save(TokenBundle("old", "dead", NOW - 1, NOW - 10, NOW - 86_400))

        outcome = mgr.refresh_now()

        assert outcome.used_fallback is True
        assert outcome.rotated is False, "AH returned the same token we sent"
        assert outcome.credential_age_s is None, "a .env credential has no history"

    def test_refresh_now_always_calls_the_refresher(self, tmp_path):
        """Even with a perfectly fresh access token — refreshing the access token
        is not the point, exercising the refresh credential is."""
        refresher = FakeRefresher(A={"access_token": "a2", "expires_in": 10_000})
        mgr = _manager(tmp_path, refresher)
        mgr.store.save(TokenBundle("still-good", "A", NOW + 10_000, NOW, NOW))

        mgr.refresh_now()

        assert refresher.calls == ["A"]


class TestTokenStoreDurability:
    def test_a_failed_write_leaves_the_original_intact(self, tmp_path, monkeypatch):
        store = TokenStore(tmp_path / "tokens.json")
        store.save(TokenBundle("good", "A", NOW + 100, NOW, NOW))
        before = store.path.read_bytes()

        def boom(*args, **kwargs):
            raise OSError("disk full")

        monkeypatch.setattr(json, "dump", boom)
        with pytest.raises(OSError):
            store.save(TokenBundle("new", "B", NOW + 200, NOW, NOW))

        assert store.path.read_bytes() == before, "partial write clobbered the token"
        assert list(tmp_path.glob(".ah_tokens-*")) == [], "temp file left behind"

    def test_a_corrupt_file_warns_rather_than_failing_silently(self, tmp_path, caplog):
        path = tmp_path / "tokens.json"
        path.write_text("{not json")
        with caplog.at_level("WARNING"):
            assert TokenStore(path).load() is None
        assert "could not be parsed" in caplog.text
        assert "ah_login" in caplog.text


class TestARejectedCredentialIsNotAnEmptyResult:
    """An auth failure must break the pipeline, not produce zero rows.

    The clearance feed is an append-only snapshot: a run that records nothing
    is indistinguishable from a day with no markdowns. If an expired
    credential yielded an empty snapshot, the portal would report "geen
    laatste kans koopjes" - a plausible answer - and the only signal that
    authentication had lapsed would be its continued absence.

    This is the half of the requirement that was unverified. The failure path
    was correct; nothing held it that way.
    """

    def test_an_auth_failure_propagates_out_of_the_feed(self, tmp_path, monkeypatch):
        from bonuschef.config import AHMarkdownConfig
        from bonuschef.dags.defs.assets.dlt import ah_markdowns

        class _Dead:
            def graphql(self, *_a, **_k):
                raise AHAuthError(
                    "All known AH refresh tokens were rejected", status=401
                )

        monkeypatch.setattr(ah_markdowns, "token_manager", lambda cfg: _Dead())
        cfg = AHMarkdownConfig(store_id=1876, token_file=tmp_path / "t.json")

        with pytest.raises(AHAuthError):
            list(
                ah_markdowns._iter_markdowns(cfg, "2026-01-01T00:00:00Z", cfg.store_id)
            )

    def test_the_feed_does_not_swallow_it_into_zero_rows(self, tmp_path, monkeypatch):
        """The distinction that matters: raising, versus returning nothing."""
        from bonuschef.config import AHMarkdownConfig
        from bonuschef.dags.defs.assets.dlt import ah_markdowns

        class _Dead:
            def graphql(self, *_a, **_k):
                raise AHAuthError("rejected", status=401)

        monkeypatch.setattr(ah_markdowns, "token_manager", lambda cfg: _Dead())
        cfg = AHMarkdownConfig(store_id=1876, token_file=tmp_path / "t.json")

        rows = None
        try:
            rows = list(
                ah_markdowns._iter_markdowns(cfg, "2026-01-01T00:00:00Z", cfg.store_id)
            )
        except AHAuthError:
            pass
        assert rows is None, (
            "an expired credential produced an empty snapshot, which reads as "
            "'no clearance items today' rather than as a failure"
        )
