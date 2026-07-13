from __future__ import annotations

import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from interfaces.research.api.marketplace_host_runtime import (
    MARKETPLACE_HOST_DB_PATH_ENV,
    marketplace_host_store_from_env,
)
from substrate.marketplace_host import SQLiteHostStore, backup_sqlite_host_store
from tools.backup_marketplace_sqlite import main as backup_main


def test_runtime_store_is_opt_in_and_explicit_configuration_is_durable(
    tmp_path: Path,
) -> None:
    assert marketplace_host_store_from_env({}) is None
    assert marketplace_host_store_from_env({MARKETPLACE_HOST_DB_PATH_ENV: ""}) is None

    path = tmp_path / "marketplace-host.sqlite3"
    first = marketplace_host_store_from_env(
        {MARKETPLACE_HOST_DB_PATH_ENV: str(path)}
    )
    assert isinstance(first, SQLiteHostStore)
    first.put_document("doc-1", {"document_id": "doc-1"})

    reopened = marketplace_host_store_from_env(
        {MARKETPLACE_HOST_DB_PATH_ENV: str(path)}
    )
    assert isinstance(reopened, SQLiteHostStore)
    assert reopened.get_document("doc-1") == {"document_id": "doc-1"}


def test_module_level_uvicorn_app_uses_explicit_runtime_store(
    tmp_path: Path,
) -> None:
    marketplace_path = tmp_path / "marketplace-host.sqlite3"
    graph_path = tmp_path / "graph.duckdb"
    script = (
        "import importlib; "
        "module = importlib.import_module('interfaces.research.api.app'); "
        "print(module.app.state.marketplace_host_store.path)"
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=Path.cwd(),
        env={
            "PATH": "/usr/bin:/bin",
            MARKETPLACE_HOST_DB_PATH_ENV: str(marketplace_path),
            "ANTIEK_DUCKDB_PATH": str(graph_path),
        },
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(marketplace_path)
    assert SQLiteHostStore(marketplace_path).path == marketplace_path


@pytest.mark.parametrize("value", ["relative.sqlite3", " /tmp/marketplace.sqlite3", " "])
def test_runtime_store_rejects_malformed_explicit_paths(value: str) -> None:
    with pytest.raises(RuntimeError, match=MARKETPLACE_HOST_DB_PATH_ENV):
        marketplace_host_store_from_env({MARKETPLACE_HOST_DB_PATH_ENV: value})


def test_runtime_store_rejects_existing_unrelated_database_without_mutation(
    tmp_path: Path,
) -> None:
    path = tmp_path / "unrelated.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute("CREATE TABLE unrelated(value TEXT)")
    path.chmod(0o640)

    with pytest.raises(RuntimeError, match="failed to initialize"):
        marketplace_host_store_from_env({MARKETPLACE_HOST_DB_PATH_ENV: str(path)})

    with sqlite3.connect(path) as con:
        tables = {
            str(row[0])
            for row in con.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        assert tables == {"unrelated"}
        assert con.execute("PRAGMA user_version").fetchone()[0] == 0
    assert path.stat().st_mode & 0o777 == 0o640


def test_online_backup_round_trips_and_is_mode_0600(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    store = SQLiteHostStore(source)
    store.put_document("doc-1", {"document_id": "doc-1", "title": "Durable"})
    store.put_membership("owner-a", "doc-1")
    store.put_receipt("receipt-1", {"receipt_id": "receipt-1"})

    destination = tmp_path / "snapshot.sqlite3"
    assert backup_sqlite_host_store(source, destination) == destination
    restored = SQLiteHostStore(destination)
    assert restored.get_document("doc-1") == {
        "document_id": "doc-1",
        "title": "Durable",
    }
    assert restored.list_membership("owner-a") == ["doc-1"]
    assert restored.get_receipt("receipt-1") == {"receipt_id": "receipt-1"}
    assert destination.stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(destination) as con:
        assert con.execute("PRAGMA quick_check").fetchall() == [("ok",)]


def test_online_backup_is_consistent_while_writer_transaction_is_active(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.sqlite3"
    store = SQLiteHostStore(source)
    store.put_document("committed", {"document_id": "committed"})

    writer = sqlite3.connect(source)
    try:
        writer.execute("BEGIN IMMEDIATE")
        writer.execute(
            "INSERT INTO hosted_documents(document_id, payload_json) VALUES (?, ?)",
            ("uncommitted", '{"document_id":"uncommitted"}'),
        )
        destination = tmp_path / "snapshot.sqlite3"
        backup_sqlite_host_store(source, destination)
    finally:
        writer.rollback()
        writer.close()

    snapshot = SQLiteHostStore(destination)
    assert snapshot.get_document("committed") == {"document_id": "committed"}
    assert snapshot.get_document("uncommitted") is None


def test_backup_refuses_missing_source_and_existing_destination(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        backup_sqlite_host_store(tmp_path / "missing.sqlite3", tmp_path / "new.sqlite3")

    source = tmp_path / "source.sqlite3"
    SQLiteHostStore(source)
    destination = tmp_path / "existing.sqlite3"
    destination.write_bytes(b"do not replace")
    with pytest.raises(FileExistsError):
        backup_sqlite_host_store(source, destination)
    assert destination.read_bytes() == b"do not replace"

    sidecar_only = tmp_path / "sidecar-only.sqlite3"
    Path(f"{sidecar_only}-wal").write_bytes(b"stale")
    with pytest.raises(FileExistsError, match="sidecar"):
        backup_sqlite_host_store(source, sidecar_only)
    assert not sidecar_only.exists()
    assert Path(f"{sidecar_only}-wal").read_bytes() == b"stale"


def test_backup_rejects_unversioned_schema_without_leaving_output(
    tmp_path: Path,
) -> None:
    source = tmp_path / "unversioned.sqlite3"
    with sqlite3.connect(source) as con:
        con.execute("CREATE TABLE unrelated(value TEXT)")
    destination = tmp_path / "snapshot.sqlite3"

    with pytest.raises(RuntimeError, match="schema version|invalid schema"):
        backup_sqlite_host_store(source, destination)
    assert not destination.exists()


def test_backup_rejects_matching_columns_without_required_constraints(
    tmp_path: Path,
) -> None:
    source = tmp_path / "weak-schema.sqlite3"
    with sqlite3.connect(source) as con:
        con.executescript(
            """
            CREATE TABLE hosted_documents (
                document_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            CREATE TABLE host_memberships (
                sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id TEXT NOT NULL,
                document_id TEXT NOT NULL
            );
            CREATE INDEX host_memberships_owner_sequence
                ON host_memberships(owner_id, sequence);
            CREATE TABLE purchase_receipts (
                receipt_id TEXT PRIMARY KEY,
                payload_json TEXT NOT NULL
            );
            PRAGMA user_version=1;
            """
        )
    destination = tmp_path / "snapshot.sqlite3"

    with pytest.raises(RuntimeError, match="schema objects|foreign key|uniqueness"):
        backup_sqlite_host_store(source, destination)
    assert not destination.exists()


def test_backup_rejects_partial_required_index(tmp_path: Path) -> None:
    source = tmp_path / "partial-index.sqlite3"
    SQLiteHostStore(source)
    with sqlite3.connect(source) as con:
        con.execute("DROP INDEX host_memberships_owner_sequence")
        con.execute(
            "CREATE INDEX host_memberships_owner_sequence "
            "ON host_memberships(owner_id, sequence) WHERE sequence > 0"
        )
    destination = tmp_path / "snapshot.sqlite3"

    with pytest.raises(RuntimeError, match="schema objects|ordering index"):
        backup_sqlite_host_store(source, destination)
    assert not destination.exists()


def test_backup_rejects_unexpected_trigger_and_orphaned_membership(
    tmp_path: Path,
) -> None:
    triggered = tmp_path / "triggered.sqlite3"
    SQLiteHostStore(triggered)
    with sqlite3.connect(triggered) as con:
        con.execute(
            "CREATE TRIGGER erase_receipts AFTER INSERT ON purchase_receipts "
            "BEGIN DELETE FROM purchase_receipts; END"
        )
    with pytest.raises(RuntimeError, match="schema objects"):
        backup_sqlite_host_store(triggered, tmp_path / "triggered-snapshot.sqlite3")

    orphaned = tmp_path / "orphaned.sqlite3"
    SQLiteHostStore(orphaned)
    with sqlite3.connect(orphaned) as con:
        con.execute(
            "INSERT INTO host_memberships(owner_id, document_id) VALUES (?, ?)",
            ("owner-a", "missing-doc"),
        )
    destination = tmp_path / "orphaned-snapshot.sqlite3"
    with pytest.raises(RuntimeError, match="foreign_key_check"):
        backup_sqlite_host_store(orphaned, destination)
    assert not destination.exists()


def test_backup_rejects_invalid_persisted_json(tmp_path: Path) -> None:
    source = tmp_path / "invalid-json.sqlite3"
    SQLiteHostStore(source)
    with sqlite3.connect(source) as con:
        con.execute(
            "INSERT INTO hosted_documents(document_id, payload_json) VALUES (?, ?)",
            ("bad-doc", "not-json"),
        )
    destination = tmp_path / "snapshot.sqlite3"

    with pytest.raises(RuntimeError, match="not valid JSON"):
        backup_sqlite_host_store(source, destination)
    assert not destination.exists()


def test_backup_cli_uses_verified_snapshot_contract(tmp_path: Path) -> None:
    source = tmp_path / "source.sqlite3"
    SQLiteHostStore(source).put_document("doc-cli", {"document_id": "doc-cli"})
    destination = tmp_path / "snapshot.sqlite3"

    assert backup_main(
        ["--source", str(source), "--destination", str(destination)]
    ) == 0
    assert SQLiteHostStore(destination).get_document("doc-cli") == {
        "document_id": "doc-cli"
    }


def test_production_templates_and_runbook_carry_the_same_path_contract() -> None:
    service = Path("infrastructure/ansible/templates/antiek.service.j2").read_text()
    backup = Path("infrastructure/ansible/templates/backup.sh.j2").read_text()
    recovery = Path("infrastructure/runbooks/disaster-recovery.md").read_text()

    expected = (
        "ANTIEK_MARKETPLACE_HOST_DB_PATH={{ antiek_state_dir }}/"
        "marketplace-host.sqlite3"
    )
    assert expected in service
    assert "tools/backup_marketplace_sqlite.py" in backup
    assert '--source "${STATE_DIR}/marketplace-host.sqlite3"' in backup
    assert '--destination "${STAGING}/marketplace-host.sqlite3"' in backup
    assert "systemctl stop antiek" in recovery
    assert "systemctl is-active --quiet antiek" in recovery
    assert "Expected exactly one backup directory" in recovery
    assert "ALLOW_LEGACY_EMPTY_DIRS" in recovery
    assert "Expected exactly one marketplace restore outcome" in recovery
    assert 'mv "${TARGET}" "${TARGET}.pre-restore-${RESTORE_STAMP}"' in recovery
    assert 'rm -f "${MARKETPLACE_RESTORE_TMP}"' in recovery
    assert "set -euo pipefail" in recovery
    assert "verify_sqlite_host_store(p)" in recovery
    assert ".marketplace-host.restore.sqlite3" in recovery
    assert '"${MARKETPLACE_RESTORE_TMP}-wal"' in recovery
    assert '"${MARKETPLACE_RESTORE_TMP}-shm"' in recovery
    assert '"${MARKETPLACE_RESTORE_TMP}-journal"' in recovery
    assert ".marketplace-host.restore.absent" in recovery
    assert '"${MARKETPLACE_DB}-wal"' in recovery
    assert '"${MARKETPLACE_DB}-shm"' in recovery
    assert '"${MARKETPLACE_DB}-journal"' in recovery
    assert ".pre-restore-${RESTORE_STAMP}" in recovery
    assert 'mv "${MARKETPLACE_RESTORE_TMP}" "${MARKETPLACE_DB}"' in recovery
