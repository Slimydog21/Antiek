from __future__ import annotations

import hashlib
import json

import pytest

from roles.note_taker import Distillation, DistilledQuestion
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read, connect_write
from services.html_projection.gate import assert_script_free
from substrate.graph.insight_question import insight_node_id
from substrate.graph.retrieval_gate import non_privileged_chunk_sql_clause
from substrate.graph.schema import init_database_at_path
from substrate.graph.search import search_nodes_by_label
from substrate.graph.traverse import resolve_node, shortest_path
from substrate.multimedia.information_asset import (
    project_multimedia_information_asset,
    register_multimedia_information_asset,
)
from substrate.multimedia.knowledge_registration import (
    CanonicalMultimediaKnowledgeRegistrar,
    MultimediaKnowledgeRegistrationError,
    register_multimedia_with_twin,
)
from substrate.multimedia.read_model import CreateMultimediaDraftRequest, MultimediaAssetStore


class _Embedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:8]]


class _Distiller:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.source_event_ids: tuple[str, ...] = ()
        self.calls = 0

    def distill(self, text: str, *, source_event_ids=(), context="") -> Distillation:
        self.calls += 1
        self.source_event_ids = tuple(source_event_ids)
        if self.empty:
            return Distillation()
        return Distillation(
            insights=[
                ExtractedNote(
                    note_id="note-aircraft",
                    text="High-bypass engines changed long-haul economics.",
                    confidence="high",
                    source_event_ids=self.source_event_ids,
                )
            ],
            questions=[DistilledQuestion(text="Which engine transition mattered most?")],
        )


@pytest.fixture
def prepared(tmp_path, monkeypatch):
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)
    store = MultimediaAssetStore(tmp_path / "assets")
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Aircraft engine transitions",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("High-bypass engines changed long-haul economics.",),
            selected_arc_ids=("mechanism",),
        ),
        owner_id="owner-a",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-a")
    asset = project_multimedia_information_asset(ready, owner_id="owner-a")
    return db_path, events_dir, asset


def test_canonical_registrar_writes_owner_document_chunks_and_entity(prepared) -> None:
    db_path, events_dir, asset = prepared
    registrar = CanonicalMultimediaKnowledgeRegistrar(
        db_path=db_path, owner_id="owner-a", events_dir=events_dir
    )
    receipt = register_multimedia_information_asset(asset, registrar=registrar)
    assert receipt.owner_identity_digest == hashlib.sha256(b"owner-a").hexdigest()

    with connect_read(db_path) as connection:
        document = connection.execute(
            "SELECT raw_text, document_type, content_class, owner_user_id, metadata "
            "FROM documents WHERE document_id=?",
            [receipt.twin_document_id.replace("mm-twin-", "mm-info-")],
        ).fetchone()
        assert document is not None
        assert document[0] == asset.html
        assert document[1:4] == ("multimedia_html", "personal_reading", "owner-a")
        assert json.loads(document[4])["html_sha256"] == asset.html_sha256
        chunks = connection.execute(
            "SELECT section_path, text FROM chunks ORDER BY chunk_index"
        ).fetchall()
        assert chunks
        assert all(row[0] and row[1] for row in chunks)
        entity = connection.execute(
            "SELECT node_type, graph_scope, metadata FROM nodes WHERE node_id=?",
            [receipt.graph_node_id],
        ).fetchone()
        assert entity is not None
        assert entity[:2] == ("entity", "depth")
        assert json.loads(entity[2])["twin_document_id"] == receipt.twin_document_id

    replay = registrar.register(asset)
    assert replay == receipt

    source_document_id = receipt.twin_document_id.replace("mm-twin-", "mm-info-")
    with connect_read(db_path) as connection:
        foreign_sql, foreign_params = non_privileged_chunk_sql_clause(
            policy_tag="operator_only", owner_user_id="owner-b"
        )
        assert connection.execute(
            f"SELECT count(*) FROM documents d WHERE d.document_id=?{foreign_sql}",
            [source_document_id, *foreign_params],
        ).fetchone()[0] == 0
        owner_sql, owner_params = non_privileged_chunk_sql_clause(
            policy_tag="operator_only", owner_user_id="owner-a"
        )
        assert connection.execute(
            f"SELECT count(*) FROM documents d WHERE d.document_id=?{owner_sql}",
            [source_document_id, *owner_params],
        ).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_twin_uses_existing_note_writers_real_event_provenance_and_replays(prepared) -> None:
    db_path, events_dir, asset = prepared
    distiller = _Distiller()
    first = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert distiller.source_event_ids == (first.source_event_id,)
    assert distiller.calls == 1
    assert len(first.insight_node_ids) == 1
    assert len(first.question_node_ids) == 1
    assert first.twin_html_sha256 == hashlib.sha256(first.twin_html.encode()).hexdigest()
    assert first.insight_node_ids[0] in first.twin_html
    assert first.question_node_ids[0] in first.twin_html
    assert_script_free(first.twin_html)

    with connect_read(db_path) as connection:
        twin = connection.execute(
            "SELECT raw_text, document_type, owner_user_id, metadata FROM documents WHERE document_id=?",
            [first.registration.twin_document_id],
        ).fetchone()
        assert twin is not None
        assert twin[:3] == (first.twin_html, "multimedia_twin", "owner-a")
        assert json.loads(twin[3])["source_html_sha256"] == asset.html_sha256
        provenance = connection.execute(
            "SELECT metadata FROM nodes WHERE node_id=?", [first.insight_node_ids[0]]
        ).fetchone()
        assert first.source_event_id in json.loads(provenance[0])["source_event_ids"]

    replay_distiller = _Distiller()
    second = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=replay_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert second.twin_html == first.twin_html
    assert replay_distiller.calls == 0
    with connect_read(db_path) as connection:
        assert connection.execute("SELECT count(*) FROM documents").fetchone()[0] == 2
        assert connection.execute(
            "SELECT count(*) FROM nodes WHERE node_type='insight'"
        ).fetchone()[0] == 1
        assert connection.execute(
            "SELECT count(*) FROM nodes WHERE node_type='question'"
        ).fetchone()[0] == 1


@pytest.mark.asyncio
async def test_empty_distillation_materializes_honest_empty_twin(prepared) -> None:
    db_path, events_dir, asset = prepared
    result = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=_Distiller(empty=True),
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert result.insight_node_ids == ()
    assert result.question_node_ids == ()
    assert "No insights were proposed" in result.twin_html
    assert "No open questions were proposed" in result.twin_html


@pytest.mark.asyncio
async def test_existing_twin_with_public_class_fails_closed(prepared) -> None:
    db_path, events_dir, asset = prepared
    first = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=_Distiller(),
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    connection = connect_write(db_path, purpose="test_twin_conflict")
    try:
        connection.execute(
            "UPDATE documents SET content_class='unrestricted' WHERE document_id=?",
            [first.registration.twin_document_id],
        )
    finally:
        connection.close()
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="twin document conflicts"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=_Distiller(),
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )


@pytest.mark.asyncio
async def test_identical_notes_are_scoped_per_owner_asset(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    init_database_at_path(db_path)
    node_ids = []
    for owner in ("owner-a", "owner-b"):
        store = MultimediaAssetStore(tmp_path / owner)
        draft = store.create_draft(
            CreateMultimediaDraftRequest(
                topic="Same topic",
                target_minutes=15,
                mode="audio",
                route_policy="balanced",
                sources=("Same source.",),
                selected_arc_ids=("history",),
            ),
            owner_id=owner,
        )
        ready = store.approve_dry_run(draft.asset.asset_id, owner_id=owner)
        asset = project_multimedia_information_asset(ready, owner_id=owner)
        result = await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id=owner,
            distiller=_Distiller(),
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
        node_ids.append(result.insight_node_ids[0])
    assert node_ids[0] != node_ids[1]
    with connect_read(db_path) as connection:
        rows = connection.execute(
            "SELECT metadata FROM nodes WHERE node_id IN (?, ?)", node_ids
        ).fetchall()
        scopes = {json.loads(row[0])["identity_scope"] for row in rows}
        assert len(scopes) == 2
        assert search_nodes_by_label(
            connection, "High-bypass", policy_tag="operator_only"
        ) == []
        owner_a_hits = search_nodes_by_label(
            connection,
            "High-bypass",
            policy_tag="operator_only",
            owner_user_id="owner-a",
        )
        assert len(owner_a_hits) == 1
        assert owner_a_hits[0]["node_id"] == node_ids[0]
        with pytest.raises(ValueError, match="node not found"):
            resolve_node(connection, node_ids[1], owner_user_id="owner-a")
        target = connection.execute(
            "SELECT target_node_id FROM edges WHERE source_node_id=?",
            [node_ids[0]],
        ).fetchone()[0]
        assert shortest_path(
            connection,
            node_ids[0],
            target,
            scope="depth",
            owner_user_id="owner-a",
        )
        assert shortest_path(
            connection,
            node_ids[0],
            target,
            scope="depth",
            owner_user_id="owner-b",
        ) == []


@pytest.mark.asyncio
async def test_retry_after_twin_failure_uses_persisted_distillation(
    prepared, monkeypatch
) -> None:
    db_path, events_dir, asset = prepared
    import substrate.multimedia.knowledge_registration as registration_module

    original = registration_module._register_twin_document
    first_distiller = _Distiller()

    def fail_twin(**kwargs):
        raise OSError("simulated twin failure")

    monkeypatch.setattr(registration_module, "_register_twin_document", fail_twin)
    with pytest.raises(OSError, match="twin failure"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=first_distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert first_distiller.calls == 1

    monkeypatch.setattr(registration_module, "_register_twin_document", original)
    replay_distiller = _Distiller(empty=True)
    recovered = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=replay_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert replay_distiller.calls == 0
    assert recovered.insight_node_ids


@pytest.mark.asyncio
async def test_foreign_preexisting_note_id_fails_before_edges_or_twin(prepared) -> None:
    db_path, events_dir, asset = prepared
    registrar = CanonicalMultimediaKnowledgeRegistrar(
        db_path=db_path, owner_id="owner-a", events_dir=events_dir
    )
    receipt = registrar.register(asset)
    source_document_id = receipt.twin_document_id.replace("mm-twin-", "mm-info-")
    node_id = insight_node_id(
        "High-bypass engines changed long-haul economics.",
        identity_scope=source_document_id,
    )
    connection = connect_write(db_path, purpose="plant_foreign_note")
    try:
        connection.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, metadata, owner_user_id) "
            "VALUES (?, 'tampered', 'insight', 'depth', '{}', 'owner-b')",
            [node_id],
        )
    finally:
        connection.close()
    with pytest.raises(ValueError, match="private promoted graph node conflicts"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=_Distiller(),
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    with connect_read(db_path) as connection:
        assert connection.execute(
            "SELECT count(*) FROM edges WHERE source_node_id=?", [node_id]
        ).fetchone()[0] == 0
        assert connection.execute(
            "SELECT count(*) FROM documents WHERE document_type='multimedia_twin'"
        ).fetchone()[0] == 0


@pytest.mark.asyncio
async def test_missing_artifact_event_fails_then_replay_recovers(
    prepared, monkeypatch
) -> None:
    db_path, events_dir, asset = prepared
    import substrate.event_log.events as event_module

    original = event_module._append_jsonl

    def fail_append(path, row):
        raise OSError("simulated append failure")

    monkeypatch.setattr(event_module, "_append_jsonl", fail_append)
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="source event"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=_Distiller(),
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    monkeypatch.setattr(event_module, "_append_jsonl", original)
    recovered = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=_Distiller(),
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert recovered.source_event_id


@pytest.mark.asyncio
async def test_committed_notes_reconcile_after_graph_event_append_failure(
    prepared, monkeypatch
) -> None:
    db_path, events_dir, asset = prepared
    import substrate.event_log.events as event_module

    original = event_module._append_jsonl

    def fail_note_node(path, row):
        payload = row.get("payload", {})
        if row.get("action_type") == "graph.node.inserted" and str(
            payload.get("node_id", "")
        ).startswith("insight-"):
            raise OSError("simulated note event append failure")
        return original(path, row)

    distiller = _Distiller()
    monkeypatch.setattr(event_module, "_append_jsonl", fail_note_node)
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="event reconciliation"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert distiller.calls == 1

    monkeypatch.setattr(event_module, "_append_jsonl", original)
    replay_distiller = _Distiller(empty=True)
    recovered = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=replay_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert replay_distiller.calls == 0
    assert recovered.insight_node_ids


def test_cross_owner_tamper_and_existing_document_conflict_fail_closed(prepared) -> None:
    db_path, events_dir, asset = prepared
    foreign = CanonicalMultimediaKnowledgeRegistrar(
        db_path=db_path, owner_id="owner-b", events_dir=events_dir
    )
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="owner identity"):
        foreign.register(asset)

    registrar = CanonicalMultimediaKnowledgeRegistrar(
        db_path=db_path, owner_id="owner-a", events_dir=events_dir
    )
    receipt = registrar.register(asset)
    source_document_id = receipt.twin_document_id.replace("mm-twin-", "mm-info-")
    connection = connect_write(db_path, purpose="test_conflict")
    try:
        connection.execute(
            "UPDATE documents SET raw_text='tampered' WHERE document_id=?",
            [source_document_id],
        )
    finally:
        connection.close()
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="document conflicts"):
        registrar.register(asset)
