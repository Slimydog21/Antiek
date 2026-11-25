"""DuckDB observation and closed-archive restore verification fixtures."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
from pathlib import Path

import duckdb
import pytest

from tools.deploy.backup_restore_verify import (
    ObservationLimits,
    RestoreLimits,
    RestoreRefused,
    RestoreReport,
    SnapshotObservation,
    observe_snapshot,
    verify_closed_archive,
)


def _observe(connection, scratch: Path):
    return observe_snapshot(connection, scratch_parent=scratch, limits=ObservationLimits())


def test_self_fk_sequence_and_row_multiset(tmp_path: Path) -> None:
    connection = duckdb.connect(str(tmp_path / "source.db"))
    connection.execute("CREATE SEQUENCE seq_write_log_id START 10 INCREMENT 3")
    connection.execute("CREATE SEQUENCE write_event_outbox_sequence START 5")
    connection.execute(
        "CREATE TABLE edges(edge_id INTEGER PRIMARY KEY, superseded_by INTEGER REFERENCES edges(edge_id), label TEXT)"
    )
    connection.execute(
        "CREATE TABLE deliverable_sections(section_id INTEGER PRIMARY KEY, parent_section_id INTEGER REFERENCES deliverable_sections(section_id))"
    )
    connection.execute("CREATE INDEX idx_edges_label ON edges(label)")
    connection.execute("INSERT INTO edges VALUES (1, NULL, '')")
    connection.execute("INSERT INTO edges VALUES (2, 1, NULL), (3, 1, NULL)")
    connection.execute("INSERT INTO deliverable_sections VALUES (1, NULL)")
    connection.execute("INSERT INTO deliverable_sections VALUES (2, 1)")
    for expected in (10, 13, 16, 19):
        assert connection.execute("SELECT nextval('seq_write_log_id')").fetchone()[0] == expected

    first = _observe(connection, tmp_path)
    assert (
        SnapshotObservation.from_canonical_bytes(
            first.canonical_bytes(), limits=ObservationLimits()
        )
        == first
    )
    assert (
        next(
            o
            for o in first.catalog_objects
            if o["kind"] == "sequence" and o["name"] == "seq_write_log_id"
        )["next_value"]
        == 22
    )
    fk = [
        o for o in first.catalog_objects if o["kind"] == "constraint" and o["type"] == "FOREIGN KEY"
    ]
    assert {(o["table"], o["referenced_table"]) for o in fk} == {
        ("edges", "edges"),
        ("deliverable_sections", "deliverable_sections"),
    }
    connection.execute("CREATE TABLE reordered AS SELECT * FROM edges ORDER BY edge_id DESC")
    connection.execute("DELETE FROM edges WHERE edge_id = 3")
    connection.execute("INSERT INTO edges SELECT * FROM reordered WHERE edge_id = 3")
    connection.execute("DROP TABLE reordered")
    assert _observe(connection, tmp_path).tables["main.edges"] == first.tables["main.edges"]
    connection.execute("UPDATE edges SET label = 'changed' WHERE edge_id = 2")
    changed = _observe(connection, tmp_path)
    assert changed.tables["main.edges"].row_count == first.tables["main.edges"].row_count
    assert changed.tables["main.edges"].content_sha256 != first.tables["main.edges"].content_sha256
    connection.close()


def test_duplicate_rows_change_digest_without_count_change(tmp_path: Path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE items (value TEXT)")
    connection.execute("INSERT INTO items VALUES ('a'), ('a'), ('b')")
    original = _observe(connection, tmp_path).tables["main.items"]
    connection.execute("DELETE FROM items WHERE value = 'b'")
    connection.execute("INSERT INTO items VALUES ('a')")
    changed = _observe(connection, tmp_path).tables["main.items"]
    assert changed.row_count == original.row_count
    assert changed.content_sha256 != original.content_sha256


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.update(catalog_scheme="wrong"),
        lambda d: d.update(tables={"main.t": {"row_count": True, "content_sha256": "0" * 64}}),
        lambda d: d.update(extra=True),
    ],
)
def test_malformed_source_report_refused(tmp_path: Path, change) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE t (n INTEGER)")
    report = json.loads(_observe(connection, tmp_path).canonical_bytes())
    change(report)
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(RestoreRefused):
        SnapshotObservation.from_canonical_bytes(raw, limits=ObservationLimits())


def test_duplicate_keys_and_oversized_report_refused(tmp_path: Path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE t (n INTEGER)")
    raw = _observe(connection, tmp_path).canonical_bytes()
    duplicate = raw.replace(b'"catalog_scheme":', b'"catalog_scheme":"wrong","catalog_scheme":', 1)
    with pytest.raises(RestoreRefused, match="SOURCE_REPORT_FORMAT"):
        SnapshotObservation.from_canonical_bytes(duplicate, limits=ObservationLimits())
    with pytest.raises(RestoreRefused, match="SOURCE_REPORT_SIZE"):
        SnapshotObservation.from_canonical_bytes(
            raw, limits=ObservationLimits(source_report_bytes=4)
        )


@pytest.mark.parametrize(
    "ddl",
    [
        "CREATE VIEW unsupported_view AS SELECT 1 AS n",
        "CREATE TYPE unsupported_type AS ENUM ('a', 'b')",
        "CREATE MACRO unsupported_macro() AS 1",
        "CREATE TABLE unsupported_table (n STRUCT(a INTEGER))",
        "CREATE TABLE unsupported_generated (n INTEGER, doubled INTEGER GENERATED ALWAYS AS (n * 2))",
    ],
)
def test_unsupported_catalog_or_content_refused(tmp_path: Path, ddl: str) -> None:
    connection = duckdb.connect()
    connection.execute(ddl)
    with pytest.raises(RestoreRefused):
        _observe(connection, tmp_path)


def test_attached_database_refused(tmp_path: Path) -> None:
    connection = duckdb.connect()
    connection.execute(f"ATTACH '{tmp_path / 'other.db'}' AS other")
    with pytest.raises(RestoreRefused, match="CATALOG_UNSUPPORTED"):
        _observe(connection, tmp_path)


def test_dotted_schema_or_table_cannot_alias_table_report_key(tmp_path: Path) -> None:
    connection = duckdb.connect()
    connection.execute('CREATE SCHEMA "a.b"')
    connection.execute('CREATE TABLE "a.b".c (n INTEGER)')
    connection.execute("CREATE SCHEMA a")
    connection.execute('CREATE TABLE a."b.c" (n INTEGER)')
    with pytest.raises(RestoreRefused, match="CATALOG_UNSUPPORTED"):
        _observe(connection, tmp_path)


def test_initialized_antiek_schema_is_fully_observed(tmp_path: Path) -> None:
    from substrate.graph.schema import init_database_at_path

    database = str(tmp_path / "antiek.db")
    init_database_at_path(database)
    connection = duckdb.connect(database)
    try:
        observation = _observe(connection, tmp_path)
        assert len(observation.tables) == 54
        assert {o["name"] for o in observation.catalog_objects if o["kind"] == "sequence"} == {
            "seq_write_log_id",
            "write_event_outbox_sequence",
        }
        self_fks = {
            (o["table"], tuple(o["columns"]))
            for o in observation.catalog_objects
            if o["kind"] == "constraint"
            and o["type"] == "FOREIGN KEY"
            and o["table"] == o["referenced_table"]
        }
        assert ("edges", ("superseded_by",)) in self_fks
        assert ("deliverable_sections", ("parent_section_id",)) in self_fks
        assert (
            SnapshotObservation.from_canonical_bytes(
                observation.canonical_bytes(), limits=ObservationLimits()
            )
            == observation
        )
    finally:
        connection.close()


def test_sequence_continuation_survives_real_export_import(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.db"))
    source.execute("CREATE SEQUENCE s START 10 INCREMENT 3")
    source.execute("CREATE TABLE t (id INTEGER DEFAULT nextval('s'))")
    for _ in range(4):
        source.execute("INSERT INTO t DEFAULT VALUES")
    expected = _observe(source, tmp_path)
    export = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    restored = duckdb.connect(str(tmp_path / "restored.db"))
    restored.execute(f"IMPORT DATABASE '{export}'")
    actual = _observe(restored, tmp_path)
    assert actual == expected
    assert restored.execute("SELECT nextval('s')").fetchone()[0] == 22
    source.close()
    restored.close()


def test_supported_constraints_and_index_survive_roundtrip(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.db"))
    source.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
    source.execute(
        "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id), score INTEGER CHECK (score > 0))"
    )
    source.execute("CREATE INDEX child_parent ON child(parent_id)")
    source.execute("INSERT INTO parent VALUES (1)")
    source.execute("INSERT INTO child VALUES (2, 1, 3)")
    expected = _observe(source, tmp_path)
    export = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    restored = duckdb.connect(str(tmp_path / "restored.db"))
    restored.execute(f"IMPORT DATABASE '{export}'")
    assert _observe(restored, tmp_path) == expected
    source.close()
    restored.close()


def test_normalized_real_export_exposes_all_lost_self_fks(tmp_path: Path) -> None:
    from substrate.graph.schema import init_database_at_path
    from tools.backup_normalize_schema import normalize_exported_schema_sql

    database = str(tmp_path / "antiek.db")
    init_database_at_path(database)
    source = duckdb.connect(database)
    expected = _observe(source, tmp_path)
    export = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    source.close()
    schema = export / "schema.sql"
    schema.write_text(normalize_exported_schema_sql(schema.read_text()))
    restored = duckdb.connect(str(tmp_path / "restored.db"))
    restored.execute(f"IMPORT DATABASE '{export}'")
    actual = _observe(restored, tmp_path)
    restored.close()

    assert expected.tables == actual.tables
    source_only = [o for o in expected.catalog_objects if o not in actual.catalog_objects]
    restored_only = [o for o in actual.catalog_objects if o not in expected.catalog_objects]
    assert restored_only == []
    assert {(o["table"], tuple(o["columns"])) for o in source_only} == {
        ("edges", ("superseded_by",)),
        ("deliverable_sections", ("parent_section_id",)),
        ("derived_asset_revisions", ("derived_asset_id", "parent_revision_id")),
        (
            "derived_asset_revisions",
            ("derived_asset_id", "restored_from_revision_id", "content_sha256", "manifest_sha256"),
        ),
    }


def test_catalog_macros_cannot_hide_persistent_objects(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.db"))
    source.execute("CREATE TABLE hidden (n INTEGER)")
    source.execute("INSERT INTO hidden VALUES (7)")
    source.execute(
        "CREATE MACRO duckdb_tables() AS TABLE "
        "SELECT * FROM system.main.duckdb_tables() WHERE table_name <> 'hidden'"
    )
    source.execute(
        "CREATE MACRO duckdb_functions() AS TABLE "
        "SELECT * FROM system.main.duckdb_functions() "
        "WHERE function_name NOT IN ('duckdb_tables', 'duckdb_functions')"
    )
    assert (
        source.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name='hidden'").fetchone()[
            0
        ]
        == 0
    )
    assert (
        source.execute(
            "SELECT count(*) FROM system.main.duckdb_tables() WHERE table_name='hidden'"
        ).fetchone()[0]
        == 1
    )
    with pytest.raises(RestoreRefused, match="CATALOG_UNSUPPORTED"):
        _observe(source, tmp_path)

    export = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    restored = duckdb.connect(str(tmp_path / "restored.db"))
    restored.execute(f"IMPORT DATABASE '{export}'")
    with pytest.raises(RestoreRefused, match="CATALOG_UNSUPPORTED"):
        _observe(restored, tmp_path)
    source.close()
    restored.close()


def test_collation_mutated_export_refused(tmp_path: Path) -> None:
    source = duckdb.connect(str(tmp_path / "source.db"))
    source.execute("CREATE TABLE t (s VARCHAR)")
    source.execute("INSERT INTO t VALUES ('A')")
    _observe(source, tmp_path)
    export = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    source.close()
    schema = export / "schema.sql"
    original = schema.read_text()
    assert "s VARCHAR" in original
    schema.write_text(original.replace("s VARCHAR", "s VARCHAR COLLATE NOCASE", 1))
    restored = duckdb.connect(str(tmp_path / "restored.db"))
    restored.execute(f"IMPORT DATABASE '{export}'")
    assert restored.execute("SELECT count(*) FROM t WHERE s = 'a'").fetchone()[0] == 1
    with pytest.raises(RestoreRefused, match="CATALOG_UNSUPPORTED"):
        _observe(restored, tmp_path)
    restored.close()


def test_catalog_inventory_cap_refuses_before_table_scan(tmp_path: Path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE t (n INTEGER)")
    with pytest.raises(RestoreRefused, match="OBSERVATION_SIZE"):
        observe_snapshot(
            connection, scratch_parent=tmp_path, limits=ObservationLimits(catalog_objects=1)
        )


def _closed_fixture(tmp_path: Path, *, mutation: str | None = None, manifest: bytes | None = None):
    root = tmp_path / "antiek-backup.ABC12345"
    root.mkdir()
    source = duckdb.connect(str(tmp_path / "source.db"))
    source.execute("CREATE SEQUENCE s START 10 INCREMENT 3")
    source.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY, label VARCHAR)")
    source.execute(
        "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER REFERENCES parent(id), score INTEGER CHECK (score > 0))"
    )
    source.execute("CREATE TABLE bag (value VARCHAR)")
    source.execute("CREATE INDEX child_parent ON child(parent_id)")
    source.execute("INSERT INTO parent VALUES (1, ''), (2, NULL)")
    source.execute("INSERT INTO child VALUES (10, 1, 3), (11, 1, 3)")
    source.execute("INSERT INTO bag VALUES ('a'), ('a'), ('b')")
    for _ in range(4):
        source.execute("SELECT nextval('s')")
    expected = _observe(source, tmp_path).canonical_bytes()
    if mutation == "content":
        source.execute("UPDATE parent SET label='changed' WHERE id=1")
    elif mutation == "duplicates":
        source.execute("DELETE FROM bag WHERE value='b'")
        source.execute("INSERT INTO bag VALUES ('a')")
    elif mutation == "count":
        source.execute("INSERT INTO parent VALUES (3, 'extra')")
    elif mutation == "index":
        source.execute("DROP INDEX child_parent")
    elif mutation == "sequence":
        source.execute("DROP SEQUENCE s")
        source.execute("CREATE SEQUENCE s START 10 INCREMENT 3")
    elif mutation == "table":
        source.execute("DROP TABLE bag")
        source.execute("CREATE TABLE substitute (value VARCHAR)")
        source.execute("INSERT INTO substitute VALUES ('a'), ('a'), ('b')")
    elif mutation == "constraint":
        source.execute("DROP INDEX child_parent")
        source.execute("DROP TABLE child")
        source.execute(
            "CREATE TABLE child (id INTEGER PRIMARY KEY, parent_id INTEGER, score INTEGER)"
        )
        source.execute("CREATE INDEX child_parent ON child(parent_id)")
        source.execute("INSERT INTO child VALUES (10, 1, 3), (11, 1, 3)")
    elif mutation == "view":
        source.execute("CREATE VIEW unsupported_view AS SELECT id FROM parent")
    export = root / "duckdb"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    source.close()
    if manifest is not None:
        (root / "source_manifest.json").write_bytes(manifest)
    events = root / "research_events"
    events.mkdir()
    (events / "event.json").write_text("{}")
    archive = tmp_path / "closed.tar.gz"
    _pack(root, archive)
    return archive, expected, root


def _pack(root: Path, archive: Path) -> None:
    with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as stream:
        stream.add(root, arcname=root.name)


def _gnu_tar() -> str:
    command = shutil.which("gtar") or shutil.which("tar")
    if (
        command is None
        or "GNU tar"
        not in subprocess.run(
            [command, "--version"], capture_output=True, text=True, check=False
        ).stdout
    ):
        pytest.skip("GNU tar is unavailable")
    return command


def _verify(archive: Path, expected: bytes, scratch: Path):
    return verify_closed_archive(
        archive=archive,
        source_report_bytes=expected,
        scratch_parent=scratch,
        limits=RestoreLimits.production(),
    )


def test_closed_archive_success_binds_report_and_cleans(tmp_path: Path) -> None:
    archive, expected, _ = _closed_fixture(tmp_path, manifest=b'{"forged":"ignored"}')
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = _verify(archive, expected, scratch)
    assert report.archive_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report.archive_bytes == archive.stat().st_size
    assert report.source_observation_sha256 == report.restored_observation_sha256
    assert report.source_catalog_sha256 == report.restored_catalog_sha256
    assert (
        report.source_counts
        == report.restored_counts
        == {"main.bag": 3, "main.child": 2, "main.parent": 2}
    )
    assert report.source_content_sha256 == report.restored_content_sha256
    assert (
        RestoreReport.from_canonical_bytes(
            report.canonical_bytes(), limits=RestoreLimits.production()
        )
        == report
    )
    assert list(scratch.iterdir()) == []


def test_producer_shaped_gnu_tar_success(tmp_path: Path) -> None:
    gtar = _gnu_tar()
    archive, expected, root = _closed_fixture(tmp_path, manifest=b'{"forged":"ignored"}')
    subprocess.run([gtar, "-czf", str(archive), "-C", str(tmp_path), root.name], check=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = _verify(archive, expected, scratch)
    assert report.archive_sha256 == hashlib.sha256(archive.read_bytes()).hexdigest()
    assert report.archive_bytes == archive.stat().st_size
    assert report.source_counts == report.restored_counts
    assert report.source_content_sha256 == report.restored_content_sha256
    assert list(scratch.iterdir()) == []


def test_same_count_mutation_refuses_forged_manifest(tmp_path: Path) -> None:
    archive, expected, _ = _closed_fixture(
        tmp_path, mutation="content", manifest=expected_manifest()
    )
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="CONTENT_MISMATCH"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def expected_manifest() -> bytes:
    return b'{"source_counts":{"main.parent":2},"claim":"verified"}'


@pytest.mark.parametrize(
    "mutation, code",
    [
        ("duplicates", "CONTENT_MISMATCH"),
        ("count", "COUNT_MISMATCH"),
        ("index", "CATALOG_MISMATCH"),
        ("sequence", "CATALOG_MISMATCH"),
        ("table", "TABLE_SET_MISMATCH"),
        ("constraint", "CATALOG_MISMATCH"),
        ("view", "CATALOG_UNSUPPORTED"),
    ],
)
def test_changed_restored_snapshot_refuses(tmp_path: Path, mutation: str, code: str) -> None:
    archive, expected, _ = _closed_fixture(tmp_path, mutation=mutation)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match=code):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


@pytest.mark.parametrize("change", ["extra_sql", "missing_schema", "second_root"])
def test_bad_export_layout_refuses_and_cleans(tmp_path: Path, change: str) -> None:
    archive, expected, root = _closed_fixture(tmp_path)
    if change == "extra_sql":
        (root / "duckdb" / "extra.sql").write_text("SELECT 1")
    elif change == "missing_schema":
        (root / "duckdb" / "schema.sql").unlink()
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
    with pytest.raises(RestoreRefused, match="EXPORT_LAYOUT_INVALID"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_damaged_archive_refuses_and_cleans(tmp_path: Path) -> None:
    archive, expected, _ = _closed_fixture(tmp_path)
    archive.write_bytes(archive.read_bytes()[:-8])
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="ARCHIVE_ADMISSION_FAILED"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_invalid_import_sql_refuses_and_cleans(tmp_path: Path) -> None:
    archive, expected, root = _closed_fixture(tmp_path)
    (root / "duckdb" / "schema.sql").write_text("CREATE TABLE broken (")
    _pack(root, archive)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="IMPORT_OR_OBSERVATION_FAILED") as raised:
        _verify(archive, expected, scratch)
    assert raised.value.__cause__ is None
    assert list(scratch.iterdir()) == []


def test_invalid_source_report_refuses_before_scratch(tmp_path: Path) -> None:
    archive, _, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="SOURCE_REPORT_FORMAT"):
        _verify(archive, b'{"duplicate":1,"duplicate":2}', scratch)
    assert list(scratch.iterdir()) == []


def test_restore_report_parser_is_bounded_and_duplicate_key_rejecting(tmp_path: Path) -> None:
    archive, expected, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    raw = _verify(archive, expected, scratch).canonical_bytes()
    duplicate = raw.replace(b'"archive_bytes":', b'"archive_bytes":1,"archive_bytes":', 1)
    with pytest.raises(RestoreRefused, match="REPORT_FORMAT"):
        RestoreReport.from_canonical_bytes(duplicate, limits=RestoreLimits.production())
    limits = RestoreLimits(ObservationLimits(report_bytes=4), RestoreLimits.production().archive)
    with pytest.raises(RestoreRefused, match="REPORT_FORMAT"):
        RestoreReport.from_canonical_bytes(raw, limits=limits)
    wrong = json.loads(raw)
    wrong["report_scheme"] = "wrong"
    with pytest.raises(RestoreRefused, match="REPORT_FORMAT"):
        RestoreReport.from_canonical_bytes(
            json.dumps(wrong, sort_keys=True, separators=(",", ":")).encode(),
            limits=RestoreLimits.production(),
        )


@pytest.mark.parametrize(
    "field, key, replacement",
    [
        ("source_counts", "main.bag", 4),
        ("source_content_sha256", "main.bag", "0" * 64),
        ("source_observation_sha256", None, "0" * 64),
        ("source_catalog_sha256", None, "0" * 64),
    ],
)
def test_restore_report_parser_rejects_unequal_proofs(
    tmp_path: Path, field: str, key: str | None, replacement: int | str
) -> None:
    archive, expected, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    report = json.loads(_verify(archive, expected, scratch).canonical_bytes())
    if key is None:
        report[field] = replacement
    else:
        report[field][key] = replacement
    raw = json.dumps(report, sort_keys=True, separators=(",", ":")).encode()
    with pytest.raises(RestoreRefused, match="REPORT_FORMAT"):
        RestoreReport.from_canonical_bytes(raw, limits=RestoreLimits.production())


def test_quoted_scratch_path_is_sql_literal_safe(tmp_path: Path) -> None:
    archive, expected, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "quote'parent"
    scratch.mkdir()
    report = _verify(archive, expected, scratch)
    assert report.source_observation_sha256 == report.restored_observation_sha256
    assert list(scratch.iterdir()) == []


def test_quoted_archive_root_refuses_before_import(tmp_path: Path) -> None:
    archive, expected, root = _closed_fixture(tmp_path)
    with tarfile.open(archive, "w:gz", format=tarfile.USTAR_FORMAT) as stream:
        stream.add(root, arcname="antiek-backup.'ABC12345")
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="EXPORT_LAYOUT_INVALID"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_cleanup_failure_overrides_success(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import tools.deploy.backup_restore_verify as verifier

    archive, expected, _ = _closed_fixture(tmp_path)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    original = verifier.shutil.rmtree

    def failed_cleanup(path):
        original(path)
        raise OSError("simulated cleanup failure")

    monkeypatch.setattr(verifier.shutil, "rmtree", failed_cleanup)
    with pytest.raises(RestoreRefused, match="CLEANUP_FAILED"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []


def test_real_antiek_gnu_tar_refuses_four_lost_self_fks(tmp_path: Path) -> None:
    from substrate.graph.schema import init_database_at_path
    from tools.backup_normalize_schema import normalize_exported_schema_sql

    gtar = _gnu_tar()
    database = str(tmp_path / "antiek.db")
    init_database_at_path(database)
    source = duckdb.connect(database)
    expected = _observe(source, tmp_path).canonical_bytes()
    root = tmp_path / "antiek-backup.ABC12345"
    root.mkdir()
    export = root / "duckdb"
    source.execute(f"EXPORT DATABASE '{export}' (FORMAT PARQUET)")
    source.close()
    files = list(export.iterdir())
    assert len([path for path in files if path.suffix == ".parquet"]) == 54
    assert {path.name for path in files if path.suffix != ".parquet"} == {"schema.sql", "load.sql"}
    schema = export / "schema.sql"
    schema.write_text(normalize_exported_schema_sql(schema.read_text()))
    archive = tmp_path / "closed.tar.gz"
    subprocess.run([gtar, "-czf", str(archive), "-C", str(tmp_path), root.name], check=True)
    scratch = tmp_path / "scratch"
    scratch.mkdir()
    with pytest.raises(RestoreRefused, match="CATALOG_MISMATCH"):
        _verify(archive, expected, scratch)
    assert list(scratch.iterdir()) == []
