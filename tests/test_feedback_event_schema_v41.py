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
    ArtifactHighlightCreatedPayload,
    D2QueueTransitionReason,
    DeliverableHtmlEditedPayload,
    DispatchErrorCode,
    FeedbackDispatchCompletedPayload,
    HighlightColor,
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
