"""Helper file to get the SHA of all files uploaded on Monday."""

import os
import requests
from datetime import datetime


def get_commits_by_message(
    owner: str,
    repo: str,
    message_filter: str,
    branch: str = "main",
    token: str | None = None,
    max_pages: int = 2,
):
    """
    Retrieve commits from a GitHub repo whose commit message matches a given string
    and were made on a Monday.

    Args:
        owner (str): GitHub username or org.
        repo (str): Repository name.
        message_filter (str): Commit message to match (exact match, case-sensitive).
        branch (str, optional): Branch name (default: 'main').
        token (str, optional): GitHub token to avoid rate limits.
        max_pages (int, optional): Number of pages to fetch (100 commits per page).

    Returns:
        list[dict]: List of {sha, message, date, author, weekday} dicts for commits made on Mondays.
    """
    headers = {"Accept": "application/vnd.github+json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    matches = []

    for page in range(1, max_pages + 1):
        url = f"https://api.github.com/repos/{owner}/{repo}/commits"
        params = {"sha": branch, "per_page": 100, "page": page}
        response = requests.get(url, headers=headers, params=params)
        response.raise_for_status()

        commits = response.json()
        if not commits:
            break

        for c in commits:
            message = c["commit"]["message"]
            date_str = c["commit"]["author"]["date"]
            date_obj = datetime.fromisoformat(date_str.replace("Z", "+00:00"))

            # weekday() -> Monday = 0, Sunday = 6
            if message.strip() == message_filter and date_obj.weekday() == 0:
                matches.append(
                    {
                        "sha": c["sha"],
                        "message": message,
                        "date": date_str,
                        "author": c["commit"]["author"]["name"],
                        "weekday": date_obj.strftime("%A"),
                    }
                )

    return matches


if __name__ == "__main__":
    commits = get_commits_by_message(
        owner="supermarkt",
        repo="checkjebon",
        token=os.environ.get("GITHUB_TOKEN"),
        message_filter="Update supermarkets.json",
    )

    if not commits:
        print("No matching commits found on a Monday.")
    else:
        for c in commits:
            print(f"{c['date']} | {c['sha']} | {c['weekday']} | {c['message']}")
