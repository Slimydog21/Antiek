from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.context_pack.recursive_feedback import (
    MAX_RECEIPTS_PER_OWNER_DAY,
    FeedbackUnitRef,
    FileRecursiveFeedbackStore,
    build_outcome_receipt,
)


def _unit(index: int = 1) -> FeedbackUnitRef:
    return FeedbackUnitRef(unit_id=f"unit-{index}", text_digest=f"{index:064x}")


def _receipt(
    *,
    owner: str = "owner-a",
    observation: str = "observation-1",
    outcome: str = "saved",
    observed_at_ms: int = 1_000,
    context: str | None = None,
):
    return build_outcome_receipt(
        owner_user_id=owner,
        observation_id=observation,
        context_pack_event_id=context or f"event-context-{observation}",
        dispatch_event_id="event-dispatch-1",
        units=[_unit()],
        task_class="research_reasoning",
        model_policy_id="provider/model",
        outcome=outcome,
        observed_at_ms=observed_at_ms,
    )


def test_owner_isolation_idempotency_conflict_and_no_text(tmp_path):
    store = FileRecursiveFeedbackStore(tmp_path)
    receipt = _receipt()
    assert store.append("owner-a", receipt) == receipt
    assert store.append("owner-a", receipt) == receipt
    assert store.list("owner-a") == (receipt,)
    assert store.list("owner-b") == ()
    with pytest.raises(PermissionError, match="owner scope"):
        store.append("owner-b", receipt)
    conflict = replace(receipt, outcome="cited")
    with pytest.raises(ValueError, match="conflicts"):
        store.append("owner-a", conflict)
    digest_conflict = replace(
        _receipt(observation="observation-2"),
        units=(FeedbackUnitRef(unit_id="unit-1", text_digest="f" * 64),),
    )
    with pytest.raises(ValueError, match="digest conflicts"):
        store.append("owner-a", digest_conflict)
    encoded = next(tmp_path.glob("*.json")).read_text()
    assert "owner-a" not in encoded
    assert "prompt" not in encoded
    assert "private unit prose" not in encoded


def test_opt_out_deletes_receipts_and_rejects_future_feedback(tmp_path):
    store = FileRecursiveFeedbackStore(tmp_path)
    store.append("owner-a", _receipt())
    assert store.delete_and_opt_out("owner-a") == 1
    assert store.list("owner-a") == ()
    with pytest.raises(PermissionError, match="opted out"):
        store.append("owner-a", _receipt(observation="observation-2"))


def test_synthetic_signal_is_rejected_and_no_signal_is_explicit():
    with pytest.raises(ValueError, match="explicit user"):
        build_outcome_receipt(
            owner_user_id="owner-a",
            observation_id="synthetic-1",
            context_pack_event_id="event-context-1",
            dispatch_event_id=None,
            units=[_unit()],
            task_class="research_reasoning",
            model_policy_id="provider/model",
            outcome="saved",
            signal_source="synthetic",  # type: ignore[arg-type]
            observed_at_ms=1,
        )
    assert _receipt(outcome="no_signal").outcome == "no_signal"


def test_daily_rate_bound_rejects_poison_burst(tmp_path):
    store = FileRecursiveFeedbackStore(tmp_path)
    for index in range(MAX_RECEIPTS_PER_OWNER_DAY):
        store.append(
            "owner-a",
            _receipt(observation=f"observation-{index}", observed_at_ms=1_000),
        )
    with pytest.raises(ValueError, match="daily rate limit"):
        store.append(
            "owner-a",
            _receipt(observation="observation-overflow", observed_at_ms=1_000),
        )


def test_duplicate_semantic_signal_cannot_manufacture_samples(tmp_path):
    store = FileRecursiveFeedbackStore(tmp_path)
    store.append("owner-a", _receipt())
    with pytest.raises(ValueError, match="already recorded"):
        store.append(
            "owner-a",
            _receipt(
                observation="observation-2",
                context="event-context-observation-1",
            ),
        )

    with pytest.raises(ValueError, match="already recorded"):
        store.append(
            "owner-a",
            _receipt(
                observation="observation-3",
                context="event-context-observation-1",
                outcome="merged",
            ),
        )
