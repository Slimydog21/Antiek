"""AFF SPR-09 — the falsifiable compounding benchmark.

Measures cost-to-resolve on a frozen question set across a cold-graph control and
a warm-graph arm, reporting a signed warm-minus-cold delta with a confidence
interval over n runs - a benchmark allowed to come back null, zero, negative, or
invalid.

See ``README.md`` for the keystone finding (the host-local demo loop does not
consume the reuse pack, so the mock delta is ~0 and a live reuse-consuming run is
the operator-window measurement) and how this differs from
``compounding/verification/`` (growth-happened vs cost-got-cheaper).
"""

from .question_set import BenchmarkQuestion, QuestionSet, load_question_set
from .measure import CostToResolve, METRIC_NAMES, measure_investigation, measure_trajectory
from .harness import ArmResult, ColdSeed, IrrelevantSeed, WarmSeed, run_arm
from .aggregate import aggregate_comparison, bootstrap_ci, t_interval
from .result_schema import ArmComparison, BenchmarkResult, MetricDelta
from .validity import Verdict, decide
from .pilot import ProposedParameters, propose_parameters, run_pilot

__all__ = [
    "BenchmarkQuestion",
    "QuestionSet",
    "load_question_set",
    "CostToResolve",
    "METRIC_NAMES",
    "measure_investigation",
    "measure_trajectory",
    "ArmResult",
    "ColdSeed",
    "WarmSeed",
    "IrrelevantSeed",
    "run_arm",
    "aggregate_comparison",
    "bootstrap_ci",
    "t_interval",
    "ArmComparison",
    "BenchmarkResult",
    "MetricDelta",
    "Verdict",
    "decide",
    "ProposedParameters",
    "propose_parameters",
    "run_pilot",
]
