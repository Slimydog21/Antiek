"""TipTap ProseMirror JSON ↔ notebook_blocks codec.

Bridges the UI-redesign sprint-7 TipTap editor (which speaks
ProseMirror JSON) and the master-spec §4.2 notebook substrate (which
stores one row per block in ``notebook_blocks``).

The substrate is row-per-block so substrate-citation blocks
(``claim_card``, ``region_embed``, etc.) can reference live graph
state by ``ref_id`` and the renderer fetches the current substrate
state at render time per §4.2's substrate-as-source-of-truth
invariant. The TipTap editor serialises its document to a single
ProseMirror JSON tree; this codec translates between the two shapes
without ever denormalising substrate content into the notebook.

Round-trip property: ``compose(decompose(doc)) == doc`` for any
TipTap document with only the block types in
``VALID_NOTEBOOK_BLOCK_TYPES``. Block types outside that set are
preserved as ``prose`` blocks with the raw node JSON embedded so
nothing is silently dropped on save.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

VALID_BLOCK_TYPES: frozenset[str] = frozenset({
    "prose",
    "region_embed",
    "claim_card",
    "note",
    "question_card",
    "cross_doc_link",
    "chat_exchange",
    "master_md_section",
    "image",
    "latex",
})


# Map TipTap node names → notebook_blocks block_type. TipTap custom
# nodes are registered with these exact names in
# ``apps/reading/src/modes/Notebook/blocks/*.tsx``; if those node
# names change, this map must follow.
_TIPTAP_NODE_TO_BLOCK_TYPE: dict[str, str] = {
    "claim_card": "claim_card",
    "region_embed": "region_embed",
    "note_block": "note",
    "cross_doc_link": "cross_doc_link",
    "master_md_section": "master_md_section",
    "question_card": "question_card",
    "chat_exchange": "chat_exchange",
    "image": "image",
    "math_block": "latex",
}


@dataclass(frozen=True)
class DecomposedBlock:
    """One block's worth of TipTap content, ready to write as a row."""

    block_type: str
    ref_id: str | None
    content_json: dict[str, Any]


def decompose(tiptap_doc: dict[str, Any]) -> list[DecomposedBlock]:
    """Convert a TipTap document JSON into ordered block rows.

    The TipTap doc shape is ``{type: 'doc', content: [...nodes]}``;
    each top-level child becomes one row. Custom Antiek nodes map to
    their substrate block_type; everything else becomes a ``prose``
    block carrying the raw node JSON.
    """
    if not isinstance(tiptap_doc, dict):
        raise ValueError("tiptap_doc must be an object")
    if tiptap_doc.get("type") != "doc":
        raise ValueError("tiptap_doc.type must be 'doc'")
    content = tiptap_doc.get("content")
    if content is None:
        return []
    if not isinstance(content, list):
        raise ValueError("tiptap_doc.content must be a list")

    blocks: list[DecomposedBlock] = []
    for node in content:
        if not isinstance(node, dict):
            raise ValueError("each top-level node must be an object")
        node_type = node.get("type", "")
        block_type = _TIPTAP_NODE_TO_BLOCK_TYPE.get(node_type, "prose")
        attrs = node.get("attrs") or {}
        ref_id = _extract_ref_id(block_type, attrs)
        blocks.append(
            DecomposedBlock(
                block_type=block_type,
                ref_id=ref_id,
                content_json=node,
            )
        )
    return blocks


def compose(blocks: list[dict[str, Any]]) -> dict[str, Any]:
    """Reverse of ``decompose``. Reconstruct a TipTap document JSON
    from ordered block rows. Used on notebook load so the TipTap
    editor can render the persisted state.

    Each block in ``blocks`` must carry a ``content_json`` field
    holding the original TipTap node JSON; if missing, a minimal
    placeholder prose node is synthesised so the editor doesn't
    crash on round-trip with malformed data.
    """
    content: list[dict[str, Any]] = []
    for block in blocks:
        node_json = block.get("content_json")
        if isinstance(node_json, str):
            # Allow content_json passed as a JSON string (matches the
            # substrate's TEXT column shape on round-trip from DuckDB).
            try:
                node_json = json.loads(node_json)
            except json.JSONDecodeError:
                node_json = None
        if not isinstance(node_json, dict):
            node_json = {
                "type": "paragraph",
                "content": [{"type": "text", "text": "(empty)"}],
            }
        content.append(node_json)
    return {"type": "doc", "content": content}


def _extract_ref_id(block_type: str, attrs: dict[str, Any]) -> str | None:
    """Pull the substrate reference id out of a node's attrs.

    Each substrate-citation block type has its own attribute name —
    ``claim_id`` for claim_card, ``document_id`` for region_embed,
    etc. The substrate's ``ref_id`` column is the single canonical
    handle; this function normalises into it.
    """
    if block_type == "claim_card":
        return _str_or_none(attrs.get("claim_id"))
    if block_type == "region_embed":
        return _str_or_none(attrs.get("document_id"))
    if block_type == "note":
        return _str_or_none(attrs.get("note_id"))
    if block_type == "question_card":
        return _str_or_none(attrs.get("question_id"))
    if block_type == "cross_doc_link":
        # Cross-doc carries source + target; we record the source
        # as the canonical ref. Both are stored in content_json for
        # the renderer.
        return _str_or_none(attrs.get("source_document_id"))
    if block_type == "chat_exchange":
        return _str_or_none(attrs.get("exchange_id"))
    if block_type == "master_md_section":
        return _str_or_none(attrs.get("synthesis_id"))
    if block_type == "image":
        return _str_or_none(attrs.get("image_id"))
    return None


def _str_or_none(value: Any) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s else None
