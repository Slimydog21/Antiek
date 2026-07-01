"""JSON IO for prompt-autoresearch mutation outcomes."""

from __future__ import annotations

import json
import math
from decimal import Decimal
from pathlib import Path
from typing import Any

from tools.prompt_autoresearch.runner import PromptMutationOutcome
from tools.prompt_autoresearch.score import CompositeScore

_FLOAT_TOLERANCE = 1e-9


def _as_float(value: Any, *, field: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{field} must be a number")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError(f"{field} must be finite")
    return number


def _as_bool(value: Any, *, field: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a boolean")
    return value


def _as_unit_interval(value: Any, *, field: str) -> float:
    number = _as_float(value, field=field)
    if number < 0.0 or number > 1.0:
        raise ValueError(f"{field} must be in [0, 1]")
    return number


def _as_non_negative_float(value: Any, *, field: str) -> float:
    number = _as_float(value, field=field)
    if number < 0.0:
        raise ValueError(f"{field} must be non-negative")
    return number


def _as_str(value: Any, *, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return value


def _optional_str(value: Any, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string when present")
    return value


def _optional_str_default(value: Any, *, field: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string when present")
    return value


def outcome_to_json(outcome: PromptMutationOutcome) -> dict[str, Any]:
    """Convert a runner outcome into the stable verdict JSON shape."""
    scores = outcome.composite_breakdown
    return {
        "mutation_id": outcome.mutation_id,
        "accepted": outcome.accepted,
        "baseline_score": outcome.baseline_score,
        "candidate_score": outcome.candidate_score,
        "delta": outcome.delta,
        "epsilon_required": outcome.epsilon_required,
        "composite_breakdown": {
            "rubric": scores.rubric,
            "voice_style": scores.voice_style,
            "sector_vocab": scores.sector_vocab,
            "grounding": scores.grounding,
            "total": scores.total,
        },
        "cost_usd": str(outcome.cost_usd),
        "mutation_rationale": outcome.mutation_rationale,
        "parent_baseline_id": outcome.parent_baseline_id,
        "proposed_at": outcome.proposed_at,
        "notes": outcome.notes,
    }


def _composite_from_json(raw: Any, *, index: int) -> CompositeScore:
    if not isinstance(raw, dict):
        raise ValueError(f"outcomes[{index}].composite_breakdown must be an object")
    return CompositeScore(
        rubric=_as_unit_interval(raw.get("rubric"), field=f"outcomes[{index}].composite_breakdown.rubric"),
        voice_style=_as_unit_interval(raw.get("voice_style"), field=f"outcomes[{index}].composite_breakdown.voice_style"),
        sector_vocab=_as_unit_interval(raw.get("sector_vocab"), field=f"outcomes[{index}].composite_breakdown.sector_vocab"),
        grounding=_as_unit_interval(raw.get("grounding"), field=f"outcomes[{index}].composite_breakdown.grounding"),
        total=_as_unit_interval(raw.get("total"), field=f"outcomes[{index}].composite_breakdown.total"),
    )


def outcome_from_json(raw: Any, *, index: int) -> PromptMutationOutcome:
    """Convert one JSON object into the runner's verdict input type."""
    if not isinstance(raw, dict):
        raise ValueError(f"outcomes[{index}] must be an object")
    try:
        cost = Decimal(str(raw.get("cost_usd", "0")))
    except Exception as exc:  # pragma: no cover - Decimal's exception type is version-specific.
        raise ValueError(f"outcomes[{index}].cost_usd must be decimal-compatible") from exc
    if not cost.is_finite():
        raise ValueError(f"outcomes[{index}].cost_usd must be finite")
    if cost < Decimal("0"):
        raise ValueError(f"outcomes[{index}].cost_usd must be non-negative")

    baseline_score = _as_unit_interval(raw.get("baseline_score"), field=f"outcomes[{index}].baseline_score")
    candidate_score = _as_unit_interval(raw.get("candidate_score"), field=f"outcomes[{index}].candidate_score")
    delta = _as_float(raw.get("delta"), field=f"outcomes[{index}].delta")
    epsilon_required = _as_non_negative_float(raw.get("epsilon_required"), field=f"outcomes[{index}].epsilon_required")
    accepted = _as_bool(raw.get("accepted"), field=f"outcomes[{index}].accepted")
    expected_delta = candidate_score - baseline_score
    if abs(delta - expected_delta) > _FLOAT_TOLERANCE:
        raise ValueError(
            f"outcomes[{index}].delta must equal candidate_score - baseline_score"
        )
    expected_accepted = delta > epsilon_required
    if accepted != expected_accepted:
        raise ValueError(
            f"outcomes[{index}].accepted must equal delta > epsilon_required"
        )

    return PromptMutationOutcome(
        mutation_id=_as_str(raw.get("mutation_id"), field=f"outcomes[{index}].mutation_id"),
        accepted=accepted,
        baseline_score=baseline_score,
        candidate_score=candidate_score,
        delta=delta,
        epsilon_required=epsilon_required,
        composite_breakdown=_composite_from_json(raw.get("composite_breakdown"), index=index),
        cost_usd=cost,
        mutation_rationale=_optional_str_default(raw.get("mutation_rationale"), field=f"outcomes[{index}].mutation_rationale"),
        parent_baseline_id=_optional_str(raw.get("parent_baseline_id"), field=f"outcomes[{index}].parent_baseline_id"),
        proposed_at=_optional_str_default(raw.get("proposed_at"), field=f"outcomes[{index}].proposed_at"),
        notes=str(raw.get("notes", "")),
    )


def write_outcomes_json(
    path: Path,
    *,
    role: str,
    outcomes: list[PromptMutationOutcome],
) -> None:
    """Write role + outcomes as the verdict CLI's input file."""
    if not role:
        raise ValueError("role must be a non-empty string")
    payload = {
        "role": role,
        "outcomes": [outcome_to_json(outcome) for outcome in outcomes],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def load_outcomes_json(path: Path) -> tuple[str | None, list[PromptMutationOutcome]]:
    """Load either ``[{...}]`` or ``{"role": "...", "outcomes": [{...}]}``."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"could not read outcomes JSON: {path}") from exc
    try:
        raw = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"outcomes JSON is malformed: {path}") from exc
    role: str | None = None
    if isinstance(raw, dict):
        if "role" in raw:
            role = _as_str(raw["role"], field="role")
        raw_outcomes = raw.get("outcomes")
    else:
        raw_outcomes = raw
    if not isinstance(raw_outcomes, list):
        raise ValueError("input must be a JSON array or an object with an outcomes array")
    return role, [
        outcome_from_json(item, index=i)
        for i, item in enumerate(raw_outcomes)
    ]
