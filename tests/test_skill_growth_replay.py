from __future__ import annotations

import os
from pathlib import Path

from compounding.skill_growth import (
    evaluate_candidate_replay_for_gate,
    load_baseline_backtest_reports,
    materialize_candidate_skill_overlay,
    prepare_candidate_replay_workspace,
    replay_candidate_backtest_cohort,
    unavailable_candidate_replay_evaluation,
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


def _report(
    synthesis_id: str,
    *,
    outcome: str = "confirmed",
) -> BacktestReport:
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
        outcomes=({"thesis_outcomes": [{"outcome": outcome}]},),
    )


def _seed_archived_synthesis(db_path: Path, synthesis_id: str) -> None:
    from datetime import UTC, datetime

    from middleware.archive.archive import ArchiveInputs, archive_synthesis_via_db
    from middleware.outcomes.recorder import (
        build_outcome_record,
        record_outcome_via_db,
    )
    from runtime.db_lock import connect_write
    from substrate.graph.schema import init_database_at_path

    init_database_at_path(str(db_path))
    inputs = ArchiveInputs(
        target_question="Will X work?",
        synthesis_timestamp=datetime.now(UTC),
        status="passed",
        implicit_recommendation="proceed",
        thesis_text="X works because evidence supports it.",
        model_versions={"test": "1"},
    )
    with connect_write(str(db_path), purpose="test:seed_baseline") as con:
        archive_synthesis_via_db(
            con,
            inputs,
            investigation_id=f"inv-{synthesis_id}",
            synthesis_id=synthesis_id,
        )
        record_outcome_via_db(
            con,
            build_outcome_record(
                synthesis_id=synthesis_id,
                observer="test",
                payload={"thesis_outcomes": [{"outcome": "confirmed"}]},
            ),
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


def test_prepare_candidate_replay_workspace_copies_baseline_db(tmp_path: Path) -> None:
    db_path = tmp_path / "baseline.duckdb"
    _seed_archived_synthesis(db_path, "syn-heldout-ok")

    workspace = prepare_candidate_replay_workspace(
        baseline_db_path=db_path,
        workspace_parent=tmp_path / "workspaces",
    )

    assert workspace.root.parent == tmp_path / "workspaces"
    assert workspace.copied_baseline_db is True
    assert workspace.db_path.exists()
    assert workspace.home_dir.is_dir()
    assert workspace.events_dir.is_dir()
    assert workspace.phase_log_dir.is_dir()
    assert workspace.research_dir.is_dir()
    assert workspace.research_artifacts_dir.is_dir()
    assert workspace.overlay_parent.is_dir()

    loaded = load_baseline_backtest_reports(
        db_path=workspace.db_path,
        synthesis_ids=("syn-heldout-ok",),
    )
    assert loaded.complete is True
    assert loaded.reports[0].synthesis_id == "syn-heldout-ok"


def test_replay_candidate_backtest_cohort_runs_runner_in_isolated_workspace(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(tmp_path / "prod.duckdb"))
    monkeypatch.setenv("ANTIEK_HOME", str(tmp_path / "prod-home"))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "prod-events"))
    monkeypatch.setenv("ANTIEK_RESEARCH_PHASE_LOG_DIR", str(tmp_path / "prod-phases"))
    monkeypatch.setenv("ANTIEK_RESEARCH_DIR", str(tmp_path / "prod-research"))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(tmp_path / "prod-artifacts"))
    monkeypatch.setenv("ANTIEK_KNOWLEDGE_SKILLS_DIR", str(tmp_path / "prod-skills"))

    workspace = prepare_candidate_replay_workspace(
        workspace_parent=tmp_path / "workspaces",
    )
    seen_env: list[dict[str, str | None]] = []

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        import os

        seen_env.append(
            {
                "db": os.environ.get("ANTIEK_DUCKDB_PATH"),
                "home": os.environ.get("ANTIEK_HOME"),
                "events": os.environ.get("ANTIEK_RESEARCH_EVENTS_DIR"),
                "phases": os.environ.get("ANTIEK_RESEARCH_PHASE_LOG_DIR"),
                "research": os.environ.get("ANTIEK_RESEARCH_DIR"),
                "artifacts": os.environ.get("ANTIEK_RESEARCH_ARTIFACTS_DIR"),
                "skills": os.environ.get("ANTIEK_KNOWLEDGE_SKILLS_DIR"),
            }
        )
        assert skills_root.is_relative_to(workspace.overlay_parent)
        return _report(synthesis_id)

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=("heldout-1",),
        baseline_skills_root=tmp_path / "baseline-skills",
        replay_workspace=workspace,
        backtest_runner=runner,
    )

    assert replay.status == "replayed"
    assert replay.overlay.overlay_skills_root.is_relative_to(workspace.overlay_parent)
    assert seen_env == [
        {
            "db": str(workspace.db_path),
            "home": str(workspace.home_dir),
            "events": str(workspace.events_dir),
            "phases": str(workspace.phase_log_dir),
            "research": str(workspace.research_dir),
            "artifacts": str(workspace.research_artifacts_dir),
            "skills": str(replay.overlay.overlay_skills_root),
        }
    ]
    assert os.environ["ANTIEK_DUCKDB_PATH"] == str(tmp_path / "prod.duckdb")
    assert os.environ["ANTIEK_HOME"] == str(tmp_path / "prod-home")
    assert os.environ["ANTIEK_RESEARCH_EVENTS_DIR"] == str(tmp_path / "prod-events")
    assert os.environ["ANTIEK_RESEARCH_PHASE_LOG_DIR"] == str(tmp_path / "prod-phases")
    assert os.environ["ANTIEK_RESEARCH_DIR"] == str(tmp_path / "prod-research")
    assert os.environ["ANTIEK_RESEARCH_ARTIFACTS_DIR"] == str(
        tmp_path / "prod-artifacts"
    )
    assert os.environ["ANTIEK_KNOWLEDGE_SKILLS_DIR"] == str(tmp_path / "prod-skills")


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


def test_evaluate_candidate_replay_for_gate_reports_ready_delta(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        return _report(synthesis_id, outcome="confirmed")

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=tuple(f"candidate-{i}" for i in range(3)),
        baseline_skills_root=tmp_path / "baseline-skills",
        overlay_parent=tmp_path,
        backtest_runner=runner,
    )
    baseline = tuple(
        _report(f"baseline-{i}", outcome="partially_confirmed")
        for i in range(3)
    )

    evaluation = evaluate_candidate_replay_for_gate(
        baseline_reports=baseline,
        candidate_replay=replay,
        minimum_graded_outcomes=3,
    )

    assert evaluation.ready_for_gate is True
    assert evaluation.comparison.delta == 0.5
    assert "candidate replay ready" in evaluation.notes


def test_evaluate_candidate_replay_for_gate_refuses_partial_replay(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))

    def runner(synthesis_id: str, skills_root: Path) -> BacktestReport:
        if synthesis_id == "bad":
            raise RuntimeError("candidate failed")
        return _report(synthesis_id)

    replay = replay_candidate_backtest_cohort(
        _synthesis(),
        heldout_synthesis_ids=("ok", "bad"),
        baseline_skills_root=tmp_path / "baseline-skills",
        overlay_parent=tmp_path,
        backtest_runner=runner,
    )

    evaluation = evaluate_candidate_replay_for_gate(
        baseline_reports=(_report("baseline-1"), _report("baseline-2")),
        candidate_replay=replay,
        minimum_graded_outcomes=1,
    )

    assert evaluation.ready_for_gate is False
    assert "status=partial" in evaluation.notes
    assert "failed=bad" in evaluation.notes


def test_unavailable_candidate_replay_evaluation_materializes_overlay_and_fails_closed(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    baseline = tmp_path / "baseline-skills"
    skill_path = baseline / "quantum-computing-knowledge" / "SKILL.md"
    skill_path.parent.mkdir(parents=True)
    skill_path.write_text("# Quantum\n")

    evaluation = unavailable_candidate_replay_evaluation(
        _synthesis(),
        heldout_synthesis_ids=("heldout-1", "heldout-2"),
        baseline_skills_root=baseline,
        overlay_parent=tmp_path,
        reason="production candidate replay runner is not wired",
    )

    assert evaluation.ready_for_gate is False
    assert evaluation.replay.status == "runner_unavailable"
    assert evaluation.replay.heldout_synthesis_ids == ("heldout-1", "heldout-2")
    assert tuple(error.synthesis_id for error in evaluation.replay.errors) == (
        "heldout-1",
        "heldout-2",
    )
    assert "runner_unavailable" in evaluation.notes
    assert (
        evaluation.replay.overlay.overlay_skills_root
        / "quantum-computing-knowledge"
        / "SKILL.md"
    ).exists()
    assert trajectory("inv-overlay") == []


def test_load_baseline_backtest_reports_loads_reports_and_errors(tmp_path: Path) -> None:
    db_path = tmp_path / "graph.duckdb"
    _seed_archived_synthesis(db_path, "syn-heldout-ok")

    loaded = load_baseline_backtest_reports(
        db_path=db_path,
        synthesis_ids=("syn-heldout-ok", "syn-missing"),
    )

    assert loaded.synthesis_ids == ("syn-heldout-ok", "syn-missing")
    assert loaded.complete is False
    assert tuple(report.synthesis_id for report in loaded.reports) == (
        "syn-heldout-ok",
    )
    assert loaded.reports[0].outcomes_recorded == 1
    assert len(loaded.errors) == 1
    assert loaded.errors[0].synthesis_id == "syn-missing"
    assert "synthesis_id not found" in loaded.errors[0].error
