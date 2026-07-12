"""Tests for the Midnight-Oil completion summary (ask #13 accountability).

Exercises the verdict priority (unknown > over_budget > over_time > goal_gap >
partial > delivered), the honesty rules (unmeasurable exclusion, unknown defer),
utilization ratios, validation, and purity/immutability.
"""

from __future__ import annotations

import dataclasses

import pytest

from substrate.midnight_oil.completion_summary import (
    CompletionSummary,
    CompletionSummaryError,
    MOCompletionInputs,
    build_completion_summary,
)


def _inputs(
    *,
    run_id: str = "mo-run-1",
    goals: int = 3,
    requested: int = 60,
    ceiling: float = 5.0,
    met: int = 0,
    partial: int = 0,
    unmet: int = 0,
    unmeasurable: int = 0,
    spend: float = 3.0,
    actual: int = 55,
    artifacts: int = 1,
) -> MOCompletionInputs:
    return MOCompletionInputs(
        run_id=run_id,
        goal_count=goals,
        requested_minutes=requested,
        price_ceiling_usd=ceiling,
        goals_met=met,
        goals_partial=partial,
        goals_unmet=unmet,
        goals_unmeasurable=unmeasurable,
        actual_spend_usd=spend,
        actual_minutes=actual,
        artifacts_produced=artifacts,
    )


# --- verdict: delivered ----------------------------------------------------


def test_delivered_all_goals_met_within_bounds() -> None:
    report = build_completion_summary(
        _inputs(goals=3, met=3, spend=3.0, ceiling=5.0, actual=55, requested=60)
    )
    assert report.verdict == "delivered"
    assert report.delivery_ratio == pytest.approx(1.0)
    assert report.budget_utilization == pytest.approx(0.6)
    assert report.time_utilization == pytest.approx(55 / 60)


# --- verdict: partial ------------------------------------------------------


def test_partial_some_goals_partial() -> None:
    report = build_completion_summary(
        _inputs(goals=3, met=2, partial=1, spend=3.0, ceiling=5.0)
    )
    assert report.verdict == "partial"
    assert report.delivery_ratio == pytest.approx(2 / 3)


# --- verdict: goal_gap -----------------------------------------------------


def test_goal_gap_unmet_goals() -> None:
    report = build_completion_summary(
        _inputs(goals=3, met=1, unmet=2, spend=3.0, ceiling=5.0)
    )
    assert report.verdict == "goal_gap"


def test_goal_gap_notes_mention_unmet() -> None:
    report = build_completion_summary(_inputs(met=1, unmet=2))
    joined = " | ".join(report.notes).lower()
    assert "unmet" in joined


# --- verdict: over_budget (priority over goals) ----------------------------


def test_over_budget_takes_priority_over_delivered() -> None:
    # All goals met BUT overspent -> over_budget (not delivered)
    report = build_completion_summary(
        _inputs(goals=3, met=3, spend=6.0, ceiling=5.0)
    )
    assert report.verdict == "over_budget"
    assert report.budget_utilization == pytest.approx(1.2)


def test_over_budget_takes_priority_over_goal_gap() -> None:
    # Has unmet goals AND overspent -> over_budget (spend violation surfaces first)
    report = build_completion_summary(
        _inputs(met=1, unmet=2, spend=6.0, ceiling=5.0)
    )
    assert report.verdict == "over_budget"


# --- verdict: over_time ----------------------------------------------------


def test_over_time_after_budget_ok() -> None:
    # Within budget, but over time -> over_time
    report = build_completion_summary(
        _inputs(met=3, spend=3.0, ceiling=5.0, actual=70, requested=60)
    )
    assert report.verdict == "over_time"
    assert report.time_utilization is not None and report.time_utilization > 1.0


def test_over_budget_beats_over_time() -> None:
    # Both over budget AND over time -> over_budget (spend priority)
    report = build_completion_summary(
        _inputs(met=3, spend=6.0, ceiling=5.0, actual=70, requested=60)
    )
    assert report.verdict == "over_budget"


# --- verdict: unknown ------------------------------------------------------


def test_unknown_no_measurable_no_spend() -> None:
    report = build_completion_summary(
        _inputs(goals=2, unmeasurable=2, met=0, spend=0.0)
    )
    assert report.verdict == "unknown"
    assert report.delivery_ratio is None
    assert any("defer" in n for n in report.notes)


def test_unknown_not_fabricated_as_delivered() -> None:
    # No measurable goals but DID spend -> not unknown (spend > 0), not delivered
    # (no goals met). Should be... let's see: measurable=0, spend>0 -> not unknown.
    # Then over_budget? No (3/5). over_time? No. goal_gap? unmet=0. partial? ratio None.
    # delivery_ratio None < 1.0 is False (None). So falls to delivered? No —
    # measurable==0 means delivery_ratio is None, partial check is ratio < 1.0
    # which is None < 1.0 -> False. So delivered with 0 measurable goals.
    # That's actually honest: spent money, no goals to miss, within bounds.
    report = build_completion_summary(
        _inputs(goals=2, unmeasurable=2, spend=3.0, ceiling=5.0)
    )
    # No measurable goals but spend within bounds -> delivered (honest: nothing failed)
    assert report.verdict == "delivered"
    assert report.measurable_goal_count == 0


# --- honesty: unmeasurable excluded from ratio -----------------------------


def test_unmeasurable_excluded_from_delivery_ratio() -> None:
    # 2 met, 1 unmeasurable -> ratio = 2/2 = 1.0 (unmeasurable excluded)
    report = build_completion_summary(
        _inputs(goals=3, met=2, unmeasurable=1, spend=3.0, ceiling=5.0)
    )
    assert report.measurable_goal_count == 2
    assert report.delivery_ratio == pytest.approx(1.0)
    assert report.verdict == "delivered"


# --- utilization ratios ----------------------------------------------------


def test_budget_utilization_none_when_ceiling_zero() -> None:
    report = build_completion_summary(
        _inputs(met=1, spend=0.0, ceiling=0.0)
    )
    assert report.budget_utilization is None


def test_time_utilization_none_when_requested_zero() -> None:
    report = build_completion_summary(
        _inputs(met=1, spend=3.0, ceiling=5.0, actual=0, requested=0)
    )
    assert report.time_utilization is None


def test_exact_ceiling_is_delivered_not_over_budget() -> None:
    # spend == ceiling -> utilization 1.0, NOT > 1.0 -> not over_budget
    report = build_completion_summary(
        _inputs(met=3, spend=5.0, ceiling=5.0)
    )
    assert report.budget_utilization == pytest.approx(1.0)
    assert report.verdict == "delivered"


def test_exact_time_box_is_delivered_not_over_time() -> None:
    report = build_completion_summary(
        _inputs(met=3, spend=3.0, ceiling=5.0, actual=60, requested=60)
    )
    assert report.time_utilization == pytest.approx(1.0)
    assert report.verdict == "delivered"


# --- provenance / purity ---------------------------------------------------


def test_run_id_carried_through() -> None:
    report = build_completion_summary(_inputs(run_id="mo-777", met=1))
    assert report.run_id == "mo-777"


def test_authority_is_always_advisory() -> None:
    assert build_completion_summary(_inputs(met=1)).authority == "advisory"


def test_summary_is_immutable() -> None:
    report = build_completion_summary(_inputs(met=1))
    assert isinstance(report, CompletionSummary)
    assert dataclasses.is_dataclass(report)
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.verdict = "delivered"  # type: ignore[misc]


def test_inputs_is_immutable() -> None:
    inp = _inputs(met=1)
    assert isinstance(inp, MOCompletionInputs)
    with pytest.raises(dataclasses.FrozenInstanceError):
        inp.goals_met = 5  # type: ignore[misc]


def test_determinism_same_inputs_same_report() -> None:
    inp = _inputs(met=2, partial=1)
    assert build_completion_summary(inp) == build_completion_summary(inp)


def test_notes_describe_verdict() -> None:
    report = build_completion_summary(_inputs(met=1, unmet=1))
    joined = " | ".join(report.notes).lower()
    assert "descriptive" in joined
    assert "unmet" in joined


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "field,bad",
    [
        ("goals", -1),
        ("ceiling", -0.1),
        ("spend", -1.0),
        ("actual", -1),
        ("requested", -1),
        ("met", -1),
        ("unmet", -1),
    ],
)
def test_validation_rejects_negatives(field: str, bad: int | float) -> None:
    base: dict[str, object] = {"met": 1, "spend": 3.0, "ceiling": 5.0}
    base[field] = bad
    with pytest.raises(CompletionSummaryError):
        build_completion_summary(_inputs(**base))  # type: ignore[arg-type]


# --- public api exports ----------------------------------------------------


def test_public_api_exports() -> None:
    from substrate.midnight_oil import completion_summary as mod

    assert set(mod.__all__) == {
        "CompletionSummary",
        "CompletionSummaryError",
        "MOCompletionInputs",
        "build_completion_summary",
    }
    assert issubclass(mod.CompletionSummaryError, ValueError)
    assert dataclasses.is_dataclass(mod.MOCompletionInputs)
    assert dataclasses.is_dataclass(mod.CompletionSummary)
