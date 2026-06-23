"""Classify dispatch/decompose failures for DRW plan creation.

Maps caught exceptions to the closed code set in
``docs/decisions/drw-plan-failure-contract.md``. Pure function — no I/O.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass

from substrate.dispatch.base import ProviderError

# Canonical human-safe copy — must match drw-plan-failure-contract.md §4.
_MESSAGES: dict[str, str] = {
    "provider_unconfigured": (
        "No model provider is configured. Set a provider key and restart."
    ),
    "provider_upstream_error": (
        "The model provider returned an error. Retry, or check your key's quota."
    ),
    "timeout": "The engine took too long to respond. Try again.",
    "unknown": "Something unexpected went wrong. Try again.",
}

# HTTP status per drw-plan-failure-contract.md §3.
_STATUS: dict[str, int] = {
    "provider_unconfigured": 503,
    "provider_upstream_error": 502,
    "timeout": 504,
    "unknown": 500,
}

_DEFAULT_RETRYABLE: dict[str, bool] = {
    "provider_unconfigured": False,
    "provider_upstream_error": True,
    "timeout": True,
    "unknown": True,
}


@dataclass(frozen=True)
class FailureClassification:
    code: str
    status: int
    message: str
    retryable: bool


def _is_empty_registry_provider_error(exc: ProviderError) -> bool:
    """No usable provider: exhausted chain or tier not bootstrapped (router.py)."""
    if exc.provider == "<none>":
        return True
    msg = str(exc).lower()
    return "not registered" in msg or "no api key" in msg


def classify_dispatch_failure(exc: BaseException) -> FailureClassification:
    """Map a decompose exception to HTTP status + structured detail fields."""

    if isinstance(exc, ProviderError):
        if _is_empty_registry_provider_error(exc):
            code = "provider_unconfigured"
            retryable = False
        else:
            code = "provider_upstream_error"
            retryable = bool(exc.retryable)
    elif isinstance(exc, (asyncio.TimeoutError, TimeoutError)):
        code = "timeout"
        retryable = _DEFAULT_RETRYABLE[code]
    else:
        # Honest catch-all — never default to provider_unconfigured.
        code = "unknown"
        retryable = _DEFAULT_RETRYABLE[code]

    return FailureClassification(
        code=code,
        status=_STATUS[code],
        message=_MESSAGES[code],
        retryable=retryable,
    )