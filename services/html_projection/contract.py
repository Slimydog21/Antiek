"""Block taxonomy + rendering contract (HPRJ SPR-02 / M1).

The HTML projection renderer turns a canonical doc-model into self-contained
HTML. A doc-model is the TipTap document the ``.antiek`` container stores as
``content.tiptap.json`` (see ``services/antiek_format/SPEC.md`` §2.2) PLUS
the manifest provenance fields the renderer needs for the footer. The
renderer MUST handle every block type that can appear in that document.

This module is the SINGLE SOURCE OF TRUTH for which block types exist and
how each renders. Every entry cites the code location that defines the type
(file:line) — not a decision doc — so a maintainer who adds a block type to
the substrate/container is mechanically reminded to add a partial here.

Three layers of block types exist in the codebase, and the renderer must
cover the UNION:

1.  **Substrate notebook blocks** — ``substrate/notebooks/__init__.py``
    ``VALID_BLOCK_TYPES`` (the SQL CHECK constraint set; the row-per-block
    substrate store). These are the literate-analysis block types a
    notebook row can carry.

2.  **TipTap/ProseMirror codec types** —
    ``substrate/notebooks/tiptap_codec.py`` ``_TIPTAP_NODE_TO_BLOCK_TYPE``
    maps TipTap custom node names (``note_block``, ``math_block``) onto the
    substrate block types. The TipTap body the container stores uses the
    ``antiek_<block_type>`` naming convention (SPEC.md §2.2).

3.  **Container block types** —
    ``services/antiek_format/manifest.schema.json`` ``blocks_index[*].block_type``
    enum (``highlight_card, voice_block, ai_qa, cite_link, cross_doc_jump,
    prose``). These are the block types the ``.antiek`` container's
    blocks_index carries. The markdown projector
    (``services/antiek_format/markdown_projector.py``) renders the same set.

The renderer keys on the TipTap node ``type`` string (that is what the
doc-model's ``content`` array carries). It accepts both the ``antiek_``
prefixed form (container convention) and the bare form (substrate
convention) for every type, so a doc-model coming from either path renders.

Unknown-block fallback (master-spec invariant: never a silent drop, never a
crash): a node whose ``type`` is not in the contract renders a VISIBLE
``unsupported block (<type>)`` placeholder. The raw node JSON is NOT
inlined into the visible HTML — it stays only inside the inert data island
(round-trip preserves it). This keeps the visible surface honest about what
could not be rendered without leaking unescaped structure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True)
class BlockContract:
    """One row of the rendering contract table.

    Attributes
    ----------
    block_type:
        The canonical (bare) block type name — the substrate row value and
        the ``blocks_index`` value. Never carries the ``antiek_`` prefix.
    tiptap_types:
        Every TipTap node ``type`` string that maps to this block type.
        Always includes ``antiek_<block_type>``; includes the bare name;
        includes any aliased TipTap node name (e.g. ``note_block`` →
        ``note``, ``math_block`` → ``latex``).
    source:
        ``file:line`` citation(s) where this type is defined. Comma-joined
        when more than one location defines it.
    partial:
        The partial module name (under ``services/html_projection/partials/``)
        that renders this block. ``None`` for the prose fallback (rendered
        inline by the core renderer, no dedicated partial needed — but we
        still list the contract row so the taxonomy is complete).
    widget:
        ``True`` if this block type is a widget-call seam reserved for
        SPR-03 (charts/sparklines/dep-graphs). Today no block type is a
        widget; the field is here so SPR-03 can flip it without reshaping
        this table. Out of scope for SPR-02.
    """

    block_type: str
    tiptap_types: tuple[str, ...]
    source: str
    partial: str | None
    widget: bool = False


# ── The contract table ──
#
# Order is the canonical rendering-precedence order (prose first as the
# fallback bedrock; then container block types; then substrate-only block
# types). Order does NOT affect rendering dispatch (dispatch is by an
# O(1) dict built below) — it exists so a human reading the table top to
# bottom sees the common types first.
#
# Cited file:line values are stable references to the lines that DEFINE
# each type. They were captured at SPR-02 build time against the tree on
# branch html-projection/land-antiek at commit 24eed084.

CONTRACT_TABLE: Final[tuple[BlockContract, ...]] = (
    # ── Container block types (manifest.schema.json blocks_index enum) ──
    # All six are defined by services/antiek_format/manifest.schema.json
    # lines 76-83 (the block_type enum) and rendered by the markdown
    # projector (services/antiek_format/markdown_projector.py:159-216).

    BlockContract(
        block_type="prose",
        tiptap_types=("antiek_prose", "prose", "paragraph", "doc"),
        source=(
            "substrate/notebooks/__init__.py:41 "
            "(VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:91 "
            "(default decompose target); "
            "services/antiek_format/manifest.schema.json:83 "
            "(blocks_index enum)"
        ),
        partial=None,  # rendered inline by core renderer (text flatten)
    ),
    BlockContract(
        block_type="highlight_card",
        tiptap_types=("antiek_highlight_card", "highlight_card"),
        source=(
            "services/antiek_format/manifest.schema.json:77 "
            "(blocks_index enum); "
            "services/antiek_format/markdown_projector.py:159 "
            "(rendered as antiek_highlight_card/highlight_card)"
        ),
        partial="highlight_card",
    ),
    BlockContract(
        block_type="voice_block",
        tiptap_types=("antiek_voice_block", "voice_block"),
        source=(
            "services/antiek_format/manifest.schema.json:78 "
            "(blocks_index enum); "
            "services/antiek_format/markdown_projector.py:167 "
            "(rendered as antiek_voice_block/voice_block); "
            "services/antiek_format/SPEC.md:47 (blocks/<block_id>.audio)"
        ),
        partial="voice_block",
    ),
    BlockContract(
        block_type="ai_qa",
        tiptap_types=("antiek_ai_qa", "ai_qa"),
        source=(
            "services/antiek_format/manifest.schema.json:79 "
            "(blocks_index enum); "
            "services/antiek_format/markdown_projector.py:191 "
            "(rendered as antiek_ai_qa/ai_qa)"
        ),
        partial="ai_qa",
    ),
    BlockContract(
        block_type="cite_link",
        tiptap_types=("antiek_cite_link", "cite_link"),
        source=(
            "services/antiek_format/manifest.schema.json:80 "
            "(blocks_index enum); "
            "services/antiek_format/markdown_projector.py:204 "
            "(rendered as antiek_cite_link/cite_link)"
        ),
        partial="cite_link",
    ),
    BlockContract(
        block_type="cross_doc_jump",
        tiptap_types=("antiek_cross_doc_jump", "cross_doc_jump"),
        source=(
            "services/antiek_format/manifest.schema.json:81 "
            "(blocks_index enum); "
            "services/antiek_format/markdown_projector.py:209 "
            "(rendered as antiek_cross_doc_jump/cross_doc_jump)"
        ),
        partial="cross_doc_jump",
    ),

    # ── Substrate-only notebook block types ──
    # Defined by substrate/notebooks/__init__.py:40-51 VALID_BLOCK_TYPES
    # and mapped by substrate/notebooks/tiptap_codec.py:46-56
    # _TIPTAP_NODE_TO_BLOCK_TYPE. These carry ref_id (a live substrate
    # reference) resolved at render time (M6 tombstone semantics).
    BlockContract(
        block_type="region_embed",
        tiptap_types=("antiek_region_embed", "region_embed"),
        source=(
            "substrate/notebooks/__init__.py:42 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:47 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: region_embed→region_embed, "
            "attrs.document_id)"
        ),
        partial="region_embed",
    ),
    BlockContract(
        block_type="claim_card",
        tiptap_types=("antiek_claim_card", "claim_card"),
        source=(
            "substrate/notebooks/__init__.py:43 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:46 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: claim_card→claim_card, "
            "attrs.claim_id)"
        ),
        partial="claim_card",
    ),
    BlockContract(
        block_type="note",
        tiptap_types=("antiek_note", "note", "note_block"),
        source=(
            "substrate/notebooks/__init__.py:44 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:48 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: note_block→note, "
            "attrs.note_id)"
        ),
        partial="note",
    ),
    BlockContract(
        block_type="question_card",
        tiptap_types=("antiek_question_card", "question_card"),
        source=(
            "substrate/notebooks/__init__.py:45 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:51 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: question_card→question_card, "
            "attrs.question_id)"
        ),
        partial="question_card",
    ),
    BlockContract(
        block_type="cross_doc_link",
        tiptap_types=("antiek_cross_doc_link", "cross_doc_link"),
        source=(
            "substrate/notebooks/__init__.py:46 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:49 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: cross_doc_link→cross_doc_link, "
            "attrs.source_document_id)"
        ),
        partial="cross_doc_link",
    ),
    BlockContract(
        block_type="chat_exchange",
        tiptap_types=("antiek_chat_exchange", "chat_exchange"),
        source=(
            "substrate/notebooks/__init__.py:47 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:52 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: chat_exchange→chat_exchange, "
            "attrs.exchange_id)"
        ),
        partial="chat_exchange",
    ),
    BlockContract(
        block_type="master_md_section",
        tiptap_types=("antiek_master_md_section", "master_md_section"),
        source=(
            "substrate/notebooks/__init__.py:48 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:50 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: master_md_section→"
            "master_md_section, attrs.synthesis_id)"
        ),
        partial="master_md_section",
    ),
    BlockContract(
        block_type="image",
        tiptap_types=("antiek_image", "image"),
        source=(
            "substrate/notebooks/__init__.py:49 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:54 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: image→image, attrs.image_id)"
        ),
        partial="image",
    ),
    BlockContract(
        block_type="latex",
        tiptap_types=("antiek_latex", "latex", "math_block"),
        source=(
            "substrate/notebooks/__init__.py:50 (VALID_BLOCK_TYPES); "
            "substrate/notebooks/tiptap_codec.py:55 "
            "(_TIPTAP_NODE_TO_BLOCK_TYPE: math_block→latex)"
        ),
        partial="latex",
    ),
)


def _build_dispatch() -> dict[str, BlockContract]:
    """Build the TipTap-type → contract dispatch map.

    Every ``tiptap_types`` alias for a contract row maps to that row.
    A node's ``type`` is looked up here; a miss means unknown-block
    fallback. This is O(1) and built once at import.
    """
    dispatch: dict[str, BlockContract] = {}
    for contract in CONTRACT_TABLE:
        for tt in contract.tiptap_types:
            dispatch[tt] = contract
    return dispatch


_TIPTAP_TYPE_TO_CONTRACT: Final[dict[str, BlockContract]] = _build_dispatch()


def contract_for_tiptap_type(tiptap_type: str) -> BlockContract | None:
    """Return the contract for a TipTap node ``type``, or ``None`` if the
    type is unknown (caller renders the unsupported-block fallback)."""
    return _TIPTAP_TYPE_TO_CONTRACT.get(tiptap_type)


def known_block_types() -> frozenset[str]:
    """The canonical (bare) block type names the renderer handles."""
    return frozenset(c.block_type for c in CONTRACT_TABLE)


def known_tiptap_types() -> frozenset[str]:
    """Every TipTap node ``type`` string the renderer dispatches on."""
    return frozenset(_TIPTAP_TYPE_TO_CONTRACT.keys())


__all__ = [
    "CONTRACT_TABLE",
    "BlockContract",
    "contract_for_tiptap_type",
    "known_block_types",
    "known_tiptap_types",
]
