"""An unmetered successful answer must not become a settled zero charge."""

from __future__ import annotations

import sqlite3
from pathlib import Path
from uuid import uuid4

import pytest

from substrate.byot_usage.ledger import ByotUsageLedger, OperationConflict


def test_record_unknown_answer_holds_reservation_and_rejects_second_transition(
    tmp_path: Path,
) -> None:
    ledger = ByotUsageLedger(tmp_path / "usage.sqlite3")
    assert ledger.key_usage("key-a", "owner-a") is None
    ledger.prepare_operation("key-a", "owner-a", "quick-ask:one", 7, "a" * 64)
    first_use = ledger.key_usage("key-a", "owner-a")
    assert first_use is not None and first_use.held_cents == 7
    assert [(row.api_key_id, row.held_cents) for row in ledger.snapshot("owner-a")] == [
        ("key-a", 7),
    ]
    ledger.mark_operation_sent("owner-a", "quick-ask:one")
    ledger.record_unknown_result(
        "owner-a", "quick-ask:one", result_text="the answer",
        dispatch_event_id="evt-one", provider_id="key-a", model_id="model-a",
    )
    row = ledger.operation("owner-a", "quick-ask:one")
    assert row is not None
    assert (row.state, row.result_text, row.provider_id, row.model_id) == (
        "unknown", "the answer", "key-a", "model-a",
    )
    assert row.actual_cents is None and row.evidence_sha256 is None
    usage = ledger.key_usage("key-a", "owner-a")
    assert usage is not None and usage.used_cents == 0 and usage.held_cents == 7
    with pytest.raises(OperationConflict):
        ledger.record_unknown_result(
            "owner-a", "quick-ask:one", result_text="second answer",
            dispatch_event_id="evt-two", provider_id="key-a", model_id="model-a",
        )
    assert ledger.operation("owner-a", "quick-ask:one").result_text == "the answer"


def test_v3_journal_migrates_nullable_replay_facts_and_binds_new_requests(
    tmp_path: Path,
) -> None:
    path = tmp_path / "old-ledger.sqlite3"
    con = sqlite3.connect(path)
    con.execute(
        "CREATE TABLE byot_usage_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
    )
    con.execute("INSERT INTO byot_usage_meta VALUES ('schema_version', '3')")
    con.execute(
        "CREATE TABLE byot_operation_journal ("
        "api_key_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,"
        "operation_id TEXT NOT NULL, state TEXT NOT NULL,"
        "reserved_cents INTEGER NOT NULL, actual_cents INTEGER,"
        "authority_digest TEXT NOT NULL, evidence_sha256 TEXT,"
        "provider_id TEXT, model_id TEXT, dispatch_event_id TEXT, result_text TEXT,"
        "created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
        "PRIMARY KEY (owner_user_id, operation_id))"
    )
    con.execute(
        "INSERT INTO byot_operation_journal"
        " (api_key_id, owner_user_id, operation_id, state, reserved_cents,"
        " authority_digest, created_at, updated_at)"
        " VALUES ('key-a', 'owner-a', 'quick-ask:legacy', 'prepared', 7, ?, 't', 't')",
        ("a" * 64,),
    )
    con.commit()
    con.close()

    ledger = ByotUsageLedger(path)
    old = ledger.operation("owner-a", "quick-ask:legacy")
    assert old is not None and old.request_digest is None and old.finish_reason is None
    assert old.quote_estimate_usd is None and old.cost_usd_estimate is None
    with pytest.raises(OperationConflict):
        ledger.prepare_operation(
            "key-a", "owner-a", "quick-ask:legacy", 7, "a" * 64,
            request_digest="b" * 64,
            quote_estimate_usd="0.001",
        )
    fresh = ledger.prepare_operation(
        "key-a", "owner-a", "quick-ask:new", 7, "a" * 64,
        request_digest="b" * 64,
        quote_estimate_usd="0.001",
    )
    assert fresh.request_digest == "b" * 64
    assert fresh.quote_estimate_usd == "0.001"
    with sqlite3.connect(path) as check:
        assert check.execute(
            "SELECT value FROM byot_usage_meta WHERE key = 'schema_version'"
        ).fetchone() == ("5",)


def test_v4_journal_keeps_existing_receipt_and_adds_nullable_precise_cost(
    tmp_path: Path,
) -> None:
    path = tmp_path / "v4-ledger.sqlite3"
    with sqlite3.connect(path) as con:
        con.execute(
            "CREATE TABLE byot_usage_meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)"
        )
        con.execute("INSERT INTO byot_usage_meta VALUES ('schema_version', '4')")
        con.execute(
            "CREATE TABLE byot_operation_journal ("
            "api_key_id TEXT NOT NULL, owner_user_id TEXT NOT NULL,"
            "operation_id TEXT NOT NULL, state TEXT NOT NULL,"
            "reserved_cents INTEGER NOT NULL, actual_cents INTEGER,"
            "authority_digest TEXT NOT NULL, evidence_sha256 TEXT,"
            "provider_id TEXT, model_id TEXT, dispatch_event_id TEXT, result_text TEXT,"
            "created_at TEXT NOT NULL, updated_at TEXT NOT NULL,"
            "request_digest TEXT, finish_reason TEXT,"
            "PRIMARY KEY (owner_user_id, operation_id))"
        )
        con.execute(
            "INSERT INTO byot_operation_journal"
            " (api_key_id, owner_user_id, operation_id, state, reserved_cents,"
            " actual_cents, authority_digest, evidence_sha256, provider_id, model_id,"
            " dispatch_event_id, result_text, created_at, updated_at,"
            " request_digest, finish_reason) VALUES"
            " ('key-a', 'owner-a', 'quick-ask:old', 'settled', 1, 1, ?, ?,"
            " 'key-a', 'model-a', 'evt-a', 'saved answer', 't', 't', ?, 'length')",
            ("a" * 64, "e" * 64, "r" * 64),
        )
    ledger = ByotUsageLedger(path)
    row = ledger.operation("owner-a", "quick-ask:old")
    assert row is not None
    assert (row.result_text, row.request_digest, row.finish_reason) == (
        "saved answer", "r" * 64, "length",
    )
    assert row.quote_estimate_usd is None and row.cost_usd_estimate is None


def test_recent_quick_ask_read_is_owner_scoped_bound_and_fixed_at_ten(
    tmp_path: Path,
) -> None:
    path = tmp_path / "usage.sqlite3"
    ledger = ByotUsageLedger(path)
    ids = [str(uuid4()) for _ in range(12)]
    for operation_id in ids:
        ledger.prepare_operation(
            "key-a", "owner-a", f"quick-ask:{operation_id}", 1,
            "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.01",
        )
        ledger.mark_operation_sent("owner-a", f"quick-ask:{operation_id}")
    legacy = str(uuid4())
    prepared = str(uuid4())
    foreign = str(uuid4())
    ledger.prepare_operation(
        "key-a", "owner-a", f"quick-ask:{legacy}", 1, "a" * 64,
    )
    ledger.mark_operation_sent("owner-a", f"quick-ask:{legacy}")
    ledger.prepare_operation(
        "key-a", "owner-a", f"quick-ask:{prepared}", 1,
        "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.01",
    )
    ledger.prepare_operation(
        "key-b", "owner-b", f"quick-ask:{foreign}", 1,
        "a" * 64, request_digest="b" * 64, quote_estimate_usd="0.01",
    )
    ledger.mark_operation_sent("owner-b", f"quick-ask:{foreign}")
    with sqlite3.connect(path) as con:
        con.execute(
            "UPDATE byot_operation_journal SET request_digest = ?"
            " WHERE owner_user_id = ? AND operation_id = ?",
            ("b" * 64, "owner-a", f"quick-ask:{legacy}"),
        )
        for index, operation_id in enumerate(ids):
            con.execute(
                "UPDATE byot_operation_journal SET created_at = ?"
                " WHERE owner_user_id = ? AND operation_id = ?",
                (f"2026-09-27T00:00:{index:02d}+00:00", "owner-a",
                 f"quick-ask:{operation_id}"),
            )
    rows = ByotUsageLedger(path, create=False).recent_quick_ask_operations("owner-a")
    assert [row.operation_id for row in rows] == [
        f"quick-ask:{operation_id}" for operation_id in reversed(ids[2:])
    ]
    assert len(rows) == 10
    assert all(row.owner_user_id == "owner-a" for row in rows)
    assert [row.operation_id for row in ledger.recent_quick_ask_operations("owner-b")] == [
        f"quick-ask:{foreign}",
    ]
    with pytest.raises(ValueError):
        ledger.recent_quick_ask_operations("")
