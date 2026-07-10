"""Operator-controlled benchmark wedge configuration.

Validates exactly two distinct enabled model IDs with positive pricing,
one hard budget cap, one per-call timeout, and suite coverage of all four
canonical Antiek task classes with non-empty scoring expectations.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

from substrate.model_registration.registry import ModelRegistry

from ..suite import TaskClass

_CANONICAL_TASK_CLASSES: frozenset[str] = frozenset(("distill", "synthesize", "wrestle", "book_qa"))


@dataclass(frozen=True)
class ModelWedgeCandidate:
    """One validated candidate model with resolved pricing."""

    model_id: str
    provider_id: str
    input_usd_per_1m: float
    output_usd_per_1m: float


@dataclass(frozen=True)
class WedgeConfig:
    """Operator-approved benchmark wedge: two models, four task classes, one cap.

    ``max_usd`` is the total hard cap across all calls.
    ``per_call_maximum_usd`` is the provider-enforced maximum for a single
    call — also used as the reservation amount in the journal.
    """

    candidates: tuple[ModelWedgeCandidate, ModelWedgeCandidate]
    max_usd: Decimal
    per_call_maximum_usd: Decimal
    timeout_s: float
    task_classes: tuple[TaskClass, ...]

    def __post_init__(self) -> None:
        if len(self.candidates) != 2:
            raise ValueError("exactly two candidate models required")
        if self.candidates[0].model_id == self.candidates[1].model_id:
            raise ValueError("candidate model IDs must be distinct")
        if (
            not self.max_usd.is_finite()
            or not self.per_call_maximum_usd.is_finite()
            or self.max_usd <= 0
            or self.per_call_maximum_usd <= 0
        ):
            raise ValueError("budget limits must be positive")
        if self.per_call_maximum_usd > self.max_usd:
            raise ValueError("per-call maximum must not exceed total cap")
        if not math.isfinite(self.timeout_s) or self.timeout_s <= 0:
            raise ValueError("timeout must be positive")
        if set(self.task_classes) != _CANONICAL_TASK_CLASSES:
            raise ValueError("wedge must contain exactly the four canonical task classes")
        for candidate in self.candidates:
            if not candidate.model_id.strip() or not candidate.provider_id.strip():
                raise ValueError("candidate model and provider IDs must not be blank")
            if (
                not math.isfinite(candidate.input_usd_per_1m)
                or not math.isfinite(candidate.output_usd_per_1m)
                or candidate.input_usd_per_1m <= 0
                or candidate.output_usd_per_1m <= 0
            ):
                raise ValueError("candidate pricing must be positive")

    @property
    def model_ids(self) -> tuple[str, str]:
        return (self.candidates[0].model_id, self.candidates[1].model_id)


def validate_wedge_config(
    registry: ModelRegistry,
    *,
    candidate_model_ids: tuple[str, str],
    max_usd: Decimal | str | int | float,
    per_call_maximum_usd: Decimal | str | int | float,
    timeout_s: float,
    suite_task_classes: tuple[TaskClass, ...],
) -> WedgeConfig:
    """Validate and return an immutable wedge configuration.

    Raises ``ValueError`` for every spec-violation before dispatch:
    invalid count, duplicate, disabled, zero-price, missing-class,
    and empty-keyword cases.
    """
    max_d = Decimal(str(max_usd))
    if max_d <= 0:
        raise ValueError("max_usd must be positive")
    per_call_d = Decimal(str(per_call_maximum_usd))
    if per_call_d <= 0:
        raise ValueError("per_call_maximum_usd must be positive")
    if per_call_d > max_d:
        raise ValueError("per_call_maximum_usd must not exceed max_usd")
    if timeout_s <= 0:
        raise ValueError("timeout_s must be positive")

    # --- model validation ---
    ids = [m.strip() for m in candidate_model_ids]
    if len(ids) != 2:
        raise ValueError("exactly two candidate model IDs required")
    seen: set[str] = set()
    for mid in ids:
        if not mid:
            raise ValueError("model ID must not be blank")
        if mid in seen:
            raise ValueError(f"duplicate model ID: {mid!r}")
        seen.add(mid)

    candidates: list[ModelWedgeCandidate] = []
    for mid in ids:
        entry = registry.models.get(mid)
        if entry is None:
            raise ValueError(f"model {mid!r} is not registered")
        if not entry.enabled:
            raise ValueError(f"model {mid!r} is disabled")
        if entry.input_usd_per_1m <= 0 or entry.output_usd_per_1m <= 0:
            raise ValueError(
                f"model {mid!r} has zero pricing "
                f"(input={entry.input_usd_per_1m}, output={entry.output_usd_per_1m})"
            )
        candidates.append(
            ModelWedgeCandidate(
                model_id=entry.model_id,
                provider_id=entry.provider_id,
                input_usd_per_1m=entry.input_usd_per_1m,
                output_usd_per_1m=entry.output_usd_per_1m,
            )
        )

    # --- suite coverage ---
    classes = set(suite_task_classes)
    if not _CANONICAL_TASK_CLASSES.issubset(classes):
        missing = _CANONICAL_TASK_CLASSES - classes
        raise ValueError(f"suite must cover all four task classes; missing: {sorted(missing)}")

    return WedgeConfig(
        candidates=(candidates[0], candidates[1]),
        max_usd=max_d,
        per_call_maximum_usd=per_call_d,
        timeout_s=timeout_s,
        task_classes=tuple(suite_task_classes),
    )
