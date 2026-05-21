"""Wired-hook tests for federation primitives (Sprint 30+ thread 1).

Confirms ``federate_outbound_citation`` fires the ``on_emitted`` hook
exactly once on success, and ``accept_inbound_citation`` fires the
``on_outcome`` hook exactly once for EVERY outcome (accepted AND
refused) so the audit trail is complete by construction."""

from __future__ import annotations

import pytest

from substrate.cross_graph.event_emit import (
    make_broadcasting_inbound_hook,
)
from substrate.cross_graph.federation import (
    FederationConfig,
    FederationGateError,
    federate_outbound_citation,
)
from substrate.cross_graph.inbound import (
    InboundCitationOutcome,
    InboundRejection,
    NonceLedger,
    accept_inbound_citation,
)
from substrate.cross_graph.partner_identity import (
    PartnerRegistry,
    generate_shared_secret,
    register_partner,
    trust_partner,
)
from substrate.schemas.events import (
    ActionType,
    Event,
    FederationInboundCitationAcceptedPayload,
    FederationInboundCitationRefusedPayload,
)


def _trusted_partner() -> tuple[FederationConfig, PartnerRegistry, str]:
    secret = generate_shared_secret()
    reg = PartnerRegistry()
    register_partner(
        reg, display_name="B", substrate_url="https://b.example",
        shared_secret_hex=secret, partner_id="prt-b",
    )
    trust_partner(reg, partner_id="prt-b")
    config = FederationConfig(
        allowed_partner_substrates=("prt-b",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    return config, reg, secret


def _outbound_kwargs(**overrides):
    base = dict(
        partner_id="prt-b",
        referencing_user_id="user-a",
        referencing_investigation_id="inv-a-1",
        referenced_user_id="user-b",
        referenced_note_id="note-b",
        revenue_routing_handle="opaque",
        referenced_user_opted_in=True,
        referenced_user_attribution_consented=True,
    )
    base.update(overrides)
    return base


# ── on_emitted (outbound) ──────────────────────────────────────────


def test_outbound_hook_fires_once_on_success():
    config, reg, _ = _trusted_partner()
    captured = []
    out = federate_outbound_citation(
        config=config, partner_registry=reg,
        on_emitted=lambda c: captured.append(c),
        **_outbound_kwargs(),
    )
    assert len(captured) == 1
    assert captured[0] is out
    assert captured[0].partner_id == "prt-b"


def test_outbound_hook_not_fired_on_refusal():
    config, reg, _ = _trusted_partner()
    config = FederationConfig(
        allowed_partner_substrates=(),  # disallow all
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    captured = []
    with pytest.raises(FederationGateError):
        federate_outbound_citation(
            config=config, partner_registry=reg,
            on_emitted=lambda c: captured.append(c),
            **_outbound_kwargs(),
        )
    assert captured == []


def test_outbound_hook_optional_no_op_when_none():
    config, reg, _ = _trusted_partner()
    # Should not raise even though no hook is provided.
    out = federate_outbound_citation(
        config=config, partner_registry=reg, **_outbound_kwargs(),
    )
    assert out.partner_id == "prt-b"


def test_outbound_hook_can_raise_to_signal_failure():
    """If the hook raises, the substrate lets it propagate (the
    outcome is undefined at that point — the operator's caller
    decides whether to swallow)."""
    config, reg, _ = _trusted_partner()

    def angry_hook(_c):
        raise RuntimeError("audit pipeline down")

    with pytest.raises(RuntimeError, match="audit pipeline down"):
        federate_outbound_citation(
            config=config, partner_registry=reg,
            on_emitted=angry_hook,
            **_outbound_kwargs(),
        )


# ── on_outcome (inbound) — fires on BOTH accept + refuse ───────────


def test_inbound_hook_fires_on_accept():
    config, reg, _ = _trusted_partner()
    out = federate_outbound_citation(
        config=config, partner_registry=reg, **_outbound_kwargs(),
    )
    captured = []
    outcome = accept_inbound_citation(
        config=config, partner_registry=reg, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
        on_outcome=lambda o, pid: captured.append((o, pid)),
    )
    assert len(captured) == 1
    assert captured[0][0] is outcome
    assert captured[0][1] == "prt-b"
    assert outcome.accepted is True


def test_inbound_hook_fires_on_refuse_too():
    """Critical: refused outcomes MUST fire the hook so the audit
    trail records the typed rejection. Silent drops would be a
    §13.7 audit gap."""
    config, reg, _ = _trusted_partner()
    captured: list[tuple[InboundCitationOutcome, str]] = []
    outcome = accept_inbound_citation(
        config=config, partner_registry=reg, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token="garbage",
        on_outcome=lambda o, pid: captured.append((o, pid)),
    )
    assert outcome.accepted is False
    assert outcome.rejection is InboundRejection.TOKEN_INVALID
    assert len(captured) == 1
    assert captured[0][0].rejection is InboundRejection.TOKEN_INVALID


def test_inbound_hook_fires_for_every_rejection_kind():
    """The hook must fire regardless of which gate fails."""
    captured = []

    def hook(outcome, pid):
        captured.append(outcome.rejection)

    # PARTNER_NOT_ALLOWED — empty allowed list
    config_a = FederationConfig(
        allowed_partner_substrates=(),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    accept_inbound_citation(
        config=config_a, partner_registry=PartnerRegistry(),
        nonce_ledger=NonceLedger(), partner_id="prt-x",
        token="x", on_outcome=hook,
    )

    # PARTNER_NOT_REGISTERED — config allows but registry empty
    config_b = FederationConfig(
        allowed_partner_substrates=("prt-x",),
        require_opt_in_for_outbound_citations=True,
        require_attribution_for_outbound_citations=True,
    )
    accept_inbound_citation(
        config=config_b, partner_registry=PartnerRegistry(),
        nonce_ledger=NonceLedger(), partner_id="prt-x",
        token="x", on_outcome=hook,
    )

    assert captured == [
        InboundRejection.PARTNER_NOT_ALLOWED,
        InboundRejection.PARTNER_NOT_REGISTERED,
    ]


def test_inbound_hook_optional_no_op_when_none():
    config, reg, _ = _trusted_partner()
    out = federate_outbound_citation(
        config=config, partner_registry=reg, **_outbound_kwargs(),
    )
    outcome = accept_inbound_citation(
        config=config, partner_registry=reg, nonce_ledger=NonceLedger(),
        partner_id="prt-b", token=out.signed_token,
    )
    assert outcome.accepted is True


# ── End-to-end: hooks integrated with event bridge ─────────────────


def test_hook_integration_with_broadcasting_inbound_hook():
    """The make_broadcasting_inbound_hook factory yields a hook that
    matches the on_outcome signature; wiring it in produces typed
    Events for every outcome the substrate emits."""
    config, reg, _ = _trusted_partner()
    out = federate_outbound_citation(
        config=config, partner_registry=reg, **_outbound_kwargs(),
    )
    emitted: list[Event] = []
    hook = make_broadcasting_inbound_hook(
        investigation_id="inv-x",
        broadcast=lambda e: emitted.append(e),
    )
    ledger = NonceLedger()
    # First accept → ACCEPTED event.
    accept_inbound_citation(
        config=config, partner_registry=reg, nonce_ledger=ledger,
        partner_id="prt-b", token=out.signed_token,
        on_outcome=hook,
    )
    # Replay → REFUSED event.
    accept_inbound_citation(
        config=config, partner_registry=reg, nonce_ledger=ledger,
        partner_id="prt-b", token=out.signed_token,
        on_outcome=hook,
    )

    assert len(emitted) == 2
    assert emitted[0].action_type == ActionType.FEDERATION_INBOUND_CITATION_ACCEPTED
    assert isinstance(emitted[0].payload, FederationInboundCitationAcceptedPayload)
    assert emitted[1].action_type == ActionType.FEDERATION_INBOUND_CITATION_REFUSED
    assert isinstance(emitted[1].payload, FederationInboundCitationRefusedPayload)
    assert emitted[1].payload.rejection == "replay_detected"
