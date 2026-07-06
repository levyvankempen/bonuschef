"""Configuration dataclasses with validation."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class GitHubConfig:
    """Configuration for GitHub API access."""

    owner: str
    repo: str
    path: str
    message_filter: str
    start_date: str
    branch: str
    token: str | None
    max_pages: int

    def __post_init__(self) -> None:
        for field in (
            "owner",
            "repo",
            "path",
            "message_filter",
            "start_date",
            "branch",
        ):
            if not getattr(self, field):
                raise ValueError(f"GITHUB_{field.upper()} is required")
        if self.max_pages < 1:
            raise ValueError("GITHUB_MAX_PAGES must be >= 1")

    @classmethod
    def from_env(cls) -> "GitHubConfig":
        max_pages_raw = os.getenv("GITHUB_MAX_PAGES", "")
        if not max_pages_raw.isdigit():
            raise ValueError(
                f"GITHUB_MAX_PAGES must be a positive integer, got: {max_pages_raw!r}"
            )
        return cls(
            owner=os.getenv("GITHUB_OWNER", ""),
            repo=os.getenv("GITHUB_REPO", ""),
            path=os.getenv("GITHUB_PATH", ""),
            message_filter=os.getenv("GITHUB_MESSAGE_FILTER", ""),
            start_date=os.getenv("GITHUB_START_DATE", ""),
            branch=os.getenv("GITHUB_BRANCH", "main"),
            token=os.getenv("GITHUB_TOKEN"),
            max_pages=int(max_pages_raw),
        )


@dataclass(frozen=True)
class AHMarkdownConfig:
    """Configuration for Albert Heijn store markdown ("laatste kans") access.

    The markdown/clearance feed is store-specific and requires a *member*
    token (the anonymous SupermarktConnector token is not authorised for it).
    A one-time browser login yields a refresh token (see ``utils/ah_login.py``);
    that refresh token is the only secret the pipeline needs at runtime.
    """

    store_id: int
    refresh_token: str
    client_id: str = "appie"

    def __post_init__(self) -> None:
        if self.store_id < 1:
            raise ValueError("AH_STORE_ID must be a positive integer")
        if not self.refresh_token:
            raise ValueError(
                "AH_REFRESH_TOKEN is required — run "
                "`python -m bonuschef.utils.ah_login` once to obtain it, "
                "then add it to your .env"
            )

    @classmethod
    def from_env(cls) -> "AHMarkdownConfig":
        store_raw = os.getenv("AH_STORE_ID", "1876")
        if not store_raw.isdigit():
            raise ValueError(
                f"AH_STORE_ID must be a positive integer, got: {store_raw!r}"
            )
        return cls(
            store_id=int(store_raw),
            refresh_token=os.getenv("AH_REFRESH_TOKEN", ""),
            client_id=os.getenv("AH_CLIENT_ID", "appie"),
        )


@dataclass(frozen=True)
class DatabaseConfig:
    """Configuration for PostgreSQL database connection."""

    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str = "prefer"

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("PG_HOST is required")
        if not self.database:
            raise ValueError("PG_DB is required")
        if not self.username:
            raise ValueError("PG_USER is required")

    @property
    def url(self) -> str:
        return (
            f"postgresql+psycopg2://{self.username}:{self.password}"
            f"@{self.host}:{self.port}/{self.database}"
            f"?sslmode={self.sslmode}"
        )

    @classmethod
    def from_env(cls) -> "DatabaseConfig":
        port_raw = os.getenv("PG_PORT", "5432")
        if not port_raw.isdigit():
            raise ValueError(f"PG_PORT must be a positive integer, got: {port_raw!r}")
        return cls(
            host=os.getenv("PG_HOST", ""),
            port=int(port_raw),
            database=os.getenv("PG_DB", ""),
            username=os.getenv("PG_USER", ""),
            password=os.getenv("PG_PASSWORD", ""),
            sslmode=os.getenv("PG_SSLMODE", "prefer"),
        )
