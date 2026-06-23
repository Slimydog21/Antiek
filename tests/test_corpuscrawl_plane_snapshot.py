"""Corpuscrawl snapshot for analytics manifest — absent store is honest."""

from __future__ import annotations

from pathlib import Path

from substrate.analytics import corpuscrawl_snapshot as cc_snap


def test_absent_store(tmp_path: Path, monkeypatch) -> None:
    missing = tmp_path / "no-corpus.duckdb"
    monkeypatch.delenv("CORPUSCRAWL_DUCKDB_PATH", raising=False)
    snap = cc_snap.corpuscrawl_plane_snapshot(missing)
    assert snap["status"] == "absent"
    assert snap["layer"] == "discovery_fts"