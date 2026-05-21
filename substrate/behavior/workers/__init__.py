"""Reward-proxy backfill workers (SPR-01 M5).

Three workers populate the three reward-proxy columns on
``behavior_events`` asynchronously. Their contracts are documented
in ``substrate/behavior/REWARD_PROXY.md``; the modules below are
their implementations.

State at SPR-01 closeout:
- ``reward_immediate`` — real implementation; runs against
  behavior_events alone.
- ``reward_medium`` — stub. Notebooks table empty until SPR-08.
- ``reward_deep`` — stub. Deliverables table not yet created.

The stubs check their join-dependency tables before running and
log-and-exit when those tables are missing or empty. This is the
M5 "handles empty gracefully" requirement.
"""

from .reward_deep import run_reward_deep_backfill
from .reward_immediate import (
    IMMEDIATE_WINDOW_S,
    run_reward_immediate_backfill,
)
from .reward_medium import run_reward_medium_backfill

__all__ = [
    "IMMEDIATE_WINDOW_S",
    "run_reward_deep_backfill",
    "run_reward_immediate_backfill",
    "run_reward_medium_backfill",
]
