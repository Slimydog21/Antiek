"""Monitoring mode — ambient research ("puttering") over the personal lane.

This package is the Personal-Reading Lane SPR-09 thin slice: a saved feed
(a ``MONITOR``) bound to a prior deep-research investigation, a resumable
``REFRESH`` that surfaces newly-ingested ``personal_reading`` content since
the last view, and a "puttering" read surface that lets the owner graze
those fresh items in full on the owner path.

It is a **read/query surface plus a resumable in-process refresh** — never
a daemon, scheduler, queue, or second writer. It composes the existing
machinery rather than reinventing a parallel lane:

* the ``monitors`` table created by
  :func:`substrate.graph.schema.ensure_schema`;
* the deterministic-id hash :func:`orchestration.continuous.research_topic.topic_id_for`;
* the embedding + cosine machinery in :mod:`substrate.graph.search`
  (``EmbeddingModel`` / ``cosine_similarity_sql``);
* the §16 single-writer coordinator :func:`runtime.db_lock.connect_write`;
* the owner-path read posture + ``/read/{document_id}`` open-route
  convention in :mod:`substrate.books.personal_space`;
* the non-attributable proof in
  :func:`substrate.collective_graph.eligibility.is_attribution_eligible`.

The full ambient-research product (learned ranker, multi-thread fan-in,
serendipity, always-on scheduling) is a deliberate north star, not built
here. See ``docs/decisions/monitoring-mode-north-star.md``.
"""
from __future__ import annotations

from orchestration.monitoring.monitor import (
    FeedItem,
    Monitor,
    RefreshResult,
    create_monitor,
    delete_monitor,
    list_monitors,
    putter_feed,
    refresh_monitor,
)

__all__ = [
    "FeedItem",
    "Monitor",
    "RefreshResult",
    "create_monitor",
    "delete_monitor",
    "list_monitors",
    "putter_feed",
    "refresh_monitor",
]
