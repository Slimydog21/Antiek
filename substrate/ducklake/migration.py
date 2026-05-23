"""Stage 1 → Stage 2 migration — move per-user files into shard dirs.

Per master-spec §13.6: triggered when per-user DuckDB file count
approaches OS handle limits OR catalog Postgres becomes the
contention point. This module produces a plan first; execution is
gated on operator approval (no auto-migration ever).
"""

from __future__ import annotations

import os
import shutil
from dataclasses import dataclass, field
from typing import Optional

from .catalog import DuckLakeCatalog
from .routing import HashPrefixSharding, NoSharding, ShardingStrategy


@dataclass(frozen=True)
class MigrationStep:
    user_id: str
    from_path: str
    to_path: str
    shard_id: Optional[str]
    size_bytes: int


@dataclass(frozen=True)
class MigrationPlan:
    steps: tuple[MigrationStep, ...]
    from_strategy: str
    to_strategy: str

    @property
    def total_bytes(self) -> int:
        return sum(s.size_bytes for s in self.steps)


def plan_stage1_to_stage2(
    *,
    catalog: DuckLakeCatalog,
    root_dir: str,
    to_strategy: HashPrefixSharding,
    from_strategy: ShardingStrategy = NoSharding(),
) -> MigrationPlan:
    """Produce a deterministic migration plan from the current catalog.

    The plan is purely declarative; nothing is moved. Operator review
    happens between plan + execute. Per §13.6 the operator must
    confirm both (a) the trigger condition has been demonstrated in
    the marketplace-metrics dashboard and (b) per-user latency SLA
    has slack to absorb a migration window.
    """
    steps: list[MigrationStep] = []
    for entry in catalog.list_all():
        new_path = to_strategy.db_path_for(entry.user_id, root_dir=root_dir)
        if new_path == entry.db_path:
            continue
        steps.append(MigrationStep(
            user_id=entry.user_id,
            from_path=entry.db_path,
            to_path=new_path,
            shard_id=to_strategy.shard_id_for(entry.user_id),
            size_bytes=entry.last_size_bytes,
        ))
    return MigrationPlan(
        steps=tuple(steps),
        from_strategy=type(from_strategy).__name__,
        to_strategy=type(to_strategy).__name__,
    )


def execute_migration_plan(
    plan: MigrationPlan,
    *,
    catalog: DuckLakeCatalog,
    dry_run: bool = True,
) -> list[MigrationStep]:
    """Execute the plan. `dry_run=True` (default) returns the steps
    that *would* run without touching disk. Production override
    requires explicit operator action.

    Discipline: each step is independent; if one fails, the others
    that have completed stay completed and the catalog reflects
    their new paths. Resuming a partial migration is a fresh
    plan_stage1_to_stage2 call.
    """
    if dry_run:
        return list(plan.steps)

    completed: list[MigrationStep] = []
    for step in plan.steps:
        new_dir = os.path.dirname(step.to_path)
        if new_dir:
            os.makedirs(new_dir, exist_ok=True)
        if os.path.exists(step.from_path):
            shutil.move(step.from_path, step.to_path)
        catalog.register(
            user_id=step.user_id,
            db_path=step.to_path,
            shard_id=step.shard_id,
            last_size_bytes=step.size_bytes,
        )
        completed.append(step)
    return completed
