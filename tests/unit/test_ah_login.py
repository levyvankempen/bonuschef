"""Tests for the one-time AH login bootstrap CLI."""

import json

import pytest

from bonuschef.utils import ah_login
from bonuschef.utils.ah_login import LOGIN_URL, _extract_code, main


@pytest.mark.parametrize(
    "arg, expected",
    [
        ("abc123", "abc123"),
        ("  abc123\n", "abc123"),
        ("appie://login-exit?code=abc123", "abc123"),
        ("appie://login-exit?code=abc123&state=x", "abc123"),
        ("code=abc123", "abc123"),
        ("https://login.ah.nl/x?foo=1&code=zzz", "zzz"),
    ],
)
def test_extract_code(arg, expected):
    assert _extract_code(arg) == expected


def test_no_args_prints_instructions(capsys):
    assert main([]) == 0
    out = capsys.readouterr().out
    assert LOGIN_URL in out
    assert "STEP 2" in out


def test_exchange_saves_tokens_and_prints_env_line(monkeypatch, tmp_path, capsys):
    token_file = tmp_path / "tokens.json"
    monkeypatch.setenv("AH_TOKEN_FILE", str(token_file))
    monkeypatch.setattr(
        ah_login,
        "exchange_code",
        lambda code, client_id: {
            "access_token": "acc",
            "refresh_token": "ref",
            "expires_in": 604798,
        },
    )
    assert main(["appie://login-exit?code=thecode"]) == 0
    out = capsys.readouterr().out
    assert "AH_REFRESH_TOKEN=ref" in out
    assert str(token_file) in out
    saved = json.loads(token_file.read_text())
    assert saved["access_token"] == "acc"
    assert saved["refresh_token"] == "ref"


def test_missing_refresh_token_fails(monkeypatch, capsys):
    monkeypatch.setattr(ah_login, "exchange_code", lambda code, client_id: {})
    assert main(["code"]) == 1
    assert "did the code expire" in capsys.readouterr().out
