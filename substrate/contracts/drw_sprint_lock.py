"""Frozen DRW sprint-lock — the seam-#6 resolution.

**The single biggest integration risk.** Three product specs (Read, Write,
Speak) cite DRW's sprints *by number*: Read builds against DRW SPR-01/03/04/
05/06/10, Write against SPR-01/03/10, Speak against SPR-07 (counts verified by
scanning the spec bodies — see ``inventory.md``). If DRW renumbers a sprint,
those citations silently point at the wrong deliverable and three downstream
contracts break with no error.

This module freezes the DRW sprint → deliverable map as a versioned constant
and gives the SPR-08 conformance CI two functions to assert against:
``resolve_drw_sprint(n)`` (number → deliverable) and ``downstream_citations()``
(the reverse index). **Renumbering a DRW sprint without updating this lock AND
every downstream citation fails the SPR-08 conformance CI.** Changing the map
at all requires bumping ``LOCK_VERSION`` — a deliberate, reviewable act, not a
silent drift.

The map is hand-authored against the DRW spec's sprint filenames
(``specs/deep-research-workspace/sprint-NN-*.html``), not scanned at runtime —
the specs are documentation inputs, the lock is the machine-readable contract.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump on ANY change to DRW_SPRINTS. The SPR-08 conformance gate records the
# version a downstream citation was validated against.
LOCK_VERSION: int = 1


@dataclass(frozen=True)
class Deliverable:
    """A DRW sprint's frozen identity: its number, the deliverable it ships,
    the contracts it owns (by contract class name in ``substrate.contracts``),
    and the build status the unified spec observed."""

    sprint: int
    slug: str
    deliverable: str
    owns_contracts: tuple[str, ...] = ()
    status: str = "planned"  # planned | live | provisional


# The frozen map. Slugs match the DRW spec filenames exactly
# (sprint-NN-<slug>.html) so a renumber/rename is detectable.
DRW_SPRINTS: dict[int, Deliverable] = {
    1: Deliverable(
        1, "insight-question-nodes",
        "Insight/question graph nodes — the atom of the flywheel",
        ("InsightNodeContract", "QuestionNodeContract"),
        status="live",
    ),
    2: Deliverable(
        2, "research-runner",
        "ResearchRunner execution protocol (start/stream/steer/status/cost/cancel)",
        ("ResearchRunner",),
        status="live",
    ),
    3: Deliverable(
        3, "async-note-taker",
        "Async living-note distillation",
        ("NoteTakerOutputContract",),
        status="live",
    ),
    4: Deliverable(
        4, "max-context-pack",
        "Max-context assembly within a token budget",
        ("ContextPackContract",),
        status="live",
    ),
    5: Deliverable(
        5, "cascade-planner",
        "Cascade one problem into N approved research plans",
        (),  # produces ResearchPlan (owned by SPR-02's protocol module)
        status="planned",
    ),
    6: Deliverable(
        6, "parallel-orchestration",
        "Launch + glass-box orchestration of N parallel researches",
        (),
        status="planned",
    ),
    7: Deliverable(
        7, "structural-gap-detection",
        "Structural gap detection (unanswered questions, contradictions)",
        (),
        status="planned",
    ),
    8: Deliverable(
        8, "universal-ingest",
        "Universal file + external deep-research ingest",
        (),
        status="planned",
    ),
    9: Deliverable(
        9, "glassbox-monitor-ui",
        "Glass-box N-research monitor UI",
        (),
        status="planned",
    ),
    10: Deliverable(
        10, "reading-surface",
        "Shared reading surface (the canonical reader)",
        ("ReaderSurfaceContract",),
        status="provisional",  # not yet implemented — see reading_surface.py
    ),
}


# Reverse index: which downstream specs cite each DRW sprint. Grounded in the
# spec-body citation counts (see inventory.md "DRW citation audit"). This is
# what the conformance gate uses to know a renumber's blast radius.
_DOWNSTREAM_CITATIONS: dict[int, tuple[str, ...]] = {
    1: ("read", "write"),
    3: ("read", "write"),
    4: ("read",),
    5: ("read",),
    6: ("read",),
    7: ("speak",),
    10: ("read", "write"),
}


def resolve_drw_sprint(n: int) -> Deliverable:
    """Resolve a DRW sprint number to its frozen deliverable. Raises
    ``KeyError`` with a clear message if the number is outside the locked
    range — the conformance harness (SPR-08) calls this for every DRW sprint
    cited across the five specs; an unresolved citation is a loud failure."""
    try:
        return DRW_SPRINTS[n]
    except KeyError:
        raise KeyError(
            f"DRW SPR-{n:02d} is not in the frozen sprint-lock "
            f"(LOCK_VERSION={LOCK_VERSION}; valid: {sorted(DRW_SPRINTS)}). "
            "Either the citation is wrong or DRW renumbered without bumping "
            "the lock."
        ) from None


def downstream_citations() -> dict[int, tuple[str, ...]]:
    """The reverse index: DRW sprint number → the product specs that cite it.
    The conformance gate asserts every cited sprint still resolves to the same
    deliverable."""
    return dict(_DOWNSTREAM_CITATIONS)


def cited_sprints() -> tuple[int, ...]:
    """The DRW sprint numbers that downstream specs actually depend on."""
    return tuple(sorted(_DOWNSTREAM_CITATIONS))


def verify_citations_resolve() -> list[str]:
    """Return a list of unresolved-citation error strings (empty = clean). The
    SPR-08 CI gate fails if this is non-empty. Every DRW sprint a downstream
    spec cites must resolve in the frozen map."""
    errors: list[str] = []
    for sprint, specs in _DOWNSTREAM_CITATIONS.items():
        if sprint not in DRW_SPRINTS:
            errors.append(
                f"DRW SPR-{sprint:02d} cited by {list(specs)} but absent from "
                f"the lock (LOCK_VERSION={LOCK_VERSION})"
            )
    return errors
