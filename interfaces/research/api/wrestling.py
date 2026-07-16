"""Backend wrestling bridge — the proto-note_taker (Sprint 2 day 2-3).

Subscribes to ``distillation.requested`` events. For each request:

1. Resolves the source-region text by walking the trajectory for the
   matching ``document.region_selected`` event.
2. Builds a tiny context pack (param_version_stamp + phase_metadata +
   the region text as the session layer). No graph evidence and no
   skill content yet — those wire in once the substrate has them.
3. Dispatches a ``synthesizer`` role call asking the model to emit
   structured JSON ``Claim[]`` + a rendered prose summary.
4. Parses the JSON; falls back to a single ``unknown``-confidence claim
   carrying the raw response if parsing fails (loudly, so the operator
   sees a malformed-response event in the log).
5. Emits ``distillation.delivered`` with the structured payload and
   broadcasts to any subscribed WebSocket clients.

The real wrestling roles (``challenger``, ``grounder``, ``note_taker``)
arrive in Sprint 4 with graph access and proper attribution. Until
then this handler is the closed-loop demonstration that proves the
seam works end-to-end: human selects PDF text → posts a question →
sees structured claims stream into the notes panel.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import os
import sys
import uuid
from pathlib import Path
from typing import Any, Protocol

# Direct import — interfaces/research/api/ depends on substrate.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from datetime import UTC, datetime  # noqa: E402

from processing.embedding import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from runtime.db_lock import connect_write  # noqa: E402
from runtime.research_runner.distillation_execution import (  # noqa: E402
    ApprovedDistillationTicket,
    DistillationApprovalRequirement,
    DistillationExecutionResult,
)
from runtime.research_runner.provider_gateway import (  # noqa: E402
    DispatchIneligible,
    ProviderOutcomeUnknown,
)
from substrate.constants import ANTIEK_PARAM_VERSION  # noqa: E402
from substrate.context_pack import (  # noqa: E402
    LayerSource,
    WorkingMemoryIntegrityError,
    assemble_context_pack,
    build_working_memory_layer,
)
from substrate.distillation_dispatch import (  # noqa: E402
    CommandSnapshot,
    CommandState,
    DistillationDispatchJournal,
)
from substrate.event_log import (  # noqa: E402
    PhysicalTrajectoryError,
    emit_typed,
    iter_physical_events,
    trajectory,
)
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.schemas import (  # noqa: E402
    EVENT_SCHEMA_VERSION,
    ActionType,
    Claim,
    ConfidenceLevel,
    DistillationApprovalRequiredPayload,
    DistillationDeliveredPayload,
    DistillationRequestedPayload,
    DocumentLoadedPayload,
    DocumentRegionSelectedPayload,
    Event,
)

from .broadcast import EventBroadcaster  # noqa: E402

# The role-tail prompt appended after the context pack. Asks for
# structured JSON; the parser tolerates loose formatting (Markdown code
# fences, leading prose) by extracting the first valid JSON object.
ROLE_PROMPT_TAIL = """
You are reading text the user just highlighted in a document. The user
has asked a question about it. Respond with a JSON object only — no
prose before or after, no markdown fences:

{
  "rendered_text": "<2-4 sentence summary suitable for direct display>",
  "claims": [
    {"text": "<one factual claim>",
     "confidence": "high" | "moderate" | "low" | "unknown"}
  ]
}

Rules:
- Every claim must be directly supported by the source text. Prefer
  "moderate" if you are paraphrasing; "low" if interpolating.
- Quote-extract before you paraphrase. If the source contradicts itself,
  emit two claims at "moderate" rather than averaging.
- Maximum 8 claims. Be terse — the model is the one paying for the
  output tokens, and the user reads the rendered_text first.
""".strip()


# Confidence values mirror substrate.constants.CONFIDENCE_LEVELS.
_VALID_CONFIDENCE = {"high", "moderate", "low", "unknown"}


def _normalize_confidence(raw: Any) -> ConfidenceLevel:
    """Coerce a raw confidence value to one of the four valid levels.
    Unknown or missing input returns ``"unknown"`` — the schema-defined
    "I don't know" value, which downstream cohort analysis already
    treats as uncalibrated."""
    if isinstance(raw, str) and raw.lower() in _VALID_CONFIDENCE:
        return raw.lower()  # type: ignore[return-value]
    return "unknown"


def _sha256_prefix(s: str, n: int = 12) -> str:
    return "sha256:" + hashlib.sha256(s.encode("utf-8")).hexdigest()[:n]


def _new_claim_id() -> str:
    return "c-" + uuid.uuid4().hex[:12]


def _dispatch_policy_digest() -> str:
    config_path = Path(_PKG_ROOT) / "substrate" / "dispatch" / "config.yaml"
    return hashlib.sha256(config_path.read_bytes()).hexdigest()


def _dispatch_binding(event: Event, full_prompt: str) -> dict[str, object]:
    return {
        "schema": "antiek.distillation-dispatch-binding.v1",
        "request_event": event.model_dump(mode="json"),
        "prompt_sha256": hashlib.sha256(full_prompt.encode("utf-8")).hexdigest(),
        "role": "synthesizer",
        "route_policy_sha256": _dispatch_policy_digest(),
        "spend_projection": "unavailable_on_legacy_wrestling_route",
    }


class DistillationExecutionAuthority(Protocol):
    def prepare(
        self, request_event_id: str, prompt: str
    ) -> DistillationApprovalRequirement | ApprovedDistillationTicket: ...

    def execute(
        self, ticket: ApprovedDistillationTicket
    ) -> DistillationExecutionResult: ...


def _approval_event_id(request_event_id: str) -> str:
    digest = hashlib.sha256(request_event_id.encode("utf-8")).hexdigest()[:32]
    return "evt-distill-approval-" + digest


async def _publish_distillation_approval_required(
    snapshot: CommandSnapshot,
    requirement: DistillationApprovalRequirement,
    broadcaster: EventBroadcaster,
) -> None:
    payload = DistillationApprovalRequiredPayload(
        request_event_id=snapshot.request_event_id,
        reason=requirement.reason,
        chain_id=requirement.chain_id,
        manifest_sha256=requirement.manifest_sha256,
        ceiling_cents=requirement.ceiling_cents,
        currency=requirement.currency,
        maximum_chain_exposure_cents=requirement.maximum_chain_exposure_cents,
    )
    event_id = _approval_event_id(snapshot.request_event_id)
    expected = Event(
        event_id=event_id,
        investigation_id=snapshot.investigation_id,
        role="synthesizer",
        action_type=payload.action_type,
        payload=payload,
        parent_event_id=snapshot.request_event_id,
        policy_id="wrestling-spend/approval-required",
        param_version=ANTIEK_PARAM_VERSION,
        schema_version=EVENT_SCHEMA_VERSION,
        emitted_at=datetime.now(UTC),
        document_id=snapshot.document_id,
    )
    existing = _exact_physical_event(snapshot.investigation_id, expected)
    if existing is None:
        emitted = emit_typed(
            snapshot.investigation_id,
            payload,
            parent_event_id=snapshot.request_event_id,
            role="synthesizer",
            document_id=snapshot.document_id,
            policy_id="wrestling-spend/approval-required",
            event_id=event_id,
            idempotent=True,
            strict_write=True,
        )
        if emitted is None:
            return
        existing = _exact_physical_event(snapshot.investigation_id, expected)
        if existing is None:
            raise PhysicalTrajectoryError("approval-required event is not physically visible")
    with contextlib.suppress(Exception):
        await broadcaster.broadcast(existing)


async def _publish_distillation_delivery(
    snapshot: CommandSnapshot,
    journal: DistillationDispatchJournal,
    broadcaster: EventBroadcaster,
) -> None:
    payload = snapshot.delivery_payload
    if payload is None or snapshot.policy_id is None:
        raise RuntimeError("completed distillation command has no durable delivery")
    expected = _expected_delivery_event(snapshot, payload, snapshot.policy_id)
    existing_event = _exact_physical_event(snapshot.investigation_id, expected)
    if existing_event is None:
        emitted = emit_typed(
            snapshot.investigation_id,
            payload,
            parent_event_id=snapshot.request_event_id,
            role="synthesizer",
            document_id=snapshot.document_id,
            policy_id=snapshot.policy_id,
            event_id=snapshot.delivery_event_id,
            idempotent=True,
            strict_write=True,
        )
        if emitted is None:
            return
        existing_event = _exact_physical_event(snapshot.investigation_id, expected)
        if existing_event is None:
            raise PhysicalTrajectoryError("strict delivery append is not physically visible")
    if snapshot.state is CommandState.COMPLETED:
        journal.mark_delivered(snapshot.request_event_id)
    if existing_event is not None:
        with contextlib.suppress(Exception):  # durable delivery outranks broadcast
            await broadcaster.broadcast(existing_event)


async def _publish_ambiguous_distillation_notice(
    snapshot: CommandSnapshot,
    broadcaster: EventBroadcaster,
) -> None:
    text = (
        "Synthesizer dispatch outcome is unknown. "
        "No automatic retry was attempted."
    )
    payload = DistillationDeliveredPayload(
        request_event_id=snapshot.request_event_id,
        claims=[
            Claim(
                claim_id="c-ambiguous-" + _sha256_prefix(snapshot.request_event_id, 12)[7:],
                text=text,
                confidence="unknown",
                attribution_region_ids=[],
            )
        ],
        rendered_text=text,
        rendered_text_hash=_sha256_prefix(text),
        token_count=0,
    )
    expected = _expected_delivery_event(
        snapshot, payload, "wrestling-fallback/ambiguous"
    )
    existing_event = _exact_physical_event(snapshot.investigation_id, expected)
    if existing_event is None:
        emitted = emit_typed(
            snapshot.investigation_id,
            payload,
            parent_event_id=snapshot.request_event_id,
            role="synthesizer",
            document_id=snapshot.document_id,
            policy_id="wrestling-fallback/ambiguous",
            event_id=snapshot.delivery_event_id,
            idempotent=True,
            strict_write=True,
        )
        if emitted is None:
            return
        existing_event = _exact_physical_event(snapshot.investigation_id, expected)
        if existing_event is None:
            raise PhysicalTrajectoryError("strict ambiguity append is not physically visible")
    if existing_event is not None:
        with contextlib.suppress(Exception):  # durable notice outranks broadcast
            await broadcaster.broadcast(existing_event)


def _expected_delivery_event(
    snapshot: CommandSnapshot,
    payload: DistillationDeliveredPayload,
    policy_id: str,
) -> Event:
    return Event(
        event_id=snapshot.delivery_event_id,
        investigation_id=snapshot.investigation_id,
        role="synthesizer",
        action_type=payload.action_type,
        payload=payload,
        parent_event_id=snapshot.request_event_id,
        policy_id=policy_id,
        param_version=ANTIEK_PARAM_VERSION,
        schema_version=EVENT_SCHEMA_VERSION,
        emitted_at=datetime.now(UTC),
        document_id=snapshot.document_id,
    )


def _exact_physical_event(investigation_id: str, expected: Event) -> Event | None:
    """Find one immutable event and reject substitution or corrupt storage."""
    found: Event | None = None
    for row in iter_physical_events(investigation_id):
        if row.get("event_id") != expected.event_id:
            continue
        event = Event.model_validate(row)
        actual = event.model_dump(mode="json", exclude={"emitted_at"})
        identity = expected.model_dump(mode="json", exclude={"emitted_at"})
        if actual != identity:
            raise PhysicalTrajectoryError("distillation delivery identity conflicts with journal")
        found = event
    return found


def _assert_delivery_id_absent(snapshot: CommandSnapshot) -> None:
    for row in iter_physical_events(snapshot.investigation_id):
        if row.get("event_id") == snapshot.delivery_event_id:
            raise PhysicalTrajectoryError(
                "distillation delivery identity exists before provider dispatch"
            )


def _extract_json_object(text: str) -> dict | None:
    """Back-compat alias for ``roles._json_decode.extract_json_object``.
    The body moved to a shared module in Sprint 4 day 4-5 because
    three role-side parsers needed it and importing from wrestling.py
    was creating a circular load path. Existing tests still import
    this name; the alias keeps them working without churn."""
    from roles._json_decode import extract_json_object
    return extract_json_object(text)


def _parse_claims_response(
    text: str,
    *,
    region_id: str | None,
) -> tuple[list[Claim], str]:
    """Parse the model's JSON response into ``(claims, rendered_text)``.

    Failure modes the parser tolerates:
    - Non-JSON response → returns ``([single unknown-confidence claim
      with the raw text], text)``. The downstream consumer sees an
      ``unknown`` claim and can flag for re-dispatch.
    - JSON with no ``claims`` key → empty list + extracted
      ``rendered_text`` if present, else the raw text.
    - Claim missing ``text`` or with non-string text → dropped.

    Attribution defaults to ``[region_id]`` when the model doesn't
    return its own. This matches the proto-handler's invariant: every
    claim in the response is anchored to the source region the user
    highlighted, since that's the only ground we gave the model.
    """
    obj = _extract_json_object(text)
    fallback_attribution = [region_id] if region_id else []

    if obj is None:
        return (
            [
                Claim(
                    claim_id=_new_claim_id(),
                    text=text[:1500],
                    confidence="unknown",
                    attribution_region_ids=fallback_attribution,
                )
            ],
            text[:1500],
        )

    rendered_text = str(obj.get("rendered_text", "")).strip() or text[:1500]

    raw_claims = obj.get("claims", [])
    claims: list[Claim] = []
    if isinstance(raw_claims, list):
        for rc in raw_claims:
            if not isinstance(rc, dict):
                continue
            ct = rc.get("text")
            if not isinstance(ct, str) or not ct.strip():
                continue
            attribution = rc.get("attribution_region_ids")
            if not isinstance(attribution, list):
                attribution = fallback_attribution
            else:
                attribution = [str(a) for a in attribution if isinstance(a, str)]
                if not attribution:
                    attribution = fallback_attribution
            claims.append(
                Claim(
                    claim_id=_new_claim_id(),
                    text=ct.strip(),
                    confidence=_normalize_confidence(rc.get("confidence")),
                    attribution_region_ids=attribution,
                )
            )

    return claims, rendered_text


def _resolve_region_text_from_db(
    db_path: str,
    region_id: str,
) -> str | None:
    """Prefer the chunks table for region text lookup. The wrestling
    bridge's region-handler stores the chunk row keyed by a derived
    chunk_id; we can query for it directly without walking the
    trajectory log. Returns None if no row exists.

    Sprint 3 Day 2-3 added this fast path. The trajectory walk in
    ``_resolve_region_text_from_trajectory`` is still the fallback for
    callers that bypass the graph (e.g. integration tests that don't
    init the DB)."""
    chunk_id = _region_to_chunk_id(region_id)
    try:
        import duckdb
        con = duckdb.connect(db_path, read_only=True)
    except Exception:
        return None
    try:
        row = con.execute(
            "SELECT text FROM chunks WHERE chunk_id = ?", [chunk_id]
        ).fetchone()
    except Exception:
        return None
    finally:
        con.close()
    return row[0] if row else None


def _resolve_region_text_from_trajectory(
    investigation_id: str,
    region_id: str,
) -> str | None:
    """Trajectory-based fallback. Walks the JSONL events for the
    investigation looking for the matching ``document.region_selected``
    event. O(events_per_investigation) — fine for hundreds-of-events
    sessions; if trajectories grow large we'd index this."""
    for row in trajectory(investigation_id):
        payload = row.get("payload") or {}
        if (
            payload.get("action_type") == ActionType.DOCUMENT_REGION_SELECTED.value
            and payload.get("region_id") == region_id
        ):
            return str(payload.get("text_excerpt") or "")
    return None


def _resolve_region_text(
    investigation_id: str,
    document_id: str | None,
    region_id: str | None,
    *,
    db_path: str | None = None,
) -> str | None:
    """Resolve region text. Prefers chunks-table lookup (Sprint 3
    graph integration); falls back to trajectory walk. Returns None
    when neither path produces a match.

    ``document_id`` is currently unused — the region_id is globally
    unique by construction (UUID-based generator on the client). The
    parameter stays for forward-compat with future scoped lookups."""
    if not region_id:
        return None
    if db_path:
        text = _resolve_region_text_from_db(db_path, region_id)
        if text is not None:
            return text
    return _resolve_region_text_from_trajectory(investigation_id, region_id)


def _region_to_chunk_id(region_id: str) -> str:
    """Stable mapping from a frontend-generated region_id to a graph
    chunk_id. Same region → same chunk in the graph; replaying a
    region_selected event is idempotent.

    Keeps the region_id as the chunk_id under a ``chunk-`` prefix so
    the graph SQL stays distinct from other content-addressed ids."""
    # region_id format is "r-<12hex>-<base36 timestamp>" from the
    # reading UI. We strip the leading "r-" and prepend "chunk-" so
    # the schema's chunk_id is grep-able alongside other ids without
    # collisions.
    suffix = region_id[2:] if region_id.startswith("r-") else region_id
    return f"chunk-{suffix}"


def make_distillation_handler(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
    execution_authority: DistillationExecutionAuthority | None = None,
):
    """Build the async handler closed over a broadcaster. The handler
    is registered against ``ActionType.DISTILLATION_REQUESTED``; on
    fire it dispatches a synthesizer call and emits the delivered
    event, then broadcasts the delivered event so subscribed WS
    clients see the response immediately.

    ``db_path`` lets the handler resolve region text from the
    chunks table populated by ``handle_document_region_selected``.
    None falls back to ``default_db_path()``."""
    resolved_db = db_path or default_db_path()

    async def handle_distillation_requested(event: Event) -> None:
        if not isinstance(event.payload, DistillationRequestedPayload):
            return  # defensive — handler is keyed on action_type but check anyway

        request = event.payload

        region_text = _resolve_region_text(
            event.investigation_id, event.document_id, request.region_id,
            db_path=resolved_db,
        )
        if region_text is None and request.region_id:
            region_text = (
                f"(region {request.region_id} not found in trajectory — "
                "the model is answering without source text)"
            )
        elif region_text is None:
            region_text = "(no region scope — whole-document distillation requested)"

        memory_integrity_failed = False
        try:
            memory_layer = build_working_memory_layer(
                iter_physical_events(event.investigation_id),
                investigation_id=event.investigation_id,
                cutoff_event_id=event.event_id,
            )
        except (PhysicalTrajectoryError, WorkingMemoryIntegrityError, ValueError):
            memory_layer = None
            memory_integrity_failed = True

        # The current source and question stay last and outrank working memory.
        layers = [
            LayerSource(
                kind="param_version_stamp",
                source="antiek",
                content=f"ANTIEK_PARAM_VERSION={ANTIEK_PARAM_VERSION}",
            ),
            LayerSource(
                kind="phase_metadata",
                source="loop2.wrestling",
                content=(
                    f"loop=wrestling investigation={event.investigation_id} "
                    f"document={event.document_id or '<none>'} "
                    f"region={request.region_id or '<whole_doc>'}"
                ),
            ),
            *([] if memory_layer is None else [memory_layer]),
            LayerSource(
                kind="session",
                source=f"region:{request.region_id or 'whole_doc'}",
                content=(
                    f"Source text the user highlighted:\n\n{region_text}\n\n"
                    f"---\n\nUser question:\n{request.user_prompt}"
                ),
            ),
        ]

        pack = assemble_context_pack(
            role="synthesizer",
            investigation_id=event.investigation_id,
            layers=layers,
            parent_event_id=event.event_id,
        )

        full_prompt = pack.text + "\n\n" + ROLE_PROMPT_TAIL

        # A working-memory integrity failure is proven pre-dispatch and keeps
        # the existing no-provider fallback. Provider failures are different:
        # without authoritative provider lookup they may represent an accepted
        # paid call, so the durable command becomes ambiguous and emits no
        # fabricated successful delivery.
        if memory_integrity_failed:
            response_text = (
                "Investigation working memory could not be verified. "
                "No synthesizer call was made."
            )
            token_count = 0
            policy_id = "wrestling-fallback/memory-integrity"
        else:
            dispatch_journal = DistillationDispatchJournal(resolved_db)
            async with dispatch_journal.async_execution_guard(event.event_id):
                command = dispatch_journal.reserve(
                    event.event_id,
                    _dispatch_binding(event, full_prompt),
                    investigation_id=event.investigation_id,
                    document_id=event.document_id,
                )
                if command.state is CommandState.SENDING:
                    command = dispatch_journal.mark_ambiguous(event.event_id)
                    await _publish_ambiguous_distillation_notice(command, broadcaster)
                    return
                if command.state is CommandState.AMBIGUOUS:
                    await _publish_ambiguous_distillation_notice(command, broadcaster)
                    return
                if command.state in (CommandState.COMPLETED, CommandState.DELIVERED):
                    await _publish_distillation_delivery(
                        command, dispatch_journal, broadcaster
                    )
                    return
                if execution_authority is None:
                    await _publish_distillation_approval_required(
                        command,
                        DistillationApprovalRequirement(
                            request_event_id=event.event_id,
                            chain_id=None,
                            manifest_sha256=None,
                            ceiling_cents=None,
                            currency=None,
                            maximum_chain_exposure_cents=None,
                            reason="qualified_route_unavailable",
                        ),
                        broadcaster,
                    )
                    return
                try:
                    prepared = await asyncio.to_thread(
                        execution_authority.prepare, event.event_id, full_prompt
                    )
                except DispatchIneligible:
                    await _publish_distillation_approval_required(
                        command,
                        DistillationApprovalRequirement(
                            request_event_id=event.event_id,
                            chain_id=None,
                            manifest_sha256=None,
                            ceiling_cents=None,
                            currency=None,
                            maximum_chain_exposure_cents=None,
                            reason="qualified_route_unavailable",
                        ),
                        broadcaster,
                    )
                    return
                if isinstance(prepared, DistillationApprovalRequirement):
                    await _publish_distillation_approval_required(
                        command, prepared, broadcaster
                    )
                    return
                _assert_delivery_id_absent(command)
                dispatch_journal.mark_sending(event.event_id)
                try:
                    result = await asyncio.to_thread(
                        execution_authority.execute, prepared
                    )
                except (ProviderOutcomeUnknown, DispatchIneligible):
                    command = dispatch_journal.mark_ambiguous(event.event_id)
                    await _publish_ambiguous_distillation_notice(command, broadcaster)
                    return
                claims, rendered_text = _parse_claims_response(
                    result.value.text, region_id=request.region_id
                )
                payload = DistillationDeliveredPayload(
                    request_event_id=event.event_id,
                    claims=claims,
                    rendered_text=rendered_text,
                    rendered_text_hash=_sha256_prefix(rendered_text),
                    token_count=result.value.output_tokens,
                )
                command = dispatch_journal.mark_completed(
                    event.event_id,
                    payload,
                    policy_id=f"{result.provider}/{result.model}",
                )
                await _publish_distillation_delivery(
                    command, dispatch_journal, broadcaster
                )
                return

        claims, rendered_text = _parse_claims_response(
            response_text, region_id=request.region_id
        )

        delivered_event_id = emit_typed(
            event.investigation_id,
            DistillationDeliveredPayload(
                request_event_id=event.event_id,
                claims=claims,
                rendered_text=rendered_text,
                rendered_text_hash=_sha256_prefix(rendered_text),
                token_count=token_count,
            ),
            parent_event_id=event.event_id,
            role="synthesizer",
            document_id=event.document_id,
            policy_id=policy_id,
        )

        # Broadcast the delivered event so WS subscribers (the reading
        # UI) see it without waiting for a polling fetch. Look up the
        # row we just wrote — the trajectory is authoritative.
        if delivered_event_id is None:
            return  # events disabled
        for row in trajectory(event.investigation_id):
            if row.get("event_id") == delivered_event_id:
                try:
                    delivered_event = Event.model_validate(row)
                    await broadcaster.broadcast(delivered_event)
                except Exception:  # pragma: no cover — never block on broadcast
                    pass
                return

    return handle_distillation_requested


def make_document_loaded_handler(
    *,
    db_path: str | None = None,
    broadcaster: EventBroadcaster | None = None,
):
    """Build the handler that mirrors ``document.loaded`` events into a
    row in the documents table. Sprint 3 Day 2-3: the wrestling bridge
    populates the graph organically as the user works.

    Idempotent: same document_id → no-op on re-fire. Source tier
    defaults to 4 (general tech press) when the surface doesn't
    classify; a future iteration will route through
    ``middleware/source_tier/rules.assign_tier_at_ingestion`` once the
    surface emits enough metadata for the rule-based classifier to act."""
    resolved_db = db_path or default_db_path()

    async def handle_document_loaded(event: Event) -> None:
        if not isinstance(event.payload, DocumentLoadedPayload):
            return
        if not event.document_id:
            return  # malformed — the wrestling validator should have rejected

        try:
            ensure_initialized(resolved_db)
            con = connect_write(resolved_db, purpose="wrestling.document_loaded")
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"wrestling.document_loaded: cannot acquire DB write — {exc!r}",
                flush=True,
            )
            return

        p = event.payload
        try:
            insert_document(
                con,
                document_id=event.document_id,
                source_tier=4,  # conservative default; tier_assigner will refine later
                document_type=p.media_type,
                source_uri=p.source_uri,
                title=p.title,
                investigation_id=event.investigation_id,
                metadata={
                    "content_hash": p.content_hash,
                    "size_bytes": p.size_bytes,
                    "page_count": p.page_count,
                },
                on_conflict="ignore",
            )
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"wrestling.document_loaded: insert failed — {exc!r}",
                flush=True,
            )
        finally:
            con.close()

        # RLM bridge: above-threshold long docs need the recursive
        # wrestling pattern (§11.6 + RLM-1). The decision is
        # ratification-gated; below-threshold OR pre-ratification
        # documents stay on the existing single-call path.
        try:
            from orchestration.rlm.bridge import (
                estimate_tokens_from_bytes,
                maybe_escalate_to_rlm,
            )

            decision = maybe_escalate_to_rlm(
                document_id=event.document_id,
                investigation_id=event.investigation_id or "__no_investigation__",
                estimated_tokens=estimate_tokens_from_bytes(p.size_bytes or 0),
                root_role="wrestler",
            )
            if decision.above_threshold:
                # Surface the decision for the wrestling driver +
                # observability — escalated or deferred, both informative.
                print(
                    f"wrestling.document_loaded[rlm-bridge]: "
                    f"document_id={event.document_id} "
                    f"estimated_tokens={decision.estimated_tokens} "
                    f"escalated={decision.escalated} "
                    f"session_id={decision.session_id or '-'} "
                    f"reason={decision.reason}",
                    flush=True,
                )
                # Emit the typed rlm.bridge.decided event so the
                # trajectory carries the verdict. Only emitted for
                # above-threshold documents to keep the event log
                # focused on real bridge weigh-ins; below-threshold
                # docs skip emission to avoid noise.
                if broadcaster is not None:
                    try:
                        import uuid as _uuid
                        from datetime import datetime as _dt

                        from substrate.schemas.events import (
                            ActionType as _AT,
                        )
                        from substrate.schemas.events import (
                            Event as _TypedEvent,
                        )

                        bridge_payload = decision.to_typed_payload()
                        bridge_event = _TypedEvent(
                            event_id=f"evt-{_uuid.uuid4().hex[:12]}",
                            investigation_id=(
                                event.investigation_id or "__no_investigation__"
                            ),
                            action_type=_AT.RLM_BRIDGE_DECIDED,
                            payload=bridge_payload,
                            param_version="wrestling-v0",
                            emitted_at=_dt.now(UTC),
                            document_id=event.document_id,
                        )
                        await broadcaster.broadcast(bridge_event)
                    except Exception as exc:  # pragma: no cover — emit must never block ingestion
                        print(
                            f"wrestling.document_loaded[rlm-bridge]: "
                            f"emit failed — {exc!r}",
                            flush=True,
                        )
        except Exception as exc:  # pragma: no cover — bridge must never break ingestion
            print(
                f"wrestling.document_loaded[rlm-bridge]: skipped — {exc!r}",
                flush=True,
            )

    return handle_document_loaded


def make_region_selected_handler(
    *,
    broadcaster: EventBroadcaster,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
):
    """Build the handler that mirrors ``document.region_selected``
    events into the graph: writes a chunks row (with embedding for the
    text excerpt) and a nodes row anchored to that chunk. Emits
    GRAPH_NODE_INSERTED via the ops layer.

    Idempotent: same region_id → same chunk_id → no-op on re-fire.
    """
    resolved_db = db_path or default_db_path()

    async def handle_region_selected(event: Event) -> None:
        if not isinstance(event.payload, DocumentRegionSelectedPayload):
            return
        if not event.document_id:
            return

        p = event.payload
        chunk_id = _region_to_chunk_id(p.region_id)
        # Lazy-resolve the embedder so tests + env-var overrides take
        # effect without us caching a stale module-level value.
        emb = embedder if embedder is not None else default_embedding_provider()
        try:
            vec = emb.encode(p.text_excerpt)
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"wrestling.region_selected: embedding failed — {exc!r}",
                flush=True,
            )
            return

        try:
            ensure_initialized(resolved_db)
            con = connect_write(resolved_db, purpose="wrestling.region_selected")
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"wrestling.region_selected: cannot acquire DB write — {exc!r}",
                flush=True,
            )
            return

        try:
            # Ensure the parent document exists. If the document.loaded
            # handler fired first this is a no-op; if the surface
            # somehow posted a region without a load (replay scenarios),
            # we synthesize a placeholder row so the chunks FK holds.
            insert_document(
                con,
                document_id=event.document_id,
                source_tier=4,
                document_type="pdf",
                investigation_id=event.investigation_id,
                on_conflict="ignore",
            )
            insert_chunk(
                con,
                chunk_id=chunk_id,
                document_id=event.document_id,
                chunk_index=p.char_start,  # use char_start as a stable index
                section_path=f"page {p.page}" if p.page is not None else None,
                text=p.text_excerpt,
                embedding=vec,
                token_count=len(p.text_excerpt.split()),
            )
            # Anchor the chunk as a graph node so traversal-side
            # consumers (the grounder) can find it via search +
            # connect via edges. ``label`` is a truncated excerpt for
            # discoverability; the full text lives on the chunk row.
            label = p.text_excerpt[:80].strip()
            if not label:
                label = f"region {p.region_id}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="claim",
                graph_scope="cross_domain",
                investigation_id=event.investigation_id,
                embedding=vec,
                metadata={
                    "chunk_id": chunk_id,
                    "document_id": event.document_id,
                    "region_id": p.region_id,
                    "page": p.page,
                },
                parent_event_id=event.event_id,
                on_conflict="ignore",
            )
            _ = node_id  # for clarity — id derived deterministically from label
        except Exception as exc:  # pragma: no cover — diagnostic
            print(
                f"wrestling.region_selected: insert failed — {exc!r}",
                flush=True,
            )
        finally:
            con.close()

        # Broadcast the emitted GRAPH_NODE_INSERTED event so subscribed
        # WS clients see the graph populating in real time. We look it
        # up by the chunk_id-derived label in the trajectory since
        # insert_node emits via emit_typed (which writes to the same
        # JSONL the broadcaster reads).
        for row in reversed(trajectory(event.investigation_id)):
            if (
                row.get("action_type") == ActionType.GRAPH_NODE_INSERTED.value
                and (row.get("payload") or {}).get("canonical_label") == label
            ):
                try:
                    node_event = Event.model_validate(row)
                    await broadcaster.broadcast(node_event)
                except Exception:  # pragma: no cover
                    pass
                break

    return handle_region_selected


def register_handlers(
    broadcaster: EventBroadcaster,
    *,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    execution_authority: DistillationExecutionAuthority | None = None,
) -> None:
    """Wire every wrestling handler into the broadcaster. Called once
    at app startup (see ``app.create_app``).

    ``db_path`` / ``embedder`` let tests inject test-isolated paths
    and stub providers. Production code uses ``None`` and gets the
    defaults from ``substrate/graph.default_db_path()`` +
    ``processing/embedding.default_embedding_provider()``."""
    broadcaster.register_handler(
        ActionType.DISTILLATION_REQUESTED.value,
        make_distillation_handler(
            broadcaster,
            db_path=db_path,
            execution_authority=execution_authority,
        ),
    )
    broadcaster.register_handler(
        ActionType.DOCUMENT_LOADED.value,
        make_document_loaded_handler(
            db_path=db_path, broadcaster=broadcaster,
        ),
    )
    broadcaster.register_handler(
        ActionType.DOCUMENT_REGION_SELECTED.value,
        make_region_selected_handler(
            broadcaster=broadcaster, db_path=db_path, embedder=embedder,
        ),
    )
