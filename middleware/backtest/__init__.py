"""Backtest middleware (Sprint 5 day 2-3 scaffolding, wired Sprint 10).

Direct migration of Researchmaxx ``scripts/backtest.py`` (243 LOC).
The load-bearing query path — ``graph_at_time.diff_between`` and
``archive.load_synthesis`` — landed in Sprint 10 day 4-5.
``backtest()`` is fully wired and called in production at
``interfaces/research/api/app.py:5364``.

What shipped (Sprint 5):

- ``ArchivedSynthesis``, ``SupersededEdge``, ``ChunkTierChange``,
  ``BacktestReport`` dataclasses (types.py).
- ``project_superseded_edges`` / ``project_chunk_tier_changes`` /
  ``build_report`` pure projections (analysis.py).

What shipped (Sprint 10 day 4-5):

- ``backtest()`` entry point — reads the archived synthesis, counts
  added/closed edges since its timestamp, loads cited-edges-superseded
  and tier-override changes, loads outcomes, and composes a
  ``BacktestReport``.
- DB helpers in ``db.py``: ``count_added_edges_since``,
  ``count_superseded_edges_since``, ``load_superseded_cited_edges``,
  ``load_chunk_tier_changes_since``, ``load_outcomes_for_synthesis``.
- Tables landed in ``substrate/graph/schema.py`` (the real schema home).

What remains genuinely deferred:

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
