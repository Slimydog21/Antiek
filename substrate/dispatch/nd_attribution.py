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
_nd_repeat_ctx: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "antiek_nd_decision_repeat", default=False
)
_nd_scope_ctx: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "antiek_nd_decision_scope", default=None
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


def consume_nd_decision(*, scope: object | None = None) -> NDDecision:
    """Drain staged ND attribution once, returning defaults when absent."""
    staged = _nd_ctx.get()
    if staged is None:
        return _ND_DEFAULTS.copy()
    staged_scope = _nd_scope_ctx.get()
    if staged_scope is not None and scope is not staged_scope:
        return _ND_DEFAULTS.copy()
    if not _nd_repeat_ctx.get():
        _nd_ctx.set(None)
    return staged.copy()


def push_nd_decision(
    decision: NDDecision, *, scope: object
) -> tuple[
    contextvars.Token[NDDecision | None],
    contextvars.Token[bool],
    contextvars.Token[object | None],
]:
    """Install repeatable attribution for one nested dispatch scope."""
    return (
        _nd_ctx.set(decision.copy()),
        _nd_repeat_ctx.set(True),
        _nd_scope_ctx.set(scope),
    )


def reset_nd_decision(
    tokens: tuple[
        contextvars.Token[NDDecision | None],
        contextvars.Token[bool],
        contextvars.Token[object | None],
    ],
) -> None:
    """Restore the exact enclosing attribution scope."""
    decision_token, repeat_token, scope_token = tokens
    _nd_scope_ctx.reset(scope_token)
    _nd_repeat_ctx.reset(repeat_token)
    _nd_ctx.reset(decision_token)


def peek_nd_decision() -> NDDecision | None:
    """Return staged attribution without draining it. Intended for tests."""
    return _nd_ctx.get()


def clear_nd_decision() -> None:
    """Clear staged attribution. Intended for tests."""
    _nd_ctx.set(None)
