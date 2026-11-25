"""Versioned row-content proof for a table in a caller-owned DuckDB snapshot.

The caller owns the connection, transaction, and any write lock. In particular,
this module does not establish the provenance of a production backup by itself.
"""

from __future__ import annotations

import hashlib
import heapq
import math
import re
import struct
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast

CONTENT_SCHEME = "antiek-row-multiset-sha256-v1"
_DIGEST_SIZE = 32
_DECIMAL = re.compile(r"DECIMAL\((\d+),\s*(\d+)\)")
_SCALAR_TYPES = {
    "TEXT",
    "VARCHAR",
    "INTEGER",
    "BIGINT",
    "FLOAT",
    "DOUBLE",
    "BOOLEAN",
    "TIMESTAMP",
    "DATE",
    "BLOB",
}
_MAX_MERGE_FILES = 32


class _Cursor(Protocol):
    def fetchone(self) -> tuple[Any, ...] | None: ...

    def fetchall(self) -> list[tuple[Any, ...]]: ...

    def fetchmany(self, size: int) -> list[tuple[Any, ...]]: ...


class _Connection(Protocol):
    def execute(self, query: str, parameters: object = ...) -> _Cursor: ...


def _field(tag: bytes, payload: bytes) -> bytes:
    return tag + struct.pack(">Q", len(payload)) + payload


def _identifier(value: str) -> str:
    if not value or "\x00" in value:
        raise ValueError("invalid SQL identifier")
    return '"' + value.replace('"', '""') + '"'


def _column_type(data_type: str) -> str:
    kind = data_type.upper().strip()
    if kind in _SCALAR_TYPES or kind == "FLOAT[]" or _DECIMAL.fullmatch(kind):
        return kind
    raise ValueError(f"unsupported DuckDB column type: {data_type}")


def _value(value: object, kind: str) -> bytes:
    if value is None:
        return _field(b"N", b"")
    if kind in {"TEXT", "VARCHAR"}:
        return _field(b"S", cast(str, value).encode("utf-8"))
    if kind in {"INTEGER", "BIGINT"}:
        return _field(b"I", str(value).encode("ascii"))
    if kind in {"FLOAT", "DOUBLE"}:
        number = float(cast(Any, value))
        if math.isnan(number):
            return _field(b"F", b"nan")
        if math.isinf(number):
            return _field(b"F", b"+inf" if number > 0 else b"-inf")
        return _field(b"F", struct.pack(">f" if kind == "FLOAT" else ">d", number))
    if kind == "FLOAT[]":
        return _field(
            b"L",
            b"".join(_field(b"E", _value(item, "FLOAT")) for item in cast(Any, value)),
        )
    if kind == "BOOLEAN":
        return _field(b"B", b"1" if value else b"0")
    if kind == "TIMESTAMP":
        if not isinstance(value, str):
            raise ValueError("TIMESTAMP must come from DuckDB VARCHAR projection")
        return _field(b"T", value.encode("ascii"))
    if kind == "DATE":
        if not isinstance(value, str):
            raise ValueError("DATE must come from DuckDB VARCHAR projection")
        return _field(b"D", value.encode("ascii"))
    if kind == "BLOB":
        return _field(b"X", bytes(cast(Any, value)))
    match = _DECIMAL.fullmatch(kind)
    if match:
        scale = int(match.group(2))
        decimal_value = Decimal(cast(Any, value))
        if not decimal_value.is_finite():
            raise ValueError("invalid DECIMAL value for declared scale")
        sign, digits, exponent = decimal_value.as_tuple()
        coefficient = int("".join(map(str, digits)))
        places = cast(int, exponent) + scale
        if places >= 0:
            coefficient *= 10**places
        else:
            divisor = 10**-places
            if coefficient % divisor:
                raise ValueError("invalid DECIMAL value for declared scale")
            coefficient //= divisor
        if sign:
            coefficient = -coefficient
        return _field(b"M", f"{scale}:{coefficient}".encode("ascii"))
    raise ValueError(f"unsupported DuckDB column type: {kind}")


def _read_digest(stream: BinaryIO) -> bytes | None:
    value = stream.read(_DIGEST_SIZE)
    if not value:
        return None
    if len(value) != _DIGEST_SIZE:
        raise ValueError("truncated digest run")
    return value


def _merge_runs(paths: list[Path], output: Path) -> None:
    with output.open("wb") as destination:
        streams = [path.open("rb") for path in paths]
        try:
            heap: list[tuple[bytes, int]] = []
            for index, stream in enumerate(streams):
                item = _read_digest(stream)
                if item is not None:
                    heapq.heappush(heap, (item, index))
            while heap:
                item, index = heapq.heappop(heap)
                destination.write(item)
                following = _read_digest(streams[index])
                if following is not None:
                    heapq.heappush(heap, (following, index))
        finally:
            for stream in streams:
                stream.close()


def table_content_sha256(
    connection: _Connection,
    table_name: str,
    *,
    catalog_name: str | None = None,
    schema_name: str = "main",
    scratch_dir: str | Path | None = None,
    chunk_rows: int = 8192,
) -> str:
    """Hash a table's schema and row multiset within the caller's snapshot.

    The default catalog is DuckDB's current database. The physical catalog
    name selects a table but is excluded from the digest, so a restored
    database can have a different filename. At most ``chunk_rows`` row digests
    and 32 input runs are held at once.
    A private temporary directory holds sorted runs and is removed on success
    or failure. ``scratch_dir`` must be trusted storage with enough free space.
    """
    if chunk_rows < 1:
        raise ValueError("chunk_rows must be positive")
    if catalog_name is None:
        catalog_name = cast(
            str, cast(Any, connection.execute("SELECT current_database()").fetchone())[0]
        )
    _identifier(catalog_name)
    _identifier(schema_name)
    _identifier(table_name)
    columns = connection.execute(
        "SELECT column_name, data_type FROM information_schema.columns "
        "WHERE table_catalog = ? AND table_schema = ? AND table_name = ? "
        "ORDER BY ordinal_position",
        [catalog_name, schema_name, table_name],
    ).fetchall()
    if not columns:
        raise ValueError(f"table has no columns or does not exist: {schema_name}.{table_name}")
    typed_columns = [(name, _column_type(data_type)) for name, data_type in columns]
    digest = hashlib.sha256()
    digest.update(_field(b"V", CONTENT_SCHEME.encode("ascii")))
    digest.update(_field(b"S", schema_name.encode("utf-8")))
    digest.update(_field(b"T", table_name.encode("utf-8")))
    for name, kind in typed_columns:
        digest.update(
            _field(b"C", _field(b"N", name.encode("utf-8")) + _field(b"Y", kind.encode("ascii")))
        )

    # Python's DuckDB adapter maps temporal infinities to finite datetime
    # extrema. CAST to VARCHAR inside DuckDB preserves their distinct values.
    projection = ", ".join(
        f"CAST({_identifier(name)} AS VARCHAR)"
        if kind in {"DATE", "TIMESTAMP"}
        else _identifier(name)
        for name, kind in typed_columns
    )
    query = (
        f"SELECT {projection} FROM "
        f"{_identifier(catalog_name)}.{_identifier(schema_name)}.{_identifier(table_name)}"
    )
    with tempfile.TemporaryDirectory(prefix="antiek-row-digest-", dir=scratch_dir) as temporary:
        directory = Path(temporary)
        runs: list[Path] = []
        cursor = connection.execute(query)
        while rows := cursor.fetchmany(chunk_rows):
            row_hashes = []
            for row in rows:
                payload = b"".join(
                    _field(b"C", _field(b"Y", kind.encode("ascii")) + _value(value, kind))
                    for value, (_, kind) in zip(row, typed_columns, strict=True)
                )
                row_hashes.append(hashlib.sha256(_field(b"R", payload)).digest())
            run = directory / f"run-{len(runs)}"
            run.write_bytes(b"".join(sorted(row_hashes)))
            runs.append(run)

        pass_number = 0
        while len(runs) > 1:
            merged: list[Path] = []
            for offset in range(0, len(runs), _MAX_MERGE_FILES):
                group = runs[offset : offset + _MAX_MERGE_FILES]
                destination = directory / f"merge-{pass_number}-{len(merged)}"
                _merge_runs(group, destination)
                merged.append(destination)
                for path in group:
                    path.unlink()
            runs = merged
            pass_number += 1
        if runs:
            with runs[0].open("rb") as stream:
                while block := stream.read(1024 * _DIGEST_SIZE):
                    digest.update(block)
    return digest.hexdigest()
