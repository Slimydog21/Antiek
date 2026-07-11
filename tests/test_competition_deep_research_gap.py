"""Hermetic tests for pure competition deep research gap matrix."""

from __future__ import annotations

import pytest

from substrate.competition_deep_research_gap import (
    CompetitionDeepResearchGapError,
    build_competition_deep_research_gap,
)


def test_counts_and_residuals() -> None:
    m = build_competition_deep_research_gap(
        decisions=[
            {
                "competitor": "Perplexity",
                "area": "source_acquisition",
                "decision_summary": "Live web + citation cards",
                "antiek_status": "parity",
            },
            {
                "competitor": "Elicit",
                "area": "citation_grounding",
                "decision_summary": "Paper-grounded claims with spans",
                "antiek_status": "behind",
                "residual": "Wire citation spans into DR quality floor",
            },
            {
                "competitor": "Consensus",
                "area": "evaluation_harness",
                "decision_summary": "Literature meta-analysis UX",
                "antiek_status": "unknown",
            },
        ]
    )
    assert m.backlog_mutated is False
    assert m.to_dict()["backlog_mutated"] is False
    assert m.behind_count == 1
    assert m.unknown_count == 1
    assert m.parity_count == 1
    assert "Wire citation spans into DR quality floor" in m.residuals
    assert m.authority == "competition_deep_research_gap_advisory"


def test_empty_matrix() -> None:
    m = build_competition_deep_research_gap(decisions=[])
    assert m.decisions == ()
    assert m.behind_count == 0
    assert any("no invent competitors" in n for n in m.notes)


def test_focus_filter() -> None:
    m = build_competition_deep_research_gap(
        focus_areas=["budget_controls"],
        decisions=[
            {
                "competitor": "A",
                "area": "budget_controls",
                "decision_summary": "Hard spend caps",
                "antiek_status": "ahead",
            },
            {
                "competitor": "B",
                "area": "model_routing",
                "decision_summary": "Auto router",
                "antiek_status": "behind",
                "residual": "should be filtered out",
            },
        ],
    )
    assert len(m.decisions) == 1
    assert m.behind_count == 0
    assert m.ahead_count == 1


def test_behind_without_residual_fallback() -> None:
    m = build_competition_deep_research_gap(
        decisions=[
            {
                "competitor": "X",
                "area": "model_routing",
                "decision_summary": "Router service",
                "antiek_status": "behind",
            }
        ]
    )
    assert m.behind_count == 1
    assert any("gap recorded without residual text" in r for r in m.residuals)


def test_rejects_blank_competitor() -> None:
    with pytest.raises(CompetitionDeepResearchGapError, match="competitor"):
        build_competition_deep_research_gap(
            decisions=[
                {
                    "competitor": "  ",
                    "area": "source_acquisition",
                    "decision_summary": "x",
                    "antiek_status": "parity",
                }
            ]
        )


def test_rejects_invalid_status() -> None:
    with pytest.raises(CompetitionDeepResearchGapError, match="antiek_status"):
        build_competition_deep_research_gap(
            decisions=[
                {
                    "competitor": "X",
                    "area": "source_acquisition",
                    "decision_summary": "y",
                    "antiek_status": "winning",
                }
            ]
        )
