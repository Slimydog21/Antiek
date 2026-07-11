"""Research spans — verbatim extractive spans with provenance and floor.

SPR-03 (Deep-Research Doctrine): synthesis consumes only verbatim,
attributed, budgeted extractive spans; weak result sets are discarded-
and-requeried or honestly refused.

Submodules:
    span    — ExtractiveSpan type with verbatim enforcement
    select  — query-aware selection with injectable ranker/extractor
    floor   — retrieval floor with visible outcomes
    assemble — synthesis boundary assembler (spans only)

Architecture (round 3 rework):
    - No global mutable authorization — private module token pattern.
    - Deterministic full SHA-256 span_ids.
    - DocumentRecord includes exact raw content; validated factory.
    - Store.put recomputes and verifies; Store.get returns content.
    - Assembler verifies span against stored content.
    - extract_select is the public composed API; extractor required.
    - SelectionResult invariant-safe; bound counter/accounting.
    - Budget covers EXACT text sent to synthesis (shared render_and_count).
    - All hashes full 64-char hex.
"""

from .assemble import (
    AssembledContext,
    AttributedSpan,
    DocumentRecord,
    DocumentStore,
    FloorAwareResult,
    InMemoryDocumentStore,
    assemble_from_spans,
    assemble_or_refuse,
    content_addressed_id,
    content_hash,
)
from .floor import (
    FLOOR_MAX_REQUERIES,
    FLOOR_MIN_SPANS,
    FLOOR_QUALITY_THRESHOLD,
    FloorTripTrace,
    InsufficientSources,
    Requery,
    check_floor,
    result_set_quality,
)
from .select import (
    DefaultRanker,
    DefaultTokenCounter,
    ExtractorProtocol,
    RankerProtocol,
    SelectionResult,
    TokenCounter,
    extract_select,
    render_and_count,
    render_context_text,
    render_span_text,
    span_budget_for_tier,
    span_budget_high,
    span_budget_low,
    span_budget_medium,
)
from .span import ExtractiveSpan

__all__ = [
    # span
    "ExtractiveSpan",
    # select
    "DefaultRanker",
    "DefaultTokenCounter",
    "ExtractorProtocol",
    "RankerProtocol",
    "SelectionResult",
    "TokenCounter",
    "extract_select",
    "render_and_count",
    "render_context_text",
    "render_span_text",
    "span_budget_for_tier",
    "span_budget_high",
    "span_budget_low",
    "span_budget_medium",
    # floor
    "FLOOR_MAX_REQUERIES",
    "FLOOR_MIN_SPANS",
    "FLOOR_QUALITY_THRESHOLD",
    "FloorTripTrace",
    "InsufficientSources",
    "Requery",
    "check_floor",
    "result_set_quality",
    # assemble
    "AssembledContext",
    "AttributedSpan",
    "DocumentRecord",
    "DocumentStore",
    "FloorAwareResult",
    "InMemoryDocumentStore",
    "assemble_from_spans",
    "assemble_or_refuse",
    "content_addressed_id",
    "content_hash",
]
