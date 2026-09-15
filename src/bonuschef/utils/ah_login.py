"""One-time Albert Heijn member-login bootstrap.

The markdown/clearance feed requires a member token. AH's login is a browser
OAuth flow whose authorization code is delivered via a blocked
``appie://login-exit?code=...`` redirect, so it cannot be fully automated. Run
this once to capture the code and print a refresh token for your ``.env``.

Usage
-----
    # Step 1 — print the login URL + instructions
    python -m bonuschef.utils.ah_login

    # Step 2 — after logging in, pass the captured code (or full redirect URL)
    python -m bonuschef.utils.ah_login "appie://login-exit?code=PASTE_HERE"

Capturing the code (Firefox is easiest):
  1. Open the login URL, open DevTools (F12) → Console.
  2. Complete the login. The browser blocks the final redirect and logs:
       "Navigeren naar 'appie://login-exit?code=...' is voorkomen ..."
  3. Copy that ``code`` value and pass it to step 2.

The tokens are written straight to the token file the pipeline uses (see
``ah_auth.default_token_file``), and the refresh token is printed so you can
also keep it in ``.env`` as ``AH_REFRESH_TOKEN`` (the fallback when the token
file is missing, e.g. on a fresh host). From then on the pipeline refreshes
automatically; you only re-run this if every known refresh token is rejected.
"""

from __future__ import annotations

import re
import sys
from urllib.parse import parse_qs, urlparse

from bonuschef.utils.ah_auth import (
    AHTokenManager,
    TokenStore,
    default_token_file,
    exchange_code,
)

CLIENT_ID = "appie"
LOGIN_URL = (
    "https://login.ah.nl/secure/oauth/authorize"
    f"?client_id={CLIENT_ID}&response_type=code&redirect_uri=appie://login-exit"
)


def _extract_code(arg: str) -> str:
    """Accept a bare code or a full ``appie://login-exit?code=...`` URL."""
    arg = arg.strip()
    if "code=" in arg:
        query = urlparse(arg).query or arg.split("?", 1)[-1]
        values = parse_qs(query).get("code")
        if values:
            return values[0]
        match = re.search(r"code=([^&\s]+)", arg)
        if match:
            return match.group(1)
    return arg


def _print_instructions() -> None:
    print("STEP 1 — open this URL in your browser and log in to Albert Heijn:\n")
    print(f"  {LOGIN_URL}\n")
    print(
        "Open DevTools (F12) → Console before finishing login. The browser will\n"
        "block the final redirect and log a line like:\n\n"
        "  Navigeren naar 'appie://login-exit?code=XXXX' is voorkomen ...\n\n"
        "STEP 2 — copy that code and run:\n\n"
        '  python -m bonuschef.utils.ah_login "appie://login-exit?code=XXXX"\n'
    )


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        _print_instructions()
        return 0

    code = _extract_code(argv[0])
    tokens = exchange_code(code, client_id=CLIENT_ID)
    refresh_token = tokens.get("refresh_token")
    if not refresh_token:
        print("No refresh_token in response — did the code expire? Try again.")
        return 1

    token_file = default_token_file()
    AHTokenManager(TokenStore(token_file), client_id=CLIENT_ID).adopt(tokens)

    print(f"Login successful. Tokens saved to {token_file}\n")
    print("Also keep this line in your .env as a fallback for fresh hosts:\n")
    print(f"AH_REFRESH_TOKEN={refresh_token}\n")
    print(
        f"(access token valid ~{tokens.get('expires_in', '?')}s; the pipeline "
        "refreshes it automatically and keeps the token file up to date.)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
