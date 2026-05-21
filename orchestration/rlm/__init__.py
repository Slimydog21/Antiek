"""Recursive Language Models — long-doc wrestling bridge (RLM track).

Per `rlm_integration_spec.md` RLM-1: long-doc wrestling RLM bridge.
Load-bearing; ~600 LOC. Sprint 19+ parallel track (per
`rlm_integration_spec.md` §6 six design decisions await ratification
before RLM-1 starts).

The current Antiek wrestling bridge can't handle long PDFs (>64K
tokens) because the synthesizer's context budget caps out. The RLM
bridge dispatches an inner LLM-with-tools that walks the document
hierarchically — chunk → section → document — emitting an
`rlm.session_started` event at the start and an `rlm.session_completed`
event at the end, with `rlm.iteration` events along the way.

This module ships the orchestrator skeleton + ratification-gated
session entry point. Tool-isolation discipline per
`rlm_integration_spec.md`: every sub-LLM tool attaches to
`SubLLMWithTools`, never the root REPL (Paper §2 choice #3, static
check enforced).
"""

from .bridge import (
    RLM_BYTES_PER_TOKEN_ESTIMATE,
    RLMBridgeDecision,
    estimate_tokens_from_bytes,
    is_ratified,
    maybe_escalate_to_rlm,
)
from .session import (
    RLM_DOC_THRESHOLD_TOKENS,
    RLM_SESSION_COST_USD_CAP,
    RLMRatificationRequired,
    RLMSession,
    RLMSessionState,
    SubLLMWithTools,
    create_session,
    iterate_session,
)

__all__ = [
    "RLM_BYTES_PER_TOKEN_ESTIMATE",
    "RLM_DOC_THRESHOLD_TOKENS",
    "RLM_SESSION_COST_USD_CAP",
    "RLMBridgeDecision",
    "RLMRatificationRequired",
    "RLMSession",
    "RLMSessionState",
    "SubLLMWithTools",
    "create_session",
    "estimate_tokens_from_bytes",
    "is_ratified",
    "iterate_session",
    "maybe_escalate_to_rlm",
]
