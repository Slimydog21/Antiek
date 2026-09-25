"""Observe a DuckDB snapshot and verify its closed-archive restore.

The caller owns source provenance, the transaction, the closed archive inode,
and the sandbox. This module does not establish any of those facts.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
import shutil
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import duckdb

from tools.deploy.backup_archive_admission import (
    AdmissionReport,
    ArchiveAdmissionError,
    ArchiveLimits,
    admit_archive,
)
from tools.deploy.backup_content_digest import CONTENT_SCHEME, table_content_sha256

CATALOG_SCHEME = "antiek-duckdb-catalog-v1"
OBSERVATION_SCHEME = "antiek-source-observation-v1"
REPORT_SCHEME = "antiek-closed-archive-restore-v1"
_DUCKDB_VERSION = "1.5.4"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
_ARCHIVE_ROOT = re.compile(r"antiek-backup\.[A-Za-z0-9]{8}\Z")
_DATA_MEMBER = re.compile(r"[A-Za-z0-9_]+\.parquet\Z")
_SEQUENCE_SQL = re.compile(
    r'CREATE SEQUENCE (?:"(?:[^"]|"")+"|[A-Za-z_][A-Za-z_0-9]*) '
    r"INCREMENT BY (-?\d+) MINVALUE (-?\d+) MAXVALUE (-?\d+) "
    r"START (-?\d+) (NO CYCLE|CYCLE);\Z"
)
_PLAIN_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*\Z")
_ADMISSION_ERRORS = (ArchiveAdmissionError, OSError)
_IMPORT_ERRORS = (duckdb.Error, OSError, ValueError)
_JsonObject = dict[str, Any]


class RestoreRefused(ValueError):
    """Fixed-code refusal; callers must not expose DuckDB error text."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class ObservationLimits:
    source_report_bytes: int = 2_000_000
    tables: int = 256
    catalog_objects: int = 20_000
    identifier_bytes: int = 512
    definition_bytes: int = 65_536
    report_bytes: int = 2_000_000


@dataclass(frozen=True)
class RestoreLimits:
    observation: ObservationLimits
    archive: ArchiveLimits

    @classmethod
    def production(cls) -> RestoreLimits:
        return cls(ObservationLimits(), ArchiveLimits())


@dataclass(frozen=True)
class TableObservation:
    row_count: int
    content_sha256: str


@dataclass(frozen=True)
class SnapshotObservation:
    observation_scheme: str
    catalog_scheme: str
    content_scheme: str
    duckdb_version: str
    catalog_objects: tuple[_JsonObject, ...]
    tables: Mapping[str, TableObservation]

    def canonical_bytes(self) -> bytes:
        payload = {
            "observation_scheme": self.observation_scheme,
            "catalog_scheme": self.catalog_scheme,
            "content_scheme": self.content_scheme,
            "duckdb_version": self.duckdb_version,
            "catalog_objects": list(self.catalog_objects),
            "tables": {name: vars(value) for name, value in self.tables.items()},
        }
        return json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")

    @classmethod
    def from_canonical_bytes(cls, raw: bytes, *, limits: ObservationLimits) -> SnapshotObservation:
        if not isinstance(raw, bytes) or len(raw) > limits.source_report_bytes:
            raise RestoreRefused("SOURCE_REPORT_SIZE")

        def unique_pairs(pairs: list[tuple[str, Any]]) -> _JsonObject:
            result: _JsonObject = {}
            for key, value in pairs:
                if key in result:
                    raise RestoreRefused("SOURCE_REPORT_FORMAT")
                result[key] = value
            return result

        try:
            value = json.loads(
                raw.decode("utf-8"),
                object_pairs_hook=unique_pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
            )
            if type(value) is not dict or set(value) != {
                "observation_scheme",
                "catalog_scheme",
                "content_scheme",
                "duckdb_version",
                "catalog_objects",
                "tables",
            }:
                raise ValueError()
            if (
                value["observation_scheme"] != OBSERVATION_SCHEME
                or value["catalog_scheme"] != CATALOG_SCHEME
                or value["content_scheme"] != CONTENT_SCHEME
                or value["duckdb_version"] != _DUCKDB_VERSION
            ):
                raise RestoreRefused("SOURCE_REPORT_SCHEME")
            objects = value["catalog_objects"]
            tables = value["tables"]
            if (
                type(objects) is not list
                or type(tables) is not dict
                or len(objects) > limits.catalog_objects
                or len(tables) > limits.tables
            ):
                raise ValueError()
            if any(type(o) is not dict or not _valid_object(o, limits) for o in objects):
                raise ValueError()
            if objects != sorted(objects, key=_object_key) or len(
                {_object_key(o) for o in objects}
            ) != len(objects):
                raise ValueError()
            parsed_tables = {}
            for name, entry in tables.items():
                _bounded_name(name, limits)
                if (
                    type(entry) is not dict
                    or set(entry) != {"row_count", "content_sha256"}
                    or type(entry["row_count"]) is not int
                    or entry["row_count"] < 0
                    or type(entry["content_sha256"]) is not str
                    or not _SHA256.fullmatch(entry["content_sha256"])
                ):
                    raise ValueError()
                parsed_tables[name] = TableObservation(**entry)
            if set(parsed_tables) != {
                f"{o['schema']}.{o['name']}" for o in objects if o["kind"] == "table"
            }:
                raise ValueError()
            result = cls(
                OBSERVATION_SCHEME,
                CATALOG_SCHEME,
                CONTENT_SCHEME,
                _DUCKDB_VERSION,
                tuple(objects),
                parsed_tables,
            )
            if result.canonical_bytes() != raw:
                raise ValueError()
            return result
        except RestoreRefused:
            raise
        except (
            ValueError,
            TypeError,
            UnicodeError,
            KeyError,
            OverflowError,
            RecursionError,
        ) as exc:
            raise RestoreRefused("SOURCE_REPORT_FORMAT") from exc


@dataclass(frozen=True)
class RestoreReport:
    report_scheme: str
    archive_sha256: str
    archive_bytes: int
    source_observation_sha256: str
    restored_observation_sha256: str
    source_counts: Mapping[str, int]
    restored_counts: Mapping[str, int]
    source_catalog_sha256: str
    restored_catalog_sha256: str
    source_content_sha256: Mapping[str, str]
    restored_content_sha256: Mapping[str, str]
    content_scheme: str
    duckdb_version: str

    def canonical_bytes(self) -> bytes:
        return json.dumps(vars(self), sort_keys=True, separators=(",", ":")).encode("ascii")

    @classmethod
    def from_canonical_bytes(cls, raw: bytes, *, limits: RestoreLimits) -> RestoreReport:
        if not isinstance(raw, bytes) or len(raw) > limits.observation.report_bytes:
            raise RestoreRefused("REPORT_FORMAT")

        def unique_pairs(pairs: list[tuple[str, Any]]) -> _JsonObject:
            value: _JsonObject = {}
            for key, item in pairs:
                if key in value:
                    raise ValueError()
                value[key] = item
            return value

        try:
            value = json.loads(raw.decode("ascii"), object_pairs_hook=unique_pairs)
            if type(value) is not dict or set(value) != set(cls.__dataclass_fields__):
                raise ValueError()
            if (
                value["report_scheme"] != REPORT_SCHEME
                or value["content_scheme"] != CONTENT_SCHEME
                or value["duckdb_version"] != _DUCKDB_VERSION
                or any(
                    type(value[field]) is not str or not _SHA256.fullmatch(value[field])
                    for field in (
                        "archive_sha256",
                        "source_observation_sha256",
                        "restored_observation_sha256",
                        "source_catalog_sha256",
                        "restored_catalog_sha256",
                    )
                )
                or type(value["archive_bytes"]) is not int
                or not 0 < value["archive_bytes"] <= limits.archive.compressed_bytes
            ):
                raise ValueError()
            for field in (
                "source_counts",
                "restored_counts",
                "source_content_sha256",
                "restored_content_sha256",
            ):
                if type(value[field]) is not dict or len(value[field]) > limits.observation.tables:
                    raise ValueError()
                for name, item in value[field].items():
                    _bounded_name(name, limits.observation)
                    if field.endswith("counts"):
                        if type(item) is not int or item < 0:
                            raise ValueError()
                    elif type(item) is not str or not _SHA256.fullmatch(item):
                        raise ValueError()
            if (
                value["source_observation_sha256"] != value["restored_observation_sha256"]
                or value["source_catalog_sha256"] != value["restored_catalog_sha256"]
                or value["source_counts"] != value["restored_counts"]
                or value["source_content_sha256"] != value["restored_content_sha256"]
                or set(value["source_counts"]) != set(value["source_content_sha256"])
            ):
                raise ValueError()
            report = cls(**value)
            if report.canonical_bytes() != raw:
                raise ValueError()
            return report
        except (ValueError, TypeError, UnicodeError, KeyError, RecursionError) as exc:
            raise RestoreRefused("REPORT_FORMAT") from exc


def _bounded_name(value: object, limits: ObservationLimits) -> None:
    if (
        type(value) is not str
        or not value
        or "\x00" in value
        or len(value.encode("utf-8")) > limits.identifier_bytes
    ):
        raise ValueError("identifier")


def _bounded_text(value: object, limits: ObservationLimits) -> None:
    if type(value) is not str or len(value.encode("utf-8")) > limits.definition_bytes:
        raise ValueError("definition")


def _object_key(obj: _JsonObject) -> tuple[str, str, str, str, int]:
    return obj["kind"], obj["schema"], obj.get("table", ""), obj["name"], obj.get("ordinal", 0)


_FIELDS = {
    "schema": {"kind", "schema", "name"},
    "table": {"kind", "schema", "name"},
    "column": {"kind", "schema", "name", "table", "ordinal", "type", "nullable", "default"},
    "constraint": {
        "kind",
        "schema",
        "name",
        "table",
        "type",
        "columns",
        "expression",
        "referenced_table",
        "referenced_columns",
    },
    "index": {"kind", "schema", "name", "table", "columns", "unique", "sql"},
    "sequence": {
        "kind",
        "schema",
        "name",
        "increment",
        "minimum",
        "maximum",
        "next_value",
        "cycle",
    },
}


def _valid_object(obj: _JsonObject, limits: ObservationLimits) -> bool:
    kind = obj.get("kind")
    if type(kind) is not str or kind not in _FIELDS or set(obj) != _FIELDS[kind]:
        return False
    for field in ("schema", "name"):
        _bounded_name(obj[field], limits)
    if "." in obj["schema"] or (kind == "table" and "." in obj["name"]):
        return False
    if kind in {"column", "constraint", "index"}:
        _bounded_name(obj["table"], limits)
        if "." in obj["table"]:
            return False
    if kind == "column" and (type(obj["ordinal"]) is not int or obj["ordinal"] < 0):
        return False
    if kind == "column":
        _bounded_text(obj["type"], limits)
        if type(obj["nullable"]) is not bool or (
            obj["default"] is not None and type(obj["default"]) is not str
        ):
            return False
        if obj["default"] is not None:
            _bounded_text(obj["default"], limits)
    if kind in {"constraint", "index"}:
        if type(obj["columns"]) is not list or not obj["columns"]:
            return False
        for name in obj["columns"]:
            _bounded_name(name, limits)
    if kind == "constraint":
        if obj["type"] not in {"PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK", "NOT NULL"}:
            return False
        if obj["expression"] is not None:
            _bounded_text(obj["expression"], limits)
        if obj["referenced_table"] is not None:
            _bounded_name(obj["referenced_table"], limits)
        if type(obj["referenced_columns"]) is not list:
            return False
        for name in obj["referenced_columns"]:
            _bounded_name(name, limits)
        if (obj["type"] == "FOREIGN KEY") != (
            obj["referenced_table"] is not None and bool(obj["referenced_columns"])
        ):
            return False
    if kind == "index":
        if type(obj["unique"]) is not bool:
            return False
        _bounded_text(obj["sql"], limits)
    if kind == "sequence":
        if any(
            type(obj[field]) is not int
            for field in ("increment", "minimum", "maximum", "next_value")
        ):
            return False
        if type(obj["cycle"]) is not bool or obj["increment"] == 0:
            return False
    return True


def _rows(connection: duckdb.DuckDBPyConnection, function: str, cap: int) -> list[_JsonObject]:
    cursor = connection.execute(f"SELECT * FROM system.main.{function}()")
    names = [item[0] for item in cursor.description]
    rows = cursor.fetchmany(cap + 1)
    if len(rows) > cap:
        raise RestoreRefused("OBSERVATION_SIZE")
    return [dict(zip(names, row, strict=True)) for row in rows]


def _identifier(value: str) -> str:
    return '"' + value.replace('"', '""') + '"'


def observe_snapshot(
    connection: duckdb.DuckDBPyConnection, *, scratch_parent: Path, limits: ObservationLimits
) -> SnapshotObservation:
    """Inventory all supported persistent objects and hash every base table.

    The caller must hold a stable DuckDB transaction. Unknown catalog objects
    or properties refuse observation; they never disappear from the report.
    """
    try:
        version_row = connection.execute("SELECT system.main.version()").fetchone()
        if version_row is None or version_row[0] != f"v{_DUCKDB_VERSION}":
            raise RestoreRefused("DUCKDB_VERSION")
        catalog_row = connection.execute("SELECT system.main.current_database()").fetchone()
        if catalog_row is None or type(catalog_row[0]) is not str:
            raise RestoreRefused("CATALOG_UNSUPPORTED")
        catalog: str = catalog_row[0]
        databases = [
            r
            for r in _rows(connection, "duckdb_databases", limits.catalog_objects)
            if not r["internal"]
        ]
        if len(databases) != 1 or databases[0]["database_name"] != catalog:
            raise RestoreRefused("CATALOG_UNSUPPORTED")
        objects = []

        def admitted(function: str) -> list[_JsonObject]:
            rows = _rows(connection, function, limits.catalog_objects)
            if any(r["database_name"] != catalog and not r.get("internal", False) for r in rows):
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            return [
                r for r in rows if r["database_name"] == catalog and not r.get("internal", False)
            ]

        for row in admitted("duckdb_schemas"):
            if row["schema_name"] == "main":
                continue
            if row["comment"] is not None or row["tags"] or not row["sql"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(dict(kind="schema", schema=row["schema_name"], name=row["schema_name"]))
        tables = admitted("duckdb_tables")
        if len(tables) > limits.tables:
            raise RestoreRefused("OBSERVATION_SIZE")
        for row in tables:
            if row["temporary"] or row["comment"] is not None or row["tags"] or not row["sql"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            if "." in row["schema_name"] or "." in row["table_name"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            if re.search(r"\bGENERATED\s+ALWAYS\s+AS\b", row["sql"], re.IGNORECASE):
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            if re.search(r"\bCOLLATE\b", row["sql"], re.IGNORECASE):
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(dict(kind="table", schema=row["schema_name"], name=row["table_name"]))
        table_keys = {(r["schema_name"], r["table_name"]) for r in tables}
        for row in admitted("duckdb_columns"):
            if (row["schema_name"], row["table_name"]) not in table_keys:
                continue
            if row["comment"] is not None:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(
                dict(
                    kind="column",
                    schema=row["schema_name"],
                    name=row["column_name"],
                    table=row["table_name"],
                    ordinal=row["column_index"],
                    type=row["data_type"],
                    nullable=row["is_nullable"],
                    default=row["column_default"],
                )
            )
        for row in admitted("duckdb_constraints"):
            if (row["schema_name"], row["table_name"]) not in table_keys:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            kind = row["constraint_type"]
            if kind not in {"PRIMARY KEY", "UNIQUE", "FOREIGN KEY", "CHECK", "NOT NULL"}:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(
                dict(
                    kind="constraint",
                    schema=row["schema_name"],
                    name=row["constraint_name"],
                    table=row["table_name"],
                    type=kind,
                    columns=row["constraint_column_names"],
                    expression=row["expression"],
                    referenced_table=row["referenced_table"],
                    referenced_columns=row["referenced_column_names"],
                )
            )
        for row in admitted("duckdb_indexes"):
            if (row["schema_name"], row["table_name"]) not in table_keys or row["is_primary"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            if row["comment"] is not None or row["tags"] or not row["sql"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            expression = row["expressions"]
            if re.fullmatch(r"\[[A-Za-z_][A-Za-z_0-9]*(?:, [A-Za-z_][A-Za-z_0-9]*)*\]", expression):
                parts = expression[1:-1].split(", ")
            else:
                try:
                    parts = ast.literal_eval(expression)
                except (ValueError, SyntaxError, TypeError) as exc:
                    raise RestoreRefused("CATALOG_UNSUPPORTED") from exc
            if type(parts) is not list or not parts or any(type(p) is not str for p in parts):
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            columns = []
            for part in parts:
                if _PLAIN_IDENTIFIER.fullmatch(part):
                    columns.append(part)
                elif part.startswith('"') and part.endswith('"') and len(part) > 2:
                    columns.append(part[1:-1].replace('""', '"'))
                else:
                    raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(
                dict(
                    kind="index",
                    schema=row["schema_name"],
                    name=row["index_name"],
                    table=row["table_name"],
                    columns=columns,
                    unique=row["is_unique"],
                    sql=row["sql"],
                )
            )
        for row in admitted("duckdb_sequences"):
            if row["temporary"] or row["comment"] is not None or row["tags"]:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            match = _SEQUENCE_SQL.fullmatch(row["sql"] or "")
            if (
                not match
                or tuple(map(int, match.groups()[:3]))
                != (row["increment_by"], row["min_value"], row["max_value"])
                or (match.group(5) == "CYCLE") != row["cycle"]
            ):
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            objects.append(
                dict(
                    kind="sequence",
                    schema=row["schema_name"],
                    name=row["sequence_name"],
                    increment=row["increment_by"],
                    minimum=row["min_value"],
                    maximum=row["max_value"],
                    next_value=int(match.group(4)),
                    cycle=row["cycle"],
                )
            )
        if admitted("duckdb_views") or admitted("duckdb_types") or admitted("duckdb_functions"):
            raise RestoreRefused("CATALOG_UNSUPPORTED")
        if len(objects) > limits.catalog_objects or any(
            not _valid_object(o, limits) for o in objects
        ):
            raise RestoreRefused("OBSERVATION_SIZE")
        objects.sort(key=_object_key)
        if len({_object_key(o) for o in objects}) != len(objects):
            raise RestoreRefused("CATALOG_UNSUPPORTED")
        observations = {}
        for schema, name in sorted(table_keys):
            key = f"{schema}.{name}"
            _bounded_name(key, limits)
            count_row = connection.execute(
                f"SELECT count(*) FROM {_identifier(catalog)}.{_identifier(schema)}.{_identifier(name)}"
            ).fetchone()
            if count_row is None or type(count_row[0]) is not int or count_row[0] < 0:
                raise RestoreRefused("CATALOG_UNSUPPORTED")
            count: int = count_row[0]
            digest = table_content_sha256(
                connection,
                name,
                catalog_name=catalog,
                schema_name=schema,
                scratch_dir=scratch_parent,
            )
            observations[key] = TableObservation(count, digest)
        result = SnapshotObservation(
            OBSERVATION_SCHEME,
            CATALOG_SCHEME,
            CONTENT_SCHEME,
            _DUCKDB_VERSION,
            tuple(objects),
            observations,
        )
        if len(result.canonical_bytes()) > limits.report_bytes:
            raise RestoreRefused("OBSERVATION_SIZE")
        return result
    except RestoreRefused:
        raise
    except (ValueError, TypeError, KeyError) as exc:
        raise RestoreRefused("CATALOG_UNSUPPORTED") from exc


def _admitted_export(report: AdmissionReport, destination: Path, table_count: int) -> Path:
    members = report.members
    if not members:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    roots = {member.path.split("/", 1)[0] for member in members}
    if len(roots) != 1:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    root = roots.pop()
    if not _ARCHIVE_ROOT.fullmatch(root):
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    directories = {member.path for member in members if member.sha256 is None}
    files = {member.path for member in members if member.sha256 is not None}
    if root not in directories or f"{root}/duckdb" not in directories:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    required = {f"{root}/duckdb/schema.sql", f"{root}/duckdb/load.sql"}
    if not required <= files:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    data = []
    for path in files:
        if path in required or path == f"{root}/source_manifest.json":
            continue
        if path.startswith(f"{root}/research_events/") or path.startswith(
            f"{root}/knowledge_skills/"
        ):
            continue
        prefix = f"{root}/duckdb/"
        if not path.startswith(prefix) or not _DATA_MEMBER.fullmatch(path[len(prefix) :]):
            raise RestoreRefused("EXPORT_LAYOUT_INVALID")
        data.append(path)
    if len(data) != table_count:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    for path in directories:
        if path in {root, f"{root}/duckdb"}:
            continue
        if path in {f"{root}/research_events", f"{root}/knowledge_skills"}:
            continue
        if path.startswith(f"{root}/research_events/") or path.startswith(
            f"{root}/knowledge_skills/"
        ):
            continue
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    return destination / root / "duckdb"


def _catalog_digest(observation: SnapshotObservation) -> str:
    payload = {
        "catalog_scheme": observation.catalog_scheme,
        "duckdb_version": observation.duckdb_version,
        "catalog_objects": observation.catalog_objects,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _sql_literal(path: Path) -> str:
    value = str(path)
    if "\x00" in value:
        raise RestoreRefused("EXPORT_LAYOUT_INVALID")
    return "'" + value.replace("'", "''") + "'"


def verify_closed_archive(
    *,
    archive: Path,
    source_report_bytes: bytes,
    scratch_parent: Path,
    limits: RestoreLimits,
) -> RestoreReport:
    """Verify DuckDB data in one closed archive inside a non-root OS sandbox.

    The caller authenticates source bytes and binds the frozen archive inode.
    It also confines DuckDB IMPORT, archive parsing, and worker resources.
    Other admitted archive members are hash-bound, not semantically verified.
    """
    try:
        expected = SnapshotObservation.from_canonical_bytes(
            source_report_bytes, limits=limits.observation
        )
    except RestoreRefused as exc:
        raise RestoreRefused(exc.code) from None
    try:
        scratch = Path(tempfile.mkdtemp(prefix="antiek-restore-", dir=scratch_parent))
    except OSError:
        raise RestoreRefused("SCRATCH_FAILED") from None
    try:
        scratch.chmod(0o700)
        admitted = scratch / "admitted"
        admitted.mkdir(mode=0o700)
        admitted.chmod(0o700)
        try:
            admission = admit_archive(archive, admitted, limits=limits.archive)
        except _ADMISSION_ERRORS:
            raise RestoreRefused("ARCHIVE_ADMISSION_FAILED") from None
        export = _admitted_export(admission, admitted, len(expected.tables))
        restored_path = scratch / "restored.duckdb"
        try:
            connection = duckdb.connect(str(restored_path))
            try:
                connection.execute(f"IMPORT DATABASE {_sql_literal(export)}")
                connection.execute("BEGIN TRANSACTION")
                try:
                    actual = observe_snapshot(
                        connection, scratch_parent=scratch, limits=limits.observation
                    )
                finally:
                    connection.execute("ROLLBACK")
            finally:
                connection.close()
        except RestoreRefused as exc:
            raise RestoreRefused(exc.code) from None
        except _IMPORT_ERRORS:
            raise RestoreRefused("IMPORT_OR_OBSERVATION_FAILED") from None
        if set(actual.tables) != set(expected.tables):
            raise RestoreRefused("TABLE_SET_MISMATCH")
        if actual.catalog_objects != expected.catalog_objects:
            raise RestoreRefused("CATALOG_MISMATCH")
        if any(
            actual.tables[name].row_count != expected.tables[name].row_count
            for name in expected.tables
        ):
            raise RestoreRefused("COUNT_MISMATCH")
        if any(
            actual.tables[name].content_sha256 != expected.tables[name].content_sha256
            for name in expected.tables
        ):
            raise RestoreRefused("CONTENT_MISMATCH")
        source_digest = hashlib.sha256(source_report_bytes).hexdigest()
        restored_digest = hashlib.sha256(actual.canonical_bytes()).hexdigest()
        if source_digest != restored_digest:
            raise RestoreRefused("OBSERVATION_MISMATCH")
        report = RestoreReport(
            report_scheme=REPORT_SCHEME,
            archive_sha256=admission.archive_sha256,
            archive_bytes=admission.compressed_bytes,
            source_observation_sha256=source_digest,
            restored_observation_sha256=restored_digest,
            source_counts={name: item.row_count for name, item in expected.tables.items()},
            restored_counts={name: item.row_count for name, item in actual.tables.items()},
            source_catalog_sha256=_catalog_digest(expected),
            restored_catalog_sha256=_catalog_digest(actual),
            source_content_sha256={
                name: item.content_sha256 for name, item in expected.tables.items()
            },
            restored_content_sha256={
                name: item.content_sha256 for name, item in actual.tables.items()
            },
            content_scheme=CONTENT_SCHEME,
            duckdb_version=_DUCKDB_VERSION,
        )
        if len(report.canonical_bytes()) > limits.observation.report_bytes:
            raise RestoreRefused("REPORT_SIZE")
        return report
    except OSError:
        raise RestoreRefused("SCRATCH_FAILED") from None
    finally:
        try:
            shutil.rmtree(scratch)
        except OSError:
            raise RestoreRefused("CLEANUP_FAILED") from None
