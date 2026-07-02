"""Frozen Antiek-Unified sprint-lock.

The Unified lane is the integration layer that keeps Research, Read, Write,
and Speak behaving as one product. Its first sprint is the substrate contract
and lock: shared contract inventory, DRW citation lock, dependency DAG, and
the conformance harness that makes contract forks loud.

This lock mirrors the product-lane locks. Status changes are deliberate roadmap
events and must name their canonical verifier.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump on ANY change to UNIFIED_SPRINTS. Status changes are deliberate roadmap
# events, not prose-only handoffs.
UNIFIED_LOCK_VERSION: int = 6


@dataclass(frozen=True)
class UnifiedDeliverable:
    """A Unified sprint's frozen identity and observed build status."""

    sprint: int
    slug: str
    deliverable: str
    status: str = "planned"  # planned | live | provisional


UNIFIED_SPRINTS: dict[int, UnifiedDeliverable] = {
    1: UnifiedDeliverable(
        1,
        "substrate-contract-and-lock",
        "Substrate contract package, dependency DAG, and sprint locks",
        # Live: shared contract package/inventory, DRW sprint-lock citation
        # guard, cross-spec dependency DAG + critical path, conformance harness
        # with real negative tests, and roadmap lock consumption are covered by
        # unified-substrate-contract-lock.
        status="live",
    ),
    2: UnifiedDeliverable(
        2,
        "remote-exec-fanout",
        "Remote exec fanout",
        # Live: ratified research-only §16 carve-out, optional Daytona provider
        # seam, RemoteResearchRunner protocol parity, no-SDK-at-rest import,
        # fake-provider fanout/teardown/failure isolation, single-writer
        # promotion funnel under 20 leaves, realized-cost DispatchCall flow,
        # aggregate/per-research budget enforcement, host-local fallback, and
        # protocol-only launch call sites are covered by unified-remote-exec-fanout.
        status="live",
    ),
    3: UnifiedDeliverable(
        3,
        "seams-and-collisions",
        "Seams + collisions",
        # Live: six committed typed seams plus one provisional write-to-speak
        # seam, no-copy handoff guards, no-auto-loop shape, seam event parity,
        # voice single-owner collision guard, single escrow writer guard,
        # platform_authored/speak_derived publish gate, and flywheel seam
        # composition are covered by unified-seams-and-collisions.
        status="live",
    ),
    4: UnifiedDeliverable(
        4,
        "navigation-ia-taxonomy",
        "Navigation IA taxonomy",
        # Live: the single frontend workflow taxonomy, four-door NavRail
        # boundary, shared/More bucket, route-to-workflow resolver, honest
        # workflow stubs, bottom/left nav parity, and click/hotkey activation
        # parity are covered by unified-navigation-ia-taxonomy.
        status="live",
    ),
    5: UnifiedDeliverable(
        5,
        "coordination-gate-ledger",
        "Coordination gate ledger",
        # Live: the typed gate ledger parses docs/operator_gate_actions.md on
        # read, independent quick-status agreement catches source drift,
        # fixture mutation proves no stale state copy, the module has no write
        # path, per-product impacts are grounded, the 45-sprint roadmap/focus
        # is derived, the HTTP adapter serializes without duplicating state,
        # and the Coordination UI sanitizes/render gates + roadmap via
        # unified-coordination-gate-ledger.
        status="live",
    ),
    6: UnifiedDeliverable(
        6,
        "thread-navigation",
        "Thread navigation",
        # Live: thread reconstruction derives a read-only trajectory from
        # SPR-03 seam events, ordered/degenerated/provisional/unbuilt cases are
        # tested, the no-duplicate guard rejects forked ids and inline content,
        # the HTTP route serializes/refuses copied threads, and the frontend
        # breadcrumb/jump suppresses forked continuity while using SPR-04 IA via
        # unified-thread-navigation.
        status="live",
    ),
    7: UnifiedDeliverable(7, "cost-consent-surface", "Cost + consent surface"),
    8: UnifiedDeliverable(8, "flywheel-conformance", "Flywheel conformance"),
}


def resolve_unified_sprint(n: int) -> UnifiedDeliverable:
    """Resolve a Unified sprint number to its frozen deliverable."""
    try:
        return UNIFIED_SPRINTS[n]
    except KeyError:
        raise KeyError(
            f"Unified SPR-{n:02d} is not in the frozen sprint-lock "
            f"(UNIFIED_LOCK_VERSION={UNIFIED_LOCK_VERSION}; valid: "
            f"{sorted(UNIFIED_SPRINTS)})."
        ) from None
