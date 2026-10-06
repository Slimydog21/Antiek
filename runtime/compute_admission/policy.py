"""The version-one YAML contract, restricted to in-process execution."""

from __future__ import annotations

from collections.abc import Hashable
from pathlib import Path
from typing import Annotated, Any, Literal, Self

import yaml
from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}$")]
PositiveInt = Annotated[int, Field(gt=0)]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class BackendPolicy(StrictModel):
    kind: Literal["in_process"]
    price_usd_per_unit: None


class PoolPolicy(StrictModel):
    slots: PositiveInt


class WorkloadPolicy(StrictModel):
    enabled: bool
    backend: Identifier
    pool: Identifier
    slot_cost: PositiveInt
    acu_units: PositiveInt


class TenantPolicy(StrictModel):
    projects: list[Identifier] = Field(min_length=1)
    session_budget_acu: Annotated[int, Field(ge=0)]

    @model_validator(mode="after")
    def unique_projects(self) -> Self:
        if len(set(self.projects)) != len(self.projects):
            raise ValueError("tenant projects must be unique")
        return self


class LeasePolicy(StrictModel):
    heartbeat_interval_s: PositiveInt
    stale_after_s: PositiveInt

    @model_validator(mode="after")
    def heartbeat_window(self) -> Self:
        if self.stale_after_s <= self.heartbeat_interval_s:
            raise ValueError("stale_after_s must exceed heartbeat_interval_s")
        return self


class ComputePolicy(StrictModel):
    schema_version: Literal["antiek.compute_policy.v1"]
    policy_version: Annotated[
        str, StringConstraints(pattern=r"^1\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$")
    ]
    backends: dict[Identifier, BackendPolicy] = Field(min_length=1)
    pools: dict[Identifier, PoolPolicy] = Field(min_length=1)
    classes: dict[Identifier, WorkloadPolicy] = Field(min_length=1)
    tenants: dict[Identifier, TenantPolicy]
    leases: LeasePolicy

    @model_validator(mode="after")
    def known_routes(self) -> Self:
        for name, workload in self.classes.items():
            if workload.backend not in self.backends or workload.pool not in self.pools:
                raise ValueError(f"class {name!r} references an unknown backend or pool")
            if workload.slot_cost > self.pools[workload.pool].slots:
                raise ValueError(f"class {name!r} exceeds its pool capacity")
        return self


class _UniqueKeyLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> dict[Hashable, Any]:
        seen = set()
        for key_node, _ in node.value:
            key = self.construct_object(key_node, deep=deep)
            if not isinstance(key, str) or key in seen:
                raise yaml.constructor.ConstructorError(
                    "policy", node.start_mark, "keys must be unique strings", key_node.start_mark
                )
            seen.add(key)
        return super().construct_mapping(node, deep=deep)


def load_policy(path: str | Path | None = None) -> ComputePolicy:
    source = Path(path) if path is not None else Path(__file__).with_name("policy.v1.yaml")
    raw = yaml.load(source.read_text(encoding="utf-8"), Loader=_UniqueKeyLoader)
    return ComputePolicy.model_validate(raw)
