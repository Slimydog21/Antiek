"""Agent kernel skills — the agent CODING surface for mining + sculpting data.

Three typed, standalone, substrate-safe skills a research agent calls
directly (no binary, no network, no GPU):

* :mod:`duckdb_store` — ephemeral in-memory DuckDB store: create tables,
  insert, query, typed rows back. Never touches the corpus DB
  (single-writer invariant), by construction.
* :mod:`py_analysis` — stdlib-only summary statistics + grouped
  aggregations over a mined dataset. No pandas/numpy dependency.
* :mod:`sketch_svg` — deterministic Processing/p5-inspired generative
  SVG (or a bar sketch of a distribution), validated live through the
  zero-script gate before it is returned — safe to embed in an Antiek
  HTML asset.

See :mod:`substrate.agent_skills.registry` for the machine-readable
catalog (manifests with parameter/return/safety contracts). Importing
this package has no side effects and loads no heavy dependencies.
"""

from substrate.agent_skills.duckdb_store import DuckDBStore, QueryResult, create_store, run_sql
from substrate.agent_skills.manifest import SkillManifest, SkillParameter
from substrate.agent_skills.py_analysis import (
    AnalysisReport,
    GroupSummary,
    SeriesSummary,
    group_summarize,
    summarize_rows,
    summarize_series,
)
from substrate.agent_skills.registry import SKILLS, get_skill, list_skills
from substrate.agent_skills.sketch_svg import SeededRng, sketch_svg

__all__ = [
    "AnalysisReport",
    "DuckDBStore",
    "GroupSummary",
    "QueryResult",
    "SKILLS",
    "SeededRng",
    "SeriesSummary",
    "SkillManifest",
    "SkillParameter",
    "create_store",
    "get_skill",
    "group_summarize",
    "list_skills",
    "run_sql",
    "sketch_svg",
    "summarize_rows",
    "summarize_series",
]
