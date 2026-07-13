from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from interfaces.research.api import multimedia_routes
from roles.note_taker import Distillation
from roles.note_taker.parser import ExtractedNote
from runtime.db_lock import connect_read, connect_write
from substrate.multimedia.information_asset import project_multimedia_information_asset
from substrate.multimedia.knowledge_finalization import (
    MultimediaKnowledgeFinalizationError,
    MultimediaKnowledgeFinalizationRequest,
    MultimediaKnowledgeRecoveryRequest,
    finalize_multimedia_knowledge,
    inspect_multimedia_knowledge_finalization,
    recover_multimedia_knowledge_finalization,
)
from substrate.multimedia.knowledge_registration import (
    MultimediaKnowledgeRegistrationError,
    authorize_multimedia_distillation_recovery,
    register_multimedia_with_twin,
)
from substrate.multimedia.read_model import (
    CreateMultimediaDraftRequest,
    MultimediaAssetStore,
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
                    note_id="recovered-note",
                    text="Recovery must preserve the first safe authority boundary.",
                    confidence="high",
                    source_event_ids=tuple(source_event_ids),
                )
            ]
        )


class _Factory:
    def __init__(self) -> None:
        self.distillers: list[_Distiller] = []

    def __call__(self) -> _Distiller:
        value = _Distiller()
        self.distillers.append(value)
        return value

    @property
    def model_calls(self) -> int:
        return sum(value.calls for value in self.distillers)


def _ready(store: MultimediaAssetStore):
    draft = store.create_draft(
        CreateMultimediaDraftRequest(
            topic="Uncertain model outcome recovery",
            target_minutes=15,
            mode="audio",
            route_policy="balanced",
            sources=("Durable claims prevent silent duplicate model spend.",),
        ),
        owner_id="owner-a",
    )
    return store.approve_dry_run(draft.asset.asset_id, owner_id="owner-a")


async def _leave_uncertain(
    store: MultimediaAssetStore,
    ready,
    db_path: str,
    events_dir: str,
    monkeypatch,
) -> None:
    import substrate.multimedia.knowledge_registration as registration_module

    original = registration_module._encode_distillation

    def crash_after_response(value):
        raise RuntimeError("simulated post-model crash")

    monkeypatch.setattr(registration_module, "_encode_distillation", crash_after_response)
    with pytest.raises(RuntimeError, match="post-model crash"):
        await finalize_multimedia_knowledge(
            ready.asset.asset_id,
            MultimediaKnowledgeFinalizationRequest(
                expected_revision_id=ready.asset.revision_id,
                operator_acknowledged_model_use=True,
            ),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=_Distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    monkeypatch.setattr(registration_module, "_encode_distillation", original)


def _age_claim(db_path: str) -> None:
    connection = connect_write(db_path, purpose="test_age_distillation_claim")
    try:
        connection.execute(
            "UPDATE multimedia_distillation_claims "
            "SET created_at=CURRENT_TIMESTAMP - INTERVAL '16 minutes'"
        )
    finally:
        connection.close()


@pytest.mark.asyncio
async def test_status_and_explicit_stale_recovery(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    await _leave_uncertain(store, ready, db_path, events_dir, monkeypatch)

    fresh = inspect_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        owner_id="owner-a",
        store=store,
        db_path=db_path,
    )
    assert fresh.distillation.state == "in_progress"
    assert fresh.distillation.recovery_eligible is False

    factory = _Factory()
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="not stale"):
        await recover_multimedia_knowledge_finalization(
            ready.asset.asset_id,
            MultimediaKnowledgeRecoveryRequest(
                expected_revision_id=ready.asset.revision_id,
                operator_acknowledged_model_use=True,
                operator_acknowledged_duplicate_model_risk=True,
            ),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=factory,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert factory.model_calls == 0

    _age_claim(db_path)
    stale = inspect_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        owner_id="owner-a",
        store=store,
        db_path=db_path,
    )
    assert stale.distillation.recovery_eligible is True

    recovered = await recover_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        MultimediaKnowledgeRecoveryRequest(
            expected_revision_id=ready.asset.revision_id,
            operator_acknowledged_model_use=True,
            operator_acknowledged_duplicate_model_risk=True,
        ),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=factory,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert factory.model_calls == 1
    assert recovered.asset.knowledge_link == recovered.knowledge_link
    completed = inspect_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        owner_id="owner-a",
        store=store,
        db_path=db_path,
    )
    assert completed.distillation.state == "completed"
    assert completed.distillation.recovery_eligible is False
    before = factory.model_calls
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="already completed"):
        await recover_multimedia_knowledge_finalization(
            ready.asset.asset_id,
            MultimediaKnowledgeRecoveryRequest(
                expected_revision_id=ready.asset.revision_id,
                operator_acknowledged_model_use=True,
                operator_acknowledged_duplicate_model_risk=True,
            ),
            owner_id="owner-a",
            store=store,
            db_path=db_path,
            distiller_factory=factory,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert factory.model_calls == before

    connection = connect_write(db_path, purpose="test_corrupt_distillation_checkpoint")
    try:
        connection.execute("UPDATE multimedia_twin_runs SET distillation_json='{}'")
    finally:
        connection.close()
    corrupt = inspect_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        owner_id="owner-a",
        store=store,
        db_path=db_path,
    )
    assert corrupt.distillation.state == "integrity_conflict"
    assert corrupt.distillation.recovery_eligible is True
    repaired = await recover_multimedia_knowledge_finalization(
        ready.asset.asset_id,
        MultimediaKnowledgeRecoveryRequest(
            expected_revision_id=ready.asset.revision_id,
            operator_acknowledged_model_use=True,
            operator_acknowledged_duplicate_model_risk=True,
        ),
        owner_id="owner-a",
        store=store,
        db_path=db_path,
        distiller_factory=factory,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
    )
    assert repaired.knowledge_link == recovered.knowledge_link
    assert factory.model_calls == before + 1


@pytest.mark.asyncio
async def test_rotated_token_rejects_old_worker(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    await _leave_uncertain(store, ready, db_path, events_dir, monkeypatch)
    _age_claim(db_path)
    with connect_read(db_path) as connection:
        old_token = connection.execute(
            "SELECT claim_token FROM multimedia_distillation_claims"
        ).fetchone()[0]
    asset = project_multimedia_information_asset(ready, owner_id="owner-a")
    new_token = authorize_multimedia_distillation_recovery(
        asset, db_path=db_path, owner_id="owner-a"
    )
    assert new_token != old_token

    old_distiller = _Distiller()
    with pytest.raises(MultimediaKnowledgeRegistrationError, match="requires recovery"):
        await register_multimedia_with_twin(
            asset,
            db_path=db_path,
            owner_id="owner-a",
            distiller=old_distiller,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
            distillation_recovery_token=old_token,
        )
    assert old_distiller.calls == 0

    new_distiller = _Distiller()
    result = await register_multimedia_with_twin(
        asset,
        db_path=db_path,
        owner_id="owner-a",
        distiller=new_distiller,
        events_dir=events_dir,
        embedding_provider=_Embedding(),
        distillation_recovery_token=new_token,
    )
    assert new_distiller.calls == 1
    assert result.insight_node_ids


@pytest.mark.asyncio
async def test_recovery_ack_owner_and_completed_gates(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
    db_path = str(tmp_path / "graph.duckdb")
    events_dir = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    await _leave_uncertain(store, ready, db_path, events_dir, monkeypatch)
    _age_claim(db_path)
    factory = _Factory()
    base = {
        "expected_revision_id": ready.asset.revision_id,
        "operator_acknowledged_model_use": True,
        "operator_acknowledged_duplicate_model_risk": True,
    }
    for field in (
        "operator_acknowledged_model_use",
        "operator_acknowledged_duplicate_model_risk",
    ):
        request = MultimediaKnowledgeRecoveryRequest(**{**base, field: False})
        with pytest.raises(MultimediaKnowledgeFinalizationError, match="acknowledgement"):
            await recover_multimedia_knowledge_finalization(
                ready.asset.asset_id,
                request,
                owner_id="owner-a",
                store=store,
                db_path=db_path,
                distiller_factory=factory,
                events_dir=events_dir,
                embedding_provider=_Embedding(),
            )
    with pytest.raises(MultimediaKnowledgeFinalizationError, match="unavailable"):
        await recover_multimedia_knowledge_finalization(
            ready.asset.asset_id,
            MultimediaKnowledgeRecoveryRequest(**base),
            owner_id="owner-b",
            store=store,
            db_path=db_path,
            distiller_factory=factory,
            events_dir=events_dir,
            embedding_provider=_Embedding(),
        )
    assert factory.model_calls == 0


def test_status_and_recovery_routes_are_owner_bound(tmp_path, monkeypatch) -> None:
    store = MultimediaAssetStore(tmp_path / "assets")
    ready = _ready(store)
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
            db_path=str(tmp_path / "graph.duckdb"),
            events_dir=str(tmp_path / "events"),
            distiller_factory=_Distiller,
            embedding_provider=_Embedding(),
        )
    )
    owner = TestClient(app, headers={"x-test-user": "owner-a"})
    status = owner.get(
        f"/multimedia/assets/{ready.asset.asset_id}/knowledge-finalization"
    )
    assert status.status_code == 200
    assert status.json()["distillation"]["state"] == "not_started"

    foreign = TestClient(app, headers={"x-test-user": "owner-b"})
    assert foreign.get(
        f"/multimedia/assets/{ready.asset.asset_id}/knowledge-finalization"
    ).status_code == 404
    assert foreign.post(
        f"/multimedia/assets/{ready.asset.asset_id}/recover-knowledge-finalization",
        json={
            "expected_revision_id": ready.asset.revision_id,
            "operator_acknowledged_model_use": True,
            "operator_acknowledged_duplicate_model_risk": True,
        },
    ).status_code == 404
