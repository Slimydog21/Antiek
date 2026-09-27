"""Anchored highlights (anchor-first SPR-01): the anchor model + persistence.

A FloatMenu highlight becomes a durable, server-persisted passage anchor:
the proven NodeTextAnchor shape (substrate/feedback/domain.py — imported,
never forked), a DuckDB store under the write lock, server-authoritative pin
resolution, and the active/drifted/orphaned re-resolution ladder. Rights
truth at rest: a non-servable book's body text is never persisted.
"""

from substrate.books.highlights.resolve import (
    PinResolution,
    PinResolutionError,
    ReanchorReport,
    document_servable,
    reanchor_document,
    resolve_pin,
)
from substrate.books.highlights.schema import init_highlights_schema
from substrate.books.highlights.store import (
    AnchorRow,
    CreatePinCommand,
    HighlightSource,
    HighlightsStore,
    HighlightStatus,
)

__all__ = [
    "AnchorRow",
    "CreatePinCommand",
    "HighlightsStore",
    "HighlightSource",
    "HighlightStatus",
    "PinResolution",
    "PinResolutionError",
    "ReanchorReport",
    "document_servable",
    "init_highlights_schema",
    "reanchor_document",
    "resolve_pin",
]
