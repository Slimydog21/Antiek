"""Research launch readiness gate (pure, advisory).

Sources + quality floor + budget would_exceed honesty before deep research.
live_dispatch_authorized is always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


class ResearchLaunchReadinessError(ValueError):
    """Fail-closed validation for research launch readiness."""


@dataclass(frozen=True)
class ResearchLaunchReadinessDecision:
    session_id: str
    sources_ready: bool
    quality_ready: bool
    budget_ready: bool
    launch_ready: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "sources_ready": self.sources_ready,
            "quality_ready": self.quality_ready,
            "budget_ready": self.budget_ready,
            "launch_ready": self.launch_ready,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "research_launch_readiness_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchLaunchReadinessError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_unit(value: object, *, field: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ResearchLaunchReadinessError(f"{field} must be a finite number")
    v = float(value)
    if v != v or v == float("inf") or v == float("-inf"):
        raise ResearchLaunchReadinessError(f"{field} must be a finite number")
    if v < 0.0 or v > 1.0:
        raise ResearchLaunchReadinessError(f"{field} must be in [0, 1]")
    return v


def evaluate_research_launch_readiness(
    *,
    session_id: object,
    source_family_count: object,
    quality_overall: object,
    would_exceed: object,
    quality_floor: object = 0.5,
    operator_override: object = False,
) -> ResearchLaunchReadinessDecision:
    """Evaluate advisory launch readiness. Never authorizes live dispatch."""
    sid = _require_nonempty(session_id, field="session_id")
    if (
        not isinstance(source_family_count, int)
        or isinstance(source_family_count, bool)
        or source_family_count < 0
    ):
        raise ResearchLaunchReadinessError(
            "source_family_count must be a non-negative integer"
        )
    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise ResearchLaunchReadinessError("would_exceed must be boolean or null")
    if not isinstance(operator_override, bool):
        raise ResearchLaunchReadinessError(
            "operator_override must be an explicit boolean"
        )
    floor = _finite_unit(quality_floor, field="quality_floor")
    q_overall: float | None
    if quality_overall is None:
        q_overall = None
    else:
        q_overall = _finite_unit(quality_overall, field="quality_overall")

    notes: list[str] = [
        "live_dispatch_authorized=false — pure readiness gate only",
    ]

    sources_ready = source_family_count >= 1
    if not sources_ready:
        notes.append("source_family_count < 1 — sources_ready=false")
    else:
        notes.append(f"sources_ready=true (families={source_family_count})")

    if q_overall is None:
        quality_ready = True
        notes.append(
            "quality_overall unknown — quality_ready=true (no invent floor fail)"
        )
    elif q_overall >= floor:
        quality_ready = True
        notes.append(f"quality_overall={q_overall} >= floor={floor}")
    else:
        quality_ready = False
        notes.append(
            f"quality_overall={q_overall} < floor={floor} — quality_ready=false"
        )

    if would_exceed is True:
        if operator_override:
            budget_ready = True
            notes.append(
                "would_exceed=true with operator_override — budget_ready=true "
                "(still no live dispatch)"
            )
        else:
            budget_ready = False
            notes.append("would_exceed=true without override — budget_ready=false")
    elif would_exceed is False:
        budget_ready = True
        notes.append("would_exceed=false — budget_ready=true")
    else:
        if operator_override:
            budget_ready = True
            notes.append(
                "would_exceed=null with operator_override — budget_ready=true "
                "(unknown not invented safe)"
            )
        else:
            budget_ready = False
            notes.append(
                "would_exceed=null — budget_ready=false (no invent safe budget)"
            )

    launch_ready = sources_ready and quality_ready and budget_ready
    notes.append(f"launch_ready={launch_ready}")
    notes.append("live_dispatch_authorized=false")

    return ResearchLaunchReadinessDecision(
        session_id=sid,
        sources_ready=sources_ready,
        quality_ready=quality_ready,
        budget_ready=budget_ready,
        launch_ready=launch_ready,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="research_launch_readiness_advisory",
    )


__all__ = [
    "ResearchLaunchReadinessDecision",
    "ResearchLaunchReadinessError",
    "evaluate_research_launch_readiness",
]
