"""Recursive twin note-taker — LLM-proposed insight/question twin per asset.

Contains the signed twin-generation core (``generate``), the substrate search
layer (``search``), and the graph-promotion planner (``promotion_planner``) for
advisory promotion of twin material into the canonical knowledge graph.
"""

from .generate import (
    AUTHORITY_VERIFY_KEY_ENV,
    MAX_CONTENT_CHARS,
    MAX_CONTENT_CLASS_CHARS,
    MAX_EVENT_ID_CHARS,
    MAX_EXPIRY_UNIX,
    MAX_IDENTIFIER_CHARS,
    MAX_INSIGHTS,
    MAX_PROPOSAL_ITEM_CHARS,
    MAX_QUESTIONS,
    MAX_SIGNATURE_CHARS,
    MAX_SOURCE_EVENTS,
    MAX_SYNTHESIS_CHARS,
    MAX_TITLE_CHARS,
    MAX_TOTAL_PROPOSAL_CHARS,
    MIN_CONTENT_CHARS,
    TWIN_AUTHORITY,
    AssetContent,
    ProposedInsight,
    ProposedQuestion,
    TwinDocument,
    TwinGenerationError,
    TwinGenerationReceipt,
    TwinProposal,
    generate_twin,
    proposal_receipt_hash,
    source_asset_receipt_hash,
)

__all__ = [
    "AUTHORITY_VERIFY_KEY_ENV",
    "MAX_CONTENT_CHARS",
    "MAX_CONTENT_CLASS_CHARS",
    "MAX_EVENT_ID_CHARS",
    "MAX_EXPIRY_UNIX",
    "MAX_IDENTIFIER_CHARS",
    "MAX_INSIGHTS",
    "MAX_PROPOSAL_ITEM_CHARS",
    "MAX_QUESTIONS",
    "MAX_SIGNATURE_CHARS",
    "MAX_SOURCE_EVENTS",
    "MAX_SYNTHESIS_CHARS",
    "MAX_TITLE_CHARS",
    "MAX_TOTAL_PROPOSAL_CHARS",
    "MIN_CONTENT_CHARS",
    "TWIN_AUTHORITY",
    "AssetContent",
    "ProposedInsight",
    "ProposedQuestion",
    "TwinDocument",
    "TwinGenerationError",
    "TwinGenerationReceipt",
    "TwinProposal",
    "generate_twin",
    "proposal_receipt_hash",
    "source_asset_receipt_hash",
]
