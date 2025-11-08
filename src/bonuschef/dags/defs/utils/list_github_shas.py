"""Helper: get SHAs for weekly uploads, preferring Monday, else Tue/Wed."""

import requests
from datetime import datetime, timezone


def get_commits_by_message(
    owner: str,
    repo: str,
    message_filter: str,
    branch: str = "main",
    token: str | None = None,
    max_pages: int = 2,
    fallback_days: int = 3,
):
    """
    Retrieve commits from a GitHub repo whose commit message matches a given string,
    grouped per ISO week, preferring Monday; if no Monday, take the next available
    weekday up to `fallback_days` after Monday (Tue/Wed/etc).

    Args:
        owner (str): GitHub username or org.
        repo (str): Repository name.
        message_filter (str): Commit message to match (exact match, case-sensitive).
        branch (str, optional): Branch name (default: 'main').
        token (str, optional): GitHub token to avoid rate limits.
        max_pages (int, optional): Number of pages to fetch (100 commits per page).
        fallback_days (int, optional): How far past Monday to look (default: 3 → up to Thursday).

    Returns:
        list[dict]: One selection per ISO week where a matching commit was found.
                    Each item: {sha, message, date, author, weekday, iso_year, iso_week}
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    allowed = list(range(0, min(6, 0 + fallback_days) + 1))
    priority = {wd: i for i, wd in enumerate(allowed)}

    per_week_best: dict[tuple[int, int], dict] = {}

    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {"sha": branch, "per_page": 100, "page": page}
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()

        commits = resp.json()
        if not commits:
            break

        for c in commits:
            message = c["commit"]["message"]
            if message.strip() != message_filter:
                continue

            date_str = c["commit"]["author"]["date"]
            date_obj = datetime.fromisoformat(
                date_str.replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            wd = date_obj.weekday()
            if wd not in allowed:
                continue

            iso_year, iso_week, _ = date_obj.isocalendar()
            key = (iso_year, iso_week)

            candidate = {
                "sha": c["sha"],
                "message": message,
                "date": date_str,
                "author": c["commit"]["author"]["name"],
                "weekday": date_obj.strftime("%A"),
                "iso_year": iso_year,
                "iso_week": iso_week,
                "_weekday_idx": wd,
                "_ts": date_obj.timestamp(),
            }

            existing = per_week_best.get(key)
            if existing is None:
                per_week_best[key] = candidate
            else:
                cur_pri = priority[existing["_weekday_idx"]]
                new_pri = priority[wd]
                if (new_pri < cur_pri) or (
                    new_pri == cur_pri and candidate["_ts"] > existing["_ts"]
                ):
                    per_week_best[key] = candidate

    results = []
    for key in sorted(per_week_best.keys()):
        item = per_week_best[key].copy()
        item.pop("_weekday_idx", None)
        item.pop("_ts", None)
        results.append(item)

    return results
