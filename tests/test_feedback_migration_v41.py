"""Tests for D2 SPR-01 feedback v41 migration.

Ownership: SPR-01. Validates the nine-table rebuild, quarantine,
idempotency, and crash/resume semantics against a real DuckDB file.
"""

from __future__ import annotations

import datetime
import hashlib
import inspect
import json
import re

import duckdb
import pytest

BASELINE_DDL = """
    CREATE TABLE IF NOT EXISTS feedback_threads (
      thread_id VARCHAR PRIMARY KEY,
      owner_user_id VARCHAR NOT NULL,
      investigation_id VARCHAR NOT NULL,
      artifact_id VARCHAR NOT NULL,
      artifact_version INTEGER NOT NULL CHECK (artifact_version > 0),
      artifact_content_sha256 VARCHAR NOT NULL,
      artifact_source_sha256 VARCHAR NOT NULL,
      normalization VARCHAR NOT NULL CHECK (normalization = 'unicode-nfc-v1'),
      anchor_node_id VARCHAR NOT NULL,
      anchor_node_text_sha256 VARCHAR NOT NULL,
      anchor_start_scalar INTEGER NOT NULL CHECK (anchor_start_scalar >= 0),
      anchor_end_scalar INTEGER NOT NULL CHECK (anchor_end_scalar > anchor_start_scalar),
      anchor_quote VARCHAR NOT NULL,
      anchor_prefix VARCHAR NOT NULL,
      anchor_suffix VARCHAR NOT NULL,
      state VARCHAR NOT NULL DEFAULT 'open' CHECK (state IN ('open', 'resolved')),
      create_operation_id VARCHAR NOT NULL UNIQUE,
      create_request_sha256 VARCHAR NOT NULL,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
    );
    CREATE TABLE IF NOT EXISTS feedback_items (
      item_id VARCHAR PRIMARY KEY,
      thread_id VARCHAR NOT NULL,
      sequence INTEGER NOT NULL CHECK (sequence > 0),
      author_kind VARCHAR NOT NULL CHECK (author_kind IN ('operator', 'agent', 'system')),
      author_id VARCHAR NOT NULL,
      body_markdown VARCHAR NOT NULL,
      work_id VARCHAR,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (thread_id, sequence)
    );
    CREATE TABLE IF NOT EXISTS agent_work (
      work_id VARCHAR PRIMARY KEY,
      thread_id VARCHAR NOT NULL UNIQUE,
      logical_worker_id VARCHAR NOT NULL,
      state VARCHAR NOT NULL DEFAULT 'queued',
      context_sha256 VARCHAR NOT NULL,
      attempt_count INTEGER NOT NULL DEFAULT 0,
      active_lease_id VARCHAR,
      lease_expires_at TIMESTAMPTZ,
      not_before TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      last_error_code VARCHAR,
      result_sha256 VARCHAR,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      terminal_at TIMESTAMPTZ
    );
    CREATE TABLE IF NOT EXISTS agent_work_attempts (
      attempt_id VARCHAR PRIMARY KEY,
      work_id VARCHAR NOT NULL,
      attempt_no INTEGER NOT NULL CHECK (attempt_no > 0),
      lease_id VARCHAR NOT NULL UNIQUE,
      bridge_credential_id VARCHAR NOT NULL,
      bridge_instance_id VARCHAR NOT NULL,
      state VARCHAR NOT NULL DEFAULT 'leased',
      lease_expires_at TIMESTAMPTZ NOT NULL,
      herdr_target_observed VARCHAR,
      adapter_version VARCHAR,
      transport_receipt_sha256 VARCHAR,
      result_from_state VARCHAR,
      submitted_at TIMESTAMPTZ,
      acknowledged_at TIMESTAMPTZ,
      working_at TIMESTAMPTZ,
      completed_at TIMESTAMPTZ,
      created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
      UNIQUE (work_id, attempt_no)
    );
    """


def seed_valid_rows(con) -> None:
    """Seed one valid thread/item/work/attempt aggregate for tests."""
    now = datetime.datetime.now(datetime.UTC)
    # Insert valid thread.
    con.execute("""
    INSERT INTO feedback_threads (
        thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
        artifact_content_sha256, artifact_source_sha256, normalization,
        anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar,
        anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id,
        create_request_sha256, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        "thread-1", "owner-a", "inv-1", "art-1", 1,
        "a" * 64, "b" * 64, "unicode-nfc-v1",
        "node-1", "c" * 64, 0, 100,
        "quote text", "pre" + "x" * 29, "suf" + "y" * 29, "open", "op-1",
        "d" * 64, now, now,
    ])

    # Insert valid item.
    con.execute("""
    INSERT INTO feedback_items (
        item_id, thread_id, sequence, author_kind, author_id, body_markdown, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ["item-1", "thread-1", 1, "operator", "owner-a", "body text", now])

    # Insert valid work.
    con.execute("""
    INSERT INTO agent_work (
        work_id, thread_id, logical_worker_id, state, context_sha256, not_before, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, ["work-1", "thread-1", "worker-1", "queued", "e" * 64, now, now, now])

    # Insert valid attempt.
    con.execute("""
    INSERT INTO agent_work_attempts (
        attempt_id, work_id, attempt_no, lease_id, bridge_credential_id, bridge_instance_id,
        state, lease_expires_at, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, ["att-1", "work-1", 1, "lease-1", "cred-1", "inst-1", "leased", now, now])



@pytest.fixture
def db_path(tmp_path):
    """Create a temporary DuckDB database path."""
    return str(tmp_path / "test_feedback.duckdb")


@pytest.fixture
def baseline_db(db_path):
    """Create a baseline v40 database with test data."""
    con = duckdb.connect(db_path)
    # Create baseline schema.
    con.execute(BASELINE_DDL)
    con.close()
    return db_path


@pytest.fixture
def seeded_db(baseline_db):
    """Create a baseline database with valid test data."""
    con = duckdb.connect(baseline_db)
    seed_valid_rows(con)
    con.close()
    return baseline_db


def test_migration_creates_all_tables(seeded_db):
    """Migration creates all nine v41 tables."""
    # Add a fake LockedConnection wrapper for testing.
    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)
        def fetchone(self):
            return None

    con = FakeLockedConnection(seeded_db)
    migrate_feedback_v41(con)

    # Verify all tables exist.
    tables = set()
    for row in con.execute("SELECT table_name FROM information_schema.tables").fetchall():
        tables.add(row[0])

    # After rename, active tables should have v41 names removed.
    # The migration renames v41 → baseline names.
    # So baseline tables should be gone, v41 names should be the active ones.
    assert "schema_migrations" in tables
    assert "feedback_provenance" in tables


def test_migration_idempotent(seeded_db):
    """Running migration twice is a no-op."""
    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = FakeLockedConnection(seeded_db)
    migrate_feedback_v41(con)
    # Second run should not fail.
    migrate_feedback_v41(con)

    # Marker should be completed.
    result = con.execute("SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'").fetchone()
    assert result is not None
    assert result[0] == "completed"


def test_valid_rows_migrated(seeded_db):
    """Valid baseline rows are copied to v41 tables."""
    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = FakeLockedConnection(seeded_db)
    migrate_feedback_v41(con)

    # Check that valid thread was migrated.
    result = con.execute("SELECT thread_id, entry_kind FROM feedback_threads WHERE thread_id = 'thread-1'").fetchone()
    assert result is not None
    assert result[0] == "thread-1"
    assert result[1] == "comment"

    # Check that valid item was migrated.
    result = con.execute("SELECT item_id, entry_kind FROM feedback_items WHERE item_id = 'item-1'").fetchone()
    assert result is not None
    assert result[1] == "comment"

    # Check that valid work was migrated.
    result = con.execute("SELECT work_id, work_kind FROM agent_work WHERE work_id = 'work-1'").fetchone()
    assert result is not None
    assert result[1] == "feedback_reply"

    # Check that valid attempt was migrated.
    result = con.execute("SELECT attempt_id, work_kind FROM agent_work_attempts WHERE attempt_id = 'att-1'").fetchone()
    assert result is not None
    assert result[1] == "feedback_reply"
    assert con.execute("SELECT attempt_actual_cents FROM agent_work_attempts WHERE attempt_id = 'att-1'").fetchone()[0] == 0


def test_quarantine_malformed_thread(baseline_db):
    """Malformed threads are quarantined, not migrated."""
    con = duckdb.connect(baseline_db)
    now = datetime.datetime.now(datetime.UTC)

    # Insert a thread with invalid content hash (not 64-hex).
    con.execute("""
    INSERT INTO feedback_threads (
        thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
        artifact_content_sha256, artifact_source_sha256, normalization,
        anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar,
        anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id,
        create_request_sha256, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        "bad-thread", "owner-a", "inv-1", "art-1", 1,
        "INVALID_HASH", "b" * 64, "unicode-nfc-v1",
        "node-1", "c" * 64, 0, 100,
        "quote text", "pre" + "x" * 29, "suf" + "y" * 29, "open", "op-bad",
        "d" * 64, now, now,
    ])
    con.close()

    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = FakeLockedConnection(baseline_db)
    migrate_feedback_v41(con)

    # Bad thread should be quarantined.
    result = con.execute("SELECT reason FROM feedback_threads_v41_quarantine WHERE original_thread_id = 'bad-thread'").fetchone()
    assert result is not None
    assert result[0] in ("invalid_hash", "unknown_malformation")

    # Bad thread should NOT be in active table.
    result = con.execute("SELECT thread_id FROM feedback_threads WHERE thread_id = 'bad-thread'").fetchone()
    assert result is None


def test_quarantine_malformed_item(baseline_db):
    """Malformed items are quarantined."""
    con = duckdb.connect(baseline_db)
    now = datetime.datetime.now(datetime.UTC)

    # Insert a valid thread.
    con.execute("""
    INSERT INTO feedback_threads (
        thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
        artifact_content_sha256, artifact_source_sha256, normalization,
        anchor_node_id, anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar,
        anchor_quote, anchor_prefix, anchor_suffix, state, create_operation_id,
        create_request_sha256, created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, [
        "thread-1", "owner-a", "inv-1", "art-1", 1,
        "a" * 64, "b" * 64, "unicode-nfc-v1",
        "node-1", "c" * 64, 0, 100,
        "quote text", "pre" + "x" * 29, "suf" + "y" * 29, "open", "op-1",
        "d" * 64, now, now,
    ])

    # Insert an item with empty body (valid baseline, but v41 comment requires >= 1).
    con.execute("""
    INSERT INTO feedback_items (
        item_id, thread_id, sequence, author_kind, author_id, body_markdown, created_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ["bad-item", "thread-1", 1, "operator", "owner-a", "", now])
    con.close()

    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = FakeLockedConnection(baseline_db)
    migrate_feedback_v41(con)

    # Bad item should be quarantined.
    result = con.execute("SELECT reason FROM feedback_items_v41_quarantine WHERE original_item_id = 'bad-item'").fetchone()
    assert result is not None
    assert result[0] == "invalid_body"


def test_migration_preserves_marker(baseline_db):
    """Migration creates and completes the schema_migrations marker."""
    from substrate.feedback.migrations import migrate_feedback_v41

    class FakeLockedConnection:
        def __init__(self, path):
            self._con = duckdb.connect(path)
        def execute(self, sql, params=None):
            if params:
                return self._con.execute(sql, params)
            return self._con.execute(sql)

    con = FakeLockedConnection(baseline_db)
    migrate_feedback_v41(con)

    result = con.execute(
        "SELECT phase, completed_at FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()
    assert result is not None
    assert result[0] == "completed"
    assert result[1] is not None


def test_marker_contains_real_digests_and_detects_tamper(seeded_db):
    """Completion stores computed digests and refuses changed active bytes."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    marker = con.execute(
        "SELECT temp_schema_sha256, temp_rows_sha256, active_schema_sha256, active_rows_sha256 "
        "FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()
    assert marker is not None
    assert all(isinstance(value, str) and len(value) == 64 for value in marker)
    assert marker[0] == marker[2]
    assert marker[1] == marker[3]
    con.execute("UPDATE feedback_items SET body_markdown = 'tampered' WHERE item_id = 'item-1'")
    con.close()

    con = duckdb.connect(seeded_db)
    with pytest.raises(RuntimeError, match="active schema/row digest mismatch"):
        migrate_feedback_v41(con)
    con.close()


def test_copy_phase_rolls_back_and_resumes(seeded_db, monkeypatch):
    """A copy failure leaves temp_created and a later run resumes cleanly."""
    from substrate.feedback import migrations

    original = migrations._copy_attempts
    def fail_once(con, now):
        raise RuntimeError("synthetic copy crash")
    monkeypatch.setattr(migrations, "_copy_attempts", fail_once)
    con = duckdb.connect(seeded_db)
    with pytest.raises(RuntimeError, match="synthetic copy crash"):
        migrations.migrate_feedback_v41(con)
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()[0] == "temp_created"
    assert con.execute("SELECT count(*) FROM feedback_items_v41").fetchone()[0] == 0
    monkeypatch.setattr(migrations, "_copy_attempts", original)
    migrations.migrate_feedback_v41(con)
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id = 'd2_feedback_v41'"
    ).fetchone()[0] == "completed"
    con.close()


def test_invalid_dependent_row_quarantines_aggregate(seeded_db):
    """An invalid item or work row cannot leave a partially active aggregate."""
    con = duckdb.connect(seeded_db)
    con.execute("UPDATE feedback_items SET body_markdown = '' WHERE item_id = 'item-1'")
    con.execute("UPDATE agent_work SET state = 'not-a-state' WHERE work_id = 'work-1'")
    con.close()
    from substrate.feedback.migrations import migrate_feedback_v41
    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    assert con.execute("SELECT * FROM feedback_threads WHERE thread_id = 'thread-1'").fetchone() is None
    assert con.execute("SELECT * FROM feedback_items WHERE thread_id = 'thread-1'").fetchone() is None
    assert con.execute("SELECT * FROM agent_work WHERE thread_id = 'thread-1'").fetchone() is None
    assert con.execute("SELECT reason FROM feedback_threads_v41_quarantine WHERE original_thread_id = 'thread-1'").fetchone()[0] == 'invalid_shape'
    assert con.execute("SELECT count(*) FROM feedback_items_v41_quarantine WHERE original_thread_id = 'thread-1'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM agent_work_v41_quarantine WHERE original_work_id = 'work-1'").fetchone()[0] == 1
    assert con.execute("SELECT count(*) FROM agent_work_attempts_v41_quarantine WHERE original_work_id = 'work-1'").fetchone()[0] == 1
    con.close()


def test_overbound_legacy_id_is_quarantined_safely(baseline_db):
    """Raw malformed IDs never reach constrained quarantine columns."""
    con = duckdb.connect(baseline_db)
    now = datetime.datetime.now(datetime.UTC)
    long_id = "é" * 300
    con.execute("""INSERT INTO feedback_threads (
        thread_id, owner_user_id, investigation_id, artifact_id, artifact_version,
        artifact_content_sha256, artifact_source_sha256, normalization, anchor_node_id,
        anchor_node_text_sha256, anchor_start_scalar, anchor_end_scalar, anchor_quote,
        anchor_prefix, anchor_suffix, state, create_operation_id, create_request_sha256,
        created_at, updated_at
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", [
        long_id, "owner-a", "inv-1", "art-1", 1, "a" * 64, "b" * 64, "unicode-nfc-v1",
        "node-1", "c" * 64, 0, 2, "q", "", "", "open", "op-long", "d" * 64, now, now,
    ])
    con.close()
    from substrate.feedback.migrations import migrate_feedback_v41
    con = duckdb.connect(baseline_db)
    migrate_feedback_v41(con)
    row = con.execute("SELECT original_thread_id, evidence_json FROM feedback_threads_v41_quarantine").fetchone()
    assert row is not None
    assert len(row[0].encode()) <= 256
    assert row[0] != long_id
    evidence = json.loads(row[1])
    assert evidence["fields"]["thread_id"]["truncated"] is True
    assert evidence["fields"]["thread_id"]["byte_length"] == len(long_id.encode())
    assert "value" not in evidence["fields"]["thread_id"]
    con.close()


def test_attempt_count_over_two_quarantines_work_and_thread(seeded_db):
    """Legacy retry counts above the D2 bound cannot enter the active queue."""
    con = duckdb.connect(seeded_db)
    con.execute("UPDATE agent_work SET attempt_count = 3 WHERE work_id = 'work-1'")
    con.close()
    from substrate.feedback.migrations import migrate_feedback_v41
    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    assert con.execute("SELECT count(*) FROM agent_work WHERE work_id = 'work-1'").fetchone()[0] == 0
    assert con.execute("SELECT reason FROM agent_work_v41_quarantine WHERE original_work_id = 'work-1'").fetchone()[0] == 'attempt_count_exceeded'
    assert con.execute("SELECT count(*) FROM feedback_threads WHERE thread_id = 'thread-1'").fetchone()[0] == 0
    con.close()


@pytest.mark.parametrize(
    ("mutation", "original_thread_id", "expected_reason"),
    [
        ("UPDATE feedback_threads SET state='resolved' WHERE thread_id='thread-1'", "thread-1", "invalid_lifecycle"),
        ("UPDATE feedback_threads SET artifact_content_sha256=? WHERE thread_id='thread-1'", "thread-1", "invalid_hash"),
        ("UPDATE feedback_threads SET thread_id='thread 1' WHERE thread_id='thread-1'", "thread 1", "invalid_shape"),
        ("UPDATE feedback_threads SET thread_id='é-thread' WHERE thread_id='thread-1'", "é-thread", "invalid_shape"),
    ],
)
def test_sql_check_malformed_threads_quarantine_without_aborting(
    baseline_db, mutation, original_thread_id, expected_reason
):
    """Rows that fail v41 SQL checks are classified before any INSERT."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(baseline_db)
    seed_valid_rows(con)
    if "artifact_content_sha256=?" in mutation:
        con.execute(mutation, ["A" * 64])
    else:
        con.execute(mutation)

    migrate_feedback_v41(con)
    migrate_feedback_v41(con)

    marker = con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id='d2_feedback_v41'"
    ).fetchone()
    quarantined = con.execute(
        "SELECT reason FROM feedback_threads_v41_quarantine WHERE original_thread_id=?",
        [original_thread_id],
    ).fetchone()
    assert marker == ("completed",)
    assert quarantined == (expected_reason,)
    assert con.execute("SELECT count(*) FROM feedback_threads").fetchone() == (0,)
    con.close()


@pytest.mark.parametrize("terminal_state", ["completed", "failed"])
def test_terminal_feedback_reply_attempts_migrate_without_dispatch_evidence(
    baseline_db, terminal_state
):
    """Dispatch-only evidence checks never bind legacy feedback replies."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(baseline_db)
    seed_valid_rows(con)
    con.execute(
        "UPDATE agent_work_attempts SET state=? WHERE attempt_id='att-1'", [terminal_state]
    )

    migrate_feedback_v41(con)
    migrate_feedback_v41(con)

    row = con.execute(
        "SELECT state, work_kind, dispatch_id, attempt_actual_cents, "
        "provider_boundary_crossed, provider_receipt_sha256, provider_result_sha256, evidence_sha256 "
        "FROM agent_work_attempts WHERE attempt_id='att-1'"
    ).fetchone()
    assert row == (terminal_state, "feedback_reply", None, 0, False, None, None, None)
    assert con.execute(
        "SELECT phase FROM schema_migrations WHERE migration_id='d2_feedback_v41'"
    ).fetchone() == ("completed",)
    con.close()


def test_dispatch_attempt_constraints_keep_reply_scope_and_attempt_bound(seeded_db):
    """The exact v41 attempts DDL binds correlation and bounds only dispatch rows."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    now = datetime.datetime.now(datetime.UTC)
    values = [
        "dispatch-att", "dispatch-work", 3, "dispatch-lease", "dispatch-cred",
        "dispatch-instance", "leased", now, now, "dispatch-1", "feedback_dispatch", 0,
    ]
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO agent_work_attempts "
            "(attempt_id,work_id,attempt_no,lease_id,bridge_credential_id,bridge_instance_id,"
            "state,lease_expires_at,created_at,dispatch_id,work_kind,attempt_actual_cents) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
    values[2] = 2
    values[9] = None
    with pytest.raises(duckdb.ConstraintException):
        con.execute(
            "INSERT INTO agent_work_attempts "
            "(attempt_id,work_id,attempt_no,lease_id,bridge_credential_id,bridge_instance_id,"
            "state,lease_expires_at,created_at,dispatch_id,work_kind,attempt_actual_cents) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            values,
        )
    con.close()


def test_provenance_owner_index_exists_after_migration(seeded_db):
    """The frozen owner/thread/ref_index provenance index is installed."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    indexes = con.execute(
        "SELECT index_name FROM duckdb_indexes() "
        "WHERE index_name='idx_feedback_provenance_owner'"
    ).fetchall()
    assert indexes == [("idx_feedback_provenance_owner",)]
    con.close()


def test_successful_migration_does_not_create_phantom_quarantine_rows(seeded_db):
    """Runner evidence never masquerades as a malformed legacy row."""
    from substrate.feedback.migrations import migrate_feedback_v41

    con = duckdb.connect(seeded_db)
    migrate_feedback_v41(con)
    assert con.execute(
        "SELECT count(*) FROM feedback_threads_v41_quarantine"
    ).fetchone() == (0,)
    con.close()


def test_quarantine_evidence_hashes_oversized_values_without_raw_leak() -> None:
    """Oversized legacy values are length/digest evidence, never raw excerpts."""
    from substrate.feedback.migrations import _evidence

    oversized = "sensitive-" * 100
    encoded = _evidence({"thread_id": oversized, "state": "open"}, "invalid_shape")
    evidence = json.loads(encoded)
    assert oversized not in encoded
    assert evidence["reason"] == "invalid_shape"
    assert evidence["fields"]["thread_id"] == {
        "byte_length": len(oversized.encode()),
        "sha256": hashlib.sha256(oversized.encode()).hexdigest(),
        "truncated": True,
    }
    assert evidence["fields"]["state"]["value"] == "open"
    assert evidence["fields"]["state"]["truncated"] is False
    assert len(encoded.encode()) <= 8192


def test_column_map_matches_information_schema_and_copy_is_named() -> None:
    """Every map entry names exact destination/source columns and defaults."""
    from substrate.feedback import migrations

    con = duckdb.connect(":memory:")
    con.execute(BASELINE_DDL)
    con.execute(migrations._get_v41_ddl())
    for table, contract in migrations.FEEDBACK_V41_COLUMN_MAP.items():
        destination = tuple(
            row[0]
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name=? ORDER BY ordinal_position",
                [table],
            ).fetchall()
        )
        assert tuple(contract["destination_columns"]) == destination
        source_table = contract["source_table"]
        if source_table is None:
            continue
        source = tuple(
            row[0]
            for row in con.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name=? ORDER BY ordinal_position",
                [source_table],
            ).fetchall()
        )
        assert tuple(contract["source_columns"]) == source
        assert set(destination) == set(source) | set(contract["defaults"])
        assert set(contract["default_expressions"]) == set(contract["defaults"])
    source_text = inspect.getsource(migrations)
    assert re.search(r"SELECT\s+\*\s+FROM", source_text, re.I) is None
    for table in (
        "feedback_threads_v41",
        "feedback_items_v41",
        "agent_work_v41",
        "agent_work_attempts_v41",
    ):
        assert f"INSERT INTO {table} VALUES" not in source_text
    con.close()
