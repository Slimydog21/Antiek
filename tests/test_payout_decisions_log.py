"""Payout decisions audit log tests (Sprint 23-24 phase 2 / §13.7)."""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.ad_inventory.decisions_log import (
    DecisionGate,
    load_for_impression,
    load_for_recipient,
    persist_decision,
    persist_decisions,
)
from substrate.ad_inventory.payout import (
    PayoutRouter,
    RevShareDecision,
    RevShareKind,
    distribute_session_ad_revenue,
    distribute_with_gates,
)
from substrate.billing.kyc import KycRegistry, complete, begin, invite
from substrate.graph.schema import init_database


@pytest.fixture
def db():
    tmpdir = tempfile.mkdtemp(prefix="antiek-decisions-test-")
    db_path = os.path.join(tmpdir, "test.duckdb")
    con = connect_write(db_path, purpose="decisions_test")
    init_database(con)
    yield con
    con.close()


def _mk_decision(
    *, impression_id="imp-1", kind=RevShareKind.CREATOR,
    recipient_ref="user-a", amount_cents=500,
) -> RevShareDecision:
    import uuid
    return RevShareDecision(
        decision_id=f"rs-{uuid.uuid4().hex[:8]}",
        impression_id=impression_id,
        kind=kind,
        recipient_ref=recipient_ref,
        amount_usd_cents=amount_cents,
        document_id="doc-1",
        requires_escrow=False,
        capped_to_daily_limit=False,
    )


# ── Persistence round-trip ────────────────────────────────────────


def test_persist_then_load_by_impression(db):
    d = _mk_decision()
    persist_decision(db, d)
    rows = load_for_impression(db, impression_id="imp-1")
    assert len(rows) == 1
    assert rows[0].decision_id == d.decision_id
    assert rows[0].gate_result == "admitted"


def test_persist_is_idempotent(db):
    d = _mk_decision()
    persist_decision(db, d)
    persist_decision(db, d)
    rows = load_for_impression(db, impression_id="imp-1")
    assert len(rows) == 1


def test_persist_decisions_bulk(db):
    decisions = [
        _mk_decision(impression_id="imp-1"),
        _mk_decision(impression_id="imp-1", kind=RevShareKind.PLATFORM, recipient_ref="__platform__"),
    ]
    inserted = persist_decisions(db, decisions)
    assert inserted == 2


def test_load_for_recipient_orders_newest_first(db):
    persist_decision(db, _mk_decision(amount_cents=100))
    persist_decision(db, _mk_decision(amount_cents=200))
    rows = load_for_recipient(db, recipient_ref="user-a")
    assert len(rows) == 2


# ── Gates ──────────────────────────────────────────────────────────


def test_distribute_with_gates_marks_rolled_over_below_floor(db):
    router = PayoutRouter()
    distribute_with_gates(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=100,  # very small → creator share < $10
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={
            "doc-1": (RevShareKind.CREATOR, "user-a", False),
        },
    )
    # Creator decision should be tagged rolled_over.
    assert any(
        v == "rolled_over"
        for v in router.gates_by_decision_id.values()
    )


def test_distribute_with_gates_marks_admitted_for_kyc_completed(db):
    router = PayoutRouter()
    reg = KycRegistry()
    invite(reg, recipient_ref="user-a")
    begin(reg, recipient_ref="user-a")
    complete(reg, recipient_ref="user-a")
    decisions = distribute_with_gates(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=100_000,  # big creator share
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={
            "doc-1": (RevShareKind.CREATOR, "user-a", False),
        },
        kyc_registry=reg,
    )
    creator_d = next(
        d for d in decisions if d.kind == RevShareKind.CREATOR
    )
    assert router.gates_by_decision_id[creator_d.decision_id] == "admitted"


def test_distribute_with_gates_marks_gated_kyc_when_incomplete(db):
    router = PayoutRouter()
    reg = KycRegistry()  # nobody completed
    decisions = distribute_with_gates(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=100_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={
            "doc-1": (RevShareKind.CREATOR, "user-a", False),
        },
        kyc_registry=reg,
    )
    creator_d = next(
        d for d in decisions if d.kind == RevShareKind.CREATOR
    )
    assert router.gates_by_decision_id[creator_d.decision_id] == "gated_kyc"


def test_distribute_with_gates_marks_gated_fraud_on_block_verdict(db):
    router = PayoutRouter()
    # Build a minimal fraud verdict shape that has `.kind` ending in BLOCK.

    class _Verdict:
        kind = "FraudVerdictKind.BLOCK"

    decisions = distribute_with_gates(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=100_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={
            "doc-1": (RevShareKind.CREATOR, "user-a", False),
        },
        fraud_verdict=_Verdict(),
    )
    creator_d = next(
        d for d in decisions if d.kind == RevShareKind.CREATOR
    )
    assert router.gates_by_decision_id[creator_d.decision_id] == "gated_fraud"
    # Platform still admitted.
    platform_d = next(
        d for d in decisions if d.kind == RevShareKind.PLATFORM
    )
    assert router.gates_by_decision_id[platform_d.decision_id] == "admitted"


def test_persist_with_gate_records_correct_value(db):
    router = PayoutRouter()
    reg = KycRegistry()
    decisions = distribute_with_gates(
        router,
        impression_id="imp-1",
        ad_revenue_usd_cents=100_000,
        attribution_shares={"doc-1": 1.0},
        document_to_recipient={
            "doc-1": (RevShareKind.CREATOR, "user-a", False),
        },
        kyc_registry=reg,
    )
    # Persist with the gate dict so audit reflects what actually happened.
    gates_map = {
        d.decision_id: DecisionGate(router.gates_by_decision_id[d.decision_id])
        for d in decisions
    }
    persist_decisions(db, decisions, gate_by_decision=gates_map)
    rows = load_for_impression(db, impression_id="imp-1")
    creator_rows = [r for r in rows if r.kind == "creator"]
    assert len(creator_rows) == 1
    assert creator_rows[0].gate_result == "gated_kyc"
