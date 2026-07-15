from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight, promote_question
from substrate.research_artifact import compose_artifacts
from substrate.write.draft_generation import build_creative_writer_context
from substrate.write.outline_block import list_section_blocks


@pytest.fixture
def draft_env(monkeypatch, tmp_path):
    db = tmp_path / "graph.duckdb"
    events = tmp_path / "events"
    artifacts = tmp_path / "artifacts"
    events.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(artifacts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.delenv("ANTIEK_OPERATOR_TOKEN", raising=False)
    ensure_initialized(str(db))
    return db, events


def _composition(db, events):
    promote_insight(text="Frozen alpha evidence", investigation_id="inv-a")
    promote_question(text="What limits alpha?", investigation_id="inv-a")
    promote_insight(text="Frozen beta evidence", investigation_id="inv-b")
    return compose_artifacts(["inv-b", "inv-a"], db_path=str(db), events_dir=str(events))


def test_composition_creates_atomic_ordered_source_scaffold(draft_env):
    db, events = draft_env
    composition = _composition(db, events)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    payload = {
        "composition_id": composition.composition_id,
        "idempotency_key": "cycle41-draft-key-0001",
        "title": "Alpha and beta analysis",
        "deliverable_kind": "research_memo",
    }
    response = client.post("/write/deliverables/from-composition", json=payload)
    assert response.status_code == 201
    body = response.json()
    assert body["review_state"] == "source_scaffold"
    assert body["generated"] is False
    assert body["replayed"] is False
    assert [member["investigation_id"] for member in body["members"]] == ["inv-b", "inv-a"]
    assert [member["evidence_count"] for member in body["members"]] == [1, 2]
    assert body["insufficient_evidence_members"] == []

    con = duckdb.connect(str(db), read_only=True)
    try:
        sections = con.execute(
            "SELECT section_index, title, prose_text FROM deliverable_sections "
            "WHERE deliverable_id = ? ORDER BY section_index",
            [body["deliverable_id"]],
        ).fetchall()
        receipt = con.execute(
            "SELECT owner_user_id, composition_id, ordered_set_digest "
            "FROM deliverable_compositions WHERE deliverable_id = ?",
            [body["deliverable_id"]],
        ).fetchone()
        members = con.execute(
            "SELECT member_index, investigation_id, content_hash, rendered_sha256 "
            "FROM deliverable_composition_members WHERE deliverable_id = ? "
            "ORDER BY member_index",
            [body["deliverable_id"]],
        ).fetchall()
        analysis_blocks = list_section_blocks(con, body["analysis_section_id"])
    finally:
        con.close()
    assert sections[0] == (0, "Analysis", None)
    assert len(sections) == 3
    assert receipt == ("__operator__", composition.composition_id, composition.ordered_set_digest)
    assert [(row[0], row[1]) for row in members] == [(0, "inv-b"), (1, "inv-a")]
    assert [(row[2], row[3]) for row in members] == [
        (member.content_hash, member.rendered_sha256) for member in composition.members
    ]
    assert len(analysis_blocks) == 3


def test_composition_draft_replay_and_conflict_are_explicit(draft_env):
    db, events = draft_env
    composition = _composition(db, events)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    payload = {
        "composition_id": composition.composition_id,
        "idempotency_key": "cycle41-draft-key-0002",
        "title": "Review",
    }
    first = client.post("/write/deliverables/from-composition", json=payload)
    second = client.post("/write/deliverables/from-composition", json=payload)
    assert first.status_code == second.status_code == 201
    assert second.json()["replayed"] is True
    assert second.json()["deliverable_id"] == first.json()["deliverable_id"]
    conflict = client.post(
        "/write/deliverables/from-composition", json={**payload, "title": "Changed"}
    )
    assert conflict.status_code == 409

    con = duckdb.connect(str(db))
    try:
        con.execute(
            "UPDATE deliverable_composition_members SET evidence_count = 99 "
            "WHERE deliverable_id = ? AND member_index = 0",
            [first.json()["deliverable_id"]],
        )
    finally:
        con.close()
    drift = client.post("/write/deliverables/from-composition", json=payload)
    assert drift.status_code == 409
    assert "disagrees" in drift.json()["detail"]


def test_generation_context_uses_immutable_snapshot_text(draft_env):
    db, events = draft_env
    composition = _composition(db, events)
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.post(
        "/write/deliverables/from-composition",
        json={
            "composition_id": composition.composition_id,
            "idempotency_key": "cycle41-draft-key-0003",
            "title": "Review",
        },
    )
    analysis_section = response.json()["analysis_section_id"]
    con = duckdb.connect(str(db))
    try:
        blocks = list_section_blocks(con, analysis_section)
        con.execute("UPDATE nodes SET canonical_label = 'Mutated live label'")
        ctx = build_creative_writer_context(
            deliverable_title="Review",
            deliverable_kind="research_memo",
            section_title="Analysis",
            section_index=0,
            section_count=3,
            blocks=blocks,
            node_label_resolver=lambda _node_id: "Mutated live label",
        )
    finally:
        con.close()
    rendered = [block.body for block in ctx.blocks]
    assert "Frozen alpha evidence" in rendered
    assert "Frozen beta evidence" in rendered
    assert "Mutated live label" not in rendered


def test_missing_or_tampered_member_creates_nothing(draft_env):
    db, events = draft_env
    composition = _composition(db, events)
    member_path = composition.path.parent / composition.composition_id / "inv-a.html"
    member_path.unlink()
    client = TestClient(create_app(register_wrestling=False, register_providers=False))
    response = client.post(
        "/write/deliverables/from-composition",
        json={
            "composition_id": composition.composition_id,
            "idempotency_key": "cycle41-draft-key-0004",
            "title": "Review",
        },
    )
    assert response.status_code == 404
    con = duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute("SELECT count(*) FROM deliverable_compositions").fetchone()[0] == 0
    finally:
        con.close()


def test_duplicate_snapshot_nodes_fail_before_any_write_or_event(draft_env, monkeypatch):
    db, _events = draft_env
    from substrate.research_artifact.compose import (
        VerifiedComposition,
        VerifiedCompositionMember,
    )
    from substrate.research_artifact.schema import ArtifactInsight, ResearchArtifactBody
    from substrate.write.composition_draft import create_composition_draft

    body = ResearchArtifactBody(
        investigation_id="inv-duplicate",
        problem_question="Duplicate",
        insights=[
            ArtifactInsight(node_id="node-same", text="First"),
            ArtifactInsight(node_id="node-same", text="Second"),
        ],
    )
    member = VerifiedCompositionMember(
        investigation_id="inv-duplicate",
        content_hash=body.content_hash(),
        rendered_sha256="a" * 64,
        body=body,
    )
    composition = VerifiedComposition(
        composition_id="cmp-" + "b" * 64,
        ordered_set_digest="b" * 64,
        schema_version=1,
        members=[
            member,
            VerifiedCompositionMember(
                investigation_id="inv-other",
                content_hash=body.model_copy(
                    update={"investigation_id": "inv-other"}
                ).content_hash(),
                rendered_sha256="c" * 64,
                body=body.model_copy(update={"investigation_id": "inv-other", "insights": []}),
            ),
        ],
    )
    import substrate.write.composition_draft as module

    called = False

    def forbidden(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("place_block must not run")

    monkeypatch.setattr(module, "place_block", forbidden)
    from runtime.db_lock import connect_write

    con = connect_write(str(db), purpose="test:duplicate-prevalidation")
    try:
        with pytest.raises(ValueError, match="duplicate evidence"):
            create_composition_draft(
                con,
                owner_user_id="__operator__",
                composition=composition,
                title="Duplicate",
                deliverable_kind="research_memo",
                idempotency_key="cycle41-draft-key-duplicate",
            )
    finally:
        con.close()
    assert called is False
    read = duckdb.connect(str(db), read_only=True)
    try:
        assert read.execute("SELECT count(*) FROM deliverable_compositions").fetchone()[0] == 0
    finally:
        read.close()


def test_schema_fast_path_repairs_partial_composition_migration(draft_env):
    db, _events = draft_env
    from substrate.graph import SCHEMA_TABLES
    from substrate.graph import schema as graph_schema

    assert "deliverable_compositions" in SCHEMA_TABLES
    assert "deliverable_composition_members" in SCHEMA_TABLES
    con = duckdb.connect(str(db))
    try:
        con.execute("DROP TABLE deliverable_composition_members")
    finally:
        con.close()
    graph_schema._INITIALIZED_PATHS.discard(str(db))
    assert graph_schema._schema_is_present(str(db)) is False
    ensure_initialized(str(db))
    check = duckdb.connect(str(db), read_only=True)
    try:
        assert check.execute(
            "SELECT count(*) FROM information_schema.tables "
            "WHERE table_name = 'deliverable_composition_members'"
        ).fetchone()[0] == 1
    finally:
        check.close()
