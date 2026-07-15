from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.merge_commit import MergeCommitError, apply_review, restore


def _id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def _review(
    db: str,
    *,
    intent: str = "create",
    asset: str | None = None,
    parent: str | None = None,
    parent_hash: str | None = None,
) -> str:
    review, draft = _id("rvw"), _id("drf")
    html = "<article>reviewed</article>"
    manifest = json.dumps(
        [
            {
                "converter_id": "c",
                "converter_version": "1",
                "hosted_html_sha256": "b" * 64,
                "member_index": 0,
                "projection_id": "projection-a",
                "projection_sanitizer_policy": "p",
                "projection_sanitizer_version": "1",
                "source_asset_id": "source-a",
                "source_document_id": "document-a",
                "source_sha256": "a" * 64,
            }
        ],
        sort_keys=True,
        separators=(",", ":"),
    )
    body_hash, manifest_hash = (
        hashlib.sha256(html.encode()).hexdigest(),
        hashlib.sha256(manifest.encode()).hexdigest(),
    )
    with connect_write(db, purpose="seed-reviewed-merge") as con:
        con.execute(
            "INSERT INTO derived_asset_merge_drafts (draft_id,owner_user_id,intent,target_asset_id,"
            "expected_parent_revision_id,expected_parent_sha256,title,asset_kind,canonical_html,"
            "canonical_byte_count,canonical_sha256,manifest_json,manifest_sha256,sanitizer_policy,"
            "sanitizer_version) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [
                draft,
                "owner-a",
                intent,
                asset,
                parent,
                parent_hash,
                "Reviewed",
                "analysis",
                html,
                len(html.encode()),
                body_hash,
                manifest,
                manifest_hash,
                "antiek-derived-asset-merge",
                "1",
            ],
        )
        con.execute(
            "INSERT INTO derived_asset_merge_reviews VALUES (?,?,?,?,?,?,?,?,CURRENT_TIMESTAMP)",
            [
                review,
                draft,
                "owner-a",
                body_hash,
                manifest_hash,
                "antiek-derived-asset-merge",
                "1",
                "DERIVED_ASSET_MERGE_ACK_V1",
            ],
        )
    return review


@pytest.mark.parametrize(
    "fault_stage", ["asset", "revision", "members", "pointer", "receipt", "outbox"]
)
def test_create_revise_restore_replay_and_atomic_fault(tmp_path: Path, fault_stage: str) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    operation = _id("op")
    review = _review(db)
    created = apply_review(
        review_id=review, operation_id=operation, owner_user_id="owner-a", db_path=db
    )
    assert created.generation == 1
    assert apply_review(
        review_id=review, operation_id=operation, owner_user_id="owner-a", db_path=db
    ).replayed
    revise_review = _review(
        db,
        intent="revise",
        asset=created.derived_asset_id,
        parent=created.revision_id,
        parent_hash=created.content_sha256,
    )
    revised = apply_review(
        review_id=revise_review,
        operation_id=_id("op"),
        expected_generation=1,
        owner_user_id="owner-a",
        db_path=db,
    )
    assert revised.generation == 2
    restore_op = _id("op")
    restored = restore(
        derived_asset_id=created.derived_asset_id,
        selected_revision_id=created.revision_id,
        expected_revision_id=revised.revision_id,
        expected_content_sha256=revised.content_sha256,
        expected_generation=2,
        operation_id=restore_op,
        owner_user_id="owner-a",
        db_path=db,
    )
    assert restored.generation == 3 and restored.content_sha256 == created.content_sha256
    fault_op = _id("op")
    with pytest.raises(MergeCommitError, match="derived asset merge failed"):
        restore(
            derived_asset_id=created.derived_asset_id,
            selected_revision_id=created.revision_id,
            expected_revision_id=restored.revision_id,
            expected_content_sha256=restored.content_sha256,
            expected_generation=3,
            operation_id=fault_op,
            owner_user_id="owner-a",
            db_path=db,
            fault_hook=lambda stage: (
                (_ for _ in ()).throw(RuntimeError()) if stage == fault_stage else None
            ),
        )
    with duckdb.connect(db, read_only=True) as con:
        assert con.execute("SELECT count(*) FROM derived_asset_merge_operations").fetchone() == (3,)
        assert con.execute("SELECT generation FROM derived_asset_current_revisions").fetchone() == (
            3,
        )


def test_stale_and_command_drift_leave_no_residue(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    review = _review(db)
    operation = _id("op")
    created = apply_review(
        review_id=review, operation_id=operation, owner_user_id="owner-a", db_path=db
    )
    with pytest.raises(MergeCommitError, match="replay does not match"):
        apply_review(
            review_id=_id("rvw"), operation_id=operation, owner_user_id="owner-a", db_path=db
        )
    with pytest.raises(MergeCommitError, match="stale"):
        restore(
            derived_asset_id=created.derived_asset_id,
            selected_revision_id=created.revision_id,
            expected_revision_id=created.revision_id,
            expected_content_sha256=created.content_sha256,
            expected_generation=99,
            operation_id=_id("op"),
            owner_user_id="owner-a",
            db_path=db,
        )
