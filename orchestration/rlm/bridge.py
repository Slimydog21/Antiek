"""RLM bridge — long-doc escalation entry point.

Wires the wrestling surface (interfaces/research/api/wrestling.py) to the
RLM session orchestrator (orchestration/rlm/session.py). The bridge is
the single decision point that asks: 'does this document need RLM
mode?' and either escalates (creating an ``RLMSession``) or records the
deferral and lets the existing single-call wrestling path run.

Per master-spec §11.6 + rlm_integration_spec.md RLM-1:

1. Documents above ``RLM_DOC_THRESHOLD_TOKENS`` (default 64 000) are
   the target population for RLM-1.
2. Escalation is gated by ``ANTIEK_RLM_RATIFIED=1`` (the §6 design
   decisions must be checked off first). When the env var is absent,
   the bridge logs an ``rlm_deferred`` decision but does NOT raise —
   the document still gets ingested via the existing single-call path.
3. The bridge never instantiates tools at the root level (per the
   tool-isolation invariant); it just creates an empty session for the
   wrestling driver to populate later.

Estimating token count from ``size_bytes`` is conservative:
``estimated_tokens = size_bytes // RLM_BYTES_PER_TOKEN_ESTIMATE`` (4).
The estimator is intentionally crude — a more precise tokenizer-based
count belongs downstream once the document has been chunked.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from orchestration.rlm.prime_agent_backend import PrimeAgentRLMBackend
from orchestration.rlm.session import (
    RLM_DOC_THRESHOLD_TOKENS,
    RLM_SESSION_COST_USD_CAP,
    RLMRatificationRequired,
    create_session,
)
from substrate.schemas.events import RLMBridgeDecidedPayload

RLM_BYTES_PER_TOKEN_ESTIMATE: int = 4
"""Rough char-to-token ratio used at document-load time when we have
``size_bytes`` but no tokenizer output yet. Conservative: 4 bytes per
token under-estimates for technical/code-heavy docs (which is the safer
direction — under-counts skip RLM, they don't trigger unnecessary
escalations)."""


@dataclass(frozen=True)
class RLMBridgeDecision:
    """Verdict emitted by the bridge for a single document."""

    document_id: str
    investigation_id: str
    estimated_tokens: int
    threshold_tokens: int
    above_threshold: bool
    ratified: bool
    escalated: bool
    session_id: str | None
    reason: str

    def to_typed_payload(self) -> RLMBridgeDecidedPayload:
        """Materialize this decision as the canonical typed event
        payload for the trajectory. Callers wired into the event
        broadcaster use this to land an ``rlm.bridge.decided`` row.

        ``reason`` is constrained to the Literal set the payload
        accepts; the decision dataclass's free-form 'escalated_to_rlm'
        reason (which currently includes the cost cap suffix) is
        normalized to the literal here.
        """
        if self.reason.startswith("escalated_to_rlm"):
            reason: str = "escalated_to_rlm"
        else:
            reason = self.reason
        return RLMBridgeDecidedPayload(
            document_id_ref=self.document_id,
            estimated_tokens=self.estimated_tokens,
            threshold_tokens=self.threshold_tokens,
            above_threshold=self.above_threshold,
            ratified=self.ratified,
            escalated=self.escalated,
            session_id=self.session_id,
            reason=reason,  # type: ignore[arg-type]
        )


def estimate_tokens_from_bytes(size_bytes: int) -> int:
    """Conservative size→token estimate for document-load events.

    Returns 0 for missing/invalid sizes (treated as below-threshold)."""
    if size_bytes <= 0:
        return 0
    return size_bytes // RLM_BYTES_PER_TOKEN_ESTIMATE


def is_ratified() -> bool:
    """Whether the operator has ratified the §6 RLM design decisions."""
    return os.environ.get("ANTIEK_RLM_RATIFIED", "") == "1"


def _prime_agent_enabled() -> bool:
    return os.environ.get("ANTIEK_PRIME_AGENT_RLM_ENABLED", "") == "1"


def _bridge_executor(prime_backend: PrimeAgentRLMBackend | None) -> str:
    if prime_backend is not None and _prime_agent_enabled() and is_ratified():
        return "prime_agent"
    return "dispatch"


def maybe_escalate_to_rlm(
    *,
    document_id: str,
    investigation_id: str,
    estimated_tokens: int,
    root_role: str = "wrestler",
    threshold_tokens: int = RLM_DOC_THRESHOLD_TOKENS,
    prime_backend: PrimeAgentRLMBackend | None = None,
) -> RLMBridgeDecision:
    """Decide whether this document warrants an RLM session.

    Returns an ``RLMBridgeDecision`` describing the verdict. The
    function NEVER raises ``RLMRatificationRequired`` — under
    not-ratified state it deterministically records ``escalated=False``
    and ``reason='deferred_pending_ratification'`` so the wrestling
    surface continues on the single-call path.

    The session-creation branch can still raise on misuse (e.g. cost
    cap violations later in iteration), but the decision call itself
    is side-effect-light: it creates an ``RLMSession`` only when both
    above-threshold AND ratified hold.

    Per the cost-attribution decision (§6.2 ratification list): the
    session is attributed to ``root_role``, which the caller passes —
    typically ``'wrestler'`` for document-loaded escalations.
    """
    above = estimated_tokens >= threshold_tokens
    ratified = is_ratified()

    if not above:
        return RLMBridgeDecision(
            document_id=document_id,
            investigation_id=investigation_id,
            estimated_tokens=estimated_tokens,
            threshold_tokens=threshold_tokens,
            above_threshold=False,
            ratified=ratified,
            escalated=False,
            session_id=None,
            reason="below_threshold",
        )

    if not ratified:
        return RLMBridgeDecision(
            document_id=document_id,
            investigation_id=investigation_id,
            estimated_tokens=estimated_tokens,
            threshold_tokens=threshold_tokens,
            above_threshold=True,
            ratified=False,
            escalated=False,
            session_id=None,
            reason="deferred_pending_ratification",
        )

    root_executor = _bridge_executor(prime_backend)
    try:
        session = create_session(
            investigation_id=investigation_id,
            root_role=root_role,
            document_id=document_id,
            root_executor=root_executor,
            prime_goal_brief=(
                "RLM long-doc wrestling session rooted at bridge escalation"
                if root_executor == "prime_agent"
                else None
            ),
        )
    except RLMRatificationRequired:
        # Defensive: env var was set when is_ratified() returned True,
        # but flipped between check and call. Treat as deferred.
        return RLMBridgeDecision(
            document_id=document_id,
            investigation_id=investigation_id,
            estimated_tokens=estimated_tokens,
            threshold_tokens=threshold_tokens,
            above_threshold=True,
            ratified=False,
            escalated=False,
            session_id=None,
            reason="deferred_pending_ratification",
        )

    return RLMBridgeDecision(
        document_id=document_id,
        investigation_id=investigation_id,
        estimated_tokens=estimated_tokens,
        threshold_tokens=threshold_tokens,
        above_threshold=True,
        ratified=True,
        escalated=True,
        session_id=session.state.session_id,
        reason=(
            f"escalated_to_rlm cap_usd={RLM_SESSION_COST_USD_CAP}"
        ),
    )
