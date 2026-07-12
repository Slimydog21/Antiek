"""Tests for the Midnight Oil launch brief (ask #13 trust anchor)."""

from __future__ import annotations

import pytest

from substrate.midnight_oil.launch_brief import (
    LaunchBrief,
    LaunchBriefError,
    LaunchRefusal,
    OperatorApproval,
    PlanSummary,
    build_launch_brief,
)


def _plan(*, total=0.30, known=True, phase_count=3, plan_id="mo-plan-abc") -> PlanSummary:
    return PlanSummary(
        plan_id=plan_id,
        phase_count=phase_count,
        total_duration_minutes=60,
        goals=("understand X", "survey Y"),
        plan_total_high_cost_usd=total if known else None,
        pricing_known=known,
    )


def _approval(*, ceiling=0.50, granted=True, expired=False, revoked=False,
              operator="op-1", token="secret-consent-tok") -> OperatorApproval:
    return OperatorApproval(
        operator_id=operator,
        granted=granted,
        approved_ceiling_usd=ceiling,
        is_expired=expired,
        revoked=revoked,
        consent_token=token,
    )


# --------------------------------------------------------------------------- #
# Invariant #1 — effective ceiling is min(approved, plan-total); over-ceiling refuses.
# --------------------------------------------------------------------------- #
def test_effective_ceiling_is_min_when_plan_under_approved():
    result = build_launch_brief(
        plan=_plan(total=0.30), approval=_approval(ceiling=0.50), launched_at_label="t0"
    )
    assert isinstance(result, LaunchBrief)
    assert result.effective_ceiling_usd == pytest.approx(0.30)  # min(0.50, 0.30)
    assert result.ceiling_known is True


def test_over_ceiling_plan_refuses_launch():
    result = build_launch_brief(
        plan=_plan(total=0.80), approval=_approval(ceiling=0.50), launched_at_label="t0"
    )
    assert isinstance(result, LaunchRefusal)
    assert result.reason == "plan exceeds approved ceiling"
    assert "0.8000" in result.detail and "0.5000" in result.detail


def test_plan_total_equals_approved_ceiling_launches():
    result = build_launch_brief(
        plan=_plan(total=0.50), approval=_approval(ceiling=0.50), launched_at_label="t0"
    )
    assert isinstance(result, LaunchBrief)
    assert result.effective_ceiling_usd == pytest.approx(0.50)


# --------------------------------------------------------------------------- #
# Invariant #2 — requires explicit, unexpired, unrevoked consent naming a ceiling.
# --------------------------------------------------------------------------- #
def test_no_consent_refuses():
    result = build_launch_brief(
        plan=_plan(), approval=_approval(granted=False), launched_at_label="t0"
    )
    assert isinstance(result, LaunchRefusal)
    assert result.reason == "no operator consent"


def test_revoked_consent_refuses():
    result = build_launch_brief(
        plan=_plan(), approval=_approval(revoked=True), launched_at_label="t0"
    )
    assert isinstance(result, LaunchRefusal)
    assert result.reason == "consent revoked"


def test_expired_consent_refuses():
    result = build_launch_brief(
        plan=_plan(), approval=_approval(expired=True), launched_at_label="t0"
    )
    assert isinstance(result, LaunchRefusal)
    assert result.reason == "consent expired"


def test_no_ceiling_named_refuses():
    result = build_launch_brief(
        plan=_plan(), approval=_approval(ceiling=None), launched_at_label="t0"
    )
    assert isinstance(result, LaunchRefusal)
    assert result.reason == "no ceiling named"


# --------------------------------------------------------------------------- #
# Invariant #3 — immutable + content-addressed.
# --------------------------------------------------------------------------- #
def test_brief_id_deterministic():
    args = dict(plan=_plan(), approval=_approval(), launched_at_label="t0")
    b1 = build_launch_brief(**args)
    b2 = build_launch_brief(**args)
    assert isinstance(b1, LaunchBrief) and isinstance(b2, LaunchBrief)
    assert b1.brief_id == b2.brief_id


def test_brief_id_changes_with_ceiling():
    b1 = build_launch_brief(plan=_plan(total=0.30), approval=_approval(ceiling=0.50), launched_at_label="t0")
    b2 = build_launch_brief(plan=_plan(total=0.40), approval=_approval(ceiling=0.50), launched_at_label="t0")
    assert isinstance(b1, LaunchBrief) and isinstance(b2, LaunchBrief)
    assert b1.brief_id != b2.brief_id


def test_brief_id_changes_with_goal():
    p1 = _plan()
    p2 = PlanSummary(plan_id="mo-plan-abc", phase_count=3, total_duration_minutes=60,
                     goals=("different goal",), plan_total_high_cost_usd=0.30, pricing_known=True)
    b1 = build_launch_brief(plan=p1, approval=_approval(), launched_at_label="t0")
    b2 = build_launch_brief(plan=p2, approval=_approval(), launched_at_label="t0")
    assert isinstance(b1, LaunchBrief) and isinstance(b2, LaunchBrief)
    assert b1.brief_id != b2.brief_id


def test_brief_id_changes_with_operator():
    b1 = build_launch_brief(plan=_plan(), approval=_approval(operator="op-1"), launched_at_label="t0")
    b2 = build_launch_brief(plan=_plan(), approval=_approval(operator="op-2"), launched_at_label="t0")
    assert b1.brief_id != b2.brief_id


def test_brief_is_frozen():
    import dataclasses

    result = build_launch_brief(plan=_plan(), approval=_approval(), launched_at_label="t0")
    assert isinstance(result, LaunchBrief)
    with pytest.raises(dataclasses.FrozenInstanceError):
        result.effective_ceiling_usd = 999  # type: ignore[misc]


# --------------------------------------------------------------------------- #
# Invariant #4 — unknown plan total: brief buildable, ceiling_known False, honest note.
# --------------------------------------------------------------------------- #
def test_unpriced_plan_total_uses_approved_ceiling():
    result = build_launch_brief(
        plan=_plan(known=False), approval=_approval(ceiling=0.50), launched_at_label="t0"
    )
    assert isinstance(result, LaunchBrief)
    assert result.ceiling_known is False
    assert result.effective_ceiling_usd == pytest.approx(0.50)
    assert any("pricing incomplete" in n for n in result.honesty_notes)


# --------------------------------------------------------------------------- #
# Invariant #5 — consent token NEVER stored; only the redacted hash.
# --------------------------------------------------------------------------- #
def test_raw_token_not_in_brief():
    result = build_launch_brief(
        plan=_plan(), approval=_approval(token="super-secret-tok-123"), launched_at_label="t0"
    )
    assert isinstance(result, LaunchBrief)
    brief_repr = repr(result.__dict__)
    assert "super-secret-tok-123" not in brief_repr
    assert result.token_hash.startswith("sha256:")
    assert result.token_hash != "super-secret-tok-123"


def test_token_hash_deterministic_and_matches_redaction():
    import hashlib

    result = build_launch_brief(
        plan=_plan(), approval=_approval(token="abc"), launched_at_label="t0"
    )
    assert isinstance(result, LaunchBrief)
    expected = "sha256:" + hashlib.sha256(b"abc").hexdigest()[:16]
    assert result.token_hash == expected


def test_different_tokens_different_hashes():
    b1 = build_launch_brief(plan=_plan(), approval=_approval(token="tok-a"), launched_at_label="t0")
    b2 = build_launch_brief(plan=_plan(), approval=_approval(token="tok-b"), launched_at_label="t0")
    assert isinstance(b1, LaunchBrief) and isinstance(b2, LaunchBrief)
    assert b1.token_hash != b2.token_hash


# --------------------------------------------------------------------------- #
# Invariant #6 — goals carried verbatim + exact count.
# --------------------------------------------------------------------------- #
def test_goals_carried_verbatim():
    goals = ("understand transformers", "survey RLHF", "compare methods")
    plan = PlanSummary(plan_id="p", phase_count=3, total_duration_minutes=90, goals=goals,
                       plan_total_high_cost_usd=0.30, pricing_known=True)
    result = build_launch_brief(plan=plan, approval=_approval(), launched_at_label="t0")
    assert isinstance(result, LaunchBrief)
    assert result.goals == goals
    assert result.goal_count == 3


# --------------------------------------------------------------------------- #
# Invariant #7 — pure + fail-closed on structural bad input.
# --------------------------------------------------------------------------- #
def test_blank_launched_at_rejected():
    with pytest.raises(LaunchBriefError, match="launched_at_label"):
        build_launch_brief(plan=_plan(), approval=_approval(), launched_at_label="  ")


def test_blank_plan_id_rejected():
    bad = PlanSummary(plan_id="  ", phase_count=3, total_duration_minutes=60,
                      goals=("g",), plan_total_high_cost_usd=0.3, pricing_known=True)
    with pytest.raises(LaunchBriefError, match="plan_id"):
        build_launch_brief(plan=bad, approval=_approval(), launched_at_label="t0")


def test_empty_goals_rejected():
    bad = PlanSummary(plan_id="p", phase_count=3, total_duration_minutes=60, goals=(),
                      plan_total_high_cost_usd=0.3, pricing_known=True)
    with pytest.raises(LaunchBriefError, match="goals"):
        build_launch_brief(plan=bad, approval=_approval(), launched_at_label="t0")


def test_blank_token_rejected():
    with pytest.raises(LaunchBriefError, match="consent_token"):
        build_launch_brief(plan=_plan(), approval=_approval(token="  "), launched_at_label="t0")


def test_negative_ceiling_rejected():
    with pytest.raises(LaunchBriefError, match=">= 0"):
        build_launch_brief(plan=_plan(), approval=_approval(ceiling=-0.1), launched_at_label="t0")


def test_purity_no_io_imports():
    import inspect

    from substrate.midnight_oil import launch_brief as mod

    src = inspect.getsource(mod)
    for forbidden in ("import os", "import time", "import asyncio", "open(", "datetime.now", "requests"):
        assert forbidden not in src, f"purity breach: {forbidden!r}"


def test_boundary_types_frozen():
    import dataclasses

    for cls in (PlanSummary, OperatorApproval, LaunchBrief, LaunchRefusal):
        assert dataclasses.is_dataclass(cls)
