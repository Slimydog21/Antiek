"""Shared fixtures for services.notebooks tests.

Per-test DuckDB file with BOTH the substrate behavior schema AND
the notebooks schema applied. The fixture mirrors the pattern in
``substrate/behavior/tests/conftest.py`` so tests can grant consent +
emit + populate end-to-end.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator

import pytest


# Make sure the repo root is on sys.path. This file lives at
# services/notebooks/tests/conftest.py, so the root is three levels up.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from services.notebooks.persistence import (
    JSONPersistence,
    reset_default_persistence,
)
from services.notebooks.schema import init_notebooks_schema_at_path
from substrate.behavior.queue import BehaviorQueue, reset_default_queue
from substrate.behavior.schema import init_behavior_schema_at_path


@pytest.fixture
def combined_db(tmp_path) -> Iterator[str]:
    """Per-test DuckDB file with both substrate.behavior and
    services.notebooks schemas applied. Sets ``ANTIEK_DUCKDB_PATH``
    so all default-path lookups resolve here.
    """
    path = str(tmp_path / "spr08.duckdb")
    prev = os.environ.get("ANTIEK_DUCKDB_PATH")
    os.environ["ANTIEK_DUCKDB_PATH"] = path

    reset_default_queue()
    reset_default_persistence()

    # Order: behavior first (it creates behavior_events), then
    # notebooks (which has an FK-ish join on behavior_events.event_id
    # via reward_hook, but no hard FK; safe either way).
    init_behavior_schema_at_path(path)
    init_notebooks_schema_at_path(path)
    try:
        yield path
    finally:
        reset_default_queue()
        reset_default_persistence()
        if prev is None:
            os.environ.pop("ANTIEK_DUCKDB_PATH", None)
        else:
            os.environ["ANTIEK_DUCKDB_PATH"] = prev


@pytest.fixture
def behavior_queue(combined_db) -> Iterator[BehaviorQueue]:
    """Isolated queue bound to the per-test DB. Mirrors
    ``substrate/behavior/tests/conftest.py``."""
    q = BehaviorQueue(db_path=combined_db)
    q.start()
    try:
        yield q
    finally:
        q.shutdown(timeout_s=3.0)


@pytest.fixture
def persistence(combined_db) -> JSONPersistence:
    """JSON persistence bound to the per-test DB."""
    return JSONPersistence(db_path=combined_db)
