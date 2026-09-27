"""An unmetered successful answer must not become a settled zero charge."""

from __future__ import annotations

from pathlib import Path

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
