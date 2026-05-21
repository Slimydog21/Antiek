"""Skill registry writer — drains a ``SkillRuleAccumulator`` and
materializes promoted rules into the shared substrate skill registry.

Per master-spec §13.2 + §13.9 Phase 2 + §13.7 audit:

  - Promotion requires the accumulator's ``PromotionDecision.promote
    == True``: distinct contributors ≥ MIN_USERS_FOR_PROMOTION AND
    cumulative ε ≤ §16.2 cap.
  - The writer holds the shared substrate's writer lock (the caller
    passes a ``LockedConnection``); the single-writer invariant is
    preserved.
  - Every successful promotion emits a typed audit event so the
    operator can reconstruct cross-user provenance from the
    trajectory alone.

The writer is intentionally side-effect-light: it converts decisions
to digests, calls the existing ``propagate_to_shared_substrate``, and
emits one event per write. It does NOT re-evaluate the accumulator —
that's the accumulator's job. Re-evaluation between writes lets the
caller choose the right cadence (every contribution vs. nightly batch).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from substrate.schemas.events import ActionType, Event

from .skill_accumulator import (
    PromotionDecision,
    SkillRuleAccumulator,
)
from .skill_propagation import (
    SkillRuleDigest,
    propagate_to_shared_substrate,
)


@dataclass(frozen=True)
class WriteOutcome:
    """One row produced by ``drain_promotable_to_substrate``."""

    rule_id: str
    written: bool  # True if propagate_to_shared_substrate wrote (idempotent re-runs return False)
    distinct_user_count: int
    confidence: str
    reason: str  # "promoted_to_substrate" | "skipped_not_promotable" | "writer_error: …"


BroadcastFn = Callable[[Event], Any]
"""Sink the writer pushes typed audit events through. Sync shape; async
broadcasters wrap at the call site (mirrors the
``substrate/ad_inventory/event_emit.py`` and DP-shuffler-event-emit
patterns)."""


def _audit_event(decision: PromotionDecision, *, investigation_id: str) -> Event:
    """Build the typed ``skill_rule.promoted`` audit event for a
    promoted rule (master-spec §13.2 + §13.7).

    Carries the rule's content-addressed identifier, the cumulative
    DP ε across contributors, the distinct-user count that triggered
    promotion, the elevated confidence tier, and the contributing
    user IDs (preserved as a list for attribution + audit
    reconstruction). The schema-v5 bump replaced the v4 placeholder
    that reused ``cross_graph.citation.recorded``.
    """
    from substrate.schemas.events import SkillRulePromotedPayload

    payload = SkillRulePromotedPayload(
        rule_id=decision.rule_id,
        rule_text=decision.rule_text,
        rule_kind=decision.rule_kind,
        domain=decision.domain,
        distinct_user_count=decision.distinct_user_count,
        total_epsilon_consumed=decision.total_epsilon_consumed,
        confidence=decision.confidence,  # type: ignore[arg-type]
        contributing_user_ids=list(decision.contributing_user_ids),
    )
    return Event(
        event_id=f"evt-{uuid.uuid4().hex[:12]}",
        investigation_id=investigation_id,
        action_type=ActionType.SKILL_RULE_PROMOTED,
        payload=payload,
        param_version="substrate-v0",
        emitted_at=datetime.now(timezone.utc),
    )


def drain_promotable_to_substrate(
    *,
    accumulator: SkillRuleAccumulator,
    con: Any,
    investigation_id: str = "__shared_substrate__",
    broadcast: Optional[BroadcastFn] = None,
) -> list[WriteOutcome]:
    """Drain every promotable rule in the accumulator to the shared
    substrate's ``skill_rules`` table.

    Args:
      accumulator: the in-memory ``SkillRuleAccumulator`` whose
        contributions have settled. The caller is responsible for
        making sure no concurrent writes are still happening.
      con: a ``LockedConnection`` on the shared-substrate DuckDB.
        Per §13.2: the single-writer invariant means this MUST be the
        shared-substrate's locked writer, not a personal-graph one.
      investigation_id: identifier for the audit event envelope. Use
        a stable identifier per drain cycle so trajectory readers can
        correlate writes.
      broadcast: optional sink for the per-rule typed audit event. If
        omitted, the writer runs silent (useful for batch backfills).

    Returns:
      One ``WriteOutcome`` per evaluated decision. Promoted rules
      land in the substrate AND emit an audit event; non-promotable
      rules are recorded with ``written=False``.

    The function NEVER raises on broadcast failure — emission errors
    are surfaced in the ``WriteOutcome.reason`` field but do not abort
    the drain. A failed propagate_to_shared_substrate (e.g. write
    contention) DOES surface as a ``writer_error:`` outcome so the
    caller can retry.
    """
    outcomes: list[WriteOutcome] = []
    for decision in accumulator.evaluate_all():
        if not decision.promote:
            outcomes.append(WriteOutcome(
                rule_id=decision.rule_id,
                written=False,
                distinct_user_count=decision.distinct_user_count,
                confidence=decision.confidence,
                reason="skipped_not_promotable",
            ))
            continue

        digest = SkillRuleDigest(
            rule_id=decision.rule_id,
            rule_text=decision.rule_text,
            rule_kind=decision.rule_kind,
            domain=decision.domain,
            epsilon_budget_consumed=decision.total_epsilon_consumed,
            source_user_count=decision.distinct_user_count,
            confidence=decision.confidence,
        )
        try:
            propagate_to_shared_substrate(con, digest)
        except Exception as exc:
            outcomes.append(WriteOutcome(
                rule_id=decision.rule_id,
                written=False,
                distinct_user_count=decision.distinct_user_count,
                confidence=decision.confidence,
                reason=f"writer_error: {exc!r}",
            ))
            continue

        # Emit the typed audit event after the write succeeds (so a
        # subscriber that reads the event log and then reads the
        # skill_rules table sees consistent state).
        if broadcast is not None:
            try:
                broadcast(_audit_event(decision, investigation_id=investigation_id))
            except Exception:
                # Broadcast failure does not roll back the write —
                # the substrate row is the source of truth. The miss
                # surfaces in trajectory replay as a gap (acceptable).
                pass

        outcomes.append(WriteOutcome(
            rule_id=decision.rule_id,
            written=True,
            distinct_user_count=decision.distinct_user_count,
            confidence=decision.confidence,
            reason="promoted_to_substrate",
        ))

    return outcomes


__all__ = [
    "BroadcastFn",
    "WriteOutcome",
    "drain_promotable_to_substrate",
]
