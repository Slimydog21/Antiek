"""Concurrent-writer and migration-lock contention tests for SPR-01.

Proves the accepted contract: baseline writers cannot add rows between copy
and rename, no concurrent write is lost, and a second migration attempting
the d2_feedback_v41 lock receives migration_in_progress.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

import duckdb

from tests.test_feedback_migration_v41 import BASELINE_DDL, seed_valid_rows

REPO_ROOT = Path(__file__).resolve().parents[1]
RUNNER = REPO_ROOT / "tests" / "_migration_crash_runner.py"
WRITER = REPO_ROOT / "tests" / "_migration_concurrent_writer.py"
MIGRATION_ID = "d2_feedback_v41"


def _seeded_db(tmp_path: Path, name: str) -> Path:
    db = tmp_path / name
    con = duckdb.connect(str(db))
    con.execute(BASELINE_DDL)
    seed_valid_rows(con)
    con.close()
    return db


def _run_migration(db: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(RUNNER), str(db)],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=120,
    )


def test_writer_excluded_while_write_flock_held(tmp_path: Path) -> None:
    """A writer is refused for as long as any holder keeps the write flock.

    The migration holds this flock for its entire span (open through close),
    so this is the deterministic primitive behind "no row can be added
    between copy and rename": while the lock is held, no writer can write.
    """
    db = _seeded_db(tmp_path, "flock.duckdb")
    lock_path = str(db) + ".write.lock"

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time; "
            "fd = os.open(sys.argv[1], os.O_CREAT | os.O_WRONLY, 0o600); "
            "fcntl.flock(fd, fcntl.LOCK_EX); "
            "print('held', flush=True); "
            "time.sleep(3)",
            lock_path,
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "held"

    probe_script = (
        "import sys\n"
        "sys.path.insert(0, '.')\n"
        "from runtime.db_lock import WriteLockTimeout, connect_write\n"
        "try:\n"
        "    connect_write(sys.argv[1], purpose='probe', timeout_s=0.25)\n"
        "except WriteLockTimeout:\n"
        "    raise SystemExit(3)\n"
        "raise SystemExit(0)\n"
    )
    probe = subprocess.run(
        [
            sys.executable,
            "-c",
            probe_script,
            str(db),
        ],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        timeout=30,
    )
    holder.wait(timeout=10)
    assert probe.returncode == 3, (
        f"writer was not excluded while the flock was held: rc={probe.returncode} {probe.stderr}"
    )


def test_concurrent_writer_never_loses_rows(tmp_path: Path) -> None:
    """End-to-end race: migration completes and every successful write survives.

    The writer samples varied phases around and across the migration run.
    Contention itself is proven deterministically in
    test_writer_excluded_while_write_flock_held; here the invariant is that
    pre-migration, mid-boot, and post-migration writes are all present in
    the final active table with the marker completed.
    """
    db = _seeded_db(tmp_path, "race.duckdb")
    log_path = tmp_path / "writer-log.txt"

    writer = subprocess.Popen(
        [sys.executable, str(WRITER), str(db), "cw", str(log_path), "24", "0.05,0.15,0.25,0.35"],
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    time.sleep(0.4)  # let the writer claim inserts before the migration starts
    migrated = _run_migration(db)
    writer_out, writer_err = writer.communicate(timeout=60)
    assert writer.returncode == 0, writer_err
    assert migrated.returncode == 0, migrated.stderr

    inserted = log_path.read_text().split()
    assert len(inserted) >= 2, "writer never managed multiple inserts; test setup broken"

    con = duckdb.connect(str(db))
    marker = con.execute(
        f"SELECT phase FROM schema_migrations WHERE migration_id = '{MIGRATION_ID}'"
    ).fetchone()
    assert marker is not None and marker[0] == "completed"
    lost = [
        thread_id
        for thread_id in inserted
        if con.execute(
            "SELECT thread_id FROM feedback_threads WHERE thread_id = ?", [thread_id]
        ).fetchone()
        is None
    ]
    con.close()
    assert not lost, f"lost concurrent writes: {lost}"


def test_second_migration_receives_migration_in_progress(tmp_path: Path) -> None:
    """A migration starting while the lock is held fails closed, fast."""
    db = _seeded_db(tmp_path, "contended.duckdb")
    lock_path = str(db) + ".d2_feedback_v41.lock"

    holder = subprocess.Popen(
        [
            sys.executable,
            "-c",
            "import fcntl, os, sys, time; "
            "fd = os.open(sys.argv[1], os.O_CREAT | os.O_WRONLY, 0o600); "
            "fcntl.flock(fd, fcntl.LOCK_EX); "
            "print('held', flush=True); "
            "time.sleep(3)",
            lock_path,
        ],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert holder.stdout is not None
    assert holder.stdout.readline().strip() == "held"

    started = time.monotonic()
    contended = _run_migration(db)
    elapsed = time.monotonic() - started
    holder.wait(timeout=10)
    assert contended.returncode != 0
    assert "migration_in_progress" in contended.stderr
    assert elapsed < 3, "contended migration waited for the lock instead of failing fast"

    con = duckdb.connect(str(db))
    tables = {
        row[0]
        for row in con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    }
    con.close()
    assert not any("schema_migrations" in name or name.endswith("_v41") for name in tables), (
        "failed attempt must not mutate the catalog"
    )
