"""NotDiamond shadow advisory compose (pure).

§16 REJECT as production router. Shadow/advisory only.
live_router_authorized is always False.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_SECRETISH = re.compile(r"sk-|api[_-]?key|secret", re.I)


class NotDiamondShadowAdvisoryComposeError(ValueError):
    """Fail-closed validation for ND shadow advisory."""


@dataclass(frozen=True)
class NotDiamondShadowAdvisoryCompose:
    selected_model_id: str
    nd_recommended_model_id: str | None
    shadow_visible: bool
    differs_from_selected: bool | None
    suggested_model_id: str | None
    confidence: float | None
    task: str | None
    production_router_verdict: str
    live_router_authorized: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_model_id": self.selected_model_id,
            "nd_recommended_model_id": self.nd_recommended_model_id,
            "shadow_visible": self.shadow_visible,
            "differs_from_selected": self.differs_from_selected,
            "suggested_model_id": self.suggested_model_id,
            "confidence": self.confidence,
            "task": self.task,
            "production_router_verdict": "REJECT",
            "live_router_authorized": False,
            "notes": list(self.notes),
            "authority": "notdiamond_shadow_advisory_only",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise NotDiamondShadowAdvisoryComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def _require_model_id(value: object, *, field: str) -> str:
    mid = _require_nonempty(value, field=field)
    if len(mid) > 128 or _SECRETISH.search(mid):
        raise NotDiamondShadowAdvisoryComposeError(
            f"{field} must be a model id, not secret material"
        )
    return mid


def compose_notdiamond_shadow_advisory(
    *,
    selected_model_id: object,
    nd_recommended_model_id: object,
    kill_switch_on: object,
    confidence: object | None = None,
    task: object | None = None,
    inventory_model_ids: object | None = None,
) -> NotDiamondShadowAdvisoryCompose:
    """Compose ND shadow advisory. Never authorizes live routing."""
    if not isinstance(kill_switch_on, bool):
        raise NotDiamondShadowAdvisoryComposeError(
            "kill_switch_on must be an explicit boolean"
        )
    selected = _require_model_id(selected_model_id, field="selected_model_id")

    notes: list[str] = [
        "production_router_verdict=REJECT — NotDiamond is not production router (§16)",
        "live_router_authorized=false — operator model decision remains authority",
        "shadow is advisory only; never auto-routes",
    ]

    conf: float | None = None
    if confidence is not None:
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            raise NotDiamondShadowAdvisoryComposeError(
                "confidence must be finite in [0, 1] when set"
            )
        conf = float(confidence)
        if conf != conf or conf < 0.0 or conf > 1.0:
            raise NotDiamondShadowAdvisoryComposeError(
                "confidence must be finite in [0, 1] when set"
            )

    task_s: str | None = None
    if task is not None:
        task_s = _require_nonempty(task, field="task")

    inventory: set[str] | None = None
    if inventory_model_ids is not None:
        if not isinstance(inventory_model_ids, list):
            raise NotDiamondShadowAdvisoryComposeError(
                "inventory_model_ids must be an array when set"
            )
        inventory = set()
        for i, raw in enumerate(inventory_model_ids):
            mid = _require_model_id(raw, field=f"inventory_model_ids[{i}]")
            inventory.add(mid)
        if selected not in inventory:
            raise NotDiamondShadowAdvisoryComposeError(
                "selected_model_id must be present in inventory_model_ids when inventory is set"
            )
        notes.append(f"inventory_count={len(inventory)}")

    nd_rec: str | None = None
    if nd_recommended_model_id is not None:
        nd_rec = _require_model_id(
            nd_recommended_model_id, field="nd_recommended_model_id"
        )

    shadow_visible = False
    differs: bool | None = None
    suggested: str | None = None

    if kill_switch_on:
        notes.append(
            "kill_switch_on=true — shadow suppressed (safe default; operator must opt in)"
        )
    elif nd_rec is None:
        notes.append(
            "kill_switch_on=false but nd_recommended_model_id null — no invent shadow"
        )
    elif inventory is not None and nd_rec not in inventory:
        notes.append(
            f"nd_recommended_model_id={nd_rec} not in inventory — shadow suppressed (fail closed)"
        )
    else:
        shadow_visible = True
        differs = nd_rec != selected
        suggested = nd_rec if differs else None
        notes.append(
            f"shadow_visible=true · differs=true · suggested={nd_rec} (advisory only)"
            if differs
            else "shadow_visible=true · differs=false · ND agrees with selected (still not authority)"
        )
        if conf is not None:
            notes.append(f"confidence={conf}")

    notes.append("live_router_authorized=false")
    notes.append("production_router_verdict=REJECT")

    return NotDiamondShadowAdvisoryCompose(
        selected_model_id=selected,
        nd_recommended_model_id=nd_rec,
        shadow_visible=shadow_visible,
        differs_from_selected=differs,
        suggested_model_id=suggested,
        confidence=conf,
        task=task_s,
        production_router_verdict="REJECT",
        live_router_authorized=False,
        notes=tuple(notes),
        authority="notdiamond_shadow_advisory_only",
    )


def format_notdiamond_shadow_advisory_summary(
    c: NotDiamondShadowAdvisoryCompose,
) -> str:
    return (
        f"shadow_visible={c.shadow_visible} · differs={c.differs_from_selected} · "
        f"verdict=REJECT · live_router_authorized=false"
    )


__all__ = [
    "NotDiamondShadowAdvisoryCompose",
    "NotDiamondShadowAdvisoryComposeError",
    "compose_notdiamond_shadow_advisory",
    "format_notdiamond_shadow_advisory_summary",
]
