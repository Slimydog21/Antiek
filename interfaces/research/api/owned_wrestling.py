"""Authenticated, source-bound staging path for the existing wrestler.

Native Prime execution is absent. An owner may explicitly approve the
canonical synthesizer fallback; this path never reports Prime enhancement.
"""

from __future__ import annotations

import asyncio
import hashlib
from collections.abc import Iterator
from contextlib import contextmanager, nullcontext
from dataclasses import replace
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictInt

from runtime.db_lock import authority_handoff_guard
from substrate.books.owned_wrestling_sources import (
    OwnedSourceUnavailable,
    canonical_bytes,
    current_book_material,
    owned_execution_guard,
    read_immutable_artifact,
    source_digest,
    write_immutable_artifact,
)
from substrate.byot_usage.actions import ActionSnapshot, OwnedWrestlingJob, OwnerActionDecision
from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict
from substrate.constants import ANTIEK_PARAM_VERSION
from substrate.context_pack import LayerSource, assemble_context_pack, build_working_memory_layer
from substrate.dispatch.router import DispatchConfig
from substrate.event_log import emit_typed, iter_physical_events
from substrate.graph import default_db_path
from substrate.schemas import (
    EVENT_SCHEMA_VERSION,
    DispatchCallPayload,
    DistillationDeliveredPayload,
    DistillationRequestedPayload,
    Event,
)

from .owner_byot_dispatch import (
    OwnerByotDispatchUnavailable,
    OwnerByotOutcomeUnknown,
    approved_owner_action_route,
    authenticated_distinct_owner,
    dispatch_talk_to_book_byot,
)
from .settings_models_admin import UserModelChoice
from .wrestling import ROLE_PROMPT_TAIL, _parse_claims_response, _sha256_prefix

OWNED_POLICY = "owned-wrestling/v1"


class OwnedWrestlingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action_id: str = Field(min_length=1, max_length=128)
    user_prompt: str = Field(min_length=1, max_length=16_000)
    target_token_count: StrictInt = Field(ge=1, le=16_000)
    total_budget_cents: StrictInt = Field(ge=1)
    canonical_model: UserModelChoice
    prime_model: UserModelChoice
    approve_canonical_source_processing: StrictBool
    approve_prime_source_processing: StrictBool
    approve_canonical_fallback_if_prime_unavailable: StrictBool


class OwnedWrestlingView(BaseModel):
    action_id: str
    investigation_id: str
    request_event_id: str
    delivered_event_id: str | None
    state: str
    supplemental_status: str = "supplemental_not_run"
    action_epoch: int
    action_state: str


class OwnedWrestlingCancel(BaseModel):
    expected_epoch: int = Field(ge=0)


def _artifact_dir(ledger: ByotUsageLedger) -> Path:
    return Path(ledger._db_path).with_name("owned-wrestling-artifacts")


def _stable_id(prefix: str, owner: str, action: str) -> str:
    return prefix + hashlib.sha256(f"{owner}\0{action}".encode()).hexdigest()[:32]


def _payload_digest(payload: BaseModel) -> str:
    return hashlib.sha256(canonical_bytes(payload.model_dump(mode="json"))).hexdigest()


def _view(job: OwnedWrestlingJob, ledger: ByotUsageLedger) -> OwnedWrestlingView:
    action = ledger.action(job.owner_user_id, job.action_id)
    if action is None:
        raise OwnedSourceUnavailable("owned money action is unavailable")
    return OwnedWrestlingView(
        action_id=job.action_id, investigation_id=job.investigation_id,
        request_event_id=job.request_event_id,
        delivered_event_id=job.delivered_event_id if job.state in {"ready", "delivered"} else None,
        state=job.state,
        action_epoch=action.epoch, action_state=action.state,
    )


def _event_rows(investigation_id: str) -> list[dict[str, Any]]:
    return list(iter_physical_events(investigation_id))


def _verify_request_event(job: OwnedWrestlingJob, event: Event) -> DistillationRequestedPayload:
    if (event.event_id != job.request_event_id
        or event.investigation_id != job.investigation_id
        or event.document_id != job.document_id
        or event.policy_id != OWNED_POLICY
        or event.param_version != ANTIEK_PARAM_VERSION
        or event.schema_version != EVENT_SCHEMA_VERSION
        or event.parent_event_id is not None
        or event.phase is not None or event.synthesis_id is not None
        or event.role != "operator"
        or not isinstance(event.payload, DistillationRequestedPayload)
        or _payload_digest(event.payload) != job.request_payload_digest):
        raise OwnedSourceUnavailable("owned request event differs from binding")
    return event.payload


def _matching_persisted_event(
    job: OwnedWrestlingJob, event_id: str, payload: BaseModel,
    *, parent_event_id: str | None, role: str, policy_id: str,
) -> Event | None:
    matches = [row for row in _event_rows(job.investigation_id)
               if row.get("event_id") == event_id]
    if len(matches) > 1:
        raise OwnedSourceUnavailable("owned event ID is duplicated")
    if not matches:
        return None
    try:
        event = Event.model_validate(matches[0])
    except Exception as exc:
        raise OwnedSourceUnavailable("owned event is invalid") from exc
    if (event.investigation_id != job.investigation_id
        or event.document_id != job.document_id
        or event.parent_event_id != parent_event_id
        or event.role != role or event.policy_id != policy_id
        or event.param_version != ANTIEK_PARAM_VERSION
        or event.schema_version != EVENT_SCHEMA_VERSION
        or event.phase is not None or event.synthesis_id is not None
        or event.payload.model_dump(mode="json") != payload.model_dump(mode="json")):
        raise OwnedSourceUnavailable("same-ID event has contradictory binding or payload")
    return event


async def _publish(
    job: OwnedWrestlingJob, payload: BaseModel, *, kind: str,
    broadcaster: Any, ledger: ByotUsageLedger,
    source_gate: tuple[str, dict[str, Any]] | None = None,
) -> Event | None:
    event_id = job.request_event_id if kind == "requested" else job.delivered_event_id
    parent = None if kind == "requested" else job.request_event_id
    role = "operator" if kind == "requested" else "synthesizer"
    policy = OWNED_POLICY if kind == "requested" else OWNED_POLICY + "/canonical-fallback"
    digest = _payload_digest(payload)
    def persist() -> Event | None:
        graph_gate = (authority_handoff_guard(source_gate[0], purpose="owned-wrestling-publish")
                      if source_gate is not None else nullcontext())
        with graph_gate:
            if source_gate is not None:
                _require_current_source(source_gate[0], job, source_gate[1])
            event = _matching_persisted_event(
                job, event_id, payload, parent_event_id=parent, role=role,
                policy_id=policy,
            )
            already_present = event is not None

            def append() -> Event:
                existing = _matching_persisted_event(
                    job, event_id, payload, parent_event_id=parent, role=role,
                    policy_id=policy,
                )
                if existing is not None:
                    return existing
                emitted = emit_typed(
                    job.investigation_id, payload, event_id=event_id,
                    idempotent=True, strict_write=True, parent_event_id=parent,
                    role=role, policy_id=policy, document_id=job.document_id,
                )
                if emitted != event_id:
                    raise OwnedSourceUnavailable("owned event was not persisted")
                persisted = _matching_persisted_event(
                    job, event_id, payload, parent_event_id=parent, role=role,
                    policy_id=policy,
                )
                if persisted is None:
                    raise OwnedSourceUnavailable("owned event publication is missing")
                return persisted

            if kind == "delivered":
                return ledger.publish_owned_wrestling_delivery(
                    job.owner_user_id, job.action_id, event_id, digest,
                    already_present=already_present, append=append,
                )
            event = append()
            ledger.mark_owned_event_published(
                job.owner_user_id, job.action_id, kind, event_id, digest,
            )
            return event

    event = await asyncio.to_thread(persist)
    if event is not None:
        await broadcaster.broadcast(event)
    return event


def _source_artifact(job: OwnedWrestlingJob, ledger: ByotUsageLedger) -> dict[str, Any]:
    artifact = read_immutable_artifact(_artifact_dir(ledger), job.source_reference,
                                       job.source_digest)
    if not isinstance(artifact.get("material"), dict) or not isinstance(artifact.get("work"), dict):
        raise OwnedSourceUnavailable("owned source artifact is invalid")
    return artifact


def _current_source_digest(db_path: str, job: OwnedWrestlingJob) -> str:
    return source_digest(current_book_material(
        db_path, owner=job.owner_user_id, document_id=job.document_id,
    ))


def _require_current_source(db_path: str, job: OwnedWrestlingJob, artifact: dict[str, Any]) -> str:
    admitted = source_digest(artifact["material"])
    if _current_source_digest(db_path, job) != admitted:
        raise OwnedSourceUnavailable("current book body, chunks, ownership or rights changed")
    return admitted


def _request_payload(artifact: dict[str, Any]) -> DistillationRequestedPayload:
    work = artifact["work"]
    return DistillationRequestedPayload(
        user_prompt=work["user_prompt"], target_token_count=work["target_token_count"],
        region_id=None,
    )


def _settled_output_tokens(
    job: OwnedWrestlingJob, ledger: ByotUsageLedger, operation_id: str, prompt: str,
    context_pack_event_id: str,
) -> int:
    """Recover exact output usage from the already-settled dispatch event."""
    operation = ledger.operation(job.owner_user_id, operation_id)
    if operation is None or operation.state != "settled" or not operation.dispatch_event_id:
        raise OwnedSourceUnavailable("canonical result is not durably settled")
    rows = [row for row in _event_rows(job.investigation_id)
            if row.get("event_id") == operation.dispatch_event_id]
    if len(rows) != 1:
        raise OwnedSourceUnavailable("canonical usage event is unavailable or duplicated")
    event = Event.model_validate(rows[0])
    payload = event.payload
    if (not isinstance(payload, DispatchCallPayload)
        or payload.target_role != "synthesizer"
        or payload.context_pack_event_id != context_pack_event_id
        or event.parent_event_id != job.request_event_id
        or (payload.provider, payload.model) != (operation.provider_id, operation.model_id)
        or payload.prompt_hash != _sha256_prefix(prompt)):
        raise OwnedSourceUnavailable("canonical usage event differs from settled result")
    return payload.output_tokens


def _target_config(target_token_count: int) -> DispatchConfig:
    loaded = DispatchConfig.from_yaml(
        Path(__file__).parents[3] / "substrate/dispatch/config.yaml"
    )
    tier_name = loaded.role_tiers["synthesizer"]
    tier = loaded.tiers[tier_name]
    if target_token_count > tier.max_tokens:
        raise OwnedSourceUnavailable("requested output exceeds the synthesizer cap")
    tiers = dict(loaded.tiers)
    tiers[tier_name] = replace(tier, max_tokens=target_token_count)
    return DispatchConfig(loaded.role_tiers, tiers)


def _submit_sync(
    app: FastAPI, db_path: str, owner: str, document_id: str,
    work: OwnedWrestlingRequest, ledger: ByotUsageLedger,
) -> OwnedWrestlingJob:
    if not (work.approve_canonical_source_processing and work.approve_prime_source_processing):
        raise OwnedSourceUnavailable("both selected source-processing routes require approval")
    canonical_route = approved_owner_action_route(app, work.canonical_model, owner_user_id=owner)
    prime_route = approved_owner_action_route(app, work.prime_model, owner_user_id=owner)
    with authority_handoff_guard(db_path, purpose="owned-wrestling-admission"):
        material = current_book_material(db_path, owner=owner, document_id=document_id)
        material_digest = source_digest(material)
    investigation = _stable_id("ownw-", owner, work.action_id)
    existing = ledger.owned_wrestling_job(owner, work.action_id)
    if existing is None and _event_rows(investigation):
        raise OwnedSourceUnavailable("owned investigation already has unverifiable history")
    approved_work = work.model_dump(mode="json")
    artifact = {"material": material, "work": approved_work,
                "investigation_id": investigation}
    source_name = _stable_id("source-", owner, work.action_id)
    artifact_digest = write_immutable_artifact(_artifact_dir(ledger), source_name, artifact)
    request_payload = _request_payload(artifact)
    decision_digest = source_digest({
        "owner": owner, "document": document_id, "action": work.action_id,
        "source_digest": artifact_digest, "approval": approved_work,
    })
    decision = OwnerActionDecision(
        owner_user_id=owner, action_id=work.action_id,
        action_kind="long_document_wrestling", budget_cents=work.total_budget_cents,
        body_authority_digest=material_digest, owner_decision_digest=decision_digest,
        approved_routes=tuple(dict.fromkeys((canonical_route, prime_route))),
    )
    job = ledger.admit_owned_wrestling(
        decision, investigation_id=investigation, document_id=document_id,
        source_reference=source_name, source_digest=artifact_digest,
        request_event_id=_stable_id("owreq-", owner, work.action_id),
        delivered_event_id=_stable_id("owdel-", owner, work.action_id),
        request_payload_digest=_payload_digest(request_payload),
    )
    if existing is not None:
        rows = _event_rows(investigation)
        request_rows = [row for row in rows if row.get("event_id") == job.request_event_id]
        if rows and (len(request_rows) != 1 or rows[0].get("event_id") != job.request_event_id):
            raise OwnedSourceUnavailable("owned request history differs from binding")
        _matching_persisted_event(
            job, job.request_event_id, request_payload, parent_event_id=None,
            role="operator", policy_id=OWNED_POLICY,
        )
    return job


async def submit(
    *, request: Request, document_id: str, work: OwnedWrestlingRequest,
    broadcaster: Any, db_path: str | None = None,
) -> OwnedWrestlingView:
    try:
        owner = authenticated_distinct_owner(request)
        ledger = ByotUsageLedger()
        job = await asyncio.to_thread(
            _submit_sync, request.app, db_path or default_db_path(), owner,
            document_id, work, ledger,
        )
        artifact = await asyncio.to_thread(_source_artifact, job, ledger)
        await _publish(job, _request_payload(artifact), kind="requested",
                       broadcaster=broadcaster, ledger=ledger)
        return _view(ledger.owned_wrestling_job(owner, work.action_id) or job, ledger)
    except (OwnerByotDispatchUnavailable, OwnedSourceUnavailable, OperationConflict,
            ValueError, KeyError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from None


async def view(*, request: Request, action_id: str) -> OwnedWrestlingView:
    try:
        owner = authenticated_distinct_owner(request)
        ledger = ByotUsageLedger()
        job = ledger.owned_wrestling_job(owner, action_id)
    except (OwnerByotDispatchUnavailable, ValueError):
        job = None
    if job is None:
        raise HTTPException(status_code=404, detail="owned_wrestling_not_found")
    return _view(job, ledger)


async def cancel(
    *, request: Request, action_id: str, expected_epoch: int,
) -> OwnedWrestlingView:
    try:
        owner = authenticated_distinct_owner(request)
        ledger = ByotUsageLedger()
        job = ledger.owned_wrestling_job(owner, action_id)
        if job is None:
            raise HTTPException(status_code=404, detail="owned_wrestling_not_found")
        ledger.close_action(owner, action_id, expected_epoch=expected_epoch)
        if job.state == "queued":
            job = ledger.transition_owned_wrestling(owner, action_id,
                                                     expected="queued", state="refused")
        return _view(job, ledger)
    except (OwnerByotDispatchUnavailable, OperationConflict, ValueError):
        raise HTTPException(status_code=409, detail="owned_wrestling_cancel_conflict") from None


async def consume(event: Event, *, broadcaster: Any, db_path: str | None = None) -> None:
    """Own the source check, existing canonical consumer and publication order."""
    ledger = ByotUsageLedger()
    found_job = ledger.owned_wrestling_for_request(event.event_id)
    if found_job is None:
        raise OwnedSourceUnavailable("marked request has no server-owned binding")
    job: OwnedWrestlingJob = found_job
    graph_db = db_path or default_db_path()
    try:
        request_payload = _verify_request_event(job, event)
        artifact = _source_artifact(job, ledger)
        if _payload_digest(_request_payload(artifact)) != job.request_payload_digest:
            raise OwnedSourceUnavailable("request artifact differs from binding")
        admitted = await asyncio.to_thread(_require_current_source, graph_db, job, artifact)
    except (OwnedSourceUnavailable, KeyError, ValueError):
        if job.state == "queued":
            ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                               expected="queued", state="refused")
            current_action = ledger.action(job.owner_user_id, job.action_id)
            if current_action is not None:
                ledger.close_action(job.owner_user_id, job.action_id,
                                    expected_epoch=current_action.epoch)
        raise
    action = ledger.action(job.owner_user_id, job.action_id)
    if action is None or action.decision.body_authority_digest != admitted:
        raise OwnedSourceUnavailable("money action differs from source binding")
    if job.state in {"ready", "delivered"}:
        with owned_execution_guard(
            _artifact_dir(ledger), _stable_id("worker-", job.owner_user_id, job.action_id),
        ) as elected:
            if elected:
                await _consume_ready(job, artifact, admitted, ledger, graph_db, broadcaster)
        return
    if job.state in {"refused", "unresolved"}:
        return
    if job.state == "queued" and action.state != "open":
        ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                           expected="queued", state="refused")
        return
    with owned_execution_guard(
        _artifact_dir(ledger), _stable_id("worker-", job.owner_user_id, job.action_id),
    ) as elected:
        if not elected:
            return
        await _consume_elected(job, event, request_payload, artifact, admitted, action,
                               ledger, graph_db, broadcaster)


async def _consume_ready(
    job: OwnedWrestlingJob, artifact: dict[str, Any], admitted: str,
    ledger: ByotUsageLedger, graph_db: str, broadcaster: Any,
) -> None:
    result = read_immutable_artifact(_artifact_dir(ledger),
                                     job.result_reference or "", job.result_digest or "")
    canonical_input = read_immutable_artifact(
        _artifact_dir(ledger), job.canonical_input_reference or "",
        job.canonical_input_digest or "",
    )
    operation_id = _stable_id("owcanon-", job.owner_user_id, job.action_id)
    operation = ledger.operation(job.owner_user_id, operation_id)
    if (result.get("source_digest") != admitted
        or result.get("canonical_operation_id") != operation_id
        or canonical_input.get("source_digest") != admitted
        or canonical_input.get("request_event_id") != job.request_event_id
        or result.get("canonical_input_sha256") != hashlib.sha256(
            str(canonical_input.get("prompt", "")).encode(),
        ).hexdigest()
        or operation is None or operation.state != "settled"
        or operation.action_id != job.action_id):
        raise OwnedSourceUnavailable("owned result differs from settled canonical attempt")
    payload = DistillationDeliveredPayload.model_validate(result["payload"])
    published = await _publish(job, payload, kind="delivered", broadcaster=broadcaster,
                               ledger=ledger, source_gate=(graph_db, artifact))
    if published is None:
        return
    if job.state == "ready":
        ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                           expected="ready", state="delivered")
    current_action = ledger.action(job.owner_user_id, job.action_id)
    if current_action is not None and current_action.state != "closed":
        ledger.close_action(job.owner_user_id, job.action_id,
                            expected_epoch=current_action.epoch)


async def _consume_elected(
    job: OwnedWrestlingJob, event: Event, request_payload: DistillationRequestedPayload,
    artifact: dict[str, Any], admitted: str, action: ActionSnapshot,
    ledger: ByotUsageLedger, graph_db: str, broadcaster: Any,
) -> None:
    operation_id = _stable_id("owcanon-", job.owner_user_id, job.action_id)
    execution_token = uuid4().hex
    claimed = ledger.claim_owned_wrestling_execution(
        job.owner_user_id, job.action_id, token=execution_token,
        operation_id=operation_id,
    )
    if claimed is None:
        # A running claim is not evidence that its owner died. Only a settled
        # canonical result can be reconstructed by a new worker without a send.
        return
    job = claimed

    try:
        work = artifact["work"]
        if job.canonical_input_reference is not None:
            saved = read_immutable_artifact(
                _artifact_dir(ledger), job.canonical_input_reference,
                job.canonical_input_digest or "",
            )
            if (saved.get("source_digest") != admitted
                or saved.get("request_event_id") != event.event_id
                or saved.get("max_output_tokens") != work["target_token_count"]
                or saved.get("canonical_model") != work["canonical_model"]
                or not isinstance(saved.get("prompt"), str)
                or not isinstance(saved.get("context_pack_event_id"), str)):
                raise OwnedSourceUnavailable("canonical input differs from admitted request")
            prompt = saved["prompt"]
            pack_id = saved["context_pack_event_id"]
        else:
            if job.state != "running" or ledger.operation(job.owner_user_id, operation_id) is not None:
                raise OwnedSourceUnavailable("running canonical input is unavailable")
            rows = await asyncio.to_thread(_event_rows, job.investigation_id)
            cutoffs = [i for i, row in enumerate(rows) if row.get("event_id") == event.event_id]
            if len(cutoffs) != 1 or cutoffs[0] != 0:
                raise OwnedSourceUnavailable("owned investigation has unverifiable prior events")
            memory_layer = build_working_memory_layer(
                rows, investigation_id=job.investigation_id, cutoff_event_id=event.event_id,
            )
            if memory_layer is not None:
                raise OwnedSourceUnavailable("working-memory owner provenance is unavailable")
            source_body = artifact["material"]["body"]
            pack = assemble_context_pack(
                role="synthesizer", investigation_id=job.investigation_id,
                parent_event_id=event.event_id,
                layers=[
                    LayerSource(kind="param_version_stamp", source="antiek",
                                content=f"ANTIEK_PARAM_VERSION={ANTIEK_PARAM_VERSION}"),
                    LayerSource(kind="phase_metadata", source="loop2.wrestling",
                                content=f"loop=wrestling investigation={job.investigation_id}"
                                        f" document={job.document_id} region=<whole_doc>"),
                    LayerSource(kind="session", source=f"document:{job.document_id}",
                                content=f"Source text:\n\n{source_body}\n\n---\n\n"
                                        f"User question:\n{request_payload.user_prompt}"),
                ],
            )
            if pack.budget_overrun or pack.event_id is None:
                raise OwnedSourceUnavailable("whole book did not fit the canonical context pack")
            prompt = pack.text + "\n\n" + ROLE_PROMPT_TAIL
            pack_id = pack.event_id
            input_name = _stable_id("input-", job.owner_user_id, job.action_id)
            input_digest = write_immutable_artifact(_artifact_dir(ledger), input_name, {
                "prompt": prompt, "source_digest": admitted,
                "request_event_id": event.event_id,
                "context_pack_event_id": pack_id,
                "max_output_tokens": work["target_token_count"],
                "canonical_model": work["canonical_model"],
            })
            job = ledger.bind_owned_wrestling_input(
                job.owner_user_id, job.action_id, reference=input_name, digest=input_digest,
                execution_token=execution_token,
            )
        if not work["approve_canonical_fallback_if_prime_unavailable"]:
            ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                               expected="running", state="refused",
                                               execution_token=execution_token)
            ledger.close_action(job.owner_user_id, job.action_id, expected_epoch=action.epoch)
            return
        app = getattr(broadcaster, "_owner_model_app", None)
        if app is None:
            raise OwnedSourceUnavailable("owner model app is unavailable")
        config = _target_config(work["target_token_count"])

        @contextmanager
        def guard() -> Iterator[str]:
            with authority_handoff_guard(graph_db, purpose="owned-wrestling-send"):
                yield _current_source_digest(graph_db, job)

        def send() -> Any:
            return dispatch_talk_to_book_byot(
                app=app, request_owner_user_id=job.owner_user_id,
                resource_owner_user_id=job.owner_user_id, document_id=job.document_id,
                choice=UserModelChoice.model_validate(work["canonical_model"]),
                prompt=prompt, investigation_id=job.investigation_id,
                logical_operation_id=operation_id, resource_authority_digest=admitted,
                resource_authority_guard=guard, role="synthesizer",
                action="wrestling.distillation", owner_action=action.ref,
                config=config,
                context_pack_event_id=pack_id,
                parent_event_id=event.event_id,
                usage_ledger=ledger,
            )

        result, _authority = await asyncio.to_thread(send)
        await asyncio.to_thread(_require_current_source, graph_db, job, artifact)
        output_tokens = (await asyncio.to_thread(
            _settled_output_tokens, job, ledger, operation_id, prompt, pack_id,
        ) if result.finish_reason == "replayed" else result.usage.output_tokens)
        claims, rendered = _parse_claims_response(result.text, region_id=None)
        if any(claim.attribution_region_ids for claim in claims):
            raise OwnedSourceUnavailable("model returned an unadmitted region citation")
        claims = [
            claim.model_copy(update={"claim_id": _stable_id(
                "c-", job.owner_user_id, f"{job.action_id}:{index}:{claim.text}",
            )})
            for index, claim in enumerate(claims)
        ]
        payload = DistillationDeliveredPayload(
            request_event_id=event.event_id, claims=claims, rendered_text=rendered,
            rendered_text_hash=_sha256_prefix(rendered),
            token_count=output_tokens,
        )
        result_name = _stable_id("result-", job.owner_user_id, job.action_id)
        result_artifact = {"payload": payload.model_dump(mode="json"),
                           "source_digest": admitted,
                           "canonical_operation_id": operation_id,
                           "canonical_input_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                           "supplemental_status": "supplemental_not_run"}
        result_digest = write_immutable_artifact(_artifact_dir(ledger), result_name,
                                                 result_artifact)
        job = ledger.transition_owned_wrestling(
            job.owner_user_id, job.action_id, expected="running", state="ready",
            result_reference=result_name, result_digest=result_digest,
            publication_payload_digest=_payload_digest(payload),
            execution_token=execution_token,
        )
        await asyncio.to_thread(_require_current_source, graph_db, job, artifact)
        published = await _publish(job, payload, kind="delivered", broadcaster=broadcaster,
                                   ledger=ledger, source_gate=(graph_db, artifact))
        if published is None:
            return
        ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                           expected="ready", state="delivered")
        current_action = ledger.action(job.owner_user_id, job.action_id)
        if current_action is not None and current_action.state != "closed":
            ledger.close_action(job.owner_user_id, job.action_id,
                                expected_epoch=current_action.epoch)
    except OwnerByotOutcomeUnknown:
        ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                           expected="running", state="unresolved",
                                           execution_token=execution_token)
        raise
    except (OwnedSourceUnavailable, OwnerByotDispatchUnavailable):
        current = ledger.owned_wrestling_job(job.owner_user_id, job.action_id)
        if current is not None and current.state == "running":
            attempt = ledger.operation(job.owner_user_id, operation_id)
            state = "unresolved" if attempt is not None and attempt.state in {
                "sent", "unknown", "settlement_pending", "settled"
            } else "refused"
            ledger.transition_owned_wrestling(job.owner_user_id, job.action_id,
                                               expected="running", state=state,
                                               execution_token=execution_token)
            if state == "refused":
                current_action = ledger.action(job.owner_user_id, job.action_id)
                if current_action is not None:
                    ledger.close_action(job.owner_user_id, job.action_id,
                                        expected_epoch=current_action.epoch)
        raise


def register_owned_wrestling_routes(
    app: FastAPI, broadcaster: Any, *, db_path: str | None = None,
) -> None:
    def owner_audience(investigation_id: str) -> str | None:
        job = ByotUsageLedger().owned_wrestling_for_investigation(investigation_id)
        return job.owner_user_id if job is not None else None

    broadcaster.owner_audience_for_investigation = owner_audience

    @app.post("/books/{document_id}/wrestle", response_model=OwnedWrestlingView, status_code=202)
    async def post_owned_wrestling(
        document_id: str, work: OwnedWrestlingRequest, request: Request,
    ) -> OwnedWrestlingView:
        return await submit(request=request, document_id=document_id, work=work,
                            broadcaster=broadcaster, db_path=db_path)

    @app.get("/books/wrestle-actions/{action_id}", response_model=OwnedWrestlingView)
    async def get_owned_wrestling(action_id: str, request: Request) -> OwnedWrestlingView:
        return await view(request=request, action_id=action_id)

    @app.post("/books/wrestle-actions/{action_id}/cancel", response_model=OwnedWrestlingView)
    async def cancel_owned_wrestling(
        action_id: str, work: OwnedWrestlingCancel, request: Request,
    ) -> OwnedWrestlingView:
        return await cancel(request=request, action_id=action_id,
                            expected_epoch=work.expected_epoch)
