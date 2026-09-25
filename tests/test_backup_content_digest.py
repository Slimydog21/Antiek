"""Behavioral checks for the local DuckDB row-multiset digest."""

from __future__ import annotations

from decimal import localcontext

import duckdb
import pytest

from tools.deploy.backup_content_digest import CONTENT_SCHEME, table_content_sha256


def test_row_order_is_ignored_but_changed_values_and_duplicates_are_not(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE items (id INTEGER, label TEXT)")
    connection.execute("INSERT INTO items VALUES (1, 'one'), (2, 'two'), (1, 'one')")
    original = table_content_sha256(connection, "items", scratch_dir=tmp_path, chunk_rows=1)
    connection.execute("DELETE FROM items")
    connection.execute("INSERT INTO items VALUES (1, 'one'), (1, 'one'), (2, 'two')")
    assert table_content_sha256(connection, "items", scratch_dir=tmp_path, chunk_rows=2) == original
    connection.execute("UPDATE items SET label = 'TWO' WHERE id = 2")
    assert table_content_sha256(connection, "items", scratch_dir=tmp_path, chunk_rows=1) != original
    connection.execute("UPDATE items SET label = 'two' WHERE id = 2")
    connection.execute("DELETE FROM items WHERE id = 2")
    connection.execute("INSERT INTO items VALUES (3, 'two')")
    assert connection.execute("SELECT count(*) FROM items").fetchone()[0] == 3
    assert table_content_sha256(connection, "items", scratch_dir=tmp_path, chunk_rows=1) != original
    assert not list(tmp_path.glob("antiek-row-digest-*"))
    assert CONTENT_SCHEME == "antiek-row-multiset-sha256-v1"


def test_schema_identity_and_quoted_identifiers(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute('CREATE SCHEMA "odd""schema"')
    connection.execute('CREATE TABLE "odd""schema"."select" ("x""y" INTEGER)')
    connection.execute('INSERT INTO "odd""schema"."select" VALUES (5)')
    first = table_content_sha256(
        connection, "select", schema_name='odd"schema', scratch_dir=tmp_path
    )
    connection.execute('ALTER TABLE "odd""schema"."select" RENAME COLUMN "x""y" TO z')
    assert (
        table_content_sha256(connection, "select", schema_name='odd"schema', scratch_dir=tmp_path)
        != first
    )
    with pytest.raises(ValueError, match="invalid SQL identifier"):
        table_content_sha256(connection, "bad\x00name")


def test_external_merge_across_more_than_one_pass(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE many (value INTEGER)")
    connection.execute("INSERT INTO many SELECT range FROM range(70)")
    original = table_content_sha256(connection, "many", scratch_dir=tmp_path, chunk_rows=1)
    connection.execute("DELETE FROM many")
    connection.execute("INSERT INTO many SELECT 69 - range FROM range(70)")
    assert table_content_sha256(connection, "many", scratch_dir=tmp_path, chunk_rows=3) == original
    assert not list(tmp_path.glob("antiek-row-digest-*"))


def test_null_empty_decimal_temporal_blob_and_float_edges(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute(
        "CREATE TABLE values_test (text_value TEXT, list_value FLOAT[], "
        "decimal_value DECIMAL(18,6), date_value DATE, time_value TIMESTAMP, "
        "blob_value BLOB, float_value FLOAT, double_value DOUBLE, bool_value BOOLEAN, big BIGINT)"
    )
    connection.execute(
        "INSERT INTO values_test VALUES "
        "(NULL, NULL, 1.2, DATE '2024-01-02', TIMESTAMP '2024-01-02 03:04:05.000006', "
        "NULL, ?, 'NaN'::DOUBLE, TRUE, 4)",
        [-0.0],
    )
    base = table_content_sha256(connection, "values_test", scratch_dir=tmp_path)
    connection.execute(
        "UPDATE values_test SET text_value = '', list_value = [], blob_value = ''::BLOB"
    )
    assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) != base
    connection.execute(
        "UPDATE values_test SET text_value = NULL, list_value = NULL, blob_value = NULL"
    )
    assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) == base
    connection.execute("DELETE FROM values_test")
    connection.execute(
        "INSERT INTO values_test VALUES "
        "(NULL, NULL, 1.2, DATE '2024-01-02', TIMESTAMP '2024-01-02 03:04:05.000006', "
        "NULL, ?, 'NaN'::DOUBLE, TRUE, 4)",
        [0.0],
    )
    assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) != base
    connection.execute("DELETE FROM values_test")
    connection.execute(
        "INSERT INTO values_test VALUES "
        "(NULL, NULL, 1.2, DATE '2024-01-02', TIMESTAMP '2024-01-02 03:04:05.000006', "
        "NULL, ?, 'NaN'::DOUBLE, TRUE, 4)",
        [-0.0],
    )
    assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) == base
    for assignment in (
        "list_value = [1.0, NULL, 2.0]",
        "list_value = [2.0, NULL, 1.0]",
        "decimal_value = 1.200001",
        "date_value = DATE '2024-01-03'",
        "time_value = TIMESTAMP '2024-01-02 03:04:05.000007'",
        "blob_value = '\\x00\\xFF'::BLOB",
        "double_value = 'Infinity'::DOUBLE",
    ):
        connection.execute("UPDATE values_test SET " + assignment)
        assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) != base
        connection.execute("DELETE FROM values_test")
        connection.execute(
            "INSERT INTO values_test VALUES "
            "(NULL, NULL, 1.200000, DATE '2024-01-02', TIMESTAMP '2024-01-02 03:04:05.000006', "
            "NULL, ?, 'NaN'::DOUBLE, TRUE, 4)",
            [-0.0],
        )
        assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) == base
    connection.execute("UPDATE values_test SET list_value = [1.0, NULL, 2.0]")
    ordered = table_content_sha256(connection, "values_test", scratch_dir=tmp_path)
    connection.execute("UPDATE values_test SET list_value = [2.0, NULL, 1.0]")
    assert table_content_sha256(connection, "values_test", scratch_dir=tmp_path) != ordered


def test_unsupported_type_rejected_before_row_scan_and_temp_files_cleaned(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE nested (value STRUCT(x INTEGER))")
    with pytest.raises(ValueError, match="unsupported DuckDB column type"):
        table_content_sha256(connection, "nested", scratch_dir=tmp_path)
    assert not list(tmp_path.glob("antiek-row-digest-*"))
    connection.execute("CREATE TABLE bad (value FLOAT[])")
    connection.execute("INSERT INTO bad VALUES ([1.0])")
    assert len(table_content_sha256(connection, "bad", scratch_dir=tmp_path)) == 64


@pytest.mark.parametrize(
    ("kind", "infinite", "finite"),
    [
        ("DATE", "'infinity'::DATE", "DATE '9999-12-31'"),
        ("DATE", "'-infinity'::DATE", "DATE '0001-01-01'"),
        ("TIMESTAMP", "'infinity'::TIMESTAMP", "TIMESTAMP '9999-12-31 23:59:59.999999'"),
        ("TIMESTAMP", "'-infinity'::TIMESTAMP", "TIMESTAMP '0001-01-01 00:00:00'"),
    ],
)
def test_temporal_infinity_differs_from_finite_python_extreme(
    tmp_path, kind, infinite, finite
) -> None:
    connection = duckdb.connect()
    connection.execute(f"CREATE TABLE time_value (value {kind})")
    connection.execute(f"INSERT INTO time_value VALUES ({infinite})")
    infinite_digest = table_content_sha256(connection, "time_value", scratch_dir=tmp_path)
    connection.execute("DELETE FROM time_value")
    connection.execute(f"INSERT INTO time_value VALUES ({finite})")
    assert table_content_sha256(connection, "time_value", scratch_dir=tmp_path) != infinite_digest


def test_wide_decimal_is_exact_and_changes_digest(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE wide (value DECIMAL(38,0))")
    connection.execute("INSERT INTO wide VALUES (12345678901234567890123456789012345678)")
    original = table_content_sha256(connection, "wide", scratch_dir=tmp_path)
    connection.execute("UPDATE wide SET value = 12345678901234567890123456789012345679")
    assert table_content_sha256(connection, "wide", scratch_dir=tmp_path) != original


def test_fractional_decimal_ignores_ambient_context_precision(tmp_path) -> None:
    connection = duckdb.connect()
    connection.execute("CREATE TABLE fractional (value DECIMAL(38,38))")
    connection.execute(
        "INSERT INTO fractional VALUES ('0.12345678901234567890123456789012345678'::DECIMAL(38,38))"
    )
    original = table_content_sha256(connection, "fractional", scratch_dir=tmp_path)
    with localcontext() as context:
        context.prec = 5
        assert table_content_sha256(connection, "fractional", scratch_dir=tmp_path) == original
    connection.execute(
        "UPDATE fractional SET value = '0.12345678901234567890123456789012345679'::DECIMAL(38,38)"
    )
    assert table_content_sha256(connection, "fractional", scratch_dir=tmp_path) != original


def test_temp_shadow_cannot_replace_persistent_table(tmp_path) -> None:
    connection = duckdb.connect(str(tmp_path / "source.duckdb"))
    connection.execute("CREATE TABLE t (value INTEGER)")
    connection.execute("INSERT INTO source.main.t VALUES (1)")
    original = table_content_sha256(connection, "t", scratch_dir=tmp_path)
    connection.execute("CREATE TEMP TABLE t (value INTEGER)")
    connection.execute("INSERT INTO temp.main.t VALUES (100)")
    assert table_content_sha256(connection, "t", scratch_dir=tmp_path) == original
    connection.execute("UPDATE source.main.t SET value = 2")
    assert table_content_sha256(connection, "t", scratch_dir=tmp_path) != original


def test_attached_same_named_table_does_not_change_digest(tmp_path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    source.execute("CREATE TABLE t (value INTEGER)")
    source.execute("INSERT INTO t VALUES (1)")
    original = table_content_sha256(source, "t", scratch_dir=tmp_path)
    source.execute(f"ATTACH '{tmp_path / 'other.duckdb'}' AS other")
    source.execute("CREATE TABLE other.main.t (value TEXT, extra BOOLEAN)")
    source.execute("INSERT INTO other.main.t VALUES ('other', TRUE)")
    assert table_content_sha256(source, "t", scratch_dir=tmp_path) == original
    restored = duckdb.connect(str(tmp_path / "restored.duckdb"))
    restored.execute("CREATE TABLE t (value INTEGER)")
    restored.execute("INSERT INTO t VALUES (1)")
    assert table_content_sha256(restored, "t", scratch_dir=tmp_path) == original


def test_export_import_preserves_row_digest_across_catalogs(tmp_path) -> None:
    source = duckdb.connect(str(tmp_path / "source.duckdb"))
    source.execute(
        "CREATE TABLE evidence (id INTEGER, event_time TIMESTAMP, amount DECIMAL(38,38), "
        "samples FLOAT[], payload BLOB)"
    )
    source.execute(
        "INSERT INTO evidence VALUES "
        "(1, 'infinity'::TIMESTAMP, "
        "'0.12345678901234567890123456789012345678'::DECIMAL(38,38), "
        "[1.0, NULL, -0.0], '\\x00\\xFF'::BLOB), "
        "(1, 'infinity'::TIMESTAMP, "
        "'0.12345678901234567890123456789012345678'::DECIMAL(38,38), "
        "[1.0, NULL, -0.0], '\\x00\\xFF'::BLOB), "
        "(2, TIMESTAMP '2024-01-02 03:04:05.000006', NULL, [], NULL)"
    )
    original = table_content_sha256(source, "evidence", scratch_dir=tmp_path, chunk_rows=1)
    export_dir = tmp_path / "export"
    source.execute(f"EXPORT DATABASE '{export_dir}' (FORMAT PARQUET)")
    source.close()

    restored = duckdb.connect(str(tmp_path / "restored.duckdb"))
    restored.execute(f"IMPORT DATABASE '{export_dir}'")
    assert restored.execute("SELECT count(*) FROM evidence").fetchone()[0] == 3
    assert (
        table_content_sha256(restored, "evidence", scratch_dir=tmp_path, chunk_rows=2) == original
    )
    restored.execute("UPDATE evidence SET id = 3 WHERE id = 2")
    assert restored.execute("SELECT count(*) FROM evidence").fetchone()[0] == 3
    assert table_content_sha256(restored, "evidence", scratch_dir=tmp_path) != original
