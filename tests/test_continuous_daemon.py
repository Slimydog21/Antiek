"""Tests for the continuous research daemon (master-spec §7.3 + §7.4).

Coverage:
  - Gap normalization + registry deduplication
  - Recency / co-occurrence / interaction scoring
  - MAX_CHASE_COUNT decay: gap chased ≥3 times scores 0
  - Topic-depth cap: depth_remaining returns 0 at the §7.4 hard limit
  - DaemonBudget per-investigation cap + daily cap + persistence
  - End-to-end scan_gaps from a fixture event log
  - run_one_iteration: spawn loop, budget enforcement, decay, topic
    depth, no-op spawn vs. real-spawn callable
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

# Repo root on path.
_PKG_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from orchestration.continuous import (  # noqa: E402
    DaemonBudget,
    DaemonBudgetError,
    DaemonConfig,
    DaemonState,
    GapEntry,
    GapRegistry,
    ResearchTopic,
    normalize_gap_description,
    run_one_iteration,
    score_gap,
    topic_id_for,
)
from orchestration.continuous.daemon import scan_gaps  # noqa: E402
from orchestration.continuous.research_topic import MAX_TOPIC_DEPTH  # noqa: E402
from orchestration.continuous.scoring import (  # noqa: E402
    MAX_CHASE_COUNT,
    RECENCY_HALF_LIFE_DAYS,
)

# ── Fixtures ──────────────────────────────────────────────────────────


@pytest.fixture
def isolated_env(tmp_path, monkeypatch):
    events_dir = tmp_path / "events"
    events_dir.mkdir()
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events_dir))
    monkeypatch.delenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", raising=False)
    return {"events_dir": str(events_dir), "home": str(tmp_path)}


def _write_evidence_delivered(
    events_dir: str,
    *,
    investigation_id: str,
    gaps: list[tuple[str, str | None]],
    emitted_at: datetime | None = None,
) -> None:
    """Write an evidence.retrieve.delivered event to the daemon's
    expected jsonl format."""
    when = emitted_at or datetime.now(UTC)
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    payload = {
        "action_type": "evidence.retrieve.delivered",
        "sub_question": "fixture sub-question",
        "answer": "fixture answer",
        "supporting_claims": [],
        "evidentiary_gaps": [
            {"gap_description": desc, "additional_retrieval_suggested": hint}
            for desc, hint in gaps
        ],
        "insufficient_evidence": False,
    }
    row = {
        "event_id": f"evt-{investigation_id}-{len(gaps)}",
        "investigation_id": investigation_id,
        "action_type": "evidence.retrieve.delivered",
        "emitted_at": when.isoformat(),
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


def _write_question_identified(
    events_dir: str,
    *,
    investigation_id: str,
    question_text: str,
    emitted_at: datetime | None = None,
) -> None:
    when = emitted_at or datetime.now(UTC)
    path = Path(events_dir) / f"{investigation_id}.jsonl"
    payload = {
        "action_type": "question.identified",
        "question_text": question_text,
        "category": "mechanism",
        "evidence_type_required": "qualitative",
    }
    row = {
        "event_id": f"evt-{investigation_id}-qi",
        "investigation_id": investigation_id,
        "action_type": "question.identified",
        "emitted_at": when.isoformat(),
        "payload": payload,
    }
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")


# ── Scoring unit tests ────────────────────────────────────────────────


def test_normalize_gap_description_collapses_whitespace_and_case():
    a = normalize_gap_description("  Foo    BAR  ")
    b = normalize_gap_description("foo bar")
    c = normalize_gap_description("foo  Bar")
    assert a == b == c


def test_normalize_gap_description_empty_returns_sentinel():
    assert normalize_gap_description("") == "<empty>"


def test_gap_registry_deduplicates_within_one_investigation():
    reg = GapRegistry()
    now = datetime.now(UTC)
    reg.observe(
        gap_description="Need data on dispatch cost",
        additional_retrieval_suggested=None,
        investigation_id="inv-1",
        emitted_at=now,
    )
    reg.observe(
        gap_description="need data on dispatch cost",  # diff case
        additional_retrieval_suggested=None,
        investigation_id="inv-1",
        emitted_at=now,
    )
    assert len(reg) == 1
    entry = next(iter(reg.values()))
    assert entry.co_occurrence == 1  # same investigation, not double-counted


def test_gap_registry_counts_cross_investigation_co_occurrence():
    reg = GapRegistry()
    now = datetime.now(UTC)
    for iid in ("inv-1", "inv-2", "inv-3"):
        reg.observe(
            gap_description="What is the §13.9 quality gate threshold?",
            additional_retrieval_suggested=None,
            investigation_id=iid,
            emitted_at=now,
        )
    entry = next(iter(reg.values()))
    assert entry.co_occurrence == 3


def test_score_gap_recency_decays_per_half_life():
    """A gap 1 half-life old should score about half its co_occurrence
    component (interaction is 1.0 absent the boost)."""
    now = datetime.now(UTC)
    fresh = GapEntry(
        normalized_key="k1", gap_description="x",
        additional_retrieval_suggested=None,
        first_seen_at=now, last_seen_at=now,
        investigation_ids=["a", "b"],
    )
    old = GapEntry(
        normalized_key="k2", gap_description="x",
        additional_retrieval_suggested=None,
        first_seen_at=now, last_seen_at=now - timedelta(days=RECENCY_HALF_LIFE_DAYS),
        investigation_ids=["a", "b"],
    )
    s_fresh = score_gap(fresh, now=now)
    s_old = score_gap(old, now=now)
    assert s_fresh > 0
    assert 0.4 < s_old / s_fresh < 0.6


def test_score_gap_returns_zero_after_max_chase_count():
    now = datetime.now(UTC)
    entry = GapEntry(
        normalized_key="k", gap_description="x",
        additional_retrieval_suggested=None,
        first_seen_at=now, last_seen_at=now,
        investigation_ids=["a", "b"],
        chase_count=MAX_CHASE_COUNT,
    )
    assert score_gap(entry, now=now) == 0.0


def test_score_gap_interaction_boost_lifts_score():
    now = datetime.now(UTC)
    base = GapEntry(
        normalized_key="k", gap_description="x",
        additional_retrieval_suggested=None,
        first_seen_at=now, last_seen_at=now,
        investigation_ids=["a", "b"],
    )
    boosted = GapEntry(
        normalized_key="k", gap_description="x",
        additional_retrieval_suggested=None,
        first_seen_at=now, last_seen_at=now,
        investigation_ids=["a", "b"],
        interaction_count=1,
    )
    assert score_gap(boosted, now=now) > score_gap(base, now=now)


# ── ResearchTopic unit tests ──────────────────────────────────────────


def test_topic_id_for_is_deterministic():
    a = topic_id_for("How does dispatch routing work?")
    b = topic_id_for("how  DOES dispatch  routing work?")
    assert a == b
    assert a.startswith("topic-")


def test_topic_id_for_rejects_empty():
    with pytest.raises(ValueError):
        topic_id_for("")
    with pytest.raises(ValueError):
        topic_id_for("   ")


def test_research_topic_depth_cap_at_max_topic_depth():
    t = ResearchTopic(topic_id="t", root_question="q")
    for d in range(MAX_TOPIC_DEPTH):
        assert t.can_chase()
        t.record_spawn(f"inv-{d}", depth=d + 1)
    assert t.max_depth_reached == MAX_TOPIC_DEPTH
    assert t.depth_remaining == 0
    assert not t.can_chase()


# ── DaemonBudget tests ────────────────────────────────────────────────


def test_daemon_budget_per_investigation_cap_blocks_oversized_spawn(isolated_env):
    b = DaemonBudget(daily_cap_usd=100.0, per_investigation_cap_usd=2.0)
    b.reserve(1.50)  # ok
    with pytest.raises(DaemonBudgetError, match="per-investigation cap"):
        b.reserve(2.01)


def test_daemon_budget_daily_cap_blocks_when_total_exceeded(isolated_env):
    b = DaemonBudget(daily_cap_usd=5.0, per_investigation_cap_usd=2.0)
    b.reserve(2.0)
    b.reserve(2.0)
    b.reserve(0.9)  # 4.9 total
    with pytest.raises(DaemonBudgetError, match="daily cap exceeded"):
        b.reserve(0.5)  # would push to 5.4 > 5.0


def test_daemon_budget_persists_across_construction(isolated_env):
    b1 = DaemonBudget(daily_cap_usd=5.0)
    b1.reserve(1.0)
    b2 = DaemonBudget(daily_cap_usd=5.0)
    assert b2.remaining_today() == pytest.approx(4.0)


def test_daemon_budget_remaining_uses_current_cap_after_cap_change(isolated_env):
    DaemonBudget(daily_cap_usd=5.0).reserve(1.0)

    changed = DaemonBudget(daily_cap_usd=3.0)

    assert changed.remaining_today() == pytest.approx(2.0)


def test_daemon_budget_spend_is_not_truncated_when_cap_drops_below_spend(isolated_env):
    DaemonBudget(daily_cap_usd=5.0, per_investigation_cap_usd=5.0).reserve(4.0)

    changed = DaemonBudget(daily_cap_usd=3.0)

    assert changed.spent_today() == pytest.approx(4.0)
    assert changed.remaining_today() == pytest.approx(0.0)


def test_daemon_budget_record_actual_adjusts_total(isolated_env):
    b = DaemonBudget(daily_cap_usd=5.0)
    b.reserve(2.0)
    b.record_actual(-0.5)  # refund
    assert b.remaining_today() == pytest.approx(3.5)
    b.record_actual(0.3)
    assert b.remaining_today() == pytest.approx(3.2)


def test_daemon_budget_from_env_reads_default_when_unset(isolated_env):
    # ANTIEK_DAEMON_HOURLY_BUDGET_USD deleted by isolated_env fixture.
    b = DaemonBudget.from_env()
    assert b.daily_cap_usd == 5.0


def test_daemon_budget_from_env_honors_override(isolated_env, monkeypatch):
    monkeypatch.setenv("ANTIEK_DAEMON_HOURLY_BUDGET_USD", "12.5")
    b = DaemonBudget.from_env()
    assert b.daily_cap_usd == 12.5


# ── End-to-end scan + iterate tests ───────────────────────────────────


def test_scan_gaps_builds_registry_from_event_log(isolated_env):
    ed = isolated_env["events_dir"]
    _write_evidence_delivered(
        ed,
        investigation_id="inv-A",
        gaps=[("What is the dispatch verdict threshold?", "check §14.4")],
    )
    _write_evidence_delivered(
        ed,
        investigation_id="inv-B",
        gaps=[
            ("What is the dispatch verdict threshold?", None),
            ("Why is Phase 8 in shadow mode?", None),
        ],
    )
    registry = scan_gaps(events_dir=ed)
    assert len(registry) == 2
    # The "dispatch verdict threshold" gap should have co_occurrence=2.
    for entry in registry.values():
        if "dispatch verdict" in entry.gap_description.lower():
            assert entry.co_occurrence == 2
            # First-non-empty wins on retrieval suggestion.
            assert entry.additional_retrieval_suggested == "check §14.4"


def test_scan_gaps_picks_up_question_identified_interaction(isolated_env):
    ed = isolated_env["events_dir"]
    _write_evidence_delivered(
        ed,
        investigation_id="inv-X",
        gaps=[("Need data on Synquery PMF metrics", None)],
    )
    _write_question_identified(
        ed,
        investigation_id="inv-X",
        question_text="Need data on Synquery PMF metrics",
    )
    registry = scan_gaps(events_dir=ed)
    assert len(registry) == 1
    entry = next(iter(registry.values()))
    assert entry.interaction_count >= 1


def test_run_one_iteration_spawns_with_no_op_default(isolated_env):
    """no_op_spawn returns None, so spawns_attempted increments but
    spawns_succeeded stays at 0 + reserved budget gets refunded."""
    ed = isolated_env["events_dir"]
    _write_evidence_delivered(
        ed,
        investigation_id="inv-1",
        gaps=[("a major substrate gap to chase", None)],
    )
    _write_evidence_delivered(
        ed,
        investigation_id="inv-2",
        gaps=[("a major substrate gap to chase", None)],
    )
    state = DaemonState()
    cfg = DaemonConfig(
        events_dir=ed,
        expected_cost_per_spawn_usd=0.20,
        max_spawns_per_iteration=3,
    )
    budget = DaemonBudget(daily_cap_usd=5.0)
    result = run_one_iteration(state=state, config=cfg, budget=budget)
    assert result.gaps_observed == 1
    assert result.gaps_eligible == 1
    assert result.spawns_attempted == 1
    assert result.spawns_succeeded == 0
    assert result.skipped_reasons.get("spawn_declined", 0) == 1


def test_run_one_iteration_spawns_with_real_callable(isolated_env):
    ed = isolated_env["events_dir"]
    _write_evidence_delivered(
        ed, investigation_id="inv-1", gaps=[("dispatch tier gap A", None)],
    )
    _write_evidence_delivered(
        ed, investigation_id="inv-2", gaps=[("dispatch tier gap A", None)],
    )
    _write_evidence_delivered(
        ed, investigation_id="inv-3", gaps=[("dispatch tier gap A", None)],
    )

    spawned: list[tuple[str, dict]] = []
    counter = {"i": 0}

    def fake_spawn(question: str, context: dict):
        counter["i"] += 1
        new_id = f"inv-spawned-{counter['i']}"
        spawned.append((question, context))
        return new_id

    state = DaemonState()
    cfg = DaemonConfig(
        events_dir=ed,
        expected_cost_per_spawn_usd=0.50,
        max_spawns_per_iteration=3,
    )
    budget = DaemonBudget(daily_cap_usd=5.0)
    result = run_one_iteration(
        state=state, config=cfg, budget=budget, spawn_fn=fake_spawn,
    )
    assert result.spawns_succeeded == 1
    assert len(result.spawned_investigation_ids) == 1
    assert spawned[0][1]["policy_id"] == "continuous_daemon"
    assert spawned[0][1]["topic_id"].startswith("topic-")
    assert state.chase_counts_by_key  # one entry recorded


def test_run_one_iteration_halts_when_daily_cap_exceeded(isolated_env):
    ed = isolated_env["events_dir"]
    for i in range(5):
        _write_evidence_delivered(
            ed,
            investigation_id=f"inv-{i}",
            gaps=[(f"gap number {i} that is substantive enough to chase", None)],
        )
        # Add a cross-pollination so each gap has co_occurrence>=2.
        _write_evidence_delivered(
            ed,
            investigation_id=f"inv-cross-{i}",
            gaps=[(f"gap number {i} that is substantive enough to chase", None)],
        )

    spawn_calls: list[str] = []

    def fake_spawn(q: str, ctx: dict):
        spawn_calls.append(q)
        return f"inv-out-{len(spawn_calls)}"

    state = DaemonState()
    cfg = DaemonConfig(
        events_dir=ed,
        expected_cost_per_spawn_usd=1.50,
        max_spawns_per_iteration=10,
    )
    # Daily cap fits 3 spawns at $1.50 each, 4th would exceed.
    budget = DaemonBudget(daily_cap_usd=5.0, per_investigation_cap_usd=2.0)
    result = run_one_iteration(
        state=state, config=cfg, budget=budget, spawn_fn=fake_spawn,
    )
    assert result.halted_by_budget is True
    assert result.spawns_succeeded == 3
    assert len(spawn_calls) == 3


def test_run_one_iteration_decays_chase_counts_across_iterations(isolated_env):
    ed = isolated_env["events_dir"]
    _write_evidence_delivered(
        ed, investigation_id="inv-A", gaps=[("specific persistent gap text", None)],
    )
    _write_evidence_delivered(
        ed, investigation_id="inv-B", gaps=[("specific persistent gap text", None)],
    )

    def fake_spawn(q: str, ctx: dict):
        return f"inv-out-{ctx['gap_normalized_key'][:6]}-{q[:8]}"

    state = DaemonState()
    cfg = DaemonConfig(
        events_dir=ed,
        expected_cost_per_spawn_usd=0.10,
        max_spawns_per_iteration=1,
    )
    budget = DaemonBudget(daily_cap_usd=100.0)

    # Run MAX_CHASE_COUNT iterations — each spawns once.
    for _ in range(MAX_CHASE_COUNT):
        result = run_one_iteration(
            state=state, config=cfg, budget=budget, spawn_fn=fake_spawn,
        )
        assert result.spawns_succeeded - sum(
            1 for v in state.chase_counts_by_key.values() if v == 0
        ) >= 0

    # On the next iteration, score should be 0 → gap not eligible → no spawn.
    prior_success = state.spawns_succeeded
    result = run_one_iteration(
        state=state, config=cfg, budget=budget, spawn_fn=fake_spawn,
    )
    # Gap has been chased MAX_CHASE_COUNT times → score=0 → not eligible.
    assert result.gaps_eligible == 0
    assert result.spawns_succeeded == prior_success
