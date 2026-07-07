"""Backtest middleware.

Direct migration of Researchmaxx ``scripts/backtest.py`` with Antiek
loaders and deterministic scoring layered on top.

What shipped:

- ``ArchivedSynthesis``, ``SupersededEdge``, ``ChunkTierChange``,
  ``BacktestReport`` dataclasses (types.py).
- ``project_superseded_edges`` / ``project_chunk_tier_changes`` /
  ``build_report`` pure projections (analysis.py).
- Read-only DB loaders plus ``backtest()`` for archived syntheses.
- ``score_backtest_report`` / ``score_backtest_cohort`` for the
  Phase-8 gate's bounded backtest signal.

What's deferred:

- The CLI + markdown renderer.
- Candidate-patch replay against a temporary skill overlay.

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
from .score import (
    DEFAULT_MIN_GRADED_OUTCOMES,
    BacktestCohortScore,
    BacktestScore,
    score_backtest_cohort,
    score_backtest_report,
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
    "DEFAULT_MIN_GRADED_OUTCOMES",
    "BacktestCohortScore",
    "BacktestScore",
    "score_backtest_cohort",
    "score_backtest_report",
]
