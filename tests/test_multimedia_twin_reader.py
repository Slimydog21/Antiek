from __future__ import annotations

import hashlib
import json

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from roles.note_taker import Distillation
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_write
from services.html_projection.gate import (
    ScriptViolation,
    Violation,
)
from services.html_projection.gate import (
    assert_script_free as real_script_gate,
)
from substrate.multimedia.knowledge_finalization import (
    MultimediaKnowledgeFinalizationError,
    MultimediaKnowledgeFinalizationRequest,
    finalize_multimedia_knowledge,
    read_multimedia_twin_document,
)
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    SteeringPreviewRequest,
)


class _Embedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:8]]


class _Distiller:
    def distill(self, text: str, *, source_event_ids=(), context="") -> Distillation:
        return Distillation(
            insights=[
                ExtractedNote(
                    note_id="reader-note",
                    text="Wide-body economics linked capacity to route structure.",
                    confidence="high",
                    source_event_ids=tuple(source_event_ids),
                )
            ]
        )


async def _finalized(tmp_path):
    store = MultimediaAssetStore(tmp_path / "assets")
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Wide-body aircraft economics",
            target_minutes=15,
            sources=("Capacity and route structure changed together.",),
        ),
        owner_id="owner-a",
    )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-a")
    db_path = str(tmp_path / "graph.duckdb")
    finalized = await finalize_multimedia_knowledge(
        ready.asset.asset_id,
        MultimediaKnowledgeFinalizationRequest(
            expected_revision_id=ready.asset.revision_id,
            operator_acknowledged_model_use=True,
        ),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=_Distiller,
        events_dir=str(tmp_path / "events"),
        embedding_provider=_Embedding(),
    )
    return store, db_path, finalized


@pytest.mark.asyncio
async def test_owner_reopens_exact_inert_twin_html(tmp_path) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    document = read_multimedia_twin_document(
        finalized.asset.asset.asset_id,
        owner_id="owner-a",
        store=store,
        db_path=db_path,
    )
    assert document.asset_id == finalized.knowledge_link.asset_id
    assert document.revision_id == finalized.knowledge_link.revision_id
    assert document.source_document_id == finalized.knowledge_link.source_document_id
    assert document.twin_document_id == finalized.knowledge_link.twin_document_id
    assert document.html_sha256 == finalized.knowledge_link.twin_html_sha256
    assert "<script" not in document.html.lower()
    assert "Wide-body aircraft economics" in document.html


@pytest.mark.asyncio
async def test_missing_link_and_foreign_owner_are_opaque(tmp_path) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="unavailable"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-b",
            store=store,
            db_path=db_path,
        )
    unlinked = store.create_draft(
        CreateMultimediaDraftRequest(topic="Unlinked", target_minutes=15),
        owner_id="owner-a",
    )
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="unavailable"):
        read_multimedia_twin_document(
            unlinked.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("column", "value"),
    [
        ("owner_user_id", "owner-b"),
        ("document_type", "web_article"),
        ("content_class", "public_domain"),
        ("source_uri", "https://example.invalid/twin"),
        ("title", "Detached twin"),
        ("metadata", "{}"),
        ("raw_text", "<!doctype html><html><body>Tampered</body></html>"),
    ],
)
async def test_graph_row_tamper_fails_closed(tmp_path, column, value) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    connection = connect_write(db_path, purpose="test_twin_reader_tamper")
    try:
        connection.execute(
            f"UPDATE documents SET {column}=? WHERE document_id=?",
            [value, finalized.knowledge_link.twin_document_id],
        )
    finally:
        connection.close()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="integrity"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
async def test_active_content_gate_is_rechecked_on_read(tmp_path, monkeypatch) -> None:
    store, db_path, finalized = await _finalized(tmp_path)

    def reject(_html: str) -> None:
        raise ScriptViolation([Violation(kind="script_tag", match="<script")])

    monkeypatch.setattr("substrate.multimedia.knowledge_finalization.assert_script_free", reject)
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="integrity"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
async def test_linked_source_tamper_fails_closed(tmp_path) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    connection = connect_write(db_path, purpose="test_twin_reader_source_tamper")
    try:
        connection.execute(
            "UPDATE documents SET raw_text='detached' WHERE document_id=?",
            [finalized.knowledge_link.source_document_id],
        )
    finally:
        connection.close()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="integrity"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
async def test_concurrent_revision_change_fails_final_reopen(tmp_path, monkeypatch) -> None:
    store, db_path, finalized = await _finalized(tmp_path)

    def steer_during_read(html: str) -> None:
        real_script_gate(html)
        asset_id = finalized.asset.asset.asset_id
        steering = SteeringPreviewRequest(
            expected_parent_revision_id=finalized.asset.asset.revision_id,
            prompt="go deeper on engines in chapter 2",
        )
        preview = store.preview_steering(asset_id, steering, owner_id="owner-a")
        assert preview.status == "ready"
        store.apply_steering_preview(
            asset_id,
            ApplySteeringPreviewRequest(
                **steering.model_dump(),
                preview_token=preview.preview_token,
            ),
            owner_id="owner-a",
        )

    monkeypatch.setattr(
        "substrate.multimedia.knowledge_finalization.assert_script_free",
        steer_during_read,
    )
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="integrity"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("field", ["source_document_id", "twin_document_id", "graph_node_id"])
async def test_store_link_identity_substitution_fails_before_graph_read(tmp_path, field) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    owner_digest = hashlib.sha256(b"owner-a").hexdigest()
    path = store.root / "accounts" / owner_digest / f"{finalized.asset.asset.asset_id}.json"
    envelope = json.loads(path.read_text())
    envelope["record"]["knowledge_link"][field] = f"substituted-{field}"
    path.write_text(json.dumps(envelope))
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="integrity"):
        read_multimedia_twin_document(
            finalized.asset.asset.asset_id,
            owner_id="owner-a",
            store=store,
            db_path=db_path,
        )


@pytest.mark.asyncio
async def test_authenticated_twin_route_is_owner_bound(tmp_path, monkeypatch) -> None:
    store, db_path, finalized = await _finalized(tmp_path)
    monkeypatch.setattr(multimedia_routes, "_STORE", store)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = request.headers.get("x-test-user", "owner-a")
        return await call_next(request)

    app.include_router(multimedia_routes.multimedia_router)
    app.dependency_overrides[multimedia_routes.get_multimedia_knowledge_runtime] = lambda: (
        multimedia_routes.MultimediaKnowledgeRuntime(
            db_path=db_path,
            distiller_factory=_Distiller,
        )
    )
    url = f"/multimedia/assets/{finalized.asset.asset.asset_id}/knowledge-twin"
    owner = TestClient(app, headers={"x-test-user": "owner-a"}).get(url)
    assert owner.status_code == 200
    assert owner.json()["twin_document_id"] == finalized.knowledge_link.twin_document_id
    foreign = TestClient(app, headers={"x-test-user": "owner-b"}).get(url)
    assert foreign.status_code == 404
