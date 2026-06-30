"""Deterministic validation for model-emitted provenance references.

Role parsers may accept ids from an LLM only after checking them against the
canonical ids the orchestrator actually supplied. A miss is model noise, not a
new fact. This module is pure and deliberately small so parsers can share one
rule instead of hand-rolling membership checks.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass


class InvalidReference(ValueError):
    """Raised when a model-emitted reference is outside the canonical set."""


@dataclass(frozen=True)
class RefValidationResult:
    """Result for list validation.

    ``valid`` preserves input order after trimming and de-duplicating.
    ``invalid`` preserves the fabricated references for diagnostics.
    """

    valid: tuple[str, ...]
    invalid: tuple[str, ...]


def _canonicalize(canonical_set: Iterable[str]) -> frozenset[str]:
    return frozenset(str(ref).strip() for ref in canonical_set if str(ref).strip())


def validate_ref(candidate: object, canonical_set: Iterable[str]) -> str | None:
    """Return the normalized ref when it is canonical, otherwise ``None``."""
    if not isinstance(candidate, str):
        return None
    normalized = candidate.strip()
    if not normalized:
        return None
    return normalized if normalized in _canonicalize(canonical_set) else None


def validate_refs(
    candidates: Iterable[object],
    canonical_set: Iterable[str],
    *,
    on_invalid: str = "drop",
) -> RefValidationResult:
    """Validate a list of model-emitted refs against a canonical set.

    Args:
        candidates: Refs emitted by the model.
        canonical_set: Refs actually supplied by the orchestrator.
        on_invalid: ``"drop"`` records invalid refs in the result and keeps
            valid refs. ``"raise"`` raises ``InvalidReference`` on the first
            invalid ref.
    """
    if on_invalid not in {"drop", "raise"}:
        raise ValueError("on_invalid must be 'drop' or 'raise'")

    canonical = _canonicalize(canonical_set)
    valid: list[str] = []
    invalid: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, str):
            invalid.append(repr(candidate))
            if on_invalid == "raise":
                raise InvalidReference(f"reference {candidate!r} is not a string")
            continue

        normalized = candidate.strip()
        if not normalized or normalized not in canonical:
            invalid.append(normalized)
            if on_invalid == "raise":
                raise InvalidReference(
                    f"reference {normalized!r} is not in canonical set"
                )
            continue

        if normalized not in seen:
            valid.append(normalized)
            seen.add(normalized)

    return RefValidationResult(valid=tuple(valid), invalid=tuple(invalid))
