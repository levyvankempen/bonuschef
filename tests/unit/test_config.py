"""Tests for configuration dataclasses."""

import pytest

from bonuschef.config import DatabaseConfig, GitHubConfig


class TestGitHubConfig:
    def test_valid_config(self):
        cfg = GitHubConfig(
            owner="supermarkt",
            repo="checkjebon",
            path="data/supermarkets.json",
            message_filter="Update supermarkets.json",
            start_date="2025-01-01T00:00:00Z",
            branch="main",
            token=None,
            max_pages=2,
        )
        assert cfg.owner == "supermarkt"
        assert cfg.token is None

    def test_missing_owner_raises(self):
        with pytest.raises(ValueError, match="GITHUB_OWNER"):
            GitHubConfig(
                owner="",
                repo="checkjebon",
                path="data/supermarkets.json",
                message_filter="Update",
                start_date="2025-01-01T00:00:00Z",
                branch="main",
                token=None,
                max_pages=2,
            )

    def test_missing_repo_raises(self):
        with pytest.raises(ValueError, match="GITHUB_REPO"):
            GitHubConfig(
                owner="supermarkt",
                repo="",
                path="data/supermarkets.json",
                message_filter="Update",
                start_date="2025-01-01T00:00:00Z",
                branch="main",
                token=None,
                max_pages=2,
            )

    def test_max_pages_zero_raises(self):
        with pytest.raises(ValueError, match="GITHUB_MAX_PAGES"):
            GitHubConfig(
                owner="supermarkt",
                repo="checkjebon",
                path="data/supermarkets.json",
                message_filter="Update",
                start_date="2025-01-01T00:00:00Z",
                branch="main",
                token=None,
                max_pages=0,
            )

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("GITHUB_OWNER", "supermarkt")
        monkeypatch.setenv("GITHUB_REPO", "checkjebon")
        monkeypatch.setenv("GITHUB_PATH", "data/supermarkets.json")
        monkeypatch.setenv("GITHUB_MESSAGE_FILTER", "Update supermarkets.json")
        monkeypatch.setenv("GITHUB_START_DATE", "2025-01-01T00:00:00Z")
        monkeypatch.setenv("GITHUB_BRANCH", "main")
        monkeypatch.setenv("GITHUB_MAX_PAGES", "3")

        cfg = GitHubConfig.from_env()
        assert cfg.owner == "supermarkt"
        assert cfg.max_pages == 3
        assert cfg.token is None

    def test_from_env_invalid_max_pages(self, monkeypatch):
        monkeypatch.setenv("GITHUB_MAX_PAGES", "abc")
        with pytest.raises(ValueError, match="positive integer"):
            GitHubConfig.from_env()

    def test_from_env_missing_max_pages(self, monkeypatch):
        monkeypatch.delenv("GITHUB_MAX_PAGES", raising=False)
        with pytest.raises(ValueError, match="positive integer"):
            GitHubConfig.from_env()

    def test_frozen(self):
        cfg = GitHubConfig(
            owner="supermarkt",
            repo="checkjebon",
            path="data/supermarkets.json",
            message_filter="Update",
            start_date="2025-01-01T00:00:00Z",
            branch="main",
            token=None,
            max_pages=2,
        )
        with pytest.raises(AttributeError):
            cfg.owner = "other"


class TestDatabaseConfig:
    def test_valid_config(self):
        cfg = DatabaseConfig(
            host="localhost",
            port=5455,
            database="postgres",
            username="postgres",
            password="postgres",
        )
        assert "localhost:5455" in cfg.url
        assert "postgresql+psycopg2" in cfg.url

    def test_missing_host_raises(self):
        with pytest.raises(ValueError, match="PG_HOST"):
            DatabaseConfig(
                host="",
                port=5455,
                database="postgres",
                username="postgres",
                password="postgres",
            )

    def test_missing_database_raises(self):
        with pytest.raises(ValueError, match="PG_DB"):
            DatabaseConfig(
                host="localhost",
                port=5455,
                database="",
                username="postgres",
                password="postgres",
            )

    def test_from_env(self, monkeypatch):
        monkeypatch.setenv("PG_HOST", "localhost")
        monkeypatch.setenv("PG_PORT", "5455")
        monkeypatch.setenv("PG_DB", "postgres")
        monkeypatch.setenv("PG_USER", "postgres")
        monkeypatch.setenv("PG_PASSWORD", "secret")

        cfg = DatabaseConfig.from_env()
        assert cfg.host == "localhost"
        assert cfg.port == 5455
        assert cfg.sslmode == "prefer"
        assert "secret" in cfg.url

    def test_from_env_invalid_port(self, monkeypatch):
        monkeypatch.setenv("PG_PORT", "not_a_number")
        with pytest.raises(ValueError, match="positive integer"):
            DatabaseConfig.from_env()

    def test_default_sslmode(self):
        cfg = DatabaseConfig(
            host="localhost",
            port=5455,
            database="postgres",
            username="postgres",
            password="postgres",
        )
        assert cfg.sslmode == "prefer"
        assert "sslmode=prefer" in cfg.url
