from __future__ import annotations

from typing import Any

import pytest
from pydantic import ValidationError

from substrate.midnight_oil.stages import (
    StageEffectReceipt,
    StageKind,
    StagePlan,
    StagePlanItem,
    StageReceipt,
    StageState,
    dispatch_fence_sha256,
    effect_receipt_id,
    provider_effect_key,
    stage_key,
    stage_plan_hash,
)

OPERATION = "operation-1"
JOB = "job-1"
ROUTE_HASH = "a" * 64
INPUT_HASH = "b" * 64
OUTPUT_HASH = "c" * 64
CEILING_CENTS = 10_000


def _item(
    ordinal: int,
    kind: StageKind,
    *,
    goal: int = 0,
    shard: int | None = None,
    shard_count: int | None = None,
    predecessors: tuple[str, ...] = (),
) -> StagePlanItem:
    key = stage_key(
        operation_id=OPERATION,
        goal_index=goal,
        kind=kind,
        shard_index=shard,
    )
    return StagePlanItem(
        ordinal=ordinal,
        kind=kind,
        goal_index=goal,
        shard_index=shard,
        shard_count=shard_count,
        predecessor_stage_keys=predecessors,
        router_role="gatherer" if kind == "gather" else kind,
        route_plan_sha256=ROUTE_HASH,
        projected_max_cents=7,
        stage_key=key,
        provider_effect_key=provider_effect_key(key),
    )


def _stages(*, goals: int = 1, shards: int = 2) -> tuple[StagePlanItem, ...]:
    rows: list[StagePlanItem] = []
    for goal in range(goals):
        planner = _item(len(rows), "planner", goal=goal)
        rows.append(planner)
        gathers = tuple(
            _item(
                len(rows) + shard,
                "gather",
                goal=goal,
                shard=shard,
                shard_count=shards,
                predecessors=(planner.stage_key,),
            )
            for shard in range(shards)
        )
        rows.extend(gathers)
        verifier = _item(
            len(rows),
            "verifier",
            goal=goal,
            predecessors=tuple(row.stage_key for row in gathers),
        )
        rows.append(verifier)
        rows.append(
            _item(
                len(rows),
                "synthesizer",
                goal=goal,
                predecessors=(verifier.stage_key,),
            )
        )
    return tuple(rows)


def _plan(stages: tuple[StagePlanItem, ...] | None = None) -> StagePlan:
    rows = stages or _stages()
    return StagePlan(
        operation_id=OPERATION,
        job_id=JOB,
        approved_ceiling_cents=CEILING_CENTS,
        stages=rows,
        plan_hash=stage_plan_hash(
            operation_id=OPERATION,
            job_id=JOB,
            approved_ceiling_cents=CEILING_CENTS,
            stages=rows,
        ),
    )


def _receipt(state: StageState = "planned") -> StageReceipt:
    item = _stages(shards=1)[0]
    reserved: dict[str, Any] = {}
    returned: dict[str, Any] = {}
    if state != "planned":
        reserved = {
            "input_evidence_sha256": INPUT_HASH,
            "budget_hold_id": "hold-1",
            "dispatch_fence_sha256": dispatch_fence_sha256(
                stage=item.stage_key, lease_generation=3
            ),
            "lease_generation": 3,
            "reserved_at_ms": 10,
        }
    if state in {"returned", "settled"}:
        returned = {
            "effect_receipt_id": "d" * 64,
            "output_sha256": OUTPUT_HASH,
            "returned_at_ms": 12,
        }
    if state == "unknown":
        returned = {"unknown_at_ms": 12}
    if state == "settled":
        returned["settled_at_ms"] = 13
    return StageReceipt(
        operation_id=OPERATION,
        job_id=JOB,
        plan_hash=_plan(_stages(shards=1)).plan_hash,
        stage_key=item.stage_key,
        ordinal=item.ordinal,
        provider_effect_key=item.provider_effect_key,
        state=state,
        revision={
            "planned": 0,
            "reserved": 1,
            "unknown": 2,
            "returned": 2,
            "settled": 3,
        }[state],
        **reserved,
        **returned,
    )


def test_canonical_plan_commits_topology_routes_and_caps() -> None:
    plan = _plan()
    assert len(plan.stages) == 5
    changed = list(plan.stages)
    changed[1] = changed[1].model_copy(update={"projected_max_cents": 8})
    assert (
        stage_plan_hash(
            operation_id=OPERATION,
            job_id=JOB,
            approved_ceiling_cents=CEILING_CENTS,
            stages=tuple(changed),
        )
        != plan.plan_hash
    )
    with pytest.raises(ValidationError, match="plan_hash conflicts"):
        StagePlan(
            operation_id=OPERATION,
            job_id=JOB,
            approved_ceiling_cents=CEILING_CENTS,
            stages=tuple(changed),
            plan_hash=plan.plan_hash,
        )


def test_plan_caps_cannot_exceed_approved_operation_ceiling() -> None:
    rows = _stages(shards=1)
    ceiling = sum(row.projected_max_cents for row in rows) - 1
    with pytest.raises(ValidationError, match="exceeds approved"):
        StagePlan(
            operation_id=OPERATION,
            job_id=JOB,
            approved_ceiling_cents=ceiling,
            stages=rows,
            plan_hash=stage_plan_hash(
                operation_id=OPERATION,
                job_id=JOB,
                approved_ceiling_cents=ceiling,
                stages=rows,
            ),
        )


def test_plan_enforces_causal_role_topology() -> None:
    rows = list(_stages())
    rows[-1] = rows[-1].model_copy(update={"predecessor_stage_keys": ()})
    with pytest.raises(ValidationError, match="synthesizer must depend"):
        _plan(tuple(rows))
    rows = list(_stages())
    rows[2], rows[1] = rows[1], rows[2]
    with pytest.raises(ValidationError, match="ordinals must be contiguous"):
        _plan(tuple(rows))


def test_gather_barrier_rejects_mixed_counts_and_missing_indexes() -> None:
    rows = list(_stages(shards=2))
    rows[2] = rows[2].model_copy(update={"shard_count": 3})
    with pytest.raises(ValidationError, match="share one shard_count"):
        _plan(tuple(rows))
    rows = list(_stages(shards=1))
    missing_key = stage_key(
        operation_id=OPERATION,
        goal_index=0,
        kind="gather",
        shard_index=1,
    )
    rows[1] = rows[1].model_copy(
        update={
            "shard_index": 1,
            "shard_count": 2,
            "stage_key": missing_key,
            "provider_effect_key": provider_effect_key(missing_key),
        }
    )
    rows[2] = rows[2].model_copy(update={"predecessor_stage_keys": (missing_key,)})
    with pytest.raises(ValidationError, match="cover every contiguous index"):
        _plan(tuple(rows))


def test_provider_effect_identity_is_injective_over_large_topology() -> None:
    stages = _stages(goals=25, shards=20)
    assert len({row.stage_key for row in stages}) == len(stages)
    assert len({row.provider_effect_key for row in stages}) == len(stages)
    _plan(stages)


def test_distinct_stages_cannot_share_provider_effect_identity() -> None:
    rows = list(_stages())
    with pytest.raises(ValidationError, match="provider_effect_key conflicts"):
        StagePlanItem(
            **{
                **rows[1].model_dump(),
                "provider_effect_key": rows[0].provider_effect_key,
            }
        )


def test_reserved_state_freezes_input_hold_and_lease_fence_before_dispatch() -> None:
    assert _receipt("reserved").input_evidence_sha256 == INPUT_HASH
    with pytest.raises(ValidationError, match="requires input, hold, and dispatch fence"):
        StageReceipt(**{**_receipt("reserved").model_dump(), "budget_hold_id": None})
    with pytest.raises(ValidationError, match="planned stage cannot"):
        StageReceipt(
            **{
                **_receipt("reserved").model_dump(),
                "state": "planned",
                "revision": 0,
            }
        )


def test_unknown_state_retains_pre_dispatch_authority_without_claiming_output() -> None:
    unknown = _receipt("unknown")
    assert unknown.budget_hold_id == "hold-1"
    assert unknown.effect_receipt_id is None
    with pytest.raises(ValidationError, match="unknown stage requires only"):
        StageReceipt(**{**unknown.model_dump(), "output_sha256": OUTPUT_HASH})
    with pytest.raises(ValidationError, match="unknown stage requires only"):
        StageReceipt(**{**unknown.model_dump(), "unknown_at_ms": 9})
    recovered = StageReceipt(
        **{
            **_receipt("returned").model_dump(),
            "revision": unknown.revision + 1,
        }
    )
    assert recovered.revision > unknown.revision


def test_returned_and_settled_states_bind_effect_and_output_receipts() -> None:
    returned = _receipt("returned")
    assert returned.effect_receipt_id == "d" * 64
    assert _receipt("settled").settled_at_ms == 13
    with pytest.raises(ValidationError, match="immutable effect and output"):
        StageReceipt(**{**returned.model_dump(), "output_sha256": None})
    with pytest.raises(ValidationError, match="cannot predate"):
        StageReceipt(**{**returned.model_dump(), "returned_at_ms": 9})


def test_typed_effect_receipt_is_content_addressed_and_closed() -> None:
    item = _stages(shards=1)[0]
    receipt = StageEffectReceipt(
        receipt_id=effect_receipt_id(
            stage_key=item.stage_key,
            provider_effect_key_value=item.provider_effect_key,
            kind="planner",
            output_schema="midnight-oil.planner-output/v1",
            output_sha256=OUTPUT_HASH,
            route_receipt_id="route-1",
            source_receipt_ids=(),
            provider_event_id="event-1",
        ),
        stage_key=item.stage_key,
        provider_effect_key=item.provider_effect_key,
        kind="planner",
        output_schema="midnight-oil.planner-output/v1",
        output_sha256=OUTPUT_HASH,
        route_receipt_id="route-1",
        source_receipt_ids=(),
        provider_event_id="event-1",
        returned_at_ms=12,
    )
    assert receipt.output_sha256 == OUTPUT_HASH
    replay = StageEffectReceipt(**{**receipt.model_dump(), "returned_at_ms": 99})
    assert replay.receipt_id == receipt.receipt_id
    with pytest.raises(ValidationError, match="output schema conflicts"):
        StageEffectReceipt(
            **{
                **receipt.model_dump(),
                "output_schema": "midnight-oil.gather-output/v1",
            }
        )
    with pytest.raises(ValidationError):
        StageEffectReceipt(**{**receipt.model_dump(), "raw_output": "secret"})
    with pytest.raises(ValidationError, match="outside bounded"):
        StageEffectReceipt(**{**receipt.model_dump(), "source_receipt_ids": ("x" * 513,)})


def test_dispatch_fence_is_bound_to_stage_and_lease_generation() -> None:
    first = _stages(shards=1)[0]
    second = _stages(shards=1)[1]
    assert dispatch_fence_sha256(stage=first.stage_key, lease_generation=1) != (
        dispatch_fence_sha256(stage=first.stage_key, lease_generation=2)
    )
    assert dispatch_fence_sha256(stage=first.stage_key, lease_generation=1) != (
        dispatch_fence_sha256(stage=second.stage_key, lease_generation=1)
    )
    with pytest.raises(ValidationError, match="dispatch fence conflicts"):
        StageReceipt(**{**_receipt("reserved").model_dump(), "lease_generation": 4})
