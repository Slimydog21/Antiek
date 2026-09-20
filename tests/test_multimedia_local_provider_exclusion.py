from __future__ import annotations

from pathlib import Path

import duckdb
import pytest

from substrate.multimedia.local_provider_exclusion import (
    LocalZeroEvidenceConflict,
    LocalZeroEvidenceUnavailable,
    exclude_provider_executions,
)


def _database(path: Path) -> None:
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "CREATE TABLE multimedia_provider_executions "
            "(operator_id TEXT, asset_id TEXT, revision_id TEXT)"
        )


def test_empty_table_returns_exact_sorted_scope_without_writing(tmp_path: Path) -> None:
    path = tmp_path / "runs.duckdb"
    _database(path)
    result = exclude_provider_executions(
        db_path=str(path),
        owner_id="owner-1",
        asset_id="asset-1",
        revision_ids=("revision-2", "revision-1"),
    )
    assert result.revision_ids == ("revision-1", "revision-2")
    assert result.provider_execution_count == 0


def test_missing_database_or_table_is_unavailable_and_not_created(tmp_path: Path) -> None:
    missing = tmp_path / "missing.duckdb"
    with pytest.raises(LocalZeroEvidenceUnavailable, match="evidence_unavailable"):
        exclude_provider_executions(
            db_path=str(missing),
            owner_id="owner-1",
            asset_id="asset-1",
            revision_ids=("revision-1",),
        )
    assert not missing.exists()
    tableless = tmp_path / "tableless.duckdb"
    with duckdb.connect(str(tableless)):
        pass
    with pytest.raises(LocalZeroEvidenceUnavailable, match="evidence_unavailable"):
        exclude_provider_executions(
            db_path=str(tableless),
            owner_id="owner-1",
            asset_id="asset-1",
            revision_ids=("revision-1",),
        )


def test_any_exact_scope_row_blocks_but_unrelated_rows_do_not(tmp_path: Path) -> None:
    path = tmp_path / "runs.duckdb"
    _database(path)
    with duckdb.connect(str(path)) as connection:
        connection.executemany(
            "INSERT INTO multimedia_provider_executions VALUES (?, ?, ?)",
            [
                ("owner-2", "asset-1", "revision-1"),
                ("owner-1", "asset-2", "revision-1"),
                ("owner-1", "asset-1", "historical-revision"),
            ],
        )
    exclude_provider_executions(
        db_path=str(path),
        owner_id="owner-1",
        asset_id="asset-1",
        revision_ids=("revision-1", "narration-child"),
    )
    with duckdb.connect(str(path)) as connection:
        connection.execute(
            "INSERT INTO multimedia_provider_executions VALUES (?, ?, ?)",
            ["owner-1", "asset-1", "narration-child"],
        )
    with pytest.raises(LocalZeroEvidenceConflict, match="evidence_conflict"):
        exclude_provider_executions(
            db_path=str(path),
            owner_id="owner-1",
            asset_id="asset-1",
            revision_ids=("revision-1", "narration-child"),
        )
