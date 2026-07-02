"""Fixture: the CANONICAL FAKE GATE — asserts-own-mock-return.

The test configures a mock's ``return_value`` and then asserts the unit returns
exactly that value. It proves only that the mock returns what it was told to —
the purest form of a non-predictive test. The census must label this
``structure`` with reason ``asserts-own-mock-return``.

Contrast with test_pure_behavior: there the asserted value comes from real
production code; here it comes from the mock the test itself configured.

Parsed, not executed (see test_pure_behavior.py header).
"""

from __future__ import annotations

from unittest.mock import MagicMock


def fetch_total(provider) -> int:
    return provider.total()


def test_fetch_total_returns_configured_value():
    provider = MagicMock()
    provider.return_value = 7
    provider.total.return_value = 7
    result = provider.total()
    assert result == 7
