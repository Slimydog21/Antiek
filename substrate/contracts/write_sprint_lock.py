"""Frozen Write sprint-lock.

The coordination roadmap needs machine-readable build state for Write sprints,
the same way DRW and Read do. This lock freezes the Write sprint identities from
the committed roster manifest and records only observed implementation status;
status changes require a version bump and focused tests.
"""

from __future__ import annotations

from dataclasses import dataclass

# Bump on ANY change to WRITE_SPRINTS. Status changes are deliberate roadmap
# events, not prose-only handoffs.
WRITE_LOCK_VERSION: int = 4


@dataclass(frozen=True)
class WriteDeliverable:
    """A Write sprint's frozen identity and observed build status."""

    sprint: int
    slug: str
    deliverable: str
    status: str = "planned"  # planned | live | provisional


WRITE_SPRINTS: dict[int, WriteDeliverable] = {
    1: WriteDeliverable(
        1,
        "outline-block-model",
        "Outline block model",
        # Live: canonical outline_blocks, no-orphan-prose/no-fabricated-citation
        # invariants, nested outline tree, provenance resolution, HTTP place/
        # move/remove/list/outline/provenance endpoints, and Speak→Write
        # composer integration are covered by write-outline-block.
        status="live",
    ),
    2: WriteDeliverable(
        2,
        "edit-trajectory-capture",
        "Edit trajectory capture",
        # Live: granular edit.captured events, stable locators, deterministic
        # authoring trajectory reconstruction, reverted-edit exclusion,
        # ungated storage harvest, G8-gated training harvest, and frontend
        # diff/payload mapping are covered by write-edit-capture.
        status="live",
    ),
    3: WriteDeliverable(
        3,
        "block-repository-folders",
        "Block repository folders",
        # Live: cross-investigation folders are membership edges over graph
        # nodes, multi-folder membership does not copy content, deterministic
        # repository search filters by folder/source, provenance survives the
        # folder→node→document chain, and drag-to-outline places the same node.
        # Covered by write-block-repository.
        status="live",
    ),
    4: WriteDeliverable(
        4,
        "structured-block-editor",
        "Structured block editor",
        # Live: TipTap WriteEditor, custom lego/citation nodes, stable block-id
        # locator bridge, generated-draft ProseMirror mounting, no textarea
        # fallback, and granular edit emission are covered by
        # write-structured-editor.
        status="live",
    ),
    5: WriteDeliverable(5, "brainstorm-interview", "Brainstorm interview"),
    6: WriteDeliverable(6, "draft-generation-style", "Draft generation style"),
    7: WriteDeliverable(7, "trace-to-source", "Trace to source"),
    8: WriteDeliverable(8, "pre-outline-freeform", "Pre-outline freeform"),
    9: WriteDeliverable(9, "style-conditioning", "Style conditioning"),
}


def resolve_write_sprint(n: int) -> WriteDeliverable:
    """Resolve a Write sprint number to its frozen deliverable."""
    try:
        return WRITE_SPRINTS[n]
    except KeyError:
        raise KeyError(
            f"Write SPR-{n:02d} is not in the frozen sprint-lock "
            f"(WRITE_LOCK_VERSION={WRITE_LOCK_VERSION}; valid: {sorted(WRITE_SPRINTS)})."
        ) from None
