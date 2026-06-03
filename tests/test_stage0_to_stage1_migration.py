"""Tests for tools.migration.stage0_to_stage1."""

from __future__ import annotations

import os

from tools.migration.stage0_to_stage1 import (
    execute_plan,
    format_plan_markdown,
    plan_migration,
)


def test_plan_includes_operator_promotion_step(tmp_path):
    operator_db = str(tmp_path / "operator.duckdb")
    catalog = str(tmp_path / "catalog.sqlite")
    root_dir = str(tmp_path / "graphs")

    plan = plan_migration(
        operator_db_path=operator_db,
        first_cohort=["u-jane", "u-alex"],
        root_dir=root_dir,
        catalog_path=catalog,
    )
    # Step 1 is always the operator promotion.
    assert plan.steps[0].action == "promote_operator_file"
    assert plan.steps[0].user_id == "__operator__"
    assert plan.steps[0].from_path == operator_db


def test_plan_includes_new_user_steps(tmp_path):
    plan = plan_migration(
        operator_db_path=str(tmp_path / "op.duckdb"),
        first_cohort=["u-jane", "u-alex", "u-priya"],
        root_dir=str(tmp_path / "graphs"),
        catalog_path=str(tmp_path / "catalog.sqlite"),
    )
    actions = [s.action for s in plan.steps]
    assert actions.count("create_new_user") == 3
    user_ids = [s.user_id for s in plan.steps if s.action == "create_new_user"]
    assert set(user_ids) == {"u-jane", "u-alex", "u-priya"}


def test_plan_skips_operator_in_first_cohort(tmp_path):
    plan = plan_migration(
        operator_db_path=str(tmp_path / "op.duckdb"),
        first_cohort=["__operator__", "u-jane"],
        root_dir=str(tmp_path / "graphs"),
        catalog_path=str(tmp_path / "catalog.sqlite"),
    )
    # Operator is the promotion step, NOT a create_new_user step.
    create_users = [s.user_id for s in plan.steps if s.action == "create_new_user"]
    assert "__operator__" not in create_users


def test_dry_run_does_not_touch_disk(tmp_path):
    operator_db = tmp_path / "operator.duckdb"
    operator_db.write_text("fake duckdb")
    plan = plan_migration(
        operator_db_path=str(operator_db),
        first_cohort=["u-jane"],
        root_dir=str(tmp_path / "graphs"),
        catalog_path=str(tmp_path / "catalog.sqlite"),
    )
    out = execute_plan(plan, dry_run=True)
    assert len(out) == 2  # operator promotion + 1 user
    # Operator file still exists at the original path; no new files.
    assert operator_db.exists()
    assert not (tmp_path / "graphs").exists()


def test_execute_creates_per_user_files(tmp_path):
    operator_db = tmp_path / "operator.duckdb"
    operator_db.write_text("fake duckdb content")
    root_dir = str(tmp_path / "graphs")
    catalog = str(tmp_path / "catalog.sqlite")

    plan = plan_migration(
        operator_db_path=str(operator_db),
        first_cohort=["u-jane"],
        root_dir=root_dir,
        catalog_path=catalog,
    )
    completed = execute_plan(plan, dry_run=False)
    assert len(completed) == 2
    # Operator file copied to the new location.
    operator_target = os.path.join(root_dir, "__operator__.duckdb")
    assert os.path.exists(operator_target)
    # Catalog file created.
    assert os.path.exists(catalog)


def test_plan_with_sharding_uses_shard_dirs(tmp_path):
    plan = plan_migration(
        operator_db_path=str(tmp_path / "op.duckdb"),
        first_cohort=["u-shardtest"],
        root_dir=str(tmp_path / "graphs"),
        catalog_path=str(tmp_path / "catalog.sqlite"),
        use_sharding=True,
    )
    assert plan.sharding_strategy == "HashPrefixSharding"
    user_step = next(s for s in plan.steps if s.user_id == "u-shardtest")
    # Path should include a single-hex-char shard dir between root and file.
    parts = user_step.to_path.split(os.sep)
    assert parts[-1] == "u-shardtest.duckdb"
    assert len(parts[-2]) == 1  # single hex char


def test_format_plan_markdown_includes_all_steps(tmp_path):
    plan = plan_migration(
        operator_db_path=str(tmp_path / "op.duckdb"),
        first_cohort=["u-jane", "u-alex"],
        root_dir=str(tmp_path / "graphs"),
        catalog_path=str(tmp_path / "catalog.sqlite"),
    )
    md = format_plan_markdown(plan)
    assert "Stage 0 → Stage 1" in md
    assert "u-jane" in md
    assert "u-alex" in md
    assert "promote_operator_file" in md
    assert "--execute" in md
