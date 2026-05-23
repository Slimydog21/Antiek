"""Writer queue with DP shuffler in front."""

from __future__ import annotations

import enum
import hashlib
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


# A SHA-256 hex digest is 64 lowercase hex chars. This pattern is what
# the structural invariant test reads to verify no raw chunk content
# leaks through the evidence field.
_HASH_PATTERN = re.compile(r"^[a-f0-9]{64}$")


@dataclass(frozen=True)
class DiscoveredRule:
    """The shape of one cross-graph-propagable artefact.

    The substrate refuses to propagate a rule whose `evidence`
    contains any non-hash value. This is the architectural mechanism
    that makes §13.3 "we are architecturally incapable of leaking"
    load-bearing for skill-patch propagation: rule construction
    hashes the evidence; the original content never enters the
    DiscoveredRule.
    """

    rule_id: str
    proposer_user_id: str
    rule_kind: str  # e.g., "source_tier_assignment" | "skill_patch" | "voice_pattern"
    rule_payload: str  # the discovered statement (e.g., "Lukin papers = Tier-1 for neutral atom physics")
    evidence: tuple[str, ...]  # sha256 hex hashes of supporting chunks; no raw content
    strength_score: float  # in [0, 1]; will be DP-shuffled before aggregation
    proposed_at: str = field(default_factory=_now_iso)


def propose_rule(
    *,
    proposer_user_id: str,
    rule_kind: str,
    rule_payload: str,
    supporting_chunks: list[bytes],
    strength_score: float,
) -> DiscoveredRule:
    """Construct a DiscoveredRule from a private-graph derivation.

    `supporting_chunks` is a list of raw chunk content (bytes). This
    function HASHES each chunk and stores only the hash in the rule's
    evidence tuple. The raw content never leaves this function.
    """
    evidence_hashes = tuple(
        hashlib.sha256(chunk).hexdigest()
        for chunk in supporting_chunks
    )
    return DiscoveredRule(
        rule_id=f"rule-{uuid.uuid4().hex[:12]}",
        proposer_user_id=proposer_user_id,
        rule_kind=rule_kind,
        rule_payload=rule_payload,
        evidence=evidence_hashes,
        strength_score=max(0.0, min(1.0, strength_score)),
    )


def _validate_evidence_only_hashes(rule: DiscoveredRule) -> None:
    """Structural invariant — refuse to propagate any rule whose
    evidence section contains non-hash values."""
    for entry in rule.evidence:
        if not _HASH_PATTERN.match(entry):
            raise ValueError(
                f"rule {rule.rule_id!r} evidence contains non-hash entry "
                f"{entry!r}; refusing to propagate. "
                f"Use propose_rule() to construct rules correctly."
            )


class RulePropagationEventKind(str, enum.Enum):
    ENQUEUED = "enqueued"
    DP_SHUFFLED = "dp_shuffled"
    PROPAGATED_TO_SHARED = "propagated_to_shared"
    REFUSED_NON_HASH_EVIDENCE = "refused_non_hash_evidence"
    WRITER_FAILED = "writer_failed"


@dataclass(frozen=True)
class RulePropagationEvent:
    event_id: str = field(default_factory=lambda: f"rpe-{uuid.uuid4().hex[:12]}")
    kind: RulePropagationEventKind = RulePropagationEventKind.ENQUEUED
    rule_id: str = ""
    proposer_user_id: str = ""
    detail: str = ""
    at: str = field(default_factory=_now_iso)


@dataclass
class CrossGraphWriterQueue:
    """In-memory queue. Production wires a durable queue (Redis /
    Postgres LISTEN/NOTIFY); the contract this class exposes stays
    the same."""

    pending: list[DiscoveredRule] = field(default_factory=list)
    events: list[RulePropagationEvent] = field(default_factory=list)


SharedSubstrateWriter = Callable[[DiscoveredRule], None]


def enqueue_for_propagation(
    queue: CrossGraphWriterQueue,
    rule: DiscoveredRule,
) -> RulePropagationEvent:
    """Validate the rule + enqueue it. Refuses non-hash evidence."""
    try:
        _validate_evidence_only_hashes(rule)
    except ValueError as e:
        event = RulePropagationEvent(
            kind=RulePropagationEventKind.REFUSED_NON_HASH_EVIDENCE,
            rule_id=rule.rule_id,
            proposer_user_id=rule.proposer_user_id,
            detail=str(e),
        )
        queue.events.append(event)
        return event

    queue.pending.append(rule)
    event = RulePropagationEvent(
        kind=RulePropagationEventKind.ENQUEUED,
        rule_id=rule.rule_id,
        proposer_user_id=rule.proposer_user_id,
        detail=f"queued; strength={rule.strength_score:.2f}",
    )
    queue.events.append(event)
    return event


def _dp_shuffle_strength(
    rule: DiscoveredRule,
    *,
    epsilon: float,
) -> DiscoveredRule:
    """Apply local randomised response to the strength score.

    Substrate-only: uses the existing DP shuffler primitive
    (substrate.dp_shuffler.randomized_response style). At ε = 1.0
    the noise is well-calibrated for medium-sensitivity signals
    per §13.3.
    """
    from substrate.dp_shuffler.shuffler import LocalRandomizer

    # Treat the strength score as a Bernoulli observation (above /
    # below 0.5). The randomised response noises it; aggregation
    # across many proposers recovers the population mean.
    randomizer = LocalRandomizer(epsilon=epsilon)
    true_bit = rule.strength_score >= 0.5
    noised = randomizer.randomize(true_bit)
    shuffled_strength = 1.0 if noised else 0.0
    return DiscoveredRule(
        rule_id=rule.rule_id,
        proposer_user_id=rule.proposer_user_id,
        rule_kind=rule.rule_kind,
        rule_payload=rule.rule_payload,
        evidence=rule.evidence,
        strength_score=shuffled_strength,
    )


def drain_queue(
    queue: CrossGraphWriterQueue,
    *,
    writer: SharedSubstrateWriter,
    epsilon: float = 1.0,
) -> list[RulePropagationEvent]:
    """Drain the queue: DP-shuffle each rule's strength + write to
    shared substrate via the caller-injected writer.

    Errors in the writer are caught per-rule so one bad write does
    not block the rest of the queue.
    """
    drained: list[RulePropagationEvent] = []
    while queue.pending:
        rule = queue.pending.pop(0)
        shuffled = _dp_shuffle_strength(rule, epsilon=epsilon)
        shuffle_event = RulePropagationEvent(
            kind=RulePropagationEventKind.DP_SHUFFLED,
            rule_id=rule.rule_id,
            proposer_user_id=rule.proposer_user_id,
            detail=f"epsilon={epsilon}",
        )
        queue.events.append(shuffle_event)
        drained.append(shuffle_event)

        try:
            writer(shuffled)
            done_event = RulePropagationEvent(
                kind=RulePropagationEventKind.PROPAGATED_TO_SHARED,
                rule_id=rule.rule_id,
                proposer_user_id=rule.proposer_user_id,
            )
            queue.events.append(done_event)
            drained.append(done_event)
        except Exception as e:
            fail_event = RulePropagationEvent(
                kind=RulePropagationEventKind.WRITER_FAILED,
                rule_id=rule.rule_id,
                proposer_user_id=rule.proposer_user_id,
                detail=str(e),
            )
            queue.events.append(fail_event)
            drained.append(fail_event)

    return drained
