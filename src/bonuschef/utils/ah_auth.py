"""Albert Heijn member authentication and GraphQL helpers.

The store-specific markdown ("laatste kans koopjes") feed lives behind AH's
GraphQL API and requires a *member* access token. The anonymous token used by
``supermarktconnector`` returns redacted subgraph errors for these fields.

A one-time browser OAuth login (see ``ah_login.py``) yields a long-lived
refresh token. At runtime we exchange that refresh token for a short-lived
member access token and use it as a Bearer token against ``/graphql``.
"""

from __future__ import annotations

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


class AHAuthError(RuntimeError):
    """Raised when a token exchange or refresh fails."""


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
            f"Code exchange failed (HTTP {resp.status_code}): {resp.text[:300]}"
        )
    return resp.json()


def refresh_access_token(refresh_token: str, client_id: str = "appie") -> str:
    """Exchange a refresh token for a fresh member access token."""
    resp = requests.post(
        f"{AUTH_BASE}/token/refresh",
        headers=HEADERS,
        json={"clientId": client_id, "refreshToken": refresh_token},
        timeout=_TIMEOUT,
    )
    if not resp.ok:
        raise AHAuthError(
            f"Token refresh failed (HTTP {resp.status_code}). The refresh token "
            "may have expired — re-run `python -m bonuschef.utils.ah_login`. "
            f"Response: {resp.text[:200]}"
        )
    access_token = resp.json().get("access_token")
    if not access_token:
        raise AHAuthError("Token refresh succeeded but returned no access_token")
    return access_token


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
        raise AHAuthError(f"GraphQL HTTP {resp.status_code}: {resp.text[:300]}")
    body = resp.json()
    if body.get("errors"):
        raise AHAuthError(f"GraphQL errors: {body['errors']}")
    return body.get("data") or {}
