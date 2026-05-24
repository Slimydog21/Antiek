"""Shared fixtures for the research_bridge test suite."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterator

import pytest

# Ensure repo root is importable when pytest invokes us from any cwd.
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


_FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    """Absolute path to the fixtures directory."""
    return _FIXTURES_DIR


@pytest.fixture
def fixture_text():
    """Read a fixture by source name. Returns the verbatim string."""
    def _read(source: str) -> str:
        p = _FIXTURES_DIR / f"{source}.txt"
        return p.read_text(encoding="utf-8")
    return _read


@pytest.fixture
def tmp_db_with_bridge(tmp_path: Path) -> Iterator[Path]:
    """A DuckDB file with the graph schema + research bridge schema
    applied. One yielded path; cleaned up by tmp_path. The full graph
    schema is applied first so research_pastes' FK to documents lands
    against a real table.
    """
    from substrate.graph import init_database_at_path
    from substrate.research_bridge import init_research_bridge_at_path

    db_path = tmp_path / "test.duckdb"
    init_database_at_path(str(db_path))
    init_research_bridge_at_path(str(db_path))
    yield db_path
    # tmp_path tear-down handles cleanup.
