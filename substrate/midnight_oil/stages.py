"""Canonical plan and effect authority for durable Midnight Oil role stages."""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

StageKind = Literal["planner", "gather", "verifier", "synthesizer"]
StageState = Literal["planned", "reserved", "unknown", "returned", "settled"]
StageOutputSchema = Literal[
    "midnight-oil.planner-output/v1",
    "midnight-oil.gather-output/v1",
    "midnight-oil.verifier-output/v1",
    "midnight-oil.synthesizer-output/v1",
]

_HEX64 = r"^[0-9a-f]{64}$"
_STAGE_DOMAIN = b"antiek.midnight-oil.stage.v2\x00"
_EFFECT_DOMAIN = b"antiek.midnight-oil.stage-provider-effect.v1\x00"
_FENCE_DOMAIN = b"antiek.midnight-oil.stage-dispatch-fence.v1\x00"
_PLAN_DOMAIN = b"antiek.midnight-oil.stage-plan.v1\x00"


class _ClosedModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class StagePlanItem(_ClosedModel):
    """One immutable stage in the signed, closed execution topology."""

    ordinal: int = Field(ge=0, le=1_000_000)
    kind: StageKind
    goal_index: int = Field(ge=0, le=100_000)
    shard_index: int | None = Field(default=None, ge=0, le=100_000)
    shard_count: int | None = Field(default=None, ge=1, le=100_000)
    predecessor_stage_keys: tuple[str, ...] = ()
    router_role: str = Field(min_length=1, max_length=128)
    route_plan_sha256: str = Field(pattern=_HEX64)
    projected_max_cents: int = Field(ge=1)
    stage_key: str = Field(pattern=_HEX64)
    provider_effect_key: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical_item(self) -> StagePlanItem:
        if self.router_role != _router_role(self.kind):
            raise ValueError("router_role conflicts with stage kind")
        if self.provider_effect_key != provider_effect_key(self.stage_key):
            raise ValueError("provider_effect_key conflicts with stage identity")
        _validate_shard(self.kind, self.shard_index, self.shard_count)
        _validate_predecessors(self.stage_key, self.predecessor_stage_keys)
        return self


class StagePlan(_ClosedModel):
    """Canonical plan material signed into consent before any stage dispatch."""

    schema_version: Literal[1] = 1
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    approved_ceiling_cents: int = Field(ge=1)
    stages: tuple[StagePlanItem, ...] = Field(min_length=4, max_length=1_000_000)
    plan_hash: str = Field(pattern=_HEX64)

    @model_validator(mode="after")
    def _canonical_plan(self) -> StagePlan:
        for item in self.stages:
            expected_key = stage_key(
                operation_id=self.operation_id,
                goal_index=item.goal_index,
                kind=item.kind,
                shard_index=item.shard_index,
            )
            if item.stage_key != expected_key:
                raise ValueError("stage_key conflicts with operation topology")
        _validate_plan_topology(self.stages)
        if sum(stage.projected_max_cents for stage in self.stages) > self.approved_ceiling_cents:
            raise ValueError("stage plan exceeds approved operation ceiling")
        if self.plan_hash != stage_plan_hash(
            operation_id=self.operation_id,
            job_id=self.job_id,
            approved_ceiling_cents=self.approved_ceiling_cents,
            stages=self.stages,
        ):
            raise ValueError("plan_hash conflicts with canonical stage material")
        return self


class StageEffectReceipt(_ClosedModel):
    """Immutable digest binding for one returned typed provider output."""

    schema_version: Literal[1] = 1
    receipt_id: str = Field(pattern=_HEX64)
    stage_key: str = Field(pattern=_HEX64)
    provider_effect_key: str = Field(pattern=_HEX64)
    kind: StageKind
    output_schema: StageOutputSchema
    output_sha256: str = Field(pattern=_HEX64)
    route_receipt_id: str = Field(min_length=1, max_length=512)
    source_receipt_ids: tuple[str, ...] = ()
    provider_event_id: str = Field(min_length=1, max_length=512)
    actual_cents: int = Field(ge=0)
    returned_at_ms: int = Field(ge=0)

    @model_validator(mode="after")
    def _canonical_effect(self) -> StageEffectReceipt:
        if self.provider_effect_key != provider_effect_key(self.stage_key):
            raise ValueError("effect receipt conflicts with stage provider identity")
        expected_schema = f"midnight-oil.{self.kind}-output/v1"
        if self.output_schema != expected_schema:
            raise ValueError("output schema conflicts with stage kind")
        if len(set(self.source_receipt_ids)) != len(self.source_receipt_ids):
            raise ValueError("effect receipt has duplicate source receipts")
        if len(self.source_receipt_ids) > 100 or any(
            not value or len(value) > 512 for value in self.source_receipt_ids
        ):
            raise ValueError("effect receipt source IDs are outside bounded contract")
        expected_receipt_id = effect_receipt_id(
            stage_key=self.stage_key,
            provider_effect_key_value=self.provider_effect_key,
            kind=self.kind,
            output_schema=self.output_schema,
            output_sha256=self.output_sha256,
            route_receipt_id=self.route_receipt_id,
            source_receipt_ids=self.source_receipt_ids,
            provider_event_id=self.provider_event_id,
            actual_cents=self.actual_cents,
        )
        if self.receipt_id != expected_receipt_id:
            raise ValueError("effect receipt id conflicts with canonical content")
        return self


class StageReceipt(_ClosedModel):
    """CAS state for one stage; payload bytes and cents remain external authorities."""

    schema_version: Literal[1] = 1
    operation_id: str = Field(min_length=1, max_length=256)
    job_id: str = Field(min_length=1, max_length=256)
    plan_hash: str = Field(pattern=_HEX64)
    stage_key: str = Field(pattern=_HEX64)
    ordinal: int = Field(ge=0, le=1_000_000)
    provider_effect_key: str = Field(pattern=_HEX64)
    state: StageState
    revision: int = Field(ge=0)
    input_evidence_sha256: str | None = Field(default=None, pattern=_HEX64)
    budget_hold_id: str | None = Field(default=None, max_length=256)
    dispatch_fence_sha256: str | None = Field(default=None, pattern=_HEX64)
    lease_generation: int | None = Field(default=None, ge=1)
    effect_receipt_id: str | None = Field(default=None, pattern=_HEX64)
    output_sha256: str | None = Field(default=None, pattern=_HEX64)
    reserved_at_ms: int | None = Field(default=None, ge=0)
    unknown_at_ms: int | None = Field(default=None, ge=0)
    returned_at_ms: int | None = Field(default=None, ge=0)
    settled_at_ms: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _state_contract(self) -> StageReceipt:
        if self.provider_effect_key != provider_effect_key(self.stage_key):
            raise ValueError("provider_effect_key conflicts with stage identity")
        minimum_revision = {
            "planned": 0,
            "reserved": 1,
            "unknown": 2,
            "returned": 2,
            "settled": 3,
        }[self.state]
        if self.revision < minimum_revision or (self.state == "planned" and self.revision != 0):
            raise ValueError("revision is below the monotonic state boundary")
        reserved = (
            self.input_evidence_sha256,
            self.budget_hold_id,
            self.dispatch_fence_sha256,
            self.lease_generation,
            self.reserved_at_ms,
        )
        returned = (self.effect_receipt_id, self.output_sha256, self.returned_at_ms)
        if self.state == "planned":
            if any(
                value is not None
                for value in (*reserved, *returned, self.unknown_at_ms, self.settled_at_ms)
            ):
                raise ValueError("planned stage cannot claim reserved or returned authority")
        elif any(value is None for value in reserved):
            raise ValueError("dispatched stage requires input, hold, and dispatch fence")
        elif self.dispatch_fence_sha256 != dispatch_fence_sha256(
            stage=self.stage_key,
            lease_generation=self.lease_generation or 0,
        ):
            raise ValueError("dispatch fence conflicts with stage lease generation")
        elif self.state == "reserved":
            if any(
                value is not None for value in (*returned, self.unknown_at_ms, self.settled_at_ms)
            ):
                raise ValueError("reserved stage cannot claim provider outcome")
        elif self.state == "unknown":
            if (
                self.unknown_at_ms is None
                or self.reserved_at_ms is None
                or self.unknown_at_ms < self.reserved_at_ms
                or any(value is not None for value in (*returned, self.settled_at_ms))
            ):
                raise ValueError("unknown stage requires only an unknown-outcome checkpoint")
        elif any(value is None for value in returned):
            raise ValueError("returned stage requires immutable effect and output receipts")
        elif self.unknown_at_ms is not None:
            raise ValueError("returned stage cannot also claim unknown outcome")
        elif (
            self.returned_at_ms is None
            or self.reserved_at_ms is None
            or self.returned_at_ms < self.reserved_at_ms
        ):
            raise ValueError("returned stage cannot predate its reservation")
        elif self.state == "returned" and self.settled_at_ms is not None:
            raise ValueError("returned stage cannot claim settlement")
        elif self.state == "settled" and (
            self.settled_at_ms is None
            or self.returned_at_ms is None
            or self.settled_at_ms < self.returned_at_ms
        ):
            raise ValueError("settled stage requires ordered settlement")
        return self


def stage_key(
    *, operation_id: str, goal_index: int, kind: StageKind, shard_index: int | None
) -> str:
    _bounded_text(operation_id, "operation_id")
    if type(goal_index) is not int or goal_index < 0:
        raise ValueError("goal_index must be a non-negative integer")
    if kind not in {"planner", "gather", "verifier", "synthesizer"}:
        raise ValueError("stage kind is outside the closed contract")
    if shard_index is not None and (type(shard_index) is not int or shard_index < 0):
        raise ValueError("shard_index must be a non-negative integer or None")
    return hashlib.sha256(
        _STAGE_DOMAIN
        + _canonical_json(
            {
                "operation_id": operation_id,
                "goal_index": goal_index,
                "kind": kind,
                "shard_index": shard_index,
            }
        )
    ).hexdigest()


def provider_effect_key(stage: str) -> str:
    _sha256(stage, "stage_key")
    return hashlib.sha256(_EFFECT_DOMAIN + stage.encode()).hexdigest()


def dispatch_fence_sha256(*, stage: str, lease_generation: int) -> str:
    _sha256(stage, "stage_key")
    if type(lease_generation) is not int or lease_generation <= 0:
        raise ValueError("lease_generation must be a positive integer")
    return hashlib.sha256(_FENCE_DOMAIN + f"{stage}:{lease_generation}".encode()).hexdigest()


def stage_plan_hash(
    *,
    operation_id: str,
    job_id: str,
    approved_ceiling_cents: int,
    stages: tuple[StagePlanItem, ...],
) -> str:
    _bounded_text(operation_id, "operation_id")
    _bounded_text(job_id, "job_id")
    if type(approved_ceiling_cents) is not int or approved_ceiling_cents <= 0:
        raise ValueError("approved_ceiling_cents must be a positive integer")
    return hashlib.sha256(
        _PLAN_DOMAIN
        + _canonical_json(
            {
                "schema_version": 1,
                "operation_id": operation_id,
                "job_id": job_id,
                "approved_ceiling_cents": approved_ceiling_cents,
                "stages": [stage.model_dump(mode="json") for stage in stages],
            }
        )
    ).hexdigest()


def effect_receipt_id(
    *,
    stage_key: str,
    provider_effect_key_value: str,
    kind: StageKind,
    output_schema: StageOutputSchema,
    output_sha256: str,
    route_receipt_id: str,
    source_receipt_ids: tuple[str, ...],
    provider_event_id: str,
    actual_cents: int,
) -> str:
    """Return replay-stable identity; local observation time is excluded.

    Source receipt order is semantic because it preserves the bounded evidence
    ranking presented to the role. Reordering therefore creates a new receipt.
    """
    if type(actual_cents) is not int or actual_cents < 0:
        raise ValueError("actual_cents must be a non-negative integer")
    return hashlib.sha256(
        _canonical_json(
            {
                "schema_version": 1,
                "stage_key": stage_key,
                "provider_effect_key": provider_effect_key_value,
                "kind": kind,
                "output_schema": output_schema,
                "output_sha256": output_sha256,
                "route_receipt_id": route_receipt_id,
                "source_receipt_ids": list(source_receipt_ids),
                "provider_event_id": provider_event_id,
                "actual_cents": actual_cents,
            }
        )
    ).hexdigest()


def _validate_plan_topology(stages: tuple[StagePlanItem, ...]) -> None:
    if tuple(stage.ordinal for stage in stages) != tuple(range(len(stages))):
        raise ValueError("stage ordinals must be contiguous canonical order")
    if len({stage.stage_key for stage in stages}) != len(stages):
        raise ValueError("stage plan has duplicate stage keys")
    if len({stage.provider_effect_key for stage in stages}) != len(stages):
        raise ValueError("stage plan has provider effect collisions")
    by_goal: dict[int, list[StagePlanItem]] = {}
    seen: set[str] = set()
    for stage in stages:
        if any(key not in seen for key in stage.predecessor_stage_keys):
            raise ValueError("stage predecessor must appear earlier in canonical order")
        seen.add(stage.stage_key)
        by_goal.setdefault(stage.goal_index, []).append(stage)
    if tuple(sorted(by_goal)) != tuple(range(len(by_goal))):
        raise ValueError("goal indexes must be contiguous")
    for rows in by_goal.values():
        planner = [row for row in rows if row.kind == "planner"]
        gather = [row for row in rows if row.kind == "gather"]
        verifier = [row for row in rows if row.kind == "verifier"]
        synthesizer = [row for row in rows if row.kind == "synthesizer"]
        if len(planner) != 1 or not gather or len(verifier) != 1 or len(synthesizer) != 1:
            raise ValueError("each goal requires planner, gatherers, verifier, synthesizer")
        if planner[0].predecessor_stage_keys:
            raise ValueError("planner cannot have predecessors")
        if any(row.predecessor_stage_keys != (planner[0].stage_key,) for row in gather):
            raise ValueError("each gatherer must depend only on its planner")
        gather_keys = tuple(row.stage_key for row in gather)
        shard_counts = {row.shard_count for row in gather}
        if len(shard_counts) != 1:
            raise ValueError("gather shards must share one shard_count")
        shard_count = next(iter(shard_counts))
        if shard_count is None or tuple(row.shard_index for row in gather) != tuple(
            range(shard_count)
        ):
            raise ValueError("gather shards must cover every contiguous index")
        if verifier[0].predecessor_stage_keys != gather_keys:
            raise ValueError("verifier must depend on every ordered gather shard")
        if synthesizer[0].predecessor_stage_keys != (verifier[0].stage_key,):
            raise ValueError("synthesizer must depend on verifier")


def _validate_shard(kind: StageKind, index: int | None, count: int | None) -> None:
    if kind == "gather":
        if index is None or count is None or index >= count:
            raise ValueError("gather stage requires a valid shard index/count")
    elif index is not None or count is not None:
        raise ValueError("only gather stages may carry shard topology")


def _validate_predecessors(stage: str, predecessors: tuple[str, ...]) -> None:
    if len(set(predecessors)) != len(predecessors):
        raise ValueError("stage has duplicate predecessors")
    if stage in predecessors:
        raise ValueError("stage cannot depend on itself")
    for value in predecessors:
        _sha256(value, "predecessor_stage_key")


def _router_role(kind: StageKind) -> str:
    return "gatherer" if kind == "gather" else kind


def _canonical_json(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def _bounded_text(value: str, field: str) -> None:
    if type(value) is not str or not value or len(value) > 256:
        raise ValueError(f"{field} must be bounded and non-empty")


def _sha256(value: str, field: str) -> None:
    if (
        type(value) is not str
        or len(value) != 64
        or any(c not in "0123456789abcdef" for c in value)
    ):
        raise ValueError(f"{field} must be canonical sha256")


__all__ = [
    "StageEffectReceipt",
    "StageKind",
    "StageOutputSchema",
    "StagePlan",
    "StagePlanItem",
    "StageReceipt",
    "StageState",
    "dispatch_fence_sha256",
    "effect_receipt_id",
    "provider_effect_key",
    "stage_key",
    "stage_plan_hash",
]
