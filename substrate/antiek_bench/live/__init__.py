"""Antiek-bench live: append-only journal, hard budget, call runner.

One measured production wedge — realized spend, crash recovery, and
idempotency consequences of one append-only record.  Does not replace
the existing scoring truth or Antiek's dispatch authority.

Public surface:

* **LiveCallRecord** — deterministic-identity call record (frozen dataclass)
* **Journal** — fsync-backed JSONL append/replay with torn-tail recovery
* **HardBudget** — cap enforcement from journal state
* **LiveCallRunner** — budget-gated call execution with injected timeout
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
from .wedge_config import BENCH_ROLE, LiveWedgeConfig, validate_live_suite

__all__ = [
    "HardBudget",
    "Journal",
    "JournalCorruptionError",
    "LiveCallRecord",
    "LiveCallRunner",
    "ProviderResult",
    "Status",
    "TimeoutRunner",
    "BENCH_ROLE",
    "LiveWedgeConfig",
    "deterministic_call_id",
    "validate_live_suite",
]
