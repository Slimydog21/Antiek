"""DuckLake catalog — Sprint 22 Stage 1 + Sprint 30+ Stage 2 transition.

Per master-spec §13.6 substrate stage matrix:
  Stage 0 — single DuckDB file (operator-only)         [shipped]
  Stage 1 — DuckDB per user + shared substrate DuckLake [Sprint 22]
  Stage 2 — DuckLake catalog routes per-user files     [Sprint 30+]
  Stage 3 — Postgres-sharded                            [post Sprint 30+]

The DuckLake catalog is what makes the Stage 1 → Stage 2 transition
non-disruptive: per-user file routing moves from a directory layout
into a catalog table. Production wires Postgres; substrate-scaffold
ships an in-memory implementation + a SQLite-backed implementation
that can be promoted to Postgres by config flip.

The catalog never speaks DuckDB itself — it is a *mediator*. The
GraphRouter (substrate/multi_user/graph_router.py) consults the
catalog when the operator promotes to Stage 2.
"""

from .catalog import (
    CatalogBackend,
    CatalogEntry,
    DuckLakeCatalog,
    InMemoryCatalogBackend,
    SqliteCatalogBackend,
)
from .migration import (
    MigrationPlan,
    execute_migration_plan,
    plan_stage1_to_stage2,
)
from .routing import (
    HashPrefixSharding,
    NoSharding,
    ShardingStrategy,
    resolve_db_path,
)
from .stage import SubstrateStage

__all__ = [
    "CatalogBackend",
    "CatalogEntry",
    "DuckLakeCatalog",
    "HashPrefixSharding",
    "InMemoryCatalogBackend",
    "MigrationPlan",
    "NoSharding",
    "ShardingStrategy",
    "SqliteCatalogBackend",
    "SubstrateStage",
    "execute_migration_plan",
    "plan_stage1_to_stage2",
    "resolve_db_path",
]
