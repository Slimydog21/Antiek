"""Deep research quality + budget gate compose (pure).

live_dispatch_authorized always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class DeepResearchQualityBudgetGateComposeError(ValueError):
    """Fail-closed validation for DR quality+budget gate."""


@dataclass(frozen=True)
class DeepResearchQualityBudgetGateCompose:
    session_id: str
    quality_ready: bool
    budget_ready: bool
    citation_ready: bool
    gate_ready: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "quality_ready": self.quality_ready,
            "budget_ready": self.budget_ready,
            "citation_ready": self.citation_ready,
            "gate_ready": self.gate_ready,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "deep_research_quality_budget_gate_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeepResearchQualityBudgetGateComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_deep_research_quality_budget_gate(
    *,
    session_id: object,
    quality_overall: object,
    would_exceed: object,
    operator_ack: object,
    quality_floor: object | None = None,
    operator_override: object | None = None,
    citation_pack_ready: object | None = None,
) -> DeepResearchQualityBudgetGateCompose:
    """Compose quality+budget gate. Never authorizes live dispatch."""
    if not isinstance(operator_ack, bool):
        raise DeepResearchQualityBudgetGateComposeError(
            "operator_ack must be an explicit boolean"
        )
    sid = _require_nonempty(session_id, field="session_id")
    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise DeepResearchQualityBudgetGateComposeError(
            "would_exceed must be boolean or null"
        )
    override = False if operator_override is None else operator_override
    if not isinstance(override, bool):
        raise DeepResearchQualityBudgetGateComposeError(
            "operator_override must be boolean when set"
        )

    notes: list[str] = [
        "live_dispatch_authorized=false — quality/budget gate is advisory only",
    ]

    floor = 0.5 if quality_floor is None else quality_floor
    if not isinstance(floor, (int, float)) or isinstance(floor, bool):
        raise DeepResearchQualityBudgetGateComposeError(
            "quality_floor must be a finite number in [0,1]"
        )
    floor_f = float(floor)
    if floor_f != floor_f or floor_f < 0.0 or floor_f > 1.0:
        raise DeepResearchQualityBudgetGateComposeError(
            "quality_floor must be a finite number in [0,1]"
        )

    quality_ready = False
    if quality_overall is None:
        notes.append(
            "quality_ready=false — quality_overall unknown (null honesty)"
        )
    elif not isinstance(quality_overall, (int, float)) or isinstance(
        quality_overall, bool
    ):
        raise DeepResearchQualityBudgetGateComposeError(
            "quality_overall must be number or null"
        )
    else:
        q = float(quality_overall)
        if q != q or q < 0.0 or q > 1.0:
            raise DeepResearchQualityBudgetGateComposeError(
                "quality_overall must be in [0,1]"
            )
        quality_ready = q >= floor_f
        notes.append(
            f"quality_ready=true · overall={q} floor={floor_f}"
            if quality_ready
            else f"quality_ready=false · overall={q} < floor={floor_f}"
        )

    budget_ready = False
    if would_exceed is None:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override (would_exceed unknown)"
            )
        else:
            notes.append(
                "budget_ready=false — would_exceed unknown and no operator_override"
            )
    elif would_exceed is True:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override despite would_exceed=true"
            )
        else:
            notes.append("budget_ready=false — would_exceed=true")
    else:
        budget_ready = True
        notes.append("budget_ready=true — would_exceed=false")

    citation_ready = True
    if citation_pack_ready is not None:
        if not isinstance(citation_pack_ready, bool):
            raise DeepResearchQualityBudgetGateComposeError(
                "citation_pack_ready must be boolean when set"
            )
        citation_ready = citation_pack_ready
        notes.append(
            "citation_ready=true"
            if citation_ready
            else "citation_ready=false — citation pack not ready"
        )

    gate_ready = (
        operator_ack and quality_ready and budget_ready and citation_ready
    )
    if not operator_ack:
        notes.append("gate_ready=false — operator_ack required")
    elif not gate_ready:
        notes.append("gate_ready=false — quality/budget/citation gates closed")
    else:
        notes.append(
            "gate_ready=true — DR may proceed subject to live dispatch authorization elsewhere"
        )
    notes.append("live_dispatch_authorized=false")

    return DeepResearchQualityBudgetGateCompose(
        session_id=sid,
        quality_ready=quality_ready,
        budget_ready=budget_ready,
        citation_ready=citation_ready,
        gate_ready=gate_ready,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="deep_research_quality_budget_gate_compose_advisory",
    )


__all__ = [
    "DeepResearchQualityBudgetGateCompose",
    "DeepResearchQualityBudgetGateComposeError",
    "compose_deep_research_quality_budget_gate",
]
