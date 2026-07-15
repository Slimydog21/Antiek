"""Evidence Retriever role bridge (Sprint 7 day 1 — second
orchestrate.py role bridge).

Subscribes to ``evidence.retrieve.requested`` events. For each request:

1. Renders the evidence_retriever prompt with the request's payload
   fields (sub_question + category + evidence_type_required + top_k +
   chunks_block + subgraph_block).
2. Dispatches the ``evidence_retriever`` role (Flash tier per
   ``substrate/dispatch/config.yaml``).
3. Parses + validates the response with the closed-vocabulary
   parser shipped in Sprint 6 day 4-5.
4. Emits ``EVIDENCE_RETRIEVE_DELIVERED`` with the parsed structured
   output.

Failure-mode discipline (mirrors decomposer + grounder):

- Validation failure on parse → empty Delivered with
  ``insufficient_evidence=True``, ``supporting_claims=[]``,
  ``answer="(parse_failed)"``. A validation marker is logged to
  stderr for forensics.
- Provider unavailable → same fallback shape, policy_id stamped
  ``evidence-retriever-fallback/no-provider``.

The request payload carries ``chunks_block`` and ``subgraph_block``
verbatim so the role's input is fully reconstructable from the
trajectory — no opaque retrieval-time DB lookup needed at replay.
The bridge that PRODUCES the request is the substrate consumer's
responsibility (Sprint 8 will wire it from the constraint loop +
synthesizer chain).
"""

from __future__ import annotations

import os
import re
import sys
from collections.abc import Awaitable, Callable

# Direct import — interfaces/research/api/ depends on substrate + roles.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from roles.evidence_retriever import (  # noqa: E402
    EvidenceResult,
    EvidenceValidationError,
    parse_evidence_response,
    render_full_prompt,
)
from substrate.dispatch import ProviderError, dispatch  # noqa: E402
from substrate.event_log import emit_typed, trajectory  # noqa: E402
from substrate.schemas import (  # noqa: E402
    ActionType,
    Event,
    EvidenceRetrieveDeliveredPayload,
    EvidenceRetrieveRequestedPayload,
    EvidentiaryGap,
    SupportingClaim,
)

from .broadcast import EventBroadcaster  # noqa: E402 — after the sys.path bootstrap above

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _result_to_payload_lists(
    result: EvidenceResult,
) -> tuple[list[SupportingClaim], list[EvidentiaryGap]]:
    """Convert the parser's frozen dataclasses to the Pydantic shapes
    the ``EvidenceRetrieveDelivered`` payload expects."""
    claims = [
        SupportingClaim(
            claim=c.claim,
            evidence_type=c.evidence_type,  # type: ignore[arg-type]
            chunk_ids=list(c.chunk_ids),
            edge_ids=list(c.edge_ids),
            source_tier_min=c.source_tier_min,
            confidence=c.confidence,  # type: ignore[arg-type]
            confidence_basis=c.confidence_basis,
        )
        for c in result.supporting_claims
    ]
    gaps = [
        EvidentiaryGap(
            gap_description=g.gap_description,
            additional_retrieval_suggested=g.additional_retrieval_suggested,
        )
        for g in result.evidentiary_gaps
    ]
    return claims, gaps


def _empty_delivered_payload(
    sub_question: str, answer: str = "(parse_failed)",
) -> EvidenceRetrieveDeliveredPayload:
    """Fallback shape when the dispatch / parser fails. The
    trajectory shows the request was answered (the bridge ran), the
    answer is empty + ``insufficient_evidence=True``, downstream can
    tell from the flag that this was a failure shape."""
    return EvidenceRetrieveDeliveredPayload(
        sub_question=sub_question,
        answer=answer,
        supporting_claims=[],
        evidentiary_gaps=[],
        insufficient_evidence=True,
    )


def _extract_chunk_ids_from_block(chunks_block: str) -> tuple[str, ...]:
    """Extract canonical chunk ids from rendered chunk lines.

    Two production renderers exist: the bridge fixture/legacy form
    ``[chunk_id] ...`` and Loop One's live ``### chunk_id: chunk_id`` heading.
    Only those structural line prefixes count; IDs mentioned later in prose are
    never accepted as provenance candidates.
    """
    out: list[str] = []
    seen: set[str] = set()
    at_record_boundary = True
    for raw_line in chunks_block.splitlines():
        line = raw_line.strip()
        if line == "---":
            at_record_boundary = True
            continue
        if not at_record_boundary:
            continue
        chunk_id = ""
        bracket = re.fullmatch(r"\[([^\]]+)\](?:\s.*)?", line)
        if bracket is not None:
            chunk_id = bracket.group(1)
        else:
            heading = re.fullmatch(r"### chunk_id:\s+([^\s]+)", line)
            if heading is not None:
                chunk_id = heading.group(1)
        if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/-]{0,255}", chunk_id) is None:
            continue
        if chunk_id and chunk_id not in seen:
            out.append(chunk_id)
            seen.add(chunk_id)
        at_record_boundary = False
    return tuple(out)


# ---------------------------------------------------------------------------
# Dispatch + parse helper
# ---------------------------------------------------------------------------


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    sub_question: str,
    canonical_chunk_ids: tuple[str, ...] = (),
) -> tuple[EvidenceResult | None, str]:
    """Run one evidence_retriever dispatch + parse. Returns
    ``(EvidenceResult, policy_id)`` on success, ``(None, fallback_id)``
    on dispatch or parse failure."""
    try:
        result = dispatch(
            prompt,
            "evidence_retriever",
            investigation_id=event.investigation_id,
            parent_event_id=event.event_id,
        )
        response_text = result.text
        policy_id = f"{result.provider}/{result.model}"
    except (ProviderError, KeyError) as exc:
        print(
            f"evidence_retriever.handle: dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, "evidence-retriever-fallback/no-provider"

    try:
        parsed = parse_evidence_response(
            response_text,
            expected_sub_question=sub_question,
            canonical_chunk_ids=canonical_chunk_ids,
        )
        return parsed, policy_id
    except EvidenceValidationError as exc:
        print(
            f"evidence_retriever.handle: parse failed — {exc}",
            flush=True,
        )
        return None, policy_id


# ---------------------------------------------------------------------------
# Handler factory
# ---------------------------------------------------------------------------


def make_evidence_retriever_handler(
    broadcaster: EventBroadcaster,
) -> Callable[[Event], Awaitable[None]]:
    """Build the handler closed over a broadcaster. Registered against
    ``ActionType.EVIDENCE_RETRIEVE_REQUESTED``."""

    async def handle_evidence_retrieve_request(event: Event) -> None:
        if not isinstance(event.payload, EvidenceRetrieveRequestedPayload):
            return  # defensive — handler keyed on action_type
        req = event.payload
        sub_question = req.sub_question.strip()
        if not sub_question:
            return  # nothing to retrieve
        canonical_chunk_ids = _extract_chunk_ids_from_block(req.chunks_block)

        prompt = render_full_prompt(
            sub_question=sub_question,
            category=req.category,
            evidence_type_required=req.evidence_type_required,
            top_k=req.top_k,
            chunks_block=req.chunks_block,
            subgraph_block=req.subgraph_block,
        )

        result, policy_id = _dispatch_and_parse(
            prompt,
            event,
            sub_question=sub_question,
            canonical_chunk_ids=canonical_chunk_ids,
        )
        if result is None:
            await _emit_delivered(
                event,
                payload=_empty_delivered_payload(sub_question=sub_question),
                policy_id=policy_id,
                broadcaster=broadcaster,
            )
            return

        claims, gaps = _result_to_payload_lists(result)
        await _emit_delivered(
            event,
            payload=EvidenceRetrieveDeliveredPayload(
                sub_question=result.sub_question,
                answer=result.answer,
                supporting_claims=claims,
                evidentiary_gaps=gaps,
                insufficient_evidence=result.insufficient_evidence,
            ),
            policy_id=policy_id,
            broadcaster=broadcaster,
        )

    return handle_evidence_retrieve_request


# ---------------------------------------------------------------------------
# Emit helpers
# ---------------------------------------------------------------------------


async def _emit_delivered(
    event: Event,
    *,
    payload: EvidenceRetrieveDeliveredPayload,
    policy_id: str,
    broadcaster: EventBroadcaster,
) -> None:
    eid = emit_typed(
        event.investigation_id,
        payload,
        parent_event_id=event.event_id,
        role="evidence_retriever",
        policy_id=policy_id,
    )
    await _broadcast_emitted(event, eid, broadcaster)


async def _broadcast_emitted(
    event: Event,
    emitted_event_id: str | None,
    broadcaster: EventBroadcaster,
) -> None:
    """Look up the just-emitted event and broadcast so subscribed WS
    clients see the evidence pack in real time."""
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
    """Wire the evidence_retriever handler into the broadcaster.
    Called once at app startup from ``app.create_app``."""
    broadcaster.register_handler(
        ActionType.EVIDENCE_RETRIEVE_REQUESTED.value,
        make_evidence_retriever_handler(broadcaster),
    )
