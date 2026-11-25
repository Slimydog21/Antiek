"""Behavioral checks for restoring a closed native DuckDB backup."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import tarfile
from pathlib import Path

import duckdb
import pytest

from tools.deploy.backup_native_restore_verify import (
    NativeRestoreReport,
    verify_closed_native_archive,
)
from tools.deploy.backup_restore_verify import (
    ObservationLimits,
    RestoreLimits,
    RestoreRefused,
    RestoreReport,
    SnapshotObservation,
    observe_snapshot,
)

_ROOT = "antiek-backup.ABC12345"


def _source(tmp_path: Path) -> tuple[duckdb.DuckDBPyConnection, Path, bytes]:
    database = tmp_path / "source.duckdb"
    source = duckdb.connect(str(database))
    source.execute("CREATE SEQUENCE s START 10 INCREMENT 3")
    source.execute(
        "CREATE TABLE edges(id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES edges(id), label VARCHAR)"
    )
    source.execute("CREATE INDEX edges_label ON edges(label)")
    source.execute("CREATE TABLE bag(value VARCHAR)")
    source.execute("INSERT INTO edges VALUES (1, NULL, '')")
    source.execute("INSERT INTO edges VALUES (2, 1, NULL)")
    source.execute("INSERT INTO bag VALUES ('a'), ('a'), ('b')")
    for expected in (10, 13, 16, 19):
        assert source.execute("SELECT nextval('s')").fetchone()[0] == expected
    report = observe_snapshot(
        source, scratch_parent=tmp_path, limits=ObservationLimits()
    ).canonical_bytes()
    return source, database, report


def _pack(root: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as stream:
        stream.add(root, arcname=root.name)


def _archive_database(tmp_path: Path, database: Path) -> tuple[Path, Path, Path]:
    root = tmp_path / _ROOT
    native = root / "native"
    native.mkdir(parents=True)
    member = native / "antiek.duckdb"
    shutil.copyfile(database, member)
    archive = tmp_path / "closed-native.tar.gz"
    _pack(root, archive)
    return archive, root, member


def _closed_fixture(tmp_path: Path, mutation: str | None = None) -> tuple[Path, bytes, Path, Path]:
    source, database, expected = _source(tmp_path)
    try:
        if mutation == "content":
            source.execute("UPDATE bag SET value='changed' WHERE value='b'")
        elif mutation == "duplicates":
            source.execute("DELETE FROM bag WHERE value='b'")
            source.execute("INSERT INTO bag VALUES ('a')")
        elif mutation == "count":
            source.execute("INSERT INTO bag VALUES ('extra')")
        elif mutation == "index":
            source.execute("DROP INDEX edges_label")
        elif mutation == "sequence":
            source.execute("DROP SEQUENCE s")
            source.execute("CREATE SEQUENCE s START 10 INCREMENT 3")
        elif mutation == "self_fk":
            source.execute("DROP INDEX edges_label")
            source.execute("DROP TABLE edges")
            source.execute(
                "CREATE TABLE edges(id INTEGER PRIMARY KEY, parent_id INTEGER, label VARCHAR)"
            )
            source.execute("CREATE INDEX edges_label ON edges(label)")
            source.execute("INSERT INTO edges VALUES (1, NULL, '')")
            source.execute("INSERT INTO edges VALUES (2, 1, NULL)")
        elif mutation is not None:
            raise AssertionError(mutation)
        source.execute("CHECKPOINT")
    finally:
        source.close()
    archive, root, member = _archive_database(tmp_path, database)
    return archive, expected, root, member


def _verify(archive: Path, expected: bytes, scratch: Path) -> NativeRestoreReport:
    return verify_closed_native_archive(
        archive=archive,
        source_report_bytes=expected,
        scratch_parent=scratch,
        limits=RestoreLimits.production(),
    )


def test_closed_native_archive_proves_rows_catalog_and_file_and_cleans(tmp_path: Path) -> None:
    archive, expected, _, member = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()

    report = _verify(archive, expected, scratch)

    assert report.report_scheme == "antiek-closed-native-archive-restore-v1"
    assert report.archive_format == "antiek-native-duckdb-v1"
    assert report.archive_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report.archive_bytes == archive.stat().st_size
    assert report.native_member_path == f"{_ROOT}/native/antiek.duckdb"
    assert report.native_member_sha256 == hashlib.sha256(member.read_bytes()).hexdigest()
    assert report.native_member_bytes == member.stat().st_size
    assert report.source_observation_sha256 == report.restored_observation_sha256
    assert report.source_catalog_sha256 == report.restored_catalog_sha256
    assert report.source_counts == report.restored_counts == {"main.bag": 3, "main.edges": 2}
    assert report.source_content_sha256 == report.restored_content_sha256
    assert (
        NativeRestoreReport.from_canonical_bytes(
            report.canonical_bytes(), limits=RestoreLimits.production()
        )
        == report
    )
    with pytest.raises(RestoreRefused, match="^REPORT_FORMAT$"):
        RestoreReport.from_canonical_bytes(
            report.canonical_bytes(), limits=RestoreLimits.production()
        )
    assert list(scratch.iterdir()) == []


def test_native_archive_allows_non_database_companions(tmp_path: Path) -> None:
    archive, expected, root, _ = _closed_fixture(tmp_path)
    (root / "source_manifest.json").write_text('{"untrusted":"metadata"}')
    events = root / "research_events"
    events.mkdir()
    (events / "event.json").write_text("{}")
    skills = root / "knowledge_skills"
    skills.mkdir()
    (skills / "note.json").write_text("{}")
    _pack(root, archive)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = _verify(archive, expected, scratch)
    assert report.source_counts == report.restored_counts == {"main.bag": 3, "main.edges": 2}
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize(
    "mutation, code",
    [
        ("content", "CONTENT_MISMATCH"),
        ("duplicates", "CONTENT_MISMATCH"),
        ("count", "COUNT_MISMATCH"),
        ("index", "CATALOG_MISMATCH"),
        ("sequence", "CATALOG_MISMATCH"),
        ("self_fk", "CATALOG_MISMATCH"),
    ],
)
def test_changed_native_snapshot_refuses(tmp_path: Path, mutation: str, code: str) -> None:
    archive, expected, _, _ = _closed_fixture(tmp_path, mutation)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match=f"^{code}$"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_pre_checkpoint_file_copy_cannot_pass_as_closed_snapshot(tmp_path: Path) -> None:
    source, database, _ = _source(tmp_path)
    try:
        source.execute("CHECKPOINT")
        source.execute("INSERT INTO bag VALUES ('after-checkpoint')")
        expected = observe_snapshot(
            source, scratch_parent=tmp_path, limits=ObservationLimits()
        ).canonical_bytes()
        assert Path(f"{database}.wal").stat().st_size > 0
        archive, _, member = _archive_database(tmp_path, database)
        with duckdb.connect(str(member), read_only=True) as copied:
            assert copied.execute("SELECT count(*) FROM bag").fetchone()[0] == 3
    finally:
        source.close()
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="^COUNT_MISMATCH$"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("change", ["wal", "extra_member", "wrong_directory", "second_root"])
def test_native_layout_rejects_unexpected_members(tmp_path: Path, change: str) -> None:
    archive, expected, root, member = _closed_fixture(tmp_path)
    if change == "wal":
        (member.parent / "antiek.duckdb.wal").write_bytes(b"stale wal")
    elif change == "extra_member":
        (member.parent / "other.duckdb").write_bytes(b"unexpected")
    elif change == "wrong_directory":
        wrong = root / "duckdb"
        wrong.mkdir()
        member.rename(wrong / member.name)
        member.parent.rmdir()
    else:
        other = tmp_path / "antiek-backup.DEF67890"
        other.mkdir()
        with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as stream:
            stream.add(root, arcname=root.name)
            stream.add(other, arcname=other.name)
    if change != "second_root":
        _pack(root, archive)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="^NATIVE_LAYOUT_INVALID$"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_malformed_source_report_refuses_before_extraction(tmp_path: Path) -> None:
    archive, expected, _, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    duplicate = expected.replace(
        b'"catalog_scheme":', b'"catalog_scheme":"wrong","catalog_scheme":', 1
    )
    with pytest.raises(RestoreRefused, match="^SOURCE_REPORT_FORMAT$"):
        _verify(archive, duplicate, scratch)
    assert list(scratch.iterdir()) == []


def test_malformed_native_database_refuses_and_cleans(tmp_path: Path) -> None:
    archive, expected, root, member = _closed_fixture(tmp_path)
    member.write_bytes(b"not a DuckDB database")
    _pack(root, archive)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="^NATIVE_OPEN_OR_OBSERVATION_FAILED$") as raised:
        _verify(archive, expected, scratch)
    assert raised.value.__cause__ is None
    assert list(scratch.iterdir()) == []


def test_native_member_inode_swap_during_open_refuses(tmp_path: Path, monkeypatch) -> None:
    from tools.deploy import backup_native_restore_verify as native_verify

    archive, expected, _, _ = _closed_fixture(tmp_path)
    original_open = native_verify._observe_native

    def swap_then_open(path: Path, *, scratch: Path, limits: ObservationLimits):
        replacement = path.with_name("replacement.duckdb")
        shutil.copyfile(path, replacement)
        os.replace(replacement, path)
        return original_open(path, scratch=scratch, limits=limits)

    monkeypatch.setattr(native_verify, "_observe_native", swap_then_open)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="^NATIVE_FILE_MISMATCH$"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_native_report_rejects_inconsistent_proof(tmp_path: Path) -> None:
    archive, expected, _, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = json.loads(_verify(archive, expected, scratch).canonical_bytes())
    report["source_counts"]["main.bag"] = 4
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(RestoreRefused, match="^REPORT_FORMAT$"):
        NativeRestoreReport.from_canonical_bytes(raw, limits=RestoreLimits.production())
    assert list(scratch.iterdir()) == []


def test_initialized_antiek_schema_survives_native_archive(tmp_path: Path) -> None:
    from runtime.db_lock import flush_warm_writers
    from substrate.graph.schema import init_database_at_path

    database = tmp_path / "source.duckdb"
    init_database_at_path(str(database))
    flush_warm_writers(str(database))
    source = duckdb.connect(str(database))
    try:
        source.execute("INSERT INTO write_log(purpose) VALUES ('native_restore_fixture')")
        expected = observe_snapshot(
            source, scratch_parent=tmp_path, limits=ObservationLimits()
        ).canonical_bytes()
        source.execute("CHECKPOINT")
    finally:
        source.close()
    archive, _, _ = _archive_database(tmp_path, database)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = _verify(archive, expected, scratch)
    assert len(report.restored_counts) == 54
    observation = SnapshotObservation.from_canonical_bytes(expected, limits=ObservationLimits())
    assert len(observation.catalog_objects) == 1248
    assert (
        sum(
            object_["kind"] == "constraint"
            and object_["type"] == "FOREIGN KEY"
            and object_["table"] == object_["referenced_table"]
            for object_ in observation.catalog_objects
        )
        == 4
    )
    assert report.source_observation_sha256 == report.restored_observation_sha256
    assert list(scratch.iterdir()) == []


def test_reopened_nextval_without_logged_write_refuses_native_copy(tmp_path: Path) -> None:
    database = tmp_path / "source.duckdb"
    created = duckdb.connect(str(database))
    created.execute("CREATE SEQUENCE s START 1")
    created.close()
    source = duckdb.connect(str(database))
    try:
        assert source.execute("SELECT nextval('s')").fetchone()[0] == 1
        expected = observe_snapshot(
            source, scratch_parent=tmp_path, limits=ObservationLimits()
        ).canonical_bytes()
        source.execute("CHECKPOINT")
    finally:
        source.close()
    archive, _, _ = _archive_database(tmp_path, database)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="^CATALOG_MISMATCH$"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []
