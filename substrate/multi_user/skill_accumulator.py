"""Skill-rule accumulator for the shared substrate (master-spec §13.2
+ §13.9 Phase 2).

Bridges the per-user ``SkillRuleDigest`` extraction layer
(``substrate/multi_user/skill_propagation.py``) and the cross-graph
shared substrate. The accumulator is the gate that decides:

  - When is a discovered rule confirmed across enough independent
    users that we should promote it to the public skill registry?
  - How much cumulative DP ε has been spent on this rule across all
    contributors, and is it still under the §16.2 hard cap?
  - When does confidence elevate from 'moderate' (single-user) to
    'high' (≥ MIN_USERS_FOR_HIGH_CONFIDENCE distinct contributors)?

Design constraints per master-spec:

  - §13.2: skill patches derived in private partitions propagate as
    DISCOVERED RULES (not as patched private content). The
    accumulator only stores the rule_text + provenance metadata, never
    user-specific content.
  - §13.3 DP guarantees: cumulative ε is tracked per rule; the
    accumulator refuses to promote a rule whose cumulative ε exceeds
    the configurable cap (defaults to the §16.2 hard 10.0).
  - §13.9 Phase 2 attribution: when a rule promotes, the contributing
    user IDs are retained so any ad-revenue routed to 'rule-derived'
    content can attribute back via the existing rev-share path.

The accumulator does NOT write to the shared substrate itself; it
emits ``PromotionDecision`` records that the caller's writer (running
under the shared-substrate ``LockedConnection``) consumes. This keeps
the single-writer invariant clean.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from .skill_propagation import SkillRuleDigest


MIN_USERS_FOR_PROMOTION: int = 3
"""Number of distinct contributors required before a rule may be
promoted to the shared substrate. The conservative default reflects
master-spec §13.9 Phase 2: 'a rule promotes only after independent
corroboration; single-source rules stay in the private partition.'"""

MIN_USERS_FOR_HIGH_CONFIDENCE: int = 5
"""Promoting at ≥5 distinct users elevates confidence from 'moderate'
to 'high'. The threshold is tunable per the operator's published
trust-center stance; do not lower without revisiting §13.9."""

MAX_CUMULATIVE_EPSILON: float = 10.0
"""§16.2 hard cap on cumulative DP ε per rule. Accumulated across
contributors; the accumulator refuses to promote rules whose total
ε spend exceeds this value."""


class SkillAccumulatorError(Exception):
    """Raised on policy violations the accumulator must surface."""


@dataclass(frozen=True)
class ContributedDigest:
    """One contribution to the accumulator's per-rule bucket."""

    digest: SkillRuleDigest
    contributor_user_id: str


@dataclass(frozen=True)
class PromotionDecision:
    """Verdict produced by the accumulator for one rule_id."""

    rule_id: str
    rule_text: str
    rule_kind: str
    domain: str
    distinct_user_count: int
    total_epsilon_consumed: float
    promote: bool
    confidence: str  # "low" | "moderate" | "high"
    reason: str
    contributing_user_ids: tuple[str, ...]


@dataclass
class SkillRuleAccumulator:
    """In-memory accumulator for cross-user skill-rule contributions.

    The accumulator is intentionally append-only and idempotent: the
    same ``(rule_id, contributor_user_id)`` pair contributes once.
    Multiple observations from the same user against the same rule
    do not multiply that user's vote (they DO add to cumulative
    epsilon since each observation spent its own DP budget).
    """

    min_users_for_promotion: int = MIN_USERS_FOR_PROMOTION
    min_users_for_high_confidence: int = MIN_USERS_FOR_HIGH_CONFIDENCE
    max_cumulative_epsilon: float = MAX_CUMULATIVE_EPSILON
    _digests_by_rule: dict[str, list[ContributedDigest]] = field(
        default_factory=dict,
    )
    _epsilon_by_rule: dict[str, float] = field(default_factory=dict)

    # ── Contribution ────────────────────────────────────────────────

    def contribute(self, *, digest: SkillRuleDigest, contributor_user_id: str) -> None:
        """Record one user's contribution to a rule's bucket. The
        rule_id is content-addressed by
        ``extract_discovered_rule`` so independent users producing
        the same rule end up in the same bucket without coordination.

        Cumulative ε is added per contribution (even if the same user
        contributes twice — each observation cost budget independently).
        """
        bucket = self._digests_by_rule.setdefault(digest.rule_id, [])
        bucket.append(ContributedDigest(
            digest=digest, contributor_user_id=contributor_user_id,
        ))
        self._epsilon_by_rule[digest.rule_id] = (
            self._epsilon_by_rule.get(digest.rule_id, 0.0)
            + digest.epsilon_budget_consumed
        )

    def contribute_many(
        self,
        contributions: Iterable[tuple[SkillRuleDigest, str]],
    ) -> None:
        for digest, user_id in contributions:
            self.contribute(digest=digest, contributor_user_id=user_id)

    # ── Inspection ──────────────────────────────────────────────────

    def distinct_contributors(self, rule_id: str) -> set[str]:
        bucket = self._digests_by_rule.get(rule_id, [])
        return {c.contributor_user_id for c in bucket}

    def cumulative_epsilon(self, rule_id: str) -> float:
        return self._epsilon_by_rule.get(rule_id, 0.0)

    def buckets(self) -> dict[str, list[ContributedDigest]]:
        """Snapshot view (callers should not mutate)."""
        return dict(self._digests_by_rule)

    # ── Promotion verdicts ──────────────────────────────────────────

    def evaluate(self, rule_id: str) -> Optional[PromotionDecision]:
        """Return a ``PromotionDecision`` for one rule, or None if the
        rule has zero contributions.

        The verdict reflects the current accumulator state; callers
        re-evaluate after each new contribution. ``promote=True`` is a
        green light to call ``propagate_to_shared_substrate`` on the
        canonical digest (rebuilt below from the bucket).
        """
        bucket = self._digests_by_rule.get(rule_id, [])
        if not bucket:
            return None
        first = bucket[0].digest
        distinct_users = self.distinct_contributors(rule_id)
        cumulative_eps = self.cumulative_epsilon(rule_id)
        n_distinct = len(distinct_users)

        if cumulative_eps > self.max_cumulative_epsilon:
            return PromotionDecision(
                rule_id=rule_id,
                rule_text=first.rule_text,
                rule_kind=first.rule_kind,
                domain=first.domain,
                distinct_user_count=n_distinct,
                total_epsilon_consumed=cumulative_eps,
                promote=False,
                confidence="low",
                reason=(
                    f"cumulative_epsilon={cumulative_eps:.4f} exceeds "
                    f"§16.2 cap={self.max_cumulative_epsilon}"
                ),
                contributing_user_ids=tuple(sorted(distinct_users)),
            )

        if n_distinct < self.min_users_for_promotion:
            return PromotionDecision(
                rule_id=rule_id,
                rule_text=first.rule_text,
                rule_kind=first.rule_kind,
                domain=first.domain,
                distinct_user_count=n_distinct,
                total_epsilon_consumed=cumulative_eps,
                promote=False,
                confidence="moderate" if n_distinct >= 1 else "low",
                reason=(
                    f"distinct_users={n_distinct} below "
                    f"min_users_for_promotion={self.min_users_for_promotion}"
                ),
                contributing_user_ids=tuple(sorted(distinct_users)),
            )

        confidence = (
            "high"
            if n_distinct >= self.min_users_for_high_confidence
            else "moderate"
        )
        return PromotionDecision(
            rule_id=rule_id,
            rule_text=first.rule_text,
            rule_kind=first.rule_kind,
            domain=first.domain,
            distinct_user_count=n_distinct,
            total_epsilon_consumed=cumulative_eps,
            promote=True,
            confidence=confidence,
            reason=(
                f"distinct_users={n_distinct} ≥ "
                f"min_users_for_promotion={self.min_users_for_promotion} "
                f"and cumulative_epsilon={cumulative_eps:.4f} ≤ "
                f"cap={self.max_cumulative_epsilon}"
            ),
            contributing_user_ids=tuple(sorted(distinct_users)),
        )

    def evaluate_all(self) -> list[PromotionDecision]:
        """Evaluate every bucket. Useful for periodic batch promotion
        runs (e.g., a nightly job that scans for newly-promotable
        rules)."""
        verdicts: list[PromotionDecision] = []
        for rule_id in self._digests_by_rule.keys():
            v = self.evaluate(rule_id)
            if v is not None:
                verdicts.append(v)
        return verdicts

    def promotable_digests(self) -> list[SkillRuleDigest]:
        """Return canonical digests (one per rule) ready for
        propagation to the shared substrate. Reconstructs each digest
        with cumulative ε + distinct-user count + elevated confidence
        per the verdict."""
        out: list[SkillRuleDigest] = []
        for v in self.evaluate_all():
            if not v.promote:
                continue
            out.append(SkillRuleDigest(
                rule_id=v.rule_id,
                rule_text=v.rule_text,
                rule_kind=v.rule_kind,
                domain=v.domain,
                epsilon_budget_consumed=v.total_epsilon_consumed,
                source_user_count=v.distinct_user_count,
                confidence=v.confidence,
            ))
        return out
