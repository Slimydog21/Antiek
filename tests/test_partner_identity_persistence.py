"""Partner identity persistence tests (Sprint 30+ thread 1)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.cross_graph.partner_identity import (
    PartnerRegistry,
    PartnerTrustState,
    ensure_table,
    generate_shared_secret,
    load_registry,
    register_partner,
    revoke_partner,
    save_record,
    trust_partner,
)
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    """Initialized DuckDB at a tempfile with the V4 Phase 3 schema."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-partner-id-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="partner_identity_test")
    init_database(con)
    yield con
    con.close()


# ── ensure_table idempotent ───────────────────────────────────────


def test_ensure_table_is_idempotent(db):
    # init_database already ran; calling ensure_table again is a no-op.
    ensure_table(db)
    ensure_table(db)
    # Confirm the table exists.
    rows = db.execute(
        "SELECT count(*) FROM federation_partners"
    ).fetchone()
    assert rows[0] == 0


# ── Single-record round-trip ──────────────────────────────────────


def test_save_record_then_load_recovers_state(db):
    mem = PartnerRegistry()
    secret = generate_shared_secret()
    register_partner(
        mem,
        display_name="Partner Lab",
        substrate_url="https://lab.example",
        shared_secret_hex=secret,
        partner_id="prt-lab",
    )
    save_record(db, mem.records[-1])

    loaded = load_registry(db)
    rec = loaded.latest("prt-lab")
    assert rec is not None
    assert rec.display_name == "Partner Lab"
    assert rec.substrate_url == "https://lab.example"
    assert rec.shared_secret_hex == secret
    assert rec.state is PartnerTrustState.PENDING_HANDSHAKE


def test_full_state_machine_round_trips(db):
    mem = PartnerRegistry()
    register_partner(
        mem, display_name="P", substrate_url="https://p",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-p",
    )
    save_record(db, mem.records[-1])
    trust_partner(mem, partner_id="prt-p", operator_notes="vetted")
    save_record(db, mem.records[-1])
    revoke_partner(mem, partner_id="prt-p", revocation_reason="leak")
    save_record(db, mem.records[-1])

    loaded = load_registry(db)
    # Every state transition must be visible in the persisted log.
    states = [
        r.state for r in loaded.records if r.partner_id == "prt-p"
    ]
    assert states == [
        PartnerTrustState.PENDING_HANDSHAKE,
        PartnerTrustState.TRUSTED,
        PartnerTrustState.REVOKED,
    ]
    latest = loaded.latest("prt-p")
    assert latest is not None
    assert latest.state is PartnerTrustState.REVOKED
    assert latest.revocation_reason == "leak"


def test_save_record_is_idempotent(db):
    mem = PartnerRegistry()
    register_partner(
        mem, display_name="X", substrate_url="https://x",
        shared_secret_hex=generate_shared_secret(), partner_id="prt-x",
    )
    rec = mem.records[-1]
    a = save_record(db, rec)
    b = save_record(db, rec)  # second save of identical record → no-op
    assert a == b
    rows = db.execute(
        "SELECT count(*) FROM federation_partners WHERE partner_id = ?",
        ["prt-x"],
    ).fetchone()
    assert rows[0] == 1


def test_multiple_partners_loaded_in_audit_order(db):
    mem = PartnerRegistry()
    for pid in ("prt-z", "prt-a", "prt-m"):
        register_partner(
            mem, display_name=pid, substrate_url=f"https://{pid}",
            shared_secret_hex=generate_shared_secret(), partner_id=pid,
        )
        save_record(db, mem.records[-1])

    loaded = load_registry(db)
    # In-insertion order — matches the in-memory registry's records list.
    assert [r.partner_id for r in loaded.records] == ["prt-z", "prt-a", "prt-m"]


def test_load_empty_registry_returns_empty_registry(db):
    loaded = load_registry(db)
    assert loaded.records == []


def test_check_constraint_rejects_unknown_state(db):
    # SQL CHECK constraint must reject any state value the enum doesn't
    # know. This prevents schema drift from corrupting the registry.
    ensure_table(db)
    with pytest.raises(Exception):
        db.execute(
            """
            INSERT INTO federation_partners (
                attempt_id, partner_id, display_name, substrate_url,
                shared_secret_hex, state, registered_at, last_state_change_at
            ) VALUES (
                'bogus', 'prt-x', 'X', 'https://x', 'aa',
                'not_a_real_state', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
            )
            """
        )
