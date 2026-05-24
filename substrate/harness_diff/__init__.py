"""Harness-diff tracker — snapshot + diff the substrate's externally-visible surface."""

from substrate.harness_diff.diff import HarnessDiff, diff_snapshots
from substrate.harness_diff.snapshot import (
    HarnessSnapshot,
    capture_snapshot,
    load_snapshot,
    save_snapshot,
)

__all__ = [
    "HarnessDiff",
    "HarnessSnapshot",
    "capture_snapshot",
    "diff_snapshots",
    "load_snapshot",
    "save_snapshot",
]
