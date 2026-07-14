"""Parameter Extractor role bridge (Sprint 7 day 2 — third
orchestrate.py role bridge, third of four).

Subscribes to ``parameter_extract.requested`` events. Per request:

1. Renders the parameter_extractor prompt with the request's
   ``evidence_block`` placeholder.
2. Dispatches the ``parameter_extractor`` role (Flash tier).
3. Parses + validates the response with the discipline-enforcing
   parser shipped in this slice.
4. Converts the parsed parameters into ``ConstraintSpec`` records
   via ``roles.parameter_extractor.parameters_to_constraints`` so
   the Day 3 constraint-loop machinery reads typed constraint input
   directly from the trajectory.
5. Emits ``PARAMETER_EXTRACT_DELIVERED`` carrying BOTH the raw
   ``parameters`` list (preserved for RL trajectory mining) AND the
   derived ``constraints`` list (consumed by the constraint loop).

Failure-mode discipline (mirrors decomposer + evidence_retriever):

- Validation failure on parse → empty Delivered (parameters=[],
  constraints=[]). The trajectory shows the request was answered;
  the empty constraints list means the constraint loop has nothing
  to gate against (which is the correct safe behavior — no
  ungated constraints).
- Provider unavailable → same fallback shape, policy_id stamped
  ``parameter-extractor-fallback/no-provider``.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Awaitable, Callable
from typing import Any

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.parameter_extractor import (  # noqa: E402
    ParameterExtractResult,
    ParameterValidationError,
    parameters_to_constraints,
    parse_parameter_extractor_response,
    render_full_prompt,
)
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    MetricValue,
    Parameter,
    ParameterExtractDeliveredPayload,
    ParameterExtractRequestedPayload,
)

from .broadcast import EventBroadcaster  # noqa: E402 — after the sys.path bootstrap above
from .research_tier_routing import persisted_research_tier_override  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_to_parameter_payloads(
    result: ParameterExtractResult,
) -> list[Parameter]:
    """Convert parser dataclasses to the Pydantic shapes the payload
    expects. The MetricValue ``value`` field is heterogeneous Any —
    pass through verbatim."""
    out: list[Parameter] = []
    for p in result.parameters:
        out.append(Parameter(
            semantic_anchor=p.semantic_anchor,
            metric_value=MetricValue(
                value_type=p.metric_value.value_type,  # type: ignore[arg-type]
                value=p.metric_value.value,
                unit=p.metric_value.unit,
            ),
            qualitative_descriptor=p.qualitative_descriptor,
            evidence_status=p.evidence_status,  # type: ignore[arg-type]
            source_chunk_ids=list(p.source_chunk_ids),
            constraint_strictness=p.constraint_strictness,  # type: ignore[arg-type]
        ))
    return out


def _empty_delivered_payload() -> ParameterExtractDeliveredPayload:
    """Fallback when dispatch/parse fails. Empty parameter +
    constraint lists — the constraint loop reads zero constraints
    and gates on nothing, which is the correct safe behavior."""
    return ParameterExtractDeliveredPayload(
        parameters=[],
        constraints=[],
    )


def _extract_canonical_chunk_ids(evidence_block: str) -> tuple[str, ...]:
    """Return chunk ids present in the JSON-stringified evidence block.

    The upstream Evidence Retriever emits nested JSON with ``chunk_ids`` lists.
    Keep this parser structural: if the block is not JSON, do not regex-guess
    citations from prose.
    """
    try:
        evidence = json.loads(evidence_block)
    except json.JSONDecodeError:
        return ()

    out: list[str] = []
    seen: set[str] = set()

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if key in {"chunk_id", "chunk_ids", "source_chunk_ids"}:
                    collect(item)
                else:
                    visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    def collect(value: Any) -> None:
        if isinstance(value, str):
            cleaned = value.strip()
            if cleaned and cleaned not in seen:
                out.append(cleaned)
                seen.add(cleaned)
        elif isinstance(value, list):
            for item in value:
                collect(item)

    visit(evidence)
    return tuple(out)


# ---------------------------------------------------------------------------
# Dispatch + parse
# ---------------------------------------------------------------------------


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    canonical_chunk_ids: tuple[str, ...] = (),
) -> tuple[ParameterExtractResult | None, str]:
    """Run one parameter_extractor dispatch + parse. Returns
    ``(result, policy_id)`` on success, ``(None, fallback_id)`` on
    failure."""
    provider_override, model_override = persisted_research_tier_override(
        event.investigation_id,
    )
    try:
        result = dispatch(
            prompt,
            "parameter_extractor",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
            provider_override=provider_override,
            model_override=model_override,
        )
        response_text = result.text
        policy_id = f"{result.provider}/{result.model}"
    except (ProviderError, KeyError) as exc:
        print(
            f"parameter_extractor.handle: dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, "parameter-extractor-fallback/no-provider"

    try:
        parsed = parse_parameter_extractor_response(
            response_text,
            canonical_chunk_ids=canonical_chunk_ids,
        )
        return parsed, policy_id
    except ParameterValidationError as exc:
        print(
            f"parameter_extractor.handle: parse failed — {exc}",
            flush=True,
        )
        return None, policy_id


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_parameter_extractor_handler(
    broadcaster: EventBroadcaster,
) -> Callable[[Event], Awaitable[None]]:
    """Build the handler closed over a broadcaster. Registered against
    ``ActionType.PARAMETER_EXTRACT_REQUESTED``."""

    async def handle_parameter_extract_request(event: Event) -> None:
        if not isinstance(event.payload, ParameterExtractRequestedPayload):
            return  # defensive — handler keyed on action_type
        req = event.payload
        evidence_block = req.evidence_block or ""
        canonical_chunk_ids = _extract_canonical_chunk_ids(evidence_block)

        prompt = render_full_prompt(evidence_block=evidence_block)
        result, policy_id = _dispatch_and_parse(
            prompt,
            event,
            canonical_chunk_ids=canonical_chunk_ids,
        )

        if result is None:
            await _emit_delivered(
                event,
                payload=_empty_delivered_payload(),
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
            return

        parameters_payload = _result_to_parameter_payloads(result)
        constraints_payload = parameters_to_constraints(result.parameters)
        await _emit_delivered(
            event,
            payload=ParameterExtractDeliveredPayload(
                parameters=parameters_payload,
                constraints=constraints_payload,
            ),
            policy_id=policy_id,
            broadcaster=broadcaster,
        )

    return handle_parameter_extract_request


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


async def _emit_delivered(
    event: Event,
    *,
    payload: ParameterExtractDeliveredPayload,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        payload,
        parent_event_id=event.event_id,
        role="parameter_extractor",
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: str | None,
    broadcaster: EventBroadcaster,
) -> None:
    """Look up the just-emitted event and broadcast so subscribed WS
    clients see the parameter extraction in real time."""
    if emitted_event_id is None:
        return
    for row in reversed(trajectory(event.investigation_id)):
        if row.get("event_id") == emitted_event_id:
            try:
                emitted = Event.model_validate(row)
                await broadcaster.broadcast(emitted)
            except Exception:  # pragma: no cover — never block on broadcast
                pass
            return


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_handlers(broadcaster: EventBroadcaster) -> None:
    """Wire the parameter_extractor handler into the broadcaster.
    Called once at app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.PARAMETER_EXTRACT_REQUESTED.value,
        make_parameter_extractor_handler(broadcaster),
    )
