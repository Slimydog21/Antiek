from __future__ import annotations

import hashlib
import json
import time

import pytest

from interfaces.research.api.broadcast import EventBroadcaster
from orchestration.loop_one.orchestrator import (
    InvestigationContext,
    _deposit_synthesis_to_substrate,
    _project_success_outputs,
    _projection_input_sha256,
    _rehydrate_archived_source_coverage,
    _verify_synthesis_projection_effect,
)
from orchestration.loop_one.terminal_projection import (
    InvestigationProjectionConflict,
    investigation_projection_event_id,
    investigation_projection_id,
    project_investigation_projection,
    projection_effects_sha256,
)
from substrate.event_log import (
    append_event_once_authorized,
    claim_investigation_execution_authorized,
    investigation_execution_context,
    prepare_typed_event,
    trajectory_authorized_append_order,
)
from substrate.schemas import (
    InvestigationProjectionCompletedPayload,
    InvestigationProjectionEffectRecordedPayload,
    InvestigationProjectionFailedPayload,
    InvestigationProjectionRequestedPayload,
    SynthesizeDeliveredPayload,
)
from tests.test_investigation_execution_lease import _authority
from tests.test_loop_one_orchestrator import _SYNTHESIZER_RESPONSE

EXECUTION_ID = "a" * 64
INPUT_SHA = "b" * 64
GENERATION = 2


def _lifecycle():
    synthesis = prepare_typed_event(
        "inv-projection",
        SynthesizeDeliveredPayload.model_validate(json.loads(_SYNTHESIZER_RESPONSE)),
        event_id="evt-synthesis",
        execution_generation=GENERATION,
    )
    projection_id = investigation_projection_id(EXECUTION_ID, synthesis.event_id, INPUT_SHA)
    request = prepare_typed_event(
        synthesis.investigation_id,
        InvestigationProjectionRequestedPayload(
            projection_id=projection_id,
            execution_id=EXECUTION_ID,
            synthesis_event_id=synthesis.event_id,
            input_sha256=INPUT_SHA,
        ),
        event_id=investigation_projection_event_id(projection_id, "request"),
        parent_event_id=synthesis.event_id,
        execution_generation=GENERATION,
    )
    archive = prepare_typed_event(
        synthesis.investigation_id,
        InvestigationProjectionEffectRecordedPayload(
            projection_id=projection_id,
            request_event_id=request.event_id,
            effect="synthesis_archive",
            disposition="complete",
            effect_ref="syn-authorized",
            effect_sha256="c" * 64,
        ),
        event_id=investigation_projection_event_id(projection_id, "synthesis_archive"),
        parent_event_id=request.event_id,
        execution_generation=GENERATION,
    )
    html = prepare_typed_event(
        synthesis.investigation_id,
        InvestigationProjectionEffectRecordedPayload(
            projection_id=projection_id,
            request_event_id=request.event_id,
            effect="html_artifact",
            disposition="not_configured",
        ),
        event_id=investigation_projection_event_id(projection_id, "html_artifact"),
        parent_event_id=request.event_id,
        execution_generation=GENERATION,
    )
    completion = prepare_typed_event(
        synthesis.investigation_id,
        InvestigationProjectionCompletedPayload(
            projection_id=projection_id,
            request_event_id=request.event_id,
            synthesis_effect_event_id=archive.event_id,
            html_effect_event_id=html.event_id,
            effects_sha256=projection_effects_sha256(archive, html),
        ),
        event_id=investigation_projection_event_id(projection_id, "complete"),
        parent_event_id=request.event_id,
        execution_generation=GENERATION,
    )
    return synthesis, request, archive, html, completion


def _rows(*events):
    return [event.model_dump(mode="json") for event in events]


def test_projection_projector_accepts_partial_and_complete_lifecycle():
    synthesis, request, archive, html, completion = _lifecycle()
    partial = project_investigation_projection(
        _rows(synthesis, request, archive),
        execution_id=EXECUTION_ID,
        generation=GENERATION,
    )
    assert partial is not None and not partial.complete
    assert partial.synthesis_effect == archive and partial.html_effect is None
    complete = project_investigation_projection(
        _rows(synthesis, request, archive, html, completion),
        execution_id=EXECUTION_ID,
        generation=GENERATION,
    )
    assert complete is not None and complete.complete


def test_takeover_reuses_and_revalidates_prior_generation_receipts():
    events = [
        event.model_copy(update={"execution_generation": 1})
        for event in _lifecycle()
    ]
    completion = events[-1]
    events[-1] = completion.model_copy(
        update={
            "payload": completion.payload.model_copy(
                update={"effects_sha256": projection_effects_sha256(events[2], events[3])}
            )
        }
    )
    recovered = project_investigation_projection(
        _rows(*events), execution_id=EXECUTION_ID, generation=2
    )
    assert recovered is not None and recovered.complete


@pytest.mark.parametrize(
    "mutation", ["wrong_generation", "effect_before_request", "duplicate_effect", "bad_digest"]
)
def test_projection_projector_rejects_hostile_histories(mutation):
    synthesis, request, archive, html, completion = _lifecycle()
    events = [synthesis, request, archive, html, completion]
    if mutation == "wrong_generation":
        events[2] = archive.model_copy(update={"execution_generation": 3})
    elif mutation == "effect_before_request":
        events = [synthesis, archive, request, html, completion]
    elif mutation == "duplicate_effect":
        events.insert(3, archive.model_copy(update={"event_id": "evt-duplicate"}))
    else:
        payload = completion.payload.model_copy(update={"effects_sha256": "d" * 64})
        events[4] = completion.model_copy(update={"payload": payload})
    with pytest.raises(InvestigationProjectionConflict):
        project_investigation_projection(
            _rows(*events), execution_id=EXECUTION_ID, generation=GENERATION
        )


def test_effect_disposition_shape_is_closed():
    with pytest.raises(ValueError, match="requires proof"):
        InvestigationProjectionEffectRecordedPayload(
            projection_id="a" * 64,
            request_event_id="evt-request",
            effect="synthesis_archive",
            disposition="complete",
        )


def test_projection_failure_is_retryable_but_cannot_follow_completion():
    synthesis, request, archive, html, completion = _lifecycle()
    failure = prepare_typed_event(
        synthesis.investigation_id,
        InvestigationProjectionFailedPayload(
            projection_id=request.payload.projection_id,
            request_event_id=request.event_id,
            effect="html_artifact",
            failure_code="mutation_failed",
        ),
        event_id=investigation_projection_event_id(
            request.payload.projection_id, "failed-html_artifact-mutation_failed"
        ),
        parent_event_id=request.event_id,
        execution_generation=GENERATION,
    )
    recovered = project_investigation_projection(
        _rows(synthesis, request, failure, archive, html, completion),
        execution_id=EXECUTION_ID,
        generation=GENERATION,
    )
    assert recovered is not None and recovered.complete
    assert recovered.failures == (failure,)
    with pytest.raises(InvestigationProjectionConflict):
        project_investigation_projection(
            _rows(synthesis, request, archive, html, completion, failure),
            execution_id=EXECUTION_ID,
            generation=GENERATION,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "scenario",
    [
        "success",
        "html_verify_fail",
        "archive_retry",
        "archive_receipt_retry",
        "html_receipt_retry",
        "completion_retry",
    ],
)
async def test_paid_projection_replay_skips_completed_effects(
    tmp_path, monkeypatch, scenario
):
    authority, _ = _authority(tmp_path)
    holder = "f" * 64
    _, lease, acquired = claim_investigation_execution_authorized(
        authority,
        holder_digest=holder,
        now_ms=time.time_ns() // 1_000_000,
        ttl_ms=60_000,
    )
    assert acquired
    synthesis = prepare_typed_event(
        authority.investigation_id,
        SynthesizeDeliveredPayload.model_validate(json.loads(_SYNTHESIZER_RESPONSE)),
        event_id="evt-paid-synthesis",
        execution_generation=lease.generation,
    )
    append_event_once_authorized(authority, synthesis)
    ctx = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
        synthesis=synthesis.payload,
        synthesis_event_id=synthesis.event_id,
        synthesis_emitted_at=synthesis.emitted_at,
        execution_id=lease.execution_id,
    )
    calls = {"archive": 0, "html": 0}

    def archive(_ctx):
        calls["archive"] += 1
        if scenario == "archive_retry" and calls["archive"] == 1:
            raise RuntimeError("archive unavailable")
        return "syn-authorized"

    def html(_ctx):
        calls["html"] += 1
        return ("not_configured", "", None)

    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._deposit_synthesis_to_substrate", archive
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._maybe_export_research_artifact_after_complete",
        html,
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._verify_synthesis_projection_effect",
        lambda *args, **kwargs: True,
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._verify_html_projection_effect",
        lambda *args, **kwargs: scenario != "html_verify_fail",
    )
    broadcaster = EventBroadcaster()
    broadcaster.bind_event_authority(synthesis.event_id, authority)
    if scenario.endswith("receipt_retry") or scenario == "completion_retry":
        import orchestration.loop_one.orchestrator as orchestrator_module

        original_broadcast_emit = orchestrator_module.broadcast_emit
        injected = False

        async def fail_one_receipt(*args, **kwargs):
            nonlocal injected
            payload = args[2]
            matching_effect = (
                isinstance(payload, InvestigationProjectionEffectRecordedPayload)
                and (
                    (scenario == "archive_receipt_retry" and payload.effect == "synthesis_archive")
                    or (scenario == "html_receipt_retry" and payload.effect == "html_artifact")
                )
            )
            matching_completion = scenario == "completion_retry" and isinstance(
                payload, InvestigationProjectionCompletedPayload
            )
            if not injected and (matching_effect or matching_completion):
                injected = True
                raise RuntimeError("simulated process loss before receipt append")
            return await original_broadcast_emit(*args, **kwargs)

        monkeypatch.setattr(orchestrator_module, "broadcast_emit", fail_one_receipt)
    with investigation_execution_context(
        authority, generation=lease.generation, holder_digest=holder
    ):
        if scenario == "html_verify_fail":
            with pytest.raises(RuntimeError, match="failed durable verification"):
                await _project_success_outputs(ctx, broadcaster)
            snapshot = project_investigation_projection(
                trajectory_authorized_append_order(authority),
                execution_id=lease.execution_id,
                generation=lease.generation,
            )
            assert snapshot is not None and snapshot.completion is None
            assert len(snapshot.failures) == 1
            assert snapshot.failures[0].payload.failure_code == "verification_failed"
            return
        if scenario == "archive_retry":
            with pytest.raises(RuntimeError, match="archive unavailable"):
                await _project_success_outputs(ctx, broadcaster)
            failed = project_investigation_projection(
                trajectory_authorized_append_order(authority),
                execution_id=lease.execution_id,
                generation=lease.generation,
            )
            assert failed is not None and failed.completion is None
            assert failed.failures[0].payload.failure_code == "mutation_failed"
        if scenario.endswith("receipt_retry") or scenario == "completion_retry":
            with pytest.raises(RuntimeError, match="simulated process loss"):
                await _project_success_outputs(ctx, broadcaster)
            interrupted = project_investigation_projection(
                trajectory_authorized_append_order(authority),
                execution_id=lease.execution_id,
                generation=lease.generation,
            )
            assert interrupted is not None and interrupted.completion is None
        await _project_success_outputs(ctx, broadcaster)
        await _project_success_outputs(ctx, broadcaster)
    assert calls == {
        "archive": 2
        if scenario in {"archive_retry", "archive_receipt_retry"}
        else 1,
        "html": 2 if scenario == "html_receipt_retry" else 1,
    }
    snapshot = project_investigation_projection(
        trajectory_authorized_append_order(authority),
        execution_id=lease.execution_id,
        generation=lease.generation,
    )
    assert snapshot is not None and snapshot.complete
    with pytest.raises(ValueError, match="only HTML"):
        InvestigationProjectionEffectRecordedPayload(
            projection_id="a" * 64,
            request_event_id="evt-request",
            effect="synthesis_archive",
            disposition="not_configured",
        )


def test_synthesis_receipt_detects_durable_archive_tampering(tmp_path, monkeypatch):
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database_at_path

    database = tmp_path / "projection.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(database))
    init_database_at_path(str(database))
    authority, _ = _authority(tmp_path / "events")
    synthesis = prepare_typed_event(
        authority.investigation_id,
        SynthesizeDeliveredPayload.model_validate(json.loads(_SYNTHESIZER_RESPONSE)),
        event_id="evt-tamper-synthesis",
    )
    archived_coverage = {
        "schema_version": 1,
        "pack_schema_version": 2,
        "pack_content_hash": "c" * 64,
        "gather_plan_fingerprint": "d" * 64,
        "coverage": {
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": False,
            "partial_leaf_investigation_ids": [],
            "sources": [
                {"source": source, "succeeded_leaves": 1, "total_leaves": 1}
                for source in ("exa", "parallel", "arxiv", "substack")
            ],
            "leaves": [{
                "investigation_id": "leaf",
                "sources": [
                    {"source": source, "status": "succeeded", "document_count": 1}
                    for source in ("exa", "parallel", "arxiv", "substack")
                ],
            }],
        },
    }
    ctx = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
        synthesis=synthesis.payload,
        synthesis_event_id=synthesis.event_id,
        synthesis_emitted_at=synthesis.emitted_at,
        archived_source_coverage=archived_coverage,
    )
    synthesis_id = _deposit_synthesis_to_substrate(ctx)
    assert synthesis_id is not None
    input_sha256 = _projection_input_sha256(ctx)
    effect = prepare_typed_event(
        authority.investigation_id,
        InvestigationProjectionEffectRecordedPayload(
            projection_id="1" * 64,
            request_event_id="evt-request",
            effect="synthesis_archive",
            disposition="complete",
            effect_ref=synthesis_id,
            effect_sha256=hashlib.sha256(
                f"{synthesis_id}\x00{input_sha256}".encode()
            ).hexdigest(),
        ),
        event_id="evt-tamper-effect",
    )
    assert _verify_synthesis_projection_effect(ctx, effect, input_sha256=input_sha256)

    with connect_write(str(database), purpose="test-tamper-synthesis-coverage") as con:
        con.execute(
            "UPDATE syntheses SET substrate = ? WHERE synthesis_id = ?",
            ['{"tampered":true}', synthesis_id],
        )
    assert not _verify_synthesis_projection_effect(ctx, effect, input_sha256=input_sha256)
    with connect_write(str(database), purpose="test-restore-synthesis-coverage") as con:
        con.execute(
            "UPDATE syntheses SET substrate = ? WHERE synthesis_id = ?",
            [json.dumps(archived_coverage), synthesis_id],
        )
    assert _verify_synthesis_projection_effect(ctx, effect, input_sha256=input_sha256)

    with connect_write(str(database), purpose="test-tamper-synthesis") as con:
        con.execute(
            "UPDATE syntheses SET thesis = ? WHERE synthesis_id = ?",
            ['{"tampered":true}', synthesis_id],
        )
    assert not _verify_synthesis_projection_effect(ctx, effect, input_sha256=input_sha256)


@pytest.mark.parametrize("with_inherited", [False, True])
def test_rehydration_restores_archived_source_coverage(
    tmp_path, monkeypatch, with_inherited
):
    from orchestration.loop_one.rehydration import InvestigationRehydrationConflict
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database_at_path
    from substrate.graph.tenancy import GraphTenancyState, transition_graph_tenancy_state

    database = tmp_path / "rehydrate-coverage.duckdb"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(database))
    init_database_at_path(str(database))
    authority, _ = _authority(tmp_path / "events-rehydrate")
    synthesis = prepare_typed_event(
        authority.investigation_id,
        SynthesizeDeliveredPayload.model_validate(json.loads(_SYNTHESIZER_RESPONSE)),
        event_id="evt-rehydrate-coverage-synthesis",
        execution_generation=1,
    )
    append_event_once_authorized(authority, synthesis)
    archived_coverage = {
        "schema_version": 1,
        "pack_schema_version": 2,
        "pack_content_hash": "c" * 64,
        "gather_plan_fingerprint": "d" * 64,
        "coverage": {
            "mode": "authorized_multi_source",
            "evidence_complete": True,
            "partial": False,
            "partial_leaf_investigation_ids": [],
            "sources": [
                {"source": source, "succeeded_leaves": 1, "total_leaves": 1}
                for source in ("exa", "parallel", "arxiv", "substack")
            ],
            "leaves": [{
                "investigation_id": "leaf",
                "sources": [
                    {"source": source, "status": "succeeded", "document_count": 1}
                    for source in ("exa", "parallel", "arxiv", "substack")
                ],
            }],
        },
    }
    if with_inherited:
        archived_coverage.update({
            "schema_version": 2,
            "pack_schema_version": 3,
            "inherited_reuse": {
                "leaves": [{
                    "investigation_id": "leaf",
                    "state": "legacy_unqualified",
                    "injected_unit_count": 2,
                    "qualifications": [],
                }]
            },
        })
    original = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
        synthesis=synthesis.payload,
        synthesis_event_id=synthesis.event_id,
        synthesis_emitted_at=synthesis.emitted_at,
        archived_source_coverage=archived_coverage,
    )
    assert _deposit_synthesis_to_substrate(original) is not None
    with connect_write(str(database), purpose="scope-rehydration-coverage") as con:
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.SHADOW,
        )

    recovered = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
    )
    _rehydrate_archived_source_coverage(recovered)

    assert recovered.archived_source_coverage == archived_coverage
    assert recovered.artifact_source_coverage == archived_coverage["coverage"]
    assert recovered.artifact_inherited_reuse == archived_coverage.get("inherited_reuse")

    conflicting = InvestigationContext(
        investigation_id=authority.investigation_id,
        question="Q",
        authority=authority,
        archived_source_coverage={
            **archived_coverage,
            "pack_content_hash": "e" * 64,
        },
    )
    with pytest.raises(
        InvestigationRehydrationConflict,
        match="process and archive source coverage conflict",
    ):
        _rehydrate_archived_source_coverage(conflicting)
