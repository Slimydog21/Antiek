"""Speak workflow — additive DuckDB schema.

Speak's net-new persistent state, kept in its own module rather than
folded into ``substrate/graph/schema.py`` for two reasons:

1. **Collision safety.** ``graph/schema.py`` is a hot, concurrently-
   edited file; an isolated Speak schema merges cleanly (CLAUDE.md:
   "commit what's yours").
2. **Cohesion.** Every table here is load-bearing for exactly one
   Speak invariant, and they reference the *existing* interview +
   ip_holder + deliverable tables rather than duplicating them.

All DDL is ``CREATE TABLE IF NOT EXISTS`` / ``CREATE INDEX IF NOT
EXISTS`` — ``ensure_speak_schema`` is idempotent and cheap to call at
the top of any Speak op. Writes go through a ``LockedConnection``
(single-writer invariant, architecture_notes §2.3); we assert it.

These tables are the *source of truth*; ``substrate/speak/events.py``
is the audit layer over the mutations against them.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# The schema. Grouped by sprint so a maintainer can map a table to its
# spec milestone. FK targets (interview_projects, interviews, ip_holders,
# deliverables) live in substrate/graph/schema.py.
#
# We deliberately do NOT declare DB-level FK constraints to those parent
# tables. DuckDB's FK support is partial: a declared FK blocks UPDATEs to
# the *referenced* (parent) row even when the key is unchanged (its
# documented FK limitation). interviews rows ARE updated (transcript_turns,
# status), so a speak_consent→interviews FK would deadlock the async
# interview. The codebase already notes "DuckDB does not enforce cross-
# table FKs strictly" (graph/ops.py). Provenance is held by matching
# column names + the audit-event trail, not by a DB-level constraint.
# ---------------------------------------------------------------------------

ANTIEK_SPEAK_SCHEMA_SQL = """
-- ===========================================================================
-- SPR-03 — project publish-intent + subject (sidecar to interview_projects)
-- ===========================================================================
-- The interview_projects row carries title/topic/guide. Speak adds the
-- publish INTENT (which drives consent scope + economics) and the SUBJECT
-- of the biography (whose living/deceased status gates public publishing).
CREATE TABLE IF NOT EXISTS speak_projects (
    project_id        TEXT PRIMARY KEY,
    publish_intent    TEXT NOT NULL DEFAULT 'private_never_published'
        CHECK (publish_intent IN ('private_never_published', 'will_be_public')),
    -- Invitation dimension. 'public' (open contribution ecosystem) is
    -- GATED on G7 — the feature flag in invitations.py refuses it.
    invitation_mode   TEXT NOT NULL DEFAULT 'private'
        CHECK (invitation_mode IN ('private', 'public')),
    subject_ref       TEXT,
    subject_status    TEXT NOT NULL DEFAULT 'unknown'
        CHECK (subject_status IN ('living', 'deceased', 'non_identifiable', 'unknown')),
    created_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================================
-- SPR-03 — invite tokens (sidecar to interviews)
-- ===========================================================================
-- The interviews row already tracks an informant's lifecycle. Speak adds
-- the unique invite TOKEN (the interview.antiek.ai/{id}?token= link) and
-- the consent scopes the invite must capture, matched to publish intent.
CREATE TABLE IF NOT EXISTS speak_invites (
    invite_id               TEXT PRIMARY KEY,
    interview_id            TEXT NOT NULL,
    project_id              TEXT NOT NULL,
    token                   TEXT NOT NULL UNIQUE,
    required_consent_scopes TEXT NOT NULL,   -- JSON array ["record","attribute","publish"]
    created_at              TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_speak_invites_token ON speak_invites(token);
CREATE INDEX IF NOT EXISTS idx_speak_invites_project ON speak_invites(project_id);

-- ===========================================================================
-- SPR-01 — scoped consent per (interview, scope)
-- ===========================================================================
-- Replaces the single interviews.consent_recorded boolean with three
-- independent scopes. An interviewee can consent to be recorded but not
-- to be named (attribute) and not to be published (publish).
CREATE TABLE IF NOT EXISTS speak_consent (
    interview_id   TEXT NOT NULL,
    scope          TEXT NOT NULL CHECK (scope IN ('record', 'attribute', 'publish')),
    granted        BOOLEAN NOT NULL DEFAULT FALSE,
    recorded_at    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    revoked_at     TIMESTAMP,
    PRIMARY KEY (interview_id, scope)
);

-- ===========================================================================
-- SPR-01 — subject consent for public publishing
-- ===========================================================================
-- A living, identifiable biography subject must consent before public
-- publishing. Deceased / non-identifiable subjects follow a documented
-- different rule (recorded in `rationale`), not silent permission.
CREATE TABLE IF NOT EXISTS speak_subject_consent (
    project_id      TEXT NOT NULL,
    subject_ref     TEXT NOT NULL,
    subject_status  TEXT NOT NULL
        CHECK (subject_status IN ('living', 'deceased', 'non_identifiable', 'unknown')),
    consent_granted BOOLEAN NOT NULL DEFAULT FALSE,
    rationale       TEXT,   -- documented basis (esp. for deceased / non-identifiable)
    recorded_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (project_id, subject_ref)
);

-- ===========================================================================
-- SPR-01 + SPR-05 — claims + third-party tagging + verification state
-- ===========================================================================
-- A claim is one assertion an interviewee made. `is_third_party` marks a
-- claim about a person OTHER than the consenting interviewee — the claims
-- that need corroboration before they may be published. `verification`
-- is the publish-gate input: only 'multiply_attested' (SPR-05) or
-- 'operator_attested' (SPR-01) third-party claims are publishable.
CREATE TABLE IF NOT EXISTS speak_claims (
    claim_id        TEXT PRIMARY KEY,
    project_id      TEXT NOT NULL,
    interview_id    TEXT,             -- the attesting interviewee; NULL if operator
    text            TEXT NOT NULL,
    about_subject   BOOLEAN NOT NULL DEFAULT FALSE,
    is_third_party  BOOLEAN NOT NULL DEFAULT FALSE,
    subject_ref     TEXT,             -- who the claim is about, if a person
    verification    TEXT NOT NULL DEFAULT 'unverified'
        CHECK (verification IN (
            'unverified', 'multiply_attested', 'operator_attested', 'contradicted'
        )),
    confidence      DOUBLE NOT NULL DEFAULT 0.5,
    created_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_speak_claims_project ON speak_claims(project_id);
CREATE INDEX IF NOT EXISTS idx_speak_claims_interview ON speak_claims(interview_id);

-- ===========================================================================
-- SPR-01 — takedown requests
-- ===========================================================================
-- An interviewee or subject can demand removal of their statements /
-- attribution. An active takedown flips affected content out of
-- publishable and purges it from served output; reversible only by
-- re-consent. Every transition is audited (speak.takedown.*).
CREATE TABLE IF NOT EXISTS speak_takedowns (
    takedown_id   TEXT PRIMARY KEY,
    project_id    TEXT NOT NULL,
    target_kind   TEXT NOT NULL CHECK (target_kind IN ('interview', 'claim', 'subject')),
    target_id     TEXT NOT NULL,     -- interview_id | claim_id | subject_ref
    requested_by  TEXT,
    reason        TEXT,
    status        TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'reversed')),
    requested_at  TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reversed_at   TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_speak_takedowns_target ON speak_takedowns(target_kind, target_id);

-- ===========================================================================
-- SPR-05 — corroboration clusters + members
-- ===========================================================================
-- A cluster groups equivalent claims across interviewees. `label` is
-- 'multiply_attested' (>=2 INDEPENDENT attesters), 'single_sourced', or
-- 'contradicted'. `independent_attesters` counts distinct independence
-- keys (a rumor heard from one source counts once, not N times).
-- multiply_attested means CORROBORATED, never "proven true".
CREATE TABLE IF NOT EXISTS speak_corroboration_clusters (
    cluster_id            TEXT PRIMARY KEY,
    project_id            TEXT NOT NULL,
    canonical_text        TEXT NOT NULL,
    label                 TEXT NOT NULL DEFAULT 'single_sourced'
        CHECK (label IN ('single_sourced', 'multiply_attested', 'contradicted')),
    confidence            DOUBLE NOT NULL DEFAULT 0.5,
    independent_attesters INTEGER NOT NULL DEFAULT 1,
    created_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS speak_corroboration_members (
    cluster_id       TEXT NOT NULL,
    claim_id         TEXT NOT NULL,
    interview_id     TEXT,
    stance           TEXT NOT NULL DEFAULT 'attests' CHECK (stance IN ('attests', 'contradicts')),
    -- Independence key: attestations sharing a key are NON-independent
    -- (the same origin, or interviewees who heard it from each other), so
    -- they count as one attestation, not many.
    independence_key TEXT,
    PRIMARY KEY (cluster_id, claim_id)
);

-- ===========================================================================
-- SPR-06 — informant → payee mapping (the link that didn't exist)
-- ===========================================================================
-- One interviewee maps to one pre-onboarded escrow payee (ip_holders).
-- An unmapped interviewee accrues to a flagged HOLDING bucket, never to
-- a wrong payee.
CREATE TABLE IF NOT EXISTS speak_contributors (
    interview_id   TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    ip_holder_id   TEXT,
    holding_bucket BOOLEAN NOT NULL DEFAULT FALSE,
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- ===========================================================================
-- SPR-06 + SPR-09 — contribution accruals (ACCRUE, never disburse)
-- ===========================================================================
-- Each row is one contributor's accrued share of the 70% slice for a
-- page/impression. amount_usd is bookkeeping — with zero ad buyers it is
-- $0. `slop_gated`=TRUE rows earned nothing (low voice_style/synthesis).
-- Disbursement is gated on G2/G3; there is no payout column here.
CREATE TABLE IF NOT EXISTS speak_accruals (
    accrual_id     TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    publication_id TEXT,
    interview_id   TEXT,
    ip_holder_id   TEXT,
    page_id        TEXT,
    share_fraction DOUBLE NOT NULL DEFAULT 0.0,   -- of the 70% creator slice
    amount_usd     DECIMAL(18, 6) NOT NULL DEFAULT 0,
    impression_ref TEXT,
    slop_gated     BOOLEAN NOT NULL DEFAULT FALSE,
    accrued_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_speak_accruals_project ON speak_accruals(project_id);
CREATE INDEX IF NOT EXISTS idx_speak_accruals_holder ON speak_accruals(ip_holder_id);

-- ===========================================================================
-- SPR-09 — publications
-- ===========================================================================
-- A published biography. 'private' is never served (creator-paid);
-- 'public' registers as content_class='platform_authored' in Read's
-- servable corpus. `taken_down` mirrors a SPR-01 takedown reaching a
-- published work (purge from served output).
CREATE TABLE IF NOT EXISTS speak_publications (
    publication_id TEXT PRIMARY KEY,
    project_id     TEXT NOT NULL,
    deliverable_id TEXT,
    visibility     TEXT NOT NULL CHECK (visibility IN ('private', 'public')),
    content_class  TEXT,             -- 'platform_authored' when public + served
    served         BOOLEAN NOT NULL DEFAULT FALSE,
    published_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    taken_down     BOOLEAN NOT NULL DEFAULT FALSE
);

-- ===========================================================================
-- SPR-10 — AI verifier grades (kept, never discarded)
-- ===========================================================================
-- One row per graded interview (payout_verifier.py). The grade is what
-- the AI verifier (NOT the requester) decided about how well a transcript
-- answered the requester's information goal. A bad-but-honest or failing
-- interview is RETAINED here + labelled (honest / gamed_risk) — only the
-- payout is withheld; the transcript is never discarded. `score` feeds the
-- §9 quality_scores routing in contributor.accrue_contributions.
CREATE TABLE IF NOT EXISTS speak_interview_grades (
    interview_id     TEXT PRIMARY KEY,
    project_id       TEXT NOT NULL,
    information_goal  TEXT,           -- the requester's goal this was graded against
    score            DOUBLE NOT NULL DEFAULT 0.0,   -- in [0, 1]
    passed           BOOLEAN NOT NULL DEFAULT FALSE, -- score >= PASSING_SCORE
    honest           BOOLEAN NOT NULL DEFAULT FALSE, -- bad-but-honest vs gamed
    gamed_risk       BOOLEAN NOT NULL DEFAULT FALSE, -- the OPEN Goodhart flag
    rationale        TEXT,
    graded_by        TEXT NOT NULL DEFAULT 'deterministic-rubric',
    graded_at        TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_speak_grades_project ON speak_interview_grades(project_id);

-- ===========================================================================
-- SPR-09 — physical-book orders (QUOTE only; no fulfillment)
-- ===========================================================================
-- A provider-agnostic order shape over the existing pdf/epub export.
-- The provider is a stub: importing it does NOT enable printing or
-- shipping. status is only ever 'quoted' until a real POD vendor lands.
CREATE TABLE IF NOT EXISTS speak_book_orders (
    order_id       TEXT PRIMARY KEY,
    publication_id TEXT,
    project_id     TEXT NOT NULL,
    book_format    TEXT NOT NULL CHECK (book_format IN ('paperback', 'hardcover')),
    provider       TEXT NOT NULL DEFAULT 'stub',
    payer          TEXT NOT NULL CHECK (payer IN ('creator', 'split')),
    cost_usd       DECIMAL(18, 6) NOT NULL DEFAULT 0,
    status         TEXT NOT NULL DEFAULT 'quoted' CHECK (status IN ('quoted')),
    created_at     TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


# Tables this schema creates. Used by tests + the diagnostic CLI.
SPEAK_SCHEMA_TABLES: tuple[str, ...] = (
    "speak_projects",
    "speak_invites",
    "speak_consent",
    "speak_subject_consent",
    "speak_claims",
    "speak_takedowns",
    "speak_corroboration_clusters",
    "speak_corroboration_members",
    "speak_contributors",
    "speak_accruals",
    "speak_interview_grades",
    "speak_publications",
    "speak_book_orders",
)


def ensure_speak_schema(con: Any) -> None:
    """Create the Speak tables on a write-locked connection. Idempotent.

    Pass a ``LockedConnection`` from ``runtime.db_lock.connect_write`` —
    the only-writer invariant requires every DDL pass through the same
    coordinator as DML (architecture_notes §2.3). We assert the type so
    a raw connection can't silently bypass the lock.

    Cheap after first call (CREATE IF NOT EXISTS), so Speak ops call it
    at the top rather than tracking a "has-run" memo.
    """
    from runtime.db_lock import LockedConnection

    if not isinstance(con, LockedConnection):
        raise TypeError(
            f"ensure_speak_schema requires a LockedConnection (got "
            f"{type(con).__name__}). Acquire via "
            "runtime.db_lock.connect_write(db_path, purpose=...)."
        )
    con.execute(ANTIEK_SPEAK_SCHEMA_SQL)
