"""Tests for ``scripts/reconstruct_vector_index.py``.

End-to-end: create a DuckDB file with the chunks-table shape, plant
N chunks (some with NULL embedding), run the script, assert the right
rows got embeddings and the script honored budget + dry-run flags.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path
from typing import Any

import duckdb
import pytest

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_SCRIPT_PATH = _REPO / "scripts" / "reconstruct_vector_index.py"
_spec = importlib.util.spec_from_file_location("rvi", _SCRIPT_PATH)
assert _spec is not None and _spec.loader is not None
rvi = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(rvi)


class _DeterministicModel:
    """Deterministic 4-dim "embedding" model for tests. Returns a
    vector derived from the text content; same text → same vector.
    """

    dimension = 4

    def encode(self, text: str) -> list[float]:
        # Trivially deterministic: length, sum of bytes, vowel count, hash mod.
        text_bytes = text.encode("utf-8")
        vowels = sum(1 for c in text.lower() if c in "aeiou")
        return [
            float(len(text)),
            float(sum(text_bytes) % 1000),
            float(vowels),
            float(hash(text) % 1000),
        ]


@pytest.fixture
def populated_db(tmp_path: Path) -> Path:
    """Create a DuckDB file with the chunks-table shape and 10 chunks.

    Rows 0-6: ``embedding IS NULL`` (need reconstruction).
    Rows 7-9: pre-populated embeddings (should be left alone unless
    ``--rebuild`` is set).
    """
    db_path = tmp_path / "test.duckdb"
    con = duckdb.connect(str(db_path))
    con.execute(
        """
        CREATE TABLE chunks (
            chunk_id      TEXT PRIMARY KEY,
            text          TEXT NOT NULL,
            embedding     FLOAT[],
            token_count   INTEGER NOT NULL DEFAULT 0
        )
        """
    )
    for i in range(10):
        text = f"chunk number {i} with some content"
        if i < 7:
            con.execute(
                "INSERT INTO chunks VALUES (?, ?, NULL, ?)",
                [f"c{i:03d}", text, len(text.split())],
            )
        else:
            # Pre-populated with a sentinel vector.
            con.execute(
                "INSERT INTO chunks VALUES (?, ?, ?, ?)",
                [f"c{i:03d}", text, [-1.0, -1.0, -1.0, -1.0], len(text.split())],
            )
    con.close()
    return db_path


# ---------------------------------------------------------------------------
# Idempotent reconstruction
# ---------------------------------------------------------------------------


def test_reconstruct_fills_missing_embeddings(populated_db: Path) -> None:
    """Default mode: only NULL embeddings get filled."""
    model = _DeterministicModel()
    result = rvi.reconstruct(str(populated_db), model=model)
    assert result["missing_before"] == 7
    assert result["embedded_this_run"] == 7

    # Verify the DB: zero NULL embeddings remain; the pre-populated
    # rows are unchanged (still the sentinel).
    con = duckdb.connect(str(populated_db), read_only=True)
    null_count = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL"
    ).fetchone()[0]
    sentinel_count = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding = [-1.0, -1.0, -1.0, -1.0]"
    ).fetchone()[0]
    con.close()
    assert null_count == 0
    assert sentinel_count == 3  # pre-populated rows untouched


def test_reconstruct_is_idempotent(populated_db: Path) -> None:
    """Running twice → second run does zero work."""
    model = _DeterministicModel()
    first = rvi.reconstruct(str(populated_db), model=model)
    assert first["embedded_this_run"] == 7
    second = rvi.reconstruct(str(populated_db), model=model)
    assert second["embedded_this_run"] == 0
    assert second["missing_before"] == 0


def test_reconstruct_rebuild_re_embeds_all(populated_db: Path) -> None:
    """``--rebuild``: every chunk gets a fresh embedding, including
    the pre-populated ones (which were the sentinel).
    """
    model = _DeterministicModel()
    result = rvi.reconstruct(
        str(populated_db), model=model, rebuild=True
    )
    assert result["embedded_this_run"] == 10

    # Sentinel rows should now be the deterministic-model output.
    con = duckdb.connect(str(populated_db), read_only=True)
    sentinel_count = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding = [-1.0, -1.0, -1.0, -1.0]"
    ).fetchone()[0]
    con.close()
    assert sentinel_count == 0


# ---------------------------------------------------------------------------
# Boundedness
# ---------------------------------------------------------------------------


def test_max_chunks_caps_work(populated_db: Path) -> None:
    """``--max-chunks=3`` embeds only 3 of the 7 missing."""
    model = _DeterministicModel()
    result = rvi.reconstruct(
        str(populated_db), model=model, max_chunks=3
    )
    assert result["embedded_this_run"] == 3


def test_dry_run_writes_nothing(populated_db: Path) -> None:
    """``--dry-run``: report the plan, make no changes."""
    model = _DeterministicModel()
    result = rvi.reconstruct(
        str(populated_db), model=model, dry_run=True
    )
    assert result["missing_before"] == 7
    assert result["embedded_this_run"] == 0
    # DB unchanged.
    con = duckdb.connect(str(populated_db), read_only=True)
    null_count = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL"
    ).fetchone()[0]
    con.close()
    assert null_count == 7


# ---------------------------------------------------------------------------
# Cost budget
# ---------------------------------------------------------------------------


def test_cost_budget_stops_cleanly(populated_db: Path) -> None:
    """Cost budget exhausted → script stops cleanly, reports skipped."""
    model = _DeterministicModel()
    # 0.10 per chunk; budget 0.25 → exactly 2 fit before projected
    # 0.30 exceeds. Third chunk gets skipped on the budget check.
    result = rvi.reconstruct(
        str(populated_db),
        model=model,
        cost_per_chunk_usd=0.10,
        cost_budget_usd=0.25,
    )
    assert result["embedded_this_run"] == 2
    assert result["skipped_by_budget"] == 5  # 7 missing - 2 embedded
    # Allow tiny floating-point drift.
    assert abs(float(result["estimated_cost_usd"]) - 0.20) < 1e-9


def test_cost_budget_zero_does_no_work(populated_db: Path) -> None:
    """Budget=0 + cost>0 → embed nothing."""
    model = _DeterministicModel()
    result = rvi.reconstruct(
        str(populated_db),
        model=model,
        cost_per_chunk_usd=0.10,
        cost_budget_usd=0.0,
    )
    assert result["embedded_this_run"] == 0
    assert result["skipped_by_budget"] == 7


def test_cost_budget_none_means_unlimited(populated_db: Path) -> None:
    """No budget → embed everything missing."""
    model = _DeterministicModel()
    result = rvi.reconstruct(
        str(populated_db),
        model=model,
        cost_per_chunk_usd=0.10,
        cost_budget_usd=None,
    )
    assert result["embedded_this_run"] == 7


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_help_works() -> None:
    import subprocess
    proc = subprocess.run(
        [sys.executable, str(_SCRIPT_PATH), "--help"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0
    assert "reconstruct" in proc.stdout.lower()
    assert "--dry-run" in proc.stdout


def test_cli_dry_run_against_real_db(populated_db: Path) -> None:
    """End-to-end CLI: --dry-run on a real DB exits 0, reports the
    plan, makes no changes.
    """
    import subprocess
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--db",
            str(populated_db),
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert proc.returncode == 0, f"stderr: {proc.stderr}"
    assert "DRY RUN" in proc.stdout
    # DB unchanged.
    con = duckdb.connect(str(populated_db), read_only=True)
    null_count = con.execute(
        "SELECT COUNT(*) FROM chunks WHERE embedding IS NULL"
    ).fetchone()[0]
    con.close()
    assert null_count == 7


def test_cli_rejects_missing_db() -> None:
    import subprocess
    proc = subprocess.run(
        [
            sys.executable,
            str(_SCRIPT_PATH),
            "--db",
            "/nonexistent/path/does/not/exist.duckdb",
            "--dry-run",
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 2
    assert "does not exist" in proc.stderr


# ---------------------------------------------------------------------------
# Embeddings are stable round-trip
# ---------------------------------------------------------------------------


def test_round_trip_preserves_vectors_bit_identical(populated_db: Path) -> None:
    """The vector that goes in equals the vector that comes out."""
    model = _DeterministicModel()
    rvi.reconstruct(str(populated_db), model=model)

    con = duckdb.connect(str(populated_db), read_only=True)
    rows = con.execute(
        "SELECT chunk_id, text, embedding FROM chunks "
        "WHERE chunk_id LIKE 'c00%' ORDER BY chunk_id"
    ).fetchall()
    con.close()

    for chunk_id, text, stored_vec in rows[:7]:  # only the NULL ones got embedded
        expected = model.encode(text)
        assert list(stored_vec) == expected, (
            f"round-trip mismatch for {chunk_id}: "
            f"stored={list(stored_vec)} expected={expected}"
        )
