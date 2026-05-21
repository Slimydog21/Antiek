"""Cross-graph federation (Sprint 30+, master-spec §13.9 Phase 3).

Lets investigations cite content across user public-graph
contributions. Each cross-graph reference is recorded with
provenance so attribution + rev-share flow correctly per §13.9."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


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
    federated_substrate_id: Optional[str]  # None for same-substrate; non-None for federation
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
    federated_substrate_id: Optional[str] = None,
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
