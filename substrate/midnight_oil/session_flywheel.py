"""Replay-safe terminal composition into a bound floating research session."""

from __future__ import annotations

import hashlib
import hmac
import json
from collections.abc import Callable
from typing import Any

from substrate.engagement_spine import (
    complete_spawn,
    record_progress,
    record_twin_insight,
    record_twin_question,
)
from substrate.engagement_spine.store import EngagementStore
from substrate.floating_session import (
    complete_session_with_context_flywheel,
    session_research_context,
)
from substrate.floating_session.store import SessionStore

from .job import MidnightOilJob
from .job_store import OperationState, OwnerJob


def _canonical_sha(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def context_binding_sha256(
    *,
    owner_id: str,
    execution_id: str,
    collective_unit_id: str,
    collective_preview_sha256: str,
    floating_session_id: str,
    floating_spawn_id: str,
    parent_asset_id: str,
    duration_minutes: int,
    model_id: str | None,
    research_tier: str,
    fanout_depth: int,
    publication_manifest_sha256: str | None = None,
) -> str:
    """Commit consent to the complete immutable product/execution tuple."""
    material: dict[str, object] = {
        "collective_unit_id": collective_unit_id,
        "collective_preview_sha256": collective_preview_sha256,
        "floating_session_id": floating_session_id,
        "floating_spawn_id": floating_spawn_id,
        "parent_asset_id": parent_asset_id,
        "duration_minutes": duration_minutes,
        "model_id": model_id,
        "research_tier": research_tier,
        "fanout_depth": fanout_depth,
        "live": True,
        "owner_id": owner_id,
        "execution_id": execution_id,
    }
    if publication_manifest_sha256 is not None:
        if len(publication_manifest_sha256) != 64:
            raise ValueError("publication manifest hash is invalid")
        material["publication_manifest_sha256"] = publication_manifest_sha256
    return hashlib.sha256(
        b"antiek:midnight-oil-context-binding:v1\0"
        + json.dumps(material, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def validate_context_binding(authority: OwnerJob, job: MidnightOilJob) -> None:
    """Recompute signed product context before spend and final effects."""
    payload = authority.payload
    from .publication_sources import manifest_from_authority

    publication_manifest = manifest_from_authority(payload)
    binding_hash = payload.get("context_binding_sha256")
    if binding_hash is None:
        return
    required = {
        name: payload.get(name)
        for name in (
            "execution_id",
            "collective_unit_id",
            "collective_preview_sha256",
            "floating_session_id",
            "floating_spawn_id",
            "context_parent_asset_id",
        )
    }
    if type(binding_hash) is not str or any(
        type(value) is not str or not value for value in required.values()
    ):
        raise ValueError("context binding authority is incomplete")
    expected = context_binding_sha256(
        owner_id=authority.owner_user_id,
        execution_id=str(required["execution_id"]),
        collective_unit_id=str(required["collective_unit_id"]),
        collective_preview_sha256=str(required["collective_preview_sha256"]),
        floating_session_id=str(required["floating_session_id"]),
        floating_spawn_id=str(required["floating_spawn_id"]),
        parent_asset_id=str(required["context_parent_asset_id"]),
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
        publication_manifest_sha256=(
            publication_manifest.manifest_sha256
            if publication_manifest is not None
            else None
        ),
    )
    if not hmac.compare_digest(binding_hash, expected):
        raise ValueError("context binding authority hash requires reconciliation")


def finalize_bound_session(
    *,
    authority: OwnerJob,
    job: MidnightOilJob,
    engagement_store: EngagementStore,
    session_store: SessionStore,
    before_settle: Callable[[], None] | None = None,
) -> dict[str, Any] | None:
    """Apply terminal evidence to the signed target session, or no-op if unbound."""
    payload = authority.payload
    binding_hash = payload.get("context_binding_sha256")
    if binding_hash is None:
        return None
    validate_context_binding(authority, job)
    fields = {
        name: payload.get(name)
        for name in (
            "execution_id",
            "collective_unit_id",
            "collective_preview_sha256",
            "floating_session_id",
            "floating_spawn_id",
        )
    }
    if (
        type(binding_hash) is not str
        or len(binding_hash) != 64
        or any(type(value) is not str or not value for value in fields.values())
    ):
        raise ValueError("terminal session binding is incomplete")
    owner = authority.owner_user_id
    execution_id = str(fields["execution_id"])
    unit_id = str(fields["collective_unit_id"])
    preview = str(fields["collective_preview_sha256"])
    session_id = str(fields["floating_session_id"])
    spawn_id = str(fields["floating_spawn_id"])
    unit = engagement_store.get_owned_document(unit_id, owner)
    session = session_store.get_session(session_id)
    spawn = engagement_store.get_owned_spawn(spawn_id, owner)
    if (
        unit is None
        or unit.get("document_type") != "collective_research_unit"
        or unit.get("preview_sha256") != preview
        or session is None
        or session.get("owner_id") != owner
        or session.get("source_collective_id") != unit_id
        or session.get("source_collective_preview_sha256") != preview
        or session.get("spawn_id") != spawn_id
        or spawn is None
        or spawn.get("parent_asset_id") != session.get("parent_asset_id")
    ):
        raise ValueError("terminal session binding requires reconciliation")
    if payload.get("context_parent_asset_id") != session.get("parent_asset_id"):
        raise ValueError("terminal session binding hash requires reconciliation")
    terminal = {
        OperationState.COMPLETE,
        OperationState.FAILED,
        OperationState.BUDGET_HALTED,
        OperationState.TIMED_OUT,
        OperationState.FAILED_RECONCILE,
    }
    if authority.operation_state not in terminal:
        raise ValueError("session finalization requires terminal execution authority")
    evidence_material = [
        {
            "step_key": evidence.step_key,
            "output_text": evidence.output_text,
            "insights": list(evidence.insights),
            "questions": list(evidence.questions),
            "route_receipt": evidence.route_receipt,
            "source_receipts": list(evidence.source_receipts),
        }
        for evidence in job.step_evidence
    ]
    request_sha = _canonical_sha(
        {
            "context_binding_sha256": binding_hash,
            "operation_state": authority.operation_state.value,
            "job_id": job.job_id,
            "deposit_html_sha256": job.deposit_html_sha256,
            "evidence": evidence_material,
        }
    )
    effect_id = f"ceffect_{execution_id.removeprefix('cexec_')}"

    def claim(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is not None:
            if current.get("request_sha256") != request_sha:
                raise ValueError("terminal session effect conflicts with durable evidence")
            return current
        return {
            "document_type": "collective_execution_effect",
            "execution_id": execution_id,
            "job_id": job.job_id,
            "session_id": session_id,
            "spawn_id": spawn_id,
            "context_binding_sha256": binding_hash,
            "request_sha256": request_sha,
            "state": "finalizing",
        }

    effect = engagement_store.mutate_owned_document(effect_id, owner, claim)
    if effect.get("state") == "applied":
        return effect
    output = "\n\n".join(
        evidence.output_text.strip() for evidence in job.step_evidence if evidence.output_text.strip()
    )[:500_000]
    if not output:
        output = f"Midnight Oil ended with {authority.operation_state.value}; no provider output was returned."
    insights = [
        text[:20_000]
        for evidence in job.step_evidence
        for text in evidence.insights
        if text.strip()
    ][:128]
    questions = [
        text[:20_000]
        for evidence in job.step_evidence
        for text in evidence.questions
        if text.strip()
    ][:128]
    if authority.operation_state is OperationState.COMPLETE:
        result = complete_session_with_context_flywheel(
            session_id,
            session_store=session_store,
            engagement_store=engagement_store,
            output_text=output,
            insights=insights,
            questions=questions,
            record_twins=True,
            include_twin_promote=False,
        ).to_dict()
        terminal_status = "complete"
    else:
        complete_spawn(
            spawn_id,
            store=engagement_store,
            output_text=output,
            insights=insights,
            questions=questions,
            status="failed",
        )
        for text in insights:
            record_twin_insight(
                str(session["parent_asset_id"]),
                text,
                store=engagement_store,
                source_spawn_id=spawn_id,
                investigation_id=str(session.get("investigation_id") or ""),
                owner_id=owner,
            )
        for text in questions:
            record_twin_question(
                str(session["parent_asset_id"]),
                text,
                store=engagement_store,
                source_spawn_id=spawn_id,
                investigation_id=str(session.get("investigation_id") or ""),
                owner_id=owner,
            )
        session_store.update_status(session_id, "failed")
        result = {
            "session_id": session_id,
            "spawn_id": spawn_id,
            "status": "failed",
            "context": session_research_context(
                session_id,
                session_store=session_store,
                engagement_store=engagement_store,
                include_twin_promote=False,
            ).to_dict(),
            "view_format": "html",
        }
        terminal_status = "failed"
    record_progress(
        spawn_id,
        terminal_status,
        f"Midnight Oil {authority.operation_state.value}: {job.job_id}",
        store=engagement_store,
        owner_id=owner,
        effect_id=f"{effect_id}:terminal-progress",
    )
    result_sha = _canonical_sha(result)
    if before_settle is not None:
        before_settle()

    def settle(current: dict[str, Any] | None) -> dict[str, Any]:
        if current is None or current.get("request_sha256") != request_sha:
            raise ValueError("terminal session effect changed before settlement")
        if current.get("state") == "applied":
            if current.get("result_sha256") != result_sha:
                raise ValueError("terminal session result conflicts with applied effect")
            return current
        return {
            **current,
            "state": "applied",
            "operation_state": authority.operation_state.value,
            "session_status": terminal_status,
            "result_sha256": result_sha,
            "context_sha256": _canonical_sha(result.get("context")),
        }

    return engagement_store.mutate_owned_document(effect_id, owner, settle)
