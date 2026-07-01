"""ANT-ND SPR-02 — NotDiamond advisory-routing attribution staging.

The seven ``nd_*`` fields on ``DispatchCallPayload`` (schema v28) record what
NotDiamond advised for a dispatch call. They are written **without adding a new
event writer**: :func:`record_nd_decision` stages the values into a
:class:`contextvars.ContextVar`, and each of the two existing ``DispatchCall``
emitters drains it via :func:`consume_nd_decision` at emit time and clears it:

* ``substrate/dispatch/router.py:_emit_dispatch_call`` — the host-local router;
* ``runtime/remote_exec/cost.py:record_remote_dispatch`` — the §16 research-
  fanout carve-out (remote research leaves, ND's DRW scope).

``record_nd_decision`` writes nothing to the event log itself — it only stages a
ContextVar, so it adds no third writer (the graph/db_lock single-writer invariant
in §16 / ``CLAUDE.md`` is untouched). Both emitters clear the ContextVar on drain,
so a staged decision cannot leak onto a later, unrelated ``DispatchCall``.

Parallel-safety: the DRW runs each investigation as its own ``asyncio`` task,
and a ``ContextVar`` is copied per task, so staging in a task and draining in
that same task's dispatch call is race-free across the up-to-20 concurrent
researches (master-spec "DRW-contract compatible" invariant).

Scope (SPR-02): staging + drain plumbing only. This module adds **zero** callers
of :func:`record_nd_decision`; SPR-03 (the pre-dispatch route hook) is the only
caller. ND stays advisory — nothing here routes or blocks; the ``cd602c9``
verify-tier fallback remains primary.
"""

from __future__ import annotations

import contextvars
from typing import TypedDict


class NDDecision(TypedDict):
    """The seven ``nd_*`` attribution values, mirroring ``DispatchCallPayload``."""

    nd_session_id: str | None
    nd_recommended_provider: str | None
    nd_recommended_model: str | None
    nd_tradeoff: str | None
    nd_decision_latency_ms: int | None
    nd_bypassed: bool
    nd_bypass_reason: str | None


# The default attribution applied to every DispatchCall that ND did not advise:
# not bypassed (there was nothing to bypass), all recommendation fields NULL.
# Applied by the emitter when nothing was staged, so pre-SPR-03 calls are
# byte-unchanged except for the additive default columns.
_ND_DEFAULTS: NDDecision = {
    "nd_session_id": None,
    "nd_recommended_provider": None,
    "nd_recommended_model": None,
    "nd_tradeoff": None,
    "nd_decision_latency_ms": None,
    "nd_bypassed": False,
    "nd_bypass_reason": None,
}

# Staged attribution for the NEXT DispatchCall emitted on this context. The
# ``None`` sentinel means "nothing staged" → the emitter applies _ND_DEFAULTS.
_nd_ctx: contextvars.ContextVar[NDDecision | None] = contextvars.ContextVar(
    "antiek_nd_decision", default=None
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
    """Stage ND attribution for the next ``DispatchCall`` on this context.

    Writes **nothing** to the event log — the single-writer invariant is
    preserved; the value is drained by :func:`consume_nd_decision` inside the
    sole emitter. Handles the partial bypass case (``nd_session_id`` NULL,
    ``nd_bypassed`` True, ``nd_bypass_reason`` set) without raising.

    SPR-02 adds no callers of this function; SPR-03's pre-dispatch route hook is
    the only caller.
    """
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
    """Drain staged ND attribution for the ``DispatchCall`` being emitted and
    clear it so it never leaks onto a later call.

    Returns the seven ``nd_*`` values, defaulting to :data:`_ND_DEFAULTS`
    (``nd_bypassed`` False, rest NULL) when nothing was staged. Called by each
    ``DispatchCall`` emitter — ``_emit_dispatch_call`` (host-local router) and
    ``record_remote_dispatch`` (remote-exec fan-out): one staged decision maps
    to exactly one emitted event, and the first emitter to fire clears it.
    """
    staged = _nd_ctx.get()
    if staged is None:
        return dict(_ND_DEFAULTS)  # type: ignore[return-value]
    _nd_ctx.set(None)  # clear — a decision attributes exactly one DispatchCall
    return dict(staged)  # type: ignore[return-value]


def peek_nd_decision() -> NDDecision | None:
    """Non-draining read of the staged decision — for tests/introspection only.
    Returns ``None`` when nothing is staged."""
    return _nd_ctx.get()


def clear_nd_decision() -> None:
    """Drop any staged decision without emitting — for test isolation."""
    _nd_ctx.set(None)
