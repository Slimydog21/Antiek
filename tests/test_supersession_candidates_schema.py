"""Drift test for the supersession_candidates table (SPR-02 M1).

Coverage:
  1. Table exists after init_database_at_path and is registered in SCHEMA_TABLES.
  2. A valid row inserts (NULL edge ids — FK allows NULL — with default-valid
     enum values).
  3. CHECK constraints reject bad contradiction_type / status / decision.
  4. Parity: the SQL CHECK vocabularies EQUAL the Python CONTRADICTION_TYPES /
     REVIEW_DECISIONS frozensets, both directions — so the detector /
     apply_review layer and the table can never silently disagree.
"""

from __future__ import annotations

import os
import re
import sys
import tempfile
from datetime import UTC, datetime

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from middleware.supersession.supersession import (  # noqa: E402
    CONTRADICTION_TYPES,
    REVIEW_DECISIONS,
)
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph.schema import (  # noqa: E402
    ANTIEK_GRAPH_SCHEMA_V14_SUPERSESSION_CANDIDATES_SQL as _V14_SQL,
)
from substrate.graph.schema import (  # noqa: E402
    SCHEMA_TABLES,
    init_database_at_path,
    list_tables,
)

_COLS = (
    "candidate_id", "investigation_id", "old_edge_id", "new_edge_id",
    "contradiction_type", "reasoning", "status", "decision", "reviewer",
    "review_notes", "created_at", "reviewed_at",
)


@pytest.fixture
def db_path():
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "graph.duckdb")
        init_database_at_path(p)
        yield p


def _insert(con, **over):
    row = {
        "candidate_id": "cand-1",
        "investigation_id": "inv-1",
        "old_edge_id": None,   # NULL — FK allows NULL, so no edge seeding needed
        "new_edge_id": None,
        "contradiction_type": "uncertainty",
        "reasoning": "r",
        "status": "open",
        "decision": None,
        "reviewer": None,
        "review_notes": "",
        "created_at": datetime.now(UTC),
        "reviewed_at": None,
    }
    row.update(over)
    con.execute(
        "INSERT INTO supersession_candidates ("
        + ", ".join(_COLS)
        + ") VALUES (" + ", ".join("?" * len(_COLS)) + ")",
        [row[c] for c in _COLS],
    )


def test_table_exists_and_registered(db_path):
    assert "supersession_candidates" in SCHEMA_TABLES
    with connect_write(db_path, purpose="test") as con:
        assert "supersession_candidates" in list_tables(con)


def test_valid_row_inserts(db_path):
    with connect_write(db_path, purpose="test") as con:
        _insert(con)
        n = con.execute(
            "SELECT count(*) FROM supersession_candidates"
        ).fetchone()[0]
        assert n == 1


@pytest.mark.parametrize(
    "field,bad",
    [
        ("contradiction_type", "NOT_A_TYPE"),
        ("status", "NOT_A_STATUS"),
        ("decision", "NOT_A_DECISION"),
    ],
)
def test_check_rejects_bad_value(db_path, field, bad):
    with connect_write(db_path, purpose="test") as con, pytest.raises(duckdb.ConstraintException):
        _insert(con, **{field: bad})


def test_check_sets_match_python_frozensets():
    # The single source of truth for the vocabularies is the Python module;
    # the SQL CHECK must mirror it exactly (no missing token, no extra token).
    assert set(CONTRADICTION_TYPES) == {"supersession", "uncertainty", "error"}
    assert set(REVIEW_DECISIONS) == {
        "apply_supersession", "dismiss_new", "dismiss_old", "coexist",
    }
    ct = re.search(r"contradiction_type IN \(([^)]*)\)", _V14_SQL)
    dec = re.search(r"decision IN \(([^)]*)\)", _V14_SQL)
    assert ct is not None and dec is not None
    ct_vals = {v.strip().strip("'") for v in ct.group(1).split(",")}
    dec_vals = {v.strip().strip("'") for v in dec.group(1).split(",")}
    assert ct_vals == set(CONTRADICTION_TYPES)
    assert dec_vals == set(REVIEW_DECISIONS)
