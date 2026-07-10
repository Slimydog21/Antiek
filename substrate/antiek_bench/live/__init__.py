"""Antiek-bench live: append-only journal, hard budget, call runner,
fallback-free measured runner, and wedge configuration.

One measured production wedge — realized spend, crash recovery, and
idempotency consequences of one append-only record.  Does not replace
the existing scoring truth or Antiek's dispatch authority.

Public surface:

* **LiveCallRecord** — deterministic-identity call record (frozen dataclass)
* **Journal** — fsync-backed JSONL append/replay with torn-tail recovery
* **HardBudget** — cap enforcement from journal state
* **LiveCallRunner** — budget-gated call execution with injected timeout
* **WedgeConfig** — operator-validated two-model benchmark configuration
* **LiveRunResult** — result of one full wedge run across both models
* **build_bench_dispatch_config** — fallback-free DispatchConfig per model
* **run_all** — restart-safe measured benchmark orchestrator
* **run_live_suite** — thin high-level entry wiring scoring + journal
"""

from __future__ import annotations

from .budget import HardBudget
from .call_runner import LiveCallRunner, ProviderResult, TimeoutRunner
from .journal import (
    Journal,
    JournalCorruptionError,
    LiveCallRecord,
    Status,
    deterministic_call_id,
)
from .live_run import (
    LiveRunResult,
    ReconciliationRequiredError,
    build_bench_dispatch_config,
    deterministic_wedge_id,
    run_all,
)
from .suite_live import run_live_suite
from .wedge_config import ModelWedgeCandidate, WedgeConfig, validate_wedge_config

__all__ = [
    "HardBudget",
    "Journal",
    "JournalCorruptionError",
    "LiveCallRecord",
    "LiveCallRunner",
    "LiveRunResult",
    "ModelWedgeCandidate",
    "ProviderResult",
    "ReconciliationRequiredError",
    "Status",
    "TimeoutRunner",
    "WedgeConfig",
    "build_bench_dispatch_config",
    "deterministic_call_id",
    "deterministic_wedge_id",
    "run_all",
    "run_live_suite",
    "validate_wedge_config",
]
