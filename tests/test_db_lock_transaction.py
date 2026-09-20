"""``LockedConnection.transaction()`` must never report a write that did not land.

DuckDB aborts the whole transaction on the first failing statement. A later
COMMIT then *succeeds* while applying nothing, so a block that swallows a
failure and exits cleanly would tell its caller the write landed while the
datastore is unchanged. That is worse than the non-atomic behaviour the
contextmanager exists to remove, because it is silent.
"""

from __future__ import annotations

import os
import sys

import duckdb
import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_HERE))

from runtime.db_lock import TransactionAborted, connect_write  # noqa: E402


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / "t.duckdb")
    con = duckdb.connect(path)
    con.execute("CREATE TABLE t (k TEXT PRIMARY KEY, v INT)")
    con.execute("INSERT INTO t VALUES ('a', 1)")
    con.close()
    return path


def _rows(path: str) -> list[tuple]:
    con = duckdb.connect(path)
    try:
        return con.execute("SELECT * FROM t ORDER BY k").fetchall()
    finally:
        con.close()


def test_swallowed_failure_raises_instead_of_committing_nothing(db):
    """The trap: catching the error INSIDE the block must not look like success."""
    with connect_write(db, purpose="test") as con:
        with pytest.raises(TransactionAborted):
            with con.transaction():
                con.execute("DELETE FROM t WHERE k = 'a'")
                with pytest.raises(duckdb.ConstraintException):
                    con.execute("INSERT INTO t VALUES ('a', 2)")
                    con.execute("INSERT INTO t VALUES ('a', 3)")
                # Block exits cleanly here. Without the guard, COMMIT would
                # succeed and the caller would believe the move applied.

    assert _rows(db) == [("a", 1)], "the original row must survive"


def test_propagated_failure_rolls_back(db):
    """The correct pattern: handle the failure OUTSIDE the block."""
    with connect_write(db, purpose="test") as con:
        with pytest.raises(duckdb.ConstraintException):
            with con.transaction():
                con.execute("DELETE FROM t WHERE k = 'a'")
                con.execute("INSERT INTO t VALUES ('a', 2)")
                con.execute("INSERT INTO t VALUES ('a', 3)")

    assert _rows(db) == [("a", 1)]


def test_happy_path_still_commits(db):
    with connect_write(db, purpose="test") as con:
        with con.transaction():
            con.execute("INSERT INTO t VALUES ('z', 9)")

    assert _rows(db) == [("a", 1), ("z", 9)]


def test_nested_transaction_is_reentrant_and_commits_once(db):
    """DuckDB has no nested BEGIN; the inner block must join the outer one."""
    with connect_write(db, purpose="test") as con:
        with con.transaction():
            with con.transaction():
                con.execute("INSERT INTO t VALUES ('n', 5)")

    assert _rows(db) == [("a", 1), ("n", 5)]


def test_duckdb_still_commits_an_aborted_transaction_silently(db):
    """Pin the upstream behaviour this guard exists for.

    If a future DuckDB makes COMMIT raise on an aborted transaction, this test
    fails and the guard can be reconsidered. Without this, nobody would know
    the premise had changed.
    """
    con = duckdb.connect(db)
    try:
        con.execute("BEGIN")
        con.execute("DELETE FROM t WHERE k = 'a'")
        with pytest.raises(duckdb.ConstraintException):
            con.execute("INSERT INTO t VALUES ('a', 2)")
            con.execute("INSERT INTO t VALUES ('a', 3)")
        con.execute("COMMIT")  # succeeds today
        assert con.execute("SELECT * FROM t").fetchall() == [("a", 1)], (
            "COMMIT applied nothing — this is the silence the guard converts "
            "into a raise"
        )
    finally:
        con.close()
