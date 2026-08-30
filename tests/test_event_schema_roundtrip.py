"""Round-trip tests for the D2 v41 typed event payloads.

Every new v41 discriminator must construct, serialize, and re-validate
through the full typed union unchanged, with its exact action_type string.
"""

from __future__ import annotations

import hashlib
import subprocess
import typing
from pathlib import Path
from typing import Any

import pytest
from pydantic import TypeAdapter

from substrate.schemas.events import (
    ArtifactHighlightCreatedPayload,
    DeliverableHtmlEditedPayload,
    Event,
    FeedbackDispatchCompletedPayload,
    FeedbackDispatchProviderUnknownPayload,
    FeedbackDispatchRefusedPayload,
    FeedbackDispatchRequestedPayload,
    FeedbackThreadResolvedPayload,
    HighlightColor,
    LoopOneChildRole,
    OwnerLaunchRoleCompletedPayload,
    OwnerLaunchRoleProviderUnknownPayload,
    OwnerLaunchRoleStartedPayload,
    ProviderUnknownReason,
    TypedPayload,
)
from tools.codegen.emit_types import PAYLOAD_MODELS

HEX = "a" * 64


def _highlight() -> ArtifactHighlightCreatedPayload:
    return ArtifactHighlightCreatedPayload(
        thread_id="t-1",
        item_id="i-1",
        artifact_id="art-1",
        artifact_version=1,
        artifact_content_sha256=HEX,
        artifact_source_sha256=HEX,
        anchor_node_id="node-1",
        highlight_color=HighlightColor.QUESTION,
        provenance_digest_sha256=hashlib.sha256(b"[]").hexdigest(),
    )


def _dispatch_base() -> dict[str, Any]:
    return {
        "dispatch_id": "d-1",
        "thread_id": "t-1",
        "owner_user_id": "owner-a",
        "action": "edit_in_place",
        "artifact_id": "art-1",
        "artifact_version": 1,
        "artifact_content_sha256": HEX,
        "artifact_source_sha256": HEX,
    }


def _requested() -> FeedbackDispatchRequestedPayload:
    return FeedbackDispatchRequestedPayload(
        **_dispatch_base(),
        operation_id="op-1",
        work_id="w-1",
        authority_digest_sha256=HEX,
    )


def _refused() -> FeedbackDispatchRefusedPayload:
    return FeedbackDispatchRefusedPayload(
        **_dispatch_base(),
        operation_id="op-1",
        refusal_code="no_budget",
        remaining_budget_cents=0,
    )


def _provider_unknown() -> FeedbackDispatchProviderUnknownPayload:
    return FeedbackDispatchProviderUnknownPayload(
        **_dispatch_base(),
        operation_id="op-1",
        attempt_no=1,
        reason_code=ProviderUnknownReason.TRANSPORT_TIMEOUT,
    )


def _completed(action: str = "edit_in_place") -> FeedbackDispatchCompletedPayload:
    payload = _dispatch_base()
    payload["action"] = action
    return FeedbackDispatchCompletedPayload(
        **payload,
        outcome="succeeded",
        attempt_no=1,
        result_sha256=HEX,
        actual_cents=10,
        resolution_event_id="rev-1" if action == "edit_in_place" else None,
        child_investigation_id=None if action == "edit_in_place" else "ci-1",
        child_start_event_id=None if action == "edit_in_place" else "cse-1",
    )


def _edited() -> DeliverableHtmlEditedPayload:
    return DeliverableHtmlEditedPayload(
        dispatch_id="d-1",
        feedback_thread_id="t-1",
        owner_user_id="owner-a",
        artifact_id="art-1",
        from_version=1,
        to_version=2,
        source_sha256=HEX,
        from_content_sha256=HEX,
        to_content_sha256=HEX,
        changed_node_count=3,
        output_sha256=HEX,
        resolution_event_id="rev-1",
    )


def _resolved() -> FeedbackThreadResolvedPayload:
    return FeedbackThreadResolvedPayload(
        thread_id="t-1",
        owner_user_id="owner-a",
        artifact_id="art-1",
        artifact_version=1,
        artifact_content_sha256=HEX,
        artifact_source_sha256=HEX,
        resolution_event_id="evt-feedback-resolved-t-1",
    )


def _role_base() -> dict[str, Any]:
    return {
        "owner_user_id": "owner-a",
        "launch_claim_id": "lc-1",
        "parent_dispatch_id": "d-1",
        "feedback_thread_id": "t-1",
        "child_investigation_id": "ci-1",
        "operation_id": "op-1",
        "role": LoopOneChildRole.CONNECTOR,
        "run_id": "run-1",
        "authority_digest_sha256": HEX,
        "provider_id": "p-1",
        "model_id": "m-1",
        "source_handle": "sh-1",
    }


def _role_started() -> OwnerLaunchRoleStartedPayload:
    return OwnerLaunchRoleStartedPayload(**_role_base(), projected_max_cents=500)


def _role_unknown() -> OwnerLaunchRoleProviderUnknownPayload:
    return OwnerLaunchRoleProviderUnknownPayload(
        **_role_base(), reason_code=ProviderUnknownReason.RECEIPT_UNAVAILABLE
    )


def _role_completed() -> OwnerLaunchRoleCompletedPayload:
    return OwnerLaunchRoleCompletedPayload(
        **_role_base(),
        outcome="succeeded",
        result_sha256=HEX,
        provider_receipt_sha256=HEX,
        actual_cents=25,
    )


ALL_V41_PAYLOADS = [
    _highlight,
    _requested,
    _refused,
    _provider_unknown,
    _completed,
    lambda: _completed(action="branch_research"),
    _edited,
    _role_started,
    _role_unknown,
    _role_completed,
]

ADAPTER = TypeAdapter(TypedPayload)


@pytest.mark.parametrize("factory", ALL_V41_PAYLOADS)
def test_v41_payload_round_trips_through_union(factory) -> None:
    payload = factory()
    dumped = payload.model_dump()
    revived = ADAPTER.validate_python(dumped)
    assert type(revived) is type(payload)
    assert revived.model_dump() == dumped


def test_v41_action_type_strings_exact() -> None:
    expected = {
        "artifact.highlight.created",
        "feedback.dispatch.requested",
        "feedback.dispatch.refused",
        "feedback.dispatch.provider_unknown",
        "feedback.dispatch.completed",
        "deliverable.html.edited",
        "owner.launch.role.started",
        "owner.launch.role.provider_unknown",
        "owner.launch.role.completed",
    }
    actual = {factory().action_type for factory in ALL_V41_PAYLOADS}
    assert expected <= actual


@pytest.mark.parametrize("factory", [*ALL_V41_PAYLOADS, _resolved])
def test_d2_payloads_reject_v40_envelopes(factory) -> None:
    with pytest.raises(ValueError, match="schema_version=41"):
        Event(
            event_id="evt-1",
            investigation_id="inv-1",
            action_type=factory().action_type,
            payload=factory(),
            param_version="test",
            schema_version=40,
            emitted_at="2026-08-30T00:00:00Z",
        )


# --- codegen completeness + TS compile round-trip -------------------------


def test_codegen_registry_covers_typed_union() -> None:
    """The manual PAYLOAD_MODELS registry must track the union exactly."""
    union_names = {
        getattr(arg, "__name__", str(arg))
        for arg in typing.get_args(typing.get_args(TypedPayload)[0])
    }
    registry_names = {model.__name__ for model in PAYLOAD_MODELS}
    assert registry_names == union_names, (
        f"codegen drift: missing={union_names - registry_names} "
        f"stale={registry_names - union_names}"
    )


def test_v41_typescript_round_trip_compiles() -> None:
    """The generated TS must type v41 payloads and narrow the union."""
    worktree = Path(__file__).resolve().parents[1]
    tsc = None
    for candidate in (
        worktree / "apps/reading/node_modules/.bin/tsc",
        worktree.parents[1] / "platform/apps/reading/node_modules/.bin/tsc",
    ):
        if candidate.exists():
            tsc = candidate
            break
    if tsc is None:
        pytest.skip("no tsc available in worktree or platform checkout")

    result = subprocess.run(
        [
            str(tsc),
            "--noEmit",
            "--strict",
            "--target",
            "es2020",
            "--moduleResolution",
            "bundler",
            "--module",
            "esnext",
            str(worktree / "tests/fixtures/v41_ts_roundtrip.ts"),
        ],
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    # The harness asserts EVENT_SCHEMA_VERSION === 41 at runtime-compile level.
    types_ts = (worktree / "apps/reading/src/generated/types.ts").read_text()
    assert "EVENT_SCHEMA_VERSION = 41" in types_ts
    for discriminator in (
        '"artifact.highlight.created"',
        '"feedback.dispatch.completed"',
        '"owner.launch.role.completed"',
        '"deliverable.html.edited"',
    ):
        assert discriminator in types_ts
