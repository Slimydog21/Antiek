from __future__ import annotations

import pytest

from runtime.db_lock import connect_write
from substrate.engagement_spine.store import InMemoryEngagementStore
from substrate.engagement_spine.twin_promotion_receipt import (
    claim_promotion_receipt,
    promotion_preview_sha256,
    settle_promotion_receipt,
)
from substrate.graph import ensure_initialized
from substrate.graph.promotion_outbox import (
    ensure_promotion_outbox,
    flush_promotion_outbox,
    stage_promoted_node_event,
)


def test_preview_revision_is_owner_session_and_content_bound() -> None:
    payload = {
        "promoted": [
            {
                "twin_note_id": "twin_1",
                "graph_node_id": "insight_1",
                "kind": "insight",
                "text": "Private finding",
                "canonical_text": "private finding",
                "asset_id": "asset",
                "investigation_id": "inv",
            }
        ]
    }
    alice = promotion_preview_sha256(
        owner_id="alice", session_id="fsess_a", payload=payload
    )
    assert alice == promotion_preview_sha256(
        owner_id="alice", session_id="fsess_a", payload=payload
    )
    assert alice != promotion_preview_sha256(
        owner_id="bob", session_id="fsess_a", payload=payload
    )
    assert alice != promotion_preview_sha256(
        owner_id="alice", session_id="fsess_b", payload=payload
    )


def test_receipt_claim_conflict_and_exact_applied_replay() -> None:
    store = InMemoryEngagementStore()
    material = {"session_id": "fsess_a", "promotion_preview_sha256": "a" * 64}
    claimed, created = claim_promotion_receipt(
        store=store,
        owner_id="alice",
        idempotency_key="confirm-key-001",
        material=material,
    )
    assert created is True
    replay, replay_created = claim_promotion_receipt(
        store=store,
        owner_id="alice",
        idempotency_key="confirm-key-001",
        material=material,
    )
    assert replay_created is False
    assert replay["receipt_id"] == claimed["receipt_id"]

    result = {"graph_node_ids": ["insight_1"], "graph_write": True}
    applied = settle_promotion_receipt(
        store=store,
        owner_id="alice",
        receipt_id=claimed["receipt_id"],
        material_sha256=claimed["material_sha256"],
        result=result,
    )
    assert applied["state"] == "applied"
    replay_applied = settle_promotion_receipt(
        store=store,
        owner_id="alice",
        receipt_id=claimed["receipt_id"],
        material_sha256=claimed["material_sha256"],
        result=result,
    )
    assert replay_applied == applied

    with pytest.raises(ValueError, match="different twin promotion material"):
        claim_promotion_receipt(
            store=store,
            owner_id="alice",
            idempotency_key="confirm-key-001",
            material={**material, "promotion_preview_sha256": "b" * 64},
        )


def test_same_idempotency_key_is_owner_namespaced() -> None:
    store = InMemoryEngagementStore()
    material = {"promotion_preview_sha256": "a" * 64}
    alice, _ = claim_promotion_receipt(
        store=store,
        owner_id="alice",
        idempotency_key="shared-key-001",
        material=material,
    )
    bob, _ = claim_promotion_receipt(
        store=store,
        owner_id="bob",
        idempotency_key="shared-key-001",
        material=material,
    )
    assert alice["receipt_id"] != bob["receipt_id"]


def test_graph_event_outbox_recovery_does_not_duplicate_append(tmp_path) -> None:
    db_path = ensure_initialized(str(tmp_path / "owner.duckdb"))
    events_dir = str(tmp_path / "events")
    con = connect_write(db_path, purpose="test_promotion_outbox")
    try:
        ensure_promotion_outbox(con)
        stage_promoted_node_event(
            con,
            event_id="evt-tpr-1234567890abcdef12345678",
            investigation_id="inv-outbox",
            node_id="insight-abc",
            canonical_label="Outbox insight",
            node_type="insight",
            has_embedding=True,
        )
    finally:
        con.close()
    assert flush_promotion_outbox(db_path, events_dir=events_dir) == 1

    # Simulate append succeeding immediately before a crash prevented the
    # delivered flag from committing. Deterministic event identity suppresses
    # a second JSONL row on recovery.
    con = connect_write(db_path, purpose="test_promotion_outbox_recovery")
    try:
        con.execute("UPDATE twin_promotion_event_outbox SET emitted = FALSE")
    finally:
        con.close()
    assert flush_promotion_outbox(db_path, events_dir=events_dir) == 1
    lines = (tmp_path / "events" / "inv-outbox.jsonl").read_text().splitlines()
    assert len(lines) == 1
