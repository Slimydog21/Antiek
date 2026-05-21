-- ============================================================
-- 0002_user_consent.sql
-- Wrestle Evolution SPR-01 · M4 · Opt-in consent gate
--
-- One row per user-consent state transition. Active consent =
-- the latest row for the user with revoked_at IS NULL. Default
-- is no row (= no consent = no writes), which is industry-standard
-- privacy-on-by-default + the locked 2026-05-21 policy.
-- See substrate/behavior/PRIVACY.md.
-- ============================================================

CREATE TABLE IF NOT EXISTS user_behavior_consent (
    consent_id      TEXT PRIMARY KEY,
    user_id         TEXT NOT NULL,
    granted_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    -- revoked_at is the locked privacy posture: when set, future
    -- emits become silent no-ops. Existing rows in behavior_events
    -- are NOT deleted (the master spec's locked policy 2026-05-21:
    -- "delete future events on opt-out; trained models persist").
    -- A separate scheduled job may purge future rows under user
    -- request; that's a Sprint-22 Trust Center concern.
    revoked_at      TIMESTAMP,
    consent_version INTEGER NOT NULL
);

-- Hot path: "is user X currently opted in?" The consent gate runs
-- one query per emit, so this index is load-bearing.
CREATE INDEX IF NOT EXISTS idx_user_behavior_consent_user_active
    ON user_behavior_consent (user_id, revoked_at);

-- For audit replay ("when did user X opt in/out?"), order by time.
CREATE INDEX IF NOT EXISTS idx_user_behavior_consent_granted
    ON user_behavior_consent (granted_at);
