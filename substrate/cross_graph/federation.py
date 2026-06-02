"""Cross-graph federation (Sprint 30+, master-spec §13.9 Phase 3).

Lets investigations cite content across user public-graph
contributions. Each cross-graph reference is recorded with
provenance so attribution + rev-share flow correctly per §13.9.

The outbound-citation primitive (``federate_outbound_citation``) is
the cross-instance gate: it requires a TRUSTED partner from the
``partner_identity`` registry and emits an HMAC-signed token the
partner verifies before accepting the citation. This is what unlocks
the Sprint 30+ thread-1 "two instances federate one slice"
exit criterion."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .partner_identity import (
    PartnerRegistry,
    generate_partner_token,
    is_partner_trusted,
)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class FederationConfig:
    """Per-installation federation policy. Controls who can federate
    against this substrate (and vice versa)."""

    allowed_partner_substrates: tuple[str, ...] = ()
    require_opt_in_for_outbound_citations: bool = True
    require_attribution_for_outbound_citations: bool = True


@dataclass(frozen=True)
class CrossGraphReference:
    """A citation from User B's investigation to User A's public note.

    Recorded as a first-class graph reference; attribution events
    that route revenue to User A via the existing §13.9 Stripe
    Connect path consume this reference shape."""

    reference_id: str
    referencing_user_id: str  # whose investigation cites
    referencing_investigation_id: str
    referenced_user_id: str  # whose public note is cited
    referenced_note_id: str
    federated_substrate_id: str | None  # None for same-substrate; non-None for federation
    cited_at: str = field(default_factory=_now_iso)


def federate_search(
    *,
    topic_query: str,
    local_results: list[dict],
    federated_partner_results: dict[str, list[dict]],
    config: FederationConfig,
) -> list[dict]:
    """Merge local search results with federated partner results.

    For each partner substrate listed in config.allowed_partner_substrates,
    incorporate their results, tagging each with the partner substrate_id
    for attribution routing.
    """
    merged = [{"source_substrate": "local", **r} for r in local_results]
    for partner_id, partner_results in federated_partner_results.items():
        if partner_id not in config.allowed_partner_substrates:
            continue
        for r in partner_results:
            merged.append({"source_substrate": partner_id, **r})
    return merged


def record_cross_graph_citation(
    *,
    referencing_user_id: str,
    referencing_investigation_id: str,
    referenced_user_id: str,
    referenced_note_id: str,
    federated_substrate_id: str | None = None,
) -> CrossGraphReference:
    """Record a cross-graph citation. Returns the reference handle.
    The attribution pipeline picks this up and routes 70% of any
    attached ad revenue to referenced_user_id per §13.9."""
    return CrossGraphReference(
        reference_id=f"xref-{uuid.uuid4().hex[:12]}",
        referencing_user_id=referencing_user_id,
        referencing_investigation_id=referencing_investigation_id,
        referenced_user_id=referenced_user_id,
        referenced_note_id=referenced_note_id,
        federated_substrate_id=federated_substrate_id,
    )


# ── Outbound federation (Sprint 30+ thread 1) ───────────────────────


@dataclass(frozen=True)
class FederatedOutboundCitation:
    """A cross-instance citation packaged for transmission to a partner
    substrate. Carries the bare ``CrossGraphReference`` plus the
    revenue-routing fields the partner needs to attribute payouts
    correctly on their side."""

    reference: CrossGraphReference
    partner_id: str
    partner_substrate_url: str
    revenue_routing_handle: str
    signed_token: str


class FederationGateError(Exception):
    """Raised when a cross-instance federation operation is attempted
    against a non-TRUSTED partner, or when the operator's
    FederationConfig disallows the operation outright."""


# Optional callback the substrate fires after a successful outbound.
# Typed loosely (``Callable[[FederatedOutboundCitation], None]``) so
# both the event-emit bridge AND an offline analyzer can use the same
# hook shape. Audit-side wiring belongs to the caller, not to the
# substrate primitive — same posture as ``ad_inventory/payout.py``'s
# router/decisions split.
OutboundEmittedHook = Callable[["FederatedOutboundCitation"], None]


def federate_outbound_citation(
    *,
    config: FederationConfig,
    partner_registry: PartnerRegistry,
    partner_id: str,
    referencing_user_id: str,
    referencing_investigation_id: str,
    referenced_user_id: str,
    referenced_note_id: str,
    revenue_routing_handle: str,
    referenced_user_opted_in: bool,
    referenced_user_attribution_consented: bool,
    nonce: str | None = None,
    on_emitted: OutboundEmittedHook | None = None,
) -> FederatedOutboundCitation:
    """Federate a citation outbound to a partner substrate.

    Refuses unless:
      1. partner_id is in config.allowed_partner_substrates
      2. partner is TRUSTED in partner_registry
      3. referenced user has opted in (when required by config)
      4. attribution metadata present (when required by config)

    On success builds a ``CrossGraphReference``, signs an outbound
    token with the partner's shared secret, returns the packaged
    ``FederatedOutboundCitation``. If ``on_emitted`` is provided, it
    fires after the bundle is built — the audit-event bridge wires
    in via this hook.
    """
    if partner_id not in config.allowed_partner_substrates:
        raise FederationGateError(
            f"partner_id {partner_id!r} is not in the operator's "
            f"allowed_partner_substrates ({config.allowed_partner_substrates!r}); "
            "federation refused at the config layer"
        )

    partner = partner_registry.latest(partner_id)
    if partner is None:
        raise FederationGateError(
            f"partner_id {partner_id!r} is not registered in the "
            "partner_registry; federation refused"
        )
    if not is_partner_trusted(partner_registry, partner_id):
        raise FederationGateError(
            f"partner_id {partner_id!r} is in state {partner.state.value!r}; "
            "federation refused — only TRUSTED partners may receive "
            "outbound citations"
        )

    if (
        config.require_opt_in_for_outbound_citations
        and not referenced_user_opted_in
    ):
        raise FederationGateError(
            f"referenced_user_id {referenced_user_id!r} has not opted in "
            "to outbound federation per FederationConfig "
            "require_opt_in_for_outbound_citations=True"
        )

    if (
        config.require_attribution_for_outbound_citations
        and not referenced_user_attribution_consented
    ):
        raise FederationGateError(
            f"referenced_user_id {referenced_user_id!r} has not consented "
            "to attribution being carried in outbound citations per "
            "FederationConfig require_attribution_for_outbound_citations=True"
        )

    reference = CrossGraphReference(
        reference_id=f"xref-{uuid.uuid4().hex[:12]}",
        referencing_user_id=referencing_user_id,
        referencing_investigation_id=referencing_investigation_id,
        referenced_user_id=referenced_user_id,
        referenced_note_id=referenced_note_id,
        federated_substrate_id=partner_id,
    )

    payload: dict[str, Any] = {
        "op_kind": "outbound_citation",
        "reference_id": reference.reference_id,
        "referencing_user_id": referencing_user_id,
        "referencing_investigation_id": referencing_investigation_id,
        "referenced_user_id": referenced_user_id,
        "referenced_note_id": referenced_note_id,
        "revenue_routing_handle": revenue_routing_handle,
        "nonce": nonce or uuid.uuid4().hex,
    }
    token = generate_partner_token(
        shared_secret_hex=partner.shared_secret_hex,
        payload=payload,
    )

    citation = FederatedOutboundCitation(
        reference=reference,
        partner_id=partner_id,
        partner_substrate_url=partner.substrate_url,
        revenue_routing_handle=revenue_routing_handle,
        signed_token=token,
    )
    if on_emitted is not None:
        on_emitted(citation)
    return citation
