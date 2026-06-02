"""Per-source corpus-value census + the wired onboarding kill-gate (reframe P3).

WHY THIS EXISTS (reframe finding #2): the arXiv spec NAMED the failure mode — "an
elaborate apparatus is built for a corpus that turns out to be ~1% useful" — but
wired NO stop-rule; "measure before build" lived only in prose and was ignored once
(the SPR-01 census was satisfied on mocked data). This module replaces the prose
stop-rule with a MACHINE-CHECKED gate: a per-source census of corpus VALUE, and a
predicate that BLOCKS onboarding any source AFTER arXiv whose census falls below the
bar. ``tools/lint/source_gate.py`` is the CLI that exits non-zero on a violation.

CORPUS-VALUE, NOT MONETIZATION (the reframe's whole point): the corpus's worth is
feeding Research/Read/Write/Speak — a legally-clean, metadata-complete, link-back-
resolvable, low-duplication corpus — NOT an ad %. So the GATING metrics are
completeness / link-back / dedup; ``t1_pct`` (redistributable-open share) and
``open_pct`` are REPORTED but ADVISORY (a source can be valuable to research while
mostly link-back-only — that is arXiv itself).

This module owns the CONTRACT (the JSON shape a producer writes to
``reports/source_census.json``) + the THRESHOLDS + the gate PREDICATE. The producer
— ``compute_source_census(con, source)`` over the real corpus (via the one
``substrate.dedup`` identity ladder) — is the operator-gated P3b follow-on (it needs
the prod corpus + an unbanned ingest window); the contract here defines its target
shape so P3b is a single function, not a reinvention.

PURE: no DB, no network, no I/O beyond reading/writing the census JSON file — so the
gate predicate is unit-testable against hand-written censuses, exactly the property a
kill-gate needs (its correctness must not depend on live data).
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Thresholds — PROVISIONAL until calibrated against the first REAL arXiv census
# (the current values are reasoned defaults, not measured). They are corpus-VALUE
# bars, deliberately NOT monetization bars. Percentages are 0..100.
# ---------------------------------------------------------------------------

# A source's documents must be metadata-complete enough to be usable as research
# evidence (title + a source URI present). Below this the corpus is noise.
METADATA_COMPLETE_MIN = 95.0
# Every served/cited item must resolve back to its origin (arXiv ToU + every other
# source's attribution needs a working link-back). This is near-absolute.
LINKBACK_RESOLVABLE_MIN = 99.0
# A source that mostly re-imports what the corpus already holds adds cost, not
# value. EXCLUSIVE bound: dedup_overlap must be strictly below this.
DEDUP_OVERLAP_MAX = 20.0

# The reference source the gate EXEMPTS. arXiv is the calibration baseline the whole
# reframe is built on; the gate guards every source ADDED AFTER it, not arXiv itself
# (gating the baseline against thresholds derived from it is circular).
REFERENCE_SOURCE = "arxiv"


def _finite_pct(name: str, value: Any, source: str) -> float:
    """Coerce a census percentage to a float, REJECTING non-finite (NaN/inf) and
    out-of-range values at parse time. A NaN gating metric would silently PASS the
    gate (every ``<`` / ``>=`` comparison against NaN is False) — and NaN is exactly
    what a producer emits dividing by an empty sub-population — so the deny-by-default
    posture requires it fail loudly here, not slip through to a green gate."""
    v = float(value)
    if not math.isfinite(v):
        raise ValueError(
            f"source census for {source!r}: {name}={value!r} is not finite — a "
            f"NaN/inf metric must never reach the gate (it would silently pass)."
        )
    if not 0.0 <= v <= 100.0:
        raise ValueError(
            f"source census for {source!r}: {name}={v} is outside 0..100."
        )
    return v


@dataclass(frozen=True)
class SourceCensus:
    """One source's measured corpus-value census. ``*_pct`` are 0..100.

    ``t1_pct`` / ``open_pct`` are REPORTED for visibility but are NOT gated — the
    corpus's value is feeding products, not ad share (see module docstring)."""

    source: str
    total: int
    t1_pct: float
    open_pct: float
    metadata_complete_pct: float
    dedup_overlap_pct: float
    linkback_resolvable_pct: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceCensus:
        """Build from a parsed JSON object, failing loudly on a missing or malformed
        field — a census that omits or corrupts a gating metric must NOT default to a
        passing value (that would be a silent gate bypass). Every field is required;
        every percentage must be a FINITE number in 0..100 (see :func:`_finite_pct`)."""
        if not isinstance(d, dict):
            raise ValueError(
                f"source census entry must be a JSON object, got "
                f"{type(d).__name__}: {d!r}"
            )
        missing = {f for f in cls.__dataclass_fields__} - set(d)
        if missing:
            raise ValueError(
                f"source census for {d.get('source', '?')!r} is missing required "
                f"field(s) {sorted(missing)} — a partial census cannot be gated "
                f"(deny-by-default: no field may default to a passing value)."
            )
        source = str(d["source"])
        return cls(
            source=source,
            total=int(d["total"]),
            t1_pct=_finite_pct("t1_pct", d["t1_pct"], source),
            open_pct=_finite_pct("open_pct", d["open_pct"], source),
            metadata_complete_pct=_finite_pct(
                "metadata_complete_pct", d["metadata_complete_pct"], source
            ),
            dedup_overlap_pct=_finite_pct(
                "dedup_overlap_pct", d["dedup_overlap_pct"], source
            ),
            linkback_resolvable_pct=_finite_pct(
                "linkback_resolvable_pct", d["linkback_resolvable_pct"], source
            ),
        )


def gate_failures(c: SourceCensus, *, is_reference: bool = False) -> list[str]:
    """The gate violations for ONE source's census — empty list == passes.

    Structural deny-by-default applies to EVERY source (incl. the reference): a
    source with no measured documents (``total <= 0``) or a non-finite gating metric
    cannot be certified — there is nothing trustworthy to gate on. The reference
    source (arXiv) is then exempt from the THRESHOLD checks only (gating the
    calibration baseline against thresholds derived from it is circular), but it is
    NOT invisible — it still returns a (possibly empty) result and is still
    structurally gated. ``t1_pct`` / ``open_pct`` are advisory, never gated."""
    fails: list[str] = []
    if c.total <= 0:
        fails.append(
            f"total={c.total}: no documents measured — a source must have a "
            f"measured corpus to be certified (deny-by-default, not a vacuous pass)."
        )
        return fails
    nonfinite = [
        name
        for name, val in (
            ("metadata_complete_pct", c.metadata_complete_pct),
            ("linkback_resolvable_pct", c.linkback_resolvable_pct),
            ("dedup_overlap_pct", c.dedup_overlap_pct),
        )
        if not math.isfinite(val)
    ]
    if nonfinite:
        fails.append(
            f"non-finite gating metric(s) {nonfinite}: NaN/inf must never pass "
            f"(every threshold comparison against NaN is False — deny-by-default)."
        )
        return fails
    if is_reference:
        # Threshold-exempt (the baseline sets the bar; gating it against that bar is
        # circular) but structurally gated above — exempt, not invisible.
        return fails
    if c.metadata_complete_pct < METADATA_COMPLETE_MIN:
        fails.append(
            f"metadata_complete_pct={c.metadata_complete_pct:.1f} < "
            f"{METADATA_COMPLETE_MIN} (corpus too incomplete to be usable evidence)."
        )
    if c.linkback_resolvable_pct < LINKBACK_RESOLVABLE_MIN:
        fails.append(
            f"linkback_resolvable_pct={c.linkback_resolvable_pct:.1f} < "
            f"{LINKBACK_RESOLVABLE_MIN} (cited items must resolve back to origin)."
        )
    if c.dedup_overlap_pct >= DEDUP_OVERLAP_MAX:
        fails.append(
            f"dedup_overlap_pct={c.dedup_overlap_pct:.1f} >= {DEDUP_OVERLAP_MAX} "
            f"(source mostly re-imports corpus the graph already holds)."
        )
    return fails


def evaluate(censuses: list[SourceCensus]) -> dict[str, list[str]]:
    """Per-source gate result over ALL censuses. The reference source is threshold-
    exempt (see :func:`gate_failures`) but still appears in the result and is still
    structurally gated — so an empty / malformed row mislabeled as the reference
    cannot vanish unchecked. At most ONE reference row may exist; a duplicate is a
    mislabel/evasion signal and raises."""
    refs = [c for c in censuses if c.source == REFERENCE_SOURCE]
    if len(refs) > 1:
        raise ValueError(
            f"{len(refs)} {REFERENCE_SOURCE!r} census rows — the reference source "
            f"must be unique; duplicate reference rows are a mislabel/evasion signal."
        )
    return {
        c.source: gate_failures(c, is_reference=(c.source == REFERENCE_SOURCE))
        for c in censuses
    }


def load_censuses(path: Path) -> list[SourceCensus]:
    """Parse ``reports/source_census.json`` (a JSON array of census objects)."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError(
            f"{path} must be a JSON array of source censuses, got {type(data).__name__}."
        )
    return [SourceCensus.from_dict(d) for d in data]


def save_censuses(censuses: list[SourceCensus], path: Path) -> None:
    """Write the census array deterministically (sorted by source, indented) so a
    re-emit is a clean diff."""
    payload = [c.to_dict() for c in sorted(censuses, key=lambda c: c.source)]
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
