from __future__ import annotations

import asyncio
import hashlib
import threading

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from roles.note_taker import Distillation, DistilledQuestion
from roles.note_taker.parser import ExtractedNote
from substrate.multimedia.knowledge_finalization import (
    MultimediaKnowledgeFinalizationError,
    MultimediaKnowledgeFinalizationRequest,
    finalize_multimedia_knowledge,
)
from substrate.multimedia.read_model import (
    ApplySteeringPreviewRequest,
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
    MultimediaKnowledgeLink,
    SteeringPreviewConflict,
    SteeringPreviewRequest,
)


class _Embedding:
    dimension = 8

    def encode(self, text: str) -> list[float]:
        return [byte / 255 for byte in hashlib.sha256(text.encode()).digest()[:8]]


class _Distiller:
    def __init__(self) -> None:
        self.calls = 0

    def distill(self, text: str, *, source_event_ids=(), context="") -> Distillation:
        self.calls += 1
        return Distillation(
            insights=[
                ExtractedNote(
                    note_id="note-finalized",
                    text="Swept wings delayed compressibility effects.",
                    confidence="high",
                    source_event_ids=tuple(source_event_ids),
                )
            ],
            questions=[DistilledQuestion(text="Which experiments established the tradeoff?")],
        )


class _Factory:
    def __init__(self) -> None:
        self.calls = 0
        self.distillers: list[_Distiller] = []

    def __call__(self) -> _Distiller:
        self.calls += 1
        distiller = _Distiller()
        self.distillers.append(distiller)
        return distiller


def _ready(store: MultimediaAssetStore, *, owner: str = "owner-a"):
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Swept wing history",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("Swept wings delayed shock waves and changed aircraft design.",),
        ),
        owner_id=owner,
    )
    return store.approve_dry_run(draft.asset.asset_id, owner_id=owner)


def _request(revision_id: str, *, acknowledged: bool = True):
    return MultimediaKnowledgeFinalizationRequest(
        expected_revision_id=revision_id,
        operator_acknowledged_model_use=acknowledged,
    )


@pytest.mark.asyncio
async def test_finalization_persists_link_and_replay_skips_model(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    first_distiller = _Distiller()
    first = await finalize_multimedia_knowledge(
        ready.asset.asset_id,
        _request(ready.asset.revision_id),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=lambda: first_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert first_distiller.calls == 1
    assert first.asset.knowledge_link == first.knowledge_link
    assert first.knowledge_link.insight_node_ids
    assert store.list_assets(owner_id="owner-a").assets[0].knowledge_finalized is True

    replay_distiller = _Distiller()
    replay = await finalize_multimedia_knowledge(
        ready.asset.asset_id,
        _request(ready.asset.revision_id),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=lambda: replay_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert replay_distiller.calls == 0
    assert replay.knowledge_link == first.knowledge_link


@pytest.mark.asyncio
async def test_graph_complete_link_missing_replay_repairs_without_model(
    tmp_path, monkeypatch
) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    original = store.attach_knowledge_link
    failed = False

    def fail_once(*args, **kwargs):
        nonlocal failed
        if not failed:
            failed = True
            raise ValueError("simulated link publication failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(store, "attach_knowledge_link", fail_once)
    first_distiller = _Distiller()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="link publication"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=lambda: first_distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert first_distiller.calls == 1
    assert store.get(ready.asset.asset_id, owner_id="owner-a").knowledge_link is None

    replay_distiller = _Distiller()
    repaired = await finalize_multimedia_knowledge(
        ready.asset.asset_id,
        _request(ready.asset.revision_id),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=lambda: replay_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert replay_distiller.calls == 0
    assert repaired.asset.knowledge_link == repaired.knowledge_link


@pytest.mark.asyncio
async def test_finalization_fails_closed_for_ack_revision_readiness_and_owner(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    draft = store.create_draft(
        CreateMultimediaDraftRequest(topic="Aircraft", target_minutes=15),
        owner_id="owner-a",
    )
    factory = _Factory()
    common = {
        "store": store,
        "db_path": str(tmp_path / "graph.duckdb"),
        "distiller_factory": factory,
        "embedding_provider": _Embedding(),
    }
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="model-use"):
        await finalize_multimedia_knowledge(
            draft.asset.asset_id,
            _request(draft.asset.revision_id, acknowledged=False),
            owner_id="owner-a",
            **common,
        )
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="ready asset"):
        await finalize_multimedia_knowledge(
            draft.asset.asset_id,
            _request(draft.asset.revision_id),
            owner_id="owner-a",
            **common,
        )
    ready = store.approve_dry_run(draft.asset.asset_id, owner_id="owner-a")
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="not current"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request("stale-revision"),
            owner_id="owner-a",
            **common,
        )
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="unavailable"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-b",
            **common,
        )
    assert factory.calls == 0


def test_link_cas_conflict_and_steering_clear_stale_link(tmp_path) -> None:
    store = MultimediaAssetStore(tmp_path)
    ready = _ready(store)
    link = MultimediaKnowledgeLink(
        asset_id=ready.asset.asset_id,
        revision_id=ready.asset.revision_id,
        source_document_id="source-doc",
        source_event_id="source-event",
        graph_node_id="graph-node",
        twin_document_id="twin-doc",
        source_html_sha256="a" * 64,
        twin_html_sha256="b" * 64,
    )
    store.reserve_knowledge_finalization(
        ready.asset.asset_id,
        expected_revision_id=ready.asset.revision_id,
        owner_id="owner-a",
    )
    linked = store.attach_knowledge_link(
        ready.asset.asset_id,
        link,
        expected_revision_id=ready.asset.revision_id,
        owner_id="owner-a",
    )
    assert linked.knowledge_link == link
    with pytest.raises(ValueError, match="link conflicts"):
        store.attach_knowledge_link(
            ready.asset.asset_id,
            link.model_copy(update={"twin_document_id": "foreign-twin"}),
            expected_revision_id=ready.asset.revision_id,
            owner_id="owner-a",
        )
    steering = SteeringPreviewRequest(
        expected_parent_revision_id=ready.asset.revision_id,
        prompt="go deeper on engines in chapter 2",
    )
    preview = store.preview_steering(ready.asset.asset_id, steering, owner_id="owner-a")
    assert preview.status == "ready"
    steered = store.apply_steering_preview(
        ready.asset.asset_id,
        ApplySteeringPreviewRequest(
            **steering.model_dump(),
            preview_token=preview.preview_token,
        ),
        owner_id="owner-a",
    )
    assert steered.knowledge_link is None


@pytest.mark.asyncio
async def test_concurrent_finalization_invokes_one_distiller(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    started = threading.Event()
    release = threading.Event()

    class BlockingDistiller(_Distiller):
        def distill(self, text: str, *, source_event_ids=(), context="") -> Distillation:
            started.set()
            assert release.wait(timeout=5)
            return super().distill(
                text, source_event_ids=source_event_ids, context=context
            )

    first_distiller = BlockingDistiller()
    first = asyncio.create_task(
        finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=lambda: first_distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    )
    assert await asyncio.to_thread(started.wait, 5)
    with pytest.raises(
        SteeringPreviewConflict,
        match="multimedia_knowledge_finalization_in_progress",
    ):
        store.preview_steering(
            ready.asset.asset_id,
            SteeringPreviewRequest(
                expected_parent_revision_id=ready.asset.revision_id,
                prompt="go deeper on engines in chapter 2",
            ),
            owner_id="owner-a",
        )
    second_factory = _Factory()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="requires recovery"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=second_factory,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    release.set()
    completed = await first
    assert first_distiller.calls == 1
    assert second_factory.calls == 1
    assert sum(distiller.calls for distiller in second_factory.distillers) == 0
    assert completed.asset.knowledge_finalization_revision_id is None


@pytest.mark.asyncio
async def test_uncertain_model_outcome_never_retries_distiller(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    import substrate.multimedia.knowledge_registration as registration_module

    original_encode = registration_module._encode_distillation

    def fail_after_model(value):
        raise RuntimeError("simulated crash after model response")

    first_distiller = _Distiller()
    monkeypatch.setattr(registration_module, "_encode_distillation", fail_after_model)
    with pytest.raises(RuntimeError, match="after model response"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=lambda: first_distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert first_distiller.calls == 1

    monkeypatch.setattr(registration_module, "_encode_distillation", original_encode)
    replay_factory = _Factory()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="requires recovery"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            _request(ready.asset.revision_id),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=replay_factory,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert replay_factory.calls == 1
    assert sum(distiller.calls for distiller in replay_factory.distillers) == 0


def test_authenticated_finalization_route_and_runtime_fail_closed(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    monkeypatch.setattr(multimedia_routes, "_STORE", store)
    app = FastAPI()

    @app.middleware("http")
    async def identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        if request.headers.get("x-test-auth") == "yes":
            request.state.auth_method = "bearer_token"
            request.state.user_id = request.headers.get("x-test-user", "owner-a")
        return await call_next(request)

    multimedia_routes.register_multimedia_routes(app)
    distiller = _Distiller()
    app.dependency_overrides[multimedia_routes.get_multimedia_knowledge_runtime] = lambda: (
        multimedia_routes.MultimediaKnowledgeRuntime(
            db_path=str(tmp_path / "graph.duckdb"),
            events_dir=str(tmp_path / "events"),
            distiller_factory=lambda: distiller,
            embedding_provider=_Embedding(),
        )
    )
    ready = _ready(store)
    client = TestClient(app, headers={"x-test-auth": "yes", "x-test-user": "owner-a"})
    response = client.post(
        f"/multimedia/assets/{ready.asset.asset_id}/finalize-knowledge",
        json={
            "expected_revision_id": ready.asset.revision_id,
            "operator_acknowledged_model_use": True,
        },
    )
    assert response.status_code == 200
    assert response.json()["asset"]["knowledge_link"]["twin_document_id"]
    assert distiller.calls == 1

    foreign = TestClient(
        app, headers={"x-test-auth": "yes", "x-test-user": "owner-b"}
    ).post(
        f"/multimedia/assets/{ready.asset.asset_id}/finalize-knowledge",
        json={
            "expected_revision_id": ready.asset.revision_id,
            "operator_acknowledged_model_use": True,
        },
    )
    assert foreign.status_code == 404

    unavailable_app = FastAPI()

    @unavailable_app.middleware("http")
    async def unavailable_identity(request: Request, call_next):  # type: ignore[no-untyped-def]
        request.state.auth_method = "bearer_token"
        request.state.user_id = "owner-a"
        return await call_next(request)

    unavailable_app.include_router(multimedia_routes.multimedia_router)
    unavailable = TestClient(unavailable_app).post(
        f"/multimedia/assets/{ready.asset.asset_id}/finalize-knowledge",
        json={
            "expected_revision_id": ready.asset.revision_id,
            "operator_acknowledged_model_use": True,
        },
    )
    assert unavailable.status_code == 503


def test_runtime_environment_requires_explicit_enablement() -> None:
    assert multimedia_routes.multimedia_knowledge_runtime_from_environment({}) is None
    with pytest.raises(RuntimeError, match="configuration is incomplete"):
        multimedia_routes.multimedia_knowledge_runtime_from_environment(
            {"ANTIEK_MULTIMEDIA_KNOWLEDGE_DB_PATH": "/tmp/graph.duckdb"}
        )
    runtime = multimedia_routes.multimedia_knowledge_runtime_from_environment(
        {
            "ANTIEK_MULTIMEDIA_KNOWLEDGE_ENABLED": "true",
            "ANTIEK_MULTIMEDIA_KNOWLEDGE_DB_PATH": "/tmp/graph.duckdb",
        }
    )
    assert runtime is not None
    assert runtime.db_path == "/tmp/graph.duckdb"
