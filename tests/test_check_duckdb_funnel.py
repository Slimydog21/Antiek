"""CI gate for raw duckdb.connect in production layers."""

from __future__ import annotations

from pathlib import Path

from scripts.check_duckdb_funnel import ALLOWLIST_REL, REPO_ROOT, scan_file


def test_allowlist_db_lock_may_use_raw_connect() -> None:
    path = REPO_ROOT / "runtime" / "db_lock.py"
    assert scan_file(path) == []


def test_retrieval_substrate_on_allowlist() -> None:
    rel = "substrate/graph/retrieval_substrate.py"
    assert rel in ALLOWLIST_REL
    assert scan_file(REPO_ROOT / rel) == []


def test_escape_hatch_on_allowlist() -> None:
    assert scan_file(REPO_ROOT / "substrate" / "escape_hatch.py") == []


def test_violation_detected_in_synthetic_ast(tmp_path: Path) -> None:
    probe = tmp_path / "probe.py"
    probe.write_text("import duckdb\ncon = duckdb.connect('x')\n", encoding="utf-8")
    hits = scan_file(probe)
    assert len(hits) == 1