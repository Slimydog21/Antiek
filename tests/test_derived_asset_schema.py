"""Schema contract for immutable, operator-owned derived assets (SDAM SPR-00)."""

from __future__ import annotations

import hashlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import duckdb
import pytest

from runtime.db_lock import connect_write
from substrate.graph import schema as graph_schema
from substrate.graph.schema import init_database_at_path, list_tables

TABLES = {
    "derived_assets",
    "derived_asset_revisions",
    "derived_asset_revision_members",
    "derived_asset_current_revisions",
}
H1 = hashlib.sha256(b"one").hexdigest()
H2 = hashlib.sha256(b"two").hexdigest()
BODY = "<article>reviewed</article>"
BODY_HASH = hashlib.sha256(BODY.encode()).hexdigest()
MANIFEST = '[{"member_index":0,"projection_id":"projection-a"}]'
MANIFEST_HASH = hashlib.sha256(MANIFEST.encode()).hexdigest()


@pytest.fixture  # type: ignore[untyped-decorator]
def db_path(tmp_path: Path) -> Iterator[str]:
    path = str(tmp_path / "graph.duckdb")
    init_database_at_path(path)
    yield path


def _asset(con: Any, asset_id: str = "asset-a", owner: str = "operator-a") -> None:
    con.execute(
        "INSERT INTO derived_assets "
        "(derived_asset_id, title, asset_kind, owner_user_id) VALUES (?, ?, ?, ?)",
        [asset_id, "Analysis", "analysis", owner],
    )


def _revision(
    con: Any,
    *,
    asset_id: str = "asset-a",
    revision_id: str = "rev-a",
    operation: str = "create",
    parent: str | None = None,
    restored_from: str | None = None,
    content_hash: str = BODY_HASH,
) -> None:
    con.execute(
        "INSERT INTO derived_asset_revisions ("
        "derived_asset_id, revision_id, operation_kind, canonical_html, "
        "canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
        "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version, "
        "parent_revision_id, restored_from_revision_id"
        ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            asset_id,
            revision_id,
            operation,
            BODY,
            len(BODY.encode()),
            content_hash,
            MANIFEST,
            MANIFEST_HASH,
            "antiek-merge",
            "1",
            f"rvw-{revision_id}",
            "CREATE_OR_REVISE_DERIVED_ASSET_V1",
            parent,
            restored_from,
        ],
    )


def test_fresh_and_reopen_initialization(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-schema-test") as con:
        assert set(list_tables(con)) >= TABLES
        _asset(con)
        _revision(con)
        con.execute(
            "INSERT INTO derived_asset_revision_members VALUES "
            "('asset-a', 'rev-a', 0, 'projection-a', 'source-a', "
            "'document-a', ?, ?, 'investigation-a')",
            [H1, H2],
        )
        con.execute(
            "INSERT INTO derived_asset_current_revisions "
            "(derived_asset_id, current_revision_id, current_content_sha256, generation) "
            "VALUES ('asset-a', 'rev-a', ?, 1)",
            [BODY_HASH],
        )

    init_database_at_path(db_path)
    with connect_write(db_path, purpose="derived-asset-schema-reopen") as con:
        assert con.execute("SELECT count(*) FROM derived_asset_revisions").fetchone() == (1,)
        assert con.execute("SELECT count(*) FROM derived_asset_revision_members").fetchone() == (1,)
        assert con.execute("SELECT generation FROM derived_asset_current_revisions").fetchone() == (1,)


def test_existing_pre_v16_database_is_upgraded(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-pre-v16-fixture") as con:
        for table in (
            "derived_asset_current_revisions",
            "derived_asset_revision_members",
            "derived_asset_revisions",
            "derived_assets",
        ):
            con.execute(f"DROP TABLE {table}")
    graph_schema._INITIALIZED_PATHS.discard(db_path)

    init_database_at_path(db_path)

    with connect_write(db_path, purpose="derived-asset-upgrade-proof") as con:
        assert set(list_tables(con)) >= TABLES


def test_canonical_html_hash_and_byte_count_must_match(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-canonical-proof") as con:
        _asset(con)
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_revisions ("
                "derived_asset_id, revision_id, operation_kind, canonical_html, "
                "canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
                "sanitizer_policy, sanitizer_version, review_id, acknowledgement_version"
                ") VALUES ('asset-a', 'rev-bad', 'create', ?, 1, ?, ?, ?, "
                "'antiek-merge', '1', 'rvw-bad', 'ACK_V1')",
                [BODY, H1, MANIFEST, MANIFEST_HASH],
            )


def test_manifest_hash_must_match_canonical_manifest(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-manifest-proof") as con:
        _asset(con)
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_revisions ("
                "derived_asset_id, revision_id, operation_kind, canonical_html, "
                "canonical_byte_count, content_sha256, manifest_json, manifest_sha256, "
                "sanitizer_policy, sanitizer_version, review_id, "
                "acknowledgement_version"
                ") VALUES ('asset-a', 'rev-bad-manifest', 'create', ?, ?, ?, ?, ?, "
                "'antiek-merge', '1', 'rvw-bad', 'ACK_V1')",
                [BODY, len(BODY.encode()), BODY_HASH, MANIFEST, H1],
            )


@pytest.mark.parametrize("bad_hash", ["a" * 63, "g" * 64, "A" * 64])  # type: ignore[untyped-decorator]
def test_hashes_require_lowercase_sha256(db_path: str, bad_hash: str) -> None:
    with connect_write(db_path, purpose="derived-asset-hash-test") as con:
        _asset(con)
        with pytest.raises(duckdb.ConstraintException):
            _revision(con, content_hash=bad_hash)


@pytest.mark.parametrize("operation", ["initial", "merge", "amend", "delete"])  # type: ignore[untyped-decorator]
def test_operation_vocabulary_is_closed(db_path: str, operation: str) -> None:
    with connect_write(db_path, purpose="derived-asset-operation-test") as con:
        _asset(con)
        with pytest.raises(duckdb.ConstraintException):
            _revision(con, operation=operation)


def test_operation_shape_requires_parent_and_restore_bindings(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-shape-test") as con:
        _asset(con)
        _revision(con)
        for revision_id, operation, parent, restored_from in [
            ("bad-create", "create", "rev-a", None),
            ("bad-revise", "revise", None, None),
            ("bad-restore", "restore", "rev-a", None),
        ]:
            with pytest.raises(duckdb.ConstraintException):
                _revision(
                    con,
                    revision_id=revision_id,
                    operation=operation,
                    parent=parent,
                    restored_from=restored_from,
                )


def test_parent_restore_member_and_pointer_cannot_cross_assets(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-ownership-test") as con:
        _asset(con, "asset-a", "operator-a")
        _asset(con, "asset-b", "operator-b")
        _revision(con, asset_id="asset-a", revision_id="rev-a")
        _revision(con, asset_id="asset-b", revision_id="rev-b")

        with pytest.raises(duckdb.ConstraintException):
            _revision(
                con,
                asset_id="asset-a",
                revision_id="rev-cross",
                operation="revise",
                parent="rev-b",
            )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_revision_members VALUES "
                "('asset-a', 'rev-b', 0, 'projection-x', 'source-x', "
                "'document-x', ?, ?, NULL)",
                [H1, H2],
            )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_current_revisions "
                "(derived_asset_id, current_revision_id, current_content_sha256, generation) "
                "VALUES ('asset-a', 'rev-b', ?, 1)",
                [BODY_HASH],
            )


def test_members_are_ordered_per_revision_and_projection_unique(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-member-test") as con:
        _asset(con)
        _revision(con)
        for index, projection in enumerate(("projection-a", "projection-b")):
            con.execute(
                "INSERT INTO derived_asset_revision_members VALUES "
                "('asset-a', 'rev-a', ?, ?, ?, ?, ?, ?, ?)",
                [index, projection, f"source-{index}", f"document-{index}", H1, H2, None],
            )
        rows = con.execute(
            "SELECT member_index, projection_id FROM derived_asset_revision_members "
            "ORDER BY member_index"
        ).fetchall()
        assert rows == [(0, "projection-a"), (1, "projection-b")]
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_revision_members VALUES "
                "('asset-a', 'rev-a', 2, 'projection-a', 'source-x', "
                "'document-x', ?, ?, NULL)",
                [H1, H2],
            )


def test_current_pointer_is_one_row_per_asset_and_cas_ready(db_path: str) -> None:
    with connect_write(db_path, purpose="derived-asset-pointer-test") as con:
        _asset(con)
        _revision(con)
        con.execute(
            "INSERT INTO derived_asset_current_revisions "
            "(derived_asset_id, current_revision_id, current_content_sha256, generation) "
            "VALUES ('asset-a', 'rev-a', ?, 1)",
            [BODY_HASH],
        )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "INSERT INTO derived_asset_current_revisions "
                "(derived_asset_id, current_revision_id, current_content_sha256, generation) "
                "VALUES ('asset-a', 'rev-a', ?, 2)",
                [BODY_HASH],
            )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "UPDATE derived_asset_current_revisions "
                "SET current_content_sha256 = ? WHERE derived_asset_id = 'asset-a'",
                [H1],
            )
        with pytest.raises(duckdb.ConstraintException):
            con.execute(
                "UPDATE derived_asset_revisions SET canonical_html = 'mutated' "
                "WHERE derived_asset_id = 'asset-a' AND revision_id = 'rev-a'"
            )
        changed = con.execute(
            "UPDATE derived_asset_current_revisions "
            "SET generation = 2 WHERE derived_asset_id = 'asset-a' "
            "AND current_revision_id = 'rev-a' AND current_content_sha256 = ? "
            "AND generation = 1 RETURNING generation",
            [BODY_HASH],
        ).fetchall()
        assert changed == [(2,)]
        stale = con.execute(
            "UPDATE derived_asset_current_revisions "
            "SET generation = 3 WHERE derived_asset_id = 'asset-a' "
            "AND current_revision_id = 'rev-a' AND current_content_sha256 = ? "
            "AND generation = 1 RETURNING generation",
            [BODY_HASH],
        ).fetchall()
        assert stale == []
        assert con.execute(
            "SELECT generation FROM derived_asset_current_revisions"
        ).fetchone() == (2,)
