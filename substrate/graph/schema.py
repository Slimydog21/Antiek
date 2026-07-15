"""Antiek knowledge-graph schema (Sprint 3 Day 1-2 migration).

Subset of the Researchmaxx v2 schema, restricted to the four core
tables the graph layer needs:

- ``documents`` — primary sources, tier-classified
- ``chunks``    — content-addressed text chunks with optional embeddings
- ``nodes``     — typed graph entities
- ``edges``     — directed relationships with temporal validity

What's deferred from the Researchmaxx schema (and why):

- ``syntheses`` + ``synthesis_substrate_manifest`` — landed Sprint 10
  day 4-5 (backtest DB closure). ``middleware/archive/`` writes these.
- ``outcomes`` — landed Sprint 10 day 4-5. ``middleware/outcomes/``
  writes these.
- ``chunk_tier_overrides`` — landed Sprint 10 day 4-5. Recorded by
  the source_tier override emit path; backtest reads from here.
- ``investigations`` — DEFERRED. Investigations are reconstructable
  from the typed event stream (``investigation.start_requested`` +
  trajectory walk); a dedicated table is redundant until a query
  pattern forces it.
- ``chunks_effective_tier`` view — DEFERRED until a downstream
  consumer needs the override+document tier join inline.
- ``embeddings_meta`` — chunk-vector provider/model/dimension pinning.

VARIANT vs TEXT: Researchmaxx uses ``VARIANT`` (DuckDB v1.5.0+ storage)
for metadata columns to enable JSON SQL queries. Antiek uses ``TEXT``
for v1 — every metadata read goes through application code that
``json.loads`` it, so we don't pay the VARIANT storage-version dance
yet. Upgrade lands when middleware needs JSON-shaped WHERE clauses.

Storage discipline: every write must go through
``runtime/db_lock.connect_write`` per architecture_notes §2.3
(the only-writer invariant). ``init_database`` enforces this — pass a
``LockedConnection`` or use ``init_database_at_path``.
"""

from __future__ import annotations

import contextlib
import os
import sys

import duckdb

# Import the canonical write-locker from Sprint 1 day-2. Same flock
# discipline; this is the Quack v2.0 swap point.
try:
    from ...runtime.db_lock import LockedConnection, connect_write
except ImportError:  # pragma: no cover — direct-script fallback
    _here = os.path.dirname(os.path.abspath(__file__))
    sys.path.insert(0, os.path.dirname(os.path.dirname(_here)))
    from runtime.db_lock import LockedConnection, connect_write  # type: ignore[no-redef]


# The schema script. Idempotent — every CREATE uses IF NOT EXISTS so
# rerunning is safe. CHECK constraints make malformed inserts fail
# loudly at the DB layer; the typed Pydantic payloads enforce the same
# constraints at the application layer.
ANTIEK_GRAPH_SCHEMA_V1_SQL = """
-- ============================================================
-- Documents — primary sources at ingestion time
-- ============================================================
CREATE TABLE IF NOT EXISTS documents (
    document_id      TEXT PRIMARY KEY,
    source_uri       TEXT,
    title            TEXT,
    author           TEXT,
    published_at     TIMESTAMP,
    acquired_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_tier      INTEGER NOT NULL CHECK (source_tier BETWEEN 1 AND 5),
    document_type    TEXT NOT NULL,
    investigation_id TEXT,
    raw_text         TEXT,
    metadata         TEXT,         -- JSON string; VARIANT upgrade deferred
    -- Sprint 11 multi-user schema prep: every row carries an owner_user_id
    -- defaulting to a single-operator constant. The substrate stays
    -- single-user today; multi-user lands by changing the application
    -- layer's filter without schema migration. See master-product-spec
    -- §13 (account model + network effects).
    owner_user_id    TEXT NOT NULL DEFAULT '__operator__'
);

-- ============================================================
-- Chunks — content-addressed text segments
-- ============================================================
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id      TEXT PRIMARY KEY,
    document_id   TEXT NOT NULL REFERENCES documents(document_id),
    chunk_index   INTEGER NOT NULL,
    section_path  TEXT,
    text          TEXT NOT NULL,
    embedding     FLOAT[],          -- nullable; populated by processing/embedding
    token_count   INTEGER NOT NULL DEFAULT 0
);

-- ============================================================
-- Nodes — typed graph entities
-- ============================================================
CREATE TABLE IF NOT EXISTS nodes (
    node_id          TEXT PRIMARY KEY,
    canonical_label  TEXT NOT NULL,
    -- DRW SPR-01 adds 'insight' + 'question' (the two atomic units of
    -- distilled truth). Fresh DBs created from this constant get them
    -- directly; pre-existing prod DBs are upgraded by
    -- migrate_v9_insight_question (DuckDB cannot ALTER a CHECK in place,
    -- so that migration rebuilds the table). Keep this list in lock-step
    -- with substrate/schemas/events.NodeType and the rebuilt-table CHECK
    -- in migrate_v9_insight_question._NODES_REBUILD_SQL.
    node_type        TEXT NOT NULL CHECK (node_type IN (
        'entity', 'organization', 'person', 'property',
        'metric', 'mechanism', 'claim', 'method', 'constraint',
        'insight', 'question'
    )),
    embedding        FLOAT[],
    graph_scope      TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached    INTEGER NOT NULL DEFAULT 0,
    metadata         TEXT,
    owner_user_id    TEXT
);

-- ============================================================
-- Edges — directed relationships, temporal validity
-- ============================================================
CREATE TABLE IF NOT EXISTS edges (
    edge_id                TEXT PRIMARY KEY,
    source_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    target_node_id         TEXT NOT NULL REFERENCES nodes(node_id),
    relation               TEXT NOT NULL,
    chunk_id               TEXT REFERENCES chunks(chunk_id),
    source_document_id     TEXT REFERENCES documents(document_id),
    source_tier            INTEGER NOT NULL
        CHECK (source_tier BETWEEN 1 AND 5),
    extraction_confidence  FLOAT NOT NULL
        CHECK (extraction_confidence >= 0 AND extraction_confidence <= 1),
    extracted_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    valid_from             TIMESTAMP NOT NULL DEFAULT '1970-01-01',
    valid_until            TIMESTAMP,
    superseded_by          TEXT REFERENCES edges(edge_id),
    graph_scope            TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    investigation_id       TEXT,
    metadata               TEXT
);

-- ============================================================
-- Indexes
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_documents_tier ON documents(source_tier);
CREATE INDEX IF NOT EXISTS idx_documents_inv  ON documents(investigation_id);
CREATE INDEX IF NOT EXISTS idx_chunks_document ON chunks(document_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type    ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_scope   ON nodes(graph_scope);
CREATE INDEX IF NOT EXISTS idx_nodes_label   ON nodes(canonical_label);
CREATE INDEX IF NOT EXISTS idx_nodes_degree  ON nodes(degree_cached);
CREATE INDEX IF NOT EXISTS idx_edges_source  ON edges(source_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_target  ON edges(target_node_id);
CREATE INDEX IF NOT EXISTS idx_edges_scope   ON edges(graph_scope);
CREATE INDEX IF NOT EXISTS idx_edges_valid   ON edges(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_edges_chunk   ON edges(chunk_id);
CREATE INDEX IF NOT EXISTS idx_edges_document ON edges(source_document_id);
CREATE INDEX IF NOT EXISTS idx_edges_confidence ON edges(extraction_confidence);
CREATE INDEX IF NOT EXISTS idx_edges_tier    ON edges(source_tier);

-- ============================================================
-- Syntheses — archived Loop 1 outputs (Sprint 10 day 4-5)
-- ============================================================
-- The SOLE writer is middleware/archive/archive_synthesis_via_db.
-- The status + implicit_recommendation CHECK lists MUST agree with
-- the Pydantic SynthesisStatus + SynthesisRecommendation literals
-- (drift test in tests/test_backtest_db.py).
CREATE TABLE IF NOT EXISTS syntheses (
    synthesis_id              TEXT PRIMARY KEY,
    investigation_id          TEXT,
    target_question           TEXT NOT NULL,
    synthesis_timestamp       TIMESTAMP NOT NULL,
    status                    TEXT NOT NULL CHECK (status IN (
        'draft', 'passed', 'regressed',
        'max_iterations_reached', 'escalated'
    )),
    implicit_recommendation   TEXT NOT NULL CHECK (implicit_recommendation IN (
        'proceed', 'pass', 'conditional',
        'undetermined', 'insufficient_evidence'
    )),
    thesis_text               TEXT,
    thesis_token_count        INTEGER NOT NULL DEFAULT 0,
    has_constraint_check_result BOOLEAN NOT NULL DEFAULT FALSE,
    -- JSON columns (TEXT for now; VARIANT upgrade deferred).
    model_versions            TEXT,
    decomposition             TEXT,
    evidence                  TEXT,
    parameters                TEXT,
    substrate                 TEXT,
    thesis                    TEXT,
    agent_trace               TEXT,
    constraint_history        TEXT,
    constraint_check_result   TEXT,
    archived_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- Substrate manifest — what each synthesis pinned (per-entity rows)
-- ============================================================
CREATE TABLE IF NOT EXISTS synthesis_substrate_manifest (
    synthesis_id   TEXT NOT NULL REFERENCES syntheses(synthesis_id),
    entity_kind    TEXT NOT NULL CHECK (entity_kind IN (
        'document', 'chunk', 'node', 'edge'
    )),
    entity_id      TEXT NOT NULL,
    pinned_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (synthesis_id, entity_kind, entity_id)
);

-- ============================================================
-- Outcomes — observer-recorded post-hoc analysis of a synthesis
-- ============================================================
-- The SOLE writer is middleware/outcomes/record_outcome_via_db.
-- The sub-list/object payloads ride as TEXT-JSON columns; the typed
-- Pydantic OutcomeRecordedPayload is the canonical schema (drift
-- test enforces parity).
CREATE TABLE IF NOT EXISTS outcomes (
    outcome_id                  TEXT PRIMARY KEY,
    synthesis_id                TEXT NOT NULL REFERENCES syntheses(synthesis_id),
    observer                    TEXT NOT NULL,
    observed_at                 TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    thesis_outcomes             TEXT,    -- JSON array
    falsification_outcomes      TEXT,    -- JSON array
    execution_risk_outcomes     TEXT,    -- JSON array
    decision_alignment          TEXT,    -- JSON object (nullable)
    notes                       TEXT
);

-- ============================================================
-- Chunk tier overrides — append-only audit of post-ingestion retiering
-- ============================================================
CREATE TABLE IF NOT EXISTS chunk_tier_overrides (
    chunk_id         TEXT NOT NULL REFERENCES chunks(chunk_id),
    original_tier    INTEGER NOT NULL CHECK (original_tier BETWEEN 1 AND 5),
    override_tier    INTEGER NOT NULL CHECK (override_tier BETWEEN 1 AND 5),
    reason           TEXT NOT NULL,
    set_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    set_by           TEXT,
    PRIMARY KEY (chunk_id, set_at)
);

-- ============================================================
-- Creation surface (Sprint 13) — deliverables, sections, block links
-- ============================================================
-- A deliverable is an operator-assembled document (memo, chapter,
-- brief). Sections within it carry generated prose; section_blocks
-- attaches insight blocks (nodes / claims / notes) to a section in
-- a stable order. The creative_writer role consumes the attached
-- blocks + section title + deliverable kind to generate prose_text.
CREATE TABLE IF NOT EXISTS deliverables (
    deliverable_id        TEXT PRIMARY KEY,
    title                 TEXT NOT NULL,
    deliverable_kind      TEXT NOT NULL CHECK (deliverable_kind IN (
        'research_memo', 'book_chapter', 'biography_section',
        'investor_brief', 'general_essay'
    )),
    investigation_root_id TEXT,
    owner_user_id         TEXT NOT NULL DEFAULT '__operator__',
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    status                TEXT NOT NULL DEFAULT 'draft' CHECK (status IN (
        'draft', 'in_review', 'final'
    )),
    metadata              TEXT
);

CREATE TABLE IF NOT EXISTS deliverable_sections (
    section_id        TEXT PRIMARY KEY,
    deliverable_id    TEXT NOT NULL REFERENCES deliverables(deliverable_id),
    parent_section_id TEXT REFERENCES deliverable_sections(section_id),
    section_index     INTEGER NOT NULL,
    title             TEXT,
    prose_text        TEXT,
    prose_provenance  TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS section_blocks (
    section_id   TEXT NOT NULL REFERENCES deliverable_sections(section_id),
    block_kind   TEXT NOT NULL CHECK (block_kind IN (
        'insight', 'open_question', 'operator_note', 'claim'
    )),
    block_id     TEXT NOT NULL,
    block_index  INTEGER NOT NULL,
    attached_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (section_id, block_kind, block_id)
);

-- ============================================================
-- DeepBlu interviews (Sprint 16) — master spec §11.2
-- ============================================================
-- An interview_project bundles per-informant interviews under one
-- topic. Each interview row tracks one informant's session: invite,
-- consent, transcript document, status.
CREATE TABLE IF NOT EXISTS interview_projects (
    project_id        TEXT PRIMARY KEY,
    title             TEXT NOT NULL,
    topic_description TEXT,
    deliverable_id    TEXT REFERENCES deliverables(deliverable_id),
    interview_guide   TEXT,
    owner_user_id     TEXT NOT NULL DEFAULT '__operator__',
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS interviews (
    interview_id           TEXT PRIMARY KEY,
    project_id             TEXT NOT NULL REFERENCES interview_projects(project_id),
    informant_handle       TEXT,
    informant_email        TEXT,
    invited_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at             TIMESTAMP,
    completed_at           TIMESTAMP,
    transcript_document_id TEXT REFERENCES documents(document_id),
    consent_recorded       BOOLEAN NOT NULL DEFAULT FALSE,
    status                 TEXT NOT NULL DEFAULT 'invited' CHECK (status IN (
        'invited', 'in_progress', 'completed', 'declined', 'incomplete'
    )),
    transcript_turns       TEXT  -- JSON array of {role, text, ts}
);

-- ============================================================
-- Indexes for backtest query patterns
-- ============================================================
CREATE INDEX IF NOT EXISTS idx_syntheses_timestamp ON syntheses(synthesis_timestamp);
CREATE INDEX IF NOT EXISTS idx_syntheses_investigation ON syntheses(investigation_id);
CREATE INDEX IF NOT EXISTS idx_manifest_kind ON synthesis_substrate_manifest(entity_kind);
CREATE INDEX IF NOT EXISTS idx_manifest_entity ON synthesis_substrate_manifest(entity_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_synthesis ON outcomes(synthesis_id);
CREATE INDEX IF NOT EXISTS idx_outcomes_observed ON outcomes(observed_at);
CREATE INDEX IF NOT EXISTS idx_tier_overrides_set_at ON chunk_tier_overrides(set_at);
CREATE INDEX IF NOT EXISTS idx_edges_extracted ON edges(extracted_at);
CREATE INDEX IF NOT EXISTS idx_sections_deliverable ON deliverable_sections(deliverable_id);
CREATE INDEX IF NOT EXISTS idx_section_blocks_section ON section_blocks(section_id);
CREATE INDEX IF NOT EXISTS idx_interviews_project ON interviews(project_id);
CREATE INDEX IF NOT EXISTS idx_interviews_status ON interviews(status);
"""


# Tables this schema creates. Used by tests + the diagnostic CLI.
SCHEMA_TABLES: tuple[str, ...] = (
    "documents", "chunks", "nodes", "edges",
    "syntheses", "synthesis_substrate_manifest",
    "outcomes", "chunk_tier_overrides",
    "deliverables", "deliverable_sections", "section_blocks",
    "interview_projects", "interviews",
    "ip_holders", "notebooks", "notebook_blocks",
    "discovery_cache",
    "url_alias",
    "discovery_summary",
    "book_assets",
    "outline_blocks",
    "monitors",
    "supersession_candidates",
    "embeddings_meta",
    "multimedia_twin_runs",
    "multimedia_distillation_claims",
    "derived_assets",
    "derived_asset_revisions",
    "derived_asset_revision_members",
    "derived_asset_current_revisions",
    "html_projections",
    "derived_asset_merge_drafts",
    "derived_asset_merge_reviews",
)


# Sprint 18 additions — Pre-onboarded IP holder escrow + retrieval-time
# gating + notebook surface. Per master-spec §9.0 + §9.10 + §4.2
# (notebook surface — Wedge 2 linchpin).
ANTIEK_GRAPH_SCHEMA_V2_SPRINT18_SQL = """
-- ============================================================
-- ip_holders — Pre-onboarded IP holder escrow (Sprint 18, §9.10)
-- ============================================================
-- Architecture ships Sprint 18 alongside publisher dashboard. Escrow
-- accrues from Sprint 19 first-cohort outreach (MIT Press, Cambridge,
-- Princeton) but no money routes until first publisher opt-in. The
-- substrate creates the row + accrues escrow; payouts gate strictly
-- on claim_status='claimed' per master-spec §9.10.
CREATE TABLE IF NOT EXISTS ip_holders (
    ip_holder_id              TEXT PRIMARY KEY,
    display_name              TEXT NOT NULL,
    legal_contact_email       TEXT,
    status                    TEXT NOT NULL DEFAULT 'pre_onboarded'
        CHECK (status IN (
            'pre_onboarded',  -- account created; no notification sent
            'invited',        -- notification email sent to legal
            'claimed',        -- publisher opted in; payouts unlock
            'opted_out'       -- publisher opted out; content removal scheduled
        )),
    escrow_balance_usd        DECIMAL(18, 6) NOT NULL DEFAULT 0,
    escrow_account_ref        TEXT,  -- Stripe Connect account ID once claimed
    notification_sent_at      TIMESTAMP,
    claimed_at                TIMESTAMP,
    opted_out_at              TIMESTAMP,
    created_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata                  TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_ip_holders_status ON ip_holders(status);

-- ============================================================
-- documents — content_class + ip_holder_id retrieval-time gate
-- ============================================================
-- Per master-spec §9.0 retrieval-time gating: every retrieval call
-- carries a policy_tag; restricted content returns only when
-- policy_tag in {'private_research', 'operator_only'}.
--
-- content_class values:
--   'public_domain'                 → unrestricted retrieval (incl. CC0 dedication)
--   'opt_in_licensed'               → unrestricted retrieval (publisher claimed via §9.10)
--   'source_declared_open'          → unrestricted retrieval; source-declared open
--                                     license (CC-BY / CC-BY-SA). Servable, NOT a
--                                     §9.10 publisher opt-in and NOT public domain
--   'restricted_pending_opt_in'     → restricted: only retrievable on
--                                     policy_tag in {private_research, operator_only}
--   'user_owned'                    → only the owner_user_id user can retrieve
--   'user_public_contribution'      → user-posted to public graph (§13.9)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_class TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ip_holder_id TEXT;
ALTER TABLE nodes ADD COLUMN IF NOT EXISTS owner_user_id TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_content_class ON documents(content_class);
CREATE INDEX IF NOT EXISTS idx_documents_ip_holder ON documents(ip_holder_id);
CREATE INDEX IF NOT EXISTS idx_nodes_owner ON nodes(owner_user_id);

CREATE TABLE IF NOT EXISTS multimedia_twin_runs (
    run_id               TEXT PRIMARY KEY,
    owner_user_id        TEXT NOT NULL,
    source_document_id   TEXT NOT NULL REFERENCES documents(document_id),
    source_html_sha256   TEXT NOT NULL,
    source_event_id      TEXT NOT NULL,
    distillation_json    TEXT NOT NULL,
    distillation_sha256  TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS multimedia_distillation_claims (
    run_id               TEXT PRIMARY KEY,
    owner_user_id        TEXT NOT NULL,
    source_document_id   TEXT NOT NULL REFERENCES documents(document_id),
    source_html_sha256   TEXT NOT NULL,
    source_event_id      TEXT NOT NULL,
    claim_token          TEXT NOT NULL,
    status               TEXT NOT NULL CHECK (status IN ('in_progress', 'completed')),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at         TIMESTAMP
);

-- ============================================================
-- notebooks — Wedge 2 linchpin (Sprint 18-19, §4.2)
-- ============================================================
-- TipTap-based literate-analysis documents. Substrate references are
-- live-pulled (substrate-is-source-of-truth invariant §13 §16.1
-- REJECTs); the notebook stores reference IDs, the renderer resolves
-- current state at render time.
CREATE TABLE IF NOT EXISTS notebooks (
    notebook_id          TEXT PRIMARY KEY,
    title                TEXT NOT NULL,
    investigation_id     TEXT,  -- optional binding to an investigation
    document_id          TEXT,  -- optional binding to a document (Loop 2 wrestle notebook)
    owner_user_id        TEXT NOT NULL DEFAULT '__operator__',
    content_class        TEXT NOT NULL DEFAULT 'user_owned'
        CHECK (content_class IN (
            'user_owned', 'user_public_contribution'
        )),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata             TEXT  -- JSON
);

CREATE INDEX IF NOT EXISTS idx_notebooks_investigation ON notebooks(investigation_id);
CREATE INDEX IF NOT EXISTS idx_notebooks_document ON notebooks(document_id);
CREATE INDEX IF NOT EXISTS idx_notebooks_owner ON notebooks(owner_user_id);

CREATE TABLE IF NOT EXISTS notebook_blocks (
    block_id             TEXT PRIMARY KEY,
    notebook_id          TEXT NOT NULL REFERENCES notebooks(notebook_id),
    block_index          INTEGER NOT NULL,
    block_type           TEXT NOT NULL
        CHECK (block_type IN (
            'prose',             -- markdown prose
            'region_embed',      -- PDF region selection reference
            'claim_card',        -- claim reference (claim_id)
            'note',              -- note reference (note_id)
            'question_card',     -- open-question reference (question_id)
            'cross_doc_link',    -- bridging note + source/target documents
            'chat_exchange',     -- chat exchange snippet
            'master_md_section', -- MASTER.md section reference
            'image',             -- image artifact reference
            'latex'              -- LaTeX equation
        )),
    ref_id               TEXT,                -- substrate ref (claim_id, note_id, etc); NULL for prose/latex
    content_json         TEXT NOT NULL,       -- TipTap block JSON content
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_notebook_blocks_notebook ON notebook_blocks(notebook_id, block_index);

-- ============================================================
-- loop_3_checklist — Persistent unlock-criteria state (Sprint 30+,
-- master-spec §14.2 + §13.7). One row per criterion. The Trust
-- Center reads this surface; the unlock-env-var gate remains
-- authoritative for training-time work.
-- ============================================================
CREATE TABLE IF NOT EXISTS loop_3_checklist (
    criterion  TEXT PRIMARY KEY,
    met        BOOLEAN NOT NULL DEFAULT FALSE,
    note       TEXT,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- federation_config — Single-row substrate-wide federation policy
-- (master-spec §13.9 Phase 3 + §13.7 audit). Operator updates via the
-- /cross-graph/federation-config endpoint; default is strict (no
-- partners, opt-in + attribution required).
-- ============================================================
CREATE TABLE IF NOT EXISTS federation_config (
    singleton_key TEXT PRIMARY KEY,
    allowed_partner_substrates TEXT,
    require_opt_in_for_outbound_citations BOOLEAN NOT NULL DEFAULT TRUE,
    require_attribution_for_outbound_citations BOOLEAN NOT NULL DEFAULT TRUE,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ============================================================
-- payout_transfers — Persistent log of Stripe Connect transfer
-- attempts (Sprint 30+, master-spec §9.10 + §13.5 + §13.7 audit).
-- One row per RevShareDecision the transfer initiator handles.
-- Status state machine: pending → transferred | skipped_escrow |
-- skipped_platform | failed.
-- ============================================================
CREATE TABLE IF NOT EXISTS payout_transfers (
    transfer_attempt_id     TEXT PRIMARY KEY,
    decision_id             TEXT NOT NULL,
    stripe_transfer_id      TEXT,
    recipient_account_id    TEXT,
    amount_usd_cents        INTEGER NOT NULL,
    status                  TEXT NOT NULL CHECK (status IN (
        'pending', 'transferred', 'skipped_escrow',
        'skipped_platform', 'failed'
    )),
    note                    TEXT,
    initiated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payout_transfers_decision
    ON payout_transfers(decision_id);
CREATE INDEX IF NOT EXISTS idx_payout_transfers_recipient
    ON payout_transfers(recipient_account_id);

-- ============================================================
-- deletion_requests — Persistent log of operator-initiated
-- "delete everything" requests (Sprint 30+, master-spec §13.3).
-- Status state machine: pending → confirmed | cancelled | completed.
-- The 7-day cancellation window lives in code (substrate doesn't
-- auto-confirm); the 30-day SLA from request to completion is the
-- substrate's binding commitment.
-- ============================================================
CREATE TABLE IF NOT EXISTS deletion_requests (
    request_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    status          TEXT NOT NULL DEFAULT 'pending' CHECK (status IN (
        'pending', 'confirmed', 'cancelled', 'completed'
    )),
    requested_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reason          TEXT
);
CREATE INDEX IF NOT EXISTS idx_deletion_requests_user
    ON deletion_requests(user_id);
"""


# Sprint 18 — Exa & Browserbase Wedge 1 — discovery cache (§6.5).
# 24h dedup on the (query, investigation_id, provider, params) tuple
# so the operator doesn't pay twice for an identical search. Hit on
# cache short-circuits the Exa call and returns the prior proposal
# list AS-IS — no re-emission of DiscoveryProposed events (the audit
# trail already recorded what was considered on the first run).
ANTIEK_GRAPH_SCHEMA_V3_DISCOVERY_CACHE_SQL = """
CREATE TABLE IF NOT EXISTS discovery_cache (
    cache_key       TEXT PRIMARY KEY,
    provider        TEXT NOT NULL,
    query           TEXT NOT NULL,
    investigation_id TEXT NOT NULL,
    proposals_json  TEXT NOT NULL,
    cached_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    expires_at      TIMESTAMP NOT NULL,
    result_count    INTEGER NOT NULL DEFAULT 0,
    cost_usd        DOUBLE NOT NULL DEFAULT 0.0
);

CREATE INDEX IF NOT EXISTS idx_discovery_cache_expires
    ON discovery_cache(expires_at);
CREATE INDEX IF NOT EXISTS idx_discovery_cache_investigation
    ON discovery_cache(investigation_id);

-- ============================================================
-- url_alias — requested_url → canonical document_id (Exa-spec §14.2)
-- ============================================================
-- Doc-id collision risk: `final_url` after redirects varies across
-- fetches when sites change canonical slugs. The same logical
-- content can produce two different `url_doc_id` hashes via two
-- different `final_url` values. This alias table records every
-- `requested_url → document_id` we've ingested so the next time
-- the same `requested_url` is encountered, the caller can short-
-- circuit to the canonical doc_id rather than re-ingesting.
--
-- The PRIMARY KEY is on requested_url; document_id can repeat
-- (one document can have many aliases — every URL that redirected
-- to it).
CREATE TABLE IF NOT EXISTS url_alias (
    requested_url   TEXT PRIMARY KEY,
    document_id     TEXT NOT NULL REFERENCES documents(document_id),
    first_seen_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    last_seen_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    seen_count      INTEGER NOT NULL DEFAULT 1
);

CREATE INDEX IF NOT EXISTS idx_url_alias_document
    ON url_alias(document_id);

-- ============================================================
-- discovery_summary — 30-day rollup of DiscoveryProposed events
-- ============================================================
-- Per Exa-spec §14.1, discovery events are retained for 30 days as
-- raw JSONL then rolled up into this summary table. The summary
-- preserves per-(provider, day, query_hash) aggregates so an
-- operator looking at long-term discovery activity can see what
-- queries the agent ran without keeping every individual proposal.
--
-- Source-of-truth boundary: while a day's JSONL is live, raw events
-- are authoritative. Once rolled up (and JSONL truncated), the
-- summary row is authoritative for that day. The rollup function
-- is responsible for not double-counting if it runs twice.
CREATE TABLE IF NOT EXISTS discovery_summary (
    summary_id        TEXT PRIMARY KEY,  -- sha256(provider+day+query_hash)
    provider          TEXT NOT NULL,
    day_utc           DATE NOT NULL,
    query_hash        TEXT NOT NULL,
    query_preview     TEXT,              -- first 200 chars of one query (audit)
    proposal_count    INTEGER NOT NULL DEFAULT 0,
    selected_count    INTEGER NOT NULL DEFAULT 0,
    rejected_by_gate  INTEGER NOT NULL DEFAULT 0,
    rejected_by_op    INTEGER NOT NULL DEFAULT 0,
    fetch_failed      INTEGER NOT NULL DEFAULT 0,
    distinct_urls     INTEGER NOT NULL DEFAULT 0,
    total_cost_usd    DOUBLE NOT NULL DEFAULT 0.0,
    summarized_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_discovery_summary_day
    ON discovery_summary(day_utc);
CREATE INDEX IF NOT EXISTS idx_discovery_summary_provider
    ON discovery_summary(provider);
"""


# Sprint 23-24 + 30+ — Phase 3 persistence. Three append-only state
# stores: federation_partners (cross-instance identity records),
# advertisers (lead-gen advertiser registry), federation_nonces
# (replay-defense ledger). The application-layer registries are
# in-memory mirrors that round-trip against these tables via per-
# module CRUD helpers.
#
# Append-only audit posture: every state change appends a new row
# keyed by an attempt_id (UUID). ``latest()`` queries select the most
# recent record per logical_id. Mirrors the AdvertiserRecord /
# PartnerSubstrate frozen-dataclass design — historical state is
# preserved by construction.
ANTIEK_GRAPH_SCHEMA_V4_PHASE3_SQL = """
CREATE TABLE IF NOT EXISTS federation_partners (
    attempt_id              TEXT PRIMARY KEY,
    partner_id              TEXT NOT NULL,
    display_name            TEXT NOT NULL,
    substrate_url           TEXT NOT NULL,
    shared_secret_hex       TEXT NOT NULL,
    state                   TEXT NOT NULL CHECK (state IN (
        'pending_handshake', 'trusted', 'revoked'
    )),
    registered_at           TIMESTAMP NOT NULL,
    last_state_change_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operator_notes          TEXT NOT NULL DEFAULT '',
    revocation_reason       TEXT,
    row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_federation_partners_partner_id
    ON federation_partners(partner_id, row_inserted_at);
CREATE INDEX IF NOT EXISTS idx_federation_partners_state
    ON federation_partners(state);

CREATE TABLE IF NOT EXISTS advertisers (
    attempt_id              TEXT PRIMARY KEY,
    advertiser_id           TEXT NOT NULL,
    display_name            TEXT NOT NULL,
    contact_email           TEXT NOT NULL,
    verticals               TEXT NOT NULL DEFAULT '',
    audience_intents        TEXT NOT NULL DEFAULT '',
    status                  TEXT NOT NULL CHECK (status IN (
        'pending_review', 'approved', 'active',
        'rejected', 'suspended', 'churned'
    )),
    submitted_at            TIMESTAMP NOT NULL,
    last_status_change_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    operator_notes          TEXT NOT NULL DEFAULT '',
    rejection_reason        TEXT,
    monthly_budget_usd_cents INTEGER,
    row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_advertisers_advertiser_id
    ON advertisers(advertiser_id, row_inserted_at);
CREATE INDEX IF NOT EXISTS idx_advertisers_status
    ON advertisers(status);

CREATE TABLE IF NOT EXISTS federation_nonces (
    nonce            TEXT PRIMARY KEY,
    partner_id       TEXT NOT NULL,
    accepted_at_unix BIGINT NOT NULL,
    expires_at_unix  BIGINT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_federation_nonces_expires
    ON federation_nonces(expires_at_unix);
CREATE INDEX IF NOT EXISTS idx_federation_nonces_partner
    ON federation_nonces(partner_id);
"""


# Sprint 23-24 phase 4 — KYC state machine (master-spec §9.5). Gates
# settlement of any payout strictly above the $10 floor. Append-only
# log; latest() per recipient_ref drives the can_settle gate.
ANTIEK_GRAPH_SCHEMA_V5_KYC_SQL = """
CREATE TABLE IF NOT EXISTS kyc_status (
    attempt_id              TEXT PRIMARY KEY,
    recipient_ref           TEXT NOT NULL,
    state                   TEXT NOT NULL CHECK (state IN (
        'not_started', 'invited', 'in_progress',
        'completed', 'expired', 'rejected'
    )),
    last_state_change_at    TIMESTAMP NOT NULL,
    operator_notes          TEXT NOT NULL DEFAULT '',
    rejection_reason        TEXT,
    stripe_account_ref      TEXT,
    row_inserted_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_kyc_status_recipient_ref
    ON kyc_status(recipient_ref, row_inserted_at);
CREATE INDEX IF NOT EXISTS idx_kyc_status_state
    ON kyc_status(state);

-- Sprint 23-24 phase 4 — annual tax report log. One row per
-- (recipient_ref, tax_year) joining payout totals; emitted-at is the
-- moment the operator generated the 1099 export.
CREATE TABLE IF NOT EXISTS tax_reports (
    report_id               TEXT PRIMARY KEY,
    recipient_ref           TEXT NOT NULL,
    tax_year                INTEGER NOT NULL,
    total_payout_usd_cents  INTEGER NOT NULL,
    above_1099_threshold    BOOLEAN NOT NULL,
    csv_export_path         TEXT,
    emitted_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_tax_reports_recipient_year
    ON tax_reports(recipient_ref, tax_year);
"""


# Sprint 23-24 phase 1+2 — ad inventory persistence + payout decisions
# log + rollover ledger. Closes the "endpoint exists but data dies on
# request return" gap from the prior audit.
ANTIEK_GRAPH_SCHEMA_V6_AD_PERSISTENCE_SQL = """
-- ============================================================
-- ad_inventory_items — operator-curated lead-gen inventory
-- (master-spec §9.4 Option C). Active subset is what the
-- /ad-inventory/select matcher loads at render time.
-- ============================================================
CREATE TABLE IF NOT EXISTS ad_inventory_items (
    inventory_id              TEXT PRIMARY KEY,
    advertiser_id             TEXT NOT NULL,
    advertiser_display_name   TEXT NOT NULL,
    target_topics             TEXT NOT NULL DEFAULT '',
    target_sectors            TEXT NOT NULL DEFAULT '',
    target_sub_sectors        TEXT NOT NULL DEFAULT '',
    target_audience_intents   TEXT NOT NULL DEFAULT '',
    cpm_usd_cents             INTEGER NOT NULL CHECK (cpm_usd_cents >= 0),
    creative_url              TEXT NOT NULL,
    landing_url               TEXT NOT NULL,
    active                    BOOLEAN NOT NULL DEFAULT TRUE,
    created_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_ad_inventory_items_active
    ON ad_inventory_items(active);
CREATE INDEX IF NOT EXISTS idx_ad_inventory_items_advertiser
    ON ad_inventory_items(advertiser_id);

-- ============================================================
-- payout_decisions — every RevShareDecision the PayoutRouter emits.
-- Audit trail under §13.7. Joined against payout_transfers (V4) to
-- show the full impression → decision → transfer chain.
-- ============================================================
CREATE TABLE IF NOT EXISTS payout_decisions (
    decision_id               TEXT PRIMARY KEY,
    impression_id             TEXT NOT NULL,
    kind                      TEXT NOT NULL CHECK (kind IN (
        'creator', 'publisher', 'platform'
    )),
    recipient_ref             TEXT NOT NULL,
    amount_usd_cents          INTEGER NOT NULL CHECK (amount_usd_cents >= 0),
    document_id               TEXT,
    requires_escrow           BOOLEAN NOT NULL DEFAULT FALSE,
    capped_to_daily_limit     BOOLEAN NOT NULL DEFAULT FALSE,
    -- KYC gate result at the moment the decision was emitted.
    -- 'admitted' means the substrate cleared the recipient for
    -- settlement at this amount; 'rolled_over' means the amount
    -- was below the §9.5 floor (no KYC required); 'gated_kyc'
    -- means KYC blocked above-floor settlement; 'gated_fraud'
    -- means the AntiGamingDetector returned BLOCK.
    gate_result               TEXT NOT NULL DEFAULT 'admitted'
        CHECK (gate_result IN (
            'admitted', 'rolled_over', 'gated_kyc', 'gated_fraud'
        )),
    decided_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_payout_decisions_impression
    ON payout_decisions(impression_id);
CREATE INDEX IF NOT EXISTS idx_payout_decisions_recipient
    ON payout_decisions(recipient_ref);
CREATE INDEX IF NOT EXISTS idx_payout_decisions_gate
    ON payout_decisions(gate_result);

-- ============================================================
-- rollover_ledger — persistent per-recipient rolling balance.
-- Survives process restart; backs /creator-payouts/{user_id}'s
-- rollover_balance_cents (previously hard-coded to 0).
-- ============================================================
CREATE TABLE IF NOT EXISTS rollover_ledger (
    recipient_ref               TEXT PRIMARY KEY,
    balance_cents               INTEGER NOT NULL DEFAULT 0
        CHECK (balance_cents >= 0),
    accrual_started_month       INTEGER,  -- months-since-epoch
    state                       TEXT NOT NULL DEFAULT 'accruing'
        CHECK (state IN (
            'accruing', 'notice_sent', 'settled', 'forfeited'
        )),
    last_event_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# Read workflow SPR-01 — book_assets. A book IS a document of
# document_type='book'; this table carries the book-specific structure
# (TOC, pagination, cover) and the takedown override that the
# servable-corpus gate reads. Servability itself is NOT stored here — it
# is derived from documents.content_class (the G1 gate column) by
# substrate.books.servability. What IS stored: the takedown flag (an
# override orthogonal to license), the pre-takedown content_class (so
# takedown is reversible), and the human-readable license basis +
# provenance that let a future maintainer or counsel defend why a given
# book was or wasn't served (master-spec §9.0 / §9.10; Hachette / Bartz).
ANTIEK_GRAPH_SCHEMA_V7_BOOKS_SQL = """
CREATE TABLE IF NOT EXISTS book_assets (
    document_id              TEXT PRIMARY KEY REFERENCES documents(document_id),
    toc_json                 TEXT,                 -- JSON [{title, page_index, level}]
    page_count               INTEGER NOT NULL DEFAULT 0,
    pagination_scheme        TEXT NOT NULL DEFAULT 'pdf_page',  -- locator vocabulary
    cover_uri                TEXT,
    -- Provenance + the human-readable reason for the document's
    -- content_class. These exist for defensibility: a book's servability
    -- decision must survive scrutiny months later.
    provenance               TEXT,                 -- where the book came from
    license_basis            TEXT,                 -- why this content_class (prose)
    -- Takedown override. Orthogonal to content_class so a taken-down
    -- public-domain book stays public-domain and the action is
    -- reversible. On takedown the document's content_class is moved to
    -- restricted_pending_opt_in (reusing the existing G1 gate) and the
    -- original is saved here.
    taken_down               BOOLEAN NOT NULL DEFAULT FALSE,
    taken_down_at            TIMESTAMP,
    takedown_reason          TEXT,
    pre_takedown_content_class TEXT,
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_book_assets_taken_down
    ON book_assets(taken_down);
"""


# Write workflow SPR-01 — the OutlineBlock composition layer. This is the
# "lego block" primitive: a unit of meaning placed in an outline section.
# It SUPERSEDES section_blocks as the composition layer (section_blocks
# stays as the migration source — see substrate/write/migrate_outline_block.py)
# and is a strict EXTENSION of the Deliverable/Section/Block model, NOT a
# parallel store: an outline is deliverables + deliverable_sections
# (hierarchy via parent_section_id) + outline_blocks (the leaf composition
# units).
#
# Provenance is the moat. ``node_id`` is a SOFT reference (no FK) on
# purpose:
#   1. dangling detection — a block whose source node was deleted must be
#      *detectable and surfaced* (SPR-01 M3), which a hard FK would make
#      impossible (the row could never exist, or the node could never be
#      deleted); and
#   2. forward-compat with DRW SPR-01 — insight/question notes are
#      event-only today (note.emerged / question.identified) and become
#      first-class graph nodes later; a soft ref lets a block point at a
#      note id that is not yet a row in ``nodes``.
# substrate/write/provenance.py resolves + validates the chain; the DB
# CHECK enforces the no-orphan-prose invariant structurally (graph_node ⟹
# node_id present; user-originated ⟹ node_id absent — no fabricated
# citations).
ANTIEK_GRAPH_SCHEMA_V8_WRITE_SQL = """
CREATE TABLE IF NOT EXISTS outline_blocks (
    outline_block_id  TEXT PRIMARY KEY,
    section_id        TEXT NOT NULL REFERENCES deliverable_sections(section_id),
    block_kind        TEXT NOT NULL CHECK (block_kind IN (
        'insight', 'open_question', 'operator_note', 'claim',
        'user_authored', 'synthesized'
    )),
    provenance_kind   TEXT NOT NULL CHECK (provenance_kind IN (
        'graph_node', 'user_authored', 'synthesized', 'brainstorm'
    )),
    -- Soft reference to the source graph node (NULL for user-originated
    -- blocks). No FK — see the module note on dangling detection.
    node_id           TEXT,
    -- Migration provenance: the original section_blocks (block_kind,
    -- block_id) this row was migrated from, so the move is auditable and
    -- reversible. NULL for natively-created outline blocks.
    source_block_kind TEXT,
    source_block_id   TEXT,
    -- Inline content for user_authored / synthesized / brainstorm blocks
    -- that have no graph node of record. NULL when node-backed.
    content           TEXT,
    block_index       INTEGER NOT NULL,
    -- Clustering key (SPR-01 M4): blocks grouped by shared source document
    -- or node-embedding similarity share a cluster_id. NULL = unclustered.
    cluster_id        TEXT,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata          TEXT,
    -- The no-orphan-prose invariant, enforced at the DB layer:
    --   graph_node      ⟹ node_id present (a block claiming graph
    --                     provenance must name its node);
    --   user-originated ⟹ node_id absent (no fabricated citation to a
    --                     source the block did not come from).
    CHECK (
        (provenance_kind = 'graph_node' AND node_id IS NOT NULL)
        OR (provenance_kind <> 'graph_node' AND node_id IS NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_outline_blocks_section
    ON outline_blocks(section_id, block_index);
CREATE INDEX IF NOT EXISTS idx_outline_blocks_node
    ON outline_blocks(node_id);
CREATE INDEX IF NOT EXISTS idx_outline_blocks_cluster
    ON outline_blocks(cluster_id);
"""


# ============================================================
# V9 — write_log (DRW SPR-01)
# ============================================================
# runtime/db_lock.py has written to this table since WP-2, but the
# CREATE was never landed (the spec referenced a `migrate_v7_write_log.py`
# that did not exist, and `_log_write_event` was built to no-op
# gracefully while the table was missing). DRW SPR-01 needs the write
# observability that `connect_write(purpose="promote_insight")` produces,
# so the table is created here as the next idempotent versioned block.
# (V7/V8 numbers are already taken by the parallel Read/Write workflows;
# this is the next free integer, not a third "V7".) Columns match the
# INSERT in db_lock._log_write_event exactly.
ANTIEK_GRAPH_SCHEMA_V9_WRITE_LOG_SQL = """
CREATE SEQUENCE IF NOT EXISTS seq_write_log_id START 1;
CREATE TABLE IF NOT EXISTS write_log (
    log_id       BIGINT PRIMARY KEY DEFAULT nextval('seq_write_log_id'),
    purpose      TEXT NOT NULL,
    duration_s   DOUBLE NOT NULL DEFAULT 0.0,
    success      BOOLEAN NOT NULL DEFAULT TRUE,
    error        TEXT,
    logged_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_write_log_purpose ON write_log(purpose);
CREATE INDEX IF NOT EXISTS idx_write_log_logged_at ON write_log(logged_at);
"""


# SPR-04 — attribution_audit. Append-only, reproducible record of every
# contribution-weighting attribution computation: the FULL inputs + the
# algorithm + a math-version stamp + the per-asset output split + a timestamp.
# This is the trust layer for the §9 ad economics: a claiming publisher (or
# counsel) must be able to REPLAY exactly why they earned what they earned
# (defensibility). Mirrors the payout_decisions audit-table shape (V6). Never
# disburses — records only. Module: substrate/ad_inventory/attribution_audit.py.
ANTIEK_GRAPH_SCHEMA_V10_ATTRIBUTION_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS attribution_audit (
    audit_id            TEXT PRIMARY KEY,
    impression_set_ref  TEXT NOT NULL,
    page_id             TEXT NOT NULL,
    algorithm           TEXT NOT NULL CHECK (algorithm IN (
        'equal_split_per_chunk_citation',
        'claim_confidence_times_source_tier',
        'load_bearing_via_secondary_pass'
    )),
    algorithm_version   TEXT NOT NULL,
    -- Canonical-JSON of the exact kwargs the algorithm was called with, so the
    -- computation can be replayed against the math it was stamped with.
    inputs_json         TEXT NOT NULL,
    shares_json         TEXT NOT NULL,
    computed_at         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_attribution_audit_impression_set
    ON attribution_audit(impression_set_ref);
CREATE INDEX IF NOT EXISTS idx_attribution_audit_page
    ON attribution_audit(page_id);
"""


# SPR-06 (arxiv-ingest) — paper_author_accruals. The INTERNAL per-paper author
# accrual ledger: for each T1 paper read that produced ad revenue, how much is
# OWED to each author keyed by (arxiv_id, author_position), plus an explicit
# UNATTRIBUTED entry (author_position = -1, reusing the held-never-misattributed
# bucket semantics) that catches papers with no resolvable OpenAlex author.
# Per-author rows + the unattributed row reconcile EXACTLY to the attributed
# revenue (conservation-to-the-cent). Append-only, deterministic idempotent ids,
# version stamps + inputs_json for replay. INTERNAL accounting ONLY — this
# ledger writes NO escrow and disburses nothing (the substrate SPR-07 claim +
# SPR-08 payout build on). Module: substrate/payouts/ledger.py (which also keeps
# a defensive module-local ensure_tables). Mirrors the attribution_audit /
# frame_attention_accrual append-only shape; FK-references nothing.
ANTIEK_GRAPH_SCHEMA_V11_PAPER_AUTHOR_ACCRUALS_SQL = """
CREATE TABLE IF NOT EXISTS paper_author_accruals (
    accrual_id           TEXT PRIMARY KEY,
    event_ref            TEXT NOT NULL,
    ad_event_id          TEXT NOT NULL,
    document_id          TEXT NOT NULL,
    arxiv_id             TEXT NOT NULL,
    -- 0-based byline position, or -1 for the explicit unattributed entry.
    author_position      INTEGER NOT NULL,
    orcid                TEXT,
    -- 'author' | 'unattributed'.
    attribution_kind     TEXT NOT NULL,
    amount_cents         INTEGER NOT NULL DEFAULT 0,
    -- The event's total attributed revenue, stamped on every row of the event
    -- so reconciliation compares against the genuine total (summed per event).
    attributed_cents     INTEGER NOT NULL DEFAULT 0,
    split_policy_version TEXT NOT NULL,
    ledger_version       TEXT NOT NULL,
    -- Canonical-JSON of the exact inputs (source ad-event, attributed cents,
    -- author positions) so "why is author X owed $Y" is replayable.
    inputs_json          TEXT NOT NULL,
    accrued_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_paper_author_accruals_arxiv
    ON paper_author_accruals(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_paper_author_accruals_event
    ON paper_author_accruals(ad_event_id);
"""


# SPR-09 M4 (arxiv-ingest ToS-compliance) — arxiv_audit. The append-only,
# arxiv_id-keyed fetch→serve→accrue→takedown compliance trace. ONE query
# (substrate/audit/arxiv_audit.trace) reconstructs a paper's full lifecycle for a
# ToS-compliance answer. §9.0: stores document_id/arxiv_id/refs/reason/tier/
# counts ONLY — NEVER raw_text / snippet / served body (the writer rejects any
# body-shaped detail key). ``kind`` is a CHECK-constrained namespaced STRING
# (arxiv.fetch|serve|accrue|takedown), NOT a typed event payload — so this
# touches NO codegen surface and never bumps EVENT_SCHEMA_VERSION. Append-only:
# deterministic sha256 event_id (idempotent re-record), no in-place mutation.
# Module: substrate/audit/arxiv_audit.py (which also keeps a defensive
# module-local ensure_tables). Mirrors the attribution_audit append-only shape;
# FK-references nothing.
ANTIEK_GRAPH_SCHEMA_V12_ARXIV_AUDIT_SQL = """
CREATE TABLE IF NOT EXISTS arxiv_audit (
    event_id      TEXT PRIMARY KEY,
    arxiv_id      TEXT NOT NULL,
    document_id   TEXT NOT NULL,
    kind          TEXT NOT NULL CHECK (kind IN (
        'arxiv.fetch', 'arxiv.serve', 'arxiv.accrue', 'arxiv.takedown'
    )),
    reason        TEXT,
    tier          TEXT,
    amount_cents  INTEGER,
    -- Canonical-JSON of NON-body refs/counters ONLY (§9.0 — never paper content).
    detail_json   TEXT NOT NULL DEFAULT '{}',
    recorded_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_arxiv_audit_arxiv
    ON arxiv_audit(arxiv_id);
CREATE INDEX IF NOT EXISTS idx_arxiv_audit_document
    ON arxiv_audit(document_id);
"""


# SPR-09 (Personal-Reading Lane "monitoring mode") — monitors. A saved feed
# bound to a prior deep-research investigation. Stores the thread's derived
# query terms + an embedding centroid (the mean of the thread's chunk
# embeddings) + a last_seen_at checkpoint. The resumable refresh
# (orchestration/monitoring/monitor.py) surfaces the personal_reading
# documents ingested since the checkpoint, ranked against the centroid. The
# monitor owns NO body and NO rights state — it only points at documents
# that already carry content_class='personal_reading'; the read-side gate
# (search.py / personal_space.py) still governs what a reader may see, so a
# monitor can never widen the lane. centroid is NULLABLE: an honest NULL
# when the thread had zero embedded chunks (refresh degrades to
# chronological ranking, never a fabricated zero-vector). Box-bounded
# (§16): refresh is operator-invoked / reuses the continuous single-
# iteration pattern; this table adds no daemon. Idempotent CREATE IF NOT
# EXISTS; FK-references nothing (investigation_id is a soft ref — the
# substrate has no investigations table by design, see V1 note).
ANTIEK_GRAPH_SCHEMA_V13_MONITORS_SQL = """
CREATE TABLE IF NOT EXISTS monitors (
    monitor_id        TEXT PRIMARY KEY,
    investigation_id  TEXT NOT NULL,
    title             TEXT,
    query_terms       TEXT,          -- JSON array of salient terms
    centroid          FLOAT[],       -- nullable; mean of thread chunk embeddings
    centroid_dim      INTEGER,
    last_seen_at      TIMESTAMP NOT NULL,
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_monitors_investigation
    ON monitors(investigation_id);
"""


# Contradiction & Supersession — supersession_candidates: the review
# queue that makes contradictions TASKS, not actions. The detector writes
# candidate rows; only apply_review mutates edges. Pure idempotent
# CREATE IF NOT EXISTS. old/new_edge_id are SOFT references to
# edges(edge_id) — plain TEXT, NO foreign key — because a hard FK would make
# a candidate row BLOCK apply_review from closing the edge it points at
# (DuckDB refuses UPDATE/DELETE on a FK-referenced row), which is exactly
# backwards. Same soft-ref choice as outline_blocks.node_id; the detector
# only ever stores ids it just read from edges, so they are valid by
# construction. The contradiction_type / status / decision CHECK sets mirror
# the Python CONTRADICTION_TYPES / {'open','reviewed'} / REVIEW_DECISIONS
# frozensets in middleware/supersession/supersession.py (parity is drift-tested).
ANTIEK_GRAPH_SCHEMA_V14_SUPERSESSION_CANDIDATES_SQL = """
CREATE TABLE IF NOT EXISTS supersession_candidates (
    candidate_id       TEXT PRIMARY KEY,
    investigation_id   TEXT,
    old_edge_id        TEXT,   -- soft ref to edges(edge_id); no FK (see note above)
    new_edge_id        TEXT,   -- soft ref to edges(edge_id); no FK (see note above)
    contradiction_type TEXT CHECK (contradiction_type IN ('supersession', 'uncertainty', 'error')),
    reasoning          TEXT,
    status             TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'reviewed')),
    decision           TEXT CHECK (decision IN ('apply_supersession', 'dismiss_new', 'dismiss_old', 'coexist')),
    reviewer           TEXT,
    review_notes       TEXT DEFAULT '',
    created_at         TIMESTAMP,
    reviewed_at        TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_supersession_candidates_status
    ON supersession_candidates(status);
"""


# GF-7 — embedding provider/model pinning for chunk vectors. This is a soft-ref
# table rather than columns on chunks so legacy positional INSERT fixtures keep
# working and DuckDB FK mutation traps cannot block chunk rewrites.
ANTIEK_GRAPH_SCHEMA_V15_EMBEDDINGS_META_SQL = """
CREATE TABLE IF NOT EXISTS embeddings_meta (
    chunk_id     TEXT PRIMARY KEY,
    provider     TEXT NOT NULL,
    model_name   TEXT NOT NULL,
    dimension    INTEGER NOT NULL CHECK (dimension > 0),
    fingerprint  TEXT NOT NULL,
    embedded_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_embeddings_meta_fingerprint
    ON embeddings_meta(fingerprint);
"""


# Safe derived-asset merge (SDAM SPR-00).
#
# "Merge" is defined as a new revision of an operator-owned derived asset.
# Source rows (documents.raw_text), projection rows, and compose snapshots
# have no write method in this subsystem. The evidence boundary is frozen
# before any merge implementation lands.
#
# The container, immutable revisions, ordered evidence-member manifests, and
# mutable current pointer are separate tables. Composite foreign keys make it
# impossible to bind a parent, restore source, member, or pointer across assets.
# Future repositories own append-only/CAS behavior; routes never own DDL.
#
# docs/decisions/safe-derived-asset-merge-boundary.md is the binding record.
ANTIEK_GRAPH_SCHEMA_V16_DERIVED_ASSETS_SQL = """
-- ============================================================
-- derived_assets — operator-owned derived asset (SDAM SPR-00)
-- ============================================================
-- Stable ownership and display identity only. Revision state is elsewhere.
CREATE TABLE IF NOT EXISTS derived_assets (
    derived_asset_id    TEXT PRIMARY KEY,
    title               TEXT NOT NULL,
    asset_kind          TEXT NOT NULL CHECK (asset_kind IN (
        'document', 'analysis', 'synthesis', 'composite'
    )),
    owner_user_id       TEXT NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json       TEXT                 -- JSON; VARIANT deferred
);
CREATE INDEX IF NOT EXISTS idx_derived_assets_owner
    ON derived_assets(owner_user_id);
CREATE INDEX IF NOT EXISTS idx_derived_assets_kind
    ON derived_assets(asset_kind);

-- ============================================================
-- derived_asset_revisions — immutable revision content (SDAM SPR-00)
-- ============================================================
-- Canonical revision authority. canonical_html is the exact reviewed byte source;
-- its UTF-8 hash and the ordered member-manifest hash are persisted together.
CREATE TABLE IF NOT EXISTS derived_asset_revisions (
    derived_asset_id          TEXT NOT NULL
        REFERENCES derived_assets(derived_asset_id),
    revision_id               TEXT NOT NULL,
    operation_kind            TEXT NOT NULL CHECK (operation_kind IN (
        'create', 'revise', 'restore'
    )),
    canonical_html            TEXT NOT NULL,
    canonical_byte_count      BIGINT NOT NULL
        CHECK (canonical_byte_count = octet_length(encode(canonical_html))),
    content_sha256            TEXT NOT NULL
        CHECK (
            regexp_full_match(content_sha256, '[0-9a-f]{64}')
            AND content_sha256 = sha256(canonical_html)
        ),
    manifest_json             TEXT NOT NULL,
    manifest_sha256           TEXT NOT NULL
        CHECK (
            regexp_full_match(manifest_sha256, '[0-9a-f]{64}')
            AND manifest_sha256 = sha256(manifest_json)
        ),
    sanitizer_policy          TEXT NOT NULL,
    sanitizer_version         TEXT NOT NULL,
    review_id                 TEXT NOT NULL,
    acknowledgement_version   TEXT NOT NULL,
    parent_revision_id        TEXT,
    restored_from_revision_id TEXT,
    created_at                TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    metadata_json             TEXT,
    PRIMARY KEY (derived_asset_id, revision_id),
    UNIQUE (revision_id),
    UNIQUE (derived_asset_id, revision_id, content_sha256),
    FOREIGN KEY (derived_asset_id, parent_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id, revision_id),
    FOREIGN KEY (derived_asset_id, restored_from_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id, revision_id),
    CHECK (
        (operation_kind = 'create' AND parent_revision_id IS NULL
            AND restored_from_revision_id IS NULL)
        OR (operation_kind = 'revise' AND parent_revision_id IS NOT NULL
            AND restored_from_revision_id IS NULL)
        OR (operation_kind = 'restore' AND parent_revision_id IS NOT NULL
            AND restored_from_revision_id IS NOT NULL)
    )
);
CREATE INDEX IF NOT EXISTS idx_derived_asset_revisions_asset
    ON derived_asset_revisions(derived_asset_id);
CREATE INDEX IF NOT EXISTS idx_derived_asset_revisions_parent
    ON derived_asset_revisions(parent_revision_id);
-- ============================================================
-- derived_asset_revision_members — ordered immutable evidence manifest
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_asset_revision_members (
    derived_asset_id TEXT NOT NULL
        REFERENCES derived_assets(derived_asset_id),
    revision_id      TEXT NOT NULL,
    member_index     INTEGER NOT NULL CHECK (member_index >= 0),
    projection_id    TEXT NOT NULL,
    source_asset_id  TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    source_sha256    TEXT NOT NULL
        CHECK (regexp_full_match(source_sha256, '[0-9a-f]{64}')),
    hosted_html_sha256 TEXT NOT NULL
        CHECK (regexp_full_match(hosted_html_sha256, '[0-9a-f]{64}')),
    investigation_id TEXT,
    PRIMARY KEY (derived_asset_id, revision_id, member_index),
    UNIQUE (derived_asset_id, revision_id, projection_id),
    FOREIGN KEY (derived_asset_id, revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id, revision_id)
);

-- ============================================================
-- derived_asset_current_revisions — sole mutable CAS pointer
-- ============================================================
CREATE TABLE IF NOT EXISTS derived_asset_current_revisions (
    derived_asset_id    TEXT PRIMARY KEY
        REFERENCES derived_assets(derived_asset_id),
    current_revision_id TEXT NOT NULL,
    current_content_sha256 TEXT NOT NULL
        CHECK (regexp_full_match(current_content_sha256, '[0-9a-f]{64}')),
    generation          BIGINT NOT NULL CHECK (generation >= 1),
    updated_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (derived_asset_id, current_revision_id)
        REFERENCES derived_asset_revisions(derived_asset_id, revision_id),
    FOREIGN KEY (
        derived_asset_id, current_revision_id, current_content_sha256
    ) REFERENCES derived_asset_revisions(
        derived_asset_id, revision_id, content_sha256
    )
);
"""


# SDAM SPR-01 — immutable, owner-scoped canonical drafts and exact reviews.
# Runtime repositories only perform DML; all DDL remains in startup schema init.
ANTIEK_GRAPH_SCHEMA_V17_MERGE_DRAFTS_SQL = """
CREATE TABLE IF NOT EXISTS html_projections (
    projection_id TEXT PRIMARY KEY,
    identity_json JSON NOT NULL UNIQUE,
    projection_json JSON NOT NULL
);

CREATE TABLE IF NOT EXISTS derived_asset_merge_drafts (
    draft_id                 TEXT PRIMARY KEY CHECK (regexp_full_match(draft_id, 'drf_[0-9a-f]{32}')),
    owner_user_id            TEXT NOT NULL,
    intent                   TEXT NOT NULL CHECK (intent IN ('create', 'revise')),
    target_asset_id          TEXT,
    expected_parent_revision_id TEXT,
    expected_parent_sha256   TEXT,
    title                    TEXT NOT NULL,
    asset_kind               TEXT NOT NULL CHECK (asset_kind IN (
        'document', 'analysis', 'synthesis', 'composite'
    )),
    canonical_html           TEXT NOT NULL,
    canonical_byte_count     BIGINT NOT NULL
        CHECK (canonical_byte_count = octet_length(encode(canonical_html))),
    canonical_sha256         TEXT NOT NULL CHECK (
        regexp_full_match(canonical_sha256, '[0-9a-f]{64}')
        AND canonical_sha256 = sha256(canonical_html)
    ),
    manifest_json            TEXT NOT NULL,
    manifest_sha256          TEXT NOT NULL CHECK (
        regexp_full_match(manifest_sha256, '[0-9a-f]{64}')
        AND manifest_sha256 = sha256(manifest_json)
    ),
    sanitizer_policy         TEXT NOT NULL,
    sanitizer_version        TEXT NOT NULL,
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (
        (intent = 'create' AND target_asset_id IS NULL
            AND expected_parent_revision_id IS NULL AND expected_parent_sha256 IS NULL)
        OR (intent = 'revise' AND target_asset_id IS NOT NULL
            AND expected_parent_revision_id IS NOT NULL
            AND regexp_full_match(expected_parent_sha256, '[0-9a-f]{64}'))
    ),
    UNIQUE (draft_id, owner_user_id, canonical_sha256, manifest_sha256)
);
CREATE INDEX IF NOT EXISTS idx_merge_drafts_owner
    ON derived_asset_merge_drafts(owner_user_id);

CREATE TABLE IF NOT EXISTS derived_asset_merge_reviews (
    review_id                TEXT PRIMARY KEY CHECK (regexp_full_match(review_id, 'rvw_[0-9a-f]{32}')),
    draft_id                 TEXT NOT NULL,
    owner_user_id            TEXT NOT NULL,
    canonical_sha256         TEXT NOT NULL CHECK (regexp_full_match(canonical_sha256, '[0-9a-f]{64}')),
    manifest_sha256          TEXT NOT NULL CHECK (regexp_full_match(manifest_sha256, '[0-9a-f]{64}')),
    sanitizer_policy         TEXT NOT NULL,
    sanitizer_version        TEXT NOT NULL,
    acknowledgement_version TEXT NOT NULL,
    created_at               TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (draft_id),
    FOREIGN KEY (draft_id, owner_user_id, canonical_sha256, manifest_sha256)
        REFERENCES derived_asset_merge_drafts(
            draft_id, owner_user_id, canonical_sha256, manifest_sha256
        )
);
CREATE INDEX IF NOT EXISTS idx_merge_reviews_owner
    ON derived_asset_merge_reviews(owner_user_id);
"""


def init_database(con: LockedConnection) -> None:
    """Initialize the Antiek graph schema on a write-locked connection.

    Idempotent. Pass a ``LockedConnection`` from
    ``runtime/db_lock.connect_write`` — the architecture_notes §2.3
    only-writer invariant requires every DDL pass through the same
    coordinator that DML passes through."""
    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"init_database requires a LockedConnection (got {type(con).__name__}). "
            "Use runtime.db_lock.connect_write(db_path) or pass the result of "
            "connect_write into this function."
        )
    con.execute(ANTIEK_GRAPH_SCHEMA_V1_SQL)
    # Sprint 18 additions are idempotent (CREATE IF NOT EXISTS,
    # ALTER TABLE ADD COLUMN IF NOT EXISTS).
    con.execute(ANTIEK_GRAPH_SCHEMA_V2_SPRINT18_SQL)
    # Sprint 18 — Exa & Browserbase Wedge 1 discovery_cache.
    # docs/integration_exa_browserbase.md §6.5.
    con.execute(ANTIEK_GRAPH_SCHEMA_V3_DISCOVERY_CACHE_SQL)
    # Sprint 23-24 + 30+ Phase 3 persistence — federation partners,
    # advertisers, nonce ledger. Append-only state logs.
    con.execute(ANTIEK_GRAPH_SCHEMA_V4_PHASE3_SQL)
    # Sprint 23-24 phase 4 — KYC state machine + tax_reports for
    # §9.5 settlement gate + 1099 export.
    con.execute(ANTIEK_GRAPH_SCHEMA_V5_KYC_SQL)
    # Sprint 23-24 phase 1+2 — ad inventory persistence + payout
    # decisions audit + rollover ledger.
    con.execute(ANTIEK_GRAPH_SCHEMA_V6_AD_PERSISTENCE_SQL)
    # Read workflow SPR-01 — book_assets (TOC/pagination/cover + takedown
    # override). Servability is derived from documents.content_class, not
    # stored here. Idempotent (CREATE IF NOT EXISTS).
    con.execute(ANTIEK_GRAPH_SCHEMA_V7_BOOKS_SQL)
    # Write workflow SPR-01 — outline_blocks (the OutlineBlock composition
    # layer; supersedes section_blocks, references graph nodes for
    # provenance). Idempotent (CREATE IF NOT EXISTS).
    con.execute(ANTIEK_GRAPH_SCHEMA_V8_WRITE_SQL)
    # DRW SPR-01 — write_log table (runtime/db_lock has written to it since
    # WP-2; the CREATE was never landed). Pure idempotent SQL.
    con.execute(ANTIEK_GRAPH_SCHEMA_V9_WRITE_LOG_SQL)
    # DRW SPR-01 — promote 'insight' + 'question' to node types. The first
    # *procedural* migration: DuckDB 1.5.2 cannot ALTER a CHECK constraint in
    # place, so the nodes table is rebuilt iff the live CHECK is missing the
    # two types (idempotent — a no-op once applied, and on fresh DBs where V1
    # already carries them). Runs last: it drops+recreates nodes/edges, and
    # no table created above FK-references them (outline_blocks.node_id is a
    # soft ref, no FK). Lives in its own module — detect-and-rebuild logic,
    # not a static SQL string.
    from .migrate_v9_insight_question import migrate as _migrate_v9_insight_question
    _migrate_v9_insight_question(con)
    # SPR-04 — attribution_audit (append-only reproducible attribution record).
    # Pure idempotent CREATE IF NOT EXISTS; runs last, FK-references nothing.
    con.execute(ANTIEK_GRAPH_SCHEMA_V10_ATTRIBUTION_AUDIT_SQL)
    # SPR-06 (arxiv-ingest) — paper_author_accruals (internal per-paper author
    # accrual ledger; (arxiv_id, author_position) keyed, conservation-to-the-cent,
    # writes NO escrow). Pure idempotent CREATE IF NOT EXISTS; FK-references nothing.
    con.execute(ANTIEK_GRAPH_SCHEMA_V11_PAPER_AUTHOR_ACCRUALS_SQL)
    # SPR-09 M4 (arxiv-ingest) — arxiv_audit (append-only, arxiv_id-keyed
    # fetch→serve→accrue→takedown compliance trace; §9.0 stores NO body, only
    # refs/counts; namespaced string kinds, no typed-payload/codegen bump). Pure
    # idempotent CREATE IF NOT EXISTS; FK-references nothing.
    con.execute(ANTIEK_GRAPH_SCHEMA_V12_ARXIV_AUDIT_SQL)
    # SPR-09 (Personal-Reading Lane) — monitors (saved feed bound to an
    # investigation; carries the centroid + last_seen_at checkpoint that the
    # box-bounded resumable refresh advances). Pure idempotent CREATE IF NOT
    # EXISTS; FK-references nothing.
    con.execute(ANTIEK_GRAPH_SCHEMA_V13_MONITORS_SQL)
    # Contradiction & Supersession — supersession_candidates review queue.
    # Soft-refs edges(edge_id) (no FK, so it never blocks apply_review from
    # mutating an edge); order-independent, kept last for tidiness. Pure
    # idempotent CREATE IF NOT EXISTS. The review path (detector +
    # apply_review) lives in middleware/supersession/.
    con.execute(ANTIEK_GRAPH_SCHEMA_V14_SUPERSESSION_CANDIDATES_SQL)
    # GF-7 — chunk embedding provider/model/dimension pinning. Soft chunk_id
    # reference; pure idempotent CREATE IF NOT EXISTS.
    con.execute(ANTIEK_GRAPH_SCHEMA_V15_EMBEDDINGS_META_SQL)
    # SDAM SPR-00 — stable owned assets, immutable canonical revisions,
    # ordered evidence-member manifests, and a separate CAS-ready pointer.
    con.execute(ANTIEK_GRAPH_SCHEMA_V16_DERIVED_ASSETS_SQL)
    con.execute(ANTIEK_GRAPH_SCHEMA_V17_MERGE_DRAFTS_SQL)


# Per-process memo of db_paths known to already have the Antiek schema.
# The schema is created once (deploy/startup/tests) and NEVER uninitialized at
# runtime, so once a read-only probe confirms the sentinel table the path can be
# short-circuited forever — turning the per-request warm path from a ~4s
# read-only open (on a large prod DB) into O(1). A ``set`` (not a bool) because
# the process may touch more than one db_path (e.g. tests with temp DBs).
_INITIALIZED_PATHS: set[str] = set()


def _schema_is_present(db_path: str) -> bool:
    """Cheap read-only probe: is the Antiek schema already initialized at
    ``db_path``? Returns True if the ``nodes`` sentinel table exists.

    Two layers: (1) a per-process memo (``_INITIALIZED_PATHS``) that short-
    circuits paths already confirmed initialized — O(1), no connection; (2) a
    PLAIN read-only DuckDB connection (NOT connect_write — no application-level
    write flock) for the first probe, which NEVER blocks on the single-writer
    lock. This is the fast-path guard that lets ``init_database_at_path`` skip
    the write lock entirely when the schema is already present, which is the
    warm-path case for every per-request ``ensure_initialized`` call.

    Any failure (file absent, read-only open refused, table missing) returns
    False so the caller falls through to the write-lock init path — the fast
    path is a pure optimization that must never change cold-start behavior."""
    if db_path in _INITIALIZED_PATHS:
        return True
    try:
        con = duckdb.connect(db_path, read_only=True)
    except Exception:
        return False
    try:
        row = con.execute(
            "SELECT (EXISTS (SELECT 1 FROM information_schema.columns "
            "WHERE table_schema='main' AND table_name='nodes' "
            "AND column_name='owner_user_id') AND EXISTS (SELECT 1 FROM "
            "information_schema.tables WHERE table_schema='main' "
            "AND table_name='multimedia_twin_runs') AND EXISTS (SELECT 1 FROM "
            "information_schema.tables WHERE table_schema='main' "
            "AND table_name='multimedia_distillation_claims') AND EXISTS ("
            "SELECT 1 FROM information_schema.tables WHERE table_schema='main' "
            "AND table_name='derived_asset_current_revisions') AND EXISTS ("
            "SELECT 1 FROM information_schema.tables WHERE table_schema='main' "
            "AND table_name='derived_asset_merge_reviews'))"
        ).fetchone()
    except Exception:
        return False
    finally:
        with contextlib.suppress(Exception):
            con.close()
    present = bool(row and row[0])
    if present:
        _INITIALIZED_PATHS.add(db_path)
    return present


def init_database_at_path(db_path: str) -> None:
    """Make sure the schema is present at ``db_path``. Idempotent.

    Fast path: if ``_schema_is_present`` confirms the schema is already
    initialized (a read-only probe — no write flock), return WITHOUT acquiring
    the single-writer lock. This matters because ~15 API read paths call
    ``ensure_initialized`` (which routes here) on EVERY request; without the
    fast path each of those acquires the exclusive write flock and blocks
    behind every graph writer — the proven prod hang that broke
    GET /supersession/candidates (PR #224). With it, a warm read pays only the
    bounded read-only open, never the indefinite write-lock wait.

    Cold path: the read-only probe failed or the schema is absent, so acquire
    the write lock (creating the file if needed) and run ``init_database`` —
    the ``CREATE IF NOT EXISTS`` workhorse. Behavior-identical to before on the
    cold-start path; used by tests + the CLI + first deploy/startup."""
    if _schema_is_present(db_path):
        return
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="graph_schema_init")
    try:
        init_database(con)
    finally:
        con.close()
    # The cold path just created the schema, so memoize the path for every
    # subsequent probe — mirrors the memo update inside the warm probe, so a
    # freshly-initialized DB is O(1) on the next call too (no second read-only
    # open).
    _INITIALIZED_PATHS.add(db_path)


def list_tables(con: duckdb.DuckDBPyConnection) -> list[str]:
    """Return the table names in main schema. Read-only diagnostic."""
    rows = con.execute(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema='main' ORDER BY table_name"
    ).fetchall()
    return [r[0] for r in rows]


if __name__ == "__main__":
    import argparse

    p = argparse.ArgumentParser(description="Initialize the Antiek graph schema")
    p.add_argument("--db-path", required=True, help="Path to DuckDB file")
    args = p.parse_args()
    init_database_at_path(args.db_path)
    con = duckdb.connect(args.db_path, read_only=True)
    try:
        for t in list_tables(con):
            print(f"  {t}")
    finally:
        con.close()
