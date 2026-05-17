"""Source-tier middleware.

Three concerns:

- ``rules.py`` — the deterministic document_type → tier 1–5 classifier
  (spec §C.1) and the hedging-detection / downward-adjustment logic
  (spec §C.2-C.3).
- ``aggregate.py`` — the multi-source aggregation rule (spec §C.4):
  effective tier requires ``k`` independent sources at that tier or better.

All functions are pure. DB-touching helpers (bulk update of the
``documents.source_tier`` column, joined queries against the
``chunks_effective_tier`` view) are deferred until ``substrate/init_db.py``
migrates.
"""

from .aggregate import effective_tier
from .overrides_db import record_chunk_tier_override
from .rules import (
    DOCUMENT_TYPE_TIER,
    HEDGING_PATTERNS,
    adjust_tier_after_extraction,
    assign_tier_at_ingestion,
    classify,
    emit_tier_assigned,
    emit_tier_overridden,
    emit_tier_rewrite_bulk,
)

__all__ = [
    "classify",
    "assign_tier_at_ingestion",
    "adjust_tier_after_extraction",
    "effective_tier",
    "DOCUMENT_TYPE_TIER",
    "HEDGING_PATTERNS",
    "emit_tier_assigned",
    "emit_tier_overridden",
    "emit_tier_rewrite_bulk",
    "record_chunk_tier_override",
]
