"""Advisory model decision tree — task affinity + budget projection.

**Authority:** advisory only. This module never dispatches a provider call and
must not be treated as production routing authority (CEO-DIRECTIVE §16 /
NotDiamond REJECT as production router). Callers may surface the ranking in a
decision-tree UI; the operator (or an explicit separate dispatch policy)
remains the production authority.

Inputs (all pure / injectable):
* ``task`` — product task class (deep_research, reading, note_taker, …)
* ``models`` — inventory rows the operator has available (name, tier, optional
  usd_per_1k_tokens estimate)
* optional ``remaining_usd`` — signed remaining under the operator cap
* optional ``prompt_chars`` — for a conservative chars/4 token projection
* optional ``bench_scores`` — Antiek-bench-style ``{task: {model: score}}``
  (higher is better); when absent, static task affinity is used

Outputs a ranked list with rationale, projected cost band, and ``would_exceed``
(null when remaining is unknown — never invent $0 remaining).
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Literal

TaskClass = Literal[
    "deep_research",
    "reading",
    "note_taker",
    "synthesis",
    "write",
    "general",
]

AUTHORITY = "advisory"

# Static affinity priors when Antiek-bench scores are absent.
# Higher = preferred for the task. These are intentional defaults, not
# measurements — scores from bench_scores override when present.
_TASK_TIER_AFFINITY: dict[str, dict[str, float]] = {
    "deep_research": {"reasoning": 1.0, "balanced": 0.7, "flash": 0.35, "unknown": 0.4},
    "reading": {"flash": 0.9, "balanced": 0.7, "reasoning": 0.5, "unknown": 0.5},
    "note_taker": {"flash": 1.0, "balanced": 0.6, "reasoning": 0.3, "unknown": 0.5},
    "synthesis": {"reasoning": 0.95, "balanced": 0.75, "flash": 0.4, "unknown": 0.4},
    "write": {"balanced": 0.9, "reasoning": 0.8, "flash": 0.45, "unknown": 0.5},
    "general": {"balanced": 0.8, "reasoning": 0.7, "flash": 0.6, "unknown": 0.5},
}

_CHARS_PER_TOKEN = 4.0
# Conservative output-token multiplier for projection high-band (±).
_OUTPUT_MULTIPLIER_LOW = 0.5
_OUTPUT_MULTIPLIER_HIGH = 1.5
_BAND_PAD = 0.20  # ±20% heuristic on projected mid


@dataclass(frozen=True)
class ModelCandidate:
    """One inventory model eligible for ranking."""

    model_id: str
    provider: str = ""
    tier: str = "unknown"
    # Optional operator/registry estimate: USD per 1k tokens (input≈output mid).
    usd_per_1k_tokens: float | None = None
    enabled: bool = True


@dataclass(frozen=True)
class RankedModel:
    model_id: str
    provider: str
    tier: str
    score: float
    rationale: str
    projected_cost_usd_low: float | None
    projected_cost_usd_high: float | None
    would_exceed: bool | None
    """True/False when remaining_usd known; None when remaining unknown."""


@dataclass(frozen=True)
class DecisionTreeResult:
    task: str
    authority: str
    recommended_model_id: str | None
    ranked: list[RankedModel] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    remaining_usd: float | None = None
    prompt_chars: int | None = None


def _norm_task(task: str) -> str:
    t = (task or "general").strip().lower().replace("-", "_")
    if t not in _TASK_TIER_AFFINITY:
        return "general"
    return t


def _norm_tier(tier: str | None) -> str:
    t = (tier or "unknown").strip().lower()
    if t in {"reasoning", "balanced", "flash", "unknown"}:
        return t
    # Map common aliases.
    if t in {"smart", "strong", "opus", "o1", "o3", "thinking"}:
        return "reasoning"
    if t in {"fast", "cheap", "mini", "haiku", "flash-lite"}:
        return "flash"
    if t in {"default", "standard", "sonnet", "mid"}:
        return "balanced"
    return "unknown"


def _estimate_tokens(prompt_chars: int | None) -> int | None:
    if prompt_chars is None:
        return None
    if prompt_chars < 0:
        return None
    return max(1, int(prompt_chars / _CHARS_PER_TOKEN))


def _project_cost(
    *,
    usd_per_1k: float | None,
    prompt_tokens: int | None,
) -> tuple[float | None, float | None]:
    if usd_per_1k is None or prompt_tokens is None:
        return None, None
    if usd_per_1k < 0 or prompt_tokens <= 0:
        return None, None
    # input + estimated output band
    mid_tokens = prompt_tokens * (1.0 + (_OUTPUT_MULTIPLIER_LOW + _OUTPUT_MULTIPLIER_HIGH) / 2.0)
    mid = (mid_tokens / 1000.0) * usd_per_1k
    low = mid * (1.0 - _BAND_PAD)
    high = mid * (1.0 + _BAND_PAD)
    return round(low, 6), round(high, 6)


def _affinity_score(
    task: str,
    tier: str,
    model_id: str,
    bench: Mapping[str, Mapping[str, float]] | None,
) -> tuple[float, bool, str]:
    """Return (score, measured, rationale).

    ``measured`` is True only when this model has a bench score for ``task``.
    Incomplete bench coverage must not mix measured scores with static priors
    in one comparable scalar — callers rank measured candidates strictly ahead
    of unmeasured when any measured score exists for the task among candidates.
    """
    if bench and task in bench and model_id in bench[task]:
        raw = float(bench[task][model_id])
        return raw, True, f"antiek-bench score for task={task!r}: {raw:.4f}"
    table = _TASK_TIER_AFFINITY[task]
    prior = table.get(_norm_tier(tier), table["unknown"])
    return (
        prior,
        False,
        f"static tier affinity task={task!r} tier={_norm_tier(tier)!r}: {prior:.2f}",
    )


def rank_models_for_task(
    task: str,
    models: Sequence[ModelCandidate],
    *,
    remaining_usd: float | None = None,
    prompt_chars: int | None = None,
    bench_scores: Mapping[str, Mapping[str, float]] | None = None,
) -> DecisionTreeResult:
    """Rank available models for a task; pure, side-effect free.

    Disabled models are omitted. Empty inventory → recommended None.
    """
    task_n = _norm_task(task)
    notes = [
        "authority=advisory — not production dispatch; operator remains the authority",
        "NotDiamond / measured routers must not be wired as authoritative dispatch from this surface",
    ]
    if remaining_usd is None:
        notes.append("remaining_usd unknown — would_exceed is null (not zero-faked)")
    if prompt_chars is None:
        notes.append("prompt_chars unknown — cost projection null where rate known only as rate")

    prompt_tokens = _estimate_tokens(prompt_chars)
    # (RankedModel, measured_flag) for sort policy on incomplete bench coverage.
    working: list[tuple[RankedModel, bool]] = []

    for m in models:
        if not m.enabled:
            continue
        if not m.model_id.strip():
            continue
        score, measured, why = _affinity_score(
            task_n, m.tier, m.model_id, bench_scores
        )
        low, high = _project_cost(usd_per_1k=m.usd_per_1k_tokens, prompt_tokens=prompt_tokens)
        would: bool | None = (
            None
            if remaining_usd is None or high is None
            else high > float(remaining_usd)
        )
        rationale = why
        if would is True and high is not None and remaining_usd is not None:
            rationale += (
                f"; projection high ${high:.4f} exceeds remaining ${float(remaining_usd):.4f}"
            )
        elif would is False and high is not None and remaining_usd is not None:
            rationale += (
                f"; projection high ${high:.4f} within remaining ${float(remaining_usd):.4f}"
            )
        working.append(
            (
                RankedModel(
                    model_id=m.model_id,
                    provider=m.provider,
                    tier=_norm_tier(m.tier),
                    score=score,
                    rationale=rationale,
                    projected_cost_usd_low=low,
                    projected_cost_usd_high=high,
                    would_exceed=would,
                ),
                measured,
            )
        )

    any_measured = any(m for _, m in working)
    if any_measured:
        notes.append(
            "partial or full antiek-bench coverage for this task: "
            "measured models rank ahead of unmeasured (incompatible score systems not mixed)"
        )
        # Measured first, then by score desc, then model_id.
        working.sort(key=lambda pair: (0 if pair[1] else 1, -pair[0].score, pair[0].model_id))
    else:
        working.sort(key=lambda pair: (-pair[0].score, pair[0].model_id))

    ranked = [row for row, _ in working]
    recommended = ranked[0].model_id if ranked else None
    if not ranked:
        notes.append("no enabled models in inventory — nothing to recommend")

    return DecisionTreeResult(
        task=task_n,
        authority=AUTHORITY,
        recommended_model_id=recommended,
        ranked=ranked,
        notes=notes,
        remaining_usd=remaining_usd,
        prompt_chars=prompt_chars,
    )


def result_to_dict(result: DecisionTreeResult) -> dict[str, Any]:
    return {
        "task": result.task,
        "authority": result.authority,
        "recommended_model_id": result.recommended_model_id,
        "remaining_usd": result.remaining_usd,
        "prompt_chars": result.prompt_chars,
        "notes": list(result.notes),
        "ranked": [
            {
                "model_id": r.model_id,
                "provider": r.provider,
                "tier": r.tier,
                "score": r.score,
                "rationale": r.rationale,
                "projected_cost_usd_low": r.projected_cost_usd_low,
                "projected_cost_usd_high": r.projected_cost_usd_high,
                "would_exceed": r.would_exceed,
            }
            for r in result.ranked
        ],
    }


__all__ = [
    "AUTHORITY",
    "DecisionTreeResult",
    "ModelCandidate",
    "RankedModel",
    "TaskClass",
    "rank_models_for_task",
    "result_to_dict",
]
