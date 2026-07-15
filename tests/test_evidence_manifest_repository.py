from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from substrate.event_log import Event, append_persisted_event, trajectory
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.evidence_collection_repository import (
    EvidenceCollectionRepository,
)
from substrate.research_artifact.evidence_manifest_repository import (
    EvidenceManifestConflict,
    EvidenceManifestRepository,
    EvidenceManifestUnavailable,
)
from tests.test_evidence_collection_repository import _seed


def _manifest(path: str) -> tuple[EvidenceManifestRepository, dict, list[dict]]:
    sources = _seed(path)
    collections = EvidenceCollectionRepository(db_path=path)
    first = collections.create(
        owner_user_id="owner-a", idempotency_key="collection-1", label="First", sources=sources
    )
    second = collections.create(
        owner_user_id="owner-a", idempotency_key="collection-2", label="Second", sources=sources
    )
    repository = EvidenceManifestRepository(db_path=path)
    manifest = repository.create(
        owner_user_id="owner-a",
        idempotency_key="manifest-1",
        label="Combined proof",
        collection_ids=(first["collection_id"], second["collection_id"]),
    )
    return repository, manifest, [first, second]


def test_create_list_read_replay_order_owner_scope_and_binding_tamper(tmp_path: Path) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    repository, created, collections = _manifest(path)
    assert created["collection_count"] == 2
    assert created["total_passage_count"] == 4
    assert [item["collection_id"] for item in created["collections"]] == [
        item["collection_id"] for item in collections
    ]
    assert "collections" not in repository.list(owner_user_id="owner-a")["manifests"][0]
    assert (
        repository.create(
            owner_user_id="owner-a",
            idempotency_key="manifest-1",
            label="Combined proof",
            collection_ids=tuple(item["collection_id"] for item in collections),
        )
        == created
    )
    with pytest.raises(EvidenceManifestConflict):
        repository.create(
            owner_user_id="owner-a",
            idempotency_key="manifest-1",
            label="Changed",
            collection_ids=tuple(item["collection_id"] for item in collections),
        )
    with pytest.raises(EvidenceManifestUnavailable):
        repository.read(owner_user_id="owner-b", manifest_id=created["manifest_id"])
    with connect_write(path, purpose="tamper-manifest-binding") as con:
        con.execute(
            "UPDATE derived_evidence_manifest_collections SET collection_etag='bad' "
            "WHERE manifest_id=? AND manifest_ordinal=1",
            [created["manifest_id"]],
        )
    with pytest.raises(EvidenceManifestConflict):
        repository.read(owner_user_id="owner-a", manifest_id=created["manifest_id"])


def test_duplicate_and_foreign_inputs_persist_nothing(tmp_path: Path) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    sources = _seed(path)
    collection = EvidenceCollectionRepository(db_path=path).create(
        owner_user_id="owner-a", idempotency_key="one", label="One", sources=sources
    )
    repository = EvidenceManifestRepository(db_path=path)
    with pytest.raises(ValueError):
        repository.create(
            owner_user_id="owner-a",
            idempotency_key="duplicate",
            label="Bad",
            collection_ids=(collection["collection_id"], collection["collection_id"]),
        )
    with pytest.raises(EvidenceManifestUnavailable):
        repository.create(
            owner_user_id="owner-b",
            idempotency_key="foreign",
            label="Bad",
            collection_ids=(collection["collection_id"], "dec_" + "f" * 32),
        )
    with connect_write(path, purpose="manifest-no-effects-proof") as con:
        assert con.execute("SELECT count(*) FROM derived_evidence_manifests").fetchone() == (0,)


def test_create_enforces_owner_capacity_without_poisoning_list(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    repository, manifest, collections = _manifest(path)
    monkeypatch.setattr(
        "substrate.research_artifact.evidence_manifest_repository.MAX_MANIFESTS", 1
    )
    with pytest.raises(EvidenceManifestConflict, match="capacity"):
        repository.create(
            owner_user_id="owner-a",
            idempotency_key="over-capacity",
            label="Too many",
            collection_ids=tuple(item["collection_id"] for item in collections),
        )
    assert repository.list(owner_user_id="owner-a")["manifests"] == [
        {key: value for key, value in manifest.items() if key != "collections" and key != "collection_refs"}
    ]


def test_launch_compact_provenance_context_and_deterministic_lease_recovery(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = str(tmp_path / "graph.duckdb")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    init_database_at_path(path)
    repository, manifest, collections = _manifest(path)
    options = {"question": "Compare the two saved collections."}

    class ExpiredDatetime(datetime):
        @classmethod
        def now(cls, tz: object = None) -> datetime:
            return datetime(2000, 1, 1, tzinfo=UTC)

    monkeypatch.setattr(
        "substrate.research_artifact.evidence_manifest_repository.datetime",
        ExpiredDatetime,
    )
    prepared = repository.prepare_launch(
        owner_user_id="owner-a",
        manifest_id=manifest["manifest_id"],
        if_match=manifest["etag"],
        idempotency_key="launch",
        options=options,
    )
    event = Event.model_validate(prepared.delivery_event)
    payload = event.payload.model_dump(mode="json")
    assert payload["derived_source"] is None and payload["derived_sources"] == []
    assert payload["evidence_manifest"]["manifest_id"] == manifest["manifest_id"]
    assert [item["collection_id"] for item in payload["evidence_manifest"]["collections"]] == [
        item["collection_id"] for item in collections
    ]
    assert payload["context"].index(collections[0]["collection_id"]) < payload["context"].index(
        collections[1]["collection_id"]
    )
    assert append_persisted_event(event) is True
    recovered = repository.prepare_launch(
        owner_user_id="owner-a",
        manifest_id=manifest["manifest_id"],
        if_match=manifest["etag"],
        idempotency_key="launch",
        options=options,
    )
    assert recovered.delivery_event == prepared.delivery_event
    assert recovered.lease_token != prepared.lease_token
    assert append_persisted_event(Event.model_validate(recovered.delivery_event)) is False
    assert len(trajectory(prepared.investigation_id)) == 1
