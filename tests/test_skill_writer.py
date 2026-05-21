"""Skill registry writer tests — drain ``SkillRuleAccumulator`` →
shared-substrate ``skill_rules`` table + typed audit events."""

from __future__ import annotations

import os
import shutil
import tempfile

import pytest

from substrate.multi_user.skill_accumulator import (
    MIN_USERS_FOR_PROMOTION,
    SkillRuleAccumulator,
)
from substrate.multi_user.skill_propagation import extract_discovered_rule
from substrate.multi_user.skill_writer import (
    drain_promotable_to_substrate,
)


@pytest.fixture()
def shared_con():
    """Provide a fresh DuckDB connection scoped to one test."""
    import duckdb

    tmpdir = tempfile.mkdtemp(prefix="antiek-skill-writer-")
    db_path = os.path.join(tmpdir, "shared.duckdb")
    con = duckdb.connect(db_path)
    try:
        yield con
    finally:
        con.close()
        shutil.rmtree(tmpdir, ignore_errors=True)


def _digest(text: str = "rule A", eps: float = 0.01):
    return extract_discovered_rule(
        observation_text=text,
        rule_kind="source_tier_rule",
        domain="quantum",
        epsilon_budget_consumed=eps,
    )


# ── Empty accumulator → no rows, no events ──────────────────────────


def test_empty_accumulator_writes_nothing(shared_con):
    events: list = []
    outcomes = drain_promotable_to_substrate(
        accumulator=SkillRuleAccumulator(),
        con=shared_con,
        broadcast=events.append,
    )
    assert outcomes == []
    assert events == []


# ── Non-promotable bucket skipped ──────────────────────────────────


def test_below_threshold_skipped_not_written(shared_con):
    acc = SkillRuleAccumulator()
    acc.contribute(
        digest=_digest(), contributor_user_id="user-A",
    )  # single user; below promotion threshold
    events: list = []
    outcomes = drain_promotable_to_substrate(
        accumulator=acc, con=shared_con, broadcast=events.append,
    )
    assert len(outcomes) == 1
    assert outcomes[0].written is False
    assert outcomes[0].reason == "skipped_not_promotable"
    # The skill_rules table was never created — no write happened.
    tables = [
        r[0] for r in shared_con.execute(
            "SELECT table_name FROM information_schema.tables"
        ).fetchall()
    ]
    assert "skill_rules" not in tables
    assert events == []


# ── Promotable bucket lands + emits ──────────────────────────────


def test_promotable_rule_writes_and_emits(shared_con):
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_PROMOTION):
        acc.contribute(
            digest=_digest(eps=0.001),
            contributor_user_id=f"user-{i}",
        )
    events: list = []
    outcomes = drain_promotable_to_substrate(
        accumulator=acc,
        con=shared_con,
        investigation_id="inv-test",
        broadcast=events.append,
    )
    assert len(outcomes) == 1
    o = outcomes[0]
    assert o.written is True
    assert o.reason == "promoted_to_substrate"
    assert o.distinct_user_count == MIN_USERS_FOR_PROMOTION

    rows = shared_con.execute(
        "SELECT rule_id, source_user_count FROM skill_rules"
    ).fetchall()
    assert len(rows) == 1
    assert rows[0][1] == MIN_USERS_FOR_PROMOTION

    # One audit event was emitted for the promotion.
    assert len(events) == 1
    evt = events[0]
    at = evt.action_type
    at_value = at.value if hasattr(at, "value") else at
    assert at_value == "skill_rule.promoted"
    # Payload carries full provenance.
    p = evt.payload
    assert p.distinct_user_count == MIN_USERS_FOR_PROMOTION
    assert p.rule_id == outcomes[0].rule_id
    assert p.confidence in {"low", "moderate", "high"}
    assert len(p.contributing_user_ids) == MIN_USERS_FOR_PROMOTION


def test_promotable_rule_silent_without_broadcast(shared_con):
    """No broadcaster passed → write happens but no event leaks."""
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_PROMOTION):
        acc.contribute(
            digest=_digest(eps=0.001),
            contributor_user_id=f"user-{i}",
        )
    outcomes = drain_promotable_to_substrate(
        accumulator=acc, con=shared_con,
    )
    assert len(outcomes) == 1
    assert outcomes[0].written is True
    rows = shared_con.execute(
        "SELECT rule_id FROM skill_rules"
    ).fetchall()
    assert len(rows) == 1


# ── Idempotent re-drain ─────────────────────────────────────────────


def test_re_drain_does_not_duplicate(shared_con):
    """Same rule_id → ON CONFLICT DO NOTHING in the propagate path.
    The writer reports written=True both times; the table has one row."""
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_PROMOTION):
        acc.contribute(
            digest=_digest(eps=0.001),
            contributor_user_id=f"user-{i}",
        )
    drain_promotable_to_substrate(accumulator=acc, con=shared_con)
    drain_promotable_to_substrate(accumulator=acc, con=shared_con)
    rows = shared_con.execute("SELECT rule_id FROM skill_rules").fetchall()
    assert len(rows) == 1


# ── Writer error surfaces in outcome.reason ─────────────────────────


def test_writer_error_surfaces_in_outcome(shared_con):
    """A failing propagate call surfaces as writer_error: … instead
    of raising."""
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_PROMOTION):
        acc.contribute(
            digest=_digest(eps=0.001),
            contributor_user_id=f"user-{i}",
        )

    # Wrap the connection so the INSERT raises. DuckDB's
    # PyConnection.execute is read-only, so we route through a proxy
    # rather than monkey-patching the attribute.
    class _ProxyCon:
        def __init__(self, inner) -> None:
            self._inner = inner

        def execute(self, sql, *args, **kwargs):
            if "INSERT INTO skill_rules" in sql:
                raise RuntimeError("simulated writer fault")
            return self._inner.execute(sql, *args, **kwargs)

    proxy = _ProxyCon(shared_con)
    outcomes = drain_promotable_to_substrate(
        accumulator=acc, con=proxy,
    )

    assert len(outcomes) == 1
    assert outcomes[0].written is False
    assert outcomes[0].reason.startswith("writer_error:")


# ── Broadcast failure does NOT abort the drain ──────────────────────


def test_broadcast_failure_does_not_abort_write(shared_con):
    """If the broadcaster raises, the write still landed."""
    acc = SkillRuleAccumulator()
    for i in range(MIN_USERS_FOR_PROMOTION):
        acc.contribute(
            digest=_digest(eps=0.001),
            contributor_user_id=f"user-{i}",
        )

    def boom(evt):
        raise RuntimeError("broadcaster down")

    outcomes = drain_promotable_to_substrate(
        accumulator=acc, con=shared_con, broadcast=boom,
    )
    assert len(outcomes) == 1
    assert outcomes[0].written is True
    rows = shared_con.execute(
        "SELECT rule_id FROM skill_rules"
    ).fetchall()
    assert len(rows) == 1
