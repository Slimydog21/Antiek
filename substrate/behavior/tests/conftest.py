"""Shared fixtures for behavior-store tests.

Provides per-test tmp DuckDB files + an isolated ``BehaviorQueue``
tied to that file so tests never collide on the production DB
path. The conftest is local to ``substrate/behavior/tests/`` so it
doesn't leak into the top-level ``tests/`` tree.
"""

from __future__ import annotations

import os
import sys
from typing import Iterator

import pytest

# Make sure the repo root is on sys.path so the imports below resolve
# when pytest is invoked from arbitrary working dirs.
_REPO_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
)
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from substrate.behavior.queue import BehaviorQueue, reset_default_queue
from substrate.behavior.schema import init_behavior_schema_at_path


@pytest.fixture
def behavior_db(tmp_path) -> Iterator[str]:
    """Per-test DuckDB file pre-initialized with the behavior schema.

    Sets ``ANTIEK_DUCKDB_PATH`` so internal lookups
    (``schema.default_db_path``) resolve to this file. Clears the
    process-wide default queue both before and after so a previous
    test's queue can't reach across the boundary.
    """
    path = str(tmp_path / "behavior.duckdb")
    prev = os.environ.get("ANTIEK_DUCKDB_PATH")
    os.environ["ANTIEK_DUCKDB_PATH"] = path

    # Clear any stale default queue.
    reset_default_queue()

    init_behavior_schema_at_path(path)
    try:
        yield path
    finally:
        reset_default_queue()
        if prev is None:
            os.environ.pop("ANTIEK_DUCKDB_PATH", None)
        else:
            os.environ["ANTIEK_DUCKDB_PATH"] = prev


@pytest.fixture
def behavior_queue(behavior_db) -> Iterator[BehaviorQueue]:
    """Isolated queue bound to the per-test DB. Tests pass this
    through to ``emit_behavior_event(..., queue=...)`` to bypass the
    process-wide default."""
    q = BehaviorQueue(db_path=behavior_db)
    q.start()
    try:
        yield q
    finally:
        q.shutdown(timeout_s=3.0)
