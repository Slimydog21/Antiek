"""Candidate skill overlay helpers for Phase-8 replay.

The enforcing gate needs to compare baseline outcomes with outcomes produced
after a proposed skill patch. This module materializes the candidate skill tree
and provides the runner seam for held-out candidate backtests. It deliberately
does not choose the production investigation runner yet.
"""

from __future__ import annotations

import shutil
import tempfile
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from middleware.backtest.score import (
    DEFAULT_MIN_GRADED_OUTCOMES,
    BacktestComparison,
    compare_backtest_cohorts,
)
from middleware.backtest.types import BacktestReport
from skills.domain.auto_patch import patch_from_synthesis

CandidateBacktestRunner = Callable[[str, Path], BacktestReport]


@dataclass(frozen=True)
class CandidateSkillOverlay:
    """A temporary skill tree with one candidate synthesis patch applied."""

    baseline_skills_root: Path
    overlay_skills_root: Path
    matched_domains: tuple[str, ...]
    patched_domains: tuple[str, ...]
    skipped_domains: tuple[str, ...]
    status: str
    patch_result: dict[str, Any]


@dataclass(frozen=True)
class CandidateReplayError:
    """One held-out candidate backtest failure."""

    synthesis_id: str
    error: str


@dataclass(frozen=True)
class CandidateBacktestReplay:
    """Candidate backtest reports generated against an isolated overlay."""

    overlay: CandidateSkillOverlay
    heldout_synthesis_ids: tuple[str, ...]
    reports: tuple[BacktestReport, ...]
    errors: tuple[CandidateReplayError, ...]
    status: str

    @property
    def complete(self) -> bool:
        return self.status == "replayed"


@dataclass(frozen=True)
class CandidateReplayEvaluation:
    """Gate-facing evaluation of candidate replay output."""

    replay: CandidateBacktestReplay
    comparison: BacktestComparison
    ready_for_gate: bool
    notes: str


@dataclass(frozen=True)
class BaselineBacktestLoad:
    """Baseline held-out backtest reports loaded from the archive DB."""

    synthesis_ids: tuple[str, ...]
    reports: tuple[BacktestReport, ...]
    errors: tuple[CandidateReplayError, ...]

    @property
    def complete(self) -> bool:
        return not self.errors


def materialize_candidate_skill_overlay(
    synthesis_row: dict[str, Any],
    *,
    baseline_skills_root: Path,
    overlay_parent: Path | None = None,
) -> CandidateSkillOverlay:
    """Copy baseline skills into a temporary overlay and patch only the copy.

    The caller owns the returned directory. ``overlay_parent`` exists to make
    tests and batch replay jobs deterministic about where the temporary tree is
    placed; when omitted, the system temp directory is used.
    """

    if overlay_parent is not None:
        overlay_parent.mkdir(parents=True, exist_ok=True)
    parent_arg = str(overlay_parent) if overlay_parent is not None else None
    overlay_dir = Path(
        tempfile.mkdtemp(prefix="candidate-skill-overlay-", dir=parent_arg)
    )
    overlay_root = overlay_dir / "skills"

    if baseline_skills_root.exists():
        shutil.copytree(baseline_skills_root, overlay_root)
    else:
        overlay_root.mkdir(parents=True)

    result = patch_from_synthesis(
        synthesis_row,
        skills_root=overlay_root,
        emit_events=False,
    )

    return CandidateSkillOverlay(
        baseline_skills_root=baseline_skills_root,
        overlay_skills_root=overlay_root,
        matched_domains=tuple(result.get("matched_domains") or ()),
        patched_domains=tuple(result.get("patched") or ()),
        skipped_domains=tuple(result.get("skipped") or ()),
        status=str(result.get("status", "unknown")),
        patch_result=result,
    )


def replay_candidate_backtest_cohort(
    synthesis_row: dict[str, Any],
    *,
    heldout_synthesis_ids: Sequence[str],
    baseline_skills_root: Path,
    backtest_runner: CandidateBacktestRunner,
    overlay_parent: Path | None = None,
) -> CandidateBacktestReplay:
    """Run held-out candidate backtests against a temporary skill overlay.

    ``backtest_runner`` is the future orchestration seam: it receives a
    held-out synthesis id plus the candidate overlay skill root and returns a
    ``BacktestReport``. This helper owns isolation and error accounting, not
    the production investigation rerun mechanics.
    """

    overlay = materialize_candidate_skill_overlay(
        synthesis_row,
        baseline_skills_root=baseline_skills_root,
        overlay_parent=overlay_parent,
    )
    heldout_ids = tuple(heldout_synthesis_ids)
    if not heldout_ids:
        return CandidateBacktestReplay(
            overlay=overlay,
            heldout_synthesis_ids=heldout_ids,
            reports=(),
            errors=(),
            status="no_heldout",
        )

    reports: list[BacktestReport] = []
    errors: list[CandidateReplayError] = []
    for synthesis_id in heldout_ids:
        try:
            reports.append(backtest_runner(synthesis_id, overlay.overlay_skills_root))
        except Exception as exc:
            errors.append(
                CandidateReplayError(
                    synthesis_id=synthesis_id,
                    error=repr(exc),
                )
            )

    if reports and not errors:
        status = "replayed"
    elif reports:
        status = "partial"
    else:
        status = "failed"

    return CandidateBacktestReplay(
        overlay=overlay,
        heldout_synthesis_ids=heldout_ids,
        reports=tuple(reports),
        errors=tuple(errors),
        status=status,
    )


def evaluate_candidate_replay_for_gate(
    *,
    baseline_reports: Sequence[BacktestReport],
    candidate_replay: CandidateBacktestReplay,
    minimum_graded_outcomes: int = DEFAULT_MIN_GRADED_OUTCOMES,
) -> CandidateReplayEvaluation:
    """Compare baseline reports against candidate replay reports for the gate."""

    comparison = compare_backtest_cohorts(
        baseline_reports=baseline_reports,
        candidate_reports=candidate_replay.reports,
        minimum_graded_outcomes=minimum_graded_outcomes,
    )
    ready_for_gate = candidate_replay.complete and comparison.ready_for_gate
    if not candidate_replay.complete:
        failed_details = ", ".join(
            f"{error.synthesis_id}: {error.error}"
            for error in candidate_replay.errors
        )
        if failed_details:
            notes = (
                f"candidate replay not complete: status={candidate_replay.status}; "
                f"failed={failed_details}; {comparison.notes}"
            )
        else:
            notes = (
                f"candidate replay not complete: status={candidate_replay.status}; "
                f"{comparison.notes}"
            )
    elif not comparison.ready_for_gate:
        notes = comparison.notes
    else:
        notes = f"candidate replay ready: {comparison.notes}"

    return CandidateReplayEvaluation(
        replay=candidate_replay,
        comparison=comparison,
        ready_for_gate=ready_for_gate,
        notes=notes,
    )


def load_baseline_backtest_reports(
    *,
    db_path: Path,
    synthesis_ids: Sequence[str],
) -> BaselineBacktestLoad:
    """Load archived baseline backtest reports for held-out synthesis ids."""

    import duckdb

    from middleware.backtest import backtest

    ids = tuple(synthesis_ids)
    reports: list[BacktestReport] = []
    errors: list[CandidateReplayError] = []
    con = duckdb.connect(str(db_path), read_only=True)
    try:
        for synthesis_id in ids:
            try:
                reports.append(backtest(con, synthesis_id))
            except Exception as exc:
                errors.append(
                    CandidateReplayError(
                        synthesis_id=synthesis_id,
                        error=repr(exc),
                    )
                )
    finally:
        con.close()

    return BaselineBacktestLoad(
        synthesis_ids=ids,
        reports=tuple(reports),
        errors=tuple(errors),
    )


def unavailable_candidate_replay_evaluation(
    synthesis_row: dict[str, Any],
    *,
    heldout_synthesis_ids: Sequence[str],
    baseline_skills_root: Path,
    reason: str,
    baseline_reports: Sequence[BacktestReport] = (),
    overlay_parent: Path | None = None,
    minimum_graded_outcomes: int = DEFAULT_MIN_GRADED_OUTCOMES,
) -> CandidateReplayEvaluation:
    """Materialize the overlay and return a fail-closed replay evaluation.

    This is the production contract while the real held-out investigation
    rerunner is absent: configured replay requests become visible gate evidence
    instead of silently collapsing back to anonymous zero scores.
    """

    overlay = materialize_candidate_skill_overlay(
        synthesis_row,
        baseline_skills_root=baseline_skills_root,
        overlay_parent=overlay_parent,
    )
    heldout_ids = tuple(heldout_synthesis_ids)
    replay = CandidateBacktestReplay(
        overlay=overlay,
        heldout_synthesis_ids=heldout_ids,
        reports=(),
        errors=tuple(
            CandidateReplayError(synthesis_id=synthesis_id, error=reason)
            for synthesis_id in heldout_ids
        ),
        status="runner_unavailable" if heldout_ids else "no_heldout",
    )
    return evaluate_candidate_replay_for_gate(
        baseline_reports=baseline_reports,
        candidate_replay=replay,
        minimum_graded_outcomes=minimum_graded_outcomes,
    )
