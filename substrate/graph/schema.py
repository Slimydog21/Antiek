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
- ``embeddings_meta`` — diagnostic; add when needed.

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

import os
import sys
from typing import Optional

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
    node_type        TEXT NOT NULL CHECK (node_type IN (
        'entity', 'organization', 'person', 'property',
        'metric', 'mechanism', 'claim', 'method', 'constraint'
    )),
    embedding        FLOAT[],
    graph_scope      TEXT NOT NULL CHECK (graph_scope IN (
        'depth', 'cross_domain', 'constraint'
    )),
    created_at       TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    degree_cached    INTEGER NOT NULL DEFAULT 0,
    metadata         TEXT
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
--   'public_domain'                 → unrestricted retrieval
--   'opt_in_licensed'               → unrestricted retrieval (publisher claimed)
--   'restricted_pending_opt_in'     → restricted: only retrievable on
--                                     policy_tag in {private_research, operator_only}
--   'user_owned'                    → only the owner_user_id user can retrieve
--   'user_public_contribution'      → user-posted to public graph (§13.9)
ALTER TABLE documents ADD COLUMN IF NOT EXISTS content_class TEXT;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS ip_holder_id TEXT;
CREATE INDEX IF NOT EXISTS idx_documents_content_class ON documents(content_class);
CREATE INDEX IF NOT EXISTS idx_documents_ip_holder ON documents(ip_holder_id);

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


def init_database_at_path(db_path: str) -> None:
    """Convenience: acquire a write lock on ``db_path`` and run
    ``init_database``. Used by tests + the CLI; production callers
    should manage their own lock lifecycles."""
    parent = os.path.dirname(db_path)
    if parent:
        os.makedirs(parent, exist_ok=True)
    con = connect_write(db_path, purpose="graph_schema_init")
    try:
        init_database(con)
    finally:
        con.close()


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
