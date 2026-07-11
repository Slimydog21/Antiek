"""Competition deep research gap matrix (pure, advisory).

Operator-supplied competitor technical decisions only — never invents
competitor claims or scrapes. backlog_mutated is always False.
"""

from __future__ import annotations

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

VALID_STATUS = frozenset({"ahead", "parity", "behind", "unknown"})


class CompetitionDeepResearchGapError(ValueError):
    """Fail-closed validation for competition gap matrix."""


@dataclass(frozen=True)
class CompetitorDecision:
    competitor: str
    area: DecisionArea
    decision_summary: str
    antiek_status: GapStatus
    residual: str | None


@dataclass(frozen=True)
class CompetitionGapMatrix:
    decisions: tuple[CompetitorDecision, ...]
    behind_count: int
    unknown_count: int
    parity_count: int
    ahead_count: int
    residuals: tuple[str, ...]
    backlog_mutated: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decisions": [
                {
                    "competitor": d.competitor,
                    "area": d.area,
                    "decision_summary": d.decision_summary,
                    "antiek_status": d.antiek_status,
                    **({"residual": d.residual} if d.residual is not None else {}),
                }
                for d in self.decisions
            ],
            "behind_count": self.behind_count,
            "unknown_count": self.unknown_count,
            "parity_count": self.parity_count,
            "ahead_count": self.ahead_count,
            "residuals": list(self.residuals),
            "backlog_mutated": False,
            "notes": list(self.notes),
            "authority": "competition_deep_research_gap_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CompetitionDeepResearchGapError(f"{field} must be a non-empty string")
    return value.strip()


def build_competition_deep_research_gap(
    *,
    decisions: object,
    focus_areas: object | None = None,
) -> CompetitionGapMatrix:
    """Build gap matrix from operator-supplied competitor decision records."""
    if not isinstance(decisions, list):
        raise CompetitionDeepResearchGapError("decisions must be an array")

    notes: list[str] = [
        "backlog_mutated=false — advisory gap matrix only",
        "competitor decisions are caller-supplied only (no invent / no scrape)",
    ]

    focus: set[str] | None = None
    if focus_areas is not None:
        if not isinstance(focus_areas, list):
            raise CompetitionDeepResearchGapError(
                "focus_areas must be an array when set"
            )
        focus = set()
        for i, a in enumerate(focus_areas):
            if a not in VALID_AREAS:
                raise CompetitionDeepResearchGapError(
                    f"focus_areas[{i}] invalid DecisionArea"
                )
            focus.add(a)

    rows: list[CompetitorDecision] = []
    behind_count = 0
    unknown_count = 0
    parity_count = 0
    ahead_count = 0
    residuals: list[str] = []

    for i, d in enumerate(decisions):
        if not isinstance(d, dict):
            raise CompetitionDeepResearchGapError(f"decisions[{i}] must be an object")
        competitor = _require_nonempty(
            d.get("competitor"), field=f"decisions[{i}].competitor"
        )
        area = d.get("area")
        if area not in VALID_AREAS:
            raise CompetitionDeepResearchGapError(
                f"decisions[{i}].area invalid DecisionArea"
            )
        if focus is not None and area not in focus:
            continue
        decision_summary = _require_nonempty(
            d.get("decision_summary"),
            field=f"decisions[{i}].decision_summary",
        )
        status = d.get("antiek_status")
        if status not in VALID_STATUS:
            raise CompetitionDeepResearchGapError(
                f"decisions[{i}].antiek_status must be ahead|parity|behind|unknown"
            )
        residual_raw = d.get("residual")
        residual: str | None
        if residual_raw is None:
            residual = None
        elif isinstance(residual_raw, str) and residual_raw.strip():
            residual = residual_raw.strip()
        else:
            raise CompetitionDeepResearchGapError(
                f"decisions[{i}].residual must be non-empty string when set"
            )

        rows.append(
            CompetitorDecision(
                competitor=competitor,
                area=area,  # type: ignore[arg-type]
                decision_summary=decision_summary,
                antiek_status=status,  # type: ignore[arg-type]
                residual=residual,
            )
        )

        if status == "behind":
            behind_count += 1
            if residual:
                residuals.append(residual)
            else:
                residuals.append(
                    f"[{area}] {competitor}: gap recorded without residual text"
                )
        elif status == "unknown":
            unknown_count += 1
        elif status == "parity":
            parity_count += 1
        else:
            ahead_count += 1

    if len(decisions) == 0:
        notes.append("no decisions supplied — empty matrix (no invent competitors)")
    notes.append(
        f"counts ahead={ahead_count} parity={parity_count} "
        f"behind={behind_count} unknown={unknown_count}"
    )
    notes.append("backlog_mutated=false")

    return CompetitionGapMatrix(
        decisions=tuple(rows),
        behind_count=behind_count,
        unknown_count=unknown_count,
        parity_count=parity_count,
        ahead_count=ahead_count,
        residuals=tuple(residuals),
        backlog_mutated=False,
        notes=tuple(notes),
        authority="competition_deep_research_gap_advisory",
    )


__all__ = [
    "CompetitionDeepResearchGapError",
    "CompetitionGapMatrix",
    "CompetitorDecision",
    "build_competition_deep_research_gap",
]
