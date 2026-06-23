"""Federation event-emission tests (Sprint 30+ thread 1)."""

from __future__ import annotations

import pytest

from substrate.cross_graph.event_emit import (
    inbound_outcome_to_event,
    make_broadcasting_inbound_hook,
    make_broadcasting_partner_state_hook,
    outbound_citation_to_event,
    outbound_citation_to_payload,
    partner_registered_to_event,
    partner_registered_to_payload,
    partner_revoked_to_event,
    partner_revoked_to_payload,
    partner_trusted_to_event,
    partner_trusted_to_payload,
)
from substrate.cross_graph.federation import (
    FederationConfig,
    federate_outbound_citation,
)
from substrate.cross_graph.inbound import (
    InboundRejection,
    NonceLedger,
    accept_inbound_citation,
)
from substrate.cross_graph.partner_identity import (
    PartnerRegistry,
    PartnerTrustState,
    generate_shared_secret,
    register_partner,
    revoke_partner,
    trust_partner,
)
from substrate.schemas.events import (
    TYPED_PAYLOAD_ACTION_TYPES,
    ActionType,
    Event,
    FederationInboundCitationAcceptedPayload,
    FederationInboundCitationRefusedPayload,
    FederationOutboundCitationEmittedPayload,
    FederationPartnerRegisteredPayload,
    FederationPartnerRevokedPayload,
    FederationPartnerTrustedPayload,
)

# ── ActionType registration ────────────────────────────────────────


def test_federation_action_types_in_typed_payload_set():
    """Each federation action_type must be in TYPED_PAYLOAD_ACTION_TYPES
    so the event-log read-side reconstructs them as typed payloads,
    not as dict blobs."""
    for at in (
        ActionType.FEDERATION_PARTNER_REGISTERED,
        ActionType.FEDERATION_PARTNER_TRUSTED,
        ActionType.FEDERATION_PARTNER_REVOKED,
        ActionType.FEDERATION_OUTBOUND_CITATION_EMITTED,
        ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED,
        ActionType.FEDERATION_INBOUND_CITATION_REFUSED,
    ):
        assert at.value in TYPED_PAYLOAD_ACTION_TYPES


# ── Pure converters ────────────────────────────────────────────────


def _registered_record() -> object:
    reg = PartnerRegistry()
    return register_partner(
        reg,
        display_name="Partner Lab",
        substrate_url="https://lab.example",
        shared_secret_hex=generate_shared_secret(),
        partner_id="prt-lab",
    )


def test_partner_registered_payload_carries_audit_fields_only():
    rec = _registered_record()
    payload = partner_registered_to_payload(rec)
    assert isinstance(payload, FederationPartnerRegisteredPayload)
    assert payload.partner_id == "prt-lab"
    assert payload.display_name == "Partner Lab"
    assert payload.substrate_url == "https://lab.example"
    # The shared secret must never appear on the payload surface.
    serialized = payload.model_dump_json()
    assert rec.shared_secret_hex not in serialized
    assert "shared_secret" not in serialized


def test_partner_trusted_payload_round_trips():
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    trusted = trust_partner(reg, partner_id="prt-x", operator_notes="vetted")
    payload = partner_trusted_to_payload(trusted)
    assert isinstance(payload, FederationPartnerTrustedPayload)
    assert payload.partner_id == "prt-x"
    assert payload.operator_notes == "vetted"


def test_partner_revoked_payload_carries_reason():
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    trust_partner(reg, partner_id="prt-x")
    revoked = revoke_partner(
        reg, partner_id="prt-x", revocation_reason="leak",
    )
    payload = partner_revoked_to_payload(revoked)
    assert isinstance(payload, FederationPartnerRevokedPayload)
    assert payload.revocation_reason == "leak"


def test_partner_revoked_without_reason_raises():
    """Defensive: a record whose state == REVOKED but whose
    revocation_reason is None should never reach the converter."""
    # The state machine enforces this; we construct an invalid record
    # directly to confirm the converter complains.
    from substrate.cross_graph.partner_identity import PartnerSubstrate

    bad = PartnerSubstrate(
        partner_id="prt-bad",
        display_name="x",
        substrate_url="https://x",
        shared_secret_hex="aa",
        state=PartnerTrustState.REVOKED,
        registered_at="2026-01-01T00:00:00Z",
        last_state_change_at="2026-01-01T00:00:00Z",
        revocation_reason=None,
    )
    with pytest.raises(ValueError):
        partner_revoked_to_payload(bad)


# ── Outbound + inbound payload converters ──────────────────────────


def _outbound_outcome():
    secret = generate_shared_secret()
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="B", substrate_url="https://b",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    trust_partner(reg, partner_id="prt-b")
    config = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    return secret, federate_outbound_citation(
        config=config, partner_registry=reg,
        partner_id="prt-b",
        referencing_user_id="user-a",
        referencing_investigation_id="inv-a-1",
        referenced_user_id="user-b",
        referenced_note_id="note-b",
        revenue_routing_handle="opaque-handle",
        referenced_user_opted_in=True,
        referenced_user_attribution_consented=True,
        nonce="fixed-nonce",
    )


def test_outbound_payload_does_not_leak_signed_token():
    secret, citation = _outbound_outcome()
    payload = outbound_citation_to_payload(citation)
    assert isinstance(payload, FederationOutboundCitationEmittedPayload)
    serialized = payload.model_dump_json()
    assert citation.signed_token not in serialized
    assert "signed_token" not in serialized
    assert secret not in serialized


def test_outbound_payload_carries_routing_handle():
    _, citation = _outbound_outcome()
    payload = outbound_citation_to_payload(citation)
    assert payload.reference_id == citation.reference.reference_id
    assert payload.partner_id == "prt-b"
    assert payload.revenue_routing_handle == "opaque-handle"


def test_inbound_accepted_payload_round_trips():
    secret, citation = _outbound_outcome()
    # Receiver side
    reg_b = PartnerRegistry()
    register_partner(
        reg_b, display_name="B", substrate_url="https://a",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    trust_partner(reg_b, partner_id="prt-b")
    config_b = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=citation.signed_token,
    )
    assert outcome.accepted is True
    event = inbound_outcome_to_event(
        outcome, partner_id="prt-b", investigation_id="inv-receiver-1",
    )
    assert isinstance(event, Event)
    assert event.action_type == ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED
    assert isinstance(event.payload, FederationInboundCitationAcceptedPayload)
    assert event.payload.partner_id == "prt-b"
    assert event.payload.revenue_routing_handle == "opaque-handle"


def test_inbound_refused_payload_carries_typed_reason():
    # Receiver refuses because partner is unknown.
    config = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    outcome = accept_inbound_citation(
        config=config, partner_registry=PartnerRegistry(),
        nonce_ledger=NonceLedger(),
        partner_id="prt-b", token="anything",
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PARTNER_NOT_REGISTERED
    event = inbound_outcome_to_event(
        outcome, partner_id="prt-b", investigation_id="inv-receiver-1",
    )
    assert event.action_type == ActionType.FEDERATION_INBOUND_CITATION_REFUSED
    assert isinstance(event.payload, FederationInboundCitationRefusedPayload)
    assert event.payload.rejection == "partner_not_registered"
    # detail must not contain the (junk) token even if logged
    assert "anything" not in event.payload.detail


# ── Broadcaster hook factories ─────────────────────────────────────


def test_partner_state_hook_emits_right_type_for_each_state():
    emitted: list[Event] = []
    hook = make_broadcasting_partner_state_hook(
        investigation_id="inv-1", broadcast=lambda e: emitted.append(e),
    )
    reg = PartnerRegistry()
    rec = register_partner(
        reg, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    hook(rec)
    rec = trust_partner(reg, partner_id="prt-x")
    hook(rec)
    rec = revoke_partner(reg, partner_id="prt-x", revocation_reason="leak")
    hook(rec)

    types = [e.action_type for e in emitted]
    assert types == [
        ActionType.FEDERATION_PARTNER_REGISTERED,
        ActionType.FEDERATION_PARTNER_TRUSTED,
        ActionType.FEDERATION_PARTNER_REVOKED,
    ]


def test_inbound_hook_emits_for_both_accept_and_refuse():
    emitted: list[Event] = []
    hook = make_broadcasting_inbound_hook(
        investigation_id="inv-1", broadcast=lambda e: emitted.append(e),
    )
    secret, citation = _outbound_outcome()
    reg_b = PartnerRegistry()
    register_partner(
        reg_b, display_name="B", substrate_url="https://a",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    trust_partner(reg_b, partner_id="prt-b")
    config_b = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    ledger = NonceLedger()
    accepted = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=ledger,
        partner_id="prt-b", token=citation.signed_token,
    )
    hook(accepted, "prt-b")
    # Replay → refused.
    refused = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=ledger,
        partner_id="prt-b", token=citation.signed_token,
    )
    hook(refused, "prt-b")

    types = [e.action_type for e in emitted]
    assert types == [
        ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED,
        ActionType.FEDERATION_INBOUND_CITATION_REFUSED,
    ]
    # The refused event carries the typed reason.
    refused_payload = emitted[1].payload
    assert isinstance(refused_payload, FederationInboundCitationRefusedPayload)
    assert refused_payload.rejection == "replay_detected"


# ── Schema versioning ──────────────────────────────────────────────


def test_outbound_payload_action_type_discriminator_is_literal():
    """The discriminated union picks payloads by action_type literal.
    If a payload's literal drifts from its ActionType enum, the union
    parses it as a different type."""
    _, citation = _outbound_outcome()
    event = outbound_citation_to_event(
        citation, investigation_id="inv-1",
    )
    # Round-trip through JSON should preserve the payload subclass.
    raw = event.model_dump_json()
    parsed = Event.model_validate_json(raw)
    assert isinstance(parsed.payload, FederationOutboundCitationEmittedPayload)


def test_inbound_refused_payload_rejection_enum_is_strict():
    """The Literal[...] on rejection must reject any value outside the
    enumerated InboundRejection vocabulary."""
    with pytest.raises(Exception):
        FederationInboundCitationRefusedPayload(
            partner_id="prt-x",
            rejection="not_a_real_reason",  # type: ignore[arg-type]
            received_at="2026-05-21T00:00:00Z",
        )


def test_partner_registered_event_envelope_carries_investigation_id():
    rec = _registered_record()
    event = partner_registered_to_event(
        rec, investigation_id="inv-1",
    )
    assert event.investigation_id == "inv-1"
    assert event.action_type == ActionType.FEDERATION_PARTNER_REGISTERED


def test_partner_trusted_event_envelope_round_trip():
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    rec = trust_partner(reg, partner_id="prt-x")
    event = partner_trusted_to_event(rec, investigation_id="inv-1")
    raw = event.model_dump_json()
    parsed = Event.model_validate_json(raw)
    assert isinstance(parsed.payload, FederationPartnerTrustedPayload)
    assert parsed.payload.partner_id == "prt-x"


def test_partner_revoked_event_envelope_round_trip():
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    trust_partner(reg, partner_id="prt-x")
    rec = revoke_partner(
        reg, partner_id="prt-x", revocation_reason="leak",
    )
    event = partner_revoked_to_event(rec, investigation_id="inv-1")
    raw = event.model_dump_json()
    parsed = Event.model_validate_json(raw)
    assert isinstance(parsed.payload, FederationPartnerRevokedPayload)
    assert parsed.payload.revocation_reason == "leak"
