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

Failure-mode discipline (mirrors decomposer + synthesizer + grounder):

- ``finish_reason=length`` → one retry at ``max_tokens=16384``.
- Validation failure on parse → one self-repair re-dispatch with the
  error prepended; if that also fails → empty Delivered with
  ``insufficient_evidence=True``, ``supporting_claims=[]``,
  ``answer="(parse_failed)"``. A validation marker is logged to
  stderr for forensics.
- Provider unavailable → same fallback shape, policy_id stamped
  ``evidence-retriever-fallback/no-provider``.
- Parser coerces ``answer: null`` / missing → ``""`` (Mini dogfood).

The request payload carries ``chunks_block`` and ``subgraph_block``
verbatim so the role's input is fully reconstructable from the
trajectory — no opaque retrieval-time DB lookup needed at replay.
The bridge that PRODUCES the request is the substrate consumer's
responsibility (Sprint 8 will wire it from the constraint loop +
synthesizer chain).
"""

from __future__ import annotations

import asyncio
import hashlib
import os
import re
import sys
from collections.abc import Awaitable, Callable
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
from substrate.dispatch import dispatch  # noqa: E402
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


# First-call output budget. 8192 covers Mini deepseek stops at ~2–7.7k
# without inviting 90s+ verbose completions. Length-retry uses the same
# budget as safety (prompt HARD LIMIT should make length rare).
EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS = 8192


def _dispatch_once(
    prompt: str,
    event: Event,
    *,
    sub_question: str,
    semantic_call_id: str | None,
    attempt: int,
    max_tokens: int | None = None,
) -> tuple[str, str, str | None]:
    """One provider call. Returns ``(text, policy_id, finish_reason)``
    or raises ``ProviderError`` / ``KeyError``."""
    from .research_owner_dispatch import dispatch_loop_one

    result = None
    if attempt == 0:
        result = dispatch_loop_one(
            prompt,
            "evidence_retriever",
            investigation_id=event.investigation_id,
            semantic_call_id=semantic_call_id
            or "phase2:" + hashlib.sha256(sub_question.encode()).hexdigest()[:16],
            attempt=attempt,
            evidence_request=event.payload,
        )
    if result is None:
        kwargs: dict[str, Any] = {
            "investigation_id": event.investigation_id,
            "parent_event_id": event.event_id,
        }
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        # Phase-2 wall ≈ max(latency) under PHASE_2_MAX_CONCURRENCY=4.
        # Prefer Xiaomi MiMo for evidence when registered — Mini bench
        # ~14s vs deepseek ~24s on compact JSON (still falls through the
        # flash chain if Xiaomi errors).
        try:
            from substrate.dispatch.router import get_provider

            get_provider("xiaomi")
            kwargs["provider_override"] = "xiaomi"
            kwargs["model_override"] = "mimo-v2.5-pro"
        except KeyError:
            pass
        result = dispatch(prompt, "evidence_retriever", **kwargs)
    return result.text, f"{result.provider}/{result.model}", getattr(
        result, "finish_reason", None
    )


def _dispatch_and_parse(
    prompt: str,
    event: Event,
    *,
    sub_question: str,
    semantic_call_id: str | None = None,
    canonical_chunk_ids: tuple[str, ...] = (),
) -> tuple[EvidenceResult | None, str]:
    """Run evidence_retriever dispatch + parse with Mini dogfood retries.

    First call uses ``EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS`` (8192) plus
    optional Xiaomi primary (faster flash on Mini). Length-retry stays
    safety; synthesizer-style self-repair still runs on parse failure.
    """
    try:
        response_text, policy_id, finish = _dispatch_once(
            prompt,
            event,
            sub_question=sub_question,
            semantic_call_id=semantic_call_id,
            attempt=0,
            max_tokens=EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS,
        )
        if finish == "length":
            # Safety net — happy path should stop on first call at 16384.
            print(
                "evidence_retriever.handle: finish_reason=length — "
                f"retrying once with max_tokens={EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS}",
                flush=True,
            )
            response_text, policy_id, _finish = _dispatch_once(
                prompt,
                event,
                sub_question=sub_question,
                semantic_call_id=semantic_call_id,
                attempt=1,
                max_tokens=EVIDENCE_RETRIEVER_OUTPUT_MAX_TOKENS,
            )
    except Exception as exc:  # ProviderError/KeyError/OwnerByot*/etc.
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
        first_error = exc  # keep past except-scope (Py3 deletes the as-target)
        print(
            f"evidence_retriever.handle: parse failed — {first_error} — "
            "attempting one self-repair",
            flush=True,
        )

    repair_prefix = (
        "Your previous response failed the substrate's structural "
        "contract with the following error:\n\n"
        f"    {first_error!s}\n\n"
        "This is your one and only chance to fix it. Produce a single "
        "JSON object that satisfies the contract. ``answer`` MUST be a "
        'JSON string (use "" if insufficient_evidence is true — never '
        "null). ``supporting_claims`` and ``evidentiary_gaps`` MUST be "
        "arrays. ``insufficient_evidence`` MUST be a JSON boolean.\n\n"
        "----\n\n"
    )
    try:
        retry_text, retry_policy, _ = _dispatch_once(
            repair_prefix + prompt,
            event,
            sub_question=sub_question,
            semantic_call_id=semantic_call_id,
            attempt=1,
        )
    except Exception as exc:  # ProviderError/KeyError/OwnerByot*/etc.
        print(
            f"evidence_retriever.handle: self-repair dispatch failed — "
            f"{type(exc).__name__}: {exc}",
            flush=True,
        )
        return None, policy_id

    try:
        parsed = parse_evidence_response(
            retry_text,
            expected_sub_question=sub_question,
            canonical_chunk_ids=canonical_chunk_ids,
        )
        return parsed, retry_policy
    except EvidenceValidationError as exc:
        print(
            f"evidence_retriever.handle: parse failed after self-repair — {exc}",
            flush=True,
        )
        return None, retry_policy



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

        result, policy_id = await asyncio.to_thread(
            _dispatch_and_parse,
            prompt,
            event,
            sub_question=sub_question,
            semantic_call_id=getattr(req, "owner_semantic_call_id", None),
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
