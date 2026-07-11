"""Model decision + prompt budget projection compose (pure).

Binds a selected model from inventory to usage bar + prompt cost projection.
would_exceed is null when remaining or high cost unknown (never invents safe).
Does not read live meters or dispatch models.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.model_decision.usage_bar import (
    PromptProjection,
    UsageBar,
    compute_usage_bar,
    project_prompt_against_bar,
    prompt_projection_to_dict,
    usage_bar_to_dict,
)


class ModelDecisionPromptComposeError(ValueError):
    """Fail-closed validation for model decision prompt compose."""


@dataclass(frozen=True)
class ModelDecisionPromptComposeResult:
    selected_model_id: str
    selected_tier: str | None
    bar: UsageBar
    projection: PromptProjection
    would_exceed: bool | None
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "selected_model_id": self.selected_model_id,
            "selected_tier": self.selected_tier,
            "bar": usage_bar_to_dict(self.bar),
            "projection": prompt_projection_to_dict(self.projection),
            "would_exceed": self.would_exceed,
            "notes": list(self.notes),
            "authority": "model_decision_prompt_compose_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ModelDecisionPromptComposeError(f"{field} must be a non-empty string")
    return value.strip()


def compose_model_decision_with_projection(
    *,
    selected_model_id: object,
    models: object,
    daily_cap_usd: float | None,
    spent_usd: float | None,
    projected_cost_usd_high: float | None | None = None,
    projected_cost_usd_low: float | None | None = None,
    use_model_cost_defaults: bool = True,
) -> ModelDecisionPromptComposeResult:
    """Compose selected model + usage bar + prompt projection.

    When ``use_model_cost_defaults`` is True and high/low are None, fall back
    to the selected model's projected_cost fields (which may also be absent →
    stay None / unknown — never invent $0).
    """
    selected = _require_nonempty(selected_model_id, field="selected_model_id")
    if not isinstance(models, list) or len(models) == 0:
        raise ModelDecisionPromptComposeError("models must be a non-empty array")
    if not isinstance(use_model_cost_defaults, bool):
        raise ModelDecisionPromptComposeError(
            "use_model_cost_defaults must be an explicit boolean"
        )

    match: dict[str, Any] | None = None
    for i, m in enumerate(models):
        if not isinstance(m, dict):
            raise ModelDecisionPromptComposeError(f"models[{i}] must be an object")
        mid = _require_nonempty(m.get("model_id"), field=f"models[{i}].model_id")
        if mid == selected:
            match = m

    if match is None:
        raise ModelDecisionPromptComposeError(
            f"selected_model_id {selected} not found in models inventory"
        )

    notes: list[str] = [
        "advisory compose — no live meters, no provider dispatch",
    ]

    try:
        bar = compute_usage_bar(
            daily_cap_usd=daily_cap_usd,
            spent_usd=spent_usd,
        )
    except ValueError as e:
        raise ModelDecisionPromptComposeError(str(e)) from e

    high = projected_cost_usd_high
    low = projected_cost_usd_low
    if use_model_cost_defaults:
        if high is None and "projected_cost_usd_high" in match:
            high = match.get("projected_cost_usd_high")
        if low is None and "projected_cost_usd_low" in match:
            low = match.get("projected_cost_usd_low")

    try:
        projection = project_prompt_against_bar(
            bar,
            projected_cost_usd_low=low,  # type: ignore[arg-type]
            projected_cost_usd_high=high,  # type: ignore[arg-type]
        )
    except ValueError as e:
        raise ModelDecisionPromptComposeError(str(e)) from e

    notes.extend(bar.notes)
    notes.extend(projection.notes)
    notes.append(f"selected_model_id={selected}")

    tier_raw = match.get("tier")
    tier = (
        tier_raw.strip()
        if isinstance(tier_raw, str) and tier_raw.strip()
        else None
    )

    return ModelDecisionPromptComposeResult(
        selected_model_id=selected,
        selected_tier=tier,
        bar=bar,
        projection=projection,
        would_exceed=projection.would_exceed,
        notes=tuple(notes),
        authority="model_decision_prompt_compose_advisory",
    )


__all__ = [
    "ModelDecisionPromptComposeError",
    "ModelDecisionPromptComposeResult",
    "compose_model_decision_with_projection",
]
