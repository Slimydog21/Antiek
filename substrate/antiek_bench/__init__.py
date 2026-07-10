"""Antiek-bench core — offline task-differentiated model suite (package C).

Public surface:

* **Suite** — versioned question set with task classes (distill, synthesize, …)
* **Run** — offline scores via injectable stub providers; week_id + suite_version
* **Rewrite** — usage-pattern propose → explicit approve/promote only
* **Summary** — HTML human view of a completed run (PDF never required)

Does not auto-switch production traffic. Does not call live multi-provider APIs.
"""

from __future__ import annotations

from .dogfood_fixtures import (
    COMPETITIVE_DOGFOOD_VERSION,
    competitive_dogfood_suite,
    dogfood_fixture_payload,
    register_competitive_dogfood_suite,
)
from .leaderboard import (
    LeaderboardSnapshot,
    ModelLeaderboardRow,
    build_leaderboard,
    project_leaderboard_html,
)
from .product_path import (
    DEFAULT_OFFLINE_MODELS,
    run_offline_dogfood_product,
)
from .rewrite import (
    MAX_USAGE_ITEMS_PER_TASK,
    USAGE_SEED_POLICY_VERSION,
    ProposalIntegrityError,
    ProposalMigrationRequiredError,
    ProposalStateError,
    StaleSuiteProposalError,
    SuiteProposal,
    approve_and_promote,
    migrate_legacy_proposal,
    propose_suite_delta,
    reviewed_benchmark_seed,
)
from .run import BenchRunResult, TaskScore, run_suite
from .settings_surface import (
    project_suite_proposal_html,
    project_usage_summary_html,
    settings_approve_suite_proposal_payload,
    settings_leaderboard_payload,
    settings_suite_proposal_payload,
    settings_usage_summary_payload,
)
from .store import (
    ANTIEK_BENCH_USAGE_DIR_ENV,
    BenchStore,
    FileBenchStore,
    InMemoryBenchStore,
    resolve_usage_store,
    usage_store_data_dir,
)
from .suite import (
    SuiteDefinition,
    SuiteItem,
    SuiteRegistry,
    TaskClass,
    active_suite,
    default_core_suite,
    get_suite,
    register_suite,
)
from .summary import project_run_html
from .usage_bridge import (
    KNOWN_USAGE_FEED_SOURCES,
    TWIN_WRITE_SEED_USAGE_SOURCES,
    USAGE_EVENT_RETENTION_LIMIT,
    USAGE_EVENT_SCHEMA_VERSION,
    UsageEvent,
    classify_engagement_task,
    list_usage_events,
    propose_from_recorded_usage,
    record_collective_merge_usage,
    record_session_flywheel_usage,
    record_twin_write_seed_usage,
    record_usage_event,
    research_tier_to_task_class,
    weekly_usage_summary,
)

__all__ = [
    "ANTIEK_BENCH_USAGE_DIR_ENV",
    "COMPETITIVE_DOGFOOD_VERSION",
    "DEFAULT_OFFLINE_MODELS",
    "BenchRunResult",
    "BenchStore",
    "FileBenchStore",
    "InMemoryBenchStore",
    "LeaderboardSnapshot",
    "ModelLeaderboardRow",
    "MAX_USAGE_ITEMS_PER_TASK",
    "ProposalIntegrityError",
    "ProposalMigrationRequiredError",
    "ProposalStateError",
    "SuiteDefinition",
    "SuiteItem",
    "SuiteProposal",
    "SuiteRegistry",
    "StaleSuiteProposalError",
    "USAGE_SEED_POLICY_VERSION",
    "TaskClass",
    "TaskScore",
    "KNOWN_USAGE_FEED_SOURCES",
    "TWIN_WRITE_SEED_USAGE_SOURCES",
    "USAGE_EVENT_RETENTION_LIMIT",
    "USAGE_EVENT_SCHEMA_VERSION",
    "UsageEvent",
    "active_suite",
    "approve_and_promote",
    "migrate_legacy_proposal",
    "build_leaderboard",
    "classify_engagement_task",
    "competitive_dogfood_suite",
    "default_core_suite",
    "dogfood_fixture_payload",
    "get_suite",
    "list_usage_events",
    "project_leaderboard_html",
    "project_run_html",
    "propose_from_recorded_usage",
    "propose_suite_delta",
    "reviewed_benchmark_seed",
    "record_collective_merge_usage",
    "record_session_flywheel_usage",
    "record_twin_write_seed_usage",
    "record_usage_event",
    "research_tier_to_task_class",
    "register_competitive_dogfood_suite",
    "register_suite",
    "resolve_usage_store",
    "run_offline_dogfood_product",
    "run_suite",
    "project_suite_proposal_html",
    "project_usage_summary_html",
    "settings_approve_suite_proposal_payload",
    "settings_leaderboard_payload",
    "settings_suite_proposal_payload",
    "settings_usage_summary_payload",
    "usage_store_data_dir",
    "weekly_usage_summary",
]
