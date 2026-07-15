from __future__ import annotations

import hashlib
import json
import uuid
from pathlib import Path

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph import schema as graph_schema
from substrate.graph.schema import init_database_at_path
from substrate.research_artifact.merge_commit import MergeCommitError, apply_review, restore


def _id(prefix: str) -> str:
    return prefix + "_" + uuid.uuid4().hex


def _review(
    db: str,
    *,
    owner: str = "owner-a",
    intent: str = "create",
    asset: str | None = None,
    parent: str | None = None,
    parent_hash: str | None = None,
    body: str = "<p>reviewed</p>",
) -> str:
    review, draft = _id("rvw"), _id("drf")
    html = (
        '<article data-antiek-canonical-policy="antiek-derived-asset-merge" '
        'data-antiek-canonical-version="1"><section data-member-index="0">'
        f'{body}</section></article>'
    )
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
                owner,
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
                owner,
                body_hash,
                manifest_hash,
                "antiek-derived-asset-merge",
                "1",
                "DERIVED_ASSET_MERGE_ACK_V1",
            ],
        )
    return review


def test_textless_revision_survives_index_schema_backfill(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    created = apply_review(
        review_id=_review(db, body="<hr>"),
        operation_id=_id("op"),
        owner_user_id="owner-a",
        db_path=db,
    )
    with connect_write(db, purpose="simulate-pre-index-schema") as con:
        con.execute("DROP TABLE derived_asset_revision_indexes")
        con.execute("DROP TABLE derived_asset_revision_chunks")
    graph_schema._INITIALIZED_PATHS.discard(db)
    init_database_at_path(db)
    with duckdb.connect(db, read_only=True) as con:
        receipt = con.execute(
            "SELECT revision_content_sha256,chunk_count FROM derived_asset_revision_indexes "
            "WHERE derived_asset_id=? AND revision_id=?",
            [created.derived_asset_id, created.revision_id],
        ).fetchone()
        assert receipt == (created.content_sha256, 0)
        assert con.execute("SELECT count(*) FROM derived_asset_revision_chunks").fetchone() == (0,)


@pytest.mark.parametrize(
    "fault_stage", ["asset", "revision", "members", "index", "pointer", "receipt", "outbox"]
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
    revise_operation = _id("op")
    revised = apply_review(
        review_id=revise_review,
        operation_id=revise_operation,
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
    assert apply_review(
        review_id=review,
        operation_id=operation,
        owner_user_id="owner-a",
        db_path=db,
    ).replayed
    assert apply_review(
        review_id=revise_review,
        operation_id=revise_operation,
        expected_generation=1,
        owner_user_id="owner-a",
        db_path=db,
    ).replayed
    assert restore(
        derived_asset_id=created.derived_asset_id,
        selected_revision_id=created.revision_id,
        expected_revision_id=revised.revision_id,
        expected_content_sha256=revised.content_sha256,
        expected_generation=2,
        operation_id=restore_op,
        owner_user_id="owner-a",
        db_path=db,
    ).replayed
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
        assert con.execute("SELECT count(*) FROM derived_assets").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM derived_asset_revisions").fetchone() == (3,)
        assert con.execute("SELECT count(*) FROM derived_asset_revision_members").fetchone() == (3,)
        assert con.execute("SELECT count(*) FROM derived_asset_merge_operations").fetchone() == (3,)
        assert con.execute("SELECT count(*) FROM derived_asset_merge_outbox").fetchone() == (3,)
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
    with pytest.raises(MergeCommitError, match="historical"):
        restore(
            derived_asset_id=created.derived_asset_id,
            selected_revision_id=created.revision_id,
            expected_revision_id=created.revision_id,
            expected_content_sha256=created.content_sha256,
            expected_generation=1,
            operation_id=_id("op"),
            owner_user_id="owner-a",
            db_path=db,
        )


def test_restore_refuses_historical_authority_field_drift(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    asset_id = "ast_" + "d" * 32
    historical_id = "rev_" + "d" * 32
    revised_id = "rev_" + "e" * 32
    html = "<article>reviewed</article>"
    manifest = json.dumps([{
        "converter_id": "c", "converter_version": "1", "hosted_html_sha256": "b" * 64,
        "member_index": 0, "projection_id": "projection-a",
        "projection_sanitizer_policy": "p", "projection_sanitizer_version": "1",
        "source_asset_id": "source-a", "source_document_id": "document-a",
        "source_sha256": "a" * 64,
    }], sort_keys=True, separators=(",", ":"))
    content_hash = hashlib.sha256(html.encode()).hexdigest()
    manifest_hash = hashlib.sha256(manifest.encode()).hexdigest()
    with connect_write(db, purpose="merge-authority-field-drift") as con:
        con.execute(
            "INSERT INTO derived_assets (derived_asset_id,title,asset_kind,owner_user_id) "
            "VALUES (?,?,?,?)", [asset_id, "Drift", "analysis", "owner-a"],
        )
        con.execute(
            "INSERT INTO derived_asset_revisions (derived_asset_id,revision_id,operation_kind,"
            "canonical_html,canonical_byte_count,content_sha256,manifest_json,manifest_sha256,"
            "sanitizer_policy,sanitizer_version,review_id,acknowledgement_version,"
            "parent_revision_id,restored_from_revision_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [asset_id, historical_id, "create", html, len(html.encode()), content_hash,
             manifest, manifest_hash, "antiek-derived-asset-merge", "drifted", _id("rvw"),
             "DERIVED_ASSET_MERGE_ACK_V1", None, None],
        )
        con.execute(
            "INSERT INTO derived_asset_revision_members VALUES (?,?,?,?,?,?,?,?,?)",
            [asset_id, historical_id, 0, "projection-a", "source-a", "document-a",
             "a" * 64, "b" * 64, None],
        )
        con.execute(
            "INSERT INTO derived_asset_revisions (derived_asset_id,revision_id,operation_kind,"
            "canonical_html,canonical_byte_count,content_sha256,manifest_json,manifest_sha256,"
            "sanitizer_policy,sanitizer_version,review_id,acknowledgement_version,"
            "parent_revision_id,restored_from_revision_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [asset_id, revised_id, "revise", html, len(html.encode()), content_hash,
             manifest, manifest_hash, "antiek-derived-asset-merge", "1", _id("rvw"),
             "DERIVED_ASSET_MERGE_ACK_V1", historical_id, None],
        )
        con.execute(
            "INSERT INTO derived_asset_revision_members VALUES (?,?,?,?,?,?,?,?,?)",
            [asset_id, revised_id, 0, "projection-a", "source-a", "document-a",
             "a" * 64, "b" * 64, None],
        )
        con.execute(
            "INSERT INTO derived_asset_current_revisions VALUES (?,?,?,?,CURRENT_TIMESTAMP)",
            [asset_id, revised_id, content_hash, 2],
        )
    with pytest.raises(MergeCommitError, match="stored revision is invalid"):
        restore(
            derived_asset_id=asset_id,
            selected_revision_id=historical_id,
            expected_revision_id=revised_id,
            expected_content_sha256=content_hash,
            expected_generation=2,
            operation_id=_id("op"), owner_user_id="owner-a", db_path=db,
        )


def test_operation_identity_is_owner_scoped(tmp_path: Path) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    operation_id = _id("op")
    first = apply_review(
        review_id=_review(db, owner="owner-a"),
        operation_id=operation_id,
        owner_user_id="owner-a",
        db_path=db,
    )
    second = apply_review(
        review_id=_review(db, owner="owner-b"),
        operation_id=operation_id,
        owner_user_id="owner-b",
        db_path=db,
    )
    assert first.derived_asset_id != second.derived_asset_id
    assert first.revision_id != second.revision_id
    with duckdb.connect(db, read_only=True) as con:
        assert con.execute(
            "SELECT owner_user_id,operation_id FROM derived_asset_merge_operations "
            "ORDER BY owner_user_id"
        ).fetchall() == [("owner-a", operation_id), ("owner-b", operation_id)]
        assert con.execute(
            "SELECT owner_user_id,operation_id FROM derived_asset_merge_outbox "
            "ORDER BY owner_user_id"
        ).fetchall() == [("owner-a", operation_id), ("owner-b", operation_id)]


@pytest.mark.parametrize(
    "fault_stage", ["asset", "revision", "members", "index", "pointer", "receipt", "outbox"]
)
def test_create_faults_leave_no_unsealed_rows(tmp_path: Path, fault_stage: str) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    with pytest.raises(MergeCommitError, match="derived asset merge failed"):
        apply_review(
            review_id=_review(db),
            operation_id=_id("op"),
            owner_user_id="owner-a",
            db_path=db,
            fault_hook=lambda stage: (
                (_ for _ in ()).throw(RuntimeError()) if stage == fault_stage else None
            ),
        )
    with duckdb.connect(db, read_only=True) as con:
        for table in (
            "derived_assets",
            "derived_asset_revisions",
            "derived_asset_revision_members",
            "derived_asset_current_revisions",
            "derived_asset_merge_operations",
            "derived_asset_merge_outbox",
        ):
            assert con.execute(f"SELECT count(*) FROM {table}").fetchone() == (0,)


@pytest.mark.parametrize(
    "fault_stage", ["asset", "revision", "members", "index", "pointer", "receipt", "outbox"]
)
def test_revise_faults_preserve_exact_head(tmp_path: Path, fault_stage: str) -> None:
    db = str(tmp_path / "graph.duckdb")
    init_database_at_path(db)
    created = apply_review(
        review_id=_review(db),
        operation_id=_id("op"),
        owner_user_id="owner-a",
        db_path=db,
    )
    review_id = _review(
        db,
        intent="revise",
        asset=created.derived_asset_id,
        parent=created.revision_id,
        parent_hash=created.content_sha256,
    )
    with pytest.raises(MergeCommitError, match="derived asset merge failed"):
        apply_review(
            review_id=review_id,
            operation_id=_id("op"),
            expected_generation=1,
            owner_user_id="owner-a",
            db_path=db,
            fault_hook=lambda stage: (
                (_ for _ in ()).throw(RuntimeError()) if stage == fault_stage else None
            ),
        )
    with duckdb.connect(db, read_only=True) as con:
        assert con.execute(
            "SELECT current_revision_id,current_content_sha256,generation "
            "FROM derived_asset_current_revisions"
        ).fetchone() == (created.revision_id, created.content_sha256, 1)
        assert con.execute("SELECT count(*) FROM derived_asset_revisions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM derived_asset_revision_members").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM derived_asset_merge_operations").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM derived_asset_merge_outbox").fetchone() == (1,)
