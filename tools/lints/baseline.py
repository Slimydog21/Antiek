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
        {"path": "...", "line": N, "col": N, "kind": "...", "snippet": "..."},
        ...
      ]
    }

Sorting + the schema_version field protect against accidental churn.

Content-keyed matching (the line-shift defect, issue #3236)
-----------------------------------------------------------
A pure ``(path, line, col, kind)`` key re-flags a baselined violation as
NEW whenever any edit ABOVE it shifts its line — the offense is unchanged,
only its coordinates moved. ``snippet`` (the normalized source line at the
violation site: stripped, whitespace-collapsed) closes that: matching is
two-tier — exact ``(path, line, col, kind)`` first, then a
``(path, kind, snippet)`` content fallback, consumed one-to-one so a
finding is NEW exactly when its ``(path, kind, snippet)`` multiset exceeds
the baseline's. Entries WITHOUT a snippet (every baseline written before
this field existed) match on exact coordinates only — byte-identical to
the legacy behavior, so no flag-day.

The honesty trade-off, stated plainly: with content-keying, fixing one
site of a rule while introducing a NEW violation with byte-identical
normalized source text elsewhere in the same file nets to zero in the
multiset and is NOT flagged. The one-to-one slot consumption bounds this
to verbatim duplicates of an already-grandfathered line under the same
kind; anything beyond the grandfathered count is still NEW. Consumers
that stamp snippets: ``declared_bar``, ``cli_with_baseline``,
``mypy_strict_baseline``, ``reachability_gate`` (route findings),
``reachability_gate_py``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass, replace
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
    "normalize_snippet",
    "source_line_snippet",
    "enrich_keys_with_snippets",
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
    # Normalized source line at capture time (stripped, whitespace-collapsed
    # — see ``normalize_snippet``). Empty when unknown (legacy baselines
    # never set it). When present on BOTH a current finding and a baseline
    # entry, ``filter_to_new_only`` treats a ``(path, kind, snippet)`` match
    # as the SAME grandfathered offense — robust to the line-shift a
    # mid-file insertion causes. See "Content-keyed matching" in
    # tools/lints/README.md.
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


def normalize_snippet(text: str) -> str:
    """Canonical content-match form of a source line: stripped with every
    internal whitespace run collapsed to one space. Applied at capture time
    AND at match time (to both sides), so baselines written before
    whitespace-collapsing (strip-only snippets) still match — an entry whose
    stored snippet differs only in internal spacing compares equal."""
    return " ".join(text.split())


def source_line_snippet(path: Path, line: int) -> str:
    """The normalized 1-based source line at ``path:line``, or ``""`` when
    the file is unreadable or the line is out of range (the caller then
    falls back to exact-line matching)."""
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return ""
    if 1 <= line <= len(lines):
        return normalize_snippet(lines[line - 1])
    return ""


def enrich_keys_with_snippets(
    keys: list[ViolationKey], repo_root: Path
) -> list[ViolationKey]:
    """Return a copy of ``keys`` with each ``snippet`` set to the normalized
    source line at ``(path, line)`` (``""`` when unavailable). Relative key
    paths resolve against ``repo_root``; absolute paths are used as-is. Each
    file is read once (cached per path). This is the capture/enforce
    companion to the content-keyed fallback in ``filter_to_new_only``."""
    lines_cache: dict[str, list[str]] = {}
    out: list[ViolationKey] = []
    for k in keys:
        path = Path(k.path)
        if not path.is_absolute():
            path = repo_root / path
        cache_key = str(path)
        lines = lines_cache.get(cache_key)
        if lines is None:
            try:
                lines = path.read_text(
                    encoding="utf-8", errors="replace"
                ).splitlines()
            except OSError:
                lines = []
            lines_cache[cache_key] = lines
        snippet = (
            normalize_snippet(lines[k.line - 1]) if 1 <= k.line <= len(lines) else ""
        )
        out.append(replace(k, snippet=snippet))
    return out


def filter_to_new_only(
    current: list[ViolationKey],
    baseline: BaselineSchema,
) -> list[ViolationKey]:
    """Return current keys NOT in the baseline (new since capture).

    Matching is two-stage so a baselined offense that merely SHIFTED line
    (because a PR inserted code above it) is still recognized as the same
    grandfathered debt, not reported as NEW:

    1. Exact ``(path, line, col, kind)`` membership AND agreeing content.
       A coordinate match alone is not enough: a different violation of the
       same kind can land on a baselined coordinate as code moves, and
       absorbing it would hand every baselined coordinate out as a free pass
       on a required gate. When either side carries no snippet (substrate-lint
       and v1 baselines), this degrades to coordinate-only matching and
       behaves byte-identically to before.
    2. Content fallback: a current finding with a non-empty ``snippet``
       matches a baseline entry of the same ``(path, kind)`` whose
       normalized ``snippet`` is identical.

    Matching is ONE-TO-ONE (a baseline snippet slot absorbs at most one
    current finding), so a finding is NEW exactly when its
    ``(path, kind, snippet)`` multiset exceeds the baseline's — a NEW
    duplicate beyond the grandfathered count is still NEW.

    Exact matches are consumed in a FIRST pass, content matches in a
    SECOND. Order matters: an exact match also releases its snippet slot,
    and running exact first guarantees a still-present original is never
    displaced by a shifted twin that happens to sort earlier — otherwise
    one baselined entry could absorb one finding via content AND leave the
    exact match uncounted, masking a genuine NEW duplicate (the multiset
    rule would be violated).
    """
    # Coordinate -> the normalized snippets baselined AT that coordinate.
    # An empty string means that entry carried no snippet (a v1/legacy
    # baseline), which keeps coordinate-only matching for those.
    exact: dict[tuple[str, int, int, str], set[str]] = {}
    for k in baseline.violations:
        coord = (k.path, k.line, k.col, k.kind)
        exact.setdefault(coord, set()).add(
            normalize_snippet(k.snippet) if k.snippet else ""
        )
    slots: dict[tuple[str, str, str], int] = {}
    for k in baseline.violations:
        if k.snippet:
            sk = (k.path, k.kind, normalize_snippet(k.snippet))
            slots[sk] = slots.get(sk, 0) + 1
    # Pass 1 — exact matches consume their baseline entry's content capacity
    # too: release the snippet slot so a NEW verbatim duplicate added
    # elsewhere can't hide behind it.
    unmatched: list[ViolationKey] = []
    for k in current:
        coord = (k.path, k.line, k.col, k.kind)
        baselined_snippets = exact.get(coord)
        cur_snippet = normalize_snippet(k.snippet) if k.snippet else ""
        # A coordinate match is only the SAME offense when the content agrees.
        # Without this, a wholly different violation of the same kind landing
        # on a baselined coordinate was absorbed silently — and on a required
        # merge gate every baselined coordinate is then a free pass. Proved on
        # origin/main: baseline "import os" at test_write_routes.py:29:1
        # ruff:E402 absorbed a current "from zzz.malicious import backdoor" at
        # the same coordinate and reported 0 NEW.
        #
        # An empty string on either side means no snippet was captured (a v1
        # or substrate-lint baseline), so those keep coordinate-only matching
        # and behave byte-identically to before.
        same_offense = baselined_snippets is not None and (
            cur_snippet == ""
            or "" in baselined_snippets
            or cur_snippet in baselined_snippets
        )
        if same_offense:
            if k.snippet:
                sk = (k.path, k.kind, cur_snippet)
                if slots.get(sk, 0) > 0:
                    slots[sk] -= 1
        else:
            unmatched.append(k)
    # Pass 2 — content fallback for whatever exact matching did not absorb.
    new_only: list[ViolationKey] = []
    for k in unmatched:
        if k.snippet:
            key = (k.path, k.kind, normalize_snippet(k.snippet))
            if slots.get(key, 0) > 0:
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
    live debt). Exact match first (consuming the matching current finding's
    content capacity), then the ``(path, kind, snippet)`` content fallback
    for snippet-bearing entries, one-to-one: an entry is stale exactly when
    the current ``(path, kind, snippet)`` multiset no longer covers it.
    """
    cur_exact: set[tuple[str, int, int, str]] = {
        (k.path, k.line, k.col, k.kind) for k in current
    }
    cur_slots: dict[tuple[str, str, str], int] = {}
    for k in current:
        if k.snippet:
            sk = (k.path, k.kind, normalize_snippet(k.snippet))
            cur_slots[sk] = cur_slots.get(sk, 0) + 1
    # Pass 1 — exact matches consume the live finding's content capacity,
    # releasing its slot so a baseline entry beyond the live count is
    # reported stale instead of hiding behind a slot the exact match never
    # freed. Exact runs FIRST (mirror of filter_to_new_only) so a
    # still-present entry at its exact line is never displaced by a shifted
    # twin that sorts earlier.
    unmatched: list[ViolationKey] = []
    for k in baseline.violations:
        if (k.path, k.line, k.col, k.kind) in cur_exact:
            if k.snippet:
                sk = (k.path, k.kind, normalize_snippet(k.snippet))
                if cur_slots.get(sk, 0) > 0:
                    cur_slots[sk] -= 1
        else:
            unmatched.append(k)
    # Pass 2 — content fallback for whatever exact matching did not absorb.
    stale: list[ViolationKey] = []
    for k in unmatched:
        if k.snippet:
            key = (k.path, k.kind, normalize_snippet(k.snippet))
            if cur_slots.get(key, 0) > 0:
                cur_slots[key] -= 1
                continue
        stale.append(k)
    return sorted(stale)
