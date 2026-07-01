"""Tests for the Antiek rubric to Verifiers eval adapter."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.eval.antiek_rubric_to_verifiers import (
    AntiekRubricScore,
    adapt_antiek_rubric,
    parameter_extractor_verifiers_adapter,
)


def _fixture_rows() -> list[dict]:
    path = Path("tests/fixtures/parameter_extractor_v0.jsonl")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_parameter_extractor_adapter_scores_exact_fixture_match():
    row = _fixture_rows()[0]
    completion = {"parameters": row["expected_parameters"]}

    result = parameter_extractor_verifiers_adapter().score(completion, row)

    assert result["reward"] == 1.0
    assert result["info"]["deterministic_score"] == 1.0
    assert result["info"]["judged_score"] is None
    assert result["info"]["final_score"] == 1.0
    assert result["info"]["metadata"]["matched"] == 1
    assert result["info"]["metadata"]["expected"] == 1


def test_parameter_extractor_adapter_returns_partial_reward_without_losing_split():
    row = _fixture_rows()[2]
    completion = {"parameters": [row["expected_parameters"][0]]}

    result = parameter_extractor_verifiers_adapter().score(completion, row)

    assert result["reward"] == pytest.approx(2 / 3)
    assert result["info"]["deterministic_score"] == pytest.approx(2 / 3)
    assert result["info"]["judged_score"] is None
    assert result["info"]["final_score"] == pytest.approx(2 / 3)
    assert result["info"]["metadata"]["precision"] == 1.0
    assert result["info"]["metadata"]["recall"] == 0.5


def test_adapter_reward_exposes_prime_scalar_but_score_preserves_antiek_fields():
    adapter = adapt_antiek_rubric(
        lambda completion, reference: AntiekRubricScore(
            deterministic_score=0.75,
            judged_score=0.50,
            final_score=0.60,
            notes="weighted by operator rubric",
            metadata={"rubric": "test"},
        )
    )

    assert adapter.reward("completion", {"reference": True}) == 0.60
    result = adapter.score("completion", {"reference": True})
    assert result == {
        "reward": 0.60,
        "info": {
            "deterministic_score": 0.75,
            "judged_score": 0.50,
            "final_score": 0.60,
            "notes": "weighted by operator rubric",
            "metadata": {"rubric": "test"},
        },
    }


def test_adapter_rejects_out_of_range_scores():
    with pytest.raises(ValueError, match="final_score must be a number in \\[0, 1\\]"):
        AntiekRubricScore(
            deterministic_score=1.0,
            judged_score=None,
            final_score=1.2,
        )
