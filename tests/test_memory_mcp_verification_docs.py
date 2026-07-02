"""Verification-doc guards for the Antiek Memory MCP programme."""

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SPEC_DIR = ROOT / "docs" / "htmlspec" / "antiek-memory-mcp"
LEDGER = SPEC_DIR / ".caffenagent" / "run-ledger.md"


def _read(rel: str) -> str:
    return (SPEC_DIR / rel).read_text(encoding="utf-8")


def test_memory_mcp_specs_use_repo_relative_exit_commands() -> None:
    combined = "\n".join(path.read_text(encoding="utf-8") for path in SPEC_DIR.rglob("*") if path.is_file())

    assert "/Users/slimydog/Desktop/Antiek" not in combined
    assert "cd /Users/slimydog" not in combined
    assert ".venv/bin/python -m pytest tests/test_mcp_server.py" in combined
    assert ".venv/bin/python -m mypy services/mcp_server/ --strict" in combined
    assert ".venv/bin/python -m ruff check services/mcp_server/" in combined


def test_memory_mcp_ledger_pins_all_sprint_proof_surfaces() -> None:
    ledger = LEDGER.read_text(encoding="utf-8")

    for test_path in (
        "tests/test_mcp_server.py",
        "tests/test_mcp_tools.py",
        "tests/test_mcp_resources.py",
        "tests/test_mcp_defenses.py",
        "tests/test_mcp_e2e.py",
    ):
        assert test_path in ledger

    assert "Result: `127 passed`; strict mypy clean; ruff clean." in ledger
    assert "OAuth token validation, rate limiting, or multi-user isolation" in ledger
    assert "remain explicitly out of scope" in ledger


def test_memory_mcp_overview_names_scope_boundary_and_all_sprints() -> None:
    index = _read("index.html")

    for sprint in ("MCP-SPR-01", "MCP-SPR-02", "MCP-SPR-03", "MCP-SPR-04"):
        assert sprint in index

    assert "closed with hermetic tests" in index
    assert "This programme proves the single-operator MCP memory surface." in index
