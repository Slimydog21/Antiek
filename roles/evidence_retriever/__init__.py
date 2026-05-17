"""Evidence Retriever role (Sprint 6 day 4-5 — extraction begins).

Second orchestrate.py role to land. Same surgical pattern Day 1-2
established for the decomposer:

- ``prompt`` — verbatim port of ``prompts/evidence_retriever.md``.
  System prompt + user template + ``render_full_prompt``.
- ``parser`` — closed-vocabulary JSON parser. ``EvidenceResult``
  dataclass. ``source_tier_min`` enforces the upstream's null /
  ``[1,5]`` rule (``0`` is forbidden — the prompt explicitly warns).

What's deferred to Sprint 7:

- ``interfaces/research/api/evidence_retriever.py`` bridge handler
  (subscribes to ``evidence.retrieve_requested`` → dispatch →
  parse → emit ``evidence.retrieve_delivered``). Builds on the
  decomposer bridge pattern + the existing ``EVIDENCE_PACK_BUILT``
  ActionType.
- Typed payloads (``EvidenceRetrieveRequestedPayload`` /
  ``EvidenceRetrieveDeliveredPayload``). Schema additions land
  alongside the bridge so the typed seam closes in one slice.
- Chunks/subgraph rendering — the bridge concatenates retrieval
  results into ``chunks_block`` / ``subgraph_block`` for the prompt.
"""

from .parser import (
    EVIDENCE_CONFIDENCE_LEVELS,
    EVIDENCE_TYPES,
    SOURCE_TIER_MAX_VALUE,
    SOURCE_TIER_MIN_VALUE,
    EvidenceResult,
    EvidenceValidationError,
    ParsedClaim,
    ParsedGap,
    parse_evidence_response,
)
from .prompt import (
    EVIDENCE_RETRIEVER_PROMPT_VERSION,
    EVIDENCE_RETRIEVER_SYSTEM_PROMPT,
    EVIDENCE_RETRIEVER_TARGET_MODEL,
    EVIDENCE_RETRIEVER_TEMPERATURE,
    EVIDENCE_RETRIEVER_USER_TEMPLATE,
    render_full_prompt,
    render_user_template,
)

__all__ = [
    # parser
    "EVIDENCE_TYPES",
    "EVIDENCE_CONFIDENCE_LEVELS",
    "SOURCE_TIER_MIN_VALUE",
    "SOURCE_TIER_MAX_VALUE",
    "EvidenceValidationError",
    "ParsedClaim",
    "ParsedGap",
    "EvidenceResult",
    "parse_evidence_response",
    # prompt
    "EVIDENCE_RETRIEVER_PROMPT_VERSION",
    "EVIDENCE_RETRIEVER_TARGET_MODEL",
    "EVIDENCE_RETRIEVER_TEMPERATURE",
    "EVIDENCE_RETRIEVER_SYSTEM_PROMPT",
    "EVIDENCE_RETRIEVER_USER_TEMPLATE",
    "render_user_template",
    "render_full_prompt",
]
