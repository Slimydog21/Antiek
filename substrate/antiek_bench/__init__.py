"""Antiek-bench core — offline task-differentiated model suite (package C).

Public surface:

* **Suite** — versioned question set with task classes (distill, synthesize, …)
* **Run** — offline scores via injectable stub providers; week_id + suite_version
* **Rewrite** — usage-pattern propose → explicit approve/promote only
* **Summary** — HTML human view of a completed run (PDF never required)

Does not auto-switch production traffic. Does not call live multi-provider APIs.
"""

from __future__ import annotations

from .rewrite import (
    SuiteProposal,
    approve_and_promote,
    propose_suite_delta,
)
from .run import BenchRunResult, TaskScore, run_suite
from .store import BenchStore, InMemoryBenchStore
from .suite import (
    SuiteDefinition,
    SuiteItem,
    SuiteRegistry,
    TaskClass,
    active_suite,
    default_core_suite,
    get_suite,
    register_suite,
)
from .summary import project_run_html

__all__ = [
    "BenchRunResult",
    "BenchStore",
    "InMemoryBenchStore",
    "SuiteDefinition",
    "SuiteItem",
    "SuiteProposal",
    "SuiteRegistry",
    "TaskClass",
    "TaskScore",
    "active_suite",
    "approve_and_promote",
    "default_core_suite",
    "get_suite",
    "project_run_html",
    "propose_suite_delta",
    "register_suite",
    "run_suite",
]
