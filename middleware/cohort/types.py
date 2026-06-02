"""Cohort-analysis input dataclasses.

These shapes are what ``analyze()`` consumes. They are deliberately
DB-agnostic — a thin loader (deferred to the slice that wires
``substrate/init_db.py`` to the syntheses/outcomes tables) is the only
place that touches DuckDB. The pure analysis function takes
pre-loaded data so it can be unit-tested with fixtures and reused
inside the substrate's middleware without a DB dependency.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class CohortSynthesisRow:
    """One archived synthesis row from the cohort.

    ``thesis`` is the parsed JSON shape (matches the upstream
    ``thesis_json`` column). The cohort analysis reads
    ``thesis.thesis_components[].claim`` + ``.confidence`` for
    calibration buckets, ``thesis.falsification_conditions[].
    specific_observable`` for specificity, and
    ``thesis.execution_risks[].risk`` for completeness.
    """

    synthesis_id: str
    synthesis_timestamp: str
    target_question: str
    status: str
    thesis: dict[str, Any] | None = None
    implicit_recommendation: str | None = None
    sector: str | None = None


@dataclass(frozen=True)
class CohortOutcomeRow:
    """One observation row from the cohort.

    The four sub-lists/object are the same JSON shapes the
    ``OutcomeRecordedPayload`` carries; analysis keeps them as raw
    dicts because that's what the upstream cohort logic operates on
    and avoids round-trip cost when input is already JSON.
    """

    synthesis_id: str
    thesis_outcomes: list[dict[str, Any]] = field(default_factory=list)
    falsification_outcomes: list[dict[str, Any]] = field(default_factory=list)
    execution_risk_outcomes: list[dict[str, Any]] = field(default_factory=list)
    decision_alignment: dict[str, Any] | None = None
