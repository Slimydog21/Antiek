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

import json
import os
import re
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

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

_BRACKETED_CHUNK_LINE_RE = re.compile(
    r"(?im)^\s*\[([A-Za-z0-9][A-Za-z0-9_.:/#@-]*)\]\s+tier\s*="
)
_CHUNK_ID_LINE_RE = re.compile(
    r"(?im)^\s*(?:#{1,6}\s*)?chunk_id\s*:\s*([^\s|]+)"
)


@dataclass(frozen=True)
class CanonicalEvidenceRefs:
    chunk_ids: tuple[str, ...] | None = None
    edge_ids: tuple[str, ...] | None = None


def _canonical_refs_from_request(
    req: EvidenceRetrieveRequestedPayload,
) -> CanonicalEvidenceRefs:
    chunks = _load_json_block(req.chunks_block)
    subgraph = _load_json_block(req.subgraph_block)
    chunk_ids = _ordered_unique(
        [
            *_collect_values_for_keys(
                chunks,
                {"chunk_id", "chunk_ids", "source_chunk_ids"},
            ),
            *_chunk_ids_from_text(req.chunks_block),
        ]
    )
    edge_ids = _ordered_unique(
        _collect_values_for_keys(subgraph, {"edge_id", "edge_ids"})
    )
    return CanonicalEvidenceRefs(
        chunk_ids=chunk_ids or None,
        edge_ids=edge_ids or None,
    )


def _load_json_block(raw: str) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _collect_values_for_keys(value: Any, keys: set[str]) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys:
                refs.extend(_strings_from_value(child))
            else:
                refs.extend(_collect_values_for_keys(child, keys))
    elif isinstance(value, list):
        for child in value:
            refs.extend(_collect_values_for_keys(child, keys))
    return refs


def _strings_from_value(value: Any) -> list[str]:
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    if isinstance(value, list):
        out: list[str] = []
        for child in value:
            out.extend(_strings_from_value(child))
        return out
    return []


def _chunk_ids_from_text(raw: str) -> list[str]:
    refs = [match.group(1).strip() for match in _CHUNK_ID_LINE_RE.finditer(raw)]
    refs.extend(
        match.group(1).strip() for match in _BRACKETED_CHUNK_LINE_RE.finditer(raw)
    )
    return [ref for ref in refs if ref]


def _ordered_unique(values: list[str]) -> tuple[str, ...]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return tuple(out)


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

    The request contract renders chunks as ``[chunk_id] ...`` lines. Only that
    structural prefix counts; IDs mentioned later in prose are not accepted as
    provenance candidates.
    """
    out: list[str] = []
    seen: set[str] = set()
    for raw_line in chunks_block.splitlines():
        line = raw_line.strip()
        if not line.startswith("[") or "]" not in line:
            continue
        chunk_id = line[1:].split("]", 1)[0].strip()
        if chunk_id and chunk_id not in seen:
            out.append(chunk_id)
            seen.add(chunk_id)
    return tuple(out)


# ---------------------------------------------------------------------------
# Dispatch + parse helper
# ---------------------------------------------------------------------------


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    sub_question: str,
    canonical_refs: CanonicalEvidenceRefs,
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
            canonical_chunk_ids=canonical_refs.chunk_ids,
            canonical_edge_ids=canonical_refs.edge_ids,
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
        canonical_refs = _canonical_refs_from_request(req)

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
            canonical_refs=canonical_refs,
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
