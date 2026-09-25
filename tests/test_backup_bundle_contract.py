"""Restore admission for the DB-backed arXiv progress contract."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from substrate.graph.schema import ARXIV_BULK_PROGRESS_COLUMNS
from tools.backup_bundle_contract import BundleCompatibilityError, verify_restore_bundle


def _bundle(root: Path, *, version: int | None = 2) -> Path:
    export = root / "duckdb"
    export.mkdir(parents=True)
    (export / "schema.sql").write_text("CREATE TABLE arxiv_bulk_progress(...);\n")
    (export / "load.sql").write_text("COPY arxiv_bulk_progress ...;\n")
    progress_columns = [
        ["arxiv_bulk_progress", name, number, None, "NO", "VARCHAR"]
        for number, name in enumerate(ARXIV_BULK_PROGRESS_COLUMNS, 1)
    ]
    manifest: dict[str, object] = {
        "counts": {"documents": 8, "arxiv_bulk_progress": 1},
        "columns": progress_columns,
    }
    if version is not None:
        manifest["bundle_contract_version"] = version
    (root / "source_manifest.json").write_text(json.dumps(manifest))
    return root


def test_versioned_bundle_admitted_and_cli_exits_zero(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    assert verify_restore_bundle(root) == "v2"
    result = subprocess.run(
        [sys.executable, "-m", "tools.backup_bundle_contract", str(root)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0
    assert "v2" in result.stdout


@pytest.mark.parametrize("damage", ["missing_table", "missing_column", "future_version"])
def test_incompatible_bundle_refused_before_restore(tmp_path: Path, damage: str) -> None:
    root = _bundle(tmp_path)
    path = root / "source_manifest.json"
    manifest = json.loads(path.read_text())
    if damage == "missing_table":
        del manifest["counts"]["arxiv_bulk_progress"]
    elif damage == "missing_column":
        manifest["columns"].pop()
    else:
        manifest["bundle_contract_version"] = 3
    path.write_text(json.dumps(manifest))
    with pytest.raises(BundleCompatibilityError):
        verify_restore_bundle(root)


def test_legacy_archive_requires_explicit_choice_and_no_cursor_table(tmp_path: Path) -> None:
    root = _bundle(tmp_path, version=None)
    manifest_path = root / "source_manifest.json"
    manifest = json.loads(manifest_path.read_text())
    del manifest["counts"]["arxiv_bulk_progress"]
    manifest["columns"] = []
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BundleCompatibilityError, match="--allow-legacy"):
        verify_restore_bundle(root)
    assert verify_restore_bundle(root, allow_legacy=True) == "legacy-unversioned"

    manifest["counts"]["arxiv_bulk_progress"] = 1
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(BundleCompatibilityError, match="unversioned bundle contains"):
        verify_restore_bundle(root, allow_legacy=True)


def test_missing_or_corrupt_manifest_and_export_fail_closed(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    (root / "source_manifest.json").write_text("{")
    with pytest.raises(BundleCompatibilityError, match="unreadable"):
        verify_restore_bundle(root)
    (root / "duckdb" / "load.sql").unlink()
    with pytest.raises(BundleCompatibilityError, match="incomplete"):
        verify_restore_bundle(root)


def test_runbook_admits_bundle_before_deleting_existing_db() -> None:
    runbook = Path("infrastructure/runbooks/disaster-recovery.md").read_text()
    admission = runbook.index("-m tools.backup_bundle_contract")
    deletion = runbook.index("rm -f /home/antiek/.antiek/antiek.duckdb")
    import_db = runbook.index("IMPORT DATABASE '${RESTORE_DIR}duckdb'")
    assert admission < deletion < import_db
    template = Path("infrastructure/ansible/templates/backup.sh.j2").read_text()
    assert '"bundle_contract_version": 2' in template
