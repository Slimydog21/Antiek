"""Restore admission for the DB-backed arXiv progress contract."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from substrate.graph.schema import init_database_at_path
from tools.backup_bundle_contract import BundleCompatibilityError, verify_restore_bundle
from tools.backup_normalize_schema import normalize_exported_schema_sql


def _bundle(root: Path, *, version: int | None = 2) -> Path:
    source = root / "source.duckdb"
    init_database_at_path(str(source))
    con = duckdb.connect(str(source))
    if version is None:
        con.execute("DROP TABLE arxiv_bulk_progress")
    export = root / "duckdb"
    con.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    schema = export / "schema.sql"
    schema.write_text(normalize_exported_schema_sql(schema.read_text()))
    tables = [
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables "
            "WHERE table_schema='main' AND table_type='BASE TABLE' ORDER BY table_name"
        ).fetchall()
    ]
    def quoted(name: str) -> str:
        return '"' + name.replace('"', '""') + '"'

    manifest: dict[str, object] = {
        "counts": {
            name: con.execute(f"SELECT COUNT(*) FROM {quoted(name)}").fetchone()[0]
            for name in tables
        },
        "columns": con.execute(
            "SELECT table_name, column_name, ordinal_position, column_default, "
            "is_nullable, data_type FROM information_schema.columns "
            "WHERE table_schema='main' ORDER BY table_name, ordinal_position"
        ).fetchall(),
        "constraints": con.execute(
            "SELECT table_name, constraint_type, constraint_text, "
            "constraint_column_names, referenced_table, referenced_column_names "
            "FROM duckdb_constraints() WHERE schema_name='main' "
            "AND NOT (constraint_type='FOREIGN KEY' AND referenced_table=table_name) "
            "ORDER BY table_name, constraint_type, constraint_text, constraint_column_names"
        ).fetchall(),
        "indexes": con.execute(
            "SELECT index_name, table_name, is_unique, is_primary, expressions, sql "
            "FROM duckdb_indexes() WHERE schema_name='main' ORDER BY table_name, index_name"
        ).fetchall(),
    }
    con.close()
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
    with pytest.raises(BundleCompatibilityError, match="--allow-legacy"):
        verify_restore_bundle(root)
    assert verify_restore_bundle(root, allow_legacy=True) == "legacy-unversioned"

    manifest["counts"]["arxiv_bulk_progress"] = 0
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


def test_valid_manifest_cannot_hide_broken_or_wrong_export(tmp_path: Path) -> None:
    root = _bundle(tmp_path)
    schema = root / "duckdb" / "schema.sql"
    schema.write_text("this is not valid SQL")
    with pytest.raises(BundleCompatibilityError, match="scratch IMPORT"):
        verify_restore_bundle(root)


def test_runbook_admits_bundle_before_deleting_existing_db() -> None:
    runbook = Path("infrastructure/runbooks/disaster-recovery.md").read_text()
    admission = runbook.index("-m tools.backup_bundle_contract")
    event_copy = runbook.index('rsync -a "${RESTORE_DIR}research_events/')
    deletion = runbook.index("rm -f /home/antiek/.antiek/antiek.duckdb")
    import_db = runbook.index("IMPORT DATABASE '${RESTORE_DIR}duckdb'")
    assert admission < event_copy < deletion < import_db
    assert runbook.count("--allow-legacy") >= 2
    for shell in re.findall(r"```bash\n(.*?)```", runbook, flags=re.DOTALL):
        if "tools.backup_bundle_contract" not in shell:
            continue
        shell = shell.replace("ssh root@<new-vm-ip>", ":")
        parsed = subprocess.run(
            ["bash", "-n"], input=shell, text=True, capture_output=True, check=False
        )
        assert parsed.returncode == 0, parsed.stderr
    template = Path("infrastructure/ansible/templates/backup.sh.j2").read_text()
    assert '"bundle_contract_version": 2' in template
