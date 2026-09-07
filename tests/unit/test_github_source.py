"""Tests for the GitHub product snapshot dlt source."""

from datetime import datetime, timezone

import pytest
import requests

from bonuschef.config import GitHubConfig
from bonuschef.dags.defs.assets.dlt.github import (
    _get_commit_date,
    _snapshot_str,
    github_source,
)
from tests.conftest import FakeResponse

CFG = GitHubConfig(
    owner="supermarkt",
    repo="checkjebon",
    path="data/supermarkets.json",
    message_filter="Update supermarkets.json",
    start_date="2025-01-01T00:00:00Z",
    branch="main",
    token="ghp_secret",
    max_pages=1,
)


class TestSnapshotStr:
    def test_none_is_now_in_utc_z_format(self):
        value = _snapshot_str(None)
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
        assert abs((datetime.utcnow() - parsed).total_seconds()) < 60

    def test_datetime_is_isoformat(self):
        dt = datetime(2025, 1, 6, 8, 0, tzinfo=timezone.utc)
        assert _snapshot_str(dt) == "2025-01-06T08:00:00+00:00"

    def test_string_passthrough(self):
        assert _snapshot_str("2025-01-06T08:00:00Z") == "2025-01-06T08:00:00Z"


class TestGetCommitDate:
    def test_reads_author_date_with_bearer(self, http_get):
        http_get.queue(
            FakeResponse(200, {"commit": {"author": {"date": "2025-01-06T08:00:00Z"}}})
        )
        assert _get_commit_date(CFG, "abc") == "2025-01-06T08:00:00Z"
        url, kwargs = http_get.last
        assert url.endswith("/repos/supermarkt/checkjebon/commits/abc")
        assert kwargs["headers"]["Authorization"] == "Bearer ghp_secret"

    def test_http_error_propagates(self, http_get):
        http_get.queue(FakeResponse(404, {}))
        with pytest.raises(requests.HTTPError):
            _get_commit_date(CFG, "abc")


class TestGithubSource:
    PAYLOAD = [
        {"n": "jumbo", "d": [{"l": "x", "p": 1}]},
        {"n": "ah", "d": [{"l": "melk", "p": 1.09}, {"l": "kaas", "p": 4.5}]},
    ]

    def test_yields_ah_items_tagged_with_snapshot(self, http_get):
        http_get.queue(FakeResponse(200, self.PAYLOAD))
        rows = list(
            github_source(
                owner="o",
                repo="r",
                path="data.json",
                commit_sha="sha1",
                snapshot_at="2025-01-06T08:00:00Z",
            )
        )
        assert [r["l"] for r in rows] == ["melk", "kaas"]
        assert all(r["snapshot_sha"] == "sha1" for r in rows)
        assert all(r["snapshot_at"] == "2025-01-06T08:00:00Z" for r in rows)
        url, kwargs = http_get.last
        assert url == "https://raw.githubusercontent.com/o/r/sha1/data.json"
        assert "Authorization" not in kwargs["headers"]

    def test_branch_used_when_no_sha_and_token_forwarded(self, http_get):
        http_get.queue(FakeResponse(200, self.PAYLOAD))
        rows = list(
            github_source(
                owner="o", repo="r", path="d.json", access_token="t", branch="dev"
            )
        )
        assert rows[0]["snapshot_sha"] == "latest"
        url, kwargs = http_get.last
        assert url == "https://raw.githubusercontent.com/o/r/dev/d.json"
        assert kwargs["headers"]["Authorization"] == "Bearer t"

    def test_no_ah_chain_yields_nothing(self, http_get):
        http_get.queue(FakeResponse(200, [{"n": "jumbo", "d": [{"l": "x"}]}]))
        assert list(github_source(owner="o", repo="r", path="d.json")) == []
