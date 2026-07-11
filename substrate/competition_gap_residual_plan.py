"""Competition gap → residual execution plan (pure, advisory).

Turns operator-supplied gap decisions into an ordered residual plan for
future agents. backlog_mutated is always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal

DecisionArea = Literal[
    "source_acquisition",
    "citation_grounding",
    "multi_agent_orchestration",
    "budget_controls",
    "html_native_reading",
    "model_routing",
    "evaluation_harness",
    "unattended_swarm",
]

GapStatus = Literal["ahead", "parity", "behind", "unknown"]
ResidualPriority = Literal["P0", "P1", "P2", "P3"]

VALID_AREAS = frozenset(
    {
        "source_acquisition",
        "citation_grounding",
        "multi_agent_orchestration",
        "budget_controls",
        "html_native_reading",
        "model_routing",
        "evaluation_harness",
        "unattended_swarm",
    }
)

PRIORITY_BY_STATUS: dict[str, ResidualPriority | None] = {
    "behind": "P0",
    "unknown": "P1",
    "parity": None,
    "ahead": None,
}


class CompetitionGapResidualPlanError(ValueError):
    """Fail-closed validation for residual plan."""


@dataclass(frozen=True)
class ResidualPlanItem:
    residual_id: str
    area: str
    competitor: str
    residual_text: str
    antiek_status: str
    priority: ResidualPriority
    execution_hint: str


@dataclass(frozen=True)
class CompetitionGapResidualPlan:
    items: tuple[ResidualPlanItem, ...]
    item_count: int
    p0_count: int
    behind_planned: int
    unknown_planned: int
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [
                {
                    "residual_id": it.residual_id,
                    "area": it.area,
                    "competitor": it.competitor,
                    "residual_text": it.residual_text,
                    "antiek_status": it.antiek_status,
                    "priority": it.priority,
                    "execution_hint": it.execution_hint,
                }
                for it in self.items
            ],
            "item_count": self.item_count,
            "p0_count": self.p0_count,
            "behind_planned": self.behind_planned,
            "unknown_planned": self.unknown_planned,
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "competition_gap_residual_plan_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionGapResidualPlanError(f"{field} must be a non-empty string")
    return value.strip()


def _hint_for(area: str, status: str) -> str:
    if status == "unknown":
        return (
            f"Investigate operator-supplied evidence for {area}; "
            "do not invent competitor claims"
        )
    hints = {
        "source_acquisition": (
            "Ship pure source pack preflight (arxiv/substack registry) without live scrape"
        ),
        "citation_grounding": "Wire citation spans into DR quality floor pure modules",
        "multi_agent_orchestration": (
            "Extend collective floating cohesive prompt + MO swarm readiness free modules"
        ),
        "budget_controls": (
            "Harden model decision + prompt projection honesty (would_exceed null)"
        ),
        "html_native_reading": "Enforce html-native view authority; PDF never primary",
        "model_routing": (
            "Keep NotDiamond advisory/shadow only; decision tree remains operator authority"
        ),
        "evaluation_harness": (
            "Extend Antiek-bench recursive rewrite + usage-learn pure surfaces"
        ),
        "unattended_swarm": (
            "Compose MO brief + readiness + price ceiling; live_execution_authorized=false"
        ),
    }
    return hints.get(
        area,
        "Free pure residual: pure module + registerable routes + red-proof tests",
    )


def build_competition_gap_residual_plan(
    *,
    decisions: object,
    max_items: object | None = None,
) -> CompetitionGapResidualPlan:
    """Build ordered residual plan. Never mutates product backlog."""
    if not isinstance(decisions, list):
        raise CompetitionGapResidualPlanError("decisions must be an array")

    max_n: int | None = None
    if max_items is not None:
        if not isinstance(max_items, (int, float)) or isinstance(max_items, bool):
            raise CompetitionGapResidualPlanError(
                "max_items must be a positive finite number when set"
            )
        # Reject NaN / ±inf before int() (OverflowError is not fail-closed).
        if not math.isfinite(float(max_items)) or not (max_items > 0):
            raise CompetitionGapResidualPlanError(
                "max_items must be a positive finite number when set"
            )
        max_n = int(max_items)

    notes: list[str] = [
        "backlog_mutated=false — residual plan is advisory only",
        "plan items derived from caller-supplied decisions only (no invent competitors)",
    ]
    items: list[ResidualPlanItem] = []
    behind_planned = 0
    unknown_planned = 0
    seq = 0

    for phase in ("behind", "unknown"):
        for i, d in enumerate(decisions):
            if not isinstance(d, dict):
                raise CompetitionGapResidualPlanError(
                    f"decisions[{i}] must be an object"
                )
            if d.get("antiek_status") != phase:
                continue
            competitor = _require_nonempty(
                d.get("competitor"), field=f"decisions[{i}].competitor"
            )
            area = d.get("area")
            if area not in VALID_AREAS:
                raise CompetitionGapResidualPlanError(
                    f"decisions[{i}].area invalid DecisionArea"
                )
            residual_raw = d.get("residual")
            if residual_raw is None:
                residual_text = (
                    f"[{area}] {competitor}: gap recorded without residual text"
                )
                notes.append(
                    f"decisions[{i}] missing residual — synthetic residual_text "
                    "only (not backlog write)"
                )
            else:
                residual_text = _require_nonempty(
                    residual_raw, field=f"decisions[{i}].residual"
                )

            priority = PRIORITY_BY_STATUS[phase]
            if priority is None:
                continue
            if max_n is not None and len(items) >= max_n:
                notes.append(
                    f"max_items={max_n} reached — remaining rows not planned"
                )
                break

            seq += 1
            items.append(
                ResidualPlanItem(
                    residual_id=f"cgrp_{seq:03d}",
                    area=area,  # type: ignore[arg-type]
                    competitor=competitor,
                    residual_text=residual_text,
                    antiek_status=phase,
                    priority=priority,
                    execution_hint=_hint_for(area, phase),  # type: ignore[arg-type]
                )
            )
            if phase == "behind":
                behind_planned += 1
            else:
                unknown_planned += 1
        if max_n is not None and len(items) >= max_n:
            break

    if not items:
        notes.append("no behind/unknown residuals — empty plan (no invent items)")
    notes.append(
        f"planned behind={behind_planned} unknown={unknown_planned} "
        f"total={len(items)}"
    )
    notes.append("backlog_mutated=false")

    return CompetitionGapResidualPlan(
        items=tuple(items),
        item_count=len(items),
        p0_count=behind_planned,
        behind_planned=behind_planned,
        unknown_planned=unknown_planned,
        backlog_mutated=False,
        notes=tuple(notes),
        authority="competition_gap_residual_plan_advisory",
    )


__all__ = [
    "CompetitionGapResidualPlan",
    "CompetitionGapResidualPlanError",
    "ResidualPlanItem",
    "build_competition_gap_residual_plan",
]
