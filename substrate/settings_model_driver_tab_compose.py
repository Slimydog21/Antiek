"""Settings model driver tab compose (pure, advisory).

Decision-tree model selection with usage bar, projection, optional
Antiek-bench best, and NotDiamond shadow (never authority).

live_router_authorized always False.
secrets_stored always False.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from substrate.model_decision.prompt_compose import (
    ModelDecisionPromptComposeError,
    ModelDecisionPromptComposeResult,
    compose_model_decision_with_projection,
)

_SECRETISH = re.compile(r"sk-|api[_-]?key|secret|bearer\s", re.I)


class SettingsModelDriverTabComposeError(ValueError):
    """Fail-closed validation for settings model driver tab compose."""


@dataclass(frozen=True)
class SettingsModelDriverTabCompose:
    decision: ModelDecisionPromptComposeResult
    inventory_count: int
    pending_add_count: int
    bench_aligned: bool | None
    bench_best_for_focus: str | None
    nd_shadow_differs: bool | None
    nd_shadow_model: str | None
    tab_ready: bool
    live_router_authorized: bool
    secrets_stored: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision": self.decision.to_dict(),
            "inventory_count": self.inventory_count,
            "pending_add_count": self.pending_add_count,
            "bench_aligned": self.bench_aligned,
            "bench_best_for_focus": self.bench_best_for_focus,
            "nd_shadow_differs": self.nd_shadow_differs,
            "nd_shadow_model": self.nd_shadow_model,
            "tab_ready": self.tab_ready,
            "live_router_authorized": False,
            "secrets_stored": False,
            "notes": list(self.notes),
            "authority": "settings_model_driver_tab_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SettingsModelDriverTabComposeError(
            f"{field} must be a non-empty string"
        )
    return value.strip()


def compose_settings_model_driver_tab(
    *,
    selected_model_id: object,
    models: object,
    daily_cap_usd: object,
    spent_usd: object,
    projected_cost_usd_high: object | None = None,
    projected_cost_usd_low: object | None = None,
    bench_bests: object | None = None,
    focus_task: object | None = None,
    nd_shadow: object | None = None,
    pending_add_model_ids: object | None = None,
) -> SettingsModelDriverTabCompose:
    """Compose settings model-driver tab snapshot. Never auto-routes."""
    notes: list[str] = [
        "live_router_authorized=false — operator selects model; no auto-router",
        "secrets_stored=false — inventory/ids only; never accept raw API keys here",
        "NotDiamond is advisory/shadow only (§16 REJECT as production router)",
    ]

    try:
        decision = compose_model_decision_with_projection(
            selected_model_id=selected_model_id,
            models=models,
            daily_cap_usd=daily_cap_usd,  # type: ignore[arg-type]
            spent_usd=spent_usd,  # type: ignore[arg-type]
            projected_cost_usd_high=projected_cost_usd_high,  # type: ignore[arg-type]
            projected_cost_usd_low=projected_cost_usd_low,  # type: ignore[arg-type]
        )
    except ModelDecisionPromptComposeError as e:
        raise SettingsModelDriverTabComposeError(str(e)) from e

    notes.extend(decision.notes)
    inventory_count = len(models) if isinstance(models, list) else 0
    notes.append(f"inventory_count={inventory_count}")

    pending_add_count = 0
    if pending_add_model_ids is not None:
        if not isinstance(pending_add_model_ids, list):
            raise SettingsModelDriverTabComposeError(
                "pending_add_model_ids must be an array when set"
            )
        seen: set[str] = set()
        for i, raw in enumerate(pending_add_model_ids):
            mid = _require_nonempty(
                raw, field=f"pending_add_model_ids[{i}]"
            )
            if len(mid) > 128 or _SECRETISH.search(mid) or " " in mid:
                raise SettingsModelDriverTabComposeError(
                    f"pending_add_model_ids[{i}] must be a model id, not secret material"
                )
            if mid in seen:
                raise SettingsModelDriverTabComposeError(
                    f"duplicate pending_add_model_id: {mid}"
                )
            seen.add(mid)
        pending_add_count = len(seen)
        notes.append(
            f"pending_add_count={pending_add_count} (ids only, no secrets)"
        )

    bench_aligned: bool | None = None
    bench_best_for_focus: str | None = None
    if bench_bests is not None:
        if not isinstance(bench_bests, list):
            raise SettingsModelDriverTabComposeError(
                "bench_bests must be an array when set"
            )
        focus: str | None = None
        if focus_task is not None:
            focus = _require_nonempty(focus_task, field="focus_task")
        if len(bench_bests) == 0:
            notes.append("bench_bests empty — no invent leaderboard")
        for i, b in enumerate(bench_bests):
            if not isinstance(b, dict):
                raise SettingsModelDriverTabComposeError(
                    f"bench_bests[{i}] must be an object"
                )
            task = _require_nonempty(b.get("task"), field=f"bench_bests[{i}].task")
            best = _require_nonempty(
                b.get("best_model_id"), field=f"bench_bests[{i}].best_model_id"
            )
            score = b.get("score")
            if score is not None:
                if isinstance(score, bool) or not isinstance(score, (int, float)):
                    raise SettingsModelDriverTabComposeError(
                        f"bench_bests[{i}].score must be finite in [0, 1] when set"
                    )
                sf = float(score)
                if not math.isfinite(sf) or sf < 0 or sf > 1:
                    raise SettingsModelDriverTabComposeError(
                        f"bench_bests[{i}].score must be finite in [0, 1] when set"
                    )
            if focus is not None and task == focus:
                bench_best_for_focus = best
                bench_aligned = best == decision.selected_model_id
                notes.append(
                    f"bench_aligned=true for task={focus}"
                    if bench_aligned
                    else (
                        f"bench_aligned=false (selected={decision.selected_model_id} "
                        f"best={best})"
                    )
                )
        if focus is not None and bench_best_for_focus is None:
            notes.append(
                f"focus_task={focus} not in bench_bests — bench_aligned=null (no invent)"
            )
    elif focus_task is not None:
        notes.append("focus_task set without bench_bests — bench_aligned=null")

    nd_shadow_differs: bool | None = None
    nd_shadow_model: str | None = None
    if nd_shadow is not None:
        if not isinstance(nd_shadow, dict):
            raise SettingsModelDriverTabComposeError(
                "nd_shadow must be an object when set"
            )
        kill = nd_shadow.get("kill_switch_on")
        if not isinstance(kill, bool):
            raise SettingsModelDriverTabComposeError(
                "nd_shadow.kill_switch_on must be an explicit boolean"
            )
        rec = _require_nonempty(
            nd_shadow.get("recommended_model_id"),
            field="nd_shadow.recommended_model_id",
        )
        if kill:
            notes.append(
                "nd_shadow kill_switch_on=true — shadow suppressed (default off required)"
            )
            nd_shadow_differs = None
            nd_shadow_model = None
        else:
            nd_shadow_model = rec
            nd_shadow_differs = rec != decision.selected_model_id
            notes.append(
                f"nd_shadow_differs=true (shadow={rec}, selected={decision.selected_model_id}) — advisory only"
                if nd_shadow_differs
                else "nd_shadow_differs=false (shadow agrees with selected) — still not authority"
            )
        conf = nd_shadow.get("confidence")
        if conf is not None:
            if isinstance(conf, bool) or not isinstance(conf, (int, float)):
                raise SettingsModelDriverTabComposeError(
                    "nd_shadow.confidence must be finite in [0, 1] when set"
                )
            cf = float(conf)
            if not math.isfinite(cf) or cf < 0 or cf > 1:
                raise SettingsModelDriverTabComposeError(
                    "nd_shadow.confidence must be finite in [0, 1] when set"
                )

    tab_ready = inventory_count >= 1
    notes.append(
        "tab_ready=true — inventory present for operator selection"
        if tab_ready
        else "tab_ready=false — empty inventory"
    )
    notes.append("live_router_authorized=false")
    notes.append("secrets_stored=false")

    return SettingsModelDriverTabCompose(
        decision=decision,
        inventory_count=inventory_count,
        pending_add_count=pending_add_count,
        bench_aligned=bench_aligned,
        bench_best_for_focus=bench_best_for_focus,
        nd_shadow_differs=nd_shadow_differs,
        nd_shadow_model=nd_shadow_model,
        tab_ready=tab_ready,
        live_router_authorized=False,
        secrets_stored=False,
        notes=tuple(notes),
        authority="settings_model_driver_tab_compose_advisory",
    )


__all__ = [
    "SettingsModelDriverTabCompose",
    "SettingsModelDriverTabComposeError",
    "compose_settings_model_driver_tab",
]
