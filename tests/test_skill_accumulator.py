"""Skill-rule accumulator tests (master-spec §13.2 + §13.9 Phase 2)."""

from __future__ import annotations

from substrate.multi_user.skill_accumulator import (
    MAX_CUMULATIVE_EPSILON,
    MIN_USERS_FOR_HIGH_CONFIDENCE,
    MIN_USERS_FOR_PROMOTION,
    SkillRuleAccumulator,
)
from substrate.multi_user.skill_propagation import (
    extract_discovered_rule,
)


def _digest(text: str = "rule A", eps: float = 0.5, *, confidence: str = "moderate"):
    return extract_discovered_rule(
        observation_text=text,
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=eps,
        confidence=confidence,
    )


# ── Empty state ────────────────────────────────────────────────────


def test_evaluate_missing_rule_returns_none():
    acc = SkillRuleAccumulator()
    assert acc.evaluate("does-not-exist") is None


def test_evaluate_all_empty_returns_empty():
    acc = SkillRuleAccumulator()
    assert acc.evaluate_all() == []


# ── Idempotency by content addressing ──────────────────────────────


def test_same_rule_text_from_two_users_buckets_together():
    """The rule_id is content-addressed → independent extractions
    by different users end up in the same bucket."""
    acc = SkillRuleAccumulator()
    digest_a = _digest()
    digest_b = _digest()  # same text/kind/domain → same rule_id
    assert digest_a.rule_id == digest_b.rule_id
    acc.contribute(digest=digest_a, contributor_user_id="user-A")
    acc.contribute(digest=digest_b, contributor_user_id="user-B")
    assert len(acc.distinct_contributors(digest_a.rule_id)) == 2


# ── Promotion threshold ─────────────────────────────────────────────


def test_single_user_does_not_promote():
    acc = SkillRuleAccumulator()
    d = _digest()
    acc.contribute(digest=d, contributor_user_id="user-A")
    v = acc.evaluate(d.rule_id)
    assert v is not None
    assert v.promote is False
    assert "below min_users_for_promotion" in v.reason


def test_promotion_kicks_in_at_default_threshold():
    """≥ MIN_USERS_FOR_PROMOTION distinct users → promote=True."""
    acc = SkillRuleAccumulator()
    d = _digest()
    for u in [f"user-{i}" for i in range(MIN_USERS_FOR_PROMOTION)]:
        acc.contribute(digest=_digest(), contributor_user_id=u)
    v = acc.evaluate(d.rule_id)
    assert v is not None
    assert v.promote is True
    assert v.distinct_user_count == MIN_USERS_FOR_PROMOTION


def test_confidence_elevates_with_more_contributors():
    """≥ MIN_USERS_FOR_HIGH_CONFIDENCE → confidence='high'."""
    acc = SkillRuleAccumulator()
    d = _digest(eps=0.01)
    for i in range(MIN_USERS_FOR_HIGH_CONFIDENCE):
        acc.contribute(digest=_digest(eps=0.01), contributor_user_id=f"user-{i}")
    v = acc.evaluate(d.rule_id)
    assert v is not None
    assert v.promote is True
    assert v.confidence == "high"


# ── §16.2 ε cap ────────────────────────────────────────────────────


def test_promotion_blocked_when_cumulative_epsilon_exceeds_cap():
    """Per §16.2: rules whose cumulative ε exceeds the hard cap are
    refused promotion regardless of contributor count."""
    acc = SkillRuleAccumulator()
    big_eps = MAX_CUMULATIVE_EPSILON / 2  # two contributors → exceeds cap
    d = _digest(eps=big_eps)
    acc.contribute(digest=d, contributor_user_id="user-A")
    acc.contribute(digest=d, contributor_user_id="user-B")
    acc.contribute(digest=d, contributor_user_id="user-C")
    v = acc.evaluate(d.rule_id)
    assert v is not None
    assert v.promote is False
    assert "exceeds §16.2 cap" in v.reason


def test_promotion_allowed_when_cumulative_epsilon_below_cap():
    """Under-cap with enough contributors → promote=True."""
    acc = SkillRuleAccumulator()
    d = _digest(eps=0.001)  # tiny ε; cumulative stays far under 10
    for u in [f"user-{i}" for i in range(MIN_USERS_FOR_PROMOTION)]:
        acc.contribute(digest=_digest(eps=0.001), contributor_user_id=u)
    v = acc.evaluate(d.rule_id)
    assert v is not None and v.promote is True


# ── Output shape ────────────────────────────────────────────────────


def test_promotable_digests_carries_aggregate_state():
    """The reconstructed SkillRuleDigest carries cumulative ε +
    distinct-user count + elevated confidence."""
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_HIGH_CONFIDENCE):
        acc.contribute(
            digest=_digest(eps=0.01),
            contributor_user_id=f"user-{i}",
        )
    promotable = acc.promotable_digests()
    assert len(promotable) == 1
    p = promotable[0]
    assert p.source_user_count == MIN_USERS_FOR_HIGH_CONFIDENCE
    assert p.confidence == "high"
    assert p.epsilon_budget_consumed > 0


def test_distinct_user_contribution_is_deduped():
    """Same user contributing twice still counts as one distinct
    contributor (ε accumulates regardless)."""
    acc = SkillRuleAccumulator()
    d = _digest(eps=0.01)
    acc.contribute(digest=d, contributor_user_id="user-A")
    acc.contribute(digest=d, contributor_user_id="user-A")
    assert len(acc.distinct_contributors(d.rule_id)) == 1
    assert acc.cumulative_epsilon(d.rule_id) == 0.02
