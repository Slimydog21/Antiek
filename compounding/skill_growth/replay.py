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
