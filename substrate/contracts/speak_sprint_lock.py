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
SPEAK_LOCK_VERSION: int = 1


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
    2: SpeakDeliverable(2, "async-voice-interview", "Async voice interview"),
    3: SpeakDeliverable(3, "project-invitations", "Project invitations"),
    4: SpeakDeliverable(4, "compounding-interviewer", "Compounding interviewer"),
    5: SpeakDeliverable(
        5,
        "cross-interviewee-verification",
        "Cross-interviewee verification",
    ),
    6: SpeakDeliverable(6, "contributor-economics", "Contributor economics"),
    7: SpeakDeliverable(7, "economics-matrix", "Economics matrix"),
    8: SpeakDeliverable(8, "biography-authoring", "Biography authoring"),
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
