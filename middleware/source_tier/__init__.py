"""Source-tier middleware.

Three concerns:

- ``rules.py`` — the deterministic document_type → tier 1–5 classifier
  (spec §C.1) and the hedging-detection / downward-adjustment logic
  (spec §C.2-C.3).
- ``aggregate.py`` — the multi-source aggregation rule (spec §C.4):
  effective tier requires ``k`` independent sources at that tier or better.

All functions are pure. The ``documents`` table and
``chunk_tier_overrides`` table landed in ``substrate/graph/schema.py``
(Sprint 10 day 4-5). The ``chunks_effective_tier`` view and a bulk
``documents.source_tier`` sweep are genuinely deferred: the view has no
inline consumer yet, and the bulk sweep needs numeric-vs-named tier
vocabulary reconciliation first.
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
