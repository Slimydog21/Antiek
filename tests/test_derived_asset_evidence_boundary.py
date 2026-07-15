"""Red proofs that SPR-00 cannot mutate source evidence or revive legacy authority."""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

import duckdb
import pytest

from substrate.graph.derived_asset_schema import DERIVED_ASSET_SCHEMA_SQL
from substrate.write.derived_asset_boundary import (
    LEGACY_SOURCE_MERGE_FIELDS,
    LegacySourceMergeContractRejected,
    UnknownDerivedAssetCommitField,
    forbidden_evidence_write_patterns,
    validate_commit_boundary,
)

ROOT = Path(__file__).resolve().parents[1]
OWNED_RUNTIME = (
    ROOT / "substrate/graph/schema.py",
    ROOT / "substrate/graph/derived_asset_schema.py",
)


def test_schema_creates_only_owned_derived_asset_tables() -> None:
    created = set(
        re.findall(
            r"CREATE\s+TABLE\s+IF\s+NOT\s+EXISTS\s+(\w+)",
            DERIVED_ASSET_SCHEMA_SQL,
            re.IGNORECASE,
        )
    )
    assert {
        "derived_assets",
        "derived_asset_revisions",
        "derived_asset_revision_members",
        "derived_asset_current_revisions",
    } <= created
    assert not {"documents", "chunks", "nodes", "html_projection_objects"} & created


def test_claimed_runtime_has_no_source_or_filesystem_write_reachability() -> None:
    for path in OWNED_RUNTIME:
        source = path.read_text(encoding="utf-8")
        ast.parse(source, filename=str(path))
        assert forbidden_evidence_write_patterns(source) == ()


@pytest.mark.parametrize("field", sorted(LEGACY_SOURCE_MERGE_FIELDS))  # type: ignore[untyped-decorator]
def test_legacy_authority_is_rejected_before_io(field: str) -> None:
    payload: dict[str, object] = {
        "review_id": "rvw-safe",
        "acknowledgement": "CREATE_OR_REVISE_DERIVED_ASSET_V1",
        "idempotency_key": "retry-safe",
        field: "caller-owned",
    }
    with pytest.raises(LegacySourceMergeContractRejected) as caught:
        validate_commit_boundary(payload)
    assert caught.value.status_code == 422
    assert caught.value.code == "legacy_source_merge_contract_rejected"
    assert caught.value.rejected_fields == (field,)
    assert str(caught.value) == caught.value.message


def test_unknown_nonlegacy_field_has_generic_refusal() -> None:
    with pytest.raises(UnknownDerivedAssetCommitField) as caught:
        validate_commit_boundary(
            {
                "review_id": "rvw-safe",
                "acknowledgement": "CREATE_OR_REVISE_DERIVED_ASSET_V1",
                "idempotency_key": "retry-safe",
                "banana": True,
            }
        )
    assert caught.value.code == "unknown_derived_asset_commit_field"


def test_source_write_mutant_fails_the_boundary_lint(tmp_path: Path) -> None:
    mutant = 'con.execute("UPDATE documents SET raw_text = ?", [body])'
    mutated_runtime = tmp_path / "mutated_boundary.py"
    mutated_runtime.write_text(mutant, encoding="utf-8")
    assert forbidden_evidence_write_patterns(mutated_runtime.read_text(encoding="utf-8"))


def test_request_boundary_has_no_ddl_or_storage_authority() -> None:
    source = (ROOT / "substrate/write/derived_asset_boundary.py").read_text(encoding="utf-8")
    ast.parse(source)
    assert "init_database" not in source
    assert "ensure_tables" not in source
    assert ".execute(" not in source
    assert ".write_text(" not in source


def test_legacy_refusal_leaves_evidence_bytes_unchanged(tmp_path: Path) -> None:
    projection = tmp_path / "projection.html"
    snapshot = tmp_path / "compose.json"
    projection.write_bytes(b"<article>immutable projection</article>")
    snapshot.write_bytes(b'{"members":["projection-a"]}')
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE documents(document_id TEXT, raw_text TEXT)")
    con.execute("INSERT INTO documents VALUES ('document-a', 'immutable source')")

    before = (
        hashlib.sha256(
            con.execute("SELECT raw_text FROM documents").fetchone()[0].encode()
        ).hexdigest(),
        hashlib.sha256(projection.read_bytes()).hexdigest(),
        hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    )
    with pytest.raises(LegacySourceMergeContractRejected):
        validate_commit_boundary(
            {
                "review_id": "rvw-safe",
                "acknowledgement": "CREATE_OR_REVISE_DERIVED_ASSET_V1",
                "idempotency_key": "retry-safe",
                "draft_merge_path": str(projection),
            }
        )
    after = (
        hashlib.sha256(
            con.execute("SELECT raw_text FROM documents").fetchone()[0].encode()
        ).hexdigest(),
        hashlib.sha256(projection.read_bytes()).hexdigest(),
        hashlib.sha256(snapshot.read_bytes()).hexdigest(),
    )
    con.close()
    assert after == before


def test_schema_contains_no_legacy_caller_authority() -> None:
    lowered = DERIVED_ASSET_SCHEMA_SQL.lower()
    for field in {
        "draft_merge_path",
        "compose_index_path",
        "operator_reviewer",
        "commit_id",
        "acknowledge_body_rewrite",
    }:
        assert field not in lowered


def test_boundary_names_inputs_without_foreign_write_authority() -> None:
    sql = DERIVED_ASSET_SCHEMA_SQL.lower()
    # Provenance identity is required, but source/projection tables are not
    # referenced or cascaded: these are copied immutable bindings.
    assert "projection_id" in sql
    assert "source_document_id" in sql
    assert "references documents" not in sql
    assert "references html_projections" not in sql
    assert "on delete cascade" not in sql


def test_revision_authority_contains_canonical_review_bindings() -> None:
    sql = DERIVED_ASSET_SCHEMA_SQL.lower()
    required = {
        "canonical_html",
        "content_sha256",
        "manifest_json",
        "manifest_sha256",
        "sanitizer_policy",
        "sanitizer_version",
        "review_id",
        "acknowledgement_version",
        "parent_revision_id",
        "restored_from_revision_id",
    }
    for name in required:
        assert name in sql


def test_current_pointer_is_separate_from_stable_asset_identity() -> None:
    sql = DERIVED_ASSET_SCHEMA_SQL.lower()
    asset_body = sql.split("create table if not exists derived_assets", 1)[1].split(");", 1)[0]
    assert "current_revision_id" not in asset_body
    assert "create table if not exists derived_asset_current_revisions" in sql
