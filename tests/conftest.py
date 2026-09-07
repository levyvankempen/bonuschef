"""Shared fixtures: isolated environment and a tiny HTTP stub."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

import pytest
import requests
from streamlit.testing.v1 import AppTest

_ISOLATED_VARS = (
    "AH_REFRESH_TOKEN",
    "AH_STORE_ID",
    "AH_CLIENT_ID",
    "DAGSTER_HOST",
    "DAGSTER_PORT",
    "DAGSTER_HOME",
    "GITHUB_TOKEN",
)


@pytest.fixture(autouse=True)
def _isolated_env(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Keep tests independent of the developer's .env and real token file."""
    for var in _ISOLATED_VARS:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("AH_TOKEN_FILE", str(tmp_path / "ah_tokens.json"))


class FakeResponse:
    """Minimal stand-in for ``requests.Response``."""

    def __init__(
        self, status: int = 200, json_body: Any = None, text: str | None = None
    ) -> None:
        self.status_code = status
        self._json = json_body
        self.text = text if text is not None else json.dumps(json_body or {})

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300

    def json(self) -> Any:
        return self._json

    def raise_for_status(self) -> None:
        if not self.ok:
            raise requests.HTTPError(f"HTTP {self.status_code}")


class HttpStub:
    """Scripted replacement for ``requests.get``/``requests.post``.

    Queue responses (or exceptions) in call order; every call is recorded as
    ``(url, kwargs)`` so tests can assert on headers, params and payloads.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self._queue: list[Any] = []

    def queue(self, *responses: Any) -> HttpStub:
        self._queue.extend(responses)
        return self

    def __call__(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append((url, kwargs))
        if not self._queue:
            raise AssertionError(f"unexpected HTTP call to {url}")
        item = self._queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    @property
    def last(self) -> tuple[str, dict[str, Any]]:
        return self.calls[-1]


@pytest.fixture
def http_post(monkeypatch: pytest.MonkeyPatch) -> Iterator[HttpStub]:
    stub = HttpStub()
    monkeypatch.setattr(requests, "post", stub)
    yield stub


@pytest.fixture
def http_get(monkeypatch: pytest.MonkeyPatch) -> Iterator[HttpStub]:
    stub = HttpStub()
    monkeypatch.setattr(requests, "get", stub)
    yield stub


# ---------------------------------------------------------------------------
# Streamlit AppTest helper
# ---------------------------------------------------------------------------

# ``AppTest.from_function`` re-executes only the function's *source*, so module
# globals (``st``, imported helpers, monkeypatched names) are missing. Instead we
# run a tiny script that imports the real module and calls the function with
# arguments parked here, which keeps ``monkeypatch.setattr(module, ...)`` effective.
PAGE_ARGS: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}


def run_app(
    func: Any, *args: Any, default_timeout: float = 10, **kwargs: Any
) -> AppTest:
    """Build an (un-run) AppTest that executes ``func(*args, **kwargs)`` in-process."""
    key = f"{func.__module__}.{func.__qualname__}"
    PAGE_ARGS[key] = (args, kwargs)
    script = (
        "from tests.conftest import PAGE_ARGS\n"
        f"from {func.__module__} import {func.__qualname__} as _page\n"
        f"_args, _kwargs = PAGE_ARGS[{key!r}]\n"
        "_page(*_args, **_kwargs)\n"
    )
    return AppTest.from_string(script, default_timeout=default_timeout)
