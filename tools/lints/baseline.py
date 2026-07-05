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
    # Normalized source line at capture time (``current_source[line].strip()``).
    # Empty when unknown (substrate-lint baselines never set it). When present
    # on BOTH a current finding and a baseline entry, ``filter_to_new_only``
    # treats a ``(path, kind, snippet)`` match as the SAME grandfathered
    # offense — robust to the line-shift a mid-file insertion causes. See
    # "Content-keyed matching" in tools/lints/README.md.
    snippet: str = ""


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
                    snippet=str(v.get("snippet", "")),
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
                {
                    "path": v.path,
                    "line": v.line,
                    "col": v.col,
                    "kind": v.kind,
                    **({"snippet": v.snippet} if v.snippet else {}),
                }
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
    """Return current keys NOT in the baseline (new since capture).

    Matching is two-stage so a baselined offense that merely SHIFTED line
    (because a PR inserted code above it) is still recognized as the same
    grandfathered debt, not reported as NEW:

    1. Exact ``(path, line, col, kind)`` membership (the common case, and
       the only stage when no snippet is present — so substrate-lint
       baselines and v1 baselines behave byte-identically to before).
    2. Content fallback: a current finding with a non-empty ``snippet``
       matches a baseline entry of the same ``(path, kind)`` whose
       ``snippet`` is byte-identical. This is the same comparison the
       line-shift detector uses and it provably does NOT mask a genuine
       NEW violation — a real new offense sits on a source line the new
       code introduced, whose normalized text is not in the baseline
       Matching is ONE-TO-ONE (a baseline snippet slot absorbs at most one
       current finding), so a NEW duplicate beyond the grandfathered count
       is still NEW — content-keying is non-masking by construction.
    """
    exact: set[tuple[str, int, int, str]] = {
        (k.path, k.line, k.col, k.kind) for k in baseline.violations
    }
    # ONE-TO-ONE content matching: each baseline snippet slot absorbs at most
    # ONE current finding. A baseline that grandfathers N copies of a snippet
    # (e.g. repeated ``r.raise_for_status()``) covers up to N current
    # occurrences; the (N+1)th — a genuinely NEW duplicate — is reported NEW.
    # This is what makes content-keying provably non-masking: a real new
    # offense beyond the grandfathered count can never hide behind a slot.
    slots: dict[tuple[str, str, str], int] = {}
    for k in baseline.violations:
        if k.snippet:
            slots[(k.path, k.kind, k.snippet)] = (
                slots.get((k.path, k.kind, k.snippet), 0) + 1
            )
    new_only: list[ViolationKey] = []
    for k in current:
        if (k.path, k.line, k.col, k.kind) in exact:
            # An exact match consumes this baseline entry's content capacity
            # too: release its snippet slot so a NEW verbatim duplicate added
            # elsewhere can't hide behind it. Without this, one baselined
            # entry absorbs one finding via exact AND a second via the content
            # fallback, the exact-match variant of the verbatim-duplicate mask
            # the one-to-one design exists to prevent.
            if k.snippet:
                sk = (k.path, k.kind, k.snippet)
                if slots.get(sk, 0) > 0:
                    slots[sk] -= 1
            continue
        key = (k.path, k.kind, k.snippet) if k.snippet else None
        if key is not None and slots.get(key, 0) > 0:
            slots[key] -= 1
            continue
        new_only.append(k)
    return sorted(new_only)


def find_stale_baseline_entries(
    current: list[ViolationKey],
    baseline: BaselineSchema,
) -> list[ViolationKey]:
    """Return baseline entries NOT in current (got fixed).

    Mirrors ``filter_to_new_only``: a baselined offense that shifted line
    is NOT stale — it still reproduces, just lower in the file — so it must
    not be reported as fixed (which would invite a shrink that drops still-
    live debt). Exact match first, then the ``(path, kind, snippet)`` content
    fallback for snippet-bearing entries.
    """
    cur_exact: set[tuple[str, int, int, str]] = {
        (k.path, k.line, k.col, k.kind) for k in current
    }
    # ONE-TO-ONE mirror of filter_to_new_only: each current snippet absorbs
    # at most one baseline slot, so a baseline entry whose twin was consumed
    # by another still-live occurrence is NOT reported stale.
    cur_slots: dict[tuple[str, str, str], int] = {}
    for k in current:
        if k.snippet:
            cur_slots[(k.path, k.kind, k.snippet)] = (
                cur_slots.get((k.path, k.kind, k.snippet), 0) + 1
            )
    stale: list[ViolationKey] = []
    for k in baseline.violations:
        if (k.path, k.line, k.col, k.kind) in cur_exact:
            # Mirror of the filter fix: this baseline entry is still live at
            # its exact line, so the matching current finding's content
            # capacity is consumed here. Release its slot so a different
            # baseline entry beyond the live count is reported stale instead
            # of hiding behind a slot the exact match never freed.
            if k.snippet:
                sk = (k.path, k.kind, k.snippet)
                if cur_slots.get(sk, 0) > 0:
                    cur_slots[sk] -= 1
            continue
        key = (k.path, k.kind, k.snippet) if k.snippet else None
        if key is not None and cur_slots.get(key, 0) > 0:
            cur_slots[key] -= 1
            continue
        stale.append(k)
    return sorted(stale)
