"""v41 event-schema contract tests for D2 anchored comments.

Pins the schema version bump, the exact shared-enum strings, and every
documented payload conditional: required highlight provenance digest
(including the empty-array fixture), pre-boundary cancellation, dispatch
completion pointers, and owner role completion digests.
"""

from __future__ import annotations

import hashlib

import pydantic
import pytest

from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    AgentWorkD2TransitionedPayload,
    ArtifactHighlightCreatedPayload,
    D2QueueTransitionReason,
    DeliverableHtmlEditedPayload,
    DispatchErrorCode,
    DispatchRefusalCode,
    Event,
    FeedbackDispatchCompletedPayload,
    FeedbackDispatchRefusedPayload,
    HighlightColor,
    InvestigationSpawnedFromPayload,
    InvestigationStartRequestedPayload,
    LoopOneChildRole,
    OwnerLaunchRoleCompletedPayload,
    ProviderUnknownReason,
    RoleEventReason,
)

HEX = "a" * 64


def test_schema_version_is_exactly_41() -> None:
    assert EVENT_SCHEMA_VERSION == 41


def test_shared_enum_exact_strings() -> None:
    assert [reason.value for reason in ProviderUnknownReason] == [
        "transport_timeout",
        "provider_disconnect",
        "process_crash_after_boundary",
        "receipt_unavailable",
    ]
    assert [reason.value for reason in D2QueueTransitionReason] == [
        "leased",
        "sent",
        "provider_boundary_crossed",
        "invalid_command_result",
        "validation_retry_requeue",
        "result_checkpointed",
        "settled",
        "failed_terminal",
        "cancelled_not_sent",
    ]
    assert [reason.value for reason in RoleEventReason] == [
        "started",
        "provider_disconnect",
        "result_checkpointed",
        "settled",
        "failed_terminal",
        "cancelled_not_sent",
    ]
    assert [code.value for code in DispatchErrorCode] == [
        "provider_result_missing",
        "authority_receipt_mismatch",
        "owner_child_failed",
        "publication_recovery_required",
        "budget_exceeded",
        "provider_call_failed",
        "invalid_command_result",
    ]
    assert [code.value for code in DispatchRefusalCode] == [
        "no_budget",
        "unsupported_action",
        "owner_model_unavailable",
        "authority_receipt_mismatch",
    ]
    assert [color.value for color in HighlightColor] == [
        "essential",
        "supporting",
        "disputed",
        "question",
        "agent",
    ]
    assert {role.value for role in LoopOneChildRole} == {
        "decomposer",
        "evidence_retriever",
        "parameter_extractor",
        "connector",
        "synthesizer",
        "knowledge_extractor",
    }


def _highlight(**overrides: object) -> ArtifactHighlightCreatedPayload:
    fields = {
        "thread_id": "t-1",
        "item_id": "i-1",
        "artifact_id": "art-1",
        "artifact_version": 1,
        "artifact_content_sha256": HEX,
        "artifact_source_sha256": HEX,
        "anchor_node_id": "node-1",
        "highlight_color": "essential",
        "provenance_digest_sha256": hashlib.sha256(b"[]").hexdigest(),
    }
    fields.update(overrides)
    return ArtifactHighlightCreatedPayload(**fields)  # type: ignore[arg-type]


def test_highlight_requires_provenance_digest() -> None:
    with pytest.raises(pydantic.ValidationError):
        _highlight(provenance_digest_sha256=None)


def test_zero_ref_highlight_hashes_exact_empty_array_json() -> None:
    payload = _highlight()
    assert payload.provenance_digest_sha256 == hashlib.sha256(b"[]").hexdigest()


def test_dispatch_refusal_rejects_values_outside_closed_enum() -> None:
    fields = {
        "dispatch_id": "d-1",
        "thread_id": "t-1",
        "owner_user_id": "owner-a",
        "action": "edit_in_place",
        "artifact_id": "art-1",
        "artifact_version": 1,
        "artifact_content_sha256": HEX,
        "artifact_source_sha256": HEX,
        "operation_id": "op-1",
        "refusal_code": "no_budget",
    }
    assert FeedbackDispatchRefusedPayload(**fields).refusal_code == "no_budget"
    for invalid in ("budget_exceeded", "arbitrary", "\n"):
        with pytest.raises(pydantic.ValidationError):
            FeedbackDispatchRefusedPayload(**{**fields, "refusal_code": invalid})


def _dispatch(**overrides: object) -> FeedbackDispatchCompletedPayload:
    fields = {
        "dispatch_id": "d-1",
        "thread_id": "t-1",
        "owner_user_id": "owner-a",
        "action": "edit_in_place",
        "artifact_id": "art-1",
        "artifact_version": 1,
        "artifact_content_sha256": HEX,
        "artifact_source_sha256": HEX,
        "outcome": "cancelled",
        "attempt_no": 0,
        "actual_cents": 0,
    }
    fields.update(overrides)
    return FeedbackDispatchCompletedPayload(**fields)  # type: ignore[arg-type]


def test_attempt_no_zero_only_for_pre_boundary_cancellation() -> None:
    assert _dispatch().outcome == "cancelled"
    with pytest.raises(pydantic.ValidationError, match="pre-boundary"):
        _dispatch(outcome="succeeded")


def test_succeeded_edit_requires_result_and_resolution_pointer() -> None:
    with pytest.raises(pydantic.ValidationError, match="succeeded edit"):
        _dispatch(outcome="succeeded", attempt_no=1)
    ok = _dispatch(
        outcome="succeeded", attempt_no=1, result_sha256=HEX, resolution_event_id="rev-1"
    )
    assert ok.resolution_event_id == "rev-1"


def test_succeeded_branch_requires_both_child_pointers() -> None:
    with pytest.raises(pydantic.ValidationError, match="succeeded branch"):
        _dispatch(outcome="succeeded", attempt_no=1, action="branch_research")
    ok = _dispatch(
        outcome="succeeded",
        attempt_no=1,
        action="branch_research",
        child_investigation_id="ci-1",
        child_start_event_id="cse-1",
    )
    assert ok.child_start_event_id == "cse-1"


def test_failed_and_cancelled_require_null_pointers() -> None:
    with pytest.raises(pydantic.ValidationError, match="pointers null"):
        _dispatch(outcome="failed", attempt_no=1, resolution_event_id="rev-1")


def _role_completed(**overrides: object) -> OwnerLaunchRoleCompletedPayload:
    fields = {
        "owner_user_id": "owner-a",
        "launch_claim_id": "lc-1",
        "parent_dispatch_id": "d-1",
        "feedback_thread_id": "t-1",
        "child_investigation_id": "ci-1",
        "operation_id": "op-1",
        "role": "synthesizer",
        "run_id": "run-1",
        "authority_digest_sha256": HEX,
        "provider_id": "p-1",
        "model_id": "m-1",
        "source_handle": "sh-1",
        "outcome": "succeeded",
        "result_sha256": HEX,
        "provider_receipt_sha256": HEX,
        "actual_cents": 25,
    }
    fields.update(overrides)
    return OwnerLaunchRoleCompletedPayload(**fields)  # type: ignore[arg-type]


def test_role_succeeded_requires_result_and_receipt() -> None:
    with pytest.raises(pydantic.ValidationError, match="succeeded requires"):
        _role_completed(provider_receipt_sha256=None)


def test_role_failed_requires_closed_error_code() -> None:
    with pytest.raises(pydantic.ValidationError, match="DispatchErrorCode"):
        _role_completed(outcome="failed", result_sha256=None, provider_receipt_sha256=None)
    ok = _role_completed(
        outcome="failed",
        result_sha256=None,
        provider_receipt_sha256=None,
        error_code="budget_exceeded",
    )
    assert ok.error_code == "budget_exceeded"


def test_deliverable_edit_bounds_changed_node_count() -> None:
    fields = {
        "dispatch_id": "d-1",
        "feedback_thread_id": "t-1",
        "owner_user_id": "owner-a",
        "artifact_id": "art-1",
        "from_version": 1,
        "to_version": 2,
        "source_sha256": HEX,
        "from_content_sha256": HEX,
        "to_content_sha256": HEX,
        "changed_node_count": 20,
        "output_sha256": HEX,
        "resolution_event_id": "rev-1",
    }
    assert DeliverableHtmlEditedPayload(**fields).changed_node_count == 20
    with pytest.raises(pydantic.ValidationError):
        DeliverableHtmlEditedPayload(**{**fields, "changed_node_count": 21})


# --- v41 resolved-payload extension + v40 read adapter --------------------

from pydantic import TypeAdapter  # noqa: E402

from substrate.schemas.events import (  # noqa: E402
    FeedbackThreadResolvedPayload,
    FeedbackThreadResolvedPayloadV40,
    TypedPayload,
    resolve_feedback_thread_payload,
)

_TYPED_ADAPTER = TypeAdapter(TypedPayload)

_V40_ROW = {
    "action_type": "feedback.thread.resolved",
    "thread_id": "t-1",
    "artifact_id": "art-1",
    "artifact_version": 1,
    "reason": "operator_resolved",
}


def _v41_row(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "action_type": "feedback.thread.resolved",
        "thread_id": "t-1",
        "owner_user_id": "owner-a",
        "artifact_id": "art-1",
        "artifact_version": 1,
        "artifact_content_sha256": HEX,
        "artifact_source_sha256": HEX,
        "resolution_event_id": "evt-feedback-resolved-t-1",
        "reason": "operator_resolved",
    }
    row.update(overrides)
    return row


def test_v41_resolved_requires_full_tuple() -> None:
    assert FeedbackThreadResolvedPayload.model_validate(_v41_row()).owner_user_id == "owner-a"
    for missing in ("owner_user_id", "artifact_content_sha256", "artifact_source_sha256", "resolution_event_id"):
        row = dict(_v41_row())
        row.pop(missing)
        with pytest.raises(pydantic.ValidationError):
            FeedbackThreadResolvedPayload.model_validate(row)


def test_v41_resolved_accepts_edit_applied_reason() -> None:
    payload = FeedbackThreadResolvedPayload.model_validate(_v41_row(reason="edit_applied"))
    assert payload.reason == "edit_applied"


def test_v40_row_selected_as_adapter_with_null_pointer() -> None:
    adapter = resolve_feedback_thread_payload(40, dict(_V40_ROW))
    assert type(adapter) is FeedbackThreadResolvedPayloadV40
    assert adapter.resolution_event_id is None


def test_v40_row_rejected_by_v41_write_model() -> None:
    with pytest.raises(pydantic.ValidationError):
        FeedbackThreadResolvedPayload.model_validate(dict(_V40_ROW))


def test_legacy_resolution_cannot_be_reemitted_as_v41() -> None:
    with pytest.raises(pydantic.ValidationError):
        _TYPED_ADAPTER.validate_python(dict(_V40_ROW))


def test_newer_envelope_versions_parse_as_v41() -> None:
    for version in (41, 42):
        payload = resolve_feedback_thread_payload(version, _v41_row())
        assert type(payload) is FeedbackThreadResolvedPayload



def _d2_branch_lineage() -> dict[str, object]:
    return {
        "launch_kind": "d2_branch",
        "owner_user_id": "owner-a",
        "owner_operation_id": "owner-op-1",
        "dispatch_id": "dispatch-1",
        "parent_investigation_id": "inv-parent",
        "parent_artifact_id": "artifact-1",
        "parent_artifact_version": 2,
        "parent_artifact_content_sha256": HEX,
        "parent_artifact_source_sha256": "b" * 64,
        "feedback_thread_id": "thread-1",
        "child_investigation_id": "inv-child",
        "start_event_id": "evt-start-1",
        "spawn_context_sha256": "c" * 64,
    }


def test_d2_branch_start_and_spawn_require_complete_lineage_tuple() -> None:
    lineage = _d2_branch_lineage()
    start = InvestigationStartRequestedPayload(question="Why?", **lineage)
    spawned = InvestigationSpawnedFromPayload(**lineage)
    assert start.launch_kind == "d2_branch"
    assert spawned.spawn_context_sha256 == "c" * 64

    for field in (
        "owner_user_id",
        "owner_operation_id",
        "dispatch_id",
        "parent_investigation_id",
        "parent_artifact_id",
        "parent_artifact_version",
        "parent_artifact_content_sha256",
        "parent_artifact_source_sha256",
        "feedback_thread_id",
        "child_investigation_id",
        "start_event_id",
        "spawn_context_sha256",
    ):
        partial = {**lineage, field: None}
        with pytest.raises(pydantic.ValidationError, match="complete D2 branch lineage"):
            InvestigationStartRequestedPayload(question="Why?", **partial)
        with pytest.raises(pydantic.ValidationError, match="complete D2 branch lineage"):
            InvestigationSpawnedFromPayload(**partial)


def test_legacy_investigation_shapes_preserve_chase_fields_and_forbid_d2_fields() -> None:
    start = InvestigationStartRequestedPayload(
        question="legacy", parent_investigation_id="inv-parent", spawn_context="raw legacy"
    )
    spawned = InvestigationSpawnedFromPayload(
        parent_investigation_id="inv-parent", spawn_context="raw legacy"
    )
    assert start.launch_kind == "legacy"
    assert spawned.launch_kind == "legacy"
    for payload_type, base in (
        (InvestigationStartRequestedPayload, {"question": "legacy"}),
        (InvestigationSpawnedFromPayload, {"parent_investigation_id": "inv-parent"}),
    ):
        with pytest.raises(pydantic.ValidationError, match="legacy launch forbids D2 branch fields"):
            payload_type(**base, dispatch_id="dispatch-1")


def test_d2_branch_rejects_raw_spawn_context_and_bounds_question() -> None:
    with pytest.raises(pydantic.ValidationError, match="raw spawn_context"):
        InvestigationStartRequestedPayload(
            question="Why?", **_d2_branch_lineage(), spawn_context="secret raw text"
        )
    with pytest.raises(pydantic.ValidationError):
        InvestigationStartRequestedPayload(question="x" * 2001)


def test_agent_work_d2_transitioned_is_v41_typed_and_bounded() -> None:
    fields = {
        "event_schema_version": 41,
        "thread_id": "thread-1",
        "work_id": "work-1",
        "dispatch_id": "dispatch-1",
        "owner_user_id": "owner-a",
        "work_kind": "feedback_dispatch",
        "attempt_no": 1,
        "lease_id": "lease-1",
        "provider_boundary_crossed": True,
        "from_state": "sent",
        "to_state": "provider_unknown",
        "reason": "provider_boundary_crossed",
        "result_sha256": None,
        "provider_result_sha256": HEX,
        "provider_receipt_sha256": None,
        "attempt_actual_cents": 12,
        "emitted_at": "2026-08-30T00:00:00Z",
    }
    payload = AgentWorkD2TransitionedPayload(**fields)
    assert payload.action_type == "agent.work.d2_transitioned"
    envelope = Event(
        event_id="evt-1",
        investigation_id="inv-1",
        action_type=ActionType.AGENT_WORK_D2_TRANSITIONED,
        payload=payload,
        param_version="test",
        schema_version=41,
        emitted_at="2026-08-30T00:00:00Z",
    )
    assert envelope.schema_version == 41
    with pytest.raises(pydantic.ValidationError, match="requires schema_version=41"):
        Event(**{**envelope.model_dump(), "schema_version": 40})
    for field, value in (
        ("attempt_no", -1),
        ("attempt_actual_cents", -1),
        ("result_sha256", "A" * 64),
        ("event_schema_version", 40),
    ):
        with pytest.raises(pydantic.ValidationError):
            AgentWorkD2TransitionedPayload(**{**fields, field: value})



def test_d2_branch_envelopes_require_v41_but_legacy_shapes_remain_readable() -> None:
    d2 = InvestigationStartRequestedPayload(question="Why?", **_d2_branch_lineage())
    common = {
        "event_id": "evt-branch",
        "investigation_id": "inv-child",
        "action_type": ActionType.INVESTIGATION_START_REQUESTED,
        "param_version": "test",
        "emitted_at": "2026-08-30T00:00:00Z",
    }
    with pytest.raises(pydantic.ValidationError, match="requires schema_version=41"):
        Event(**common, payload=d2, schema_version=40)
    legacy = InvestigationStartRequestedPayload(question="legacy")
    assert Event(**common, payload=legacy, schema_version=40).schema_version == 40


def test_agent_work_d2_transition_action_is_in_typed_registry() -> None:
    assert ActionType.AGENT_WORK_D2_TRANSITIONED.value in TYPED_PAYLOAD_ACTION_TYPES



def test_d2_branch_owner_and_lineage_ids_are_bounded_ascii() -> None:
    for field, value in (("owner_user_id", "ownér"), ("owner_operation_id", "bad id")):
        with pytest.raises(pydantic.ValidationError, match="bounded ASCII|printable ASCII"):
            InvestigationStartRequestedPayload(
                question="Why?", **{**_d2_branch_lineage(), field: value}
            )
