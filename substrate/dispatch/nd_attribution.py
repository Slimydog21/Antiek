"""NotDiamond advisory-routing attribution staging.

``record_nd_decision`` writes nothing to the event log. It stages metadata for
the next ``DispatchCallPayload`` emitted on the current context, preserving the
existing single-writer dispatch event flow.
"""

from __future__ import annotations

import contextvars
from typing import TypedDict


class NDDecision(TypedDict):
    nd_session_id: str | None
    nd_recommended_provider: str | None
    nd_recommended_model: str | None
    nd_tradeoff: str | None
    nd_decision_latency_ms: int | None
    nd_bypassed: bool
    nd_bypass_reason: str | None


_ND_DEFAULTS: NDDecision = {
    "nd_session_id": None,
    "nd_recommended_provider": None,
    "nd_recommended_model": None,
    "nd_tradeoff": None,
    "nd_decision_latency_ms": None,
    "nd_bypassed": False,
    "nd_bypass_reason": None,
}

_nd_ctx: contextvars.ContextVar[NDDecision | None] = contextvars.ContextVar(
    "antiek_nd_decision",
    default=None,
)


def record_nd_decision(
    *,
    nd_session_id: str | None = None,
    nd_recommended_provider: str | None = None,
    nd_recommended_model: str | None = None,
    nd_tradeoff: str | None = None,
    nd_decision_latency_ms: int | None = None,
    nd_bypassed: bool = False,
    nd_bypass_reason: str | None = None,
) -> None:
    """Stage ND attribution for the next dispatch call in this context."""
    _nd_ctx.set(
        {
            "nd_session_id": nd_session_id,
            "nd_recommended_provider": nd_recommended_provider,
            "nd_recommended_model": nd_recommended_model,
            "nd_tradeoff": nd_tradeoff,
            "nd_decision_latency_ms": nd_decision_latency_ms,
            "nd_bypassed": nd_bypassed,
            "nd_bypass_reason": nd_bypass_reason,
        }
    )


def consume_nd_decision() -> NDDecision:
    """Drain staged ND attribution once, returning defaults when absent."""
    staged = _nd_ctx.get()
    if staged is None:
        return _ND_DEFAULTS.copy()
    _nd_ctx.set(None)
    return staged.copy()


def peek_nd_decision() -> NDDecision | None:
    """Return staged attribution without draining it. Intended for tests."""
    return _nd_ctx.get()


def clear_nd_decision() -> None:
    """Clear staged attribution. Intended for tests."""
    _nd_ctx.set(None)
