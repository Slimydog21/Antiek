"""Cohort analysis middleware (Sprint 5 day 2-3 migration).

Direct migration of Researchmaxx ``scripts/cohort.py`` (360 LOC). The
analysis function is pure — DB loading is the operator's concern.
The ``syntheses`` and ``outcomes`` tables landed in
``substrate/graph/schema.py`` (Sprint 10 day 4-5); a cohort-specific
DB loader is not yet wired (no consumer driving it).

What shipped:

- ``CohortSynthesisRow`` + ``CohortOutcomeRow`` input dataclasses
  (types.py).
- ``analyze(cohort, outcomes_by_synthesis)`` pure function computing
  the four cohort dimensions (analysis.py).

What's genuinely deferred:

- DB loader (``_load_cohort`` / ``_outcomes_by_synthesis`` in the
  upstream script). The tables exist in ``substrate/graph/schema.py``;
  wiring awaits a consumer.
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
