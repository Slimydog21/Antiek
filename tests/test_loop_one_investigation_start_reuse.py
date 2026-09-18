"""Loop One wires AFF SPR-06 knowledge reuse at investigation start."""

from __future__ import annotations

from pathlib import Path

from substrate.event_log import iter_physical_events
from substrate.flywheel.investigation_start_reuse import (
    maybe_reuse_prior_knowledge_at_start,
)
from substrate.graph.insight_question import promote_insight
from substrate.graph.schema import init_database_at_path


def test_maybe_reuse_emits_knowledge_reused_even_when_empty(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    init_database_at_path(db)

    eid = maybe_reuse_prior_knowledge_at_start(
        investigation_id="inv-reuse-empty",
        question_text="A novel question with no prior graph units?",
        db_path=db,
        events_dir=str(events),
    )
    assert eid is not None
    rows = list(iter_physical_events("inv-reuse-empty", events_dir=str(events)))
    reused = [r for r in rows if r.get("action_type") == "knowledge.reused"]
    assert len(reused) == 1
    assert reused[0].get("payload", {}).get("reused_unit_ids") == []


def test_maybe_reuse_can_inject_prior_insight(tmp_path, monkeypatch):
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    db = str(tmp_path / "g.duckdb")
    events = tmp_path / "events"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    init_database_at_path(db)

    promote_insight(
        text="The Gettysburg Address is a public-domain primary text from 1863.",
        investigation_id="inv-prior",
        confidence="high",
        emit_graph_events=False,
    )

    eid = maybe_reuse_prior_knowledge_at_start(
        investigation_id="inv-reuse-hit",
        question_text="Is the Gettysburg Address public domain?",
        db_path=db,
        events_dir=str(events),
    )
    assert eid is not None
    rows = list(iter_physical_events("inv-reuse-hit", events_dir=str(events)))
    reused = [r for r in rows if r.get("action_type") == "knowledge.reused"]
    assert len(reused) == 1
    payload = reused[0].get("payload") or {}
    assert "reused_unit_ids" in payload


def test_loop_one_run_investigation_calls_reuse():
    import orchestration.loop_one.orchestrator as orch

    src = Path(orch.__file__).read_text()
    assert "maybe_reuse_prior_knowledge_at_start" in src
    assert "asyncio.to_thread" in src
