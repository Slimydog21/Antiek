"""Antiek-bench — model-quality measurement substrate.

The execution half (run candidate models on tasks → score → record) that turns
the recursive benchmark from mock fixtures into real, falsifiable evidence.

Pure and advisory: no provider calls, no routing authority, no network in the
scoring layer. ``scorer`` enforces the honesty keystone — a model never grades
its own output. ``recorder`` is the tamper-evident dual-output bridge to the
recursive loop's two frozen consumers.
"""

from .recorder import (
    GENESIS_HASH,
    LedgerCorruption,
    RunRecord,
    UsageEvent,
    ViewRecord,
    append_to_ledger,
    read_ledger,
    record_verdict,
    week_incomplete,
    week_usage_events,
    week_view_records,
)
from .scorer import (
    ExactScorer,
    HumanScorer,
    RubricJudge,
    RubricScorer,
    ScoreVerdict,
    ScoringMethod,
)
from .task_registry import (
    BenchTask,
    TaskFamily,
    TaskRegistry,
    TaskRegistryError,
    load_default_registry,
)

__all__ = [
    "BenchTask",
    "ExactScorer",
    "GENESIS_HASH",
    "HumanScorer",
    "LedgerCorruption",
    "RubricJudge",
    "RubricScorer",
    "RunRecord",
    "ScoreVerdict",
    "ScoringMethod",
    "TaskFamily",
    "TaskRegistry",
    "TaskRegistryError",
    "UsageEvent",
    "ViewRecord",
    "append_to_ledger",
    "load_default_registry",
    "read_ledger",
    "record_verdict",
    "week_incomplete",
    "week_usage_events",
    "week_view_records",
]
