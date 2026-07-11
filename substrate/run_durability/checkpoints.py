"""Validated, content-free checkpoint primitives for durable research runs."""

from __future__ import annotations

import math
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from types import MappingProxyType
from typing import Final

_SHA256: Final = re.compile(r"[0-9a-f]{64}\Z")
_REF: Final = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,254}\Z")
MAX_REF_COUNT: Final = 8
MAX_REF_BYTES: Final = 1024


def validate_sha256(value: object, *, field: str = "sha256") -> str:
    if not isinstance(value, str) or _SHA256.fullmatch(value) is None:
        raise ValueError(f"{field} must be exactly 64 lowercase hexadecimal characters")
    return value


def validate_ref(value: object, *, field: str = "ref") -> str:
    if not isinstance(value, str) or _REF.fullmatch(value) is None:
        raise ValueError(f"{field} is not a safe opaque reference")
    return value


def validate_sequence(value: object, *, field: str = "sequence") -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError(f"{field} must be a non-negative integer")
    return value


class CheckpointKind(StrEnum):
    BRIEF_APPROVED = "brief_approved"
    PLAN_READY = "plan_ready"
    SOURCES_READY = "sources_ready"
    NOTES_READY = "notes_ready"
    SYNTHESIS_READY = "synthesis_ready"
    REPORT_READY = "report_ready"


@dataclass(frozen=True, slots=True)
class Checkpoint:
    """A boundary containing opaque references, never research content."""

    kind: CheckpointKind
    refs: Mapping[str, str]

    def __post_init__(self) -> None:
        if not isinstance(self.kind, CheckpointKind):
            raise TypeError("kind must be CheckpointKind")
        if not isinstance(self.refs, Mapping):
            raise TypeError("refs must be a mapping")
        try:
            first = tuple(self.refs.items())
            second = tuple(self.refs.items())
            claimed_length = len(self.refs)
        except Exception as exc:
            raise ValueError("checkpoint refs could not be read safely") from exc
        if first != second or claimed_length != len(first):
            raise ValueError("checkpoint refs changed while being read")
        clean: dict[str, str] = {}
        for key, value in first:
            if not isinstance(key, str) or _REF.fullmatch(key) is None:
                raise ValueError("checkpoint ref keys must be safe identifiers")
            if key in clean:
                raise ValueError("checkpoint ref keys must be unique")
            clean[key] = validate_ref(value, field=f"refs[{key!r}]")
        if not clean:
            raise ValueError("a checkpoint must contain at least one reference")
        if len(clean) > MAX_REF_COUNT:
            raise ValueError(f"a checkpoint may contain at most {MAX_REF_COUNT} references")
        if any(not key.endswith("_ref") for key in clean):
            raise ValueError("checkpoint reference keys must end in _ref")
        if (
            sum(len(key.encode()) + len(value.encode()) for key, value in clean.items())
            > MAX_REF_BYTES
        ):
            raise ValueError(
                f"checkpoint references may contain at most {MAX_REF_BYTES} UTF-8 bytes"
            )
        object.__setattr__(self, "refs", MappingProxyType(dict(sorted(clean.items()))))

    def canonical(self) -> dict[str, object]:
        return {"checkpoint_kind": self.kind.value, "refs": dict(self.refs)}


class FloorName(StrEnum):
    SOURCE_DIVERSITY = "source_diversity"
    EVIDENCE_COVERAGE = "evidence_coverage"
    CLAIM_SUPPORT = "claim_support"
    CONTRADICTION_REVIEW = "contradiction_review"


@dataclass(frozen=True, slots=True)
class FloorObservation:
    floor: FloorName
    observed: float
    required: float
    passed: bool

    def __post_init__(self) -> None:
        if not isinstance(self.floor, FloorName):
            raise TypeError("floor must be FloorName")
        for name in ("observed", "required"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TypeError(f"{name} must be a finite number")
            if not math.isfinite(float(value)) or float(value) < 0:
                raise ValueError(f"{name} must be finite and non-negative")
        if not isinstance(self.passed, bool):
            raise TypeError("passed must be bool")
        if self.passed != (float(self.observed) >= float(self.required)):
            raise ValueError("passed must agree with observed >= required")

    def canonical(self) -> dict[str, object]:
        return {
            "floor": self.floor.value,
            "observed": float(self.observed),
            "required": float(self.required),
            "passed": self.passed,
        }
