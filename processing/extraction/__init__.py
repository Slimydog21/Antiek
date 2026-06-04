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

# Reader SPR-02 — the document-model extractors. The text/markdown path
# (text_to_document / markdown_to_blocks) is dependency-light (markdown-it-py,
# the [extraction] extra); the PDF and arXiv paths are imported lazily by their
# own modules so a caller that only needs the text path does not require the
# [pdf] extra. Re-exported here so callers have one import surface alongside the
# legacy LLM chunk-extraction functions above (a different concern — chunks →
# graph nodes — kept distinct, not merged).
from .to_document_model import (
    ar5iv_html_to_blocks,
    arxiv_to_document,
    markdown_to_blocks,
    text_to_document,
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
    # Reader SPR-02 — document-model extractors
    "text_to_document",
    "markdown_to_blocks",
    "ar5iv_html_to_blocks",
    "arxiv_to_document",
]
