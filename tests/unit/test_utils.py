"""Tests for small shared utilities."""

from datetime import datetime

import pytest

from bonuschef.utils.utils import greeting_based_on_time


@pytest.mark.parametrize(
    "hour, expected",
    [
        (5, "Good morning"),
        (11, "Good morning"),
        (12, "Good afternoon"),
        (17, "Good afternoon"),
        (18, "Good evening"),
        (21, "Good evening"),
        (22, "Good night"),
        (4, "Good night"),
    ],
)
def test_greeting_by_hour(hour, expected):
    assert greeting_based_on_time(datetime(2025, 1, 6, hour)) == expected


def test_greeting_defaults_to_now():
    assert greeting_based_on_time().startswith("Good ")
