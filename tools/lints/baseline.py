"""baseline.py — shared baseline-mode helper for the substrate lints.

ARE-11 enabler. Wiring the substrate lints into CI without a baseline
file would block every existing PR on legacy violations — the classic
lint-adoption anti-pattern. This module gives the lints a way to
declare "today's violations are grandfathered; flag only NEW ones."

Flow:
1. Capture: ``--write-baseline <file>`` serializes current violations.
2. Enforce: ``--baseline <file>`` filters new run, fails on NEW only.
3. Reduce: fixed violations surface via ``find_stale_baseline_entries``.

JSON shape (deterministic — diffs cleanly across runs)::

    {
      "schema_version": 1,
      "lint": "no_raise_in_substrate_writers",
      "generated_at": "2026-05-24T19:30:00+00:00",
      "violations": [
        {"path": "...", "line": N, "col": N, "kind": "..."},
        ...
      ]
    }

Sorting + the schema_version field protect against accidental churn.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMA_VERSION",
    "ViolationKey",
    "BaselineSchema",
    "compute_keys",
    "load_baseline",
    "write_baseline",
    "filter_to_new_only",
    "find_stale_baseline_entries",
]


SCHEMA_VERSION = 1


@dataclass(frozen=True, order=True)
class ViolationKey:
    """Minimal tuple identifying "the same offense at the same place."
    Sortable (path-major) for deterministic baseline files."""

    path: str
    line: int
    col: int
    kind: str


@dataclass
class BaselineSchema:
    schema_version: int
    lint: str
    generated_at: str
    violations: list[ViolationKey]

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> BaselineSchema:
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
                for v in sorted(self.violations)
            ],
        }


def compute_keys(
    violations: Iterable[object],
    to_key: Callable[[object], ViolationKey],
) -> list[ViolationKey]:
    """Project lint-specific violations to keys via an adapter.
    Returns sorted list for stability."""
    return sorted(to_key(v) for v in violations)


def load_baseline(path: Path) -> BaselineSchema:
    with path.open("r", encoding="utf-8") as fh:
        return BaselineSchema.from_json(json.load(fh))


def write_baseline(
    path: Path,
    lint: str,
    violations: list[ViolationKey],
) -> None:
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
    """Return current keys NOT in the baseline (new since capture)."""
    grandfathered: set[ViolationKey] = set(baseline.violations)
    return sorted(k for k in current if k not in grandfathered)


def find_stale_baseline_entries(
    current: list[ViolationKey],
    baseline: BaselineSchema,
) -> list[ViolationKey]:
    """Return baseline entries NOT in current (got fixed)."""
    current_set: set[ViolationKey] = set(current)
    return sorted(k for k in baseline.violations if k not in current_set)
