"""Hermetic tests for pure deep research quality rubric."""

from __future__ import annotations

import pytest

from substrate.deep_research_quality import (
    QUALITY_DIMENSIONS,
    DeepResearchQualityError,
    evaluate_deep_research_quality,
)


def test_weighted_overall() -> None:
    r = evaluate_deep_research_quality(
        research_id="dr-1",
        dimensions=[
            {"dimension": "citation_density", "score": 0.8},
            {"dimension": "claim_grounding", "score": 1.0},
            {"dimension": "intellectual_honesty", "score": 0.9},
        ],
    )
    assert r.persisted is False
    assert r.to_dict()["persisted"] is False
    assert r.known_count == 3
    assert "source_diversity" in r.missing
    assert r.overall is not None
    # citation 0.8×1.2 + claim 1.0×1.3 + honesty 0.9×1.4 = 3.52 / 3.9
    assert abs(r.overall - (3.52 / 3.9)) < 1e-9


def test_overall_null_when_empty() -> None:
    r = evaluate_deep_research_quality(research_id="dr-2", dimensions=[])
    assert r.overall is None
    assert r.known_count == 0
    assert len(r.missing) == len(QUALITY_DIMENSIONS)
    assert any("no invent 0" in n for n in r.notes)


def test_require_all() -> None:
    r = evaluate_deep_research_quality(
        research_id="dr-3",
        require_all_dimensions=True,
        dimensions=[{"dimension": "citation_density", "score": 1}],
    )
    assert r.overall is None


def test_rejects_out_of_range() -> None:
    with pytest.raises(DeepResearchQualityError, match=r"\[0, 1\]"):
        evaluate_deep_research_quality(
            research_id="dr",
            dimensions=[{"dimension": "actionability", "score": 1.5}],
        )


def test_rejects_duplicate() -> None:
    with pytest.raises(DeepResearchQualityError, match="duplicate"):
        evaluate_deep_research_quality(
            research_id="dr",
            dimensions=[
                {"dimension": "actionability", "score": 0.5},
                {"dimension": "actionability", "score": 0.6},
            ],
        )


def test_null_score_unknown() -> None:
    r = evaluate_deep_research_quality(
        research_id="dr",
        dimensions=[{"dimension": "citation_density", "score": None}],
    )
    assert r.known_count == 0
    assert r.overall is None
