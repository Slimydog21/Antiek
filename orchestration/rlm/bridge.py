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
from decimal import Decimal

from orchestration.rlm.prime_agent_backend import (
    PrimeAgentRLMBackend,
    PrimeAgentSessionRequest,
)
from orchestration.rlm.session import (
    RLM_DOC_THRESHOLD_TOKENS,
    RLM_SESSION_COST_USD_CAP,
    RLMRatificationRequired,
    RLMSession,
    create_session,
    iterate_session,
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
    # Execution facts, populated only when the bridge drove the session
    # itself (root_executor == "prime_agent"). ``iteration_count`` is the
    # session's recorded iteration count after the drive; ``prime_state``
    # is the Prime receipt's terminal state. Both stay at their defaults
    # on the dispatch path, which the bridge does not drive.
    iteration_count: int = 0
    prime_state: str | None = None

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


_BRIDGE_WORKFLOW = "rlm-bridge-escalation"


def _drive_prime_session(
    session: RLMSession,
    prime_backend: PrimeAgentRLMBackend,
    *,
    document_id: str,
    estimated_tokens: int,
) -> str:
    """Run ONE Prime iteration for a freshly escalated session and record it.

    This is the bridge's entire execution path: one ``run_session`` call and
    one ``iterate_session``. It proves invocation without inventing an
    iteration planner — ``run_rlm_investigation`` is the full orchestrator
    but needs ``plan_iteration_fn``/``final_synthesis_fn``, neither of which
    the bridge has. The iteration is recorded whatever the receipt says, so
    the session log carries the attempt and its terminal state; a failed
    attempt is still an iteration the root executor consumed.

    BLOCKING: ``run_session`` waits on a subprocess for up to the backend's
    timeout. Callers on an event loop must hop to a worker thread.

    Returns the Prime receipt's terminal state value.
    """
    outcome = prime_backend.run_session(
        PrimeAgentSessionRequest(
            goal_brief=session.state.prime_goal_brief or _BRIDGE_WORKFLOW,
            iteration_prompt=(
                f"Document {document_id} is estimated at {estimated_tokens} "
                "tokens, above the RLM threshold. Produce the opening "
                "condensation for the wrestler: the document's thesis, its "
                "load-bearing claims, and the sections a sub-LLM should "
                "read in full."
            ),
            workflow=_BRIDGE_WORKFLOW,
            request_id=f"{session.state.session_id}:iteration:1",
        )
    )
    summary = (
        outcome.evidence.text
        if outcome.evidence is not None
        else f"prime_agent {outcome.receipt.state.value}: {outcome.receipt.detail or 'no detail'}"
    )
    # The one-shot ``-p`` lane returns no usage, so no spend can be
    # attributed here; metering lives in the JSONL-RPC lane
    # (prime_rpc_evidence.py + prime_ledger.py). Zero is "unmetered", not
    # "free", and the session cost cap cannot trip on this path.
    iterate_session(session, summary=summary, cost_usd=Decimal("0"))
    return outcome.receipt.state.value


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

    # Drive the session when Prime is the root executor. Until this call
    # existed the backend was consumed only as a truthiness token above,
    # and the session was created and abandoned: flipping both flags with
    # a binary installed produced a relabelled session and no process.
    prime_state: str | None = None
    if root_executor == "prime_agent":
        assert prime_backend is not None  # _bridge_executor guarantees it
        prime_state = _drive_prime_session(
            session,
            prime_backend,
            document_id=document_id,
            estimated_tokens=estimated_tokens,
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
        iteration_count=session.state.iteration_count,
        prime_state=prime_state,
    )
