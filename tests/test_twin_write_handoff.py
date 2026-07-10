import json

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.engagement_spine import (
    HighlightSelection,
    InMemoryEngagementStore,
    record_twin_insight,
    record_twin_question,
    send_selected_twins_to_write,
)
from substrate.floating_session import open_from_highlight
from substrate.floating_session.store import InMemorySessionStore
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight


def _seed(tmp_path, *, with_chunk=True):
    db = str(tmp_path / "graph.duckdb")
    ensure_initialized(db)
    con = connect_write(db, purpose="test/seed-handoff")
    con.execute(
        "INSERT INTO documents (document_id, title, source_tier, document_type) "
        "VALUES ('doc-1', 'Source', 2, 'book')"
    )
    if with_chunk:
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES ('chunk-1', 'doc-1', 0, 'selected text')"
        )
    con.close()
    engagement = InMemoryEngagementStore()
    sessions = InMemorySessionStore()
    session = open_from_highlight(
        HighlightSelection(asset_id="doc-1", selection_text="selected text",
                           region_id="chunk-1"),
        engagement_store=engagement, session_store=sessions,
    )
    insight = record_twin_insight(
        "doc-1", "First insight", store=engagement,
        source_spawn_id=session.spawn_id, investigation_id=session.investigation_id,
    )
    question = record_twin_question(
        "doc-1", "Then what?", store=engagement,
        source_spawn_id=session.spawn_id, investigation_id=session.investigation_id,
    )
    return db, engagement, sessions, session, insight, question


def _send(seed, *, note_ids=None):
    db, engagement, sessions, session, insight, question = seed
    return send_selected_twins_to_write(
        engagement_store=engagement, session_store=sessions,
        asset_id="doc-1", session_id=session.session_id,
        spawn_id=session.spawn_id, investigation_id=session.investigation_id,
        title="Operator title", note_ids=(
            [insight.note_id, question.note_id] if note_ids is None else note_ids
        ),
        db_path=db,
    )


def test_chunk_provenance_mixed_kinds_order_and_replay(tmp_path, monkeypatch) -> None:
    events_dir = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    seed = _seed(tmp_path)
    first = _send(seed)
    assert first.provenance_precision == "chunk"
    assert first.promoted_note_ids == (seed[4].note_id, seed[5].note_id)
    writer = connect_write(seed[0], purpose="test/remove-replay-chunk")
    writer.execute("DELETE FROM chunks WHERE chunk_id = 'chunk-1'")
    writer.close()
    replay = _send(seed)
    assert replay.deliverable_id == first.deliverable_id
    assert replay.replayed is True
    assert replay.skipped_note_ids == first.promoted_note_ids
    assert replay.provenance_precision == "chunk"

    con = duckdb.connect(seed[0], read_only=True)
    rows = con.execute(
        "SELECT b.block_kind, b.block_index, n.metadata FROM outline_blocks b "
        "JOIN nodes n ON n.node_id=b.node_id ORDER BY b.block_index"
    ).fetchall()
    con.close()
    assert [(row[0], row[1]) for row in rows] == [("insight", 0), ("open_question", 1)]
    assert all(json.loads(row[2])["chunk_id"] == "chunk-1" for row in rows)
    assert all(json.loads(row[2])["provenance_precision"] == "chunk" for row in rows)
    events = [json.loads(line) for line in next(events_dir.glob("*.jsonl")).read_text().splitlines()]
    assert [event["action_type"] for event in events] == [
        "graph.node.inserted",
        "graph.node.inserted",
        "outline_block.placed",
        "outline_block.placed",
    ]


def test_document_only_provenance_is_honest(tmp_path) -> None:
    seed = _seed(tmp_path, with_chunk=False)
    result = _send(seed)
    assert result.provenance_precision == "document"
    con = duckdb.connect(seed[0], read_only=True)
    metadata = [json.loads(row[0]) for row in con.execute("SELECT metadata FROM nodes").fetchall()]
    con.close()
    assert all(item["source_document_id"] == "doc-1" for item in metadata)
    assert all("chunk_id" not in item for item in metadata)


def test_foreign_note_and_unresolved_document_rejected_before_mutation(tmp_path) -> None:
    seed = _seed(tmp_path)
    foreign = record_twin_insight("doc-2", "Foreign", store=seed[1],
                                  source_spawn_id=seed[3].spawn_id)
    with pytest.raises(ValueError, match="does not belong"):
        _send(seed, note_ids=[foreign.note_id])

    con = connect_write(seed[0], purpose="test/remove-doc")
    con.execute("DELETE FROM chunks")
    con.execute("DELETE FROM documents")
    con.close()
    with pytest.raises(ValueError, match="canonical document"):
        _send(seed, note_ids=[seed[4].note_id])
    check = duckdb.connect(seed[0], read_only=True)
    assert check.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 0
    assert check.execute("SELECT count(*) FROM nodes").fetchone()[0] == 0
    check.close()


def test_validation_and_failure_roll_back_every_db_mutation(tmp_path, monkeypatch) -> None:
    seed = _seed(tmp_path)
    events_dir = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    with pytest.raises(ValueError, match="title"):
        send_selected_twins_to_write(
            engagement_store=seed[1], session_store=seed[2], asset_id="doc-1",
            session_id=seed[3].session_id, spawn_id=seed[3].spawn_id,
            investigation_id=seed[3].investigation_id, title="  ", note_ids=[seed[4].note_id],
            db_path=seed[0],
        )
    with pytest.raises(ValueError, match="select"):
        _send(seed, note_ids=[])

    import substrate.engagement_spine.write_handoff as handoff
    monkeypatch.setattr(handoff, "place_node_block", lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError, match="boom"):
        _send(seed)
    con = duckdb.connect(seed[0], read_only=True)
    for table in ("nodes", "deliverables", "deliverable_sections", "outline_blocks"):
        assert con.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
    con.close()
    assert not list(events_dir.glob("*.jsonl"))


def test_note_without_investigation_lineage_is_rejected(tmp_path) -> None:
    seed = _seed(tmp_path)
    unscoped = record_twin_insight(
        "doc-1", "Unscoped", store=seed[1], source_spawn_id=seed[3].spawn_id
    )
    with pytest.raises(ValueError, match="investigation"):
        _send(seed, note_ids=[unscoped.note_id])


def test_same_text_node_with_different_provenance_is_rejected(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    seed = _seed(tmp_path)
    con = connect_write(seed[0], purpose="test/seed-conflicting-node")
    promote_insight(
        text=seed[4].text,
        investigation_id="other-investigation",
        source_document_id="doc-1",
        chunk_id="chunk-1",
        metadata={"twin_note_id": "other-note"},
        con=con,
    )
    con.close()
    with pytest.raises(ValueError, match="different provenance"):
        _send(seed, note_ids=[seed[4].note_id])
    check = duckdb.connect(seed[0], read_only=True)
    assert check.execute("SELECT count(*) FROM deliverables").fetchone()[0] == 0
    check.close()
