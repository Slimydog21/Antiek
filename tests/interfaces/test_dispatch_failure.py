"""Unit tests for classify_dispatch_failure (DRW plan failure contract)."""

from __future__ import annotations

import asyncio

import pytest

from interfaces.research.api.dispatch_failure import classify_dispatch_failure
from substrate.dispatch.base import ProviderError


@pytest.mark.parametrize(
    "exc, code, status, retryable",
    [
        (
            ProviderError(
                "every tier in the chain has provider=None",
                provider="<none>",
                model="<none>",
                latency_ms=0,
            ),
            "provider_unconfigured",
            503,
            False,
        ),
        (
            ProviderError(
                "rate limited",
                provider="openrouter",
                model="anthropic/claude-3.5-sonnet",
                latency_ms=120,
                retryable=True,
            ),
            "provider_upstream_error",
            502,
            True,
        ),
        (
            ProviderError(
                "bad gateway",
                provider="openrouter",
                model="x",
                latency_ms=1,
                retryable=False,
            ),
            "provider_upstream_error",
            502,
            False,
        ),
        (
            ProviderError(
                "provider 'openrouter' is not registered (no API key / not bootstrapped)",
                provider="openrouter",
                model="m",
                latency_ms=0,
                retryable=True,
            ),
            "provider_unconfigured",
            503,
            False,
        ),
        (asyncio.TimeoutError(), "timeout", 504, True),
        (TimeoutError(), "timeout", 504, True),
        (ValueError("build_plan blew up"), "unknown", 500, True),
        (RuntimeError("db locked"), "unknown", 500, True),
    ],
)
def test_classify_dispatch_failure_branches(exc, code, status, retryable):
    c = classify_dispatch_failure(exc)
    assert c.code == code
    assert c.status == status
    assert c.retryable is retryable
    assert "ProviderError" not in c.message
    assert type(exc).__name__ not in c.message


def test_unknown_never_becomes_provider_unconfigured():
    c = classify_dispatch_failure(Exception("totally unrelated"))
    assert c.code == "unknown"
    assert c.code != "provider_unconfigured"