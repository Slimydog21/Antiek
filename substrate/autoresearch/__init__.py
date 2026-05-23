"""Autoresearch — Sprint 30+ thread 5: config sweeps.

Per `docs/integration_autoresearch.md` Wedge 3 + the Sprint 30+ doc:
DEFER until ≥ 500 graded outcomes in cohort per §14.1. Sprint 30+ is
the earliest realistic moment that condition holds.

This module is the substrate scaffold:

- `wedge3_sweep.py` — nightly sweep over context-pack composition +
  dispatch-tier routing, ranked against the outcomes table; outputs
  a `proposed_config_delta` for operator review
- `proposal.py` — typed ConfigProposal + OperatorVerdict (accept,
  reject, modify); persistence shape for review traceability

Activation discipline:
- Sweep only runs when the cohort outcomes ≥ COHORT_MIN_OUTCOMES (500)
- Promotion ONLY by explicit operator approval; no auto-promotion ever
  per the Loop 3 unlock criteria
- Every proposed delta is reproducible from `(cohort_window, baseline_config,
  sweep_axes, scoring_function)` — no operator review against opaque output
"""

from .proposal import (
    ConfigProposal,
    OperatorVerdict,
    OperatorVerdictKind,
    SweepAxes,
    CohortWindow,
    ProposalLedger,
)
from .wedge3_sweep import (
    COHORT_MIN_OUTCOMES,
    SweepInput,
    SweepResult,
    SweepCandidate,
    run_sweep,
    rank_candidates,
)

__all__ = [
    "COHORT_MIN_OUTCOMES",
    "CohortWindow",
    "ConfigProposal",
    "OperatorVerdict",
    "OperatorVerdictKind",
    "ProposalLedger",
    "SweepAxes",
    "SweepCandidate",
    "SweepInput",
    "SweepResult",
    "rank_candidates",
    "run_sweep",
]
