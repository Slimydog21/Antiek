"""Inbox acquisition connector.

Ingests dated plain-text reading-stream files from ``~/research/inbox`` into
the graph as explicit ``personal_reading`` web articles.
"""
from __future__ import annotations

from .adapter import (
    InboxIngestSummary,
    IngestResult,
    SkipRecord,
    ingest_inbox_dir,
    ingest_inbox_file,
)

__all__ = [
    "IngestResult",
    "InboxIngestSummary",
    "SkipRecord",
    "ingest_inbox_file",
    "ingest_inbox_dir",
]
