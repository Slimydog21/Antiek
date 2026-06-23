"""Sprint 05: export manifest v1 parity (duckdb_plane §14)."""

from __future__ import annotations

import json
from pathlib import Path

import duckdb

from scripts.export_analytics_parquet import DEFAULT_TABLES, export_tables
from substrate.constants import ANTIEK_PARAM_VERSION


def test_export_manifest_v1_gate(tmp_path: Path) -> None:
    db_path = tmp_path / "parity.duckdb"
    duckdb.connect(str(db_path)).close()

    out_dir = tmp_path / "export"
    manifest = export_tables(str(db_path), out_dir, DEFAULT_TABLES)

    assert manifest["antiek_param_version"] == ANTIEK_PARAM_VERSION
    assert manifest["table_layers"]
    assert "syntheses" in manifest["table_layers"]

    written = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert written["antiek_param_version"] == ANTIEK_PARAM_VERSION
    assert written["table_layers"] == manifest["table_layers"]