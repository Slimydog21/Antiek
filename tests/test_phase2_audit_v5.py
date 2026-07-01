"""Current-state checks for the Phase 2 audit reconciliation."""

from __future__ import annotations

from pathlib import Path


REPO = Path(__file__).resolve().parents[1]


def test_phase2_audit_v5_records_ducklake_router_resolution():
    text = (
        REPO / "docs" / "phase2_execution_audit_v5_2026_07_01.md"
    ).read_text(encoding="utf-8")
    router = (REPO / "substrate" / "multi_user" / "graph_router.py").read_text(
        encoding="utf-8",
    )
    graph = (REPO / "substrate" / "graph" / "__init__.py").read_text(
        encoding="utf-8",
    )

    assert "23048220 feat(ducklake): route default graph path through catalog" in text
    assert "net engineering-side-blocked items known from" in text
    assert "v4: **0**" in text
    assert "OA-010 remains `PARTIALLY MITIGATED`" in text
    assert "ANTIEK_DUCKLAKE_CATALOG_DB" in text
    assert "default_db_path()" in text
    assert "build_graph_router_from_env" in router
    assert "default_personal_graph_handle" in router
    assert "ANTIEK_DUCKLAKE_CATALOG_DB" in graph
