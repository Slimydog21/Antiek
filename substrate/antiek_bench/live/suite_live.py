"""Live suite wiring — delegates keyword scoring and BenchStore persistence
to ``run_suite`` while the journal tracks spend, replay, and attribution.
"""

from __future__ import annotations

from ..store import BenchStore
from ..suite import SuiteDefinition
from .call_runner import TimeoutRunner
from .journal import Journal
from .live_run import (
    LiveRunResult,
)
from .wedge_config import WedgeConfig


def run_live_suite(
    *,
    config: WedgeConfig,
    week_id: str,
    suite: SuiteDefinition,
    store: BenchStore,
    journal: Journal,
    timeout_runner: TimeoutRunner,
    investigation_id: str = "bench-live",
) -> LiveRunResult:
    """High-level entry point: validate, run both models, return results.

    This is the thinnest possible wiring layer.  All scoring logic
    (keyword matching, mean computation) is delegated to ``run_suite``.
    All spend/replay logic is delegated to ``LiveCallRunner`` + ``Journal``.
    """
    from .live_run import run_all

    return run_all(
        config=config,
        week_id=week_id,
        suite=suite,
        store=store,
        journal=journal,
        timeout_runner=timeout_runner,
        investigation_id=investigation_id,
    )
