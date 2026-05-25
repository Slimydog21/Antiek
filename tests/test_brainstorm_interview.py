"""Tests for the brainstorm-interview → lego blocks (specs/write/ SPR-05, backend).

M2 driver identification — parse a structured {insights, questions, data}.
M4 emit lego blocks — drivers become OutlineBlocks marked brainstorm-
   originated (NO fabricated citation); asserted data flagged unverified;
   blocks dedupe.

The voice/ASR intake (M1), clarify-loop turn cap (M3), and async budget
(M5) are UI/runtime concerns verified in the frontend + at runtime — the
backend driver→blocks core (the part that protects provenance honesty) is
what's unit-tested here.
"""

from __future__ import annotations

import os
import sys
import tempfile

import duckdb
import pytest

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from roles.interviewer.drivers import DriverSet, DriverValidationError, parse_drivers
from runtime.db_lock import connect_write
from substrate.graph.ops import insert_deliverable, insert_section
from substrate.graph.schema import init_database_at_path
from substrate.write.brainstorm_blocks import drivers_to_blocks
from substrate.write.outline_block import list_section_blocks
from substrate.write.provenance import resolve_provenance


@pytest.fixture()
def db(monkeypatch):
    d = tempfile.mkdtemp()
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(d, "events"))
    path = os.path.join(d, "antiek.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="test/seed") as con:
        did = insert_deliverable(con, title="Brainstorm memo", deliverable_kind="general_essay")
        sec = insert_section(con, deliverable_id=did, section_index=0, title="S")
    return {"path": path, "deliverable_id": did, "section": sec}


def _read(path):
    return duckdb.connect(path, read_only=True)


# ── M2 — driver parsing ────────────────────────────────────────────


def test_parse_drivers_separates_kinds():
    raw = (
        '{"insights": ["the moat is data"], '
        '"questions": ["does it scale?"], '
        '"data_points": ["margins are 80%"]}'
    )
    drivers = parse_drivers(raw)
    assert drivers.insights == ["the moat is data"]
    assert drivers.questions == ["does it scale?"]
    assert drivers.data_points == ["margins are 80%"]
    assert not drivers.is_empty()


def test_parse_drivers_tolerates_empty_kinds():
    drivers = parse_drivers('{"insights": [], "questions": ["q?"], "data_points": []}')
    assert drivers.insights == []
    assert drivers.questions == ["q?"]
    assert drivers.is_empty() is False


def test_parse_drivers_rejects_malformed():
    with pytest.raises(DriverValidationError):
        parse_drivers("not json at all")
    with pytest.raises(DriverValidationError):
        parse_drivers('{"insights": "should be a list"}')


# ── M4 — emit lego blocks with honest provenance ───────────────────


def test_drivers_become_brainstorm_blocks(db):
    drivers = DriverSet(
        insights=["the moat is data, not the model"],
        questions=["does the edit-as-data loop close?"],
        data_points=["the operator asserts 80% gross margin"],
    )
    with connect_write(db["path"], purpose="t") as con:
        result = drivers_to_blocks(
            con, section_id=db["section"], drivers=drivers,
            deliverable_id=db["deliverable_id"],
        )
    assert result.insight_count == 1
    assert result.question_count == 1
    assert result.data_count == 1
    assert len(result.flagged_unverified) == 1  # the asserted data point

    con = _read(db["path"])
    blocks = list_section_blocks(con, db["section"])
    con.close()
    # Every brainstorm block is user-originated — NO node_id (no fabricated citation).
    assert all(b.provenance_kind == "brainstorm" for b in blocks)
    assert all(b.node_id is None for b in blocks)
    kinds = sorted(b.block_kind for b in blocks)
    assert kinds == ["insight", "open_question", "user_authored"]


def test_asserted_data_flagged_unverified(db):
    drivers = DriverSet(data_points=["revenue tripled last quarter"])
    with connect_write(db["path"], purpose="t") as con:
        result = drivers_to_blocks(
            con, section_id=db["section"], drivers=drivers,
            deliverable_id=db["deliverable_id"],
        )
    con = _read(db["path"])
    blocks = list_section_blocks(con, db["section"])
    con.close()
    data_block = blocks[0]
    assert data_block.outline_block_id in result.flagged_unverified
    assert data_block.metadata.get("unverified_claim") is True


def test_brainstorm_block_provenance_resolves_as_user_originated(db):
    drivers = DriverSet(insights=["a thought from a brainstorm"])
    with connect_write(db["path"], purpose="t") as con:
        drivers_to_blocks(
            con, section_id=db["section"], drivers=drivers,
            deliverable_id=db["deliverable_id"],
        )
    con = _read(db["path"])
    block = list_section_blocks(con, db["section"])[0]
    chain = resolve_provenance(con, block)
    con.close()
    # Traces to the session, not an invented document.
    assert chain.status == "user_originated"
    assert chain.document_id is None


def test_brainstorm_blocks_dedupe(db):
    drivers = DriverSet(insights=["the same recurring idea"])
    with connect_write(db["path"], purpose="t") as con:
        first = drivers_to_blocks(
            con, section_id=db["section"], drivers=drivers,
            deliverable_id=db["deliverable_id"],
        )
        second = drivers_to_blocks(
            con, section_id=db["section"], drivers=drivers,
            deliverable_id=db["deliverable_id"],
        )
    assert len(first.block_ids) == 1
    assert second.skipped_duplicates == 1  # re-dumping the idea is a no-op
    con = _read(db["path"])
    assert len(list_section_blocks(con, db["section"])) == 1
    con.close()
