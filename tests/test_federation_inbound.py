"""Inbound federation handler tests (Sprint 30+ thread 1).

Includes a full outbound-to-inbound round trip between two simulated
substrate instances, which exercises the actual exit criterion:
"two Antiek instances federate one slice successfully."
"""

from __future__ import annotations

from substrate.cross_graph.federation import (
    FederationConfig,
    federate_outbound_citation,
)
from substrate.cross_graph.inbound import (
    DEFAULT_NONCE_RETENTION_SECONDS,
    InboundRejection,
    NonceLedger,
    accept_inbound_citation,
)
from substrate.cross_graph.partner_identity import (
    DEFAULT_CLOCK_SKEW_SECONDS,
    DEFAULT_TOKEN_TTL_SECONDS,
    PartnerRegistry,
    generate_partner_token,
    generate_shared_secret,
    register_partner,
    revoke_partner,
    trust_partner,
)

# ── Helpers ────────────────────────────────────────────────────────


def _instance(*, partner_id: str, partner_url: str, shared_secret: str) -> tuple[FederationConfig, PartnerRegistry]:
    """Build (config, registry) for one substrate instance with one
    trusted partner pre-loaded. Permissive policy on both flags."""
    reg = PartnerRegistry()
    register_partner(
        reg,
        display_name=partner_id,
        substrate_url=partner_url,
        shared_secret_hex=shared_secret,
        partner_id=partner_id,
    )
    trust_partner(reg, partner_id=partner_id)
    config = FederationConfig(
        allowed_partner_substrates=(partner_id,),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    return config, reg


def _outbound_kwargs(**overrides) -> dict:
    base = dict(
        partner_id="prt-b",
        referencing_user_id="user-a-local",
        referencing_investigation_id="inv-a-1",
        referenced_user_id="user-b-remote",
        referenced_note_id="note-b-1",
        revenue_routing_handle="opaque-b-handle",
        referenced_user_opted_in=True,
        referenced_user_attribution_consented=True,
    )
    base.update(overrides)
    return base


# ── End-to-end round trip ──────────────────────────────────────────


def test_two_instances_federate_one_slice_successfully():
    """Sprint 30+ thread 1 exit criterion at the substrate level."""
    secret = generate_shared_secret()

    # Instance A: knows about partner B
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b.example",
        shared_secret=secret,
    )
    # Instance B: knows about partner A (the sender from its perspective)
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a.example",
        shared_secret=secret,
    )
    ledger_b = NonceLedger()

    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a,
        **_outbound_kwargs(),
    )

    # Instance B receives the bundle and accepts it.
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=ledger_b,
        partner_id="prt-b", token=out.signed_token,
    )

    assert outcome.accepted is True
    assert outcome.rejection is None
    assert outcome.reference is not None
    assert outcome.reference.referencing_user_id == "user-a-local"
    assert outcome.reference.referenced_user_id == "user-b-remote"
    assert outcome.reference.federated_substrate_id == "prt-b"
    assert outcome.revenue_routing_handle == "opaque-b-handle"
    # Receiver mints its own reference_id (does not reuse sender's).
    assert outcome.reference.reference_id != out.reference.reference_id


# ── Replay defense ─────────────────────────────────────────────────


def test_replay_within_window_rejected():
    secret = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret,
    )
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret,
    )
    ledger = NonceLedger()
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    # First accept succeeds.
    first = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=ledger,
        partner_id="prt-b", token=out.signed_token,
    )
    assert first.accepted is True
    # Second accept of the SAME token must be rejected as replay.
    second = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=ledger,
        partner_id="prt-b", token=out.signed_token,
    )
    assert second.accepted is False
    assert second.rejection is InboundRejection.REPLAY_DETECTED


def test_nonce_ledger_prunes_after_retention():
    ledger = NonceLedger(retention_seconds=10)
    assert ledger.remember("n-1", now_unix=1000) is True
    # Same nonce within window → replay.
    assert ledger.remember("n-1", now_unix=1005) is False
    # After retention window the nonce is pruned and can be re-seen
    # (the token itself would already be expired in practice, but the
    # ledger contract is independent of token expiry).
    assert ledger.remember("n-1", now_unix=1100) is True


def test_separate_nonces_do_not_collide():
    ledger = NonceLedger()
    assert ledger.remember("n-a") is True
    assert ledger.remember("n-b") is True
    assert ledger.remember("n-a") is False  # replay of a
    assert ledger.remember("n-b") is False  # replay of b


# ── Refusal modes ──────────────────────────────────────────────────


def test_refuses_partner_not_in_allowed_list():
    secret = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret,
    )
    # Receiver config does NOT list prt-b as allowed.
    reg_b = PartnerRegistry()
    register_partner(
        reg_b, display_name="b", substrate_url="https://a",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    trust_partner(reg_b, partner_id="prt-b")
    config_b = FederationConfig(
        allowed_partner_substrates=(),  # empty — disallow all
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PARTNER_NOT_ALLOWED


def test_refuses_unregistered_partner():
    secret = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret,
    )
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    # Receiver has no partner registered, but config lists it as allowed.
    config_b = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=PartnerRegistry(),
        nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PARTNER_NOT_REGISTERED


def test_refuses_pending_handshake_partner():
    secret = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret,
    )
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    # Receiver knows the partner but has NOT trusted them yet.
    reg_b = PartnerRegistry()
    register_partner(
        reg_b, display_name="b", substrate_url="https://a",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    config_b = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PARTNER_NOT_TRUSTED


def test_refuses_revoked_partner():
    secret = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret,
    )
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret,
    )
    revoke_partner(reg_b, partner_id="prt-b", revocation_reason="leak")
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PARTNER_NOT_TRUSTED


def test_refuses_token_signed_with_wrong_secret():
    secret_a = generate_shared_secret()
    secret_b = generate_shared_secret()
    config_a, reg_a = _instance(
        partner_id="prt-b", partner_url="https://b", shared_secret=secret_a,
    )
    out = federate_outbound_citation(
        config=config_a, partner_registry=reg_a, **_outbound_kwargs(),
    )
    # Receiver has a DIFFERENT shared secret for this partner.
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret_b,
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.TOKEN_INVALID


def test_refuses_malformed_payload_missing_field():
    secret = generate_shared_secret()
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret,
    )
    # Hand-sign a token whose payload lacks revenue_routing_handle.
    bad_token = generate_partner_token(
        shared_secret_hex=secret,
        payload={
            "op_kind": "outbound_citation",
            "reference_id": "xref-1",
            "referencing_user_id": "u-a",
            "referencing_investigation_id": "inv-1",
            "referenced_user_id": "u-b",
            "referenced_note_id": "n-1",
            # revenue_routing_handle missing
            "nonce": "n-1",
        },
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=bad_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PAYLOAD_MALFORMED
    assert "revenue_routing_handle" in outcome.detail


def test_refuses_wrong_op_kind():
    secret = generate_shared_secret()
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret,
    )
    bad_token = generate_partner_token(
        shared_secret_hex=secret,
        payload={
            "op_kind": "handshake_ping",  # not outbound_citation
            "reference_id": "xref-1",
            "referencing_user_id": "u-a",
            "referencing_investigation_id": "inv-1",
            "referenced_user_id": "u-b",
            "referenced_note_id": "n-1",
            "revenue_routing_handle": "h",
            "nonce": "n-1",
        },
    )
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=bad_token,
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.PAYLOAD_MALFORMED


def test_outcome_detail_does_not_leak_token():
    secret = generate_shared_secret()
    config_b, reg_b = _instance(
        partner_id="prt-b", partner_url="https://a", shared_secret=secret,
    )
    # Junk token → TOKEN_INVALID outcome, detail must not contain the token.
    junk = "v1." + "aa" * 5 + ".0.0.0"
    outcome = accept_inbound_citation(
        config=config_b, partner_registry=reg_b, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=junk,
    )
    assert outcome.accepted is False
    assert junk not in outcome.detail
    assert secret not in outcome.detail


def test_default_nonce_retention_matches_token_validity():
    # The ledger's default retention is exactly TTL + skew so that a
    # nonce can never outlive its token.
    assert DEFAULT_NONCE_RETENTION_SECONDS == (
        DEFAULT_TOKEN_TTL_SECONDS + DEFAULT_CLOCK_SKEW_SECONDS
    )
