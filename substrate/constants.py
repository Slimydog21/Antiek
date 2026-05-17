"""Centralized constants for Antiek.

Every parameter that influences a model decision, a retrieval cutoff, a
tier assignment, a TTL, or a verification threshold lives here. There is
exactly one consumer of this module per role — duplication of these
values across the codebase is a documented failure mode that the
Researchmaxx audit (2026-05-13) explicitly called out.

Constants are versioned. ``ANTIEK_PARAM_VERSION`` is stamped into every
archived synthesis and event-log entry so backtests can correlate
parameter versions to outcomes. Bumping the version is a deliberate act
— it invalidates prior cohort comparisons and should be paired with an
entry in ``docs/architecture_notes.md`` explaining the change.

Lineage: Sections A–G are direct migrations from Researchmaxx
``researchmaxx_constants.py`` v1.1.0 (the production canonical at
~/.hermes/skills/research/graph-research-substrate/scripts/). Section H
contains Antiek-specific additions for paths, the wrestling-loop
vocabulary, and the DeepBlu-lineage claim classes.
"""

from __future__ import annotations

from typing import Final


# ============================================================
# Section A — Five role pipeline
# ============================================================

# A.1 Decomposer
# Below 4 the decomposition is performative; above 8 retrieval costs balloon.
SUB_QUESTIONS_MIN: Final[int] = 4
SUB_QUESTIONS_MAX: Final[int] = 8

# Keywords drive cross-domain traversal. Range chosen by the spec.
KEYWORDS_MIN: Final[int] = 8
KEYWORDS_MAX: Final[int] = 20
SYNONYMS_PER_KEYWORD_MAX: Final[int] = 3

# Paraphrase mitigation: if a sub-question's embedding is within this cosine
# distance of the top-level question, treat it as a restatement and regenerate.
DECOMPOSER_PARAPHRASE_COSINE_MAX: Final[float] = 0.85

# A.2 Evidence Retriever — vector retrieval depth
RETRIEVAL_TOP_K: Final[int] = 5

# A.4 Cross-Domain Connector — keyword→node mapping confidence floor.
# Below this we still produce a mapping but flag it as low-confidence and
# the Synthesizer is told not to lean on it.
CROSS_DOMAIN_SIMILARITY_THRESHOLD: Final[float] = 0.80

# Traversal defaults per spec §5.
TRAVERSAL_TOP_N_PATHS: Final[int] = 5
TRAVERSAL_DFS_DEPTH: Final[int] = 5
TRAVERSAL_MAX_DEPTH: Final[int] = 8

# Cross-Domain Connector pairwise-traversal cap. With M mapped nodes the
# orchestrator runs M*(M-1)/2 top-N traversals. M=4 → 6 pairs is the budget
# we accept by default.
CROSS_DOMAIN_PAIRWISE_TRAVERSAL_NODE_CAP: Final[int] = 4

# A.5 Synthesizer confidence rubric (must mirror the JSON schema enum)
CONFIDENCE_LEVELS: Final[tuple[str, ...]] = ("high", "moderate", "low", "unknown")


# ============================================================
# Section B — Constraint-checking middleware
# ============================================================

# Beyond 3 iterations the underlying issue is not addressable by revision.
CONSTRAINT_MAX_ITERATIONS: Final[int] = 3

# Strictness vocabulary mirrored by the Parameter Extractor schema.
CONSTRAINT_STRICTNESS: Final[tuple[str, ...]] = ("hard", "soft", "target")


# ============================================================
# Section C — Source-tier policy
# ============================================================

# Tier 1 is highest trust (primary), Tier 5 is lowest (anonymous/aggregator).
# Tier integers travel everywhere as-is; do not reverse the polarity downstream.
TIER_HIGHEST: Final[int] = 1
TIER_LOWEST: Final[int] = 5

# C.4 Multi-source aggregation: a claim is supported at effective tier t iff
# at least TIER_AGGREGATE_K independent sources at tier ≤ t support it.
# k=2 enforces "two independent sources at the same tier", which catches the
# single-Tier-1-source-overriding-three-Tier-3-sources failure mode.
TIER_AGGREGATE_K: Final[int] = 2

# C.3 Tier → hedging policy. The Synthesizer prompt enumerates these
# verbatim. Centralised here so prompt and code stay aligned.
TIER_HEDGING_POLICY: Final[dict[int, str]] = {
    1: "state directly; no hedging required",
    2: "attribute the source explicitly (\"peer-reviewed analysis indicates...\")",
    3: "hedge explicitly (\"trade reporting suggests...\") and flag as low-tier in the structured output",
    4: "hedge AND reduce confidence explicitly",
    5: "treat as unsupported; do not include in the thesis",
}


# ============================================================
# Section D — Temporal layer
# ============================================================

# D.3 Staleness TTLs (days). Used by the staleness scanner to flag claims
# whose evidentiary support has aged past its half-life. Each TTL is justified
# by the rate at which the underlying fact actually changes in practice.
#
# Antiek-additive entries (biographical_fact, stated_opinion, market_price,
# regulatory_status, hardware_specification, fundamental_constant) come from
# the DeepBlu lineage and the consume-side wrestling vocabulary. They live in
# the same dict so the temporal middleware has a single lookup table.
STALENESS_TTL_DAYS: Final[dict[str, int]] = {
    # Researchmaxx (production-validated)
    "financial_state":          180,   # 6 months  — quarterly cadence + lag
    "personnel":                 90,   # 3 months  — exec turnover is fast
    "funding_ownership":         90,   # 3 months  — round cadence + dilution
    "tech_milestone":           180,   # 6 months  — engineering quarter scale
    "partnership":              180,   # 6 months
    "fundamental_capability":   730,   # 24 months — physics-level constraints
    # Antiek-additive (DeepBlu lineage + consume side)
    "market_price":               1,   # intraday volatility
    "company_headcount":         30,   # monthly hiring cadence
    "regulatory_status":         90,
    "research_finding":     365 * 2,
    "hardware_specification":   365,
    "biographical_fact":   365 * 50,   # subject's stated life facts decay slowly
    "stated_opinion":            90,   # subject's current-event opinions age fast
    "fundamental_constant": 365 * 100, # effectively never
}

# Relations that strongly imply a particular claim_class.
# Used by staleness.py to bucket edges before applying TTL.
RELATION_TO_CLAIM_CLASS: Final[dict[str, str]] = {
    # personnel — from extractor vocabulary ("led_by")
    "led_by": "personnel",
    # funding_ownership — `raised_series_c` observed in live edges;
    # `raised` keyed as a prefix so future series/seed rounds are caught
    # by the staleness scanner's substring fallback.
    "raised_series_c": "funding_ownership",
    "raised": "funding_ownership",
    # partnership — from extractor vocabulary ("supplies")
    "supplies": "partnership",
    # fundamental_capability — from extractor vocabulary ("constrains").
    "constrains": "fundamental_capability",
}


# ============================================================
# Section E — Backtesting / cohort analysis
# ============================================================

# E.3 Well-calibrated confirmation rates per confidence stratum.
CONFIDENCE_CALIBRATION_TARGETS: Final[dict[str, tuple[float, float]]] = {
    "high":     (0.85, 1.00),
    "moderate": (0.65, 0.80),
    "low":      (0.50, 0.65),
    "unknown":  (0.00, 1.00),  # by definition uncalibrated
}

# E.5 Minimum cohort size before cohort accuracy is meaningfully signal.
COHORT_MIN_OBSERVED_INVESTIGATIONS: Final[int] = 30


# ============================================================
# Section F — RLM round-1 parameters (Recursive Language Models)
# ============================================================

# Maximum number of concurrent sub-LLM calls in a single "batch".
RLM_LLM_BATCH_MAX_PARALLELISM: Final[int] = 1  # sequential for memory safety

# Per RLM published work: prefer chunked batches over per-atom calls.
RLM_LLM_BATCH_CHARS_TARGET: Final[int] = 200_000

# How deep recursion of RLM-style calls may go before the orchestrator
# escalates. depth-1 is the validated default.
RLM_MAX_RECURSION_DEPTH: Final[int] = 1

# REPL stdout shown back to an orchestrator is truncated to this byte budget.
RLM_REPL_STDOUT_TRUNCATE: Final[int] = 8192

# answer["content"] cap so a runaway loop cannot exhaust memory.
RLM_ANSWER_CONTENT_MAX: Final[int] = 1_000_000

# Verification primitive: minimum agreement count required across re-dispatches.
RLM_VERIFY_AGREEMENT_MIN: Final[int] = 2

# Number of rephrased framings to dispatch when verification is invoked.
RLM_VERIFY_REDISPATCH_COUNT: Final[int] = 1

# REPL sandbox: pip packages the orchestrator may import.
RLM_REPL_AVAILABLE_PACKAGES: Final[tuple[str, ...]] = (
    "duckdb",
    "numpy",
    "sentence_transformers",
    "requests",
    "json",
    "re",
    "hashlib",
)


# ============================================================
# Section G — Phase-log assertions
# ============================================================
#
# Phases of the autonomous-deep-research protocol. Numbering is 1-indexed
# to match phase_log.py and the existing Researchmaxx code. The earlier
# scaffolding-pass tuple PHASES (0-indexed, descriptive strings) was a
# placeholder; this tuple is the actual one consumed by phase_runner.

AUTONOMOUS_RESEARCH_PHASES: Final[tuple[int, ...]] = (
    1,  # Orient
    2,  # Round 1 — broad landscape (parallel sub-agents)
    3,  # Round 1 self-critique
    4,  # Round 2 — deep dive on gaps
    5,  # Round 2 self-critique
    6,  # Final synthesis (five-role chain via orchestrate.py)
    7,  # Delivery (PDF + Bear + WhatsApp)
    8,  # Knowledge extraction → graph merge → backtest archival
    9,  # Completion (kanban transition)
)

# Phases that gate task completion. Skipping one of these without an
# explicit override is a protocol violation, not a soft warning.
AUTONOMOUS_RESEARCH_REQUIRED_PHASES_FOR_COMPLETION: Final[tuple[int, ...]] = (6, 7, 8)

# Phase 8 cannot complete unless the skill-file diff shows growth.
# Mechanical verification replaces prose enforcement.
PHASE_8_REQUIRES_SKILL_GROWTH: Final[bool] = True


# ============================================================
# Section H — Antiek-specific additions
# ============================================================
#
# Net-new constants for Antiek's paths, role catalog, dispatch defaults,
# and context-pack budgets. These do NOT exist in Researchmaxx; they are
# the substrate decisions documented in architecture_notes.md §2.

# --- Special investigation_id sentinels ----------------------

# Used as the envelope investigation_id for events that are NOT scoped
# to a single investigation — global sweeps (TIER_REWRITE_BULK), bulk
# ingestion runs, scheduled scans. Lets the typed-emit path satisfy the
# required-string contract without losing the "this is a system event"
# semantic. Query patterns: ``investigation_id = 'system'`` lifts every
# global sweep.
SYSTEM_INVESTIGATION_ID: Final[str] = "system"

# --- Paths ----------------------------------------------------

# Event log (typed trajectories). JSONL while live, Parquet when sealed.
EVENT_LOG_DIR: Final[str] = "~/.antiek/research_events"

# DuckDB write-coordinated graph store.
DUCKDB_PATH: Final[str] = "~/.antiek/research_graph.duckdb"
DUCKDB_LOCK_SUFFIX: Final[str] = ".write.lock"  # sidecar of DUCKDB_PATH
DUCKDB_LOCK_TIMEOUT_SECONDS: Final[int] = 300

# --- Source-type vocabulary (maps to integer tiers via tier_rules) -----

# String identifiers for source types. The integer tier (1–5) for each
# is assigned by `middleware/source_tier/tier_rules.py` (rule-based) and
# may be adjusted DOWNWARD only by the tier_override LLM path.
SOURCE_TYPES: Final[tuple[str, ...]] = (
    "peer_reviewed",        # journal-published, refereed
    "preprint",             # arXiv / bioRxiv / SSRN
    "primary_interview",    # captured directly from subject (DeepBlu lineage)
    "official_filing",      # 10-K, S-1, regulatory filings, government records
    "journalism_quality",   # major outlets with verified editorial standards
    "journalism_general",   # general press
    "social_media",         # X, blogs, Substack
    "unverified",           # default for unknown provenance
)

# --- Role catalog ---------------------------------------------

ROLES: Final[tuple[str, ...]] = (
    "decomposer",
    "evidence_retriever",
    "parameter_extractor",
    "connector",
    "synthesizer",
    "user_agent",
    "note_taker",            # background note-emergence during wrestling
    "challenger",            # adversarial questioner during wrestling
    "grounder",              # grounding-check role
    "tier_assigner",         # rule-based; LLM only for downward adjustment
    "constraint_checker",
    "verifier",              # cross-family verification
)

# Default model tier per role. "flash" = bulk/cheap. "pro" = quality.
# "verify" = cross-family. "synthesis" = highest-quality synthesis.
DEFAULT_ROLE_TIER: Final[dict[str, str]] = {
    "decomposer":           "pro",
    "evidence_retriever":   "flash",
    "parameter_extractor":  "flash",
    "connector":            "pro",
    "synthesizer":          "synthesis",
    "user_agent":           "pro",
    "note_taker":           "flash",
    "challenger":           "pro",
    "grounder":             "flash",
    "tier_assigner":        "flash",
    "constraint_checker":   "flash",
    "verifier":             "verify",
}

# --- Context-pack budgets -------------------------------------

# Most invocations run short-context; long context is a tactical
# resource for synthesis steps that genuinely require it.
DEFAULT_CONTEXT_BUDGET_TOKENS: Final[int] = 64_000
SYNTHESIS_CONTEXT_BUDGET_TOKENS: Final[int] = 256_000
LONG_CONTEXT_CEILING_TOKENS: Final[int] = 1_000_000   # only when justified

# --- Skill versioning -----------------------------------------

DOMAIN_SKILLS: Final[tuple[str, ...]] = (
    "quantum-knowledge",
    "defense-knowledge",
    "ai-infrastructure-knowledge",
    "semiconductor-knowledge",
)

# How many times a process pattern must be re-derived before the
# orchestrator proposes codifying it as a process skill.
PROCESS_SKILL_PROPOSAL_THRESHOLD: Final[int] = 3


# ============================================================
# Bookkeeping
# ============================================================

# Bump this whenever any constant above changes. The orchestrator stamps
# this into model_versions_json so a backtest can detect parameter drift
# between then and now.
#
# 0.0.1-scaffold → 0.1.0: substrate migration from Researchmaxx v1.1.0
#                         (2026-05-16). Adopts Sections A–G verbatim;
#                         adds Section H Antiek-specific values; folds
#                         DeepBlu-lineage claim classes into Section D.

ANTIEK_PARAM_VERSION: Final[str] = "0.1.0"
