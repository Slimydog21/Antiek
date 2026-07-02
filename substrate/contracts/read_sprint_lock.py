"""Frozen Read sprint-lock.

The coordination roadmap needs a machine-readable build state for Read sprints
instead of inferring completion from prose decision records. This lock mirrors
the DRW sprint-lock pattern at product-sprint granularity: the roster identity is
frozen, status changes require a version bump, and tests assert the promoted
sprints stay live.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump on ANY change to READ_SPRINTS. Status changes are deliberate roadmap
# events, not comments buried in a handoff.
READ_LOCK_VERSION: int = 4


@dataclass(frozen=True)
class ReadDeliverable:
    """A Read sprint's frozen identity and observed build status."""

    sprint: int
    slug: str
    deliverable: str
    status: str = "planned"  # planned | live | provisional


READ_SPRINTS: dict[int, ReadDeliverable] = {
    1: ReadDeliverable(
        1,
        "book-asset-and-corpus-gate",
        "Book asset model + servable-corpus legal gate",
        # Live: book_assets model, deny-by-default servability projection,
        # data-layer full-text gate, takedown/reinstate, ingest provenance,
        # rights-holder link, and /books API are covered by test_book_corpus_gate.
        status="live",
    ),
    2: ReadDeliverable(
        2,
        "library-browse",
        "Library/browse mode",
        # Live: /library paginated/filterable/searchable catalog, typed TS
        # client, Library mode/card UI, servability-flagged gated affordances,
        # and gated-body-never-served drift guard are covered by read-library.
        status="live",
    ),
    3: ReadDeliverable(
        3,
        "book-reader",
        "Book reader",
        # Live: /read/:documentId route, content-derived pagination, TOC/chunk
        # locators, session position, gate-aware full/snippet/removed states,
        # structured-block rendering fallback, and reader no-leak behavior are
        # covered by read-reader.
        status="live",
    ),
    4: ReadDeliverable(
        4,
        "prompt-to-curate",
        "Prompt-to-curate browsing",
        # Live: servable-only embedding ranker, /books/curate route, typed TS
        # client sanitization, and Library prompt re-ranking are covered by
        # read-curate.
        status="live",
    ),
    5: ReadDeliverable(5, "ad-border-inventory", "Ad-border inventory"),
    6: ReadDeliverable(6, "voice-notes", "Voice notes"),
    7: ReadDeliverable(7, "conversational-rabbit-hole", "Conversational rabbit hole"),
    8: ReadDeliverable(8, "research-from-passage", "Research from passage"),
    9: ReadDeliverable(9, "ad-revenue-escrow", "Ad-revenue escrow"),
}


def resolve_read_sprint(n: int) -> ReadDeliverable:
    """Resolve a Read sprint number to its frozen deliverable."""
    try:
        return READ_SPRINTS[n]
    except KeyError:
        raise KeyError(
            f"Read SPR-{n:02d} is not in the frozen sprint-lock "
            f"(READ_LOCK_VERSION={READ_LOCK_VERSION}; valid: {sorted(READ_SPRINTS)})."
        ) from None
