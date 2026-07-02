"""Write deliverable → doc-model adapter (HPRJ SPR-06 M3).

Per the M1 decision, the Write substrate (`substrate/write/`) has its own block
model — an outline tree of sections, each holding ``OutlineBlock``s typed by
``block_kind`` (`insight` / `open_question` / `operator_note` / `claim` /
`user_authored` / `synthesized`). This adapter maps that model into doc-model
JSON the SPR-02 renderer accepts (mirroring the SPR-05 synthesis adapter):

- known ``block_kind``  -> a semantic renderer node (claim_card / question_card /
  note / prose / master_md_section), rendered INLINE (no ref_id, so no resolver
  is needed and the doc-model is self-contained);
- UNKNOWN ``block_kind`` -> a visible unsupported-placeholder node, NEVER a
  silent drop (the renderer's unsupported partial renders it);
- a block that quotes a non-servable source -> CITE-ONLY (the SPR-05 contract,
  `SERVABLE_CONTENT_CLASSES` REUSED): the passage is withheld, only a
  title-ip_holder notice is emitted. The rights filter lives in this adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from substrate.constants import SERVABLE_CONTENT_CLASSES

# The known Write block kinds (substrate/write/outline_block.py BLOCK_KINDS).
_KNOWN_KINDS: frozenset[str] = frozenset(
    {"insight", "open_question", "operator_note", "claim", "user_authored", "synthesized"}
)
_CLAIM_LIKE: frozenset[str] = frozenset({"claim", "insight", "synthesized"})


@dataclass(frozen=True)
class DeliverableBlock:
    block_kind: str
    text: str
    # If the block quotes an external source, its rights; None => the block is
    # the user's / graph's own content (operator-authored), not a third-party
    # quote, and is not rights-filtered.
    content_class: str | None = None
    ip_holder_id: str | None = None
    source_title: str | None = None
    # The source document id (when known) — a stable knowledge-graph node
    # identity; the title alone collides across same-named documents.
    source_document_id: str | None = None

    @property
    def servable(self) -> bool:
        return (
            self.content_class is None
            or self.content_class in SERVABLE_CONTENT_CLASSES
        )


@dataclass(frozen=True)
class DeliverableSection:
    heading: str
    blocks: list[DeliverableBlock] = field(default_factory=list)


@dataclass(frozen=True)
class DeliverableExport:
    title: str
    sections: list[DeliverableSection] = field(default_factory=list)


def _cite_only_notice(b: DeliverableBlock) -> str:
    parts = [b.source_title or "source"]
    if b.ip_holder_id:
        parts.append(b.ip_holder_id)
    return (
        f"[cite-only — {' · '.join(parts)}; full text withheld under the "
        f"source's rights]"
    )


def unsupported_block_kinds(export: DeliverableExport) -> list[str]:
    """The Write-only block kinds this export carries that the renderer has no
    semantic node for (they render the visible placeholder). Surfaced in
    metadata + the handoff so the gap is named, not hidden."""
    return sorted(
        {
            b.block_kind
            for s in export.sections
            for b in s.blocks
            if b.block_kind not in _KNOWN_KINDS
        }
    )


def _block_node(b: DeliverableBlock) -> dict:
    if b.block_kind not in _KNOWN_KINDS:
        # Visible unsupported placeholder — the renderer's unsupported partial
        # renders the unknown type; never a silent drop.
        return {
            "type": f"write_unsupported__{b.block_kind}",
            "attrs": {"kind": b.block_kind},
        }
    if not b.servable:
        return {"type": "antiek_note", "attrs": {"body": _cite_only_notice(b)}}
    if b.block_kind in _CLAIM_LIKE:
        return {"type": "antiek_claim_card", "attrs": {"statement": b.text}}
    if b.block_kind == "open_question":
        return {"type": "antiek_question_card", "attrs": {"question": b.text}}
    if b.block_kind == "operator_note":
        return {"type": "antiek_note", "attrs": {"body": b.text}}
    # user_authored
    return {"type": "paragraph", "content": [{"type": "text", "text": b.text}]}


def adapt_deliverable(export: DeliverableExport) -> dict:
    """Adapt a Write deliverable to the doc-model. Inline nodes only (no
    ref_ids), so the result renders self-contained with the default context."""
    content: list[dict] = []
    for section in export.sections:
        content.append(
            {"type": "antiek_master_md_section", "attrs": {"heading": section.heading}}
        )
        for block in section.blocks:
            content.append(_block_node(block))
    # Knowledge-graph edges: the unique cited source TITLES (rights-safe — a
    # citation, never the passage). The block carries no document id, so the
    # title is the node identity; deduped in first-seen order.
    cited: dict[str, tuple[str, bool]] = {}
    for section in export.sections:
        for block in section.blocks:
            if not block.source_title:
                continue
            node_id = block.source_document_id or block.source_title
            if node_id not in cited:
                cited[node_id] = (block.source_title, block.servable)
    return {
        "title": export.title,
        "content": content,
        "edges": [
            {
                "kind": "cites",
                "to_document_id": node_id,
                "to_title": label,
                "tone": "success" if servable else "warning",
            }
            for node_id, (label, servable) in cited.items()
        ],
        "metadata": {"unsupported_block_kinds": unsupported_block_kinds(export)},
    }


__all__ = [
    "DeliverableBlock",
    "DeliverableExport",
    "DeliverableSection",
    "adapt_deliverable",
    "unsupported_block_kinds",
]
