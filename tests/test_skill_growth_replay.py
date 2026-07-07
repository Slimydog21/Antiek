from __future__ import annotations

from pathlib import Path

from compounding.skill_growth import (
    materialize_candidate_skill_overlay,
    replay_candidate_backtest_cohort,
)
from middleware.backtest import BacktestReport
from skills.domain.auto_patch import SECTION_MARKER
from substrate.event_log import trajectory


def _synthesis(synthesis_id: str = "syn-overlay") -> dict:
    return {
        "synthesis_id": synthesis_id,
        "investigation_id": "inv-overlay",
        "target_question": "Will PsiQuantum need fault-tolerant photonic qubits?",
        "implicit_recommendation": "conditional",
        "thesis": {
            "thesis_summary": "Photonic qubit progress depends on logical qubit scaling.",
            "thesis_components": [
                {"claim": "Fault tolerance is load-bearing.", "confidence": "high"},
            ],
        },
    }


def _report(synthesis_id: str) -> BacktestReport:
    return BacktestReport(
        synthesis_id=synthesis_id,
        synthesis_timestamp="2026-01-01T00:00:00Z",
        target_question="Will X work?",
        status="passed",
        implicit_recommendation="proceed",
        substrate_manifest_counts={},
        added_edges_since=0,
        superseded_edges_since=0,
        cited_edges_now_superseded=(),
        chunks_retired_downward=(),
        outcomes=({"thesis_outcomes": [{"outcome": "confirmed"}]},),
    )


def test_materialize_candidate_skill_overlay_patches_copy_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Quantum\n\n## Domain Fundamentals\n- baseline fact\n")

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    baseline_body = skill_path.read_text()
    overlay_body = (
        overlay.overlay_skills_root
        / "quantum-computing-knowledge"
        / "SKILL.md"
    ).read_text()

    assert overlay.status == "patched"
    assert overlay.matched_domains == ("quantum-computing-knowledge",)
    assert overlay.patched_domains == ("quantum-computing-knowledge",)
    assert baseline_body == "# Quantum\n\n## Domain Fundamentals\n- baseline fact\n"
    assert "<!-- synthesis_id: syn-overlay -->" in overlay_body
    assert SECTION_MARKER in overlay_body
    assert trajectory("inv-overlay") == []


def test_materialize_candidate_skill_overlay_creates_only_overlay_for_missing_baseline(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "missing-baseline"

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    assert not baseline.exists()
    assert overlay.status == "patched"
    assert (
        overlay.overlay_skills_root
        / "quantum-computing-knowledge"
        / "SKILL.md"
    ).exists()


def test_materialize_candidate_skill_overlay_preserves_idempotency(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text(
        "# Quantum\n\n"
        "## Auto-patched findings\n\n"
        "### From investigation `old`\n"
        "<!-- synthesis_id: syn-overlay -->\n"
    )

    overlay = materialize_candidate_skill_overlay(
        _synthesis(),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
    )

    assert overlay.status == "already_patched"
    assert overlay.patched_domains == ()
    assert overlay.skipped_domains == ("quantum-computing-knowledge",)
    assert trajectory("inv-overlay") == []


def test_replay_candidate_backtest_cohort_runs_runner_against_overlay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Quantum\n")
    calls: list[tuple[str, Path]] = []

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        calls.append((synthesis_id, skills_root))
        assert (skills_root / "quantum-computing-knowledge" / "SKILL.md").exists()
        return _report(synthesis_id)

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=("heldout-1", "heldout-2"),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
        backtest_runner=runner,
    )

    assert replay.status == "replayed"
    assert replay.complete is True
    assert tuple(report.synthesis_id for report in replay.reports) == (
        "heldout-1",
        "heldout-2",
    )
    assert replay.errors == ()
    assert calls == [
        ("heldout-1", replay.overlay.overlay_skills_root),
        ("heldout-2", replay.overlay.overlay_skills_root),
    ]
    assert trajectory("inv-overlay") == []


def test_replay_candidate_backtest_cohort_surfaces_per_id_errors(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        if synthesis_id == "bad":
            raise RuntimeError("held-out replay failed")
        return _report(synthesis_id)

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=("ok", "bad"),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
        backtest_runner=runner,
    )

    assert replay.status == "partial"
    assert replay.complete is False
    assert tuple(report.synthesis_id for report in replay.reports) == ("ok",)
    assert len(replay.errors) == 1
    assert replay.errors[0].synthesis_id == "bad"
    assert "held-out replay failed" in replay.errors[0].error


def test_replay_candidate_backtest_cohort_requires_heldout_ids(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        raise AssertionError("runner should not be called")

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=(),
        baseline_skills_root=tmp_path / "baseline-skills",
        overlay_parent=tmp_path,
        backtest_runner=runner,
    )

    assert replay.status == "no_heldout"
    assert replay.reports == ()
    assert replay.errors == ()
