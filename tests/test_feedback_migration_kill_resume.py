"""Real-process kill/resume tests for the D2 SPR-01 v41 migration.

Kills a real subprocess at every committed phase boundary via
D2_FEEDBACK_V41_CRASH_AFTER and proves a fresh process resumes to
completion with intact digests and data, per the accepted sprint gate.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import duckdb
import pytest

from tests.test_feedback_migration_v41 import BASELINE_DDL, seed_valid_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "tests" / "_migration_crash_runner.py"
MIGRATION_ID = "d2_feedback_v41"


def _build_template(tmp_path: Path) -> Path:
    template = tmp_path / "template.duckdb"
    con = duckdb.connect(str(template))
    con.execute(BASELINE_DDL)
    seed_valid_rows(con)
    con.close()
    return template


def _run(db: Path, crash_after: str | None) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    if crash_after is not None:
        env["D2_FEEDBACK_V41_CRASH_AFTER"] = crash_after
    else:
        env.pop("D2_FEEDBACK_V41_CRASH_AFTER", None)
    return subprocess.run(
        [sys.executable, str(HELPER), str(db)],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
    )


@pytest.mark.parametrize("phase", ["started", "temp_created", "copied", "renamed"])
def test_kill_after_phase_then_resume(tmp_path: Path, phase: str) -> None:
    template = _build_template(tmp_path)
    db = tmp_path / f"case-{phase}.duckdb"
    shutil.copy(template, db)

    killed = _run(db, crash_after=phase)
    assert killed.returncode == 70, f"crash exit expected, got {killed.returncode}: {killed.stderr}"

    con = duckdb.connect(str(db))
    marker = con.execute(
        f"SELECT phase FROM schema_migrations WHERE migration_id = '{MIGRATION_ID}'"
    ).fetchone()
    con.close()
    assert marker is not None and marker[0] == phase

    resumed = _run(db, crash_after=None)
    assert resumed.returncode == 0, resumed.stderr

    con = duckdb.connect(str(db))
    row = con.execute(
        "SELECT phase, active_schema_sha256, active_rows_sha256, completed_at "
        f"FROM schema_migrations WHERE migration_id = '{MIGRATION_ID}'"
    ).fetchone()
    assert row is not None
    assert row[0] == "completed"
    assert len(row[1]) == 64 and len(row[2]) == 64
    assert row[3] is not None
    assert con.execute("SELECT count(*) FROM feedback_threads WHERE thread_id = 'thread-1'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM feedback_items WHERE thread_id = 'thread-1'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM agent_work WHERE work_id = 'work-1'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM agent_work_attempts WHERE attempt_id = 'att-1'").fetchone()[0] == 1
    con.close()


def test_completed_marker_survives_third_process(tmp_path: Path) -> None:
    """A third run against a completed DB is a verified no-op."""
    db = tmp_path / "third-run.duckdb"
    shutil.copy(_build_template(tmp_path), db)
    assert _run(db, crash_after=None).returncode == 0
    con = duckdb.connect(str(db))
    before_items = con.execute("SELECT * FROM feedback_items ORDER BY item_id").fetchall()
    marker = con.execute(
        f"SELECT phase, active_rows_sha256 FROM schema_migrations WHERE migration_id = '{MIGRATION_ID}'"
    ).fetchone()
    con.close()
    assert _run(db, crash_after=None).returncode == 0
    con = duckdb.connect(str(db))
    after_items = con.execute("SELECT * FROM feedback_items ORDER BY item_id").fetchall()
    marker_after = con.execute(
        f"SELECT phase, active_rows_sha256 FROM schema_migrations WHERE migration_id = '{MIGRATION_ID}'"
    ).fetchone()
    con.close()
    assert after_items == before_items
    assert marker_after == marker
    assert marker_after[0] == "completed"
