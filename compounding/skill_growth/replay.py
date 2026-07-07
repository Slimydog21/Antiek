"""Candidate skill overlay helpers for Phase-8 replay.

The enforcing gate needs to compare baseline outcomes with outcomes produced
after a proposed skill patch. This module only materializes the candidate skill
tree. It deliberately does not run investigations or score backtests yet.
"""

from __future__ import annotations

import shutil
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from skills.domain.auto_patch import patch_from_synthesis


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
