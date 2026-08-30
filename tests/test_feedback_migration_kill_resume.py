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


def test_baseline_drift_after_crash_refuses_rename(tmp_path: Path) -> None:
    """A baseline write between crash-at-copied and resume fails closed.

    Before the rename-time baseline-digest pre-check, such rows were
    silently dropped by the rename DROP; now the resume must refuse with
    migration_conflict and leave both the baseline row and the marker
    untouched for operator resolution.
    """
    db = tmp_path / "drift.duckdb"
    shutil.copy(_build_template(tmp_path), db)

    killed = _run(db, crash_after="copied")
    assert killed.returncode == 70, killed.stderr

    con = duckdb.connect(str(db))
    con.execute(
        """INSERT INTO feedback_threads (
            thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
            artifact_content_sha256, artifact_source_sha256, normalization,
            anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar,
            anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id,
            create_request_sha256
        ) VALUES ('late-thread', 'owner-a', 'inv-1', 'art-1', 1, ?, ?, 'unicode-nfc-v1',
                  'node-1', ?, 0, 1, 'q', '', '', 'open', 'op-late', ?)""",
        ["a" * 64, "b" * 64, "c" * 64, "d" * 64],
    )
    con.close()

    resumed = _run(db, crash_after=None)
    assert resumed.returncode != 0
    assert "migration_conflict" in resumed.stderr
    assert "baseline tables changed" in resumed.stderr

    con = duckdb.connect(str(db))
    phase = con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()[0]
    assert phase == "copied"
    assert con.execute(
        "SELECT count(*) FROM feedback_threads WHERE thread_id = 'late-thread'"
    ).fetchone()[0] == 1
    assert con.execute(
        "SELECT count(*) FROM feedback_threads_v41 WHERE thread_id = 'thread-1'"
    ).fetchone()[0] == 1
    con.close()


def test_temp_created_resume_rejects_catalog_ddl_drift(tmp_path: Path) -> None:
    """A crash at temp_created cannot bless tampered temporary DDL on resume."""
    db = tmp_path / "temp-ddl-drift.duckdb"
    shutil.copy(_build_template(tmp_path), db)

    killed = _run(db, crash_after="temp_created")
    assert killed.returncode == 70, killed.stderr

    con = duckdb.connect(str(db))
    marker = con.execute(
        "SELECT phase, temp_schema_sha256 FROM schema_migrations "
        "WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()
    assert marker is not None
    assert marker[0] == "temp_created"
    assert marker[1] is not None and len(marker[1]) == 64
    con.execute("ALTER TABLE feedback_items_v41 ADD COLUMN rogue_column VARCHAR")
    con.close()

    resumed = _run(db, crash_after=None)
    assert resumed.returncode != 0
    assert "migration_conflict: temporary schema digest mismatch" in resumed.stderr

    con = duckdb.connect(str(db))
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone() == ("temp_created",)
    assert con.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='feedback_items_v41' AND column_name='rogue_column'"
    ).fetchone() == (1,)
    con.close()



def test_started_resume_rejects_preexisting_v41_catalog(tmp_path: Path) -> None:
    """No v41 object can legitimately pre-exist after atomic crash-at-started."""
    db = tmp_path / "started-catalog-tamper.duckdb"
    shutil.copy(_build_template(tmp_path), db)

    killed = _run(db, crash_after="started")
    assert killed.returncode == 70, killed.stderr

    con = duckdb.connect(str(db))
    con.execute(
        "CREATE TABLE feedback_provenance "
        "(thread_id VARCHAR, owner_user_id VARCHAR, ref_index INTEGER)"
    )
    con.execute(
        "CREATE INDEX idx_feedback_provenance_owner "
        "ON feedback_provenance(thread_id, ref_index)"
    )
    con.close()

    resumed = _run(db, crash_after=None)
    assert resumed.returncode != 0
    assert "migration_conflict: v41 catalog objects already exist at started" in resumed.stderr

    con = duckdb.connect(str(db))
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone() == ("started",)
    assert con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_name='feedback_threads_v41'"
    ).fetchone() == (0,)
    assert con.execute(
        "SELECT count(*) FROM information_schema.columns "
        "WHERE table_name='feedback_provenance'"
    ).fetchone() == (3,)
    con.close()



def test_started_resume_rejects_case_variant_v41_index(tmp_path: Path) -> None:
    """DuckDB identifiers are case-insensitive, so catalog guards must be too."""
    db = tmp_path / "started-case-variant-index.duckdb"
    shutil.copy(_build_template(tmp_path), db)

    killed = _run(db, crash_after="started")
    assert killed.returncode == 70, killed.stderr

    con = duckdb.connect(str(db))
    con.execute("CREATE TABLE index_carrier (thread_id VARCHAR, ref_index INTEGER)")
    con.execute(
        "CREATE INDEX IDX_FEEDBACK_PROVENANCE_OWNER "
        "ON index_carrier(thread_id, ref_index)"
    )
    con.close()

    resumed = _run(db, crash_after=None)
    assert resumed.returncode != 0
    assert "migration_conflict: v41 catalog objects already exist at started" in resumed.stderr

    con = duckdb.connect(str(db))
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone() == ("started",)
    assert con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE lower(table_name)='feedback_provenance'"
    ).fetchone() == (0,)
    con.close()
