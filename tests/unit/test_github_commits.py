"""Tests for weekly GitHub commit selection (Monday preferred, fallback days)."""

import pytest

from bonuschef.dags.defs.utils.github_commit_helper import commits_since_date
from bonuschef.dags.defs.utils.list_github_shas import get_commits_by_message
from tests.conftest import FakeResponse

MSG = "Update supermarkets.json"

# 2025-01-06 is a Monday.
MON = "2025-01-06T08:00:00Z"
MON_LATER = "2025-01-06T18:00:00Z"
TUE = "2025-01-07T08:00:00Z"
FRI = "2025-01-10T08:00:00Z"
NEXT_TUE = "2025-01-14T08:00:00Z"


def _commit(sha, date, message=MSG):
    return {
        "sha": sha,
        "commit": {"message": message, "author": {"date": date, "name": "bot"}},
    }


def _call(http_get, *pages, **kwargs):
    for page in pages:
        http_get.queue(FakeResponse(200, page))
    return get_commits_by_message("o", "r", MSG, max_pages=len(pages), **kwargs)


class TestGetCommitsByMessage:
    def test_prefers_monday_over_tuesday_in_same_week(self, http_get):
        result = _call(http_get, [_commit("tue", TUE), _commit("mon", MON)])
        assert [c["sha"] for c in result] == ["mon"]
        assert result[0]["weekday"] == "Monday"
        assert (result[0]["iso_year"], result[0]["iso_week"]) == (2025, 2)

    def test_falls_back_to_tuesday_when_no_monday(self, http_get):
        result = _call(http_get, [_commit("tue", TUE)])
        assert [c["sha"] for c in result] == ["tue"]

    def test_friday_outside_fallback_window_is_ignored(self, http_get):
        assert _call(http_get, [_commit("fri", FRI)]) == []

    def test_fallback_days_widens_window(self, http_get):
        result = _call(http_get, [_commit("fri", FRI)], fallback_days=5)
        assert [c["sha"] for c in result] == ["fri"]

    def test_same_weekday_keeps_latest_commit(self, http_get):
        result = _call(http_get, [_commit("early", MON), _commit("late", MON_LATER)])
        assert [c["sha"] for c in result] == ["late"]

    def test_non_matching_message_is_skipped(self, http_get):
        result = _call(
            http_get, [_commit("x", MON, message="other"), _commit("y", TUE)]
        )
        assert [c["sha"] for c in result] == ["y"]

    def test_one_result_per_week_sorted(self, http_get):
        result = _call(http_get, [_commit("w3", NEXT_TUE), _commit("w2", MON)])
        assert [c["sha"] for c in result] == ["w2", "w3"]

    def test_stops_paging_on_empty_page(self, http_get):
        http_get.queue(FakeResponse(200, [_commit("mon", MON)]), FakeResponse(200, []))
        get_commits_by_message("o", "r", MSG, max_pages=5)
        assert len(http_get.calls) == 2
        assert http_get.calls[0][1]["params"] == {
            "sha": "main",
            "per_page": 100,
            "page": 1,
        }

    def test_token_and_branch_are_forwarded(self, http_get):
        http_get.queue(FakeResponse(200, []))
        get_commits_by_message("o", "r", MSG, branch="dev", token="t", max_pages=1)
        url, kwargs = http_get.last
        assert url == "https://api.github.com/repos/o/r/commits"
        assert kwargs["headers"]["Authorization"] == "Bearer t"
        assert kwargs["params"]["sha"] == "dev"

    def test_internal_fields_are_stripped(self, http_get):
        (item,) = _call(http_get, [_commit("mon", MON)])
        assert "_ts" not in item and "_weekday_idx" not in item


class TestCommitsSinceDate:
    @pytest.fixture
    def commits(self, monkeypatch):
        monkeypatch.setattr(
            "bonuschef.dags.defs.utils.github_commit_helper.get_commits_by_message",
            lambda **kw: [
                {"sha": "old", "date": "2024-12-30T08:00:00Z"},
                {"sha": "new", "date": MON},
            ],
        )

    def test_filters_on_or_after_since(self, commits):
        result = commits_since_date("o", "r", MSG, since_iso_utc="2025-01-01T00:00:00Z")
        assert [c["sha"] for c in result] == ["new"]

    def test_since_is_inclusive(self, commits):
        result = commits_since_date("o", "r", MSG, since_iso_utc=MON)
        assert [c["sha"] for c in result] == ["new"]
