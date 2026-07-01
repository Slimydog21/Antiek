"""Read-only Loop 3 evidence status.

The persistent checklist is an operator annotation surface. This module runs
the committed evidence verifiers behind ``docs/loop_3_unlock_criteria.md`` so
the API can show whether the artifacts actually satisfy the five gates.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from compounding.verification.eval_headroom import audit_eval_headroom
from compounding.verification.open_weight_justification import (
    audit_open_weight_justification,
)
from compounding.verification.reward_signal import audit_reward_signal
from compounding.verification.sft_readiness import audit_sft_readiness
from compounding.verification.trajectory_volume import (
    audit_trajectory_volume,
    load_open_weight_policy_ids,
)

from .unlock_gate import Loop3UnlockCriterion

DEFAULT_EVENTS_DIR = Path("~/.antiek/research_events")
DEFAULT_OPEN_WEIGHT_POLICY_FILE = Path("reports/loop3/open-weight-policy-ids.json")


@dataclass(frozen=True)
class CriterionEvidenceStatus:
    criterion: str
    status: str
    passed: bool
    summary: str
    result: dict[str, Any]


@dataclass(frozen=True)
class Loop3EvidenceSnapshot:
    criteria: dict[str, bool]
    statuses: dict[str, CriterionEvidenceStatus]
    all_evidence_passed: bool
    events_dir: str
    open_weight_policy_file: str


def _events_dir() -> Path:
    return Path(os.environ.get("ANTIEK_LOOP3_EVENTS_DIR", str(DEFAULT_EVENTS_DIR)))


def _open_weight_policy_file() -> Path:
    return Path(
        os.environ.get(
            "ANTIEK_LOOP3_OPEN_WEIGHT_POLICY_FILE",
            str(DEFAULT_OPEN_WEIGHT_POLICY_FILE),
        )
    )


def _first_failed_check(result: dict[str, Any]) -> str:
    checks = result.get("checks")
    if not isinstance(checks, list):
        return "no check details"
    for check in checks:
        if isinstance(check, dict) and not check.get("passed"):
            name = check.get("name", "<unknown>")
            detail = check.get("detail", "")
            return f"{name}: {detail}"
    return "all checks passed"


def _run(
    criterion: Loop3UnlockCriterion,
    fn: Callable[[], Any],
) -> CriterionEvidenceStatus:
    try:
        audit = fn()
        result = asdict(audit)
        status = str(result.get("status", "ERROR"))
        passed = status == "PASS"
        summary = "all checks passed" if passed else _first_failed_check(result)
        return CriterionEvidenceStatus(
            criterion=criterion.value,
            status=status,
            passed=passed,
            summary=summary,
            result=result,
        )
    except Exception as exc:
        return CriterionEvidenceStatus(
            criterion=criterion.value,
            status="ERROR",
            passed=False,
            summary=f"{type(exc).__name__}: {exc}",
            result={"status": "ERROR", "error": f"{type(exc).__name__}: {exc}"},
        )


def snapshot() -> Loop3EvidenceSnapshot:
    """Run all five evidence audits with production defaults.

    This is intentionally read-only and does not mutate the persistent checklist
    or authorize training. It lets operator surfaces compare manual state with
    current artifact evidence.
    """

    events_dir = _events_dir()
    policy_file = _open_weight_policy_file()

    def trajectory_volume() -> Any:
        policy_ids = (
            load_open_weight_policy_ids([policy_file])
            if policy_file.expanduser().is_file()
            else set()
        )
        return audit_trajectory_volume(
            events_dir=events_dir,
            open_weight_policy_ids=policy_ids,
        )

    statuses = {
        Loop3UnlockCriterion.TRAJECTORY_VOLUME.value: _run(
            Loop3UnlockCriterion.TRAJECTORY_VOLUME,
            trajectory_volume,
        ),
        Loop3UnlockCriterion.SFT_READINESS.value: _run(
            Loop3UnlockCriterion.SFT_READINESS,
            audit_sft_readiness,
        ),
        Loop3UnlockCriterion.VALIDATED_REWARD.value: _run(
            Loop3UnlockCriterion.VALIDATED_REWARD,
            lambda: audit_reward_signal(events_dir=events_dir),
        ),
        Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION.value: _run(
            Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION,
            audit_open_weight_justification,
        ),
        Loop3UnlockCriterion.EVAL_HEADROOM.value: _run(
            Loop3UnlockCriterion.EVAL_HEADROOM,
            audit_eval_headroom,
        ),
    }
    criteria = {
        criterion.value: statuses[criterion.value].passed
        for criterion in Loop3UnlockCriterion
    }
    return Loop3EvidenceSnapshot(
        criteria=criteria,
        statuses=statuses,
        all_evidence_passed=all(criteria.values()),
        events_dir=str(events_dir.expanduser().resolve()),
        open_weight_policy_file=str(policy_file.expanduser().resolve()),
    )


__all__ = [
    "CriterionEvidenceStatus",
    "Loop3EvidenceSnapshot",
    "snapshot",
]
