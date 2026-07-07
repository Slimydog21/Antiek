"""Temporal middleware — TTL-per-claim-class staleness handling.

Per architecture_notes §4 (preserved strengths): different claim classes
have different time-to-live values (market data goes stale fast;
fundamental-physics constants don't). This module applies the right TTL
based on the relation that produced the claim.

Flags are advisory — they queue the entity for refresh in the next
investigation that touches it. The temporal layer never auto-invalidates.
"""

from .staleness import (
    StalenessFlag,
    StalenessScanResult,
    StalenessVerdict,
    classify_relation,
    emit_staleness_flagged,
    emit_staleness_resolve,
    evaluate_staleness,
    new_flag_id,
    scan_graph_edge_staleness,
)

__all__ = [
    "StalenessFlag",
    "StalenessScanResult",
    "StalenessVerdict",
    "classify_relation",
    "evaluate_staleness",
    "new_flag_id",
    "emit_staleness_flagged",
    "emit_staleness_resolve",
    "scan_graph_edge_staleness",
]
