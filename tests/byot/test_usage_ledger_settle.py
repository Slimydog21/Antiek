"""Tests for ByotUsageLedger — per-key usage accumulation and limits.

Verifies:
- record_settlement increments used_cents
- set_limit stores and clears limits
- snapshot / key_usage return correct rows
- would_exceed respects limits
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict


def test_record_settlement_increments_used_cents(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 500, "a" * 64)
    ledger.record_settlement("key-1", "user-A", 300, "b" * 64)

    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.used_cents == 800
    assert row.owner_user_id == "user-A"
    assert row.last_settled_at is not None


def test_record_settlement_separates_keys_and_users(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 100, "a" * 64)
    ledger.record_settlement("key-2", "user-A", 200, "b" * 64)
    ledger.record_settlement("key-1", "user-B", 300, "c" * 64)

    assert ledger.key_usage("key-1", "user-A").used_cents == 100  # type: ignore[union-attr]
    assert ledger.key_usage("key-2", "user-A").used_cents == 200  # type: ignore[union-attr]
    assert ledger.key_usage("key-1", "user-B").used_cents == 300  # type: ignore[union-attr]


def test_set_limit_stores_and_clears(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 100, "a" * 64)
    ledger.set_limit("key-1", "user-A", 1000)

    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.limit_cents == 1000

    # Clear the limit
    ledger.set_limit("key-1", "user-A", None)
    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.limit_cents is None


def test_snapshot_returns_all_keys_for_user(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 100, "a" * 64)
    ledger.record_settlement("key-2", "user-A", 200, "b" * 64)
    ledger.record_settlement("key-3", "user-B", 300, "c" * 64)

    rows = ledger.snapshot("user-A")
    assert len(rows) == 2
    assert all(r.owner_user_id == "user-A" for r in rows)
    ids = {r.api_key_id for r in rows}
    assert ids == {"key-1", "key-2"}


def test_would_exceed_with_limit(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 800, "a" * 64)
    ledger.set_limit("key-1", "user-A", 1000)

    # 800 + 100 = 900 <= 1000 → does not exceed
    assert ledger.would_exceed("key-1", "user-A", 100) is False
    # 800 + 300 = 1100 > 1000 → exceeds
    assert ledger.would_exceed("key-1", "user-A", 300) is True


def test_would_exceed_no_limit_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 100, "a" * 64)
    assert ledger.would_exceed("key-1", "user-A", 9999) is None


def test_would_exceed_unknown_key_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    assert ledger.would_exceed("nonexistent", "user-A", 100) is None


def test_would_exceed_is_scoped_per_owner(tmp_path: Path) -> None:
    # Same api_key_id, two different owners with different caps.  The
    # composite primary key allows this; would_exceed must read only the
    # requesting owner's row, never the other owner's cap.
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("shared-id", "user-A", 900, "a" * 64)
    ledger.set_limit("shared-id", "user-A", 1000)  # A: 100 headroom
    ledger.record_settlement("shared-id", "user-B", 100, "b" * 64)
    ledger.set_limit("shared-id", "user-B", 5000)  # B: 4900 headroom

    # A projection of 200 exceeds A's cap (900+200 > 1000)…
    assert ledger.would_exceed("shared-id", "user-A", 200) is True
    # …but comfortably fits within B's cap (100+200 <= 5000).
    assert ledger.would_exceed("shared-id", "user-B", 200) is False


def test_remaining_cents_property(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 700, "a" * 64)
    ledger.set_limit("key-1", "user-A", 1000)

    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.remaining_cents == 300


def test_operation_journal_reserves_and_settles_exactly_once(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit("key-1", "owner", 10)
    ledger.prepare_operation("key-1", "owner", "op-1", 8, "a" * 64)
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("key-1", "owner", "op-2", 3, "b" * 64)
    ledger.mark_operation_sent("owner", "op-1")
    ledger.record_operation_result(
        "owner", "op-1", actual_cents=2, evidence_sha256="c" * 64,
        dispatch_event_id="evt-1", provider_id="provider", model_id="model",
    )
    ledger.settle_operation("owner", "op-1", 2, "c" * 64)
    assert ledger.operation("owner", "op-1").state == "settled"  # type: ignore[union-attr]
    assert ledger.key_usage("key-1", "owner").used_cents == 2  # type: ignore[union-attr]
    with pytest.raises(OperationConflict):
        ledger.settle_operation("owner", "op-1", 2, "c" * 64)
    assert ledger.key_usage("key-1", "owner").used_cents == 2  # type: ignore[union-attr]


def test_sent_or_unknown_operation_is_never_blindly_replayed(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.prepare_operation("key-1", "owner", "op-1", 8, "a" * 64)
    ledger.mark_operation_sent("owner", "op-1")
    ledger.mark_operation_unknown("owner", "op-1")
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("key-1", "owner", "op-1", 8, "a" * 64)
    assert ledger.operation("owner", "op-1").state == "unknown"  # type: ignore[union-attr]


def test_operation_identity_cannot_be_rebound(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.prepare_operation("key-1", "owner", "op-1", 8, "a" * 64)
    with pytest.raises(OperationConflict):
        ledger.prepare_operation("key-2", "owner", "op-1", 8, "a" * 64)


@pytest.mark.parametrize("state", ["prepared", "sent", "unknown"])
def test_usage_available_balance_subtracts_durable_holds(
    tmp_path: Path, state: str,
) -> None:
    ledger = ByotUsageLedger(tmp_path / f"{state}.sqlite3")
    ledger.set_limit("key", "owner", 20)
    ledger.prepare_operation("key", "owner", "op", 7, "a" * 64)
    if state != "prepared":
        ledger.mark_operation_sent("owner", "op")
    if state == "unknown":
        ledger.mark_operation_unknown("owner", "op")
    row = ledger.key_usage("key", "owner")
    assert row is not None
    assert row.held_cents == 7
    assert row.available_cents == 13


def test_cancelled_prepared_releases_hold_and_stale_cleanup_is_visible(tmp_path: Path) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    ledger.set_limit("key", "owner", 20)
    ledger.prepare_operation("key", "owner", "op", 7, "a" * 64)
    assert ledger.cancel_stale_prepared(
        owner_user_id="owner", now=datetime(9999, 12, 31, tzinfo=UTC),
    ) == 1
    operation = ledger.operation("owner", "op")
    assert operation is not None and operation.state == "cancelled"
    assert operation.created_at and operation.updated_at
    assert ledger.key_usage("key", "owner").held_cents == 0  # type: ignore[union-attr]


def test_remaining_cents_none_when_no_limit(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 700, "a" * 64)
    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.remaining_cents is None


def test_remaining_cents_clamps_at_zero(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 1500, "a" * 64)
    ledger.set_limit("key-1", "user-A", 1000)

    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.remaining_cents == 0


def test_record_settlement_rejects_negative(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    import pytest

    with pytest.raises(ValueError, match="non-negative"):
        ledger.record_settlement("key-1", "user-A", -1, "a" * 64)


def test_set_limit_rejects_negative(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    import pytest

    with pytest.raises(ValueError, match="non-negative"):
        ledger.set_limit("key-1", "user-A", -100)


def test_record_settlement_rejects_empty_ids(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    import pytest

    with pytest.raises(ValueError, match="non-empty"):
        ledger.record_settlement("", "user-A", 100, "a" * 64)
    with pytest.raises(ValueError, match="non-empty"):
        ledger.record_settlement("key-1", "", 100, "a" * 64)
