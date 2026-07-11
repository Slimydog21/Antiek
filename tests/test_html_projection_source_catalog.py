from __future__ import annotations

import hashlib
import json
from pathlib import Path

import duckdb

from substrate.reading.projection.source_catalog import (
    ProjectionSourceCandidate,
    ProjectionSourceCatalog,
    UnresolvedProjectionSource,
    UnresolvedSourceReason,
)


def _database() -> duckdb.DuckDBPyConnection:
    con = duckdb.connect(":memory:")
    con.execute("CREATE TABLE documents(document_id TEXT, document_type TEXT, raw_text TEXT, metadata TEXT)")
    return con


def _asset(data: bytes, key: str = "pdf/source.pdf", **changes: object) -> dict[str, object]:
    value: dict[str, object] = {
        "source_asset_id": "asset-1",
        "object_key": key,
        "sha256": hashlib.sha256(data).hexdigest(),
        "byte_size": len(data),
        "media_type": "application/pdf",
    }
    value.update(changes)
    return value


def _insert(con: duckdb.DuckDBPyConnection, doc: str, kind: str, metadata: object) -> None:
    con.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?)",
        [doc, kind, "%PDF raw text must never become bytes", json.dumps(metadata)],
    )


def test_catalog_is_ordered_read_only_and_does_not_overmatch(tmp_path: Path) -> None:
    data = b"%PDF-1.7\nsource"
    path = tmp_path / "pdf/source.pdf"
    path.parent.mkdir()
    path.write_bytes(data)
    con = _database()
    _insert(con, "z", "PDF", {"html_projection_source": _asset(data)})
    _insert(con, "a", "pdf", {})
    _insert(con, "url", "web", {"source_uri": "https://example.test/file.pdf"})
    _insert(con, "paper", "paper", {"pdf_acquisition": {"sha256": "a" * 64}})
    before = con.execute("SELECT * FROM documents ORDER BY document_id").fetchall()

    result = ProjectionSourceCatalog(con, tmp_path).list()

    assert [item.document_id for item in result] == ["a", "paper", "z"]
    assert isinstance(result[0], UnresolvedProjectionSource)
    assert result[0].reason is UnresolvedSourceReason.MISSING_ASSET_METADATA
    assert isinstance(result[1], UnresolvedProjectionSource)
    assert result[1].reason is UnresolvedSourceReason.MISSING_ASSET_METADATA
    assert isinstance(result[2], ProjectionSourceCandidate)
    assert con.execute("SELECT * FROM documents ORDER BY document_id").fetchall() == before
    assert {row[0] for row in con.execute("SHOW TABLES").fetchall()} == {"documents"}


def test_catalog_closes_all_resolution_failures(tmp_path: Path) -> None:
    data = b"%PDF data"
    good = tmp_path / "good.pdf"
    good.write_bytes(data)
    outside = tmp_path.parent / "outside.pdf"
    outside.write_bytes(data)
    (tmp_path / "escape.pdf").symlink_to(outside)
    con = _database()
    cases = {
        "bad-meta": ({"html_projection_source": []}, "invalid_asset_metadata"),
        "unsafe": ({"html_projection_source": _asset(data, "../outside.pdf")}, "unsafe_object_key"),
        "symlink": ({"html_projection_source": _asset(data, "escape.pdf")}, "unsafe_object_key"),
        "missing": ({"html_projection_source": _asset(data, "absent.pdf")}, "missing_source_bytes"),
        "size": ({"html_projection_source": _asset(data, "good.pdf", byte_size=1)}, "source_size_mismatch"),
        "hash": ({"html_projection_source": _asset(data, "good.pdf", sha256="0" * 64)}, "source_hash_mismatch"),
        "media": ({"html_projection_source": _asset(data, "good.pdf", media_type="text/plain")}, "unsupported_media_type"),
    }
    for document_id, (metadata, _) in cases.items():
        _insert(con, document_id, "pdf", metadata)
    reasons = {
        item.document_id: item.reason_code
        for item in ProjectionSourceCatalog(con, tmp_path).list()
        if isinstance(item, UnresolvedProjectionSource)
    }
    assert reasons == {document_id: expected for document_id, (_, expected) in cases.items()}


def test_catalog_distinguishes_malformed_metadata_from_absent_asset_metadata(
    tmp_path: Path,
) -> None:
    con = _database()
    con.execute(
        "INSERT INTO documents VALUES (?, ?, ?, ?)",
        ["malformed", "pdf", "never source bytes", "{not-json"],
    )
    _insert(con, "missing", "pdf", {})

    records = ProjectionSourceCatalog(con, tmp_path).list()

    assert [(item.document_id, item.reason_code) for item in records] == [
        ("malformed", "invalid_asset_metadata"),
        ("missing", "missing_asset_metadata"),
    ]
