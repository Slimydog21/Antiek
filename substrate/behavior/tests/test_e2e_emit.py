"""End-to-end smoke tests for the Tier-1 behavior store (SPR-01 M7).

Exercises the full path: emit → validate → consent check → queue →
worker → row written → DP shuffler → export. The five tests below
mirror the spec's M7 acceptance list one-for-one.
"""

from __future__ import annotations

import random
import time

import duckdb
import pytest

from substrate.behavior import (
    BehaviorEventType,
    InvalidEventType,
    SchemaValidationError,
    emit_behavior_event,
    export_training_batch,
    grant_consent,
    revoke_consent,
)


def _row_count(db_path: str) -> int:
    # NOTE: We open WITHOUT read_only=True because DuckDB can't mix
    # read-only + read-write connections to the same file in one
    # process, and the queue worker (in another thread) holds the
    # writer. The test helper does no DDL or DML; it only counts.
    con = duckdb.connect(db_path)
    try:
        return int(
            con.execute("SELECT COUNT(*) FROM behavior_events").fetchone()[0]
        )
    finally:
        con.close()


def _seed_events(behavior_db: str, queue, n: int) -> None:
    """Helper for tests that need bulk data through the API. Note
    this exercises the full emit path (consent + queue), unlike the
    DP-test bulk helper which writes directly."""
    for i in range(n):
        emit_behavior_event(
            BehaviorEventType.HIGHLIGHT_CREATED,
            state={
                "document_id": f"doc-{i % 10}",
                "reading_mode": "researcher",
            },
            action={
                "start_offset": i * 10,
                "end_offset": i * 10 + 5,
            },
            queue=queue,
        )
    assert queue.flush(timeout_s=5.0) is True


def test_emit_with_consent_row_exists_within_2s(behavior_db, behavior_queue):
    """M7 Test 1: emit with consent → row exists within 2s."""
    grant_consent("__operator__", db_path=behavior_db)

    start = time.monotonic()
    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-2s"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )

    # Poll up to 2s. The queue's MAX_LATENCY_S is 0.5s so we expect
    # the row to land well before the deadline.
    deadline = start + 2.0
    while time.monotonic() < deadline:
        if _row_count(behavior_db) >= 1:
            break
        time.sleep(0.05)
    elapsed = time.monotonic() - start
    assert _row_count(behavior_db) == 1, (
        f"row not present within 2s (elapsed {elapsed:.2f}s)"
    )


def test_emit_without_consent_no_row_no_error(behavior_db, behavior_queue):
    """M7 Test 2: emit without consent → no row, no error."""
    # No grant_consent call.
    eid = emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-noconsent"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    assert eid.startswith("evt-")
    assert behavior_queue.flush(timeout_s=2.0) is True
    assert _row_count(behavior_db) == 0


def test_emit_invalid_event_type_raises(behavior_db, behavior_queue):
    """M7 Test 3: emit with invalid event type → InvalidEventType
    raised at API boundary."""
    grant_consent("__operator__", db_path=behavior_db)
    with pytest.raises(InvalidEventType):
        emit_behavior_event(
            "not_a_real_event_type",
            state={"document_id": "doc-x"},
            action={"reading_mode": "researcher"},
            queue=behavior_queue,
        )
    assert _row_count(behavior_db) == 0


def test_emit_invalid_payload_raises(behavior_db, behavior_queue):
    """Bonus: malformed state/action also raises at the boundary."""
    grant_consent("__operator__", db_path=behavior_db)
    # Missing required 'document_id' in state.
    with pytest.raises(SchemaValidationError):
        emit_behavior_event(
            BehaviorEventType.HIGHLIGHT_CREATED,
            state={"reading_mode": "researcher"},  # no document_id!
            action={"start_offset": 0, "end_offset": 5},
            queue=behavior_queue,
        )
    assert _row_count(behavior_db) == 0


def test_emit_1000_events_then_export_dp_perturbation(behavior_db, behavior_queue):
    """M7 Test 4: emit 1000 events → run export → DP shuffler
    perturbed the output within the documented epsilon."""
    grant_consent("__operator__", db_path=behavior_db)
    _seed_events(behavior_db, behavior_queue, n=1000)
    assert _row_count(behavior_db) == 1000

    rng = random.Random(7)
    result = export_training_batch(db_path=behavior_db, epsilon=1.0, rng=rng)
    assert result.row_count == 1000
    # The detailed quantitative gate (inversion rate, jitter std-dev)
    # is in test_dp_shuffler.py::test_perturbation_quantitative; here
    # we assert the structural invariants we'd notice if the export
    # path had regressed end-to-end.
    assert result.timestamp_jitter_max_s > 0.0
    assert result.epsilon == 1.0
    # All 1000 source rows stamped with the new batch id.
    con = duckdb.connect(behavior_db, read_only=True)
    try:
        unstamped = con.execute(
            "SELECT COUNT(*) FROM behavior_events "
            "WHERE dp_shuffler_batch_id IS NULL"
        ).fetchone()[0]
    finally:
        con.close()
    assert unstamped == 0


def test_revoke_then_emit_writes_no_row(behavior_db, behavior_queue):
    """M7 Test 5: revoke consent, then emit → no row."""
    grant_consent("__operator__", db_path=behavior_db)
    # First, emit one with consent → row.
    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-before-revoke"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    behavior_queue.flush(timeout_s=2.0)
    assert _row_count(behavior_db) == 1

    # Revoke + emit again → still only the first row.
    revoke_consent("__operator__", db_path=behavior_db)
    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-after-revoke"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    behavior_queue.flush(timeout_s=2.0)
    assert _row_count(behavior_db) == 1


def test_immediate_reward_worker_runs_against_emitted_data(behavior_db, behavior_queue):
    """Bonus: the M5 real worker runs end-to-end against rows we
    emit through the API. Covers the M5 "real implementation"
    acceptance ("it can run today against synthetic data because it
    only reads behavior events")."""
    from substrate.behavior.workers import run_reward_immediate_backfill

    grant_consent("__operator__", db_path=behavior_db)

    # One surfaced + one clicked within 5s, same session and link.
    surfaced_session = "sess-immediate"
    link_id = "link-42"
    emit_behavior_event(
        BehaviorEventType.CROSS_DOC_LINK_SURFACED,
        state={"document_id": "doc-a"},
        action={"link_id": link_id, "target_document_id": "doc-b"},
        session_id=surfaced_session,
        queue=behavior_queue,
    )
    # Tiny pause so the clicked row's timestamp is strictly later.
    time.sleep(0.05)
    emit_behavior_event(
        BehaviorEventType.CROSS_DOC_LINK_CLICKED,
        state={
            "document_id": "doc-a",
            "link_id": link_id,
        },
        action={"target_document_id": "doc-b"},
        session_id=surfaced_session,
        queue=behavior_queue,
    )
    assert behavior_queue.flush(timeout_s=2.0) is True

    result = run_reward_immediate_backfill(db_path=behavior_db)
    assert result.surfaced_inspected == 1
    assert result.rows_set_positive == 1
    assert result.rows_set_negative == 0
