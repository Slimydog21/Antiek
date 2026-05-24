"""baseline.py — shared baseline-mode helper for the substrate lints.

ARE-11 enabler. Wiring the substrate lints into CI without a baseline
file would block every existing PR on legacy violations — the classic
lint-adoption anti-pattern. This module gives the lints a way to
declare "today's violations are grandfathered; flag only NEW ones."

The flow:

1. **Capture:** run the lint with ``--write-baseline <file>``. The
   current violations are serialized to a deterministic JSON file,
   sorted by ``(path, line, col, kind)``.
2. **Enforce:** run the lint with ``--baseline <file>``. Any violation
   that does NOT appear in the baseline is reported and fails the
   run. Violations IN the baseline are silently allowed.
3. **Reduce:** when the operator fixes a baseline violation, the lint
   notices (the violation is gone from the new run) and can suggest
   ``--write-baseline`` to shrink the file. Optionally enforce: a
   baseline entry that no longer matches reality is itself a finding
   (stale-baseline flag).

Why a generic helper rather than per-lint baseline logic: the two
lints have different violation shapes (``Violation`` vs
``BypassViolation``), but the comparison key is the same — a stable
tuple identifying the "same offense at the same place." Centralizing
the (de)serialization + comparison + diff logic gives us one
behavior to test instead of N.

JSON shape (deterministic — diffs cleanly across runs)::

    {
      "schema_version": 1,
      "lint": "no_raise_in_substrate_writers",
      "generated_at": "2026-05-24T19:30:00Z",
      "violations": [
        {"path": "substrate/dispatch/foo.py", "line": 42, "col": 4,
         "kind": "raise:CustomDomainError"},
        ...
      ]
    }

Sorting + the schema_version field protect against accidental churn
(re-runs produce byte-identical files when violation set is identical).
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

__all__ = [
    "ViolationKey",
    "BaselineSchema",
    "compute_keys",
    "load_baseline",
    "write_baseline",
    "filter_to_new_only",
    "find_stale_baseline_entries",
]


# Schema version on the baseline file. Bump when the serialization
# changes in a non-backwards-compatible way. Today's reader/writer
# only accept v1; future versions add tolerance per the substrate
# editions convention (see ~/specs/antiek-tech-philosophy/ SPR-06).
SCHEMA_VERSION = 1


@dataclass(frozen=True, order=True)
class ViolationKey:
    """The minimal tuple identifying "the same offense at the same
    place." Two ViolationKeys are equal iff (path, line, col, kind)
    match — meaning, a lint re-run on the same file produces the
    same key for an unfixed violation, but a different key if any
    field changes (e.g., the violation moved to a different line).

    The order on this dataclass is important: it gives us
    deterministic sort for the baseline file. Path-major sort makes
    diffs human-readable when the baseline shrinks.
    """

    path: str
    line: int
    col: int
    kind: str


class _HasKey(Protocol):
    """Anything that can supply a ViolationKey. Both ``Violation``
    (no_raise lint) and ``BypassViolation`` (unannotated_bypass lint)
    implement this implicitly via the ``compute_keys`` adapter
    functions defined per-lint."""


@dataclass
class BaselineSchema:
    """Decoded baseline file contents."""

    schema_version: int
    lint: str
    generated_at: str
    violations: list[ViolationKey]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "BaselineSchema":
        if data.get("schema_version") != SCHEMA_VERSION:
            raise ValueError(
                f"baseline schema_version is "
                f"{data.get('schema_version')!r}; expected {SCHEMA_VERSION}. "
                f"Re-generate the baseline with --write-baseline or migrate."
            )
        return cls(
            schema_version=data["schema_version"],
            lint=str(data.get("lint", "<unknown>")),
            generated_at=str(data.get("generated_at", "")),
            violations=[
                ViolationKey(
                    path=str(v["path"]),
                    line=int(v["line"]),
                    col=int(v["col"]),
                    kind=str(v["kind"]),
                )
                for v in data.get("violations", [])
            ],
        )

    def to_json(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "lint": self.lint,
            "generated_at": self.generated_at,
            "violations": [
                {"path": v.path, "line": v.line, "col": v.col, "kind": v.kind}
                for v in sorted(self.violations)  # deterministic
            ],
        }


def compute_keys(
    violations: Iterable[object],
    to_key: Callable[[object], ViolationKey],
) -> list[ViolationKey]:
    """Project a sequence of lint-specific violations to keys.

    ``to_key`` is the lint-specific adapter that knows how to read
    the violation's fields. Returned list is sorted (for stability)."""
    return sorted(to_key(v) for v in violations)


def load_baseline(path: Path) -> BaselineSchema:
    """Read a baseline JSON file. Raises FileNotFoundError if absent
    (caller decides what to do — usually treat as empty baseline)."""
    with path.open("r", encoding="utf-8") as fh:
        return BaselineSchema.from_json(json.load(fh))


def write_baseline(
    path: Path,
    lint: str,
    violations: list[ViolationKey],
) -> None:
    """Write a baseline JSON file. The file is deterministic — same
    inputs always produce byte-identical output. ``generated_at`` is
    set to the UTC timestamp at write time; if the only difference
    between two writes is the timestamp, the lint can detect that
    and skip the rewrite (caller's choice)."""
    schema = BaselineSchema(
        schema_version=SCHEMA_VERSION,
        lint=lint,
        generated_at=datetime.now(UTC).isoformat(),
        violations=violations,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        json.dump(schema.to_json(), fh, indent=2, sort_keys=True)
        fh.write("\n")


def filter_to_new_only(
    current: list[ViolationKey],
    baseline: BaselineSchema,
) -> list[ViolationKey]:
    """Return only those current-run keys that are NOT in the
    baseline. These are the "new violations since baseline was
    captured" — what the lint flags in CI mode."""
    grandfathered: set[ViolationKey] = set(baseline.violations)
    return sorted(k for k in current if k not in grandfathered)


def find_stale_baseline_entries(
    current: list[ViolationKey],
    baseline: BaselineSchema,
) -> list[ViolationKey]:
    """Return baseline entries that are NOT in the current run —
    meaning, the violation has been fixed. Useful for the
    ``--check-stale`` mode that surfaces a shrinking baseline so
    the operator can refresh it."""
    current_set: set[ViolationKey] = set(current)
    return sorted(k for k in baseline.violations if k not in current_set)
