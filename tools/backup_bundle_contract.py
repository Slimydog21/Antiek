"""Reject incompatible DuckDB backup bundles before a destructive restore.

The nightly archive contains ``source_manifest.json`` beside DuckDB's Parquet
export. This check runs on the extracted archive before the recovery runbook
removes the destination DB. It proves compatibility and restorable internal
consistency, not the origin of the downloaded archive.
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from typing import Any

import duckdb

from substrate.graph.schema import (
    ARXIV_BULK_PROGRESS_COLUMNS,
    _v22_arxiv_progress_shape_is_valid,
    load_arxiv_bulk_progress,
)

BUNDLE_CONTRACT_VERSION = 2
_MANIFEST_LIMIT_BYTES = 8 * 1024 * 1024


class BundleCompatibilityError(ValueError):
    """The extracted archive cannot be imported under this code contract."""


def _manifest(root: Path) -> dict[str, Any]:
    path = root / "source_manifest.json"
    try:
        if path.stat().st_size > _MANIFEST_LIMIT_BYTES:
            raise BundleCompatibilityError("source manifest exceeds size limit")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise BundleCompatibilityError("source manifest is missing or unreadable") from exc
    if not isinstance(value, dict):
        raise BundleCompatibilityError("source manifest must be an object")
    return value


def _verify_actual_export(root: Path, manifest: dict[str, Any], *, versioned: bool) -> None:
    """IMPORT into a disposable DB and compare its catalog and data to source.

    Checking a sidecar JSON alone would allow an intact-looking manifest to
    authorize deletion of the destination before a broken export failed.
    """
    export_path = str((root / "duckdb").resolve()).replace("'", "''")
    with tempfile.TemporaryDirectory(prefix="antiek-restore-preflight-") as scratch:
        con = duckdb.connect(str(Path(scratch) / "candidate.duckdb"))
        try:
            try:
                con.execute(f"IMPORT DATABASE '{export_path}'")
            except duckdb.Error as exc:
                raise BundleCompatibilityError("DuckDB export fails scratch IMPORT") from exc

            tables = [
                row[0]
                for row in con.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'main' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name"
                ).fetchall()
            ]
            expected = manifest["counts"]
            if tables != sorted(expected):
                raise BundleCompatibilityError("actual export table inventory differs")

            def quoted(name: str) -> str:
                return '"' + name.replace('"', '""') + '"'

            counts: dict[str, int] = {}
            for table in tables:
                count_row = con.execute(f"SELECT COUNT(*) FROM {quoted(table)}").fetchone()
                if count_row is None:
                    raise BundleCompatibilityError("actual export count query returned no row")
                counts[table] = int(count_row[0])
            if counts != expected:
                raise BundleCompatibilityError("actual export row counts differ")
            catalog = {
                "columns": con.execute(
                    "SELECT table_name, column_name, ordinal_position, column_default, "
                    "is_nullable, data_type FROM information_schema.columns "
                    "WHERE table_schema = 'main' ORDER BY table_name, ordinal_position"
                ).fetchall(),
                "constraints": con.execute(
                    "SELECT table_name, constraint_type, constraint_text, "
                    "constraint_column_names, referenced_table, referenced_column_names "
                    "FROM duckdb_constraints() WHERE schema_name = 'main' "
                    "AND NOT (constraint_type = 'FOREIGN KEY' AND referenced_table = table_name) "
                    "ORDER BY table_name, constraint_type, constraint_text, constraint_column_names"
                ).fetchall(),
                "indexes": con.execute(
                    "SELECT index_name, table_name, is_unique, is_primary, expressions, sql "
                    "FROM duckdb_indexes() WHERE schema_name = 'main' "
                    "ORDER BY table_name, index_name"
                ).fetchall(),
            }
            for name, actual in catalog.items():
                if manifest.get(name) != json.loads(json.dumps(actual)):
                    raise BundleCompatibilityError(f"actual export {name} differ")
            if versioned:
                if not _v22_arxiv_progress_shape_is_valid(con):
                    raise BundleCompatibilityError("actual arXiv cursor schema is incompatible")
                try:
                    load_arxiv_bulk_progress(con)
                except Exception as exc:
                    raise BundleCompatibilityError("actual arXiv cursor row is invalid") from exc
        finally:
            con.close()


def verify_restore_bundle(root: Path, *, allow_legacy: bool = False) -> str:
    """Return the accepted contract label or raise before ``IMPORT DATABASE``.

    An unversioned pre-cursor archive needs an explicit ``allow_legacy`` choice.
    It contains no DB-backed arXiv cursor, so the next sync must bootstrap from
    a verified snapshot rather than trust an external JSON high-water file.
    """
    if not root.is_dir() or not (root / "duckdb" / "schema.sql").is_file() or not (
        root / "duckdb" / "load.sql"
    ).is_file():
        raise BundleCompatibilityError("DuckDB export is incomplete")
    manifest = _manifest(root)
    counts = manifest.get("counts")
    columns = manifest.get("columns")
    if not isinstance(counts, dict) or not isinstance(columns, list):
        raise BundleCompatibilityError("source manifest lacks table inventory")
    version = manifest.get("bundle_contract_version")
    if version is None:
        if "arxiv_bulk_progress" in counts or any(
            isinstance(row, list) and row and row[0] == "arxiv_bulk_progress"
            for row in columns
        ):
            raise BundleCompatibilityError("unversioned bundle contains a cursor table")
        if not allow_legacy:
            raise BundleCompatibilityError(
                "unversioned legacy bundle requires --allow-legacy after review"
            )
        _verify_actual_export(root, manifest, versioned=False)
        return "legacy-unversioned"
    if type(version) is not int or version != BUNDLE_CONTRACT_VERSION:
        raise BundleCompatibilityError(f"unsupported bundle contract version: {version!r}")
    if type(counts.get("arxiv_bulk_progress")) is not int or counts[
        "arxiv_bulk_progress"
    ] < 0:
        raise BundleCompatibilityError("versioned bundle lacks arXiv progress table")

    actual: list[tuple[int, str]] = []
    for row in columns:
        if not isinstance(row, list) or len(row) != 6:
            raise BundleCompatibilityError("source manifest has malformed column inventory")
        if row[0] == "arxiv_bulk_progress":
            if type(row[2]) is not int:
                raise BundleCompatibilityError("arXiv progress column order is malformed")
            actual.append((row[2], row[1]))
    expected = [(index, name) for index, name in enumerate(ARXIV_BULK_PROGRESS_COLUMNS, 1)]
    if actual != expected:
        raise BundleCompatibilityError("arXiv progress column contract is incompatible")
    _verify_actual_export(root, manifest, versioned=True)
    return f"v{BUNDLE_CONTRACT_VERSION}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("restore_dir", type=Path, help="extracted backup root")
    parser.add_argument(
        "--allow-legacy", action="store_true", help="accept an unversioned pre-cursor bundle"
    )
    args = parser.parse_args(argv)
    try:
        contract = verify_restore_bundle(args.restore_dir, allow_legacy=args.allow_legacy)
    except BundleCompatibilityError as exc:
        parser.exit(2, f"ABORT: backup compatibility: {exc}\n")
    print(f"backup compatibility: {contract}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
