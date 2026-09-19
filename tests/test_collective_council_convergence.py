from __future__ import annotations

import pytest

from substrate.engagement_spine import record_twin_insight
from substrate.engagement_spine.collective_council import (
    council_result_sha256,
    run_approved_council,
)
from substrate.engagement_spine.council_convergence import apply_council_convergence
from tests.test_collective_council_execution import _approved_council, _Executor


def _completed(tmp_path, *, member_count=1):
    base, store, plan, ledger = _approved_council(
        tmp_path, member_count=member_count
    )
    execution = run_approved_council(
        plan.plan_id, store=store, ledger=ledger, executor=_Executor(plan)
    )
    row = store.get_document(execution.result_id)
    return base, store, plan, execution, council_result_sha256(row)


def test_offline_convergence_is_replayable_and_mutates_no_source(tmp_path) -> None:
    base, store, plan, execution, result_sha = _completed(tmp_path, member_count=2)
    documents_before = {
        key: value.copy()
        for key, value in base._docs.items()
        if value.get("kind") != "council_convergence"
    }

    decision = apply_council_convergence(
        store=store,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=result_sha,
        mode="offline_collective",
    )
    replay = apply_council_convergence(
        store=store,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=result_sha,
        mode="offline_collective",
    )

    assert decision == replay
    assert decision.merge_output["source_mutated"] is False
    assert decision.merge_output["view_format"] == "html"
    assert "prompt_block" in decision.merge_output
    assert {
        key: value
        for key, value in base._docs.items()
        if value.get("kind") != "council_convergence"
    } == documents_before


def test_draft_choice_leaves_parent_untouched_and_records_receipt(tmp_path) -> None:
    _base, store, plan, execution, result_sha = _completed(tmp_path)
    parent = plan.members[0].parent_asset_id
    store.put_document(parent, {"document_id": parent, "body_text": "Original"})

    decision = apply_council_convergence(
        store=store,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=result_sha,
        mode="draft_combined",
        parent_asset_id=parent,
    )

    assert decision.state == "complete"
    assert decision.merge_output["draft_leaves_parent"] is True
    assert decision.merge_output["canonical_committed"] is False
    assert store.get_document(parent)["body_text"] == "Original"
    assert store.get_document(decision.merge_output["document_id"])["mode"] == "draft_combined"


def test_parent_merge_requires_exact_hash_and_explicit_mode(tmp_path) -> None:
    base, store, plan, execution, result_sha = _completed(tmp_path)
    parent = plan.members[0].parent_asset_id
    before = set(base._docs)

    with pytest.raises(ValueError, match="changed after operator review"):
        apply_council_convergence(
            store=store,
            plan_id=plan.plan_id,
            result_id=execution.result_id,
            expected_result_sha256="0" * 64,
            mode="into_parent",
            parent_asset_id=parent,
        )
    assert set(base._docs) == before

    decision = apply_council_convergence(
        store=store,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=result_sha,
        mode="into_parent",
        parent_asset_id=parent,
    )
    assert decision.merge_output["mode"] == "into_parent"
    assert store.get_document(parent)["mode"] == "into_parent"


def test_only_selected_existing_twins_are_promoted(tmp_path) -> None:
    _base, store, plan, execution, result_sha = _completed(tmp_path)
    parent = plan.members[0].parent_asset_id
    selected = record_twin_insight(parent, "Selected finding", store=store)
    record_twin_insight(parent, "Unselected finding", store=store)
    promoted: list[str] = []

    def promote_insight(**kwargs):
        promoted.append(kwargs["text"])
        return "insight-selected"

    decision = apply_council_convergence(
        store=store,
        plan_id=plan.plan_id,
        result_id=execution.result_id,
        expected_result_sha256=result_sha,
        mode="offline_collective",
        parent_asset_id=parent,
        promotion_note_ids=[selected.note_id],
        promote_insight_fn=promote_insight,
        promote_question_fn=lambda **_kwargs: "unused",
    )

    assert promoted == ["Selected finding"]
    assert decision.promotion_output["promoted_count"] == 1
    assert decision.promotion_note_ids == (selected.note_id,)
