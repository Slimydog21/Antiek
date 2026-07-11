"""Hermetic tests for competition gap residual plan."""

from __future__ import annotations

import pytest

from substrate.competition_gap_residual_plan import (
    CompetitionGapResidualPlanError,
    build_competition_gap_residual_plan,
)

DECISIONS = [
    {
        "competitor": "Perplexity",
        "area": "source_acquisition",
        "decision_summary": "Live web",
        "antiek_status": "parity",
    },
    {
        "competitor": "Elicit",
        "area": "citation_grounding",
        "decision_summary": "spans",
        "antiek_status": "behind",
        "residual": "Wire citation spans into DR quality floor",
    },
    {
        "competitor": "Consensus",
        "area": "evaluation_harness",
        "decision_summary": "meta",
        "antiek_status": "unknown",
    },
    {
        "competitor": "X",
        "area": "model_routing",
        "decision_summary": "router",
        "antiek_status": "behind",
    },
]


def test_orders_behind_before_unknown() -> None:
    plan = build_competition_gap_residual_plan(decisions=DECISIONS)
    assert plan.backlog_mutated is False
    assert plan.to_dict()["backlog_mutated"] is False
    assert plan.item_count == 3
    assert plan.p0_count == 2
    assert plan.unknown_planned == 1
    assert plan.items[0].priority == "P0"
    assert "citation spans" in plan.items[0].residual_text
    assert plan.items[1].priority == "P0"
    assert "without residual text" in plan.items[1].residual_text
    assert plan.items[2].priority == "P1"
    assert plan.authority == "competition_gap_residual_plan_advisory"


def test_empty_when_only_ahead() -> None:
    plan = build_competition_gap_residual_plan(
        decisions=[
            {
                "competitor": "A",
                "area": "budget_controls",
                "decision_summary": "caps",
                "antiek_status": "ahead",
            }
        ]
    )
    assert plan.items == ()
    assert any("no invent items" in n for n in plan.notes)
    assert plan.backlog_mutated is False


def test_max_items() -> None:
    plan = build_competition_gap_residual_plan(decisions=DECISIONS, max_items=1)
    assert plan.item_count == 1
    assert plan.items[0].antiek_status == "behind"
    assert any("max_items=1" in n for n in plan.notes)


def test_rejects_invalid_area_and_max() -> None:
    with pytest.raises(CompetitionGapResidualPlanError, match="max_items"):
        build_competition_gap_residual_plan(decisions=DECISIONS, max_items=0)
    with pytest.raises(CompetitionGapResidualPlanError, match="area"):
        build_competition_gap_residual_plan(
            decisions=[
                {
                    "competitor": "Elicit",
                    "area": "nonsense",
                    "decision_summary": "x",
                    "antiek_status": "behind",
                }
            ]
        )


def test_rejects_blank_competitor() -> None:
    with pytest.raises(CompetitionGapResidualPlanError, match="competitor"):
        build_competition_gap_residual_plan(
            decisions=[
                {
                    "competitor": "  ",
                    "area": "source_acquisition",
                    "decision_summary": "x",
                    "antiek_status": "behind",
                }
            ]
        )
