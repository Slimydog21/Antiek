from __future__ import annotations

import json
from decimal import Decimal

from tools.ops import autoresearch_wedge1_probe
from tools.prompt_autoresearch.outcomes_io import write_outcomes_json
from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.score import CompositeScore
from tools.prompt_autoresearch.verdict import MIN_MUTATIONS, compute_verdict


class _Readiness:
    all_satisfied = True
    items = []


def _outcome(i: int, *, delta: float = 0.10, accepted: bool = True) -> PromptMutationOutcome:
    return PromptMutationOutcome(
        mutation_id=f"m-{i}",
        accepted=accepted,
        baseline_score=0.70,
        candidate_score=0.70 + delta,
        delta=delta,
        epsilon_required=0.05,
        composite_breakdown=CompositeScore(
            rubric=0.85,
            voice_style=0.85,
            sector_vocab=0.85,
            grounding=0.90,
            total=0.70 + delta,
        ),
        cost_usd=Decimal("0.05"),
    )


def _write_verdict(path, *, decision: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "# Autoresearch Wedge 1 verdict — `synthesizer` (§15.6)\n\n"
        f"**Decision:** `{decision}`\n",
        encoding="utf-8",
    )


def test_autoresearch_wedge1_probe_passes_matching_terminal_verdict(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        autoresearch_wedge1_probe,
        "audit_wedge1_readiness",
        lambda _root: _Readiness(),
    )
    outcomes = [_outcome(i) for i in range(MIN_MUTATIONS)]
    outcomes_path = tmp_path / "reports/autoresearch/synthesizer-outcomes.json"
    write_outcomes_json(outcomes_path, role="synthesizer", outcomes=outcomes)
    verdict_path = tmp_path / "docs/decisions/autoresearch-wedge-1-verdict.md"
    _write_verdict(verdict_path, decision="ratify")

    result = autoresearch_wedge1_probe.probe_autoresearch_wedge1(
        repo_root=tmp_path,
        outcomes_path=outcomes_path,
        verdict_path=verdict_path,
    )

    assert result.status == "PASS"
    assert result.computed_decision == "ratify"
    assert result.filed_decision == "ratify"
    assert result.does_not_close_oa005 is True


def test_autoresearch_wedge1_probe_fails_without_enough_mutations(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        autoresearch_wedge1_probe,
        "audit_wedge1_readiness",
        lambda _root: _Readiness(),
    )
    outcomes = [_outcome(i) for i in range(5)]
    outcomes_path = tmp_path / "outcomes.json"
    write_outcomes_json(outcomes_path, role="synthesizer", outcomes=outcomes)
    verdict_path = tmp_path / "verdict.md"
    _write_verdict(verdict_path, decision="ratify")

    result = autoresearch_wedge1_probe.probe_autoresearch_wedge1(
        repo_root=tmp_path,
        outcomes_path=outcomes_path,
        verdict_path=verdict_path,
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert result.computed_decision == "insufficient_data"
    assert checks["computed_verdict_terminal"].passed is False


def test_autoresearch_wedge1_probe_fails_mismatched_filed_decision(
    tmp_path, monkeypatch,
):
    monkeypatch.setattr(
        autoresearch_wedge1_probe,
        "audit_wedge1_readiness",
        lambda _root: _Readiness(),
    )
    outcomes = [_outcome(i, delta=-0.05, accepted=False) for i in range(MIN_MUTATIONS)]
    outcomes_path = tmp_path / "outcomes.json"
    write_outcomes_json(outcomes_path, role="synthesizer", outcomes=outcomes)
    verdict_path = tmp_path / "verdict.md"
    _write_verdict(verdict_path, decision="ratify")

    assert compute_verdict("synthesizer", outcomes).decision == "reject"
    result = autoresearch_wedge1_probe.probe_autoresearch_wedge1(
        repo_root=tmp_path,
        outcomes_path=outcomes_path,
        verdict_path=verdict_path,
    )

    checks = {check.name: check for check in result.checks}
    assert result.status == "FAIL"
    assert result.computed_decision == "reject"
    assert checks["filed_decision_matches_computed"].passed is False


def test_autoresearch_wedge1_probe_json_cli(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        autoresearch_wedge1_probe,
        "audit_wedge1_readiness",
        lambda _root: _Readiness(),
    )
    outcomes = [_outcome(i) for i in range(MIN_MUTATIONS)]
    outcomes_path = tmp_path / "outcomes.json"
    write_outcomes_json(outcomes_path, role="synthesizer", outcomes=outcomes)
    verdict_path = tmp_path / "verdict.md"
    _write_verdict(verdict_path, decision="ratify")

    exit_code = autoresearch_wedge1_probe.main([
        "--repo-root",
        str(tmp_path),
        "--outcomes",
        str(outcomes_path),
        "--verdict",
        str(verdict_path),
        "--json",
    ])

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["status"] == "PASS"
    assert payload["does_not_close_oa005"] is True
