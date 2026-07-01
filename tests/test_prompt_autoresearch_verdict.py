"""Autoresearch Wedge 1 ratify-or-reject verdict (§15.6, the Lutke-gap test)."""

from __future__ import annotations

import json
from decimal import Decimal

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.score import CompositeScore
from tools.prompt_autoresearch.verdict import (
    MIN_MEAN_DELTA,
    MIN_MUTATIONS,
    Verdict,
    compute_verdict,
    render_verdict_markdown,
)
from tools.prompt_autoresearch.outcomes_io import (
    load_outcomes_json,
    outcome_to_json,
    write_outcomes_json,
)


def _mk_outcome(
    *,
    mutation_id: str,
    delta: float,
    accepted: bool,
    rubric: float = 0.85,
    voice_style: float = 0.85,
    sector_vocab: float = 0.85,
    grounding: float = 0.90,
    mutation_rationale: str = "",
    parent_baseline_id: str | None = None,
    proposed_at: str = "",
) -> PromptMutationOutcome:
    return PromptMutationOutcome(
        mutation_id=mutation_id,
        accepted=accepted,
        baseline_score=0.70,
        candidate_score=0.70 + delta,
        delta=delta,
        epsilon_required=0.05,
        composite_breakdown=CompositeScore(
            rubric=rubric,
            voice_style=voice_style,
            sector_vocab=sector_vocab,
            grounding=grounding,
            total=0.70 + delta,
        ),
        cost_usd=Decimal("0.05"),
        mutation_rationale=mutation_rationale,
        parent_baseline_id=parent_baseline_id,
        proposed_at=proposed_at,
    )


def test_empty_outcomes_insufficient_data():
    v = compute_verdict("synthesizer", [])
    assert v.decision == "insufficient_data"
    assert v.iteration_count == 0


def test_compute_verdict_rejects_invalid_thresholds():
    outcome = _mk_outcome(mutation_id="m-0", delta=0.10, accepted=True)

    try:
        compute_verdict("synthesizer", [outcome], min_mutations=0)
    except ValueError as exc:
        assert "min_mutations must be a positive integer" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected invalid min_mutations to be rejected")

    try:
        compute_verdict("synthesizer", [outcome], min_acceptance_rate=1.5)
    except ValueError as exc:
        assert "min_acceptance_rate must be a number in [0, 1]" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected invalid min_acceptance_rate to be rejected")

    try:
        compute_verdict("synthesizer", [outcome], min_mean_delta=-0.01)
    except ValueError as exc:
        assert "min_mean_delta must be a non-negative finite number" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected invalid min_mean_delta to be rejected")


def test_below_min_mutations_insufficient_data():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
        for i in range(5)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "insufficient_data"
    assert "Only 5 mutations" in v.rationale


def test_ratify_when_acceptance_and_mean_delta_pass():
    # 20 mutations, all accepted, mean delta 0.10 — clean ratify
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "ratify"
    assert v.acceptance_rate == 1.0
    assert v.mean_delta == 0.10
    assert v.sub_metric_regressions == []


def test_reject_when_acceptance_rate_below_floor():
    # 20 mutations, only 4 accepted (20%) — below 40% floor → reject
    outs = []
    for i in range(MIN_MUTATIONS):
        if i < 4:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True))
        else:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=-0.05, accepted=False))
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert v.accepted_count == 4
    assert v.rejected_count == 16
    assert v.acceptance_rate == 4 / MIN_MUTATIONS
    assert "acceptance rate" in v.rationale


def test_reject_when_mean_delta_below_floor():
    # 20 mutations, 60% accepted but mean delta tiny → mean below floor
    outs = []
    for i in range(MIN_MUTATIONS):
        if i < 12:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=0.02, accepted=True))
        else:
            outs.append(_mk_outcome(mutation_id=f"m-{i}", delta=-0.05, accepted=False))
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert v.mean_delta < MIN_MEAN_DELTA


def test_reject_when_grounding_regression():
    """Composite score improvement masking grounding regression → REJECT."""
    outs = [
        _mk_outcome(
            mutation_id=f"m-{i}",
            delta=0.10,
            accepted=True,
            # Composite up but grounding tanked
            grounding=0.50,
        )
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert len(v.sub_metric_regressions) > 0
    assert any("grounding" in r for r in v.sub_metric_regressions)


def test_reject_when_sector_vocab_diverges_from_rubric():
    """Sector-vocab lagging rubric by 0.10+ on accepted mutations → REJECT."""
    outs = [
        _mk_outcome(
            mutation_id=f"m-{i}",
            delta=0.10,
            accepted=True,
            rubric=0.90,
            sector_vocab=0.55,  # 0.35 below rubric
        )
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    assert v.decision == "reject"
    assert any("sector_vocab" in r for r in v.sub_metric_regressions)


def test_median_computed():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=float(i) / 100, accepted=False)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    # Deltas are 0.00..0.19; median of 20 values is mean of 9th and 10th
    assert abs(v.median_delta - 0.095) < 0.001


def test_renders_markdown_with_decision_and_metrics():
    outs = [
        _mk_outcome(
            mutation_id=f"m-{i}",
            delta=0.10,
            accepted=True,
            mutation_rationale="tighten citations" if i == 0 else "",
            parent_baseline_id="baseline-1" if i == 0 else None,
            proposed_at="2026-07-01T00:00:00Z" if i == 0 else "",
        )
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    md = render_verdict_markdown(v)
    assert "# Autoresearch Wedge 1 verdict — `synthesizer` (§15.6)" in md
    assert "**Decision:** `ratify`" in md
    assert "## Summary" in md
    assert "- Accepted mutations: **20**" in md
    assert "- Rejected mutations: **0**" in md
    assert "Best mutation rationale: tighten citations" in md
    assert "Best mutation parent baseline: `baseline-1`" in md
    assert "Best mutation proposed at: `2026-07-01T00:00:00Z`" in md
    assert "## Next steps" in md
    assert "Wedges 2-4 unlock" in md


def test_render_verdict_rejects_invalid_decision():
    verdict = Verdict(
        role="synthesizer",
        decision="maybe",
        iteration_count=20,
        acceptance_rate=1.0,
        mean_delta=0.10,
        median_delta=0.10,
        best_mutation_id="m-0",
        best_mutation_delta=0.10,
        total_cost_usd=1.0,
        rationale="invalid decision",
        sub_metric_regressions=[],
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "verdict decision must be one of" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected invalid verdict decision to be rejected")


def test_render_verdict_rejects_malformed_best_mutation_provenance():
    verdict = Verdict(
        role="synthesizer",
        decision="ratify",
        iteration_count=20,
        acceptance_rate=1.0,
        mean_delta=0.10,
        median_delta=0.10,
        best_mutation_id="m-0",
        best_mutation_delta=0.10,
        total_cost_usd=1.0,
        rationale="valid rationale",
        sub_metric_regressions=[],
        accepted_count=20,
        rejected_count=0,
        best_mutation_parent_baseline_id=123,  # type: ignore[arg-type]
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "best_mutation_parent_baseline_id must be a string when present" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected malformed best-mutation provenance to be rejected")


def test_render_verdict_rejects_impossible_mutation_counts():
    verdict = Verdict(
        role="synthesizer",
        decision="ratify",
        iteration_count=20,
        acceptance_rate=1.0,
        mean_delta=0.10,
        median_delta=0.10,
        best_mutation_id="m-0",
        best_mutation_delta=0.10,
        total_cost_usd=1.0,
        rationale="valid rationale",
        sub_metric_regressions=[],
        accepted_count=19,
        rejected_count=0,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "accepted_count + rejected_count must equal iteration_count" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected impossible mutation counts to be rejected")


def test_render_verdict_rejects_acceptance_rate_that_disagrees_with_counts():
    verdict = Verdict(
        role="synthesizer",
        decision="ratify",
        iteration_count=20,
        acceptance_rate=1.0,
        mean_delta=0.10,
        median_delta=0.10,
        best_mutation_id="m-0",
        best_mutation_delta=0.10,
        total_cost_usd=1.0,
        rationale="valid rationale",
        sub_metric_regressions=[],
        accepted_count=10,
        rejected_count=10,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "acceptance_rate must equal accepted_count / iteration_count" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected inconsistent acceptance rate to be rejected")


def test_render_verdict_rejects_best_mutation_on_zero_iterations():
    verdict = Verdict(
        role="synthesizer",
        decision="insufficient_data",
        iteration_count=0,
        acceptance_rate=0.0,
        mean_delta=0.0,
        median_delta=0.0,
        best_mutation_id="m-impossible",
        best_mutation_delta=0.0,
        total_cost_usd=0.0,
        rationale="no data",
        sub_metric_regressions=[],
        accepted_count=0,
        rejected_count=0,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "best_mutation_id must be absent when iteration_count is zero" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected zero-iteration best mutation to be rejected")


def test_render_verdict_rejects_missing_best_mutation_on_positive_iterations():
    verdict = Verdict(
        role="synthesizer",
        decision="reject",
        iteration_count=1,
        acceptance_rate=0.0,
        mean_delta=-0.10,
        median_delta=-0.10,
        best_mutation_id=None,
        best_mutation_delta=-0.10,
        total_cost_usd=0.05,
        rationale="one failed mutation",
        sub_metric_regressions=[],
        accepted_count=0,
        rejected_count=1,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "best_mutation_id must be present when iteration_count is positive" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected missing positive-iteration best mutation to be rejected")


def test_render_verdict_rejects_ratify_below_thresholds():
    verdict = Verdict(
        role="synthesizer",
        decision="ratify",
        iteration_count=20,
        acceptance_rate=0.20,
        mean_delta=0.10,
        median_delta=0.10,
        best_mutation_id="m-0",
        best_mutation_delta=0.10,
        total_cost_usd=1.0,
        rationale="claims ratify despite weak acceptance",
        sub_metric_regressions=[],
        accepted_count=4,
        rejected_count=16,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "ratify verdict requires acceptance_rate at least MIN_ACCEPTANCE_RATE" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected below-threshold ratify verdict to be rejected")


def test_render_verdict_rejects_full_volume_insufficient_data():
    verdict = Verdict(
        role="synthesizer",
        decision="insufficient_data",
        iteration_count=20,
        acceptance_rate=0.0,
        mean_delta=-0.10,
        median_delta=-0.10,
        best_mutation_id="m-0",
        best_mutation_delta=-0.10,
        total_cost_usd=1.0,
        rationale="claims insufficient data despite full volume",
        sub_metric_regressions=[],
        accepted_count=0,
        rejected_count=20,
    )

    try:
        render_verdict_markdown(verdict)
    except ValueError as exc:
        assert "insufficient_data verdict requires iteration_count below MIN_MUTATIONS" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected full-volume insufficient_data verdict to be rejected")


def test_render_reject_includes_regression_list():
    outs = [
        _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True, grounding=0.30)
        for i in range(MIN_MUTATIONS)
    ]
    v = compute_verdict("synthesizer", outs)
    md = render_verdict_markdown(v)
    assert "## Sub-metric regressions" in md
    assert "grounding" in md


def test_render_verdict_escapes_dynamic_inline_content():
    verdict = Verdict(
        role="synth`role\nextra",
        decision="reject",
        iteration_count=20,
        acceptance_rate=0.0,
        mean_delta=-0.10,
        median_delta=-0.10,
        best_mutation_id="m`0\nnext",
        best_mutation_delta=-0.10,
        total_cost_usd=1.0,
        rationale="# forged heading\nuse **bold** | table",
        sub_metric_regressions=["grounding | dropped\n# hidden"],
        accepted_count=0,
        rejected_count=20,
        best_mutation_rationale="tighten **citations**\nnext",
        best_mutation_parent_baseline_id="base`1",
        best_mutation_proposed_at="2026-07-01T00:00:00Z",
    )

    md = render_verdict_markdown(verdict)

    assert "# Autoresearch Wedge 1 verdict — `` synth`role extra `` (§15.6)" in md
    assert "- Best mutation: `` m`0 next ``" in md
    assert "Best mutation parent baseline: `` base`1 ``" in md
    assert "\\# forged heading use \\*\\*bold\\*\\* \\| table" in md
    assert "tighten \\*\\*citations\\*\\* next" in md
    assert "grounding \\| dropped \\# hidden" in md
    assert "\n# forged heading" not in md


def test_outcome_json_round_trips(tmp_path):
    outcome = _mk_outcome(
        mutation_id="m-roundtrip",
        delta=0.12,
        accepted=True,
        rubric=0.90,
        mutation_rationale="tighten citations",
        parent_baseline_id="baseline-1",
        proposed_at="2026-07-01T00:00:00Z",
    )
    path = tmp_path / "outcomes.json"

    write_outcomes_json(path, role="synthesizer", outcomes=[outcome])

    role, loaded = load_outcomes_json(path)
    assert role == "synthesizer"
    assert len(loaded) == 1
    assert loaded[0].mutation_id == outcome.mutation_id
    assert loaded[0].cost_usd == outcome.cost_usd
    assert loaded[0].mutation_rationale == "tighten citations"
    assert loaded[0].parent_baseline_id == "baseline-1"
    assert loaded[0].proposed_at == "2026-07-01T00:00:00Z"
    assert loaded[0].composite_breakdown.rubric == 0.90
    assert outcome_to_json(loaded[0]) == outcome_to_json(outcome)


def test_outcome_json_loads_legacy_rows_without_provenance(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload.pop("mutation_rationale", None)
    payload.pop("parent_baseline_id", None)
    payload.pop("proposed_at", None)
    path.write_text(json.dumps([payload]), encoding="utf-8")

    _, loaded = load_outcomes_json(path)

    assert loaded[0].mutation_rationale == ""
    assert loaded[0].parent_baseline_id is None
    assert loaded[0].proposed_at == ""


def test_outcome_json_rejects_malformed_provenance(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["parent_baseline_id"] = 123
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].parent_baseline_id must be a string when present" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected malformed provenance to be rejected")


def test_outcome_json_rejects_non_finite_score(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["delta"] = float("nan")
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].delta must be finite" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected non-finite delta to be rejected")


def test_outcome_json_rejects_non_finite_composite_score(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["composite_breakdown"]["grounding"] = float("inf")
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].composite_breakdown.grounding must be finite" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected non-finite grounding score to be rejected")


def test_outcome_json_rejects_out_of_range_composite_score(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["composite_breakdown"]["total"] = 1.2
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].composite_breakdown.total must be in [0, 1]" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected out-of-range total score to be rejected")


def test_outcome_json_rejects_negative_epsilon(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["epsilon_required"] = -0.01
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].epsilon_required must be non-negative" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected negative epsilon to be rejected")


def test_outcome_json_rejects_delta_that_does_not_match_scores(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["baseline_score"] = 0.70
    payload["candidate_score"] = 0.71
    payload["delta"] = 0.20
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].delta must equal candidate_score - baseline_score" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected inconsistent delta to be rejected")


def test_outcome_json_rejects_accepted_flag_that_does_not_match_epsilon(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["baseline_score"] = 0.70
    payload["candidate_score"] = 0.75
    payload["delta"] = 0.05
    payload["epsilon_required"] = 0.05
    payload["accepted"] = True
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].accepted must equal delta > epsilon_required" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected inconsistent accepted flag to be rejected")


def test_outcome_json_rejects_non_finite_cost(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["cost_usd"] = "NaN"
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].cost_usd must be finite" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected non-finite cost to be rejected")


def test_outcome_json_rejects_negative_cost(tmp_path):
    path = tmp_path / "outcomes.json"
    payload = _outcome_json()
    payload["cost_usd"] = "-0.01"
    path.write_text(json.dumps([payload]), encoding="utf-8")

    try:
        load_outcomes_json(path)
    except ValueError as exc:
        assert "outcomes[0].cost_usd must be non-negative" in str(exc)
    else:  # pragma: no cover - defensive assertion path
        raise AssertionError("expected negative cost to be rejected")


def _outcome_json(mutation_id: str = "m-0") -> dict:
    return {
        "mutation_id": mutation_id,
        "accepted": True,
        "baseline_score": 0.70,
        "candidate_score": 0.80,
        "delta": 0.10,
        "epsilon_required": 0.05,
        "composite_breakdown": {
            "rubric": 0.85,
            "voice_style": 0.85,
            "sector_vocab": 0.85,
            "grounding": 0.90,
            "total": 0.80,
        },
        "cost_usd": "0.05",
        "mutation_rationale": "test mutation",
        "parent_baseline_id": "baseline-0",
        "proposed_at": "2026-07-01T00:00:00Z",
    }


def test_verdict_cli_writes_markdown_from_json(tmp_path):
    from tools.prompt_autoresearch.verdict_cli import main

    outcomes_path = tmp_path / "outcomes.json"
    output_path = tmp_path / "verdict.md"
    write_outcomes_json(
        outcomes_path,
        role="synthesizer",
        outcomes=[
            _mk_outcome(mutation_id=f"m-{i}", delta=0.10, accepted=True)
            for i in range(MIN_MUTATIONS)
        ],
    )

    rc = main(["--outcomes", str(outcomes_path), "--output", str(output_path)])

    assert rc == 0
    md = output_path.read_text(encoding="utf-8")
    assert "# Autoresearch Wedge 1 verdict — `synthesizer` (§15.6)" in md
    assert "**Decision:** `ratify`" in md


def test_verdict_cli_requires_role_when_json_is_bare_array(tmp_path, capsys):
    from tools.prompt_autoresearch.verdict_cli import main

    outcomes_path = tmp_path / "outcomes.json"
    outcomes_path.write_text(json.dumps([_outcome_json()]), encoding="utf-8")

    rc = main(["--outcomes", str(outcomes_path)])

    assert rc == 2
    assert "--role is required" in capsys.readouterr().err


def test_verdict_cli_rejects_missing_outcomes_file(tmp_path, capsys):
    from tools.prompt_autoresearch.verdict_cli import main

    missing = tmp_path / "missing.json"

    rc = main(["--role", "synthesizer", "--outcomes", str(missing)])

    assert rc == 2
    assert f"could not read outcomes JSON: {missing}" in capsys.readouterr().err


def test_verdict_cli_rejects_malformed_outcomes_json(tmp_path, capsys):
    from tools.prompt_autoresearch.verdict_cli import main

    outcomes_path = tmp_path / "malformed.json"
    outcomes_path.write_text("{not-json", encoding="utf-8")

    rc = main(["--role", "synthesizer", "--outcomes", str(outcomes_path)])

    assert rc == 2
    assert f"outcomes JSON is malformed: {outcomes_path}" in capsys.readouterr().err
