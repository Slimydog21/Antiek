from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from runtime.research_runner import HostLocalRunner, ResearchPlan
from runtime.research_runner.reasoning_loop import ReasoningEvidence, run_research_reasoning
from substrate.context_pack import build_canonical_recursive_pack
from substrate.context_pack.recursive_feedback import (
    FeedbackUnitRef,
    FileRecursiveFeedbackStore,
    build_outcome_receipt,
)
from substrate.context_pack.recursive_ranking import (
    apply_advisory_ranking,
    build_ranking_snapshot,
)
from substrate.dispatch.base import NormalizedUsage
from substrate.engagement_spine import (
    InMemoryEngagementStore,
    record_twin_insight,
    record_twin_question,
)
from substrate.event_log import trajectory


def _recursive_pack():
    store = InMemoryEngagementStore()
    record_twin_question(
        "asset",
        "Which evidence would falsify the adoption thesis?",
        store=store,
    )
    return build_canonical_recursive_pack(
        store=store,
        owner_user_id="owner",
        asset_ids=["asset"],
        asset_owner=lambda _asset: "owner",
        goal="adoption thesis evidence",
    )


@pytest.mark.asyncio
async def test_host_runner_exposes_recursive_prompt_at_injected_loop_boundary():
    captured: list[str] = []

    async def loop(ctx):
        captured.append(ctx.prompt_prefix)
        yield ctx.plan_event("captured")

    runner = HostLocalRunner(
        loop,
        recursive_notes_provider=lambda _investigation_id, _plan: _recursive_pack(),
    )
    plan = ResearchPlan(
        investigation_id="inv-recursive-consumer",
        sub_question="Assess the adoption thesis",
    )
    await runner.start(plan.investigation_id, plan)
    await runner.join()

    assert len(captured) == 1
    assert "## recursive_notes: canonical_recursive_notes" in captured[0]
    recursive_json = captured[0][captured[0].index("{", captured[0].index("## recursive_notes")) :]
    recursive_json = recursive_json[: recursive_json.index("\n\n## session")]
    decoded = json.loads(recursive_json)
    assert decoded["units"][0]["text"] == (
        "Which evidence would falsify the adoption thesis?"
    )
    rows = trajectory(plan.investigation_id)
    pack_event = next(
        row for row in rows
        if row["action_type"] == "context_pack.assembled"
    )
    receipt = pack_event["payload"]["recursive_context"]
    assert receipt["included_units"][0]["unit_id"]
    assert "Which evidence" not in json.dumps(receipt)


@pytest.mark.asyncio
async def test_red_control_without_provider_has_no_recursive_context():
    captured: list[str] = []

    async def loop(ctx):
        captured.append(ctx.prompt_prefix)
        yield ctx.plan_event("captured")

    plan = ResearchPlan(
        investigation_id="inv-recursive-red",
        sub_question="Assess the adoption thesis",
    )
    runner = HostLocalRunner(loop)
    await runner.start(plan.investigation_id, plan)
    await runner.join()

    assert captured == [""]
    assert not any(
        row["action_type"] == "context_pack.assembled"
        and row["payload"].get("recursive_context") is not None
        for row in trajectory(plan.investigation_id)
    )


@pytest.mark.asyncio
async def test_required_recursive_provider_failure_is_not_silently_dropped():
    async def loop(ctx):
        yield ctx.plan_event("must not start")

    def broken_provider(_investigation_id, _plan):
        raise ValueError("canonical authority unavailable")

    plan = ResearchPlan(
        investigation_id="inv-recursive-required-failure",
        sub_question="Assess the adoption thesis",
    )
    runner = HostLocalRunner(loop, recursive_notes_provider=broken_provider)
    with pytest.raises(ValueError, match="canonical authority unavailable"):
        await runner.start(plan.investigation_id, plan)


@pytest.mark.asyncio
async def test_prior_research_insight_reaches_next_prompt_and_durable_ranking(tmp_path):
    """Close the recursive loop across the real pack, runner, and reasoner seams."""
    store = InMemoryEngagementStore()
    for text in (
        "Research A found that leadership support predicts adoption.",
        "Research A found that training quality predicts adoption.",
        "Research A found that workflow fit predicts adoption.",
        "Research A found that migration cost predicts adoption.",
    ):
        record_twin_insight("research-a", text, store=store)

    def build_pack():
        return build_canonical_recursive_pack(
            store=store,
            owner_user_id="owner",
            asset_ids=["research-a"],
            asset_owner=lambda _asset: "owner",
            goal="Which evidence changes the adoption thesis?",
            per_asset_limit=4,
        )

    baseline_pack = build_pack()
    target = baseline_pack.units[-1]
    feedback_store = FileRecursiveFeedbackStore(tmp_path / "feedback")
    provider_calls: list[dict[str, object]] = []

    def fake_dispatch(**kwargs):
        provider_calls.append(kwargs)
        investigation_id = str(kwargs["investigation_id"])
        return SimpleNamespace(
            text=(
                '{"insights":[{"text":"Migration cost remains decisive.",'
                '"source_document_ids":["doc-b"]}],"questions":[]}'
            ),
            usage=NormalizedUsage(input_tokens=40, output_tokens=10),
            cost_usd=0.01,
            event_id=f"dispatch-{investigation_id}",
        )

    async def loop(ctx):
        result = await run_research_reasoning(
            ctx,
            [
                ReasoningEvidence(
                    document_id="doc-b",
                    title="Research B evidence",
                    url="https://example.test/research-b",
                    snippet="Teams with lower migration costs adopted faster.",
                )
            ],
            dispatch_fn=fake_dispatch,
        )
        yield ctx.note(result.output.insights[0].text)

    for index in range(3):
        pack = build_pack()
        contexts = []

        async def observed_loop(ctx, captured_contexts=contexts):
            captured_contexts.append(ctx)
            async for event in loop(ctx):
                yield event

        investigation_id = f"research-b-{index}"
        plan = ResearchPlan(
            investigation_id=investigation_id,
            sub_question="Which evidence changes the adoption thesis?",
        )
        runner = HostLocalRunner(
            observed_loop,
            recursive_notes_provider=lambda _investigation_id, _plan, pack=pack: pack,
        )
        await runner.start(plan.investigation_id, plan)
        await runner.join()
        assert target.text in str(provider_calls[-1]["prompt"])
        assert provider_calls[-1]["context_pack_event_id"] == contexts[0].context_pack_event_id
        receipt = build_outcome_receipt(
            owner_user_id="owner",
            observation_id=f"explicit-save-{index}",
            context_pack_event_id=contexts[0].context_pack_event_id,
            dispatch_event_id=f"dispatch-{investigation_id}",
            units=[FeedbackUnitRef(unit_id=target.unit_id, text_digest=target.text_digest)],
            task_class="research_reasoning",
            model_policy_id="test/reasoner",
            outcome="saved",
            observed_at_ms=1_000 + index,
        )
        feedback_store.append("owner", receipt)

    snapshot = build_ranking_snapshot(
        owner_user_id="owner",
        task_class="research_reasoning",
        receipts=feedback_store.list("owner"),
        now_ms=2_000,
    )
    ranked_pack = apply_advisory_ranking(
        baseline_pack,
        owner_user_id="owner",
        snapshot=snapshot,
    )

    assert snapshot.features[0].unit_id == target.unit_id
    assert snapshot.features[0].sample_count == 3
    assert [unit.unit_id for unit in ranked_pack.units].index(target.unit_id) < len(
        baseline_pack.units
    ) - 1

    final_plan = ResearchPlan(
        investigation_id="research-b-ranked",
        sub_question="Which evidence changes the adoption thesis?",
    )
    final_runner = HostLocalRunner(
        loop,
        recursive_notes_provider=lambda _investigation_id, _plan: ranked_pack,
    )
    await final_runner.start(final_plan.investigation_id, final_plan)
    await final_runner.join()
    ranked_prompt = str(provider_calls[-1]["prompt"])
    unit_after_target = baseline_pack.units[-2]
    assert ranked_prompt.index(target.text) < ranked_prompt.index(unit_after_target.text)
