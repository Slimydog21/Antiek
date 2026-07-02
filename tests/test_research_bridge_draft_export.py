"""Mode A draft-export ledger tests for the Deep Research Bridge."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_read, connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_bridge.draft_export import (
    list_draft_exports,
    record_draft_export,
)
from substrate.research_bridge.schema import init_research_bridge


@pytest.fixture
def db(monkeypatch: pytest.MonkeyPatch) -> str:
    d = tempfile.mkdtemp()
    path = os.path.join(d, "draft-export.duckdb")
    ev = os.path.join(d, "events")
    os.makedirs(ev, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", ev)
    init_database_at_path(path)
    con = connect_write(path, purpose="research_bridge_draft_export_test")
    try:
        init_research_bridge(con)
        con.execute(
            "INSERT INTO deliverables "
            "(deliverable_id, title, deliverable_kind, owner_user_id) VALUES "
            "('dlv-a', 'Draft A', 'research_memo', '__operator__')"
        )
    finally:
        con.close()
    return path


def test_record_draft_export_requires_existing_deliverable(db: str) -> None:
    con = connect_write(db, purpose="record missing draft export")
    try:
        with pytest.raises(ValueError, match="does not exist"):
            record_draft_export(
                con,
                session_id="sess-a",
                deliverable_id="missing",
                output_path="/tmp/draft.md",
            )
    finally:
        con.close()


def test_record_and_list_draft_exports(db: str) -> None:
    con = connect_write(db, purpose="record draft export")
    try:
        export_id = record_draft_export(
            con,
            session_id=" sess-a ",
            deliverable_id=" dlv-a ",
            output_path=" ~/Desktop/draft-a.md ",
        )
    finally:
        con.close()

    con = connect_read(db)
    try:
        rows = list_draft_exports(con)
    finally:
        con.close()

    assert len(rows) == 1
    assert rows[0].export_id == export_id
    assert rows[0].session_id == "sess-a"
    assert rows[0].deliverable_id == "dlv-a"
    assert rows[0].output_path == "~/Desktop/draft-a.md"


def test_record_draft_export_rejects_blank_fields(db: str) -> None:
    con = connect_write(db, purpose="record invalid draft export")
    try:
        with pytest.raises(ValueError, match="session_id must be non-empty"):
            record_draft_export(
                con,
                session_id=" ",
                deliverable_id="dlv-a",
                output_path="/tmp/draft.md",
            )
    finally:
        con.close()
