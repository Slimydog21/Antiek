"""Speak workflow — the audit-event vocabulary.

Speak is interview-as-acquisition (specs/speak/): aggregate stakeholder
interviews into the shared graph, corroborate across interviewees,
author with Write, publish with Read, and pay contributors their fair
share. The Speak substrate owns its own DuckDB tables
(``substrate/speak/schema.py``) as the source of truth; *this* module
is the append-only audit layer over those single-writer mutations.

Why string constants instead of new ``ActionType`` enum members
-----------------------------------------------------------------
``substrate/schemas/events.py`` is a hot, concurrently-edited file (the
operator's parallel-stream tooling commits big batches; CLAUDE.md
warns about collisions on mainline files). The ``log_event`` path
accepts ``str | ActionType`` and ``_coerce`` passes strings through
unchanged, so a plain string is a first-class action_type — it lands
in the JSONL/Parquet trajectory identically. We register Speak's
vocabulary HERE, centrally for the workflow, rather than mutating the
shared enum. This also keeps the codegen-staleness gate green with no
TS drift (SPR-01 M7 / SPR-09 M6 requirement: ``check_staleness.py``
passes). If Speak ships to the TS reading surface and the events need
TS enum members, promote these into ``ActionType`` in a dedicated,
codegen-regenerated commit then.

These values are stored in Parquet — they MUST remain stable across
refactors. Add new ones; never repurpose an existing string.
"""

from __future__ import annotations

from typing import Any

# ── The stable Speak action_type vocabulary ────────────────────────────
# Namespaced ``speak.*`` so they never collide with the central enum.
SPEAK_PROJECT_CREATED = "speak.project.created"
SPEAK_INTERVIEW_INVITED = "speak.interview.invited"
SPEAK_CONSENT_RECORDED = "speak.consent.recorded"
SPEAK_CONSENT_REVOKED = "speak.consent.revoked"
SPEAK_THIRD_PARTY_TAGGED = "speak.third_party.tagged"
SPEAK_SUBJECT_CONSENT_RECORDED = "speak.subject_consent.recorded"
SPEAK_PUBLISH_BLOCKED = "speak.publish.blocked"
SPEAK_TAKEDOWN_REQUESTED = "speak.takedown.requested"
SPEAK_TAKEDOWN_REVERSED = "speak.takedown.reversed"
SPEAK_CLAIM_MULTIPLY_ATTESTED = "speak.claim.multiply_attested"
SPEAK_CLAIM_CONTRADICTED = "speak.claim.contradicted"
SPEAK_CONTRIBUTOR_MAPPED = "speak.contributor.mapped"
SPEAK_CONTRIBUTION_ACCRUED = "speak.contribution.accrued"
SPEAK_DISBURSEMENT_BLOCKED = "speak.disbursement.blocked"
# SPR-10 — the AI verifier graded an interview against the requester's
# information goal (payout_verifier.py). A Speak-local string, NOT a
# central ActionType: per this module's doctrine that keeps the codegen
# staleness gate green with no TS drift (EVENT_SCHEMA_VERSION unchanged).
SPEAK_INTERVIEW_GRADED = "speak.interview.graded"
SPEAK_PUBLISHED = "speak.published"
SPEAK_BOOK_ORDER_QUOTED = "speak.book_order.quoted"
# SPR-11 — a biography template was composed: ONE shared event recording the
# three surface ids it wires together {investigation_id, deliverable_id,
# project_id}. This event IS the Speak↔investigation link (create_project takes
# no investigation arg); it is held in the shared trajectory log, NOT in a new
# biography_* store. A Speak-local string (not a central ActionType) so the
# codegen-staleness gate stays green with no TS drift — same doctrine as
# SPEAK_INTERVIEW_GRADED above (EVENT_SCHEMA_VERSION unchanged).
SPEAK_BIOGRAPHY_COMPOSED = "speak.biography.composed"

# The full set, for tests + a future enum-promotion audit.
SPEAK_ACTION_TYPES: frozenset[str] = frozenset({
    SPEAK_PROJECT_CREATED,
    SPEAK_INTERVIEW_INVITED,
    SPEAK_CONSENT_RECORDED,
    SPEAK_CONSENT_REVOKED,
    SPEAK_THIRD_PARTY_TAGGED,
    SPEAK_SUBJECT_CONSENT_RECORDED,
    SPEAK_PUBLISH_BLOCKED,
    SPEAK_TAKEDOWN_REQUESTED,
    SPEAK_TAKEDOWN_REVERSED,
    SPEAK_CLAIM_MULTIPLY_ATTESTED,
    SPEAK_CLAIM_CONTRADICTED,
    SPEAK_CONTRIBUTOR_MAPPED,
    SPEAK_CONTRIBUTION_ACCRUED,
    SPEAK_DISBURSEMENT_BLOCKED,
    SPEAK_INTERVIEW_GRADED,
    SPEAK_PUBLISHED,
    SPEAK_BOOK_ORDER_QUOTED,
    SPEAK_BIOGRAPHY_COMPOSED,
})


def record_speak_event(
    action_type: str,
    payload: dict[str, Any],
    *,
    project_id: str | None = None,
    role: str | None = None,
) -> str | None:
    """Append one Speak audit event to the trajectory log.

    ``project_id`` becomes the ``investigation_id`` so a project's whole
    Speak history (consent → corroboration → publish → accrual) is one
    queryable stream. Returns the event_id, or None when events are
    disabled (``ANTIEK_EVENTS_DISABLED``). Non-fatal by design — a
    failed audit write must never abort a substrate mutation that
    already committed.
    """
    if action_type not in SPEAK_ACTION_TYPES:
        # Cheap guard against typos becoming permanent Parquet strings.
        raise ValueError(f"unknown Speak action_type: {action_type!r}")
    from substrate.event_log import log_event

    return log_event(
        project_id or "speak-unscoped",
        action_type,
        payload=payload,
        role=role,
    )
