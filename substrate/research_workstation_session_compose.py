"""Research workstation session compose (pure, advisory).

Composes floating + twin + sources + quality + budget into a session
snapshot. live_dispatch_authorized is always False.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any


class ResearchWorkstationSessionComposeError(ValueError):
    """Fail-closed validation for workstation session compose."""


@dataclass(frozen=True)
class ResearchWorkstationSessionCompose:
    session_id: str
    parent_asset_id: str
    floating_instance_count: int
    twin_bound: bool
    sources_ready: bool
    quality_ready: bool
    budget_ready: bool
    floating_ready: bool
    twin_ready: bool
    cohesive_ready: bool
    session_ready: bool
    live_dispatch_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "parent_asset_id": self.parent_asset_id,
            "floating_instance_count": self.floating_instance_count,
            "twin_bound": self.twin_bound,
            "sources_ready": self.sources_ready,
            "quality_ready": self.quality_ready,
            "budget_ready": self.budget_ready,
            "floating_ready": self.floating_ready,
            "twin_ready": self.twin_ready,
            "cohesive_ready": self.cohesive_ready,
            "session_ready": self.session_ready,
            "live_dispatch_authorized": False,
            "notes": list(self.notes),
            "authority": "research_workstation_session_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ResearchWorkstationSessionComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_bool(value: object, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ResearchWorkstationSessionComposeError(
            f"{field} must be an explicit boolean"
        )
    return value


def _require_nonneg_int(value: object, *, field: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ResearchWorkstationSessionComposeError(
            f"{field} must be a non-negative integer"
        )
    return value


def compose_research_workstation_session(
    *,
    session_id: object,
    parent_asset_id: object,
    floating_instance_count: object,
    twin_bound: object,
    source_family_count: object,
    quality_overall: object,
    would_exceed: object,
    quality_floor: object | None = None,
    cohesive_pack_ready: object | None = None,
    operator_override: object | None = None,
) -> ResearchWorkstationSessionCompose:
    """Compose workstation session readiness. Never live-dispatches."""
    sid = _require_nonempty(session_id, field="session_id")
    parent = _require_nonempty(parent_asset_id, field="parent_asset_id")
    float_n = _require_nonneg_int(
        floating_instance_count, field="floating_instance_count"
    )
    sources_n = _require_nonneg_int(
        source_family_count, field="source_family_count"
    )
    twin = _require_bool(twin_bound, field="twin_bound")

    if would_exceed is not None and not isinstance(would_exceed, bool):
        raise ResearchWorkstationSessionComposeError(
            "would_exceed must be boolean or null"
        )

    override = False if operator_override is None else operator_override
    if not isinstance(override, bool):
        raise ResearchWorkstationSessionComposeError(
            "operator_override must be boolean when set"
        )

    cohesive = False if cohesive_pack_ready is None else cohesive_pack_ready
    if not isinstance(cohesive, bool):
        raise ResearchWorkstationSessionComposeError(
            "cohesive_pack_ready must be boolean when set"
        )

    if quality_floor is None:
        floor = 0.5
    else:
        if not isinstance(quality_floor, (int, float)) or isinstance(
            quality_floor, bool
        ):
            raise ResearchWorkstationSessionComposeError(
                "quality_floor must be finite in [0, 1] when set"
            )
        floor = float(quality_floor)
        if not math.isfinite(floor) or floor < 0 or floor > 1:
            raise ResearchWorkstationSessionComposeError(
                "quality_floor must be finite in [0, 1] when set"
            )

    if quality_overall is not None:
        if not isinstance(quality_overall, (int, float)) or isinstance(
            quality_overall, bool
        ):
            raise ResearchWorkstationSessionComposeError(
                "quality_overall must be null or finite in [0, 1]"
            )
        qo = float(quality_overall)
        if not math.isfinite(qo) or qo < 0 or qo > 1:
            raise ResearchWorkstationSessionComposeError(
                "quality_overall must be null or finite in [0, 1]"
            )
    else:
        qo = None

    notes: list[str] = [
        "live_dispatch_authorized=false — session compose advisory only",
    ]

    sources_ready = sources_n >= 1
    notes.append(
        f"sources_ready=true (families={sources_n})"
        if sources_ready
        else "sources_ready=false — need ≥1 knowledge-dense source family"
    )

    quality_ready = False
    if qo is None:
        notes.append(
            "quality_ready=false — quality_overall unknown (no invent 1.0)"
        )
    elif qo >= floor:
        quality_ready = True
        notes.append(f"quality_ready=true (overall={qo} floor={floor})")
    else:
        notes.append(f"quality_ready=false (overall={qo} < floor={floor})")

    budget_ready = False
    if would_exceed is None:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override with would_exceed=null (honesty)"
            )
        else:
            notes.append(
                "budget_ready=false — would_exceed unknown without operator_override"
            )
    elif would_exceed is True:
        if override:
            budget_ready = True
            notes.append(
                "budget_ready=true via operator_override with would_exceed=true"
            )
        else:
            notes.append("budget_ready=false — would_exceed=true")
    else:
        budget_ready = True
        notes.append("budget_ready=true (would_exceed=false)")

    floating_ready = float_n >= 1
    notes.append(
        f"floating_ready=true (instances={float_n})"
        if floating_ready
        else "floating_ready=false — no floating deep-research instances yet"
    )

    twin_ready = twin
    notes.append("twin_ready=true" if twin_ready else "twin_ready=false — twin bind not proposed/bound")

    cohesive_ready = cohesive
    notes.append(
        "cohesive_ready=true"
        if cohesive_ready
        else "cohesive_ready=false — multi-select pack not acked (optional until multi-instance)"
    )

    session_ready = (
        sources_ready
        and quality_ready
        and budget_ready
        and floating_ready
        and twin_ready
    )
    if float_n >= 2 and not cohesive:
        session_ready = False
        notes.append(
            "session_ready=false — ≥2 floating instances require cohesive_pack_ready"
        )
    elif session_ready:
        notes.append("session_ready=true — advisory gates pass")
    else:
        notes.append("session_ready=false — one or more core gates failed")
    notes.append("live_dispatch_authorized=false")

    return ResearchWorkstationSessionCompose(
        session_id=sid,
        parent_asset_id=parent,
        floating_instance_count=float_n,
        twin_bound=twin,
        sources_ready=sources_ready,
        quality_ready=quality_ready,
        budget_ready=budget_ready,
        floating_ready=floating_ready,
        twin_ready=twin_ready,
        cohesive_ready=cohesive_ready,
        session_ready=session_ready,
        live_dispatch_authorized=False,
        notes=tuple(notes),
        authority="research_workstation_session_compose_advisory",
    )


__all__ = [
    "ResearchWorkstationSessionCompose",
    "ResearchWorkstationSessionComposeError",
    "compose_research_workstation_session",
]
