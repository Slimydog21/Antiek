"""Sprint 19 multi-user substrate event payload tests."""

from __future__ import annotations

from datetime import datetime

from pydantic import TypeAdapter, ValidationError

from substrate.schemas import (
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    Event,
    GraphScopeChangedPayload,
    TypedPayload,
    UserIdentityAttachedPayload,
    UserRegisteredPayload,
)


def test_multi_user_action_types_are_typed():
    for action_type in (
        ActionType.USER_REGISTERED,
        ActionType.USER_IDENTITY_ATTACHED,
        ActionType.GRAPH_SCOPE_CHANGED,
    ):
        assert action_type.value in TYPED_PAYLOAD_ACTION_TYPES


def test_multi_user_payloads_roundtrip_through_typed_union():
    adapter = TypeAdapter(TypedPayload)
    payloads = [
        UserRegisteredPayload(
            user_id="user-1",
            email="reader@example.com",
            auth_provider="clerk",
            provider_subject="clerk|user-1",
            registered_at="2026-07-01T00:00:00Z",
        ),
        UserIdentityAttachedPayload(
            user_id="user-1",
            identity_provider="google",
            provider_subject="google-oauth2|abc",
            email="reader@example.com",
            attached_at="2026-07-01T00:01:00Z",
        ),
        GraphScopeChangedPayload(
            user_id="user-1",
            previous_scope="operator",
            new_scope="personal",
            changed_at="2026-07-01T00:02:00Z",
            changed_by="operator",
            reason="created personal graph",
        ),
    ]

    for payload in payloads:
        restored = adapter.validate_python(payload.model_dump())
        assert restored == payload


def test_multi_user_event_envelope_roundtrip():
    event = Event(
        event_id="evt-user-1",
        investigation_id="inv-multi-user-plumbing",
        action_type=ActionType.USER_REGISTERED,
        payload=UserRegisteredPayload(
            user_id="user-1",
            email=None,
            auth_provider="supabase",
            provider_subject="auth-user-1",
            registered_at="2026-07-01T00:00:00Z",
        ),
        param_version="test",
        emitted_at=datetime(2026, 7, 1, 0, 0, 0),
    )

    restored = Event.model_validate_json(event.model_dump_json())

    assert restored.action_type == ActionType.USER_REGISTERED
    assert isinstance(restored.payload, UserRegisteredPayload)
    assert restored.payload.user_id == "user-1"


def test_multi_user_payloads_reject_empty_user_id():
    try:
        UserRegisteredPayload(
            user_id="",
            email=None,
            auth_provider="clerk",
            provider_subject="clerk|empty",
            registered_at="2026-07-01T00:00:00Z",
        )
    except ValidationError as exc:
        assert "user_id" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected empty user_id to be rejected")
