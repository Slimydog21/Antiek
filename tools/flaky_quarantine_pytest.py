"""Pytest hooks for the flaky-quarantine re-run harness.

Loaded ONLY when explicitly requested via ``-p tools.flaky_quarantine_pytest``.
Not part of default ``pytest tests/ -q`` runs.

Provides:
  * deterministic collection-order shuffle via ``FLAKY_QUARANTINE_SHUFFLE_SEED``
  * per-nodeid pass/fail recording via ``FLAKY_QUARANTINE_RESULTS_FILE`` (JSONL)
"""

from __future__ import annotations

import json
import os
import random
from pathlib import Path


def pytest_configure(config) -> None:
    config.addinivalue_line(
        "markers",
        "flaky_harness: internal marker for flaky-quarantine fixture suite",
    )


def pytest_collection_modifyitems(config, items) -> None:
    seed_raw = os.environ.get("FLAKY_QUARANTINE_SHUFFLE_SEED")
    if seed_raw is None:
        return
    seed = int(seed_raw)
    # Stable pre-sort so the same seed always yields the same order.
    items.sort(key=lambda item: item.nodeid)
    rng = random.Random(seed)
    rng.shuffle(items)


def pytest_runtest_logreport(report) -> None:
    if report.when != "call":
        return
    results_path = os.environ.get("FLAKY_QUARANTINE_RESULTS_FILE")
    if not results_path:
        return
    record = {
        "nodeid": report.nodeid,
        "passed": report.passed,
        "failed": report.failed,
        "skipped": report.skipped,
    }
    path = Path(results_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")