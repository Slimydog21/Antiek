"""LLM extraction — chunks → typed graph nodes + attributed edges.

Sprint 3 Day 4-5: completes the substrate triangle. The wrestling
bridge populates chunks (Day 2-3), the grounder consumes them
(Day 3-4), extraction promotes chunks into typed nodes + edges ready
for cross-doc linking (Sprint 5).

See ``extract.py`` for the migration scope split.
"""

from .extract import (
    ANTIEK_NODE_TYPES,
    DEFAULT_GRAPH_SCOPE,
    DEFAULT_SOURCE_TIER,
    EXTRACTION_SYSTEM_PROMPT,
    ExtractedEdge,
    ExtractedNode,
    ExtractionResult,
    extract_from_chunk,
    parse_extraction_response,
)

__all__ = [
    "ANTIEK_NODE_TYPES",
    "DEFAULT_GRAPH_SCOPE",
    "DEFAULT_SOURCE_TIER",
    "EXTRACTION_SYSTEM_PROMPT",
    "ExtractedNode",
    "ExtractedEdge",
    "ExtractionResult",
    "parse_extraction_response",
    "extract_from_chunk",
]
