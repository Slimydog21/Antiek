-- SPR-04 M1 — Reading-mode user-settings migration.
--
-- This migration is the substrate-side counterpart to
-- apps/reading/src/settings/userSettings.ts. Today the TS module
-- persists to localStorage; when the user-settings REST endpoint
-- lands, the TS module switches to a network read and this table
-- becomes the source of truth.
--
-- The column lives on the existing `user` row (NOT a new `user_settings`
-- table) so the read is a join-free lookup. If a Wave-3 sprint needs
-- many more settings, we will split into a `user_settings` table at
-- that point — for SPR-04 a single column is the right minimum.
--
-- ──────────────────────────────────────────────────────────────────
-- Why new users default to 'reader' and existing users to 'researcher'
-- ──────────────────────────────────────────────────────────────────
--
-- Dual-market positioning (master spec, decision locked 2026-05-21):
-- Antiek serves two audiences with one product surface — the agentic
-- researcher (current Wrestle users) and the cozy reader / 50-year-old
-- who wants Kindle-for-the-internet. Reading mode is the bridge: same
-- WrestleApp shell, different layout.
--
-- The asymmetric default is deliberate:
--
--   * New users → 'reader' → cozy-reader onboarding lands in the calm
--     single-pane view. The consumer wedge ships first; researchers
--     who want the three-column UI can flip the toggle.
--
--   * Existing users → 'researcher' → no UI changes under their feet.
--     A user who has been using the three-column Wrestle for months
--     should not get yanked into a calmer UI without consent.
--
-- A future maintainer might "fix" this asymmetry by defaulting
-- everyone to 'researcher'. Do not do that without re-reading the
-- master-spec positioning decision. The asymmetry is the feature.
--
-- ──────────────────────────────────────────────────────────────────
-- DDL
-- ──────────────────────────────────────────────────────────────────

-- New-user default is 'reader'. The DEFAULT in the column declaration
-- below applies to every INSERT that omits reading_mode — i.e. every
-- new signup. This matches the TS module's DEFAULTS_NEW_USER.
ALTER TABLE "user"
  ADD COLUMN IF NOT EXISTS reading_mode TEXT NOT NULL DEFAULT 'reader';

-- Existing-user backfill: every row that existed BEFORE this migration
-- ran is an "existing user" by definition. Set them to 'researcher'.
-- The WHERE clause guards against re-running the migration: it only
-- touches rows whose reading_mode is still the column default AND
-- whose created_at predates the migration timestamp.
--
-- Replace the literal date below with the actual deploy timestamp at
-- apply time. The intent is: rows older than the cutover get the
-- existing-user default; rows created after get the new-user default
-- (which the column DEFAULT already provides).
UPDATE "user"
   SET reading_mode = 'researcher'
 WHERE reading_mode = 'reader'
   AND created_at < TIMESTAMPTZ '2026-05-21 00:00:00+00';

-- Enum guard so a typo in the TS client cannot corrupt the column.
-- Closed vocabulary mirrors apps/reading/src/settings/userSettings.ts
-- ReadingMode type.
ALTER TABLE "user"
  ADD CONSTRAINT user_reading_mode_check
  CHECK (reading_mode IN ('researcher', 'reader'));
