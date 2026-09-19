from __future__ import annotations

from dataclasses import replace

import pytest

from substrate.dispatch.research_cost_envelope import (
    ResearchCostEnvelopeInvalid,
    build_loop_one_workload_plan,
    build_whole_run_cost_envelope,
)
from substrate.dispatch.research_quote import build_research_route_manifest
from tests.test_research_quote import _config


def test_loop_one_plan_covers_real_conditional_call_bounds() -> None:
    plan = build_loop_one_workload_plan(max_sub_questions=8)
    assert [
        (row.role, row.mandatory_calls, row.conditional_calls, row.max_calls) for row in plan.roles
    ] == [
        ("decomposer", 1, 1, 2),
        ("evidence_retriever", 1, 7, 8),
        ("parameter_extractor", 1, 0, 1),
        ("connector", 1, 0, 1),
        ("synthesizer", 1, 5, 6),
        ("knowledge_extractor", 0, 12, 12),
    ]
    assert len(plan.plan_sha256) == 64
    assert build_loop_one_workload_plan(max_sub_questions=8) == plan
    assert build_loop_one_workload_plan(max_sub_questions=4).plan_sha256 != plan.plan_sha256


def test_envelope_uses_fallback_max_not_sum_and_exact_selected_synthesizer() -> None:
    config = _config()
    for role in (
        "evidence_retriever",
        "parameter_extractor",
        "connector",
        "knowledge_extractor",
    ):
        config.role_tiers[role] = "pro"
    manifest = build_research_route_manifest(config)
    selected = next(
        row for row in manifest.routes if row.role == "synthesizer" and row.fallback_index == 1
    )
    envelope = build_whole_run_cost_envelope(
        manifest,
        selected_driver_role="synthesizer",
        selected_driver_provider=selected.provider,
        selected_driver_model=selected.model,
        selected_driver_pricing_fingerprint=selected.pricing_fingerprint,
    )
    synthesizer = next(row for row in envelope.roles if row.role == "synthesizer")
    decomposer = next(row for row in envelope.roles if row.role == "decomposer")
    assert synthesizer.selected_route_only is True
    assert synthesizer.pricing_fingerprints == (selected.pricing_fingerprint,)
    assert decomposer.selected_route_only is False
    assert len(decomposer.pricing_fingerprints) == 2
    expected_decomposer_max = max(
        max(row.input_per_mtok, row.cached_input_per_mtok, row.input_per_mtok * 1.25)
        * row.context_budget_tokens * 4
        + row.output_per_mtok * row.max_output_tokens
        for row in manifest.routes
        if row.role == "decomposer"
    ) / 1_000_000
    assert float(decomposer.route_max_usd) == pytest.approx(expected_decomposer_max)
    assert envelope.projection_kind == "admission_upper_bound"
    assert envelope.forecast_status == "not_measured"
    assert envelope.forecast_usd_low is None


def test_envelope_fails_closed_on_unknown_pricing_or_missing_role() -> None:
    config = _config()
    for role in (
        "evidence_retriever",
        "parameter_extractor",
        "connector",
        "knowledge_extractor",
    ):
        config.role_tiers[role] = "pro"
    manifest = build_research_route_manifest(config)
    selected = next(row for row in manifest.routes if row.role == "synthesizer")
    missing = replace(
        manifest,
        routes=tuple(row for row in manifest.routes if row.role != "connector"),
    )
    with pytest.raises(ResearchCostEnvelopeInvalid, match="connector"):
        build_whole_run_cost_envelope(
            missing,
            selected_driver_role="synthesizer",
            selected_driver_provider=selected.provider,
            selected_driver_model=selected.model,
            selected_driver_pricing_fingerprint=selected.pricing_fingerprint,
        )
