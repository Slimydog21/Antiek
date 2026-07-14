"""Speak ↔ Write SPR-01 — the OutlineComposer drop-in (the "later" arrived).

When Speak SPR-08 shipped, ``substrate/write/`` did not exist, so biography
outlines were persisted via ``biography.SpeakOutlineComposer`` (the legacy
``section_blocks`` table) against the ``contracts.OutlineComposer`` Protocol.
Write has since landed (``substrate/write/outline_block.place_block``), and
its ``outline_blocks`` table is the canonical composition layer that
**supersedes** ``section_blocks``. So this module supplies the contract's
intended real implementation: ``WriteOutlineComposer`` composes a biography
outline through Write's lego-block layer, so Speak no longer forks onto the
legacy substrate — exactly the "Write's composer drops in later" the
execution record promised.

The mapping (technical taste, made honest):

A Speak biography block is an interview-attested *claim* living in
``speak_claims`` — NOT a graph node. Write's taxonomy gives a block two
provenance shapes: ``graph_node`` (requires a ``node_id``; content null) or
user-originated (``user_authored`` / ``synthesized`` / ``brainstorm``;
``node_id`` null, inline ``content``). A speak_claim has no graph node, and
promoting it to one carries the same G2/G3-class shared-graph consent weight
this workflow keeps operator-gated (see ``drw_gap_source``). So a Speak block
maps to a **``synthesized``** outline block — the outline unit IS a
composition synthesized from the interview claim — carrying:

  • ``content``           = the claim text (what the deliverable already uses);
  • ``source_block_kind`` = ``"speak_claim"`` + ``source_block_id`` = claim_id
    (the provenance link back to the speak_claim of record — never lost);
  • ``metadata.speak_block_kind`` = the original Speak kind (claim/insight/…);
  • ``metadata.contributor_interview_ids`` = the SPR-06 split provenance, now
    self-describing INSIDE the canonical layer (not only in Speak's Outline
    object).

This stays consent-safe: the claim text is already in the (private)
deliverable the draft is built from; the publish gate still controls public
exposure. No speak_claim is promoted to the shared graph.
"""

from __future__ import annotations

from typing import Any

from .contracts import OutlineBlock, OutlineComposer

# Speak claims are interview-attested, non-node content; the outline block is
# a composition synthesized from them. ("synthesized","synthesized") is the
# only coherent Write pair for non-node inline content (see _COHERENT_PAIRS).
_SPEAK_BLOCK_PROVENANCE = "synthesized"
_SPEAK_OUTLINE_BLOCK_KIND = "synthesized"


class WriteOutlineComposer:
    """``contracts.OutlineComposer`` backed by Write's canonical
    ``outline_blocks`` layer (``substrate.write.place_block``)."""

    def __init__(
        self,
        con: Any,
        *,
        investigation_id: str = "__operator__",
        emit_events: bool = True,
    ):
        self.con = con
        self.investigation_id = investigation_id
        self.emit_events = emit_events

    def compose(self, *, deliverable_id: str, section_title: str, blocks: list[OutlineBlock]) -> str:
        from substrate.graph.ops import insert_section
        from substrate.write.outline_block import place_block

        section_id = insert_section(
            self.con, deliverable_id=deliverable_id, section_index=0, title=section_title,
        )
        idx = 0
        for b in blocks:
            content = (b.body or b.label or "").strip()
            if not content:
                # Write refuses orphan (contentless) non-node blocks; a claim
                # with no text is not composable — skip rather than fabricate.
                continue
            place_block(
                self.con,
                section_id=section_id,
                block_kind=_SPEAK_OUTLINE_BLOCK_KIND,
                provenance_kind=_SPEAK_BLOCK_PROVENANCE,
                block_index=idx,
                content=content,
                source_block_kind="speak_claim",
                source_block_id=b.block_id,
                deliverable_id=deliverable_id,
                investigation_id=self.investigation_id,
                metadata={
                    "speak_block_kind": b.block_kind,
                    "contributor_interview_ids": list(b.contributor_interview_ids),
                    "source_tier": b.source_tier,
                },
                on_conflict="ignore",
                emit_event=self.emit_events,
            )
            idx += 1
        return section_id


def default_outline_composer(con: Any, *, investigation_id: str = "__operator__") -> OutlineComposer:
    """The SPR-08 default now that Write exists: compose through Write's
    canonical ``outline_blocks`` layer. Falls back to the legacy
    ``SpeakOutlineComposer`` (``section_blocks``) if Write is unavailable.
    Imported lazily by ``biography`` to avoid an import cycle."""
    try:
        import substrate.write.outline_block  # noqa: F401 — availability probe
    except ImportError:  # pragma: no cover — Write not present
        from .biography import SpeakOutlineComposer
        return SpeakOutlineComposer(con)
    return WriteOutlineComposer(con, investigation_id=investigation_id)
