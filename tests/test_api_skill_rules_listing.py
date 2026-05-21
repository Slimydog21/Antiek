"""Skill rules listing endpoint tests."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="antiek-skill-rules-")
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


def _seed_skill_rule(
    db_path: str,
    *,
    rule_id: str,
    domain: str,
    confidence: str = "moderate",
) -> None:
    """Drive the writer end-to-end via the substrate to seed a rule."""
    from runtime.db_lock import connect_write
    from substrate.multi_user.skill_accumulator import (
        MIN_USERS_FOR_PROMOTION,
        SkillRuleAccumulator,
    )
    from substrate.multi_user.skill_propagation import (
        SkillRuleDigest,
        propagate_to_shared_substrate,
    )

    # The writer's content-addressed digest derives rule_id from text/
    # kind/domain; we override here by writing the digest directly
    # so the test can assert against a known rule_id.
    digest = SkillRuleDigest(
        rule_id=rule_id,
        rule_text=f"rule text for {rule_id}",
        rule_kind="source_tier_rule",
        domain=domain,
        epsilon_budget_consumed=0.01,
        source_user_count=MIN_USERS_FOR_PROMOTION,
        confidence=confidence,
    )
    with connect_write(db_path, purpose="test:seed_skill_rule") as con:
        propagate_to_shared_substrate(con, digest)


# ── Empty state ────────────────────────────────────────────────────


def test_list_skill_rules_empty(isolated_db):
    client = _client()
    resp = client.get("/skill-rules")
    assert resp.status_code == 200
    assert resp.json() == {"rules": []}


# ── Listing post-seed ──────────────────────────────────────────────


def test_list_skill_rules_returns_seeded(isolated_db):
    _seed_skill_rule(
        isolated_db, rule_id="skill-test-1", domain="quantum",
    )
    client = _client()
    resp = client.get("/skill-rules")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_id"] == "skill-test-1"
    assert body["rules"][0]["domain"] == "quantum"


# ── Filter by domain ───────────────────────────────────────────────


def test_list_skill_rules_filters_by_domain(isolated_db):
    _seed_skill_rule(isolated_db, rule_id="r-q", domain="quantum")
    _seed_skill_rule(isolated_db, rule_id="r-d", domain="defense")
    client = _client()
    resp = client.get("/skill-rules?domain=defense")
    body = resp.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_id"] == "r-d"


# ── Filter by confidence ───────────────────────────────────────────


def test_list_skill_rules_filters_by_confidence(isolated_db):
    _seed_skill_rule(
        isolated_db, rule_id="r-high", domain="x", confidence="high",
    )
    _seed_skill_rule(
        isolated_db, rule_id="r-mod", domain="x", confidence="moderate",
    )
    client = _client()
    resp = client.get("/skill-rules?confidence=high")
    body = resp.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_id"] == "r-high"


# ── Limit ───────────────────────────────────────────────────────────


def test_list_skill_rules_respects_limit(isolated_db):
    for i in range(5):
        _seed_skill_rule(
            isolated_db, rule_id=f"r-{i}", domain="x",
        )
    client = _client()
    resp = client.get("/skill-rules?limit=2")
    body = resp.json()
    assert len(body["rules"]) == 2


# ── Substring search on rule_text ───────────────────────────────────


def test_list_skill_rules_substring_search_matches(isolated_db):
    """The ?q= filter does a case-insensitive substring match on
    rule_text. The seed helper generates 'rule text for <rule_id>'
    so we can search by rule_id substring."""
    _seed_skill_rule(isolated_db, rule_id="skill-quantum-a", domain="x")
    _seed_skill_rule(isolated_db, rule_id="skill-defense-b", domain="x")
    client = _client()
    resp = client.get("/skill-rules?q=QUANTUM")  # case-insensitive
    body = resp.json()
    assert len(body["rules"]) == 1
    assert body["rules"][0]["rule_id"] == "skill-quantum-a"


def test_list_skill_rules_search_empty_returns_all(isolated_db):
    """Empty / whitespace-only q is ignored — full list returned."""
    _seed_skill_rule(isolated_db, rule_id="r-1", domain="x")
    _seed_skill_rule(isolated_db, rule_id="r-2", domain="x")
    client = _client()
    resp = client.get("/skill-rules?q=%20%20")  # %20 = space
    body = resp.json()
    assert len(body["rules"]) == 2


def test_list_skill_rules_search_combines_with_other_filters(isolated_db):
    """q + domain filter compose (AND semantics)."""
    _seed_skill_rule(isolated_db, rule_id="skill-q-a", domain="quantum")
    _seed_skill_rule(isolated_db, rule_id="skill-q-b", domain="defense")
    _seed_skill_rule(isolated_db, rule_id="skill-other-c", domain="quantum")
    client = _client()
    resp = client.get("/skill-rules?q=skill-q&domain=quantum")
    body = resp.json()
    rule_ids = {r["rule_id"] for r in body["rules"]}
    # 'skill-q' substring matches both skill-q-a and skill-q-b; domain
    # filter cuts to quantum → only skill-q-a.
    assert rule_ids == {"skill-q-a"}
