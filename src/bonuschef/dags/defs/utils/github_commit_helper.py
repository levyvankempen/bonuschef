"""Helper file to retrieve GitHub commit info."""

from datetime import datetime
from typing import List, Dict
from ..assets.dlt.github_backfill.list_github_shas import get_commits_by_message


def commits_since_date(
    owner: str,
    repo: str,
    message_filter: str,
    since_iso_utc: str,  # e.g. "2025-09-01T00:00:00Z"
    branch: str = "main",
    token: str | None = None,
    max_pages: int = 2,
) -> List[Dict]:
    """Return commits (with Monday/message filters) on/after since_iso_utc."""
    since_dt = datetime.fromisoformat(since_iso_utc.replace("Z", "+00:00"))
    commits = get_commits_by_message(
        owner=owner,
        repo=repo,
        message_filter=message_filter,
        branch=branch,
        token=token,
        max_pages=max_pages,
    )
    out: List[Dict] = []
    for c in commits:
        c_dt = datetime.fromisoformat(c["date"].replace("Z", "+00:00"))
        if c_dt >= since_dt:
            out.append(c)
    return out
