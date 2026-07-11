"""Deep research quality rubric (pure, advisory).

Scores research outputs against hard-to-vary dimensions using only
caller-supplied metrics — never invents quality from free text or live judges.

overall is null when no dimension is known (never invents 0 or 1).
persisted is always False.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

QualityDimensionId = Literal[
    "citation_density",
    "source_diversity",
    "claim_grounding",
    "counterargument_coverage",
    "intellectual_honesty",
    "recursive_questions",
    "actionability",
]

QUALITY_DIMENSIONS: tuple[QualityDimensionId, ...] = (
    "citation_density",
    "source_diversity",
    "claim_grounding",
    "counterargument_coverage",
    "intellectual_honesty",
    "recursive_questions",
    "actionability",
)

DIMENSION_WEIGHTS: dict[QualityDimensionId, float] = {
    "citation_density": 1.2,
    "source_diversity": 1.1,
    "claim_grounding": 1.3,
    "counterargument_coverage": 1.0,
    "intellectual_honesty": 1.4,
    "recursive_questions": 1.0,
    "actionability": 0.9,
}


class DeepResearchQualityError(ValueError):
    """Fail-closed validation for deep research quality rubric."""


@dataclass(frozen=True)
class DimensionResult:
    dimension: QualityDimensionId
    score: float | None
    weight: float
    known: bool
    note: str | None


@dataclass(frozen=True)
class DeepResearchQualityReport:
    research_id: str
    dimensions: tuple[DimensionResult, ...]
    overall: float | None
    known_count: int
    missing: tuple[QualityDimensionId, ...]
    persisted: bool
    notes: tuple[str, ...]
    authority: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "research_id": self.research_id,
            "dimensions": [
                {
                    "dimension": d.dimension,
                    "score": d.score,
                    "weight": d.weight,
                    "known": d.known,
                    "note": d.note,
                }
                for d in self.dimensions
            ],
            "overall": self.overall,
            "known_count": self.known_count,
            "missing": list(self.missing),
            "persisted": False,
            "notes": list(self.notes),
            "authority": "deep_research_quality_rubric_advisory",
        }


def _require_nonempty(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DeepResearchQualityError(f"{field} must be a non-empty string")
    return value.strip()


def _finite_unit(value: object, *, field: str) -> float | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise DeepResearchQualityError(f"{field} must be finite number or null")
    v = float(value)
    if v != v or v == float("inf") or v == float("-inf"):
        raise DeepResearchQualityError(f"{field} must be finite number or null")
    if v < 0.0 or v > 1.0:
        raise DeepResearchQualityError(f"{field} must be in [0, 1]")
    return v


def evaluate_deep_research_quality(
    *,
    research_id: object,
    dimensions: object,
    require_all_dimensions: object = False,
) -> DeepResearchQualityReport:
    """Score deep research from caller-supplied dimension metrics only."""
    rid = _require_nonempty(research_id, field="research_id")
    if not isinstance(dimensions, list):
        raise DeepResearchQualityError("dimensions must be an array")
    if not isinstance(require_all_dimensions, bool):
        raise DeepResearchQualityError(
            "require_all_dimensions must be an explicit boolean"
        )

    notes: list[str] = [
        "persisted=false — advisory rubric only (no quality ledger write)",
        "scores are caller-supplied only (no invent from free text / live judge)",
    ]

    by_dim: dict[QualityDimensionId, tuple[float | None, str | None]] = {}
    for i, d in enumerate(dimensions):
        if not isinstance(d, dict):
            raise DeepResearchQualityError(f"dimensions[{i}] must be an object")
        dim = d.get("dimension")
        if dim not in QUALITY_DIMENSIONS:
            raise DeepResearchQualityError(
                f"dimensions[{i}].dimension must be one of "
                + "|".join(QUALITY_DIMENSIONS)
            )
        if dim in by_dim:
            raise DeepResearchQualityError(f"duplicate dimension {dim}")
        score = _finite_unit(d.get("score"), field=f"dimensions[{i}].score")
        note_raw = d.get("note")
        note: str | None
        if note_raw is None:
            note = None
        elif isinstance(note_raw, str):
            note = note_raw.strip() or None
        else:
            raise DeepResearchQualityError(
                f"dimensions[{i}].note must be string when set"
            )
        by_dim[dim] = (score, note)  # type: ignore[index]

    results: list[DimensionResult] = []
    missing: list[QualityDimensionId] = []
    weight_sum = 0.0
    weighted = 0.0
    known_count = 0

    for dim in QUALITY_DIMENSIONS:
        weight = DIMENSION_WEIGHTS[dim]
        supplied = by_dim.get(dim)
        score = supplied[0] if supplied else None
        note = supplied[1] if supplied else None
        if score is None:
            missing.append(dim)
            results.append(
                DimensionResult(
                    dimension=dim,
                    score=None,
                    weight=weight,
                    known=False,
                    note=note or "unknown — not invented",
                )
            )
            continue
        known_count += 1
        weight_sum += weight
        weighted += score * weight
        results.append(
            DimensionResult(
                dimension=dim,
                score=score,
                weight=weight,
                known=True,
                note=note,
            )
        )

    overall: float | None
    if require_all_dimensions and missing:
        notes.append(
            "require_all_dimensions=true and missing="
            + ",".join(missing)
            + " — overall=null"
        )
        overall = None
    elif known_count == 0 or weight_sum <= 0:
        notes.append("no known dimensions — overall=null (no invent 0)")
        overall = None
    else:
        overall = weighted / weight_sum
        if overall != overall or overall == float("inf"):
            raise DeepResearchQualityError("overall overflowed to non-finite")
        notes.append(
            f"overall from {known_count}/{len(QUALITY_DIMENSIONS)} known dimensions"
        )

    notes.append("persisted=false")

    return DeepResearchQualityReport(
        research_id=rid,
        dimensions=tuple(results),
        overall=overall,
        known_count=known_count,
        missing=tuple(missing),
        persisted=False,
        notes=tuple(notes),
        authority="deep_research_quality_rubric_advisory",
    )


__all__ = [
    "DIMENSION_WEIGHTS",
    "DeepResearchQualityError",
    "DeepResearchQualityReport",
    "DimensionResult",
    "QUALITY_DIMENSIONS",
    "evaluate_deep_research_quality",
]
