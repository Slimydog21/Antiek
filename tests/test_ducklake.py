"""DuckLake catalog + sharding + migration tests."""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.ducklake import (
    DuckLakeCatalog,
    HashPrefixSharding,
    InMemoryCatalogBackend,
    NoSharding,
    SqliteCatalogBackend,
    SubstrateStage,
    execute_migration_plan,
    plan_stage1_to_stage2,
    resolve_db_path,
)


# ── Catalog backends ──────────────────────────────────────────────


def test_inmemory_upsert_get_remove():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    entry = cat.register(user_id="u-1", db_path="/tmp/u-1.duckdb")
    assert cat.lookup("u-1") == entry
    assert cat.deregister("u-1")
    assert cat.lookup("u-1") is None


def test_inmemory_upsert_overwrites():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    cat.register(user_id="u-1", db_path="/tmp/a.duckdb")
    cat.register(user_id="u-1", db_path="/tmp/b.duckdb")
    assert cat.lookup("u-1").db_path == "/tmp/b.duckdb"
    assert len(cat.list_all()) == 1


def test_sqlite_persists_across_reopens():
    with tempfile.TemporaryDirectory() as td:
        db_file = os.path.join(td, "catalog.sqlite")
        cat1 = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=db_file))
        cat1.register(user_id="u-1", db_path="/tmp/u-1.duckdb", shard_id="a")
        # Reopen.
        cat2 = DuckLakeCatalog(backend=SqliteCatalogBackend(db_path=db_file))
        entry = cat2.lookup("u-1")
        assert entry is not None
        assert entry.db_path == "/tmp/u-1.duckdb"
        assert entry.shard_id == "a"


# ── Sharding strategies ───────────────────────────────────────────


def test_no_sharding_flat_layout():
    s = NoSharding()
    assert s.shard_id_for("u-1") is None
    p = s.db_path_for("u-1", root_dir="/root")
    assert p == "/root/u-1.duckdb"


def test_hash_prefix_sharding_distributes():
    s = HashPrefixSharding(hex_chars=1)
    shards = {s.shard_id_for(f"u-{i}") for i in range(100)}
    # With 100 random user_ids, we should populate close to all 16 shards.
    assert len(shards) >= 10
    # Same user_id always maps to same shard.
    assert s.shard_id_for("u-1") == s.shard_id_for("u-1")


def test_hash_prefix_sharding_path_includes_shard():
    s = HashPrefixSharding(hex_chars=1)
    p = s.db_path_for("u-1", root_dir="/root")
    parts = p.split(os.sep)
    assert parts[-2] == s.shard_id_for("u-1")
    assert parts[-1] == "u-1.duckdb"


def test_invalid_user_id_rejected():
    with pytest.raises(ValueError):
        NoSharding().db_path_for("", root_dir="/root")


def test_resolve_db_path_catalog_wins_when_present():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    cat.register(user_id="u-1", db_path="/migrated/path.duckdb")
    p = resolve_db_path(
        "u-1",
        catalog=cat,
        strategy=NoSharding(),
        root_dir="/root",
    )
    assert p == "/migrated/path.duckdb"


def test_resolve_db_path_falls_through_to_strategy():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    p = resolve_db_path(
        "u-1",
        catalog=cat,
        strategy=NoSharding(),
        root_dir="/root",
    )
    assert p == "/root/u-1.duckdb"


# ── Migration plan + execute ──────────────────────────────────────


def test_plan_stage1_to_stage2_moves_unsharded_to_sharded():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    cat.register(user_id="u-1", db_path="/root/u-1.duckdb", last_size_bytes=1024)
    cat.register(user_id="u-2", db_path="/root/u-2.duckdb", last_size_bytes=2048)
    plan = plan_stage1_to_stage2(
        catalog=cat,
        root_dir="/root",
        to_strategy=HashPrefixSharding(hex_chars=1),
    )
    assert len(plan.steps) == 2
    assert plan.total_bytes == 1024 + 2048
    # Every step has from != to.
    for step in plan.steps:
        assert step.from_path != step.to_path
        assert step.shard_id is not None


def test_plan_skips_already_correct_paths():
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    s = HashPrefixSharding(hex_chars=1)
    # Pre-populate with the sharded path.
    cat.register(user_id="u-1", db_path=s.db_path_for("u-1", root_dir="/root"))
    plan = plan_stage1_to_stage2(
        catalog=cat, root_dir="/root", to_strategy=s,
    )
    assert plan.steps == ()


def test_dry_run_does_not_touch_disk(tmp_path):
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    src = tmp_path / "u-1.duckdb"
    src.write_text("placeholder")
    cat.register(user_id="u-1", db_path=str(src))
    plan = plan_stage1_to_stage2(
        catalog=cat, root_dir=str(tmp_path), to_strategy=HashPrefixSharding(hex_chars=1),
    )
    out = execute_migration_plan(plan, catalog=cat, dry_run=True)
    assert len(out) == 1
    # File still in place; catalog still points at old path.
    assert src.exists()
    assert cat.lookup("u-1").db_path == str(src)


def test_real_migration_moves_files_and_updates_catalog(tmp_path):
    cat = DuckLakeCatalog(backend=InMemoryCatalogBackend())
    src = tmp_path / "u-1.duckdb"
    src.write_text("placeholder")
    cat.register(user_id="u-1", db_path=str(src), last_size_bytes=11)
    plan = plan_stage1_to_stage2(
        catalog=cat, root_dir=str(tmp_path), to_strategy=HashPrefixSharding(hex_chars=1),
    )
    out = execute_migration_plan(plan, catalog=cat, dry_run=False)
    assert len(out) == 1
    new_path = out[0].to_path
    assert os.path.exists(new_path)
    assert not src.exists()  # moved, not copied
    assert cat.lookup("u-1").db_path == new_path


# ── Stage enum ────────────────────────────────────────────────────


def test_stage_enum_has_all_four_stages():
    stages = list(SubstrateStage)
    assert len(stages) == 4
    assert SubstrateStage.STAGE_0_SINGLE_FILE in stages
    assert SubstrateStage.STAGE_3_POSTGRES_SHARDED in stages
