PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS paid_operations (
    operation_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    canonical_intent_json BLOB NOT NULL CHECK (length(canonical_intent_json) <= 1048576),
    quote_cents INTEGER NOT NULL CHECK (
        typeof(quote_cents) = 'integer'
        AND quote_cents >= 0
        AND quote_cents <= 9223372036854775807
    ),
    ceiling_cents INTEGER NOT NULL CHECK (
        typeof(ceiling_cents) = 'integer'
        AND ceiling_cents >= 0
        AND ceiling_cents <= 9223372036854775807
        AND quote_cents <= ceiling_cents
    ),
    state TEXT NOT NULL CHECK (
        state IN (
            'intent_created',
            'consent_issued',
            'queued',
            'running',
            'complete',
            'failed',
            'budget_halted',
            'timed_out',
            'failed_reconcile'
        )
    ),
    version INTEGER NOT NULL CHECK (typeof(version) = 'integer' AND version >= 0),
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer' AND created_at_ms >= 0),
    updated_at_ms INTEGER NOT NULL CHECK (typeof(updated_at_ms) = 'integer' AND updated_at_ms >= 0),
    expires_at_ms INTEGER NOT NULL CHECK (typeof(expires_at_ms) = 'integer' AND expires_at_ms >= 0),
    consent_token_hash TEXT,
    consent_key_id TEXT,
    consent_issued_at_ms INTEGER CHECK (consent_issued_at_ms IS NULL OR (typeof(consent_issued_at_ms) = 'integer' AND consent_issued_at_ms >= 0)),
    consent_expires_at_ms INTEGER CHECK (consent_expires_at_ms IS NULL OR (typeof(consent_expires_at_ms) = 'integer' AND consent_expires_at_ms >= 0)),
    consent_claimed_at_ms INTEGER CHECK (consent_claimed_at_ms IS NULL OR (typeof(consent_claimed_at_ms) = 'integer' AND consent_claimed_at_ms >= 0)),
    lease_worker_id TEXT,
    lease_generation INTEGER CHECK (lease_generation IS NULL OR (typeof(lease_generation) = 'integer' AND lease_generation >= 0)),
    lease_expires_at_ms INTEGER CHECK (lease_expires_at_ms IS NULL OR (typeof(lease_expires_at_ms) = 'integer' AND lease_expires_at_ms >= 0)),
    terminal_code TEXT,
    terminal_reason TEXT,
    reconciliation_status TEXT,
    result_checkpoint_hash TEXT,
    settled_cents INTEGER CHECK (settled_cents IS NULL OR (typeof(settled_cents) = 'integer' AND settled_cents >= 0)),
    external_charged_cents INTEGER CHECK (
        external_charged_cents IS NULL
        OR (typeof(external_charged_cents) = 'integer' AND external_charged_cents >= 0)
    ),
    PRIMARY KEY (account_id, owner_user_id, operation_id)
);

CREATE INDEX IF NOT EXISTS idx_paid_operations_owner_created
    ON paid_operations(account_id, owner_user_id, created_at_ms);

CREATE TABLE IF NOT EXISTS paid_operation_queue (
    account_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    operation_kind TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    canonical_options_json BLOB NOT NULL CHECK (length(canonical_options_json) <= 1048576),
    enqueued_at_ms INTEGER NOT NULL CHECK (typeof(enqueued_at_ms) = 'integer' AND enqueued_at_ms >= 0),
    queue_state TEXT NOT NULL CHECK (queue_state IN ('queued')),
    PRIMARY KEY (account_id, owner_user_id, operation_id),
    FOREIGN KEY (account_id, owner_user_id, operation_id)
        REFERENCES paid_operations(account_id, owner_user_id, operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS paid_account_budgets (
    account_id TEXT PRIMARY KEY,
    period_id TEXT NOT NULL,
    limit_cents INTEGER NOT NULL CHECK (typeof(limit_cents) = 'integer' AND limit_cents >= 0),
    reserved_cents INTEGER NOT NULL DEFAULT 0 CHECK (typeof(reserved_cents) = 'integer' AND reserved_cents >= 0),
    settled_cents INTEGER NOT NULL DEFAULT 0 CHECK (typeof(settled_cents) = 'integer' AND settled_cents >= 0),
    version INTEGER NOT NULL DEFAULT 0 CHECK (typeof(version) = 'integer' AND version >= 0),
    CHECK (reserved_cents + settled_cents <= limit_cents)
);

CREATE TABLE IF NOT EXISTS paid_operation_ledger (
    movement_key TEXT PRIMARY KEY,
    account_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    period_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    step_id TEXT NOT NULL,
    movement_type TEXT NOT NULL CHECK (movement_type IN ('reserve', 'settle', 'release', 'retain', 'reconcile')),
    cents INTEGER NOT NULL CHECK (typeof(cents) = 'integer' AND cents >= 0),
    lease_worker_id TEXT NOT NULL,
    lease_generation INTEGER NOT NULL CHECK (typeof(lease_generation) = 'integer' AND lease_generation >= 0),
    expected_operation_version INTEGER NOT NULL CHECK (
        typeof(expected_operation_version) = 'integer' AND expected_operation_version >= 0
    ),
    operation_version INTEGER NOT NULL CHECK (
        typeof(operation_version) = 'integer'
        AND operation_version = expected_operation_version + 1
    ),
    prior_movement_key TEXT,
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer' AND created_at_ms >= 0),
    FOREIGN KEY (account_id, owner_user_id, operation_id)
        REFERENCES paid_operations(account_id, owner_user_id, operation_id)
        ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_paid_operation_ledger_operation
    ON paid_operation_ledger(account_id, owner_user_id, operation_id);

CREATE TABLE IF NOT EXISTS paid_operation_checkpoints (
    account_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    step_id TEXT NOT NULL,
    intent_hash TEXT NOT NULL,
    lease_worker_id TEXT NOT NULL,
    lease_generation INTEGER NOT NULL CHECK (typeof(lease_generation) = 'integer' AND lease_generation >= 0),
    expected_operation_version INTEGER NOT NULL CHECK (
        typeof(expected_operation_version) = 'integer' AND expected_operation_version >= 0
    ),
    operation_version INTEGER NOT NULL CHECK (
        typeof(operation_version) = 'integer'
        AND operation_version = expected_operation_version + 1
    ),
    provider_id TEXT NOT NULL,
    endpoint_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    response_body_hash TEXT NOT NULL,
    response_body_json TEXT NOT NULL,
    provider_receipt TEXT NOT NULL,
    observed_cost_cents INTEGER NOT NULL CHECK (
        typeof(observed_cost_cents) = 'integer' AND observed_cost_cents >= 0
    ),
    checkpoint_material_hash TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer' AND created_at_ms >= 0),
    PRIMARY KEY (account_id, owner_user_id, operation_id, step_id),
    UNIQUE (provider_id, endpoint_id, idempotency_key),
    FOREIGN KEY (account_id, owner_user_id, operation_id)
        REFERENCES paid_operations(account_id, owner_user_id, operation_id)
        ON DELETE RESTRICT
);

CREATE TABLE IF NOT EXISTS paid_operation_reconciliation_audit (
    command_id TEXT NOT NULL,
    account_id TEXT NOT NULL,
    owner_user_id TEXT NOT NULL,
    operation_id TEXT NOT NULL,
    operator_user_id TEXT NOT NULL,
    operation_version INTEGER NOT NULL CHECK (typeof(operation_version) = 'integer' AND operation_version >= 0),
    evidence_hash TEXT NOT NULL,
    decision TEXT NOT NULL CHECK (decision IN ('confirm_charged', 'confirm_not_charged')),
    reason TEXT NOT NULL,
    charged_cents INTEGER NOT NULL CHECK (typeof(charged_cents) = 'integer' AND charged_cents >= 0),
    authorized_settled_cents INTEGER NOT NULL CHECK (
        typeof(authorized_settled_cents) = 'integer'
        AND authorized_settled_cents >= 0
        AND authorized_settled_cents <= charged_cents
    ),
    step_id TEXT NOT NULL,
    movement_key TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL CHECK (typeof(created_at_ms) = 'integer' AND created_at_ms >= 0),
    PRIMARY KEY (account_id, owner_user_id, operation_id, command_id),
    FOREIGN KEY (account_id, owner_user_id, operation_id)
        REFERENCES paid_operations(account_id, owner_user_id, operation_id)
        ON DELETE RESTRICT
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_paid_operation_reconciliation_one_audit_per_movement
    ON paid_operation_reconciliation_audit(account_id, owner_user_id, operation_id, movement_key);
