from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from runtime.db_lock import connect_write
from services.html_projection.canonical_merge import POLICY, VERSION
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.derived_citation_source import DerivedCitationConflict
from substrate.research_artifact.derived_asset_retrieval import DerivedAssetRetrievalIntegrity
from substrate.research_artifact.derived_html_index import (
    CHUNKER_POLICY,
    CHUNKER_VERSION,
    publish_revision_index,
    revision_chunk_id,
)
from substrate.research_artifact.evidence_collection_repository import (
    EvidenceCollectionConflict,
    EvidenceCollectionRepository,
    EvidenceCollectionUnavailable,
)
from substrate.event_log import Event, append_persisted_event, trajectory
from substrate.research_artifact.merge_draft import ACKNOWLEDGEMENT_VERSION
from substrate.schemas import DerivedCitationSource


def _seed(path: str) -> tuple[DerivedCitationSource, ...]:
    asset_id = "ast_" + "a" * 32
    revision_id = "rev_" + "b" * 32
    html = (
        '<article data-antiek-canonical-policy="antiek-derived-asset-merge" '
        'data-antiek-canonical-version="1"><section data-member-index="0">'
        '<h1 id="one">One</h1><p>First passage.</p>'
        '<h2 id="two">Two</h2><p>Second passage.</p></section></article>'
    )
    digest = hashlib.sha256(html.encode()).hexdigest()
    manifest = json.dumps([{
        "converter_id": "converter", "converter_version": "1",
        "hosted_html_sha256": "d" * 64, "member_index": 0,
        "projection_id": "projection-a", "projection_sanitizer_policy": "policy",
        "projection_sanitizer_version": "1", "source_asset_id": "source-a",
        "source_document_id": "document-a", "source_sha256": "c" * 64,
    }], sort_keys=True, separators=(",", ":"))
    with connect_write(path, purpose="evidence-collection-fixture") as con:
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id,title,asset_kind,owner_user_id) "
            "VALUES (?, 'Evidence', 'analysis', 'owner-a')", [asset_id]
        )
        con.execute(
            "INSERT INTO derived_asset_revisions (derived_asset_id,revision_id,operation_kind,"
            "canonical_html,canonical_byte_count,content_sha256,manifest_json,manifest_sha256,"
            "sanitizer_policy,sanitizer_version,review_id,acknowledgement_version) "
            "VALUES (?,?,'create',?,?,?,?,?,?,?,'review',?)",
            [asset_id, revision_id, html, len(html.encode()), digest, manifest,
             hashlib.sha256(manifest.encode()).hexdigest(), POLICY, VERSION,
             ACKNOWLEDGEMENT_VERSION],
        )
        con.execute(
            "INSERT INTO derived_asset_revision_members VALUES (?,?,0,'projection-a',"
            "'source-a','document-a',?,?,NULL)",
            [asset_id, revision_id, "c" * 64, "d" * 64],
        )
        con.execute(
            "INSERT INTO derived_asset_current_revisions "
            "(derived_asset_id,current_revision_id,current_content_sha256,generation) "
            "VALUES (?,?,?,1)", [asset_id, revision_id, digest]
        )
        chunks = publish_revision_index(
            con, asset_id=asset_id, revision_id=revision_id,
            content_sha256=digest, canonical_html=html,
        )
    return tuple(DerivedCitationSource(
        derived_asset_id=asset_id, revision_id=revision_id, content_sha256=digest,
        generation=1, citation_id=revision_chunk_id(
            asset_id=asset_id, revision_id=revision_id, content_sha256=digest,
            chunker_policy=CHUNKER_POLICY, chunker_version=CHUNKER_VERSION, chunk=chunk,
        ), chunk_ordinal=chunk.ordinal, chunk_text_sha256=chunk.text_sha256,
        excerpt=chunk.text,
    ) for chunk in chunks)


def test_create_replay_list_read_owner_scope_and_tamper(tmp_path: Path) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    sources = _seed(path)
    assert len(sources) == 2
    repository = EvidenceCollectionRepository(db_path=path)

    created = repository.create(
        owner_user_id="owner-a", idempotency_key="save-1",
        label="Key passages", sources=sources,
    )
    assert [source["excerpt"] for source in created["sources"]] == [
        source.excerpt for source in sources
    ]
    assert [(location["citation_id"], location["chunk_ordinal"],
             location["section_anchor"])
            for location in created["locations"]] == [
        (sources[0].citation_id, 0, "one"),
        (sources[1].citation_id, 1, "two"),
    ]
    assert repository.create(
        owner_user_id="owner-a", idempotency_key="save-1",
        label="Key passages", sources=sources,
    ) == created
    with pytest.raises(EvidenceCollectionConflict):
        repository.create(
            owner_user_id="owner-a", idempotency_key="save-1",
            label="Different", sources=sources,
        )
    assert repository.list(owner_user_id="owner-a")["collections"][0]["member_count"] == 2
    assert "sources" not in repository.list(owner_user_id="owner-a")["collections"][0]
    with pytest.raises(EvidenceCollectionUnavailable):
        repository.read(owner_user_id="owner-b", collection_id=created["collection_id"])

    with connect_write(path, purpose="evidence-collection-tamper") as con:
        con.execute(
            "UPDATE derived_evidence_collection_members SET excerpt='tampered' "
            "WHERE collection_id=? AND member_ordinal=1", [created["collection_id"]]
        )
    with pytest.raises((EvidenceCollectionConflict, DerivedCitationConflict)):
        repository.read(owner_user_id="owner-a", collection_id=created["collection_id"])


def test_schema_has_collection_tables(tmp_path: Path) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    with connect_write(path, purpose="evidence-collection-schema-proof") as con:
        tables = {row[0] for row in con.execute("SHOW TABLES").fetchall()}
    assert {"derived_evidence_collections", "derived_evidence_collection_members",
            "derived_evidence_collection_operations"} <= tables


def test_read_rejects_tampered_verified_location(tmp_path: Path) -> None:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    repository = EvidenceCollectionRepository(db_path=path)
    created = repository.create(
        owner_user_id="owner-a", idempotency_key="save-location",
        label="Location proof", sources=_seed(path),
    )
    with connect_write(path, purpose="evidence-location-tamper") as con:
        con.execute(
            "UPDATE derived_asset_revision_chunks SET section_anchor='forged' "
            "WHERE derived_asset_id=? AND revision_id=? AND chunk_ordinal=0",
            [created["derived_asset_id"], created["revision_id"]],
        )
    with pytest.raises(DerivedAssetRetrievalIntegrity):
        repository.read(
            owner_user_id="owner-a", collection_id=created["collection_id"]
        )


def test_launch_lease_redelivers_same_persisted_event_without_duplicate_append(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = str(tmp_path / "graph.duckdb")
    events = str(tmp_path / "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    init_database_at_path(path)
    repository = EvidenceCollectionRepository(db_path=path)
    created = repository.create(
        owner_user_id="owner-a", idempotency_key="save-launch",
        label="Launch evidence", sources=_seed(path),
    )
    options = {"question": "Compare these exact passages."}
    prepared = repository.prepare_launch(
        owner_user_id="owner-a", collection_id=created["collection_id"],
        if_match=created["etag"], idempotency_key="launch-crash", options=options,
    )
    event = Event.model_validate(prepared.delivery_event)
    assert append_persisted_event(event) is True
    with connect_write(path, purpose="expire-launch-lease") as con:
        con.execute(
            "UPDATE derived_evidence_collection_operations "
            "SET delivery_lease_expires_at=TIMESTAMP '2000-01-01' "
            "WHERE owner_user_id='owner-a' AND idempotency_key='launch-crash'"
        )
    recovered = repository.prepare_launch(
        owner_user_id="owner-a", collection_id=created["collection_id"],
        if_match=created["etag"], idempotency_key="launch-crash", options=options,
    )
    assert recovered.delivery_event == prepared.delivery_event
    assert recovered.lease_token != prepared.lease_token
    assert append_persisted_event(Event.model_validate(recovered.delivery_event)) is False
    assert [row["event_id"] for row in trajectory(prepared.investigation_id)] == [event.event_id]
