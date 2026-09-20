from __future__ import annotations

import hashlib
from dataclasses import replace

import pytest

from runtime.db_lock import connect_write
from services.html_projection.island import embed_island
from substrate.feedback.anchor import ArtifactAnchorMismatch, validate_artifact_anchor
from substrate.feedback.domain import ArtifactVersionRef, NodeTextAnchor, normalize_node_text
from substrate.feedback.service import create_artifact_feedback
from substrate.feedback.store import CreateThreadCommand, FeedbackStore
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.paths import artifact_source_path_for
from substrate.research_artifact.store import ResearchArtifactStore


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _seed_versions(db_path: str, monkeypatch, tmp_path) -> tuple[ArtifactVersionRef, str]:
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "artifacts"))
    text = "Cafe\N{COMBINING ACUTE ACCENT} 🧪 result"
    model = {
        "title": "Research",
        "content": [],
        "research_artifact": {
            "schema_version": 1,
            "investigation_id": "inv-1",
            "problem_question": "Question?",
            "insights": [
                {
                    "node_id": "insight-1",
                    "text": text,
                    "source_document_id": "doc-1",
                    "confidence": "high",
                }
            ],
            "open_questions": [],
            "synthesis_excerpt": None,
            "synthesis_withheld": False,
            "source_event_ids": [],
            "agent_notes": [],
        },
    }
    island = embed_island(model)
    source = f"<html><body>{island}</body></html>".encode()
    source_hash = _digest(source)
    store = ResearchArtifactStore(db_path)
    store.save_source(
        "artifact-1",
        "inv-1",
        "owner-1",
        artifact_source_path_for("artifact-1", source_hash),
        source,
    )
    version_one = f"<html><body><main>{island}</main></body></html>"
    version_one_hash = _digest(version_one.encode())
    assert store.add_version(
        "artifact-1", "owner-1", "stone", version_one, version_one_hash
    )[0] == 1
    version_two = f"<html><body><article>{island}</article></body></html>"
    assert store.add_version(
        "artifact-1", "owner-1", "paper", version_two, _digest(version_two.encode())
    )[0] == 2
    with connect_write(db_path, purpose="test/seed-artifact-source-rights") as con:
        con.execute(
            "INSERT INTO documents ("
            "document_id, source_tier, document_type, owner_user_id, content_class"
            ") VALUES ('doc-1', 1, 'paper', 'owner-1', 'public_domain')"
        )
    return ArtifactVersionRef("artifact-1", 1, version_one_hash, source_hash), text


def test_older_immutable_version_remains_a_valid_node_anchor(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    artifact, text = _seed_versions(db_path, monkeypatch, tmp_path)
    normalized = normalize_node_text(text)
    anchor = NodeTextAnchor(
        node_id="insight-1",
        node_text_sha256=_digest(normalized.encode()),
        start_scalar=5,
        end_scalar=6,
        quote="🧪",
        prefix="Café ",
        suffix=" result",
    )

    with connect_write(db_path, purpose="test/validate-artifact-anchor") as con:
        validated = validate_artifact_anchor(
            con,
            owner_user_id="owner-1",
            artifact=artifact,
            anchor=anchor,
        )

    assert validated.investigation_id == "inv-1"
    assert validated.source_document_id == "doc-1"
    assert validated.artifact.version == 1


def test_artifact_anchor_rejects_wrong_owner_without_leaking_identity(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    artifact, text = _seed_versions(db_path, monkeypatch, tmp_path)
    normalized = normalize_node_text(text)
    anchor = NodeTextAnchor(
        "insight-1",
        _digest(normalized.encode()),
        5,
        6,
        "🧪",
        "Café ",
        " result",
    )

    with (
        connect_write(db_path, purpose="test/reject-cross-owner-anchor") as con,
        pytest.raises(ArtifactAnchorMismatch, match="artifact version not found"),
    ):
        validate_artifact_anchor(
            con,
            owner_user_id="owner-2",
            artifact=artifact,
            anchor=anchor,
        )


def test_safe_create_boundary_validates_anchor_before_persisting(tmp_path, monkeypatch) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    artifact, text = _seed_versions(db_path, monkeypatch, tmp_path)
    normalized = normalize_node_text(text)
    anchor = NodeTextAnchor(
        "insight-1",
        _digest(normalized.encode()),
        5,
        6,
        "🧪",
        "Café ",
        " result",
    )
    command = CreateThreadCommand(
        thread_id="fth-safe",
        root_item_id="fit-safe",
        work_id="wrk-safe",
        owner_user_id="owner-1",
        investigation_id="inv-1",
        logical_worker_id="research-owner",
        artifact=artifact,
        anchor=anchor,
        body_markdown="Check the evidence.",
        operation_id="feedback:create:safe",
        request_sha256="d" * 64,
        context_sha256="e" * 64,
    )

    created = create_artifact_feedback(db_path, command)

    assert created.thread_id == "fth-safe"
    with pytest.raises(ArtifactAnchorMismatch):
        create_artifact_feedback(
            db_path,
            replace(
                command,
                thread_id="fth-forged",
                root_item_id="fit-forged",
                work_id="wrk-forged",
                operation_id="feedback:create:forged",
                artifact=ArtifactVersionRef(
                    artifact.artifact_id,
                    artifact.version,
                    "0" * 64,
                    artifact.source_sha256,
                ),
            ),
        )
    with connect_write(db_path, purpose="test/safe-create-rejection") as con:
        assert FeedbackStore().get_thread(
            con, owner_user_id="owner-1", thread_id="fth-forged"
        ) is None


def test_restricted_source_anchor_is_refused_before_comment_creation(
    tmp_path, monkeypatch
) -> None:
    db_path = str(tmp_path / "graph.duckdb")
    init_database_at_path(db_path)
    artifact, text = _seed_versions(db_path, monkeypatch, tmp_path)
    with connect_write(db_path, purpose="test/restrict-artifact-source") as con:
        con.execute(
            "UPDATE documents SET content_class='restricted_pending_opt_in' "
            "WHERE document_id='doc-1'"
        )
    normalized = normalize_node_text(text)
    anchor = NodeTextAnchor(
        "insight-1",
        _digest(normalized.encode()),
        5,
        6,
        "🧪",
        "Café ",
        " result",
    )

    with (
        connect_write(db_path, purpose="test/reject-restricted-anchor") as con,
        pytest.raises(ArtifactAnchorMismatch, match="not servable"),
    ):
        validate_artifact_anchor(
            con,
            owner_user_id="owner-1",
            artifact=artifact,
            anchor=anchor,
        )
