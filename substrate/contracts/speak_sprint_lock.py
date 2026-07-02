"""Frozen Speak sprint-lock.

The coordination roadmap needs machine-readable build state for Speak sprints
instead of treating the whole Speak lane as unknown. This lock mirrors the
Read/Write sprint-lock pattern: the roster identity is frozen, status changes
are deliberate roadmap events, and promoted sprints must name their verifier.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump on ANY change to SPEAK_SPRINTS. Status changes are deliberate roadmap
# events, not prose-only handoffs.
SPEAK_LOCK_VERSION: int = 8


@dataclass(frozen=True)
class SpeakDeliverable:
    """A Speak sprint's frozen identity and observed build status."""

    sprint: int
    slug: str
    deliverable: str
    status: str = "planned"  # planned | live | provisional


SPEAK_SPRINTS: dict[int, SpeakDeliverable] = {
    1: SpeakDeliverable(
        1,
        "consent-rights-gate",
        "Consent + rights gate",
        # Live: scoped interviewee consent, legacy record-consent bridge,
        # third-party claim tagging, verification-before-publish, subject
        # consent, takedown purge/blocking, legal-gate refusal, and the
        # public publish gate are covered by speak-consent-rights-gate.
        status="live",
    ),
    2: SpeakDeliverable(
        2,
        "async-voice-interview",
        "Async voice interview",
        # Live: async session/resume, incomplete/complete lifecycle,
        # consent-gated answer submission, ASR failure surfacing,
        # corrected-transcript distillation, interviewer follow-ups,
        # invitee token voice route, and the single voice-pipeline owner guard
        # are covered by speak-async-voice-interview.
        status="live",
    ),
    3: SpeakDeliverable(
        3,
        "project-invitations",
        "Project invitations",
        # Live: project sidecar, project-scoped claim aggregation/isolation,
        # unique invite tokens, same-email dedupe, invite lifecycle tracking,
        # public ecosystem G7 gate, publish-intent consent scopes, operator
        # REST routes, token landing, and the warm Speak index are covered by
        # speak-project-invitations.
        status="live",
    ),
    4: SpeakDeliverable(
        4,
        "compounding-interviewer",
        "Compounding interviewer",
        # Live: accumulated context conditioning, must-cover/open-question
        # chasing, non-leading corroboration prompts, deepening targets,
        # record-only privacy filtering, DRW+Speak composite gap source,
        # interviewer role parser/prompt guards, trajectory capture, and the
        # Loop-3 no-training gate are covered by speak-compounding-interviewer.
        status="live",
    ),
    5: SpeakDeliverable(
        5,
        "cross-interviewee-verification",
        "Cross-interviewee verification",
        # Live: independent-attester counting, same-interviewee de-dupe,
        # contradiction preservation, multiply-attested corroboration,
        # never-proven wording, project-scoped corroboration endpoint, and
        # Speak agreement/disagreement rendering are covered by
        # speak-cross-interviewee-verification.
        status="live",
    ),
    6: SpeakDeliverable(
        6,
        "contributor-economics",
        "Contributor economics",
        # Live: informant-to-payee mapping, holding buckets, Option-B claim
        # contribution shares, slop-gated $0 rows, zero-buyer-safe escrow
        # accrual, no double-count reconciliation, G2/G3 disbursement refusal,
        # and the Speak "owed, not paid" surface are covered by
        # speak-contributor-economics.
        status="live",
    ),
    7: SpeakDeliverable(
        7,
        "economics-matrix",
        "Economics matrix",
        # Live: all four invitation/publishing cells, public-always-splits
        # binding rule, 10% public / 50% private margins, creator cost carry,
        # flip-to-public consent recheck, read-only economics endpoint gates,
        # physical-book payer allocation, and the four-cell Speak settings
        # surface are covered by speak-economics-matrix.
        status="live",
    ),
    8: SpeakDeliverable(
        8,
        "biography-authoring",
        "Biography authoring",
        # Live: claim-derived outline assembly, Write outline_blocks reuse,
        # bounded deepening, creative_writer dispatch seam, public exclusion
        # of unverified third-party claims, private unverified marking, voice
        # style gate, contributor provenance, draft API route, and Speak
        # assemble/no-fake-biography surface are covered by
        # speak-biography-authoring.
        status="live",
    ),
    9: SpeakDeliverable(9, "publishing-physical", "Publishing + physical"),
}


def resolve_speak_sprint(n: int) -> SpeakDeliverable:
    """Resolve a Speak sprint number to its frozen deliverable."""
    try:
        return SPEAK_SPRINTS[n]
    except KeyError:
        raise KeyError(
            f"Speak SPR-{n:02d} is not in the frozen sprint-lock "
            f"(SPEAK_LOCK_VERSION={SPEAK_LOCK_VERSION}; valid: {sorted(SPEAK_SPRINTS)})."
        ) from None
