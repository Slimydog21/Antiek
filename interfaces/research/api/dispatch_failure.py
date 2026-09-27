"""Classify dispatch/decompose failures for DRW plan creation.

Maps caught exceptions to the closed code set in
``docs/decisions/drw-plan-failure-contract.md``. Pure function — no I/O.

Also holds ``RoleDispatchFailed``, the typed signal a Loop One role bridge
raises when no model answered its call.
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

class RoleDispatchFailed(Exception):
    """No model answered a research role's call.

    Raised by a role bridge's ``_dispatch_and_parse`` when the provider call
    itself failed (ProviderError, an unregistered provider, an open breaker,
    an unavailable owner credential), as distinct from a model that answered
    with something that did not parse. The bridge's handler catches it and
    emits its fallback Delivered stamped ``role_outcome="dispatch_failed"``,
    so the orchestrator cannot mistake the outage for the model's own
    ``insufficient_evidence`` verdict. ``policy_id`` is the stamp the bridge
    has always put on that fallback event."""

    def __init__(self, role: str, policy_id: str) -> None:
        self.role = role
        self.policy_id = policy_id
        super().__init__(f"{role} dispatch failed ({policy_id})")
