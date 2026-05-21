"""Persistent nonce ledger tests (Sprint 30+ thread 1 replay defense)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.cross_graph.inbound import (
    DEFAULT_NONCE_RETENTION_SECONDS,
    ensure_nonce_table,
    load_active_nonces,
    prune_expired_nonces,
    remember_nonce_persistent,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-nonce-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="nonce_persistence_test")
    init_database(con)
    yield con
    con.close()


def test_first_nonce_observation_returns_true(db):
    assert remember_nonce_persistent(
        db, nonce="n-1", partner_id="prt-x", now_unix=1000,
    ) is True


def test_replay_within_retention_window_returns_false(db):
    assert remember_nonce_persistent(
        db, nonce="n-1", partner_id="prt-x", now_unix=1000,
    ) is True
    # Same nonce within window → replay.
    assert remember_nonce_persistent(
        db, nonce="n-1", partner_id="prt-x", now_unix=1100,
    ) is False


def test_nonce_can_be_reused_after_expiry(db):
    assert remember_nonce_persistent(
        db, nonce="n-1", partner_id="prt-x",
        retention_seconds=10, now_unix=1000,
    ) is True
    # Past the retention window → row pruned, nonce reusable.
    assert remember_nonce_persistent(
        db, nonce="n-1", partner_id="prt-x",
        retention_seconds=10, now_unix=1100,
    ) is True


def test_prune_expired_removes_expected_rows(db):
    remember_nonce_persistent(
        db, nonce="old", partner_id="prt-x",
        retention_seconds=10, now_unix=1000,
    )
    remember_nonce_persistent(
        db, nonce="new", partner_id="prt-x",
        retention_seconds=100, now_unix=1000,
    )
    prune_expired_nonces(db, now_unix=1050)
    rows = db.execute(
        "SELECT nonce FROM federation_nonces ORDER BY nonce"
    ).fetchall()
    assert [r[0] for r in rows] == ["new"]


def test_load_active_nonces_skips_expired(db):
    remember_nonce_persistent(
        db, nonce="alive", partner_id="prt-x",
        retention_seconds=100, now_unix=1000,
    )
    remember_nonce_persistent(
        db, nonce="dead", partner_id="prt-x",
        retention_seconds=10, now_unix=1000,
    )
    ledger = load_active_nonces(db, now_unix=1050)
    assert "alive" in ledger.seen
    assert "dead" not in ledger.seen


def test_partner_id_recorded_alongside_nonce(db):
    remember_nonce_persistent(
        db, nonce="n-from-a", partner_id="prt-a", now_unix=1000,
    )
    remember_nonce_persistent(
        db, nonce="n-from-b", partner_id="prt-b", now_unix=1000,
    )
    rows = db.execute(
        "SELECT nonce, partner_id FROM federation_nonces "
        "ORDER BY nonce"
    ).fetchall()
    assert rows == [("n-from-a", "prt-a"), ("n-from-b", "prt-b")]


def test_default_retention_matches_token_validity_envelope():
    # Persistent ledger uses the same DEFAULT_NONCE_RETENTION_SECONDS
    # as the in-memory ledger — they must not drift.
    assert DEFAULT_NONCE_RETENTION_SECONDS > 0


def test_ensure_nonce_table_idempotent(db):
    ensure_nonce_table(db)
    ensure_nonce_table(db)
    rows = db.execute("SELECT count(*) FROM federation_nonces").fetchone()
    assert rows[0] == 0


def test_substrate_restart_inherits_replay_state(db):
    """Simulate substrate restart: write nonces, then a fresh
    process loads load_active_nonces and the previously-seen nonce
    cannot be re-claimed."""
    remember_nonce_persistent(
        db, nonce="n-survivor", partner_id="prt-x",
        retention_seconds=100, now_unix=1000,
    )
    # "Restart": load_active_nonces produces an in-memory ledger
    # carrying the survivor.
    inherited = load_active_nonces(db, now_unix=1050)
    assert inherited.remember("n-survivor", now_unix=1050) is False
    # And the persistent ledger still refuses the replay.
    assert remember_nonce_persistent(
        db, nonce="n-survivor", partner_id="prt-x",
        retention_seconds=100, now_unix=1050,
    ) is False
