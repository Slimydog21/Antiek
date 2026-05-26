"""Continuous research daemon — Sprint 14+ per master-spec §7.3.

The daemon is the "second interpretation" of continuous-mode research:
a separate process that watches the event log for evidentiary_gap
records across all prior runs, scores them, spawns investigations
against the strongest open questions, and accumulates results into
a shared rolling document.

Public surface:

    from orchestration.continuous import (
        run_one_iteration,
        DaemonState,
        DaemonBudget,
        GapRegistry,
        ResearchTopic,
        score_gap,
        topic_id_for,
    )

The daemon's main loop is in ``daemon.py`` and is intentionally
parameterized so a single iteration can run in tests without sleeping.
The CLI entry is ``python -m orchestration.continuous``.

Cost-runaway mitigations per master-spec §7.4 — hard caps and decay
logic — are enforced in ``budget.py`` and ``scoring.py`` respectively.
"""

from __future__ import annotations

from .budget import DaemonBudget, DaemonBudgetError
from .daemon import (
    DaemonConfig,
    DaemonState,
    SpawnFn,
    no_op_spawn,
    run_one_iteration,
)
from .research_topic import ResearchTopic, topic_id_for
from .scoring import (
    GapEntry,
    GapRegistry,
    normalize_gap_description,
    score_gap,
)
from .suggestions import (
    DAEMON_SPAWN_POLICY_ID,
    DEFAULT_MAX_SUGGESTIONS,
    Suggestion,
    build_suggestions,
    policy_is_daemon,
)

__all__ = [
    "DAEMON_SPAWN_POLICY_ID",
    "DEFAULT_MAX_SUGGESTIONS",
    "DaemonBudget",
    "DaemonBudgetError",
    "DaemonConfig",
    "DaemonState",
    "GapEntry",
    "GapRegistry",
    "ResearchTopic",
    "SpawnFn",
    "Suggestion",
    "build_suggestions",
    "no_op_spawn",
    "normalize_gap_description",
    "policy_is_daemon",
    "run_one_iteration",
    "score_gap",
    "topic_id_for",
]
