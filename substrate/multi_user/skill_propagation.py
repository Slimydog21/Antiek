"""Cross-graph skill-rule propagation (master-spec §13.2).

The key architectural commitment: skill patches derived in a user's
private-facing partition propagate to ALL users as DISCOVERED RULES,
not as the patched private content.

Example from master-spec §13.2 verbatim:
  A skill patch derived in the operator's private graph (e.g.,
  'Tier-1 sources in neutral atom physics include Lukin lab papers
  but not Vuletic preprints') propagates to all users via the
  shared-substrate writer queue — not as the patched private content,
  but as the discovered rule.

This module is the extraction layer that turns a private observation
into a shareable rule digest, with differential-privacy guarantees
per §13.3 + the §16.2 ε ≤ 10 cap.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class SkillRuleDigest:
    """A discovered rule extracted from one or more users' private
    observations, suitable for propagation to the shared substrate.

    The digest carries:
    - rule_id: stable identifier (idempotency)
    - rule_text: the rule itself (e.g., 'Lukin papers in neutral
      atom physics are Tier 1')
    - rule_kind: 'source_tier_rule' | 'rubric_threshold' |
      'extraction_pattern' | 'verification_pattern'
    - domain: 'quantum' | 'defense' | etc — the topic the rule applies to
    - epsilon_budget_consumed: how much of the user's DP budget was
      spent extracting the rule
    - source_user_count: how many distinct users contributed
      observations (≥1; aggregation across users is allowed only with
      DP shuffling per §13.3)

    The digest does NOT carry any private content — only the
    discovered rule's text + provenance metadata."""

    rule_id: str
    rule_text: str
    rule_kind: str
    domain: str
    epsilon_budget_consumed: float
    source_user_count: int
    extracted_at: str = field(default_factory=_now_iso)
    confidence: str = "moderate"


def extract_discovered_rule(
    *,
    observation_text: str,
    rule_kind: str,
    domain: str,
    epsilon_budget_consumed: float,
    confidence: str = "moderate",
    source_user_count: int = 1,
) -> SkillRuleDigest:
    """Turn a private observation into a shareable rule digest.

    Per master-spec §13.3 DP guarantees + §16.2 ε ≤ 10 cap. The
    epsilon_budget_consumed is the caller's responsibility — the
    extraction itself does not consume budget; what consumes budget
    is whatever DP-aggregation produced the observation_text.

    The rule_id is content-addressed (SHA-256 prefix of
    rule_text + domain + rule_kind) so re-extracting the same rule
    is idempotent."""
    canonical = json.dumps({
        "rule_text": observation_text,
        "rule_kind": rule_kind,
        "domain": domain,
    }, sort_keys=True, separators=(",", ":"))
    rule_id = "skill-" + hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:24]
    return SkillRuleDigest(
        rule_id=rule_id,
        rule_text=observation_text,
        rule_kind=rule_kind,
        domain=domain,
        epsilon_budget_consumed=epsilon_budget_consumed,
        source_user_count=source_user_count,
        confidence=confidence,
    )


def propagate_to_shared_substrate(
    con: Any,
    digest: SkillRuleDigest,
) -> str:
    """Write a discovered rule into the shared substrate skill registry.

    Caller passes a LockedConnection on the shared_substrate DuckDB
    (NOT on a user's personal-graph file — that would violate the
    single-writer-on-substrate invariant per §13.2). Returns the
    rule_id; idempotent (re-propagation of the same content is a
    no-op).

    The shared-substrate schema's `skill_rules` table is created
    by Sprint 22+ shared-substrate init code — not yet in
    substrate/graph/schema.py. This function uses CREATE TABLE IF
    NOT EXISTS so it's safe to call against a fresh shared_substrate
    DuckDB.
    """
    con.execute("""
        CREATE TABLE IF NOT EXISTS skill_rules (
            rule_id                  TEXT PRIMARY KEY,
            rule_text                TEXT NOT NULL,
            rule_kind                TEXT NOT NULL,
            domain                   TEXT NOT NULL,
            epsilon_budget_consumed  FLOAT NOT NULL,
            source_user_count        INTEGER NOT NULL,
            confidence               TEXT NOT NULL,
            extracted_at             TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
    """)
    con.execute("""
        INSERT INTO skill_rules (
            rule_id, rule_text, rule_kind, domain,
            epsilon_budget_consumed, source_user_count, confidence,
            extracted_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (rule_id) DO NOTHING
    """, [
        digest.rule_id, digest.rule_text, digest.rule_kind, digest.domain,
        digest.epsilon_budget_consumed, digest.source_user_count,
        digest.confidence, digest.extracted_at,
    ])
    return digest.rule_id
