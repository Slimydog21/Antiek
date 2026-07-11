"""Hermetic tests for pure Antiek-bench recursive rewrite."""

from __future__ import annotations

import pytest

from substrate.antiek_bench_recursive_rewrite import (
    AntiekBenchRewriteError,
    propose_antiek_bench_recursive_rewrite,
)


def test_proposes_from_failures() -> None:
    p = propose_antiek_bench_recursive_rewrite(
        week_label="2026-W28",
        patterns=[
            {
                "task_family": "citation_binding",
                "model_id": "model-a",
                "outcome": "failed",
                "n": 3,
            },
            {
                "task_family": "citation_binding",
                "model_id": "model-b",
                "outcome": "worked",
                "n": 2,
            },
            {
                "task_family": "html_compose",
                "model_id": "model-a",
                "outcome": "mixed",
                "n": 2,
            },
        ],
    )
    assert p.applied is False
    assert p.to_dict()["applied"] is False
    assert len(p.proposals) == 2
    assert p.proposals[0].task_family == "citation_binding"
    assert p.proposals[0].priority == 3
    assert p.proposals[0].focus_models[0] == "model-a"


def test_empty_patterns() -> None:
    p = propose_antiek_bench_recursive_rewrite(week_label="2026-W28", patterns=[])
    assert p.proposals == ()
    assert p.applied is False


def test_unknown_no_invent() -> None:
    p = propose_antiek_bench_recursive_rewrite(
        week_label="2026-W28",
        patterns=[
            {
                "task_family": "research_pack",
                "model_id": "m1",
                "outcome": "unknown",
                "n": 10,
            }
        ],
    )
    assert p.proposals == ()
    assert any("unknown" in n for n in p.notes)


def test_rejects_bad_outcome() -> None:
    with pytest.raises(AntiekBenchRewriteError, match="outcome"):
        propose_antiek_bench_recursive_rewrite(
            week_label="w",
            patterns=[
                {
                    "task_family": "t",
                    "model_id": "m",
                    "outcome": "great",
                }
            ],
        )


def test_requires_week() -> None:
    with pytest.raises(AntiekBenchRewriteError, match="week_label"):
        propose_antiek_bench_recursive_rewrite(week_label="  ", patterns=[])
