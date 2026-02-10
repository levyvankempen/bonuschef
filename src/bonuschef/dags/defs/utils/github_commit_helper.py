"""Helper file to retrieve GitHub commit info."""

from datetime import datetime

from .list_github_shas import get_commits_by_message


def commits_since_date(
    owner: str,
    repo: str,
    message_filter: str,
    since_iso_utc: str,
    branch: str = "main",
    token: str | None = None,
    max_pages: int = 2,
) -> list[dict]:
    """Return commits (with message filters) on/after since_iso_utc."""
    since_dt = datetime.fromisoformat(since_iso_utc.replace("Z", "+00:00"))
    commits = get_commits_by_message(
        owner=owner,
        repo=repo,
        message_filter=message_filter,
        branch=branch,
        token=token,
        max_pages=max_pages,
    )
    return [
        c
        for c in commits
        if datetime.fromisoformat(c["date"].replace("Z", "+00:00")) >= since_dt
    ]
