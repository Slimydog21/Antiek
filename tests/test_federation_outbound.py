"""Outbound federation tests (Sprint 30+ thread 1).

Exercises ``federate_outbound_citation`` — the cross-instance gate
that refuses unless the partner is TRUSTED, the operator's
FederationConfig allows the partner, opt-in is present (when
required), and attribution consent is present (when required).
"""

from __future__ import annotations

import pytest

from substrate.cross_graph.federation import (
    FederationConfig,
    FederationGateError,
    federate_outbound_citation,
)
from substrate.cross_graph.partner_identity import (
    PartnerRegistry,
    generate_shared_secret,
    register_partner,
    revoke_partner,
    trust_partner,
    verify_partner_token,
)


def _trusted_partner(reg: PartnerRegistry, *, partner_id: str = "prt-x") -> str:
    """Helper: register + trust a partner, return its shared_secret_hex."""
    secret = generate_shared_secret()
    register_partner(
        reg,
        display_name="Partner X",
        substrate_url="https://x.example",
        shared_secret_hex=secret,
        partner_id=partner_id,
    )
    trust_partner(reg, partner_id=partner_id)
    return secret


def _permissive_config(*partners: str) -> FederationConfig:
    return FederationConfig(
        allowed_partner_substrates=partners,
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )


def _kwargs(**overrides) -> dict:
    base = dict(
        partner_id="prt-x",
        referencing_user_id="user-b",
        referencing_investigation_id="inv-1",
        referenced_user_id="user-a",
        referenced_note_id="note-1",
        revenue_routing_handle="opaque-handle-1",
        referenced_user_opted_in=True,
        referenced_user_attribution_consented=True,
        nonce="fixed-nonce",
    )
    base.update(overrides)
    return base


# ── Happy path ─────────────────────────────────────────────────────


def test_outbound_citation_happy_path_emits_verifiable_token():
    reg = PartnerRegistry()
    secret = _trusted_partner(reg)
    config = _permissive_config("prt-x")

    out = federate_outbound_citation(
        config=config, partner_registry=reg, **_kwargs(),
    )

    assert out.partner_id == "prt-x"
    assert out.partner_substrate_url == "https://x.example"
    assert out.revenue_routing_handle == "opaque-handle-1"
    assert out.reference.referencing_user_id == "user-b"
    assert out.reference.referenced_user_id == "user-a"
    assert out.reference.federated_substrate_id == "prt-x"

    # The partner-side verification round-trips with the same secret.
    payload = verify_partner_token(
        shared_secret_hex=secret, token=out.signed_token,
    )
    assert payload is not None
    assert payload["op_kind"] == "outbound_citation"
    assert payload["reference_id"] == out.reference.reference_id
    assert payload["revenue_routing_handle"] == "opaque-handle-1"
    assert payload["nonce"] == "fixed-nonce"


# ── Refusal gates ──────────────────────────────────────────────────


def test_refuses_partner_not_in_allowed_list():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    config = _permissive_config()  # empty allowed list
    with pytest.raises(FederationGateError) as ei:
        federate_outbound_citation(
            config=config, partner_registry=reg, **_kwargs(),
        )
    assert "allowed_partner_substrates" in str(ei.value)


def test_refuses_unregistered_partner():
    reg = PartnerRegistry()  # nothing registered
    config = _permissive_config("prt-x")
    with pytest.raises(FederationGateError) as ei:
        federate_outbound_citation(
            config=config, partner_registry=reg, **_kwargs(),
        )
    assert "not registered" in str(ei.value)


def test_refuses_pending_handshake_partner():
    reg = PartnerRegistry()
    secret = generate_shared_secret()
    register_partner(
        reg, display_name="P", substrate_url="https://x.example",
        shared_secret_hex=secret, partner_id="prt-x",
    )
    # NOTE: no trust_partner call → still PENDING_HANDSHAKE.
    config = _permissive_config("prt-x")
    with pytest.raises(FederationGateError) as ei:
        federate_outbound_citation(
            config=config, partner_registry=reg, **_kwargs(),
        )
    assert "TRUSTED" in str(ei.value)


def test_refuses_revoked_partner():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    revoke_partner(reg, partner_id="prt-x", revocation_reason="leak")
    config = _permissive_config("prt-x")
    with pytest.raises(FederationGateError):
        federate_outbound_citation(
            config=config, partner_registry=reg, **_kwargs(),
        )


def test_refuses_when_user_not_opted_in_and_required():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    config = FederationConfig(
        allowed_partner_substrates=("prt-x",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=False,
    )
    with pytest.raises(FederationGateError) as ei:
        federate_outbound_citation(
            config=config, partner_registry=reg,
            **_kwargs(referenced_user_opted_in=False),
        )
    assert "opted in" in str(ei.value)


def test_opt_in_check_skipped_when_config_disables():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    config = FederationConfig(
        allowed_partner_substrates=("prt-x",),
        require_opt_in_for_outbound_citations=False,
        require_attribution_for_outbound_citations=False,
    )
    # Citation succeeds even with opted_in=False because config relaxed it.
    out = federate_outbound_citation(
        config=config, partner_registry=reg,
        **_kwargs(referenced_user_opted_in=False),
    )
    assert out.reference.referenced_user_id == "user-a"


def test_refuses_when_attribution_not_consented_and_required():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    config = FederationConfig(
        allowed_partner_substrates=("prt-x",),
        require_opt_in_for_outbound_citations=False,
        require_attribution_for_outbound_citations=True,
    )
    with pytest.raises(FederationGateError) as ei:
        federate_outbound_citation(
            config=config, partner_registry=reg,
            **_kwargs(referenced_user_attribution_consented=False),
        )
    assert "attribution" in str(ei.value)


def test_nonce_default_is_unique_across_calls():
    reg = PartnerRegistry()
    _trusted_partner(reg)
    config = _permissive_config("prt-x")
    # nonce=None → uuid4 hex each call.
    kwargs = _kwargs()
    del kwargs["nonce"]
    a = federate_outbound_citation(
        config=config, partner_registry=reg, **kwargs,
    )
    b = federate_outbound_citation(
        config=config, partner_registry=reg, **kwargs,
    )
    secret = reg.latest("prt-x").shared_secret_hex
    pa = verify_partner_token(shared_secret_hex=secret, token=a.signed_token)
    pb = verify_partner_token(shared_secret_hex=secret, token=b.signed_token)
    assert pa["nonce"] != pb["nonce"]
    # And the references are independent.
    assert a.reference.reference_id != b.reference.reference_id
