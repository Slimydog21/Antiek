"""Antiek Deep Research Bridge — substrate."""

from __future__ import annotations

from .db_path import (
    default_db_path,
    ensure_research_bridge_initialized,
)
from .schema import (
    ANTIEK_RESEARCH_BRIDGE_SCHEMA_V1_SQL,
    init_research_bridge,
    init_research_bridge_at_path,
)
from .source_detection import (
    KNOWN_SOURCES,
    SourceDetectionResult,
    detect_source,
)
from .ingest import (
    IngestResult,
    PASTE_DOCUMENT_TYPE,
    PasteEmptyError,
    PasteTooLargeError,
    ingest_paste,
    MAX_PASTE_BYTES,
)
from .paste_log import (
    list_paste_events,
    log_paste_event,
)
from .extractor import (
    EXTRACTOR_VERSION,
    ExtractedItem,
    ExtractionResult,
    ExtractorError,
    LlmCallResult,
    LlmCallable,
    StoredItem,
    extract_paste,
    list_insights,
    list_open_questions,
    render_prompt,
)
from .gap import (
    CASCADE_VERSION,
    CLUSTER_VERSION,
    GapCluster,
    GapFinderError,
    GapPrompt,
    GapRunResult,
    StoredCluster,
    StoredPrompt,
    StoredRun,
    find_gaps,
    list_gap_runs,
    read_gap_run,
    record_prompt_answer,
    record_prompt_signal,
    would_run_percentage,
)


__all__ = [
    "ANTIEK_RESEARCH_BRIDGE_SCHEMA_V1_SQL",
    "default_db_path",
    "ensure_research_bridge_initialized",
    "init_research_bridge",
    "init_research_bridge_at_path",
    "KNOWN_SOURCES",
    "SourceDetectionResult",
    "detect_source",
    "IngestResult",
    "PASTE_DOCUMENT_TYPE",
    "PasteEmptyError",
    "PasteTooLargeError",
    "ingest_paste",
    "MAX_PASTE_BYTES",
    "list_paste_events",
    "log_paste_event",
    "EXTRACTOR_VERSION",
    "ExtractedItem",
    "ExtractionResult",
    "ExtractorError",
    "LlmCallResult",
    "LlmCallable",
    "StoredItem",
    "extract_paste",
    "list_insights",
    "list_open_questions",
    "render_prompt",
    "CASCADE_VERSION",
    "CLUSTER_VERSION",
    "GapCluster",
    "GapFinderError",
    "GapPrompt",
    "GapRunResult",
    "StoredCluster",
    "StoredPrompt",
    "StoredRun",
    "find_gaps",
    "list_gap_runs",
    "read_gap_run",
    "record_prompt_answer",
    "record_prompt_signal",
    "would_run_percentage",
]
