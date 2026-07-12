"""Antiek-bench — model-quality measurement substrate.

The execution half (run candidate models on tasks → score → record) that turns
the recursive benchmark from mock fixtures into real, falsifiable evidence.

Pure and advisory: no provider calls, no routing authority, no network in the
scoring layer. ``scorer`` enforces the honesty keystone — a model never grades
its own output.
"""

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
    "HumanScorer",
    "RubricJudge",
    "RubricScorer",
    "ScoreVerdict",
    "ScoringMethod",
    "TaskFamily",
    "TaskRegistry",
    "TaskRegistryError",
    "load_default_registry",
]
