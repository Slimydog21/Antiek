"""Tests for ByotUsageLedger — per-key usage accumulation and limits.

Verifies:
- record_settlement increments used_cents
- set_limit stores and clears limits
- snapshot / key_usage return correct rows
- would_exceed respects limits
"""

from __future__ import annotations

from pathlib import Path

from substrate.byot_usage.ledger import ByotUsageLedger


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
    assert ledger.would_exceed("key-1", 100) is False
    # 800 + 300 = 1100 > 1000 → exceeds
    assert ledger.would_exceed("key-1", 300) is True


def test_would_exceed_no_limit_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 100, "a" * 64)
    assert ledger.would_exceed("key-1", 9999) is None


def test_would_exceed_unknown_key_returns_none(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    assert ledger.would_exceed("nonexistent", 100) is None


def test_remaining_cents_property(tmp_path: Path) -> None:
    db = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(db)

    ledger.record_settlement("key-1", "user-A", 700, "a" * 64)
    ledger.set_limit("key-1", "user-A", 1000)

    row = ledger.key_usage("key-1", "user-A")
    assert row is not None
    assert row.remaining_cents == 300


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
