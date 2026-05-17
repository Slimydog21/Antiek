"""Backtest middleware (Sprint 5 day 2-3 scaffolding).

Direct migration of Researchmaxx ``scripts/backtest.py`` (243 LOC),
scaffold only — the load-bearing query path depends on a graph-loader
analogue of ``graph_at_time.diff_between`` plus an
``archive.load_synthesis`` extraction, neither of which has migrated.

What shipped:

- ``ArchivedSynthesis``, ``SupersededEdge``, ``ChunkTierChange``,
  ``BacktestReport`` dataclasses (types.py).
- ``project_superseded_edges`` / ``project_chunk_tier_changes`` /
  ``build_report`` pure projections (analysis.py).
- ``backtest()`` scaffold function that raises
  ``NotImplementedError`` until the DB layer migrates.

What's deferred:

- ``graph_at_time`` migration → enables the ``added/superseded``
  counts since synthesis_timestamp.
- ``middleware/archive/load_synthesis`` extraction.
- The CLI + markdown renderer.

The shape is fixed now so the cohort module + downstream consumers
can be wired against the same dataclasses without churn later.
"""

from .analysis import (
    backtest,
    build_report,
    project_chunk_tier_changes,
    project_superseded_edges,
)
from .db import (
    archived_synthesis_from_row,
    count_added_edges_since,
    count_superseded_edges_since,
    load_chunk_tier_changes_since,
    load_outcomes_for_synthesis,
    load_superseded_cited_edges,
)
from .types import (
    ArchivedSynthesis,
    BacktestReport,
    ChunkTierChange,
    SupersededEdge,
)

__all__ = [
    "ArchivedSynthesis",
    "SupersededEdge",
    "ChunkTierChange",
    "BacktestReport",
    "project_superseded_edges",
    "project_chunk_tier_changes",
    "build_report",
    "backtest",
    "archived_synthesis_from_row",
    "count_added_edges_since",
    "count_superseded_edges_since",
    "load_chunk_tier_changes_since",
    "load_outcomes_for_synthesis",
    "load_superseded_cited_edges",
]
