"""Fixture: structure-only test — ONLY call-shape assertions on a behavioral mock.

The lint must flag this: every assertion pins HOW the provider was invoked,
never the unit's output. Parsed by the lint with ``ast``; never executed by pytest.
"""

from __future__ import annotations

from unittest.mock import MagicMock


def dispatch(provider, payload: str) -> None:
    provider.send(payload)


def test_only_call_shape_on_provider():
    provider = MagicMock()
    dispatch(provider, "doc-1")
    provider.send.assert_called_once_with("doc-1")