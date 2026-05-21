-- Sprint SPR-03 / M3 — persistent banned-until sentinel for the
-- cross-process throttle. When a domain returns 429, the fetcher
-- writes (domain, banned_until) here and short-circuits subsequent
-- fetches against that domain until the ban window expires. This
-- closes the failure mode from memory project_researchmaxx_arxiv
-- (2026-05-17): the in-process throttle didn't survive worker
-- restart, so the cron worker would 429-ban us repeatedly because
-- nothing remembered the prior ban across restarts.
--
-- Schema:
--   domain        — bare host (e.g. "export.arxiv.org"). PRIMARY KEY
--                   so a fresh 429 atomically overwrites the older ban
--                   when the new Retry-After is longer.
--   banned_until  — UTC timestamp the ban expires; fetcher compares
--                   against CURRENT_TIMESTAMP and short-circuits when
--                   not yet expired.
--   retry_after_s — original Retry-After value (or default 60) so
--                   debugging stuck domains is one query away.
--   created_at    — append-only audit field.
--   reason        — short HTTP status / source code (e.g. "429" or
--                   "503_after_max_retries").
--
-- The throttle's Redis sliding window is the FIRST gate (avoids 429
-- in the first place); this table is the SECOND gate (honors a 429
-- once it happens). They're complementary: lose Redis → throttle
-- degrades to "every domain is fair game" but the banned_until table
-- still prevents repeat 429s; lose this table → throttle keeps us
-- polite but a 429 we missed gets retried on next start.

CREATE TABLE IF NOT EXISTS ingestion_bans (
    domain         TEXT PRIMARY KEY,
    banned_until   TIMESTAMP NOT NULL,
    retry_after_s  INTEGER NOT NULL DEFAULT 60,
    reason         TEXT NOT NULL DEFAULT '429',
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_ingestion_bans_until
    ON ingestion_bans(banned_until);
