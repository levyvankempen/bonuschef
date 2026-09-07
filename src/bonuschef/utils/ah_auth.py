"""Albert Heijn member authentication and GraphQL helpers.

The store-specific markdown ("laatste kans koopjes") feed lives behind AH's
GraphQL API and requires a *member* access token. The anonymous token used by
``supermarktconnector`` returns redacted subgraph errors for these fields.

A one-time browser OAuth login (see ``ah_login.py``) yields a long-lived
refresh token. At runtime :class:`AHTokenManager` keeps a small JSON token file
up to date so the pipeline survives unattended:

- the access token (valid ~7 days) is cached and reused across runs,
- it is refreshed at most once a day, which also keeps the refresh token
  "in use" (AH expires refresh tokens that sit idle for weeks),
- if AH rotates the refresh token on refresh, the new one is persisted,
- the ``AH_REFRESH_TOKEN`` env var is only a bootstrap / fallback, so a fresh
  login pasted into ``.env`` takes over when the stored token is dead.
"""

from __future__ import annotations

import json
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import requests

AUTH_BASE = "https://api.ah.nl/mobile-auth/v1/auth"
GRAPHQL_URL = "https://api.ah.nl/graphql"

# Mirrors the headers the official Android app sends; required or AH 403s.
HEADERS = {
    "Host": "api.ah.nl",
    "x-application": "AHWEBSHOP",
    "user-agent": "Appie/8.8.2 Model/phone Android/7.0-API24",
    "content-type": "application/json; charset=UTF-8",
}

_TIMEOUT = 20

# Refresh the access token at least this often even if AH says it lives longer:
# a daily refresh keeps the refresh token alive and bounds the damage of a
# revoked access token to one day.
MAX_ACCESS_TOKEN_AGE_S = 24 * 3600
# Refresh a little before the recorded expiry so a run never starts with a
# token that dies mid-flight.
EXPIRY_MARGIN_S = 5 * 60

LOGIN_HINT = "re-run `python -m bonuschef.utils.ah_login` to obtain a new token"


class AHAuthError(RuntimeError):
    """Raised when a token exchange, refresh, or GraphQL call fails."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


# ---------------------------------------------------------------------------
# Raw HTTP calls
# ---------------------------------------------------------------------------


def exchange_code(code: str, client_id: str = "appie") -> dict[str, Any]:
    """Exchange a one-time OAuth authorization code for member tokens."""
    resp = requests.post(
        f"{AUTH_BASE}/token",
        headers=HEADERS,
        json={"clientId": client_id, "code": code},
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise AHAuthError(
            f"Code exchange failed (HTTP {resp.status_code}): {resp.text[:300]}",
            status=resp.status_code,
        )
    return resp.json()


def refresh_tokens(refresh_token: str, client_id: str = "appie") -> dict[str, Any]:
    """Exchange a refresh token for a fresh token response.

    Returns AH's JSON body, which always carries ``access_token`` and
    ``expires_in`` and may carry a rotated ``refresh_token``.
    """
    resp = requests.post(
        f"{AUTH_BASE}/token/refresh",
        headers=HEADERS,
        json={"clientId": client_id, "refreshToken": refresh_token},
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise AHAuthError(
            f"Token refresh failed (HTTP {resp.status_code}). The refresh token "
            f"may have expired — {LOGIN_HINT}. Response: {resp.text[:200]}",
            status=resp.status_code,
        )
    body = resp.json()
    if not body.get("access_token"):
        raise AHAuthError("Token refresh succeeded but returned no access_token")
    return body


def refresh_access_token(refresh_token: str, client_id: str = "appie") -> str:
    """Exchange a refresh token for a fresh member access token (no caching)."""
    return refresh_tokens(refresh_token, client_id)["access_token"]


def graphql(access_token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Run a GraphQL query with a member Bearer token; return the ``data`` block.

    Raises ``AHAuthError`` on transport errors or GraphQL-level errors (AH
    redacts subgraph errors when the token is not authorised for a field).
    """
    resp = requests.post(
        GRAPHQL_URL,
        headers={**HEADERS, "Authorization": f"Bearer {access_token}"},
        json={"query": query, "variables": variables},
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise AHAuthError(
            f"GraphQL HTTP {resp.status_code}: {resp.text[:300]}",
            status=resp.status_code,
        )
    body = resp.json()
    if body.get("errors"):
        raise AHAuthError(f"GraphQL errors: {body['errors']}")
    return body.get("data") or {}


# ---------------------------------------------------------------------------
# Persistent token store + manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenBundle:
    """What we persist between runs."""

    access_token: str
    refresh_token: str
    access_expires_at: float  # unix epoch seconds
    refreshed_at: float  # unix epoch seconds

    def is_fresh(self, now: float, margin_s: float = EXPIRY_MARGIN_S) -> bool:
        return self.access_expires_at - margin_s > now


def default_token_file() -> Path:
    """Where tokens live unless ``AH_TOKEN_FILE`` overrides it.

    Prefers ``DAGSTER_HOME`` because that is the one volume every Dagster
    process (webserver, daemon, run workers) already shares in compose/k8s.
    """
    override = os.getenv("AH_TOKEN_FILE")
    if override:
        return Path(override).expanduser()
    dagster_home = os.getenv("DAGSTER_HOME")
    if dagster_home:
        return Path(dagster_home) / "ah_tokens.json"
    return Path.home() / ".bonuschef" / "ah_tokens.json"


class TokenStore:
    """Atomic JSON file persistence for a :class:`TokenBundle`."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def load(self) -> TokenBundle | None:
        try:
            raw = json.loads(self.path.read_text())
            return TokenBundle(
                access_token=str(raw["access_token"]),
                refresh_token=str(raw["refresh_token"]),
                access_expires_at=float(raw["access_expires_at"]),
                refreshed_at=float(raw.get("refreshed_at", 0)),
            )
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, OSError):
            # Corrupt or unreadable file: treat as absent rather than crash the
            # pipeline; the next refresh rewrites it.
            return None

    def save(self, bundle: TokenBundle) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".ah_tokens-")
        try:
            with os.fdopen(fd, "w") as fh:
                json.dump(asdict(bundle), fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            Path(tmp).unlink(missing_ok=True)
            raise


class AHTokenManager:
    """Hands out a valid member access token, refreshing and persisting as needed."""

    def __init__(
        self,
        store: TokenStore,
        bootstrap_refresh_token: str = "",
        client_id: str = "appie",
        *,
        refresh: Callable[[str, str], dict[str, Any]] = refresh_tokens,
        now: Callable[[], float] = time.time,
    ) -> None:
        self.store = store
        self.bootstrap_refresh_token = bootstrap_refresh_token
        self.client_id = client_id
        self._refresh = refresh
        self._now = now

    # -- public API ---------------------------------------------------------

    def get_access_token(self, force_refresh: bool = False) -> str:
        """Return a usable access token, refreshing when stale or forced."""
        bundle = self.store.load()
        if bundle and not force_refresh and bundle.is_fresh(self._now()):
            return bundle.access_token
        return self._refresh_and_store(bundle).access_token

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Run a GraphQL query, retrying once with a forced refresh on 401/403."""
        try:
            return graphql(self.get_access_token(), query, variables)
        except AHAuthError as exc:
            if exc.status not in (401, 403):
                raise
        return graphql(self.get_access_token(force_refresh=True), query, variables)

    def adopt(
        self, tokens: dict[str, Any], refresh_token_used: str = ""
    ) -> TokenBundle:
        """Persist a token response (from login or refresh) and return the bundle."""
        now = self._now()
        expires_in = float(tokens.get("expires_in") or MAX_ACCESS_TOKEN_AGE_S)
        bundle = TokenBundle(
            access_token=str(tokens["access_token"]),
            refresh_token=str(tokens.get("refresh_token") or refresh_token_used),
            access_expires_at=now + min(expires_in, MAX_ACCESS_TOKEN_AGE_S),
            refreshed_at=now,
        )
        if not bundle.refresh_token:
            raise AHAuthError("Token response carried no refresh token to persist")
        self.store.save(bundle)
        return bundle

    # -- internals ----------------------------------------------------------

    def _candidates(self, bundle: TokenBundle | None) -> list[str]:
        """Refresh tokens to try, most likely to work first, without duplicates."""
        ordered = [bundle.refresh_token if bundle else "", self.bootstrap_refresh_token]
        # Another process may have rotated the token since we loaded the file.
        latest = self.store.load()
        if latest and latest.refresh_token:
            ordered.insert(1, latest.refresh_token)
        unique: list[str] = []
        for token in ordered:
            if token and token not in unique:
                unique.append(token)
        return unique

    def _refresh_and_store(self, bundle: TokenBundle | None) -> TokenBundle:
        candidates = self._candidates(bundle)
        if not candidates:
            raise AHAuthError(
                "No AH refresh token available: set AH_REFRESH_TOKEN or "
                f"{LOGIN_HINT} (token file: {self.store.path})"
            )
        errors: list[str] = []
        for token in candidates:
            try:
                tokens = self._refresh(token, self.client_id)
            except AHAuthError as exc:
                errors.append(str(exc))
                continue
            return self.adopt(tokens, refresh_token_used=token)
        raise AHAuthError(
            "All known AH refresh tokens were rejected — "
            f"{LOGIN_HINT}. Details: {' | '.join(errors)}",
            status=401,
        )
