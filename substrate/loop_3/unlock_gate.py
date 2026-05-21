"""Loop 3 unlock-criteria gate (docs/loop_3_unlock_criteria.md)."""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass, field
from typing import Optional


class Loop3UnlockCriterion(str, enum.Enum):
    """The five criteria from `docs/loop_3_unlock_criteria.md`."""

    TRAJECTORY_VOLUME = "trajectory_volume"
    SFT_READINESS = "sft_readiness"
    VALIDATED_REWARD = "validated_reward"
    OPEN_WEIGHT_JUSTIFICATION = "open_weight_justification"
    EVAL_HEADROOM = "eval_headroom"


ALL_CRITERIA: tuple[Loop3UnlockCriterion, ...] = tuple(Loop3UnlockCriterion)


class Loop3UnlockRequired(Exception):
    """Raised when a Loop 3 operation is attempted without unlock.

    Per master-spec §14.2 parallel-track discipline + §15.6 Lutke gap:
    'No work happens until trajectory volume + SFT readiness +
    validated reward + open-weight justification + eval headroom are
    all checked.'

    Operator-set ANTIEK_LOOP3_UNLOCKED=1 in env to ratify."""


@dataclass
class UnlockChecklist:
    """Operator's progress against the 5 criteria. Tracked
    substrate-side for the Trust Center surface (§13.7); the
    unlock-env gate is the authoritative one."""

    trajectory_volume: bool = False
    sft_readiness: bool = False
    validated_reward: bool = False
    open_weight_justification: bool = False
    eval_headroom: bool = False
    notes: dict = field(default_factory=dict)

    def all_met(self) -> bool:
        return all([
            self.trajectory_volume,
            self.sft_readiness,
            self.validated_reward,
            self.open_weight_justification,
            self.eval_headroom,
        ])

    def remaining(self) -> list[Loop3UnlockCriterion]:
        out: list[Loop3UnlockCriterion] = []
        if not self.trajectory_volume:
            out.append(Loop3UnlockCriterion.TRAJECTORY_VOLUME)
        if not self.sft_readiness:
            out.append(Loop3UnlockCriterion.SFT_READINESS)
        if not self.validated_reward:
            out.append(Loop3UnlockCriterion.VALIDATED_REWARD)
        if not self.open_weight_justification:
            out.append(Loop3UnlockCriterion.OPEN_WEIGHT_JUSTIFICATION)
        if not self.eval_headroom:
            out.append(Loop3UnlockCriterion.EVAL_HEADROOM)
        return out


def check_unlocked() -> None:
    """Refuse to proceed unless ANTIEK_LOOP3_UNLOCKED=1.

    The env-var gate is intentional: even with all 5 checklist
    items marked met, the operator must explicitly flip the env to
    1 to authorize training-time work. This separates 'criteria
    technically satisfied' from 'operator authorizes training' —
    they are NOT the same decision."""
    if os.environ.get("ANTIEK_LOOP3_UNLOCKED", "") != "1":
        raise Loop3UnlockRequired(
            "Loop 3 training-time work requires explicit operator "
            "ratification. Per docs/loop_3_unlock_criteria.md all 5 "
            "criteria must be met, AND operator must set "
            "ANTIEK_LOOP3_UNLOCKED=1 in env to authorize. Per master- "
            "spec §14.2: 'No work on Loop 3 unlock criteria until "
            "the criteria themselves pass.'"
        )
