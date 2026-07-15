"""Cost flow for remote-exec research — through the existing DispatchCall path.

The single discipline this module enforces: **remote-exec cost is not a new
cost surface.** A remote research's spend (sandbox time + the inference the
in-sandbox loop ran) flows through the exact same ``DispatchCallPayload``
event the host-local dispatch path emits, so SPR-07's cost surface sees it
with zero special-casing. A reader of the trajectory cannot tell a remote
leaf's cost from a host-local leaf's cost by shape — only by the
``provider`` field naming "daytona", which is information, not a divergence.

What flows where:

  * Per **step**, the runner calls ``record_remote_dispatch`` with the
    realized ``cost_usd`` / ``tokens`` the sandbox reported for that step.
    That emits one ``DispatchCallPayload`` event onto the investigation's
    JSONL — the same emit the router does in ``_emit_dispatch_call``.
  * The same ``cost_usd`` is charged to the ``BudgetManager`` (per-research
    cap + aggregate ``TOTAL_ACQUISITION_BUDGET_USD``). Charging and emitting
    use the *same* number, so the ledger reconciles with the dispatch stream
    by construction — no estimate-presented-as-actual, no under-count.

The cost is **realized, not estimated**: the value comes off
``RemoteStepEvent.cost_usd``, which the provider populates from the sandbox's
actual time slice + the inference it ran. The host-side runner never invents
a cost; it records what the sandbox reports, exactly as the host-local runner
records what each step reports.

Budget halt: ``BudgetManager.charge`` raises ``BudgetExceeded`` when a charge
pushes the research past its per-research cap or the fan-out past the
aggregate cap; ``BudgetManager.can_launch`` gates whether the *next* leaf may
start. The runner and the fan-out orchestration use both to stop launching
new leaves and to halt an over-spending one — identical semantics to the
host-local runner, because it is the *same* ``BudgetManager``.
"""

from __future__ import annotations

import os
import sys

try:
    from substrate.dispatch.nd_attribution import consume_nd_decision

    from ...event_log import emit_typed
    from ...schemas.events import DispatchCallPayload
    from ..research_runner.budget import BudgetManager
    from .provider import RemoteStepEvent
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.remote_exec.provider import RemoteStepEvent  # type: ignore[no-redef]
    from runtime.research_runner.budget import BudgetManager  # type: ignore[no-redef]
    from substrate.dispatch.nd_attribution import consume_nd_decision
    from substrate.event_log import emit_typed  # type: ignore[no-redef]
    from substrate.schemas.events import DispatchCallPayload  # type: ignore[no-redef]


# Default tier label for remote-exec inference. Remote leaves run the same
# research loop a host-local leaf runs; "pro" is the loop's default tier (the
# in-sandbox loop overrides via the event's data when it dispatches at a
# different tier). Kept a Literal-valid value so the DispatchCallPayload
# validates.
DEFAULT_REMOTE_TIER = "pro"


def record_remote_dispatch(
    *,
    investigation_id: str,
    event: RemoteStepEvent,
    budget: BudgetManager,
    role: str = "user_agent",
    events_dir: str | None = None,
    parent_event_id: str | None = None,
    context_pack_event_id: str | None = None,
) -> str | None:
    """Charge the budget for one remote step and emit its ``DispatchCall``
    event, both from the *same* realized cost on the ``RemoteStepEvent``.

    Returns the emitted event_id (or ``None`` if events are disabled). Raises
    ``BudgetExceeded`` if the charge pushes the research past its per-research
    cap or the fan-out past the aggregate cap — the runner catches it and
    halts the leaf, exactly as the host-local runner does.

    Charge-then-emit ordering: we charge first so a budget halt does not leave
    a dangling cost event for a step the runner is about to refuse. If the
    charge raises, no event is emitted and the runner halts the leaf; the
    over-spend that triggered the halt is still recorded in the ledger (honest
    accounting — ``BudgetManager.charge`` applies the charge before raising)."""
    # Charge first. On BudgetExceeded this propagates to the runner, which
    # transitions the leaf to BUDGET_HALTED. The ledger has already recorded
    # the over-spend (honest accounting in BudgetManager.charge).
    budget.charge(investigation_id, event.cost_usd, event.tokens)

    # Emit a DispatchCall event in the same shape the router emits. The only
    # remote-distinguishing field is `provider` (e.g. "daytona") — by design:
    # it is information for the cost surface, not a schema fork.
    provider = event.provider or "remote_exec"
    model = event.model or "research-leaf"
    tier = event.data.get("tier", DEFAULT_REMOTE_TIER)
    nd = consume_nd_decision()
    return emit_typed(
        investigation_id,
        DispatchCallPayload(
            provider=provider,
            model=model,
            tier=tier,
            target_role=role,
            input_tokens=int(event.data.get("input_tokens", 0)),
            output_tokens=int(event.data.get("output_tokens", event.tokens)),
            cost_usd=float(event.cost_usd),
            latency_ms=int(event.data.get("latency_ms", 0)),
            verification_required=bool(event.data.get("verification_required", False)),
            fallback_chain_index=0,
            prompt_hash=str(event.data.get("prompt_hash", "remote")),
            finish_reason=event.data.get("finish_reason"),
            context_pack_event_id=context_pack_event_id,
            nd_session_id=nd["nd_session_id"],
            nd_recommended_provider=nd["nd_recommended_provider"],
            nd_recommended_model=nd["nd_recommended_model"],
            nd_tradeoff=nd["nd_tradeoff"],
            nd_decision_latency_ms=nd["nd_decision_latency_ms"],
            nd_bypassed=nd["nd_bypassed"],
            nd_bypass_reason=nd["nd_bypass_reason"],
        ),
        parent_event_id=parent_event_id,
        role=role,
        policy_id=f"{provider}/{model}",
        events_dir=events_dir,
    )


__all__ = ["record_remote_dispatch", "DEFAULT_REMOTE_TIER"]
