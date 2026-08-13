"""P1 §6 — ``GET /export/my-graph`` (full-graph export bundle, read half).

Builds a temp DuckDB (real Antiek schema + rows), a temp events dir (one
sealed parquet written via DuckDB COPY + one live jsonl through the
substrate event log), and a temp home, then asserts:

- 200 + ``application/zip`` content type + attachment filename
- the zip carries ``graph/`` + ``events/`` + ``manifest.json``
- manifest counts match reality (tables, table_rows, event files, master 0)
- the exported ``graph/schema.sql`` is normalized (no self-ref-FK stray
  commas) and the events parquet round-trips
- the source DB file checksum is UNCHANGED (export never mutates the graph)
- the temp bundle dir is cleaned up after streaming (no leftover dirs)
- 503 (value-free body) when the db path is invalid (empty home)
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import tempfile
import zipfile

import duckdb
from fastapi.testclient import TestClient

from interfaces.research.api import export_routes
from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.event_log import default_events_dir, log_event
from substrate.graph.schema import init_database_at_path


def _sha256(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False, register_providers=False))


def _build_store(monkeypatch, tmp_path) -> dict[str, str]:
    """Temp home + real-schema DB with rows + events dir with parquet+jsonl."""
    home = tmp_path / "home"
    events = tmp_path / "events"
    events.mkdir()
    db = tmp_path / "graph.duckdb"

    monkeypatch.setenv("ANTIEK_HOME", str(home))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))

    init_database_at_path(str(db))
    with connect_write(str(db), purpose="test:export-fixture") as con:
        con.execute(
            "INSERT INTO documents (document_id, title, source_tier, document_type) "
            "VALUES ('d1', 'a', 1, 'url'), ('d2', 'b', 2, 'url')"
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n1', 'x', 'entity', 'depth')"
        )

    # One sealed parquet: written via DuckDB COPY (pyarrow is an optional
    # dependency; duckdb writes a real parquet either way).
    con = duckdb.connect(str(db))
    try:
        con.execute(
            f"COPY (SELECT 'evt-1' AS event_id, 'research.started' AS action_type) "
            f"TO '{events / 'inv-sealed.parquet'}' (FORMAT PARQUET)"
        )
    finally:
        con.close()
    # One live jsonl via the substrate event log (append-only, unsealed).
    log_event("inv-live", "research.started", events_dir=str(events))
    return {"home": str(home), "events": str(events), "db": str(db)}


def test_export_my_graph_bundle(monkeypatch, tmp_path):
    paths = _build_store(monkeypatch, tmp_path)
    db = paths["db"]
    # Events resolution honors ANTIEK_RESEARCH_EVENTS_DIR (fallback: ANTIEK_HOME).
    assert default_events_dir() == paths["events"]

    before = _sha256(db)

    created_dirs: list[str] = []
    real_mkdtemp = tempfile.mkdtemp

    def tracked_mkdtemp(*args, **kwargs):
        d = real_mkdtemp(*args, **kwargs)
        created_dirs.append(d)
        return d

    monkeypatch.setattr(export_routes.tempfile, "mkdtemp", tracked_mkdtemp)

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 200, resp.text[:500]
    assert resp.headers["content-type"].startswith("application/zip")
    disposition = resp.headers["content-disposition"]
    assert disposition.startswith("attachment; filename=")
    assert "antiek-graph-export-" in disposition
    assert disposition.rstrip('"').endswith(".zip")

    # The export must not mutate the source DB file.
    assert _sha256(db) == before, "source DuckDB file changed during export"

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    names = zf.namelist()
    assert "manifest.json" in names
    graph_entries = [n for n in names if n.startswith("graph/")]
    event_entries = [n for n in names if n.startswith("events/")]
    assert graph_entries, "zip missing graph/ contents"
    assert event_entries, "zip missing events/ contents"

    manifest = json.loads(zf.read("manifest.json"))
    assert manifest["source_db_path"] == "graph.duckdb"
    assert manifest["generated_at"]
    assert manifest["graph_not_mutated"] is True
    # The real Antiek schema (init_database_at_path) carries dozens of
    # tables; the two we seeded must be counted at their exact row counts.
    assert manifest["counts"]["tables"] >= 2
    assert manifest["counts"]["table_rows"]["documents"] == 2
    assert manifest["counts"]["table_rows"]["nodes"] == 1
    assert manifest["counts"]["event_files"] == 2
    assert manifest["counts"]["event_parquet_files"] == 1
    assert manifest["counts"]["event_jsonl_files"] == 1
    assert manifest["counts"]["master_files"] == 0
    assert manifest["master_md"]["status"].startswith("n/a")
    assert manifest["event_schema_version"] >= 1

    # graph/schema.sql is normalized: no self-ref-FK stray commas.
    schema = zf.read("graph/schema.sql").decode("utf-8")
    assert ", ," not in schema
    assert ", )" not in schema
    assert "CREATE TABLE" in schema

    # events copied verbatim and the parquet round-trips.
    assert "events/inv-sealed.parquet" in names
    assert "events/inv-live.jsonl" in names
    pq_path = tmp_path / "roundtrip.parquet"
    pq_path.write_bytes(zf.read("events/inv-sealed.parquet"))
    con = duckdb.connect()
    try:
        rows = con.execute(
            f"SELECT COUNT(*) FROM read_parquet('{pq_path}')"
        ).fetchone()[0]
    finally:
        con.close()
    assert rows == 1

    # The temp bundle is cleaned up after streaming completes.
    assert created_dirs, "mkdtemp was not called by the route"
    assert all(not os.path.exists(d) for d in created_dirs), (
        f"export temp dirs not cleaned up: {[d for d in created_dirs if os.path.exists(d)]}"
    )

    # The only DB-named sibling files are the DB and the writer-coordination
    # sidecar (house protocol; created by connect_write during setup).
    db_siblings = sorted(
        p.name for p in tmp_path.iterdir() if p.name.startswith("graph.duckdb")
    )
    assert db_siblings == ["graph.duckdb", "graph.duckdb.write.lock"]


def test_export_my_graph_503_when_db_path_invalid(monkeypatch, tmp_path):
    home = tmp_path / "empty-home"
    home.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(home))
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(home / "research_graph.duckdb"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "no-events"))

    resp = _client().get("/export/my-graph")
    assert resp.status_code == 503
    body = json.dumps(resp.json())
    assert str(home) not in body, "503 body leaks the db path"
    assert "traceback" not in body.lower()
    assert "research_graph" not in body
    assert "graph database unavailable" in body
