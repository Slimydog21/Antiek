"""Cohort analysis middleware (Sprint 5 day 2-3 migration).

Direct migration of Researchmaxx ``scripts/cohort.py`` (360 LOC). The
analysis function is pure — DB loading is the operator's concern and
lands when ``substrate/init_db.py`` extends to the syntheses /
outcomes tables.

What shipped:

- ``CohortSynthesisRow`` + ``CohortOutcomeRow`` input dataclasses
  (types.py).
- ``analyze(cohort, outcomes_by_synthesis)`` pure function computing
  the four cohort dimensions (analysis.py).

What's deferred:

- DB loader (``_load_cohort`` / ``_outcomes_by_synthesis`` in the
  upstream script). Wires in alongside ``init_db`` migration.
- Markdown renderer (``_render_markdown``). HTML/markdown rendering
  is the operator-surface concern per the architecture's "structured
  everywhere the agent touches, HTML everywhere the human looks"
  rule — it ships with the operator CLI.
- The CLI itself.
"""

from .analysis import analyze
from .types import CohortOutcomeRow, CohortSynthesisRow

__all__ = [
    "CohortSynthesisRow",
    "CohortOutcomeRow",
    "analyze",
]
