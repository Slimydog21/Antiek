from __future__ import annotations

import json

import pytest

from runtime.research_runner import HostLocalRunner, ResearchPlan
from substrate.context_pack import build_canonical_recursive_pack
from substrate.engagement_spine import InMemoryEngagementStore, record_twin_question
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
