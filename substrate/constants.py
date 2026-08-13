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

from typing import Final, NamedTuple

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


# C.5 Curated tier-3 news allowlist. Per Exa-spec §6.6 this lives
# at the substrate level (not in the Exa adapter) because tier
# assignment is a substrate decision, not a search-API decision.
# Adding entries is operator-edited; no automatic learning. Edit
# this tuple directly to allow a new outlet at tier 3 instead of
# the default tier 4.
CURATED_NEWS_TIER_3: Final[frozenset[str]] = frozenset({
    "nytimes.com",
    "wsj.com",
    "ft.com",
    "bloomberg.com",
    "reuters.com",
    "economist.com",
    "theatlantic.com",
    "newyorker.com",
    "washingtonpost.com",
    "apnews.com",
})

# C.6 Tier-2 known-good research host allowlist. Suffix-matched
# host families (".gov", ".edu", ".ac.uk") + the explicit `doi.org`
# are handled at the predicate site; this set is for named non-
# suffix hosts that should still resolve to tier 2.
RESEARCH_HOSTS_TIER_2: Final[frozenset[str]] = frozenset({
    "arxiv.org",
    "ssrn.com",
    "biorxiv.org",
    "medrxiv.org",
})


# C.7 Acquisition-layer daily budget caps. Per the Exa-spec §13.2 the
# **total** acquisition spend across all providers is bounded at this
# combined cap, enforced before any per-provider cap takes effect. The
# combined cap defends against "Exa $5 + Browserbase $5 + future
# provider $5 = $15 silent drift" — when a new provider lands, the
# operator must consciously lift this total or the spend stays
# bounded.
TOTAL_ACQUISITION_BUDGET_USD: Final[float] = 10.0


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


# ── DRW SPR-01 — controlled relation vocabulary for insight/question nodes ──
# The graph's ``edges.relation`` column is free-form TEXT, but the two new
# atomic node types (insight, question) earn a *closed* relation set so
# structural gap detection (SPR-07) can query by relation name without
# guessing at spelling drift. Promotion code references these constants —
# never a hardcoded string — so a typo is a NameError, not a silent
# orphan edge.
#
# Every edge is node->node (``edges.source_node_id`` / ``target_node_id``
# are both NOT NULL FKs to ``nodes``). Two provenance facts therefore do
# NOT appear here as relations, because their target is not a node:
#   * the *investigation* an insight/question came from — carried by the
#     ``GRAPH_NODE_INSERTED`` event envelope's ``investigation_id`` and in
#     node ``metadata`` (the spec's "derived_from"/"raised_by" intent);
#   * the *document/chunk* that grounds an insight — carried by the
#     edge's own ``source_document_id`` / ``chunk_id`` columns on a
#     ``supported_by`` edge (so the spec's "supported_by -> document"
#     intent is preserved without a phantom document node).
class InsightQuestionRelation(NamedTuple):
    relation: str
    source_type: str            # node_type the edge originates from
    target_types: tuple[str, ...]  # node_types the edge may point at
    why: str


# All non-insight/question node types, for relations that may point at any
# substantive node (e.g. a question can ask about any graph entity).
_ALL_SUBSTANTIVE_NODE_TYPES: Final[tuple[str, ...]] = (
    "entity", "organization", "person", "property",
    "metric", "mechanism", "claim", "method", "constraint",
)

INSIGHT_QUESTION_RELATIONS: Final[tuple[InsightQuestionRelation, ...]] = (
    InsightQuestionRelation(
        "supported_by", "insight", _ALL_SUBSTANTIVE_NODE_TYPES,
        "An insight is evidenced by the claim/entity nodes it rests on; the "
        "edge also carries source_document_id + chunk_id for the originating "
        "source. The primary, near-universal case is insight -> claim.",
    ),
    InsightQuestionRelation(
        "contradicts", "insight", ("claim", "insight"),
        "An insight stands against a claim or another insight. SPR-07 reads "
        "this relation to surface contradictions as structural gaps.",
    ),
    InsightQuestionRelation(
        "refines", "insight", ("insight",),
        "A living note's newer version refines the one it supersedes "
        "(SPR-03). Lets the reading surface show note lineage without "
        "losing the prior text from the graph.",
    ),
    InsightQuestionRelation(
        "asks_about", "question", _ALL_SUBSTANTIVE_NODE_TYPES + ("insight",),
        "What a question concerns — any substantive node or an insight. "
        "SPR-07 finds 'unanswered question' gaps by questions whose "
        "asks_about target has no resolving insight.",
    ),
    InsightQuestionRelation(
        "resolved_by", "question", ("insight",),
        "The insight that answers a question. Document-level resolution "
        "rides on the edge's source_document_id; insight resolution is the "
        "node->node case here.",
    ),
)

# ── AFF SPR-07 — the cross-investigation dedup self-edge relation ──
# A candidate unit that near-duplicates an EXISTING unit links to the survivor
# (a ``duplicate_of`` edge) instead of inserting a new row, so the graph
# compounds rather than bloats. The candidate's source/provenance rides the
# edge's ``source_document_id`` / ``chunk_id`` so citations + reuse-credit
# accrue to the SURVIVING unit. The edge is IDENTITY-based, NOT trust-based
# (SPR-08 owns trust) and never widens the survivor's §9.0 servability.
#
# This is a same-node_type SELF-edge (insight->insight, question->question),
# DISTINCT from the closed provenance vocabulary above
# (``INSIGHT_QUESTION_RELATIONS`` / ``validate_insight_question_edge``), which
# is keyed by a single (relation -> source_type) and cannot carry one relation
# with two source types. So ``duplicate_of`` is its own named constant the
# deposit path references (never a hardcoded string — a typo is a NameError),
# and the deposit path inserts the edge directly through the single writer with
# explicit, type-correct source/target node ids. It rides the existing
# ``GRAPH_EDGE_INSERTED`` ActionType (``edges.relation`` is free-form TEXT, the
# ``GraphEdgeInsertedPayload.relation`` field is a free-form ``str``) — so there
# is NO new ActionType, NO narrateEvent rule change, and NO
# EVENT_SCHEMA_VERSION bump.
DUPLICATE_OF_RELATION: Final[str] = "duplicate_of"

# Fast membership + validation surface for the promotion functions.
INSIGHT_QUESTION_RELATION_NAMES: Final[frozenset[str]] = frozenset(
    r.relation for r in INSIGHT_QUESTION_RELATIONS
)
_INSIGHT_QUESTION_RELATION_BY_NAME: Final[dict[str, InsightQuestionRelation]] = {
    r.relation: r for r in INSIGHT_QUESTION_RELATIONS
}


def validate_insight_question_edge(
    relation: str, source_type: str, target_type: str
) -> None:
    """Raise ``ValueError`` if ``(relation, source_type, target_type)`` is
    not in the controlled vocabulary. The promotion functions call this so
    a malformed edge fails loudly at write time rather than landing a
    silently-untraversable relation in the graph."""
    spec = _INSIGHT_QUESTION_RELATION_BY_NAME.get(relation)
    if spec is None:
        raise ValueError(
            f"unknown insight/question relation {relation!r}; allowed: "
            f"{sorted(INSIGHT_QUESTION_RELATION_NAMES)}"
        )
    if source_type != spec.source_type:
        raise ValueError(
            f"relation {relation!r} originates from {spec.source_type!r}, "
            f"not {source_type!r}"
        )
    if target_type not in spec.target_types:
        raise ValueError(
            f"relation {relation!r} cannot point at a {target_type!r} node; "
            f"allowed targets: {spec.target_types}"
        )


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
    "interviewer",           # speak vertical (async_interview + orchestrator)
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
    "interviewer":          "pro",
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
# Section I — Read workflow: servable-corpus legal gate (§9.0 / §9.10)
# ============================================================
#
# The Read workflow ("Spotify for books") serves book full text ONLY for
# content whose license permits it. The binding minimum (master-spec §9.0
# retrieval-time gating + §9.10 publisher consent) is encoded as a
# deny-by-default gate over the EXISTING ``documents.content_class``
# column — the same column the chunk-search G1 gate keys off in
# ``substrate/graph/search.py``. There is deliberately NO second
# servability column: a parallel status would drift from G1, and a gate
# that can drift is a gate that fails open. Servability is DERIVED from
# content_class (+ a book-level takedown override), never stored
# authoritatively beside it.
#
# Legal lineage: *Hachette v. Internet Archive* (2nd Cir. 2024) killed
# the structural fair-use defence for aggregate-and-serve; *Bartz v.
# Anthropic* (~$1.5B settlement) priced post-serve damages far above
# the cost of pre-serve gating. The lesson encoded here: serve full text
# only for public-domain, platform-authored, or publisher-opted-in
# content, and deny by default for everything else (including unknown /
# NULL provenance and anything aggregated from online).

# Content classes whose FULL TEXT may be served by the Read workflow.
# This is an ALLOWLIST (deny-by-default), intentionally STRICTER than the
# chunk-search gate's denylist in search.py (where NULL content_class
# passes as legacy/grandfathered). Serving a whole book full-text is a
# higher-liability act than returning a ≤500-char research snippet, so
# unknown / NULL / restricted content resolves to metadata-only here.
#
# Maps to the documents.content_class vocabulary (schema.py V2 §18):
#   public_domain             → out-of-copyright / CC0 dedication; servable
#   user_owned                → platform/operator-authored (Write workflow); servable
#   user_public_contribution  → user-posted to public graph (§13.9); servable
#   opt_in_licensed           → publisher claimed via §9.10 opt-in; servable
#   source_declared_open      → source-declared open license (CC-BY / CC-BY-SA);
#                               servable; NOT a §9.10 opt-in and NOT public domain
# Everything else (restricted_pending_opt_in, NULL, unrecognised) is
# gated to metadata-only and never served full text.
SERVABLE_CONTENT_CLASSES: Final[frozenset[str]] = frozenset({
    "public_domain",
    "user_owned",
    "user_public_contribution",
    "opt_in_licensed",
    "source_declared_open",
})

# ── The fourth rights state: personal_reading (Personal-Reading Lane SPR-01) ──
#
# The first three rights states answer "may Antiek serve this body to the
# public / accrue ad attribution / train on it?":
#   * SERVABLE_CONTENT_CLASSES (above)        → yes, full body servable
#   * restricted_pending_opt_in (gated)       → body withheld, EARNS to escrow
#                                               (a copyrighted-but-public work
#                                               whose holder may still onboard)
#   * user_owned                              → private operator/Write content,
#                                               servable to its owner, not public
#
# personal_reading is the FOURTH state and it is categorically different from
# all three: it is third-party copyrighted content the OWNER fetched for their
# OWN reading (a Paul Graham essay, a YouTube transcript, a subscribed Substack
# post, the owner's own tweets). It has NO positive rights basis that would let
# Antiek serve it publicly or monetize it, AND — unlike restricted_pending_opt_in
# — it must NEVER earn (there is no rights-holder onboarding flow that would ever
# release escrow on content the owner ingested for private reading). It is:
#   * NOT in SERVABLE_CONTENT_CLASSES         → never served full text publicly
#   * a member of NON_ATTRIBUTABLE_CONTENT_CLASSES (collective_graph/eligibility)
#                                             → zero ad attribution, zero IP escrow
#   * ABSENT from PUBLIC_GRAPH_CONTENT_CLASSES (ad_inventory/attribution)
#                                             → monetization_eligible() is False
#   * excluded from the public chunk-search gate (graph/search.py) on any
#     non-privileged policy_tag                → does not surface on monetized reads
#   * a member of NON_TRAINABLE_CONTENT_CLASSES → never enters an SFT/RL export
#   * readable IN FULL only on the owner / operator_only path
# This is the §9.0 (Hachette / Bartz) discipline applied to the ambient-ingest
# reading path the books family already protects for the corpus path.
PERSONAL_READING_CONTENT_CLASS: Final[str] = "personal_reading"

# The document_type strings the third-party ingest connectors emit. A document
# of one of these types lands personal_reading by default (the insert_document
# deny-by-default guard, substrate/graph/ops.py) UNLESS the connector passes an
# explicit positive content_class (e.g. a verified public_domain Project
# Gutenberg text). "web_article" (acquisition/urls), "video_transcript"
# (acquisition/youtube) and "social_thread" (acquisition/twitter) are verified
# against the live connectors; "newsletter_post" is reserved for SPR-06 Substack.
# These are the EXACT types the deny-by-default guard is scoped to — a genuine
# operator upload (book / paper / user_owned) is NOT here and keeps its existing
# behaviour (NULL content_class stays NULL; the schema default is untouched).
THIRD_PARTY_DOCUMENT_TYPES: Final[frozenset[str]] = frozenset({
    "web_article",
    "video_transcript",
    "social_thread",
    "newsletter_post",
})

# The content classes the OWNER may read in full on their personal / operator
# path: everything publicly servable PLUS personal_reading. Defined as a strict
# superset of SERVABLE_CONTENT_CLASSES by exactly one element so the owner read
# path never has to enumerate the servable set itself (and cannot drift from it).
# This is the READ-side allowlist for the owner/privileged full-body serve — the
# public serve path stays on SERVABLE_CONTENT_CLASSES (narrower), never this.
PERSONAL_READABLE_CONTENT_CLASSES: Final[frozenset[str]] = (
    SERVABLE_CONTENT_CLASSES | {PERSONAL_READING_CONTENT_CLASS}
)

# personal_reading is owner-readable but NEVER publicly servable. This module-
# level assertion makes a future edit that adds it to the servable allowlist
# fail loudly AT IMPORT TIME — the §9.0 serve gate is too load-bearing to let it
# drift silently into the servable set.
assert PERSONAL_READING_CONTENT_CLASS not in SERVABLE_CONTENT_CLASSES, (
    "personal_reading must NOT be in SERVABLE_CONTENT_CLASSES — it is the "
    "owner-readable / public-non-servable lane (Personal-Reading Lane SPR-01). "
    "If you intend a work to be publicly servable, give it a positive rights "
    "class (public_domain / source_declared_open / opt_in_licensed), not "
    "personal_reading."
)
assert (
    SERVABLE_CONTENT_CLASSES | {PERSONAL_READING_CONTENT_CLASS}
) == PERSONAL_READABLE_CONTENT_CLASSES and len(PERSONAL_READABLE_CONTENT_CLASSES) == len(SERVABLE_CONTENT_CLASSES) + 1, (
    "PERSONAL_READABLE_CONTENT_CLASSES must be SERVABLE_CONTENT_CLASSES plus "
    "exactly personal_reading (a strict superset by one element)."
)

# source-declared open license (CC-BY / CC-BY-SA found in source metadata);
# servable; NOT a §9.10 publisher opt-in and NOT public domain. Distinct from
# opt_in_licensed (which means EXACTLY "a publisher claimed the work via the
# §9.10 opt-in flow") so the reader display and the rev-share payout gate read
# a truthful provenance: the open license was declared AT THE SOURCE, not
# claimed by a publisher.
SOURCE_DECLARED_OPEN_CONTENT_CLASS: Final[str] = "source_declared_open"

# The documents.content_class value that means "gated": withheld from
# full-text serving AND from the ad/attribution chunk-retrieval path,
# but retrievable on private_research / operator_only paths (master-spec
# §9.0). MUST be a member of search.py's RESTRICTED_CONTENT_CLASSES — the
# two name the same gate state from the write side and the read side.
# This is the deny-by-default landing zone for any book with unknown or
# unestablished rights (including "aggregated from online").
GATED_DEFAULT_CONTENT_CLASS: Final[str] = "restricted_pending_opt_in"

# Content classes that NEVER enter a training / RL data export (Personal-Reading
# Lane SPR-01 M4). There is no content_class-selecting SFT/RL export in the tree
# TODAY — substrate/loop_3/ is a budget/loop + trajectory-harvest runner; it
# never materializes document bodies by content_class — so this is a GUARD-RAIL
# constant, NOT a filter currently applied to a live export. It is the ready-made
# denylist the future export author imports instead of hand-rolling a literal
# list: it excludes BOTH personal_reading (the owner's private third-party
# reading — never trainable) AND restricted_pending_opt_in (gated
# copyrighted-but-public content — body withheld, never trainable). Defined here
# (after GATED_DEFAULT_CONTENT_CLASS resolves) via an explicit union so it can
# never silently diverge from the gated-class name.
NON_TRAINABLE_CONTENT_CLASSES: Final[frozenset[str]] = frozenset({
    PERSONAL_READING_CONTENT_CLASS,
    GATED_DEFAULT_CONTENT_CLASS,
})

# The content_class a book is moved to on takedown. It is the SAME gate
# state as the gated default — a removal demand restricts the content
# exactly as an unknown-rights book is restricted — but the two are kept
# as distinct named constants because they document distinct intents, and
# takedown additionally sets the book_assets.taken_down flag (which the
# servability projection treats as TAKEN_DOWN, not merely gated). Reusing
# the existing restricted gate means no new gating mechanism is
# introduced; the original content_class is saved on the book_assets row
# so takedown is reversible (master-spec §9.10 30-day removal SLA; Bartz
# pre-serve-takedown discipline).
TAKEDOWN_CONTENT_CLASS: Final[str] = GATED_DEFAULT_CONTENT_CLASS

# The presentation vocabulary the library + reader surfaces render. These
# are DERIVED from (content_class, taken_down) by
# substrate.books.servability.servability_of — they are not a stored
# column. The order is the deny-by-default reading order: the first three
# serve full text, the last two do not.
BOOK_SERVABILITY_STATUSES: Final[tuple[str, ...]] = (
    "public_domain",       # out-of-copyright / CC0; full text servable
    "platform_authored",   # operator/Write-workflow authored; servable
    "publisher_opted_in",  # publisher claimed via §9.10 opt-in; servable
    "source_declared_open",  # source-declared open license (CC-BY / CC-BY-SA); servable
    "gated_metadata_only",  # default: metadata/snippet only, full text withheld
    "taken_down",          # removed on demand; full text purged
    # owner-reads-in-full / public-non-servable (Personal-Reading Lane SPR-01).
    # NOT in the first-three serve group — the public surface renders this as
    # "your reading" (owner-only), never a publicly servable status. Distinct
    # from gated_metadata_only so the library can render it differently (the
    # owner CAN read it in full; a gated book they cannot).
    "personal_readable",
)

# The default servability for a freshly-ingested book with no established
# license — including anything aggregated "from online" with unknown
# rights. Deny-by-default is the whole point of this gate.
BOOK_DEFAULT_SERVABILITY: Final[str] = "gated_metadata_only"

# Max characters of body text returned for a NON-servable (gated) book.
# This is the legally load-bearing line between "snippet view" and
# "full-text serving": *Authors Guild v. Google* (2d Cir. 2015) upheld
# bounded snippet view of in-copyright books as fair use, while *Hachette
# v. Internet Archive* (2024) enjoined serving full text. A gated book
# therefore returns at most this many characters; a servable book returns
# the whole body. Zero would mean "metadata only, no body at all" — we
# keep a small snippet because the Google precedent blesses it and it
# makes the library useful without crossing the line.
SERVE_SNIPPET_MAX_CHARS: Final[int] = 500


# ============================================================
# Section J — Read workflow: ad-border economics (SPR-05 / SPR-09)
# ============================================================
#
# "Spotify for books" runs ads at the border of each page window from v1,
# even with zero buyers, accruing an attention-share ledger to each book's
# rights holder. Accrual is NOT disbursement: escrow accrues, payout stays
# gated on G2 (lawyer review) + G3 (publisher opt-in). These constants
# define the impression/attention semantics precisely so SPR-09's accrual
# rests on auditable definitions (defensibility).

# Attention ("dwell") is counted only when a slot stays continuously
# visible for at least this many milliseconds WHILE the tab is focused.
# Below this, a slot scrolling past is an impression but not attention.
# Tuned to "a reader actually rested on the border", not a scroll-by.
READER_ATTENTION_DWELL_MS: Final[int] = 1000

# Border positions that never obstruct the reading column. TOP/BOTTOM are
# the v1 default (a single reading column with ad rails above/below the
# page window); LEFT/RIGHT are permitted only on wide viewports where the
# reading column has margin to spare. The reading column is sacred — an
# ad never narrows it on a small screen.
READER_AD_SLOT_POSITIONS: Final[tuple[str, ...]] = ("top", "bottom", "left", "right")
READER_AD_SLOT_POSITIONS_DEFAULT: Final[tuple[str, ...]] = ("top", "bottom")

# Targeting signal allowlist (SPR-05 M5). Ad targeting may use ONLY these
# book-metadata signals — never the gated full text of a book, and never
# anything derived from a reader's private notes. A gated book contributes
# only its document_type + topic metadata, never its body. This is the
# privacy + legal-gate boundary for targeting; the DP posture (§16) caps
# any aggregate claim at ε ≤ 10 (enforced in substrate/dp_shuffler/, not
# here — this allowlist is the per-impression input boundary).
READER_TARGETING_SIGNAL_ALLOWLIST: Final[frozenset[str]] = frozenset({
    "document_type",   # 'book'
    "topic",           # coarse subject tag from metadata
    "author",          # surface author for contextual match
    "servability",     # public_domain / publisher_opted_in / …
})

# The recipient bucket for ad revenue attributed to a book whose rights
# holder is unknown (ip_holder_id IS NULL). Revenue accrues here, FLAGGED
# as unattributed, rather than to a wrong holder — and never disburses.
UNATTRIBUTED_RIGHTS_BUCKET: Final[str] = "__unattributed__"


# ============================================================
# Section K — Eval ablation thresholds (Eval-discipline SPR-01)
# ============================================================
# The pure ablation primitive (substrate/eval/ablation.py) turns one varied
# factor + a noise estimate into one of three verdicts. These are the ONLY
# knobs — every other number in a report is computed from the inputs.

# The verdict multiplier: |Δ| must exceed σ·noise for "factor_related". 2σ
# ≈ 2.5% one-sided false-positive under a Gaussian — defensible without
# being a vibes-confirmer. Surface this choice in any handoff that relies on
# a verdict; do not silently relax it.
ABLATION_VERDICT_SIGMA: Final[float] = 2.0

# Minimum replicate-sample count (baseline + treatment combined) before the
# pooled-stdev noise estimate is trusted. Below this, fall back to an
# operator override, else the verdict is inconclusive.
ABLATION_MIN_SAMPLES_FOR_NOISE: Final[int] = 2

# A noise estimate at or below this floor is treated as inconclusive: an
# identically-zero stdev (identical replicates) would manufacture false
# certainty (|Δ| > 0 ⇒ "factor_related" at infinite σ). Refuse to verdict.
ABLATION_INCONCLUSIVE_NOISE_FLOOR: Final[float] = 1e-9


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

# 0.1.0 → 0.2.0: eval-discipline SPR-01 — adds Section K ablation thresholds
#                (ABLATION_VERDICT_SIGMA, ABLATION_MIN_SAMPLES_FOR_NOISE,
#                ABLATION_INCONCLUSIVE_NOISE_FLOOR). No existing constant
#                changed; the ablation primitive stamps this into every report.

ANTIEK_PARAM_VERSION: Final[str] = "0.2.0"
