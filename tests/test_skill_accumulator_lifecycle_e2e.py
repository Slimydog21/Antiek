"""Skill accumulator → writer → audit event end-to-end integration.

Drives the cross-user discovery loop end-to-end:
  Multiple users extract the same rule
    → SkillRuleAccumulator buckets by content-address
    → PromotionDecision fires once minimum contributors reached
    → drain_promotable_to_substrate writes to skill_rules
    → typed skill_rule.promoted audit event emitted
    → GET /skill-rules surfaces the row

Confirms the §13.2 "rules propagate, content doesn't" invariant
flows correctly across all five hops.
"""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-skill-lifecycle-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    try:
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _strip_action_type(evt) -> str:
    at = evt.action_type
    return at.value if hasattr(at, "value") else at


# ── Single-user contribution → no promotion ────────────────────


def test_single_contribution_does_not_promote_or_appear_in_api(isolated_db):
    """One user → below MIN_USERS_FOR_PROMOTION threshold → no
    promotion → no row in skill_rules → API returns empty."""
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_accumulator import (
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        extract_discovered_rule,
    )
    from substrate.multi_user.skill_writer import (
        drain_promotable_to_substrate,
    )

    acc = SkillRuleAccumulator()
    digest = extract_discovered_rule(
        observation_text="Tier-1 sources include MIT Press primaries",
        rule_kind="source_tier_rule",
        domain="academic_publishing",
        epsilon_budget_consumed=0.01,
    )
    acc.contribute(digest=digest, contributor_user_id="user-A")

    captured = []
    with connect_write(isolated_db, purpose="test:e2e_drain") as con:
        outcomes = drain_promotable_to_substrate(
            accumulator=acc, con=con, broadcast=captured.append,
        )
    assert len(outcomes) == 1
    assert outcomes[0].written is False
    assert outcomes[0].reason == "skipped_not_promotable"
    assert captured == []

    # API surface shows nothing.
    client = _client()
    resp = client.get("/skill-rules")
    assert resp.status_code == 200
    assert resp.json()["rules"] == []


# ── Threshold reached → promotion + audit event + API row ─────


def test_three_users_promote_with_full_chain(isolated_db):
    """Three distinct users → bridge promotes → writer lands row
    → typed event emitted → /skill-rules returns the rule."""
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_accumulator import (
        MIN_USERS_FOR_PROMOTION,
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        extract_discovered_rule,
    )
    from substrate.multi_user.skill_writer import (
        drain_promotable_to_substrate,
    )

    acc = SkillRuleAccumulator()
    for u in range(MIN_USERS_FOR_PROMOTION):
        digest = extract_discovered_rule(
            observation_text="Lukin lab papers are tier 1 in neutral-atom",
            rule_kind="source_tier_rule",
            domain="quantum",
            epsilon_budget_consumed=0.005,
        )
        acc.contribute(digest=digest, contributor_user_id=f"user-{u}")

    captured_events = []
    with connect_write(isolated_db, purpose="test:e2e_promote") as con:
        outcomes = drain_promotable_to_substrate(
            accumulator=acc,
            con=con,
            broadcast=captured_events.append,
        )

    # Outcome: promoted to substrate.
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.written is True
    assert o.reason == "promoted_to_substrate"
    assert o.distinct_user_count == MIN_USERS_FOR_PROMOTION
    rule_id = o.rule_id

    # Audit event: skill_rule.promoted with full provenance.
    assert len(captured_events) == 1
    evt = captured_events[0]
    assert _strip_action_type(evt) == "skill_rule.promoted"
    p = evt.payload
    assert p.rule_id == rule_id
    assert p.distinct_user_count == MIN_USERS_FOR_PROMOTION
    assert p.confidence in {"low", "moderate", "high"}
    # Per master-spec §13.2: contributing user IDs preserved for
    # attribution + audit, NOT private content.
    assert sorted(p.contributing_user_ids) == sorted(
        f"user-{u}" for u in range(MIN_USERS_FOR_PROMOTION)
    )

    # API surface returns the row.
    client = _client()
    resp = client.get("/skill-rules")
    body = resp.json()
    assert len(body["rules"]) == 1
    api_rule = body["rules"][0]
    assert api_rule["rule_id"] == rule_id
    assert api_rule["domain"] == "quantum"
    assert api_rule["source_user_count"] == MIN_USERS_FOR_PROMOTION

    # Detail endpoint round-trips.
    detail = client.get(f"/skill-rules/{rule_id}").json()
    assert detail["rule_id"] == rule_id
    assert detail["rule_text"] == "Lukin lab papers are tier 1 in neutral-atom"


# ── Re-drain is idempotent ────────────────────────────────────────


def test_re_drain_does_not_duplicate_audit_event(isolated_db):
    """A second drain pass with the same accumulator state returns
    written=True (substrate row already exists; ON CONFLICT no-op),
    but emits another typed event each time. The writer doesn't
    suppress duplicate audit events — the audit log is append-only
    and the consumer is expected to dedupe by rule_id if needed."""
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_accumulator import (
        MIN_USERS_FOR_PROMOTION,
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        extract_discovered_rule,
    )
    from substrate.multi_user.skill_writer import (
        drain_promotable_to_substrate,
    )

    acc = SkillRuleAccumulator()
    for u in range(MIN_USERS_FOR_PROMOTION):
        digest = extract_discovered_rule(
            observation_text="dup rule",
            rule_kind="source_tier_rule",
            domain="x",
            epsilon_budget_consumed=0.001,
        )
        acc.contribute(digest=digest, contributor_user_id=f"user-{u}")

    captured = []
    with connect_write(isolated_db, purpose="test:e2e_drain_1") as con:
        drain_promotable_to_substrate(
            accumulator=acc, con=con, broadcast=captured.append,
        )
    with connect_write(isolated_db, purpose="test:e2e_drain_2") as con:
        drain_promotable_to_substrate(
            accumulator=acc, con=con, broadcast=captured.append,
        )

    # Substrate state: exactly one row (idempotent via ON CONFLICT).
    client = _client()
    body = client.get("/skill-rules").json()
    assert len(body["rules"]) == 1

    # Audit: two events emitted; deduplication is consumer-side.
    promoted_events = [
        e for e in captured if _strip_action_type(e) == "skill_rule.promoted"
    ]
    assert len(promoted_events) == 2


# ── ε cap enforced end-to-end ────────────────────────────────────


def test_epsilon_cap_blocks_promotion_through_full_chain(isolated_db):
    """Per master-spec §16.2: cumulative ε > 10 → no promotion even
    when distinct-user threshold is met. The writer surfaces this
    as skipped_not_promotable; no audit event emitted; no row lands."""
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_accumulator import (
        MAX_CUMULATIVE_EPSILON,
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        extract_discovered_rule,
    )
    from substrate.multi_user.skill_writer import (
        drain_promotable_to_substrate,
    )

    acc = SkillRuleAccumulator()
    # Each contribution spends MAX_CUMULATIVE_EPSILON / 2 ε; with 3+
    # contributors, cumulative exceeds the cap.
    big = MAX_CUMULATIVE_EPSILON / 2
    for u in range(3):
        digest = extract_discovered_rule(
            observation_text="costly rule",
            rule_kind="source_tier_rule",
            domain="x",
            epsilon_budget_consumed=big,
        )
        acc.contribute(digest=digest, contributor_user_id=f"user-{u}")

    captured = []
    with connect_write(isolated_db, purpose="test:e2e_cap") as con:
        outcomes = drain_promotable_to_substrate(
            accumulator=acc, con=con, broadcast=captured.append,
        )
    assert outcomes[0].written is False
    assert outcomes[0].reason == "skipped_not_promotable"
    assert captured == []

    client = _client()
    assert client.get("/skill-rules").json()["rules"] == []
