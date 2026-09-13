"""Configuration dataclasses with validation."""

import os
from dataclasses import dataclass, field
from pathlib import Path


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
        for name in (
            "owner",
            "repo",
            "path",
            "message_filter",
            "start_date",
            "branch",
        ):
            if not getattr(self, name):
                raise ValueError(f"GITHUB_{name.upper()} is required")
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
    A one-time browser login yields a refresh token (see ``utils/ah_login.py``).
    At runtime the tokens live in ``token_file`` and are refreshed automatically
    (see ``utils/ah_auth.AHTokenManager``); ``refresh_token`` from the
    environment is only the bootstrap/fallback, so it may be empty once the
    token file exists.
    """

    store_id: int
    refresh_token: str = ""
    client_id: str = "appie"
    token_file: Path = field(default_factory=lambda: Path("ah_tokens.json"))

    def __post_init__(self) -> None:
        if self.store_id < 1:
            raise ValueError("AH_STORE_ID must be a positive integer")

    @classmethod
    def from_env(cls) -> "AHMarkdownConfig":
        # Imported lazily: config.py must stay import-light for the portal.
        from bonuschef.utils.ah_auth import default_token_file

        store_raw = os.getenv("AH_STORE_ID", "1876")
        if not store_raw.isdigit():
            raise ValueError(
                f"AH_STORE_ID must be a positive integer, got: {store_raw!r}"
            )
        return cls(
            store_id=int(store_raw),
            refresh_token=os.getenv("AH_REFRESH_TOKEN", ""),
            client_id=os.getenv("AH_CLIENT_ID", "appie"),
            token_file=default_token_file(),
        )


@dataclass(frozen=True)
class DagsterConfig:
    """Where the portal can reach the Dagster webserver (GraphQL API).

    Used by the Streamlit portal to trigger jobs on demand (e.g. refreshing
    the store clearance snapshot). Defaults suit ``dagster dev`` on the same
    machine; docker compose / k8s override ``DAGSTER_HOST`` with the service
    name.
    """

    host: str = "localhost"
    port: int = 3000

    def __post_init__(self) -> None:
        if not self.host:
            raise ValueError("DAGSTER_HOST is required")
        if not 0 < self.port < 65536:
            raise ValueError("DAGSTER_PORT must be a valid TCP port")

    @classmethod
    def from_env(cls) -> "DagsterConfig":
        port_raw = os.getenv("DAGSTER_PORT", "3000")
        if not port_raw.isdigit():
            raise ValueError(
                f"DAGSTER_PORT must be a positive integer, got: {port_raw!r}"
            )
        return cls(host=os.getenv("DAGSTER_HOST", "localhost"), port=int(port_raw))


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


@dataclass(frozen=True)
class NtfyConfig:
    """Where unattended run failures get pushed.

    The topic is a capability URL: anyone who knows the name can read the
    notifications, so it must be long and random. Unlike every other config
    here, ``from_env`` returns ``None`` rather than raising when the topic is
    unset — absent alerting is a deliberate choice, not a misconfiguration, and
    it keeps local development and the test suite free of external services.
    """

    topic: str
    server: str = "https://ntfy.sh"

    def __post_init__(self) -> None:
        if not self.topic:
            raise ValueError("NTFY_TOPIC is required")
        if not self.server.startswith(("http://", "https://")):
            raise ValueError("NTFY_SERVER must be an http(s) URL")

    @property
    def url(self) -> str:
        return f"{self.server.rstrip('/')}/{self.topic}"

    @classmethod
    def from_env(cls) -> "NtfyConfig | None":
        """``None`` when unconfigured, so callers can skip rather than handle."""
        topic = os.getenv("NTFY_TOPIC", "").strip()
        if not topic:
            return None
        return cls(topic=topic, server=os.getenv("NTFY_SERVER", "https://ntfy.sh"))
