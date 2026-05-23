"""Substrate Stage 0 → Stage 1 migration (Sprint 22 §13.6).

Per master-spec §13.6 substrate transition matrix:
  Stage 0 — single DuckDB file with single-writer agent
            (per-user file path; currently always '__operator__')
  Stage 1 — DuckDB per user + shared substrate DuckLake
            (file-per-user routing in app layer; Postgres catalog)

This script performs the one-time transition for the first cohort
of real users. It is **declarative-first** — every run starts with
a dry-run that produces a `MigrationPlan` the operator reviews
before any disk movement happens.

The script's invariants:
- The existing operator graph at `ANTIEK_DUCKDB_PATH` is NOT touched.
  It becomes `__operator__`'s per-user file via a copy + rename.
- New users get fresh per-user files created by
  `substrate.graph_per_user.create_user_graph`.
- The DuckLake catalog (substrate/ducklake/) records every per-user
  file with its encryption key reference.
- Operator can `--dry-run` (default) to see the plan without
  touching disk.

Usage:
    python -m tools.migration.stage0_to_stage1 \
        --operator-db ~/.antiek/operator.duckdb \
        --first-cohort u-jane,u-alex,u-priya \
        --root-dir ~/.antiek/personal_graphs \
        --catalog-sqlite ~/.antiek/catalog.sqlite \
        [--dry-run | --execute]
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from substrate.ducklake import (
    DuckLakeCatalog,
    HashPrefixSharding,
    NoSharding,
    SqliteCatalogBackend,
)
from substrate.graph_per_user import (
    InMemoryKeyProvider,
    create_user_graph,
)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class MigrationStep:
    user_id: str
    action: str  # "promote_operator_file" | "create_new_user"
    from_path: Optional[str]
    to_path: str
    notes: str = ""


@dataclass(frozen=True)
class MigrationPlan:
    """The declarative plan the operator reviews before execution."""

    operator_db: str
    root_dir: str
    catalog_path: str
    steps: tuple[MigrationStep, ...]
    sharding_strategy: str
    proposed_at: str = field(default_factory=_now_iso)


def plan_migration(
    *,
    operator_db_path: str,
    first_cohort: list[str],
    root_dir: str,
    catalog_path: str,
    use_sharding: bool = False,
) -> MigrationPlan:
    """Build the declarative plan. Does not touch disk."""
    sharding = HashPrefixSharding(hex_chars=1) if use_sharding else NoSharding()
    sharding_name = type(sharding).__name__

    steps: list[MigrationStep] = []

    # Step 1 — promote operator file
    safe_operator_id = "__operator__"
    operator_target = sharding.db_path_for(safe_operator_id, root_dir=root_dir)
    steps.append(MigrationStep(
        user_id=safe_operator_id,
        action="promote_operator_file",
        from_path=operator_db_path,
        to_path=operator_target,
        notes="Stage-0 file becomes __operator__'s personal graph",
    ))

    # Step 2..N — create new users
    for user_id in first_cohort:
        if user_id == safe_operator_id:
            continue
        target = sharding.db_path_for(user_id, root_dir=root_dir)
        steps.append(MigrationStep(
            user_id=user_id,
            action="create_new_user",
            from_path=None,
            to_path=target,
            notes=f"fresh per-user DuckDB + per-graph key",
        ))

    return MigrationPlan(
        operator_db=operator_db_path,
        root_dir=root_dir,
        catalog_path=catalog_path,
        steps=tuple(steps),
        sharding_strategy=sharding_name,
    )


def format_plan_markdown(plan: MigrationPlan) -> str:
    """Render the plan for operator review."""
    lines: list[str] = []
    lines.append("# Stage 0 → Stage 1 Migration Plan")
    lines.append("")
    lines.append(f"**Proposed at:** {plan.proposed_at}")
    lines.append(f"**Operator DB:** `{plan.operator_db}`")
    lines.append(f"**Per-user root:** `{plan.root_dir}`")
    lines.append(f"**Catalog SQLite:** `{plan.catalog_path}`")
    lines.append(f"**Sharding strategy:** `{plan.sharding_strategy}`")
    lines.append(f"**Total steps:** {len(plan.steps)}")
    lines.append("")
    lines.append("## Steps")
    lines.append("")
    for i, step in enumerate(plan.steps, start=1):
        lines.append(f"### Step {i} — {step.action} ({step.user_id})")
        if step.from_path:
            lines.append(f"- From: `{step.from_path}`")
        lines.append(f"- To: `{step.to_path}`")
        lines.append(f"- Notes: {step.notes}")
        lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("**To execute:** re-run with `--execute` (the default is `--dry-run`).")
    return "\n".join(lines)


def execute_plan(
    plan: MigrationPlan,
    *,
    dry_run: bool = True,
) -> list[MigrationStep]:
    """Execute the plan. `dry_run=True` (default) returns the planned
    steps without touching disk."""
    if dry_run:
        return list(plan.steps)

    catalog = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=plan.catalog_path))
    key_provider = InMemoryKeyProvider()  # production swaps KMSStubKeyProvider
    sharding = (
        HashPrefixSharding(hex_chars=1)
        if plan.sharding_strategy == "HashPrefixSharding"
        else NoSharding()
    )

    completed: list[MigrationStep] = []
    for step in plan.steps:
        target_dir = os.path.dirname(step.to_path)
        if target_dir:
            os.makedirs(target_dir, exist_ok=True)

        if step.action == "promote_operator_file":
            if step.from_path and os.path.exists(step.from_path):
                shutil.copy2(step.from_path, step.to_path)
            # Register in catalog with a synthetic key entry (the
            # existing operator file is not yet encrypted; production
            # operator runs a separate key-rewrap pass).
            catalog.register(
                user_id=step.user_id,
                db_path=step.to_path,
                encryption_key_ref="alias/antiek-graph-__operator__",
            )
        elif step.action == "create_new_user":
            create_user_graph(
                user_id=step.user_id,
                catalog=catalog,
                key_provider=key_provider,
                strategy=sharding,
                root_dir=plan.root_dir,
            )
        completed.append(step)

    return completed


def _main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Stage 0 → Stage 1 substrate migration (Sprint 22 §13.6)",
    )
    parser.add_argument("--operator-db", required=True,
                        help="Path to the Stage-0 operator DuckDB file")
    parser.add_argument("--first-cohort", default="",
                        help="Comma-separated user_ids for the first cohort")
    parser.add_argument("--root-dir", required=True,
                        help="Per-user files root dir")
    parser.add_argument("--catalog-sqlite", required=True,
                        help="DuckLake catalog SQLite path")
    parser.add_argument("--sharding", action="store_true",
                        help="Use HashPrefixSharding (Stage 1.5+)")
    parser.add_argument("--execute", action="store_true",
                        help="Actually execute (default is --dry-run)")
    parser.add_argument("--plan-out", default="",
                        help="Optional path to write the plan markdown")
    args = parser.parse_args(argv)

    cohort = [u.strip() for u in args.first_cohort.split(",") if u.strip()]
    plan = plan_migration(
        operator_db_path=args.operator_db,
        first_cohort=cohort,
        root_dir=args.root_dir,
        catalog_path=args.catalog_sqlite,
        use_sharding=args.sharding,
    )

    md = format_plan_markdown(plan)
    print(md)
    if args.plan_out:
        with open(args.plan_out, "w") as f:
            f.write(md)

    if args.execute:
        print("\n## Executing")
        completed = execute_plan(plan, dry_run=False)
        for s in completed:
            print(f"  - completed: {s.action} ({s.user_id})")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
