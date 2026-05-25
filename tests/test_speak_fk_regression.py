"""Speak — DuckDB FK regression sentinel.

Backstops the failure documented in
``tests/regression/agent_failures/speak-duckdb-fk-blocks-interview-update.yaml``:
a DB-level foreign key from a Speak child table to ``interviews`` makes
DuckDB refuse to UPDATE the (parent) ``interviews`` row — its documented
FK limitation — which deadlocks the async interview + invitee answer
flow, since both append to ``interviews.transcript_turns`` on every turn.

This test reproduces the EXACT path that crashed (insert interview →
insert a speak_consent child → UPDATE interviews) and asserts it
succeeds. It fails the moment a future edit re-adds a parent-referencing
FK to the Speak schema — which is the whole point.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.ops import insert_interview, insert_interview_project
from substrate.graph.schema import init_database
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.schema import ANTIEK_SPEAK_SCHEMA_SQL, ensure_speak_schema


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "1")
    tmpdir = tempfile.mkdtemp(prefix="speak-fk-regression-")
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="speak_fk_regression_setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def test_speak_schema_declares_no_parent_referencing_fks():
    """Static guard: the Speak DDL must not declare REFERENCES to the
    shared parent tables whose rows are UPDATEd in place. A future edit
    that adds one trips this immediately, before the runtime deadlock."""
    forbidden = (
        "REFERENCES interviews",
        "REFERENCES interview_projects",
        "REFERENCES ip_holders",
    )
    for needle in forbidden:
        assert needle not in ANTIEK_SPEAK_SCHEMA_SQL, (
            f"Speak schema re-introduced a DB-level FK ({needle!r}). DuckDB "
            "blocks UPDATE of a referenced parent row — this will deadlock "
            "the async interview. Use column-name + audit-event provenance "
            "instead (see graph/ops.py + the agent-failure fixture)."
        )


def test_updating_interview_with_consent_child_does_not_deadlock(db):
    """Runtime guard: reproduce the crashed path end to end."""
    with connect_write(db, purpose="speak_fk_regression") as con:
        project_id = insert_interview_project(con, title="Dad's biography")
        interview_id = insert_interview(con, project_id=project_id, informant_handle="aunt")
        # A consent child row for this interview — the exact precondition
        # that made the parent un-updatable when an FK was declared.
        record_consent(con, interview_id=interview_id, scopes=[ConsentScope.RECORD])

        # The append-a-turn write that crashed: UPDATE interviews while a
        # speak_consent child references it. Must NOT raise.
        turns = [{"role": "informant", "text": "He baked bread before dawn.", "ts": "2026-05-25T00:00:00Z"}]
        con.execute(
            "UPDATE interviews SET transcript_turns = ?, status = 'in_progress' "
            "WHERE interview_id = ?",
            [json.dumps(turns), interview_id],
        )
        row = con.execute(
            "SELECT status, transcript_turns FROM interviews WHERE interview_id = ?",
            [interview_id],
        ).fetchone()
    assert row[0] == "in_progress"
    assert "bread" in row[1]
