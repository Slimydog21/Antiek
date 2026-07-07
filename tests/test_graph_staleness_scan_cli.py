from __future__ import annotations

import json
from datetime import datetime

from middleware.temporal import scan_graph_edge_staleness
from runtime.db_lock import connect_read, connect_write
from substrate.event_log import trajectory
from substrate.graph import init_database_at_path, insert_document, insert_edge, insert_node
from tools.graph_staleness_scan import main


def _seed_graph(path: str) -> None:
    init_database_at_path(path)
    with connect_write(path, purpose="test:graph-staleness-scan-cli") as con:
        insert_document(
            con,
            document_id="doc-stale",
            source_tier=2,
            document_type="paper",
            published_at=datetime(2026, 3, 1),
        )
        source = insert_node(
            con,
            canonical_label="source",
            node_type="entity",
            graph_scope="depth",
            investigation_id="seed",
        )
        target = insert_node(
            con,
            canonical_label="target",
            node_type="entity",
            graph_scope="depth",
            investigation_id="seed",
        )
        insert_edge(
            con,
            edge_id="edge-stale",
            source_node_id=source,
            target_node_id=target,
            relation="led_by",
            source_tier=2,
            extraction_confidence=0.9,
            graph_scope="depth",
            investigation_id="seed",
            source_document_id="doc-stale",
        )


def test_cli_dry_run_prints_summary_without_events(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "graph.duckdb")
    _seed_graph(db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    rc = main([
        "--graph", db_path,
        "--as-of", "2026-07-07T00:00:00Z",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["emit_events"] is False
    assert summary["scanned"] == 1
    assert summary["flagged"] == 1
    assert summary["flags"][0]["event_id"] is None
    assert trajectory("graph-staleness-scan") == []


def test_cli_emit_events_appends_typed_staleness_event(tmp_path, monkeypatch, capsys):
    db_path = str(tmp_path / "graph.duckdb")
    _seed_graph(db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    rc = main([
        "--graph", db_path,
        "--as-of", "2026-07-07T00:00:00Z",
        "--investigation-id", "inv-staleness",
        "--emit-events",
    ])

    assert rc == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["emit_events"] is True
    assert summary["flagged"] == 1
    assert summary["flags"][0]["event_id"] is not None
    rows = trajectory("inv-staleness")
    assert len(rows) == 1
    assert rows[0]["payload"]["edge_id"] == "edge-stale"


def test_cli_missing_graph_returns_2(tmp_path, capsys):
    rc = main(["--graph", str(tmp_path / "missing.duckdb")])
    assert rc == 2
    assert "graph not found" in capsys.readouterr().err


def test_cli_negative_limit_returns_2(tmp_path, capsys):
    db_path = str(tmp_path / "graph.duckdb")
    _seed_graph(db_path)

    rc = main(["--graph", db_path, "--limit", "-1"])

    assert rc == 2
    assert "limit must be non-negative" in capsys.readouterr().err


def test_cli_matches_scanner_result(tmp_path):
    db_path = str(tmp_path / "graph.duckdb")
    _seed_graph(db_path)

    with connect_read(db_path) as con:
        result = scan_graph_edge_staleness(
            con,
            investigation_id="manual",
            as_of=datetime(2026, 7, 7),
            emit_events=False,
        )

    assert result.scanned == 1
    assert len(result.flagged) == 1
