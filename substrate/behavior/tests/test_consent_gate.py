"""Consent gate tests (SPR-01 M4 verification gate).

Asserts:
- Default state is no consent.
- Granting flips the gate; emit succeeds and writes a row.
- Revoking flips it back; subsequent emit writes nothing.
- Re-granting after revoke works.
- The emit API returns an opaque event id even when consent is
  absent (no side-channel leak).
"""

from __future__ import annotations

import duckdb

from substrate.behavior import (
    BehaviorEventType,
    emit_behavior_event,
    grant_consent,
    is_consent_active,
    revoke_consent,
)
from substrate.behavior.consent import (
    CURRENT_CONSENT_VERSION,
    get_consent_state,
)


def _row_count(db_path: str, *, user_id: str = "__operator__") -> int:
    con = duckdb.connect(db_path)
    try:
        return int(
            con.execute(
                "SELECT COUNT(*) FROM behavior_events WHERE user_id = ?",
                [user_id],
            ).fetchone()[0]
        )
    finally:
        con.close()


def test_default_state_is_no_consent(behavior_db):
    assert is_consent_active("__operator__", db_path=behavior_db) is False
    state = get_consent_state("__operator__", db_path=behavior_db)
    assert state.granted is False
    assert state.is_active is False


def test_emit_without_consent_writes_no_row(behavior_db, behavior_queue):
    eid = emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-1"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    # Returned id is opaque + well-formed; consent state is NOT
    # leaked through the return value.
    assert eid.startswith("evt-")
    # Flush to give any (would-be) writes a chance to land.
    assert behavior_queue.flush(timeout_s=2.0) is True
    assert _row_count(behavior_db) == 0


def test_grant_then_emit_writes_a_row(behavior_db, behavior_queue):
    grant_consent("__operator__", db_path=behavior_db)
    assert is_consent_active("__operator__", db_path=behavior_db) is True

    eid = emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-2"},
        action={"reading_mode": "cozy"},
        queue=behavior_queue,
    )
    assert eid.startswith("evt-")
    assert behavior_queue.flush(timeout_s=2.0) is True
    assert _row_count(behavior_db) == 1


def test_revoke_then_emit_writes_no_row(behavior_db, behavior_queue):
    grant_consent("__operator__", db_path=behavior_db)
    revoke_consent("__operator__", db_path=behavior_db)
    assert is_consent_active("__operator__", db_path=behavior_db) is False

    emit_behavior_event(
        BehaviorEventType.HIGHLIGHT_CREATED,
        state={"document_id": "doc-3", "reading_mode": "researcher"},
        action={"start_offset": 0, "end_offset": 10},
        queue=behavior_queue,
    )
    assert behavior_queue.flush(timeout_s=2.0) is True
    assert _row_count(behavior_db) == 0


def test_opt_out_then_in_then_emit_writes_a_row(behavior_db, behavior_queue):
    """Spec acceptance: opt-out → emit → no row → opt-back-in →
    emit → row written."""
    grant_consent("__operator__", db_path=behavior_db)
    revoke_consent("__operator__", db_path=behavior_db)

    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-revoked"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    behavior_queue.flush(timeout_s=2.0)
    assert _row_count(behavior_db) == 0

    # Opt back in
    grant_consent("__operator__", db_path=behavior_db)
    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-regranted"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    behavior_queue.flush(timeout_s=2.0)
    assert _row_count(behavior_db) == 1


def test_revoke_does_not_delete_existing_rows(behavior_db, behavior_queue):
    """Locked privacy policy 2026-05-21: delete future events on
    opt-out; trained models (and historical rows) persist."""
    grant_consent("__operator__", db_path=behavior_db)
    emit_behavior_event(
        BehaviorEventType.HIGHLIGHT_CREATED,
        state={"document_id": "doc-keep", "reading_mode": "researcher"},
        action={"start_offset": 0, "end_offset": 10},
        queue=behavior_queue,
    )
    assert behavior_queue.flush(timeout_s=2.0) is True
    assert _row_count(behavior_db) == 1

    # Revoke
    revoke_consent("__operator__", db_path=behavior_db)
    # Existing row MUST still be present.
    assert _row_count(behavior_db) == 1


def test_consent_version_recorded_on_emit(behavior_db, behavior_queue):
    grant_consent("__operator__", db_path=behavior_db)
    emit_behavior_event(
        BehaviorEventType.DOCUMENT_OPENED,
        state={"document_id": "doc-v"},
        action={"reading_mode": "researcher"},
        queue=behavior_queue,
    )
    behavior_queue.flush(timeout_s=2.0)
    con = duckdb.connect(behavior_db, read_only=True)
    try:
        version = con.execute(
            "SELECT consent_version FROM behavior_events LIMIT 1"
        ).fetchone()[0]
    finally:
        con.close()
    assert version == CURRENT_CONSENT_VERSION
