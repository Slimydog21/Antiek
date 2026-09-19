"""Additive, idempotent authority shadow for FK-sensitive legacy interviews."""

from __future__ import annotations

from typing import Any

from .authority import interview_account_digest

INTERVIEW_AUTHORITY_SCHEMA_SQL = """
-- Parent membership below is deliberately enforced by account-qualified
-- transactions and integrity audits rather than DuckDB foreign keys. DuckDB
-- foreign keys block legitimate updates to referenced parent rows.
CREATE TABLE IF NOT EXISTS interview_projects_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    title                TEXT NOT NULL,
    origin_kind          TEXT NOT NULL DEFAULT 'ai_composition'
        CHECK (origin_kind IN ('ai_composition', 'owner_native')),
    topic_description    TEXT,
    deliverable_id       TEXT,
    interview_guide      TEXT,
    migration_state      TEXT NOT NULL DEFAULT 'canonical'
        CHECK (migration_state IN ('canonical', 'legacy_migrated')),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, project_id)
);
CREATE TABLE IF NOT EXISTS interviews_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id         TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    informant_handle     TEXT,
    informant_email      TEXT,
    invited_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at           TIMESTAMP,
    completed_at         TIMESTAMP,
    transcript_document_id TEXT,
    consent_recorded     BOOLEAN NOT NULL DEFAULT FALSE,
    status               TEXT NOT NULL DEFAULT 'invited'
        CHECK (status IN ('invited', 'in_progress', 'completed', 'declined', 'incomplete')),
    transcript_turns     TEXT,
    migration_state      TEXT NOT NULL DEFAULT 'canonical'
        CHECK (migration_state IN ('canonical', 'legacy_migrated')),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, interview_id),
    UNIQUE (account_digest, project_id, interview_id)
);
CREATE TABLE IF NOT EXISTS interview_authority_quarantine (
    entity_kind          TEXT NOT NULL CHECK (entity_kind IN ('project', 'interview')),
    entity_id            TEXT NOT NULL,
    reason               TEXT NOT NULL,
    observed_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (entity_kind, entity_id, reason)
);
CREATE TABLE IF NOT EXISTS interview_invite_capabilities (
    token_digest          TEXT PRIMARY KEY CHECK (length(token_digest) = 64),
    invite_id             TEXT NOT NULL,
    account_digest        TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id          TEXT NOT NULL,
    project_id            TEXT NOT NULL,
    owner_user_id         TEXT NOT NULL,
    required_scopes_json  TEXT NOT NULL DEFAULT '["record"]',
    revoked_at            TIMESTAMP,
    expires_at            TIMESTAMP,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (account_digest, invite_id)
);
CREATE TABLE IF NOT EXISTS interview_margins (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id         TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    schema_version       INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    revision             BIGINT NOT NULL DEFAULT 0 CHECK (revision >= 0),
    body                 TEXT NOT NULL DEFAULT '',
    content_sha256       TEXT NOT NULL CHECK (length(content_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, interview_id)
);
CREATE TABLE IF NOT EXISTS interview_margin_mutation_receipts (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id         TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    revision             BIGINT NOT NULL,
    content_sha256       TEXT NOT NULL CHECK (length(content_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, interview_id, mutation_key)
);
CREATE TABLE IF NOT EXISTS interview_consent_events (
    event_id              TEXT PRIMARY KEY,
    account_digest        TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id          TEXT NOT NULL,
    owner_user_id         TEXT NOT NULL,
    invite_id             TEXT,
    scope                 TEXT NOT NULL CHECK (scope IN ('record', 'attribute', 'publish')),
    granted               BOOLEAN NOT NULL,
    actor_kind            TEXT NOT NULL CHECK (actor_kind IN (
        'invitee_capability', 'operator_witness', 'legacy_projection'
    )),
    policy_version        INTEGER NOT NULL DEFAULT 1,
    recorded_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_interview_consent_parent
    ON interview_consent_events(account_digest, interview_id, scope, recorded_at);
CREATE INDEX IF NOT EXISTS idx_interviews_authority_project
    ON interviews_authority(account_digest, project_id);
CREATE INDEX IF NOT EXISTS idx_interview_invite_capability_parent
    ON interview_invite_capabilities(account_digest, interview_id);
CREATE TABLE IF NOT EXISTS interview_derivation_bindings (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    investigation_id     TEXT NOT NULL,
    investigation_digest TEXT NOT NULL CHECK (length(investigation_digest) = 64),
    stream_key           TEXT NOT NULL CHECK (length(stream_key) = 64),
    revision             BIGINT NOT NULL DEFAULT 1 CHECK (revision >= 1),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, project_id)
);
CREATE TABLE IF NOT EXISTS interview_answer_derivations (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    interview_id         TEXT NOT NULL,
    question_id          TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    answer_sha256        TEXT NOT NULL CHECK (length(answer_sha256) = 64),
    investigation_id     TEXT NOT NULL,
    investigation_digest TEXT NOT NULL CHECK (length(investigation_digest) = 64),
    stream_key           TEXT NOT NULL CHECK (length(stream_key) = 64),
    binding_revision     BIGINT NOT NULL CHECK (binding_revision >= 1),
    delivery_state       TEXT NOT NULL DEFAULT 'pending'
        CHECK (delivery_state IN ('pending', 'processing', 'completed', 'failed')),
    document_id          TEXT,
    admission_receipt_id TEXT,
    event_id             TEXT,
    event_json           TEXT,
    event_fingerprint    TEXT CHECK (
        event_fingerprint IS NULL OR length(event_fingerprint) = 64
    ),
    attempt_count        INTEGER NOT NULL DEFAULT 0 CHECK (attempt_count >= 0),
    last_error_code      TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, interview_id, question_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_answer_derivations_pending
    ON interview_answer_derivations(account_digest, delivery_state, created_at);
CREATE TABLE IF NOT EXISTS interview_claims_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    claim_id             TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    interview_id         TEXT NOT NULL,
    question_id          TEXT NOT NULL,
    source_document_id   TEXT NOT NULL,
    source_receipt_id    TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    text                 TEXT NOT NULL,
    text_sha256          TEXT NOT NULL CHECK (length(text_sha256) = 64),
    about_subject        BOOLEAN NOT NULL DEFAULT FALSE,
    is_third_party       BOOLEAN NOT NULL DEFAULT FALSE,
    subject_ref          TEXT,
    speaker_is_subject   BOOLEAN NOT NULL DEFAULT FALSE,
    independence_key     TEXT,
    verification         TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification IN (
            'unverified', 'multiply_attested', 'operator_attested', 'contradicted'
        )),
    confidence           DOUBLE NOT NULL DEFAULT 0.5 CHECK (
        confidence >= 0.0 AND confidence <= 1.0
    ),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, claim_id),
    UNIQUE (account_digest, interview_id, source_document_id, claim_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_claims_project
    ON interview_claims_authority(account_digest, project_id, created_at);
CREATE INDEX IF NOT EXISTS idx_interview_claims_interview
    ON interview_claims_authority(account_digest, interview_id, created_at);
CREATE TABLE IF NOT EXISTS interview_corroboration_clusters_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    cluster_id           TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    canonical_claim_id   TEXT NOT NULL,
    canonical_text       TEXT NOT NULL,
    label                TEXT NOT NULL CHECK (
        label IN ('single_sourced', 'multiply_attested', 'contradicted')
    ),
    confidence           DOUBLE NOT NULL CHECK (confidence >= 0.0 AND confidence <= 0.95),
    independent_attesters INTEGER NOT NULL CHECK (independent_attesters >= 0),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, cluster_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_corroboration_project
    ON interview_corroboration_clusters_authority(account_digest, project_id, created_at);
CREATE TABLE IF NOT EXISTS interview_corroboration_members_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    cluster_id           TEXT NOT NULL,
    claim_id             TEXT NOT NULL,
    stance               TEXT NOT NULL CHECK (stance IN ('attests', 'contradicts')),
    independence_key     TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, cluster_id, claim_id),
    UNIQUE (account_digest, claim_id)
);
CREATE TABLE IF NOT EXISTS interview_composition_drafts_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    draft_id             TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    command_id           TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    title                TEXT NOT NULL,
    manifest_json        TEXT NOT NULL,
    manifest_sha256      TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
    body_html            TEXT NOT NULL,
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    visibility           TEXT NOT NULL DEFAULT 'private' CHECK (visibility = 'private'),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, draft_id),
    UNIQUE (account_digest, command_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_composition_project
    ON interview_composition_drafts_authority(account_digest, project_id, created_at);
CREATE TABLE IF NOT EXISTS interview_contributor_attribution_events (
    event_id             TEXT NOT NULL,
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    project_id           TEXT NOT NULL,
    interview_id         TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    command_id           TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    action               TEXT NOT NULL CHECK (action IN ('bind', 'revoke')),
    contributor_ref      TEXT,
    display_label        TEXT,
    evidence_basis       TEXT CHECK (evidence_basis IN (
        'self_reported', 'operator_verified', 'contractual_record'
    )),
    evidence_ref         TEXT,
    target_event_id      TEXT,
    consent_event_ids_json TEXT NOT NULL,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, event_id),
    UNIQUE (account_digest, command_id)
);
CREATE INDEX IF NOT EXISTS idx_interview_contributor_attribution_parent
    ON interview_contributor_attribution_events(
        account_digest, project_id, interview_id, created_at
    );
CREATE TABLE IF NOT EXISTS interview_composition_proposals_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    proposal_id          TEXT NOT NULL,
    draft_id             TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    revision             BIGINT NOT NULL CHECK (revision >= 1),
    base_revision        BIGINT NOT NULL CHECK (base_revision >= 0),
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_body_sha256   TEXT NOT NULL CHECK (length(source_body_sha256) = 64),
    provider_id          TEXT NOT NULL,
    model_id             TEXT NOT NULL,
    projected_max_cents  BIGINT NOT NULL CHECK (projected_max_cents > 0),
    approved_ceiling_cents BIGINT NOT NULL CHECK (approved_ceiling_cents > 0),
    instruction          TEXT NOT NULL,
    state                TEXT NOT NULL DEFAULT 'staged' CHECK (state = 'staged'),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, proposal_id),
    UNIQUE (account_digest, mutation_key),
    UNIQUE (account_digest, draft_id, revision),
    CHECK (projected_max_cents <= approved_ceiling_cents)
);
CREATE INDEX IF NOT EXISTS idx_interview_composition_proposal_draft
    ON interview_composition_proposals_authority(account_digest, draft_id, revision);
CREATE TABLE IF NOT EXISTS interview_composition_execution_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    proposal_id          TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    attempt_id           TEXT NOT NULL,
    run_id               TEXT NOT NULL,
    state                TEXT NOT NULL CHECK (state IN (
        'dispatching', 'provider_returned', 'reconcile_required',
        'call_not_dispatched', 'rejected', 'ready_for_review'
    )),
    prompt_sha256        TEXT NOT NULL CHECK (length(prompt_sha256) = 64),
    route_sha256         TEXT NOT NULL CHECK (length(route_sha256) = 64),
    hold_id              TEXT,
    provider             TEXT,
    model                TEXT,
    actual_cents         BIGINT,
    dispatch_event_id    TEXT,
    raw_result_json      TEXT,
    raw_result_sha256    TEXT,
    receipt_prompt_sha256 TEXT,
    result_html          TEXT,
    result_html_sha256   TEXT,
    rejection_reason     TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, proposal_id),
    UNIQUE (account_digest, attempt_id),
    UNIQUE (run_id),
    CHECK (
        (state = 'dispatching' AND hold_id IS NOT NULL
            AND provider IS NULL AND model IS NULL AND actual_cents IS NULL
            AND dispatch_event_id IS NULL AND raw_result_json IS NULL
            AND raw_result_sha256 IS NULL AND receipt_prompt_sha256 IS NULL
            AND result_html IS NULL AND result_html_sha256 IS NULL
            AND rejection_reason IS NULL)
        OR (state = 'reconcile_required' AND hold_id IS NOT NULL
            AND provider IS NULL AND model IS NULL AND actual_cents IS NULL
            AND dispatch_event_id IS NULL AND raw_result_json IS NULL
            AND raw_result_sha256 IS NULL AND receipt_prompt_sha256 IS NULL
            AND result_html IS NULL AND result_html_sha256 IS NULL)
        OR (state = 'call_not_dispatched' AND hold_id IS NOT NULL
            AND provider IS NULL AND model IS NULL AND actual_cents IS NULL
            AND dispatch_event_id IS NULL AND raw_result_json IS NULL
            AND raw_result_sha256 IS NULL AND receipt_prompt_sha256 IS NULL
            AND result_html IS NULL AND result_html_sha256 IS NULL)
        OR (state IN ('provider_returned', 'rejected', 'ready_for_review')
            AND hold_id IS NOT NULL AND provider IS NOT NULL AND model IS NOT NULL
            AND actual_cents IS NOT NULL AND actual_cents >= 0
            AND dispatch_event_id IS NOT NULL AND raw_result_json IS NOT NULL
            AND raw_result_sha256 IS NOT NULL AND receipt_prompt_sha256 IS NOT NULL)
    ),
    CHECK (
        (state = 'provider_returned' AND result_html IS NULL
            AND result_html_sha256 IS NULL AND rejection_reason IS NULL)
        OR state != 'provider_returned'
    ),
    CHECK (
        (state = 'ready_for_review' AND result_html IS NOT NULL
            AND result_html_sha256 IS NOT NULL AND rejection_reason IS NULL)
        OR (state = 'rejected' AND result_html IS NULL
            AND result_html_sha256 IS NULL AND rejection_reason IS NOT NULL)
        OR state NOT IN ('ready_for_review', 'rejected')
    )
);
CREATE TABLE IF NOT EXISTS interview_write_documents_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    write_document_id    TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    title                TEXT NOT NULL,
    current_revision     BIGINT NOT NULL DEFAULT 0 CHECK (current_revision >= 0),
    current_body_sha256  TEXT,
    visibility           TEXT NOT NULL DEFAULT 'private' CHECK (visibility = 'private'),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, write_document_id),
    UNIQUE (account_digest, project_id)
);
CREATE TABLE IF NOT EXISTS interview_write_review_events_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    event_id             TEXT NOT NULL,
    write_document_id    TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    action               TEXT NOT NULL CHECK (action IN ('reject', 'accept', 'undo')),
    proposal_id          TEXT NOT NULL,
    acceptance_key       TEXT,
    target_event_id      TEXT,
    rationale            TEXT,
    revision             BIGINT,
    prior_revision       BIGINT,
    prior_body_sha256    TEXT,
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_body_sha256   TEXT NOT NULL CHECK (length(source_body_sha256) = 64),
    result_html_sha256   TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    event_sha256         TEXT NOT NULL CHECK (length(event_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, event_id),
    UNIQUE (account_digest, mutation_key),
    UNIQUE (account_digest, acceptance_key),
    CHECK ((action = 'reject' AND revision IS NULL AND target_event_id IS NULL)
        OR (action = 'accept' AND revision IS NOT NULL AND target_event_id IS NULL)
        OR (action = 'undo' AND revision IS NOT NULL AND target_event_id IS NOT NULL)),
    CHECK ((action = 'accept' AND acceptance_key = proposal_id)
        OR (action != 'accept' AND acceptance_key IS NULL))
);
CREATE TABLE IF NOT EXISTS interview_write_revisions_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    write_document_id    TEXT NOT NULL,
    revision             BIGINT NOT NULL CHECK (revision >= 1),
    owner_user_id        TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    review_event_sha256  TEXT NOT NULL CHECK (length(review_event_sha256) = 64),
    action               TEXT NOT NULL CHECK (action IN ('accept', 'undo')),
    proposal_id          TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_body_sha256   TEXT NOT NULL CHECK (length(source_body_sha256) = 64),
    result_html_sha256   TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    body_html            TEXT NOT NULL,
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    prior_revision       BIGINT NOT NULL CHECK (prior_revision >= 0),
    prior_body_sha256    TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, write_document_id, revision),
    UNIQUE (account_digest, event_id)
);
CREATE TABLE IF NOT EXISTS interview_write_edit_events_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    event_id             TEXT NOT NULL,
    write_document_id    TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    operation            TEXT NOT NULL DEFAULT 'edit'
        CHECK (operation IN ('edit', 'restore')),
    target_revision      BIGINT,
    target_body_sha256   TEXT,
    base_revision        BIGINT NOT NULL CHECK (base_revision >= 1),
    revision             BIGINT NOT NULL CHECK (revision = base_revision + 1),
    prior_body_sha256    TEXT NOT NULL CHECK (length(prior_body_sha256) = 64),
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    root_acceptance_event_id TEXT NOT NULL,
    proposal_id          TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_body_sha256   TEXT NOT NULL CHECK (length(source_body_sha256) = 64),
    result_html_sha256   TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    summary              TEXT,
    event_sha256         TEXT NOT NULL CHECK (length(event_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, event_id),
    UNIQUE (account_digest, mutation_key),
    UNIQUE (account_digest, write_document_id, revision)
    ,CHECK ((operation = 'edit' AND target_revision IS NULL AND target_body_sha256 IS NULL)
        OR (operation = 'restore' AND target_revision IS NOT NULL
            AND target_revision >= 0 AND target_revision < base_revision
            AND length(target_body_sha256) = 64))
);
CREATE TABLE IF NOT EXISTS interview_write_edit_revisions_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    write_document_id    TEXT NOT NULL,
    revision             BIGINT NOT NULL CHECK (revision >= 2),
    owner_user_id        TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    edit_event_sha256    TEXT NOT NULL CHECK (length(edit_event_sha256) = 64),
    root_acceptance_event_id TEXT NOT NULL,
    proposal_id          TEXT NOT NULL,
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_body_sha256   TEXT NOT NULL CHECK (length(source_body_sha256) = 64),
    result_html_sha256   TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    body_html            TEXT NOT NULL,
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    prior_revision       BIGINT NOT NULL CHECK (prior_revision = revision - 1),
    prior_body_sha256    TEXT NOT NULL CHECK (length(prior_body_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, write_document_id, revision),
    UNIQUE (account_digest, event_id)
);
CREATE TABLE IF NOT EXISTS interview_write_native_events_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    event_id             TEXT NOT NULL,
    write_document_id    TEXT NOT NULL,
    project_id           TEXT NOT NULL,
    owner_user_id        TEXT NOT NULL,
    mutation_key         TEXT NOT NULL,
    request_sha256       TEXT NOT NULL CHECK (length(request_sha256) = 64),
    operation            TEXT NOT NULL CHECK (operation IN ('create', 'edit', 'restore')),
    target_revision      BIGINT,
    target_body_sha256   TEXT,
    base_revision        BIGINT NOT NULL CHECK (base_revision >= 0),
    revision             BIGINT NOT NULL CHECK (revision = base_revision + 1),
    prior_body_sha256    TEXT,
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    title                TEXT,
    summary              TEXT,
    event_sha256         TEXT NOT NULL CHECK (length(event_sha256) = 64),
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, event_id),
    UNIQUE (account_digest, mutation_key),
    UNIQUE (account_digest, write_document_id, revision),
    CHECK ((operation = 'create' AND base_revision = 0 AND revision = 1
            AND prior_body_sha256 IS NULL AND target_revision IS NULL
            AND target_body_sha256 IS NULL AND title IS NOT NULL AND summary IS NULL)
        OR (operation = 'edit' AND base_revision >= 1 AND prior_body_sha256 IS NOT NULL
            AND target_revision IS NULL AND target_body_sha256 IS NULL
            AND title IS NULL)
        OR (operation = 'restore' AND base_revision >= 2 AND prior_body_sha256 IS NOT NULL
            AND target_revision IS NOT NULL AND target_revision >= 1
            AND target_revision < base_revision AND length(target_body_sha256) = 64
            AND title IS NULL))
);
CREATE TABLE IF NOT EXISTS interview_write_native_revisions_authority (
    account_digest       TEXT NOT NULL CHECK (length(account_digest) = 64),
    write_document_id    TEXT NOT NULL,
    revision             BIGINT NOT NULL CHECK (revision >= 1),
    owner_user_id        TEXT NOT NULL,
    event_id             TEXT NOT NULL,
    event_sha256         TEXT NOT NULL CHECK (length(event_sha256) = 64),
    operation            TEXT NOT NULL CHECK (operation IN ('create', 'edit', 'restore')),
    target_revision      BIGINT,
    target_body_sha256   TEXT,
    body_html            TEXT NOT NULL,
    body_sha256          TEXT NOT NULL CHECK (length(body_sha256) = 64),
    prior_revision       BIGINT NOT NULL CHECK (prior_revision = revision - 1),
    prior_body_sha256    TEXT,
    created_at           TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, write_document_id, revision),
    UNIQUE (account_digest, event_id),
    CHECK ((operation = 'create' AND revision = 1 AND prior_body_sha256 IS NULL)
        OR (operation IN ('edit', 'restore') AND revision >= 2
            AND length(prior_body_sha256) = 64))
);
CREATE TABLE IF NOT EXISTS interview_write_evidence_insertions_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    insertion_id TEXT NOT NULL,
    write_document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    native_event_id TEXT NOT NULL,
    native_event_sha256 TEXT NOT NULL CHECK (length(native_event_sha256) = 64),
    operation TEXT NOT NULL CHECK (operation = 'evidence_insert'),
    revision BIGINT NOT NULL CHECK (revision >= 2),
    citation_receipt_sha256 TEXT NOT NULL CHECK (length(citation_receipt_sha256) = 64),
    source_asset_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    chunk_ids_json TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_content_sha256 TEXT NOT NULL CHECK (length(source_content_sha256) = 64),
    excerpt_sha256 TEXT NOT NULL CHECK (length(excerpt_sha256) = 64),
    preview_sha256 TEXT NOT NULL CHECK (length(preview_sha256) = 64),
    receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, insertion_id),
    UNIQUE (account_digest, native_event_id),
    UNIQUE (account_digest, write_document_id, revision)
);
CREATE TABLE IF NOT EXISTS interview_write_evidence_bundles_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    bundle_id TEXT NOT NULL,
    write_document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    native_event_id TEXT NOT NULL,
    native_event_sha256 TEXT NOT NULL CHECK (length(native_event_sha256) = 64),
    operation TEXT NOT NULL CHECK (operation = 'evidence_bundle'),
    revision BIGINT NOT NULL CHECK (revision >= 2),
    item_count INTEGER NOT NULL CHECK (item_count BETWEEN 2 AND 32),
    manifest_sha256 TEXT NOT NULL CHECK (length(manifest_sha256) = 64),
    preview_sha256 TEXT NOT NULL CHECK (length(preview_sha256) = 64),
    receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, bundle_id),
    UNIQUE (account_digest, native_event_id),
    UNIQUE (account_digest, write_document_id, revision)
);
CREATE TABLE IF NOT EXISTS interview_write_evidence_bundle_units_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    bundle_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 31),
    relationship TEXT NOT NULL CHECK (relationship IN (
        'supports', 'contradicts', 'context', 'unresolved'
    )),
    operator_label TEXT,
    citation_receipt_sha256 TEXT NOT NULL CHECK (length(citation_receipt_sha256) = 64),
    source_asset_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    chunk_ids_json TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_content_sha256 TEXT NOT NULL CHECK (length(source_content_sha256) = 64),
    excerpt_sha256 TEXT NOT NULL CHECK (length(excerpt_sha256) = 64),
    unit_receipt_sha256 TEXT NOT NULL CHECK (length(unit_receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, bundle_id, ordinal),
    UNIQUE (account_digest, bundle_id, citation_receipt_sha256)
);
CREATE TABLE IF NOT EXISTS interview_evidence_bundle_synthesis_proposals_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    proposal_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    write_document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    mutation_key TEXT NOT NULL,
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    revision BIGINT NOT NULL CHECK (revision >= 1),
    base_revision BIGINT NOT NULL CHECK (base_revision = revision - 1),
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_content_sha256 TEXT NOT NULL CHECK (length(source_content_sha256) = 64),
    source_receipt_sha256 TEXT NOT NULL CHECK (length(source_receipt_sha256) = 64),
    provider_id TEXT NOT NULL,
    model_id TEXT NOT NULL,
    projected_max_cents BIGINT NOT NULL CHECK (projected_max_cents >= 1),
    approved_ceiling_cents BIGINT NOT NULL CHECK (
        approved_ceiling_cents >= projected_max_cents
    ),
    instruction TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'staged' CHECK (state = 'staged'),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, proposal_id),
    UNIQUE (account_digest, mutation_key),
    UNIQUE (account_digest, bundle_id, revision)
);
CREATE TABLE IF NOT EXISTS interview_evidence_bundle_synthesis_inputs_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    proposal_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 31),
    relationship TEXT NOT NULL CHECK (relationship IN (
        'supports', 'contradicts', 'context', 'unresolved'
    )),
    operator_label TEXT,
    citation_receipt_sha256 TEXT NOT NULL CHECK (length(citation_receipt_sha256) = 64),
    source_asset_id TEXT NOT NULL,
    claim_id TEXT NOT NULL,
    source_document_id TEXT NOT NULL,
    chunk_ids_json TEXT NOT NULL,
    source_title TEXT NOT NULL,
    source_content_sha256 TEXT NOT NULL CHECK (length(source_content_sha256) = 64),
    excerpt_text TEXT NOT NULL,
    excerpt_sha256 TEXT NOT NULL CHECK (length(excerpt_sha256) = 64),
    input_receipt_sha256 TEXT NOT NULL CHECK (length(input_receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, proposal_id, ordinal),
    UNIQUE (account_digest, proposal_id, citation_receipt_sha256)
);
CREATE TABLE IF NOT EXISTS interview_write_synthesis_acceptances_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    acceptance_id TEXT NOT NULL,
    write_document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    native_event_id TEXT NOT NULL,
    native_event_sha256 TEXT NOT NULL CHECK (length(native_event_sha256) = 64),
    operation TEXT NOT NULL CHECK (operation = 'synthesis_accept'),
    proposal_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    execution_run_id TEXT NOT NULL,
    base_revision BIGINT NOT NULL CHECK (base_revision >= 1),
    base_html_sha256 TEXT NOT NULL CHECK (length(base_html_sha256) = 64),
    revision BIGINT NOT NULL CHECK (revision = base_revision + 1),
    html_sha256 TEXT NOT NULL CHECK (length(html_sha256) = 64),
    source_manifest_sha256 TEXT NOT NULL CHECK (length(source_manifest_sha256) = 64),
    source_content_sha256 TEXT NOT NULL CHECK (length(source_content_sha256) = 64),
    source_receipt_sha256 TEXT NOT NULL CHECK (length(source_receipt_sha256) = 64),
    prompt_sha256 TEXT NOT NULL CHECK (length(prompt_sha256) = 64),
    route_sha256 TEXT NOT NULL CHECK (length(route_sha256) = 64),
    result_html_sha256 TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    preview_sha256 TEXT NOT NULL CHECK (length(preview_sha256) = 64),
    receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, acceptance_id),
    UNIQUE (account_digest, native_event_id),
    UNIQUE (account_digest, proposal_id),
    UNIQUE (account_digest, write_document_id, revision)
);
CREATE TABLE IF NOT EXISTS interview_synthesis_knowledge_admissions_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    admission_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    acceptance_id TEXT NOT NULL,
    acceptance_receipt_sha256 TEXT NOT NULL CHECK (length(acceptance_receipt_sha256) = 64),
    native_event_id TEXT NOT NULL,
    native_event_sha256 TEXT NOT NULL CHECK (length(native_event_sha256) = 64),
    write_document_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    revision BIGINT NOT NULL CHECK (revision >= 2),
    body_sha256 TEXT NOT NULL CHECK (length(body_sha256) = 64),
    proposal_id TEXT NOT NULL,
    bundle_id TEXT NOT NULL,
    execution_run_id TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL CHECK (length(prompt_sha256) = 64),
    route_sha256 TEXT NOT NULL CHECK (length(route_sha256) = 64),
    raw_result_sha256 TEXT NOT NULL CHECK (length(raw_result_sha256) = 64),
    result_html_sha256 TEXT NOT NULL CHECK (length(result_html_sha256) = 64),
    target_investigation_id TEXT NOT NULL,
    target_investigation_digest TEXT NOT NULL CHECK (length(target_investigation_digest) = 64),
    target_graph_key TEXT NOT NULL CHECK (length(target_graph_key) = 64),
    item_count INTEGER NOT NULL CHECK (item_count BETWEEN 1 AND 32),
    item_manifest_sha256 TEXT NOT NULL CHECK (length(item_manifest_sha256) = 64),
    mutation_key TEXT NOT NULL,
    mutation_key_sha256 TEXT NOT NULL CHECK (length(mutation_key_sha256) = 64),
    request_sha256 TEXT NOT NULL CHECK (length(request_sha256) = 64),
    preview_sha256 TEXT NOT NULL CHECK (length(preview_sha256) = 64),
    receipt_sha256 TEXT NOT NULL CHECK (length(receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, admission_id),
    UNIQUE (account_digest, mutation_key)
);
CREATE TABLE IF NOT EXISTS interview_synthesis_knowledge_admission_items_authority (
    account_digest TEXT NOT NULL CHECK (length(account_digest) = 64),
    admission_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    acceptance_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK (ordinal BETWEEN 0 AND 31),
    unit_index INTEGER NOT NULL CHECK (unit_index BETWEEN 0 AND 31),
    kind TEXT NOT NULL CHECK (kind IN ('insight', 'question')),
    original_text_sha256 TEXT NOT NULL CHECK (length(original_text_sha256) = 64),
    admitted_text TEXT NOT NULL,
    admitted_text_sha256 TEXT NOT NULL CHECK (length(admitted_text_sha256) = 64),
    graph_node_id TEXT NOT NULL,
    node_disposition TEXT NOT NULL CHECK (node_disposition IN ('created', 'reused')),
    evidence_json TEXT NOT NULL,
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    item_receipt_sha256 TEXT NOT NULL CHECK (length(item_receipt_sha256) = 64),
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (account_digest, admission_id, ordinal),
    UNIQUE (account_digest, acceptance_id, unit_index)
);
"""


def migrate_interview_authority_schema(con: Any) -> None:
    """Copy explicit-owner legacy rows into additive composite canonical tables."""

    con.execute(INTERVIEW_AUTHORITY_SCHEMA_SQL)
    evidence_columns = {
        str(row[1]) for row in con.execute(
            "PRAGMA table_info('interview_write_evidence_insertions_authority')"
        ).fetchall()
    }
    if "operation" not in evidence_columns:
        con.execute(
            "ALTER TABLE interview_write_evidence_insertions_authority "
            "ADD COLUMN operation TEXT DEFAULT 'evidence_insert'"
        )
    write_document_columns = {
        str(row[1])
        for row in con.execute(
            "PRAGMA table_info('interview_write_documents_authority')"
        ).fetchall()
    }
    if "origin_kind" not in write_document_columns:
        con.execute(
            "ALTER TABLE interview_write_documents_authority "
            "ADD COLUMN origin_kind TEXT DEFAULT 'ai_composition'"
        )
    con.execute(
        "UPDATE interview_write_documents_authority SET origin_kind = 'ai_composition' "
        "WHERE origin_kind IS NULL"
    )
    write_edit_columns = {
        str(row[1])
        for row in con.execute(
            "PRAGMA table_info('interview_write_edit_events_authority')"
        ).fetchall()
    }
    for column, sql_type in (
        ("operation", "TEXT"),
        ("target_revision", "BIGINT"),
        ("target_body_sha256", "TEXT"),
    ):
        if column not in write_edit_columns:
            con.execute(
                f"ALTER TABLE interview_write_edit_events_authority "
                f"ADD COLUMN {column} {sql_type}"
            )
    con.execute(
        "UPDATE interview_write_edit_events_authority SET operation = 'edit' "
        "WHERE operation IS NULL"
    )
    claim_columns = {
        str(row[1])
        for row in con.execute("PRAGMA table_info('interview_claims_authority')").fetchall()
    }
    if "independence_key" not in claim_columns:
        con.execute(
            "ALTER TABLE interview_claims_authority ADD COLUMN independence_key TEXT"
        )
    corroboration_member_columns = {
        str(row[1])
        for row in con.execute(
            "PRAGMA table_info('interview_corroboration_members_authority')"
        ).fetchall()
    }
    if "independence_key" not in corroboration_member_columns:
        con.execute(
            "ALTER TABLE interview_corroboration_members_authority "
            "ADD COLUMN independence_key TEXT"
        )
    derivation_columns = {
        str(row[1])
        for row in con.execute("PRAGMA table_info('interview_answer_derivations')").fetchall()
    }
    for column in (
        "admission_receipt_id", "event_id", "event_json", "event_fingerprint"
    ):
        if column not in derivation_columns:
            con.execute(
                f"ALTER TABLE interview_answer_derivations ADD COLUMN {column} TEXT"
            )
    con.execute(
        "UPDATE interview_answer_derivations SET delivery_state = 'failed', "
        "last_error_code = 'migration_missing_delivery_evidence', "
        "updated_at = CURRENT_TIMESTAMP WHERE delivery_state IN ('processing', 'completed') "
        "AND (document_id IS NULL OR admission_receipt_id IS NULL OR event_id IS NULL "
        "OR event_json IS NULL OR event_fingerprint IS NULL)"
    )
    project_columns = {
        str(row[1]) for row in con.execute("PRAGMA table_info('interview_projects')").fetchall()
    }
    if not project_columns:
        return
    owner_expr = "NULLIF(trim(owner_user_id), '')" if "owner_user_id" in project_columns else "NULL"
    def project_expr(column: str, fallback: str = "NULL") -> str:
        return column if column in project_columns else fallback

    title_expr = project_expr("title", "''")
    rows = con.execute(
        f"SELECT project_id, {title_expr} AS title, "
        f"{project_expr('topic_description')} AS topic_description, "
        f"{project_expr('deliverable_id')} AS deliverable_id, "
        f"{project_expr('interview_guide')} AS interview_guide, "
        f"{owner_expr} AS owner_user_id, "
        f"{project_expr('created_at', 'CAST(CURRENT_TIMESTAMP AS TIMESTAMP)')} AS created_at "
        "FROM interview_projects"
    ).fetchall()
    migrated_projects: dict[str, tuple[str, str]] = {}
    for project_id, title, topic, deliverable_id, guide, owner_user_id, created_at in rows:
        if not isinstance(owner_user_id, str) or not owner_user_id:
            con.execute(
                "INSERT INTO interview_authority_quarantine VALUES "
                "('project', ?, 'missing_explicit_owner', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING",
                [str(project_id)],
            )
            continue
        digest = interview_account_digest(owner_user_id)
        existing = con.execute(
            "SELECT owner_user_id, title, topic_description, deliverable_id, interview_guide "
            "FROM interview_projects_authority WHERE account_digest = ? AND project_id = ?",
            [digest, str(project_id)],
        ).fetchone()
        expected = (owner_user_id, str(title), topic, deliverable_id, guide)
        if existing is not None and tuple(existing) != expected:
            con.execute(
                "INSERT INTO interview_authority_quarantine VALUES "
                "('project', ?, 'canonical_content_conflict', CURRENT_TIMESTAMP) ON CONFLICT DO NOTHING",
                [str(project_id)],
            )
            continue
        con.execute(
            "INSERT INTO interview_projects_authority "
            "(account_digest, project_id, owner_user_id, title, topic_description, "
            "deliverable_id, interview_guide, migration_state, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 'legacy_migrated', ?) ON CONFLICT DO NOTHING",
            [digest, str(project_id), owner_user_id,
             str(title), topic, deliverable_id, guide, created_at],
        )
        migrated_projects[str(project_id)] = (digest, owner_user_id)

    interview_exists = con.execute(
        "SELECT count(*) FROM information_schema.tables "
        "WHERE table_schema = 'main' AND table_name = 'interviews'"
    ).fetchone()[0]
    if not interview_exists:
        return
    interview_columns = {
        str(row[1]) for row in con.execute("PRAGMA table_info('interviews')").fetchall()
    }
    if not interview_columns:
        return
    def interview_expr(column: str, fallback: str = "NULL") -> str:
        return column if column in interview_columns else fallback

    status_expr = interview_expr("status", "'invited'")
    interviews = con.execute(
        f"SELECT interview_id, project_id, {interview_expr('informant_handle')}, "
        f"{interview_expr('informant_email')}, "
        f"{interview_expr('invited_at', 'CAST(CURRENT_TIMESTAMP AS TIMESTAMP)')}, "
        f"{interview_expr('started_at')}, {interview_expr('completed_at')}, "
        f"{interview_expr('transcript_document_id')}, "
        f"{interview_expr('consent_recorded', 'FALSE')}, "
        f"{status_expr}, {interview_expr('transcript_turns')} "
        "FROM interviews"
    ).fetchall()
    for row in interviews:
        (interview_id, project_id, handle, email, invited_at, started_at, completed_at,
         transcript_document_id, consent_recorded, status, transcript_turns) = row
        owner = migrated_projects.get(str(project_id))
        if owner is None:
            con.execute(
                "INSERT INTO interview_authority_quarantine VALUES "
                "('interview', ?, 'missing_or_ambiguous_project_owner', CURRENT_TIMESTAMP) "
                "ON CONFLICT DO NOTHING",
                [str(interview_id)],
            )
            continue
        digest, owner_user_id = owner
        con.execute(
            "INSERT INTO interviews_authority "
            "(account_digest, interview_id, project_id, owner_user_id, informant_handle, "
            "informant_email, invited_at, started_at, completed_at, transcript_document_id, "
            "consent_recorded, status, transcript_turns, migration_state) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'legacy_migrated') "
            "ON CONFLICT DO NOTHING",
            [str(digest), str(interview_id), str(project_id), str(owner_user_id), handle, email,
             invited_at, started_at, completed_at, transcript_document_id,
            consent_recorded, status, transcript_turns],
        )
        if consent_recorded:
            con.execute(
                "INSERT INTO interview_consent_events "
                "(event_id, account_digest, interview_id, owner_user_id, scope, granted, "
                "actor_kind) VALUES (?, ?, ?, ?, 'record', TRUE, 'legacy_projection') "
                "ON CONFLICT DO NOTHING",
                [f"legacy-consent-{digest}-{interview_id}", str(digest), str(interview_id),
                 str(owner_user_id)],
            )

    # Created last: its presence is the warm-start proof that every migration
    # statement above completed successfully at least once.
    con.execute(
        "CREATE TABLE IF NOT EXISTS interview_authority_migration_manifest ("
        "singleton_key INTEGER PRIMARY KEY CHECK (singleton_key = 1), "
        "schema_version INTEGER NOT NULL, completed_at TIMESTAMP NOT NULL, "
        "source_rows BIGINT NOT NULL DEFAULT 0, migrated_rows BIGINT NOT NULL DEFAULT 0, "
        "quarantine_count BIGINT NOT NULL DEFAULT 0, migration_state TEXT NOT NULL DEFAULT 'complete')"
    )
    manifest_columns = {
        str(row[1])
        for row in con.execute(
            "PRAGMA table_info('interview_authority_migration_manifest')"
        ).fetchall()
    }
    for column, sql_type in (
        ("source_rows", "BIGINT"),
        ("migrated_rows", "BIGINT"),
        ("quarantine_count", "BIGINT"),
        ("migration_state", "TEXT"),
    ):
        if column not in manifest_columns:
            con.execute(
                f"ALTER TABLE interview_authority_migration_manifest ADD COLUMN {column} {sql_type}"
            )
    source_rows = len(rows) + len(interviews)
    migrated_rows = con.execute(
        "SELECT (SELECT count(*) FROM interview_projects_authority WHERE migration_state = "
        "'legacy_migrated') + (SELECT count(*) FROM interviews_authority WHERE migration_state = "
        "'legacy_migrated')"
    ).fetchone()[0]
    quarantine_count = con.execute(
        "SELECT count(*) FROM interview_authority_quarantine"
    ).fetchone()[0]
    migration_state = "complete_with_quarantine" if quarantine_count else "complete"
    con.execute(
        "INSERT INTO interview_authority_migration_manifest "
        "(singleton_key, schema_version, completed_at, source_rows, migrated_rows, "
        "quarantine_count, migration_state) VALUES (1, 22, CURRENT_TIMESTAMP, ?, ?, ?, ?) "
        "ON CONFLICT DO UPDATE SET schema_version = excluded.schema_version, "
        "completed_at = excluded.completed_at, source_rows = excluded.source_rows, "
        "migrated_rows = excluded.migrated_rows, quarantine_count = excluded.quarantine_count, "
        "migration_state = excluded.migration_state",
        [source_rows, migrated_rows, quarantine_count, migration_state],
    )


__all__ = ["INTERVIEW_AUTHORITY_SCHEMA_SQL", "migrate_interview_authority_schema"]
