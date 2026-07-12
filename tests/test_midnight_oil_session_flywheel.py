from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.engagement_spine import HighlightSelection, list_progress, list_twin_notes
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.floating_session import open_from_highlight_with_references
from substrate.floating_session.store import InMemorySessionStore
from substrate.midnight_oil.job import (
    InMemoryJobStore,
    MidnightOilStepEvidence,
    create_job,
)
from substrate.midnight_oil.job_store import OperationState, OwnerJob
from substrate.midnight_oil.session_flywheel import (
    context_binding_sha256,
    finalize_bound_session,
    validate_context_binding,
)


def test_terminal_effect_completes_bound_session_once() -> None:
    engagement = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    owner = "alice"
    unit_id = "cunit_" + "1" * 24
    preview = "2" * 64
    engagement.mutate_owned_document(
        unit_id,
        owner,
        lambda _current: {
            "document_type": "collective_research_unit",
            "collective_unit_id": unit_id,
            "preview_sha256": preview,
        },
    )
    session = open_from_highlight_with_references(
        HighlightSelection(
            asset_id="research-parent",
            selection_text="Confirmed collective context",
            region_id="terminal-effect",
        ),
        engagement_store=engagement,
        session_store=sessions,
        references=["https://arxiv.org/abs/1706.03762"],
        owner_id=owner,
        source_collective_id=unit_id,
        source_collective_preview_sha256=preview,
    )
    job = create_job(
        ["Continue cohesive research"],
        30,
        store=InMemoryJobStore(),
        job_id="moil_terminal_effect",
        asset_id="moil_asset_terminal_effect",
    )
    job = replace(
        job,
        status="complete",
        deposit_state="complete",
        deposit_html_sha256="3" * 64,
        step_evidence=(
            MidnightOilStepEvidence(
                step_key="operation:0",
                spawn_id="worker-spawn",
                output_text="Durable synthesis from the paid provider.",
                insights=("A recursive insight",),
                questions=("Which uncertainty remains?",),
            ),
        ),
    )
    execution_id = "cexec_" + "5" * 24
    binding_hash = context_binding_sha256(
        owner_id=owner,
        execution_id=execution_id,
        collective_unit_id=unit_id,
        collective_preview_sha256=preview,
        floating_session_id=session.session_id,
        floating_spawn_id=session.spawn_id,
        parent_asset_id=session.parent_asset_id,
        duration_minutes=job.duration_minutes,
        model_id=job.model_id,
        research_tier=job.research_tier,
        fanout_depth=job.fanout_depth,
    )
    authority = OwnerJob(
        owner_user_id=owner,
        job_id=job.job_id,
        state_version=4,
        approved_ceiling_cents=100,
        consent_receipt_id="receipt",
        consent_config_hash="4" * 64,
        consent_issued_at_ms=1,
        consent_expires_at_ms=100,
        consent_claimed_at_ms=2,
        operation_id="operation",
        operation_state=OperationState.COMPLETE,
        dispatch_started_at_ms=3,
        dispatched_at_ms=4,
        completed_at_ms=5,
        payload={
            "execution_id": execution_id,
            "collective_unit_id": unit_id,
            "collective_preview_sha256": preview,
            "floating_session_id": session.session_id,
            "floating_spawn_id": session.spawn_id,
            "context_binding_sha256": binding_hash,
            "context_parent_asset_id": session.parent_asset_id,
        },
    )
    with pytest.raises(RuntimeError, match="before effect settlement"):
        finalize_bound_session(
            authority=authority,
            job=job,
            engagement_store=engagement,
            session_store=sessions,
            before_settle=lambda: (_ for _ in ()).throw(
                RuntimeError("before effect settlement")
            ),
        )
    first = finalize_bound_session(
        authority=authority,
        job=job,
        engagement_store=engagement,
        session_store=sessions,
    )
    second = finalize_bound_session(
        authority=authority,
        job=job,
        engagement_store=engagement,
        session_store=sessions,
    )
    assert first == second
    assert first is not None and first["state"] == "applied"
    completed = engagement.get_owned_spawn(session.spawn_id, owner)
    assert completed is not None
    assert completed["status"] == "complete"
    assert "Durable synthesis" in completed["output_text"]
    notes = list_twin_notes("research-parent", store=engagement, owner_id=owner)
    assert {(note.kind, note.text) for note in notes} == {
        ("insight", "A recursive insight"),
        ("question", "Which uncertainty remains?"),
    }
    assert list_twin_notes("research-parent", store=engagement, owner_id="bob") == []
    progress = list_progress(session.spawn_id, store=engagement, owner_id=owner)
    assert len([event for event in progress if event.effect_id]) == 1
    with pytest.raises(ValueError, match="binding authority hash"):
        validate_context_binding(
            replace(
                authority,
                payload={**authority.payload, "context_parent_asset_id": "redirected-parent"},
            ),
            job,
        )
