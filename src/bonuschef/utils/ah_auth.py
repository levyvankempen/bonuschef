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
import logging
import os
import tempfile
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, TypeVar

import requests

_log = logging.getLogger(__name__)

_T = TypeVar("_T")

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


def _post_graphql(
    access_token: str, query: str, variables: dict[str, Any]
) -> dict[str, Any]:
    """POST a GraphQL document and return the whole body, errors included."""
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
    return resp.json()


def graphql(access_token: str, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    """Run a GraphQL query with a member Bearer token; return the ``data`` block.

    Raises ``AHAuthError`` on transport errors or GraphQL-level errors (AH
    redacts subgraph errors when the token is not authorised for a field).
    """
    body = _post_graphql(access_token, query, variables)
    if body.get("errors"):
        raise AHAuthError(f"GraphQL errors: {body['errors']}")
    return body.get("data") or {}


def graphql_partial(
    access_token: str, query: str, variables: dict[str, Any]
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Like :func:`graphql`, but hand the errors back instead of raising.

    ``recipe(id:)`` answers an unknown id with HTTP 200, a null field and a
    redacted subgraph error - byte-identical to what it returns when the recipe
    subgraph is down. A caller that has to tell those apart cannot have the
    errors raised away before it sees them.
    """
    body = _post_graphql(access_token, query, variables)
    return body.get("data") or {}, list(body.get("errors") or [])


# ---------------------------------------------------------------------------
# Persistent token store + manager
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TokenBundle:
    """What we persist between runs."""

    access_token: str
    refresh_token: str
    access_expires_at: float  # unix epoch seconds
    refreshed_at: float  # unix epoch seconds — when we last performed a refresh
    # When *this* refresh token value first appeared. Distinct from
    # ``refreshed_at``, which is stamped on every refresh and so can never tell
    # us how long a credential survives. 0.0 means unknown: files written before
    # this field existed cannot say, and guessing would understate the age.
    refresh_token_issued_at: float = 0.0

    def is_fresh(self, now: float, margin_s: float = EXPIRY_MARGIN_S) -> bool:
        return self.access_expires_at - margin_s > now

    def credential_age_s(self, now: float) -> float | None:
        """How long this refresh token has been in service, or None if unknown."""
        if not self.refresh_token_issued_at:
            return None
        return now - self.refresh_token_issued_at


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
                refresh_token_issued_at=float(raw.get("refresh_token_issued_at", 0)),
            )
        except FileNotFoundError:
            return None
        except (ValueError, KeyError, TypeError, OSError):
            # Corrupt or unreadable file: treat as absent rather than crash the
            # pipeline; the next refresh rewrites it. Say so, though — silently
            # returning None makes a corrupt file look like a missing one, and
            # that strands the deployment if AH_REFRESH_TOKEN has been cleared.
            _log.warning(
                "AH token file %s exists but could not be parsed; treating it as "
                "absent. If AH_REFRESH_TOKEN is unset too, re-run `%s`.",
                self.path,
                "python -m bonuschef.utils.ah_login",
            )
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


@dataclass(frozen=True)
class RefreshOutcome:
    """What one forced refresh told us about the refresh credential.

    Exists so the heartbeat can report on the credential it just exercised;
    ``get_access_token`` returns a bare string and cannot carry any of this.
    """

    bundle: TokenBundle
    rotated: bool  # did AH hand back a different refresh token than we sent?
    credential_age_s: float | None  # age of the credential used, None if unknown
    used_fallback: bool  # the stored credential was rejected; .env's was used


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
        return self._refresh_and_store(bundle).bundle.access_token

    def _retrying(self, call: Callable[[str], _T]) -> _T:
        """Run ``call`` with a token, retrying once with a forced refresh on 401/403."""
        try:
            return call(self.get_access_token())
        except AHAuthError as exc:
            if exc.status not in (401, 403):
                raise
        return call(self.get_access_token(force_refresh=True))

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        """Run a GraphQL query, retrying once with a forced refresh on 401/403."""
        return self._retrying(lambda token: graphql(token, query, variables))

    def graphql_partial(
        self, query: str, variables: dict[str, Any]
    ) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """As :meth:`graphql`, but returning GraphQL-level errors to the caller."""
        return self._retrying(lambda token: graphql_partial(token, query, variables))

    def refresh_now(self) -> RefreshOutcome:
        """Exercise the refresh credential unconditionally and report on it.

        The heartbeat calls this rather than ``get_access_token(force_refresh=True)``
        because it needs the rotation and age facts, which a bare token cannot
        carry.
        """
        return self._refresh_and_store(self.store.load())

    def adopt(
        self, tokens: dict[str, Any], refresh_token_used: str = ""
    ) -> TokenBundle:
        """Persist a token response (from login or refresh) and return the bundle."""
        now = self._now()
        refresh_token = str(tokens.get("refresh_token") or refresh_token_used)
        if not refresh_token:
            raise AHAuthError("Token response carried no refresh token to persist")
        # Same credential as on disk -> keep its issue time, so age measures how
        # long this value has survived. Different -> the clock starts now.
        # Unknown (0.0) stays unknown; we never invent a start date.
        previous = self.store.load()
        issued_at = (
            previous.refresh_token_issued_at
            if previous is not None and previous.refresh_token == refresh_token
            else now
        )
        expires_in = float(tokens.get("expires_in") or MAX_ACCESS_TOKEN_AGE_S)
        bundle = TokenBundle(
            access_token=str(tokens["access_token"]),
            refresh_token=refresh_token,
            access_expires_at=now + min(expires_in, MAX_ACCESS_TOKEN_AGE_S),
            refreshed_at=now,
            refresh_token_issued_at=issued_at,
        )
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

    def _refresh_and_store(self, bundle: TokenBundle | None) -> RefreshOutcome:
        candidates = self._candidates(bundle)
        if not candidates:
            raise AHAuthError(
                "No AH refresh token available: set AH_REFRESH_TOKEN or "
                f"{LOGIN_HINT} (token file: {self.store.path})"
            )
        errors: list[str] = []
        for index, token in enumerate(candidates):
            # Age belongs to the credential we are about to use, and only when
            # that is the one we loaded — a .env fallback has no known history.
            age = (
                bundle.credential_age_s(self._now())
                if bundle is not None and token == bundle.refresh_token
                else None
            )
            try:
                tokens = self._refresh(token, self.client_id)
            except AHAuthError as exc:
                errors.append(str(exc))
                continue
            adopted = self.adopt(tokens, refresh_token_used=token)
            return RefreshOutcome(
                bundle=adopted,
                # Compare against what was actually sent, not what was on disk:
                # otherwise a fallback to .env reads as a rotation.
                rotated=adopted.refresh_token != token,
                credential_age_s=age,
                used_fallback=index > 0,
            )
        raise AHAuthError(
            "All known AH refresh tokens were rejected — "
            f"{LOGIN_HINT}. Details: {' | '.join(errors)}",
            status=401,
        )


def manager_from_env() -> "AHTokenManager":
    """The token manager the whole deployment shares.

    Lives here rather than in the markdowns asset module so that jobs, schedules
    and sensors can reach it without importing ``dlt``, and so a credential-only
    job need not depend on ``AHMarkdownConfig``, which exists to carry a store id.
    """
    return AHTokenManager(
        TokenStore(default_token_file()),
        bootstrap_refresh_token=os.getenv("AH_REFRESH_TOKEN", ""),
        client_id=os.getenv("AH_CLIENT_ID", "appie"),
    )
