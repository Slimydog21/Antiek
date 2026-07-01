"""RLM-kind investigation entrypoint.

Sprint 13 splits ``investigation.start_requested`` into two lanes:
``loop_one`` keeps the fixed phase chain, while ``rlm`` starts the
open-ended RLM lane. This module owns the latter subscription boundary.
"""

from __future__ import annotations

from decimal import Decimal

from interfaces.research.api.broadcast import EventBroadcaster
from orchestration.rlm.session import (
    RLMRatificationRequired,
    create_session,
    iterate_session,
    iteration_payload,
    session_completed_payload,
    session_started_payload,
)
from substrate.schemas import (
    ActionType,
    Event,
    InvestigationFailedPayload,
    InvestigationStartRequestedPayload,
)

from .coordinator import broadcast_emit


def _action_value(action_type) -> str:
    return action_type.value if hasattr(action_type, "value") else str(action_type)


def make_rlm_investigation_handler(broadcaster: EventBroadcaster):
    """Build the RLM-kind handler for ``investigation.start_requested``.

    This is the bootstrap lane wiring: it proves routing, ratification,
    session event emission, and per-investigation isolation. The real root
    planner can replace the deterministic iteration body without changing the
    event subscription contract.
    """

    async def handle_investigation_start(event: Event) -> None:
        if not isinstance(event.payload, InvestigationStartRequestedPayload):
            return
        req = event.payload
        if req.investigation_kind != "rlm":
            return

        try:
            session = create_session(
                investigation_id=event.investigation_id,
                root_role="rlm_orchestrator",
            )
        except RLMRatificationRequired as exc:
            await broadcast_emit(
                broadcaster,
                event.investigation_id,
                InvestigationFailedPayload(
                    phase=1,
                    reason=str(exc),
                    last_completed_phase=None,
                ),
                role="rlm_orchestrator",
                policy_id="rlm-orchestrator/ratification-gate",
            )
            return

        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            session_started_payload(session),
            role="rlm_orchestrator",
            policy_id="rlm-orchestrator/bootstrap",
        )

        iterate_session(
            session,
            summary=(
                "RLM investigation lane accepted the open-ended question "
                f"and initialized root planning for: {req.question}"
            ),
            cost_usd=Decimal("0.00"),
        )
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            iteration_payload(session, session.iterations[-1]),
            role="rlm_orchestrator",
            policy_id="rlm-orchestrator/bootstrap",
        )

        final_summary = (
            "RLM investigation bootstrap completed; root-tool planning is "
            "initialized for the next orchestration slice."
        )
        session.complete(final_summary=final_summary)
        await broadcast_emit(
            broadcaster,
            event.investigation_id,
            session_completed_payload(session, final_summary=final_summary),
            role="rlm_orchestrator",
            policy_id="rlm-orchestrator/bootstrap",
        )

    return handle_investigation_start


def register_handlers(broadcaster: EventBroadcaster) -> None:
    broadcaster.register_handler(
        _action_value(ActionType.INVESTIGATION_START_REQUESTED),
        make_rlm_investigation_handler(broadcaster),
    )


__all__ = ["make_rlm_investigation_handler", "register_handlers"]
