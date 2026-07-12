"""Quality verdict composite — one advisory verdict from heterogeneous axes.

The deep-research quality package scores an artifact on several FALSIFIABLE axes
that each produce a different shape of result:

  * ``rubric_scorer`` (#1817) — five [0, 1] rubric axes, averaged into an overall.
  * ``citation_grounding`` (#1848) — a VERDICT (grounded / partially_grounded /
    ungrounded); an unresolved citation is FATAL.
  * ``source_diversity`` (#1921) — a [0, 1] Gini-Simpson score, measured-flag.
  * ``problem_question_coverage`` (#1929) — a [0, 1] lexical-coverage score.

None of these composes the others into a single defensibility verdict. The
rubric's ``overall`` is a BLIND MEAN — it cannot GATE. An artifact can score 0.95
on the rubric, have broad sources, and cover its question, yet cite a FABRICATED
source: that artifact is indefensible, but the rubric mean smiles on it. The
cardinal sin of deep research (a hallucinated citation) must be able to drop the
floor regardless of how high the soft axes score. THIS module is that gate + the
binding-constraint signal: which axis is the worst thing to fix first.

**The fatal-gate discipline (load-bearing).** An axis marked ``fatal=True`` (a
fabricated citation, or a verdict the caller flags as indefensible) makes the
whole verdict ``indefensible`` with ``overall_score`` at the floor (0.0). No soft
axis can outvote a structural failure — a perfectly-sourced fabrication is still a
fabrication. This is the one composition rule the blind rubric mean structurally
cannot express.

**Soft axes combine as a weighted mean of the MEASURED only.** An axis that
reports ``score=None`` (unmeasured — e.g. source diversity of an ungrounded
artifact) is EXCLUDED from the mean, never fabricated to 0 (that would penalize an
artifact for something it could not be measured on). Its absence lowers
``measured_axis_count`` and is surfaced in the notes so the operator sees that the
verdict is partial. ``binding_axis`` is the MEASURED soft axis with the lowest
score — the constraint to fix first — never an unmeasured one (you cannot bind on
what you did not measure).

**Honest scope.** This composite is advisory and pure: it combines axis RESULTS
handed to it (compatible ``AxisContribution`` shapes mirroring each axis's
load-bearing fields), never calling an axis module or an LLM. Authority stays with
the operator. Verdicts are graduated and never vague: ``defensible`` (no fatal,
all axes measured, overall >= threshold) / ``defensible_with_gaps`` (no fatal, but
below threshold or some axes unmeasured) / ``indefensible`` (a fatal gate fired).

**Honesty rules (load-bearing):**
* A fatal axis is decisive: ``gated=True``, ``overall_score=0.0``,
  ``verdict="indefensible"``, ``binding_axis`` = the fatal axis. No partial credit.
* Unknowns (``score=None``) are excluded from the mean and counted as unmeasured,
  never coerced to 0 or to the floor.
* Deterministic and pure: same contributions in -> same verdict out. No LLM, no
  network, no clock, no mutation. ``authority`` is always ``"advisory"``.
* Every contribution is carried through (auditable): the score, the fatal flag,
  and the reason for each axis are on the verdict, so the operator can always see
  *why* the verdict is what it is.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFENSIBLE_THRESHOLD: float = 0.80


class QualityVerdictError(ValueError):
    """A composite input violates a load-bearing invariant."""


@dataclass(frozen=True)
class AxisContribution:
    """One axis's contribution to the composite verdict (compatible shape).

    Mirrors the load-bearing fields each axis module produces, so this module
    composes axis RESULTS without importing off-main axis siblings (keeps the PR
    independently bar-clean on frozen main). The caller adapts each axis module's
    output into this shape at the route layer.

    ``score`` is the axis's [0, 1] score, or ``None`` when the axis could not be
    measured for this artifact (e.g. source diversity of an artifact with no
    grounded insights). ``fatal`` marks a structural failure that drops the floor
    (e.g. a fabricated citation). ``reason`` is the axis's own rationale, carried
    through verbatim for auditability.
    """

    axis: str
    score: float | None = None
    fatal: bool = False
    reason: str = ""


@dataclass(frozen=True)
class DRQualityVerdict:
    """The single composite defensibility verdict for one artifact. Advisory."""

    investigation_id: str
    overall_score: float  # gated composite in [0, 1]; 0.0 when gated or nothing measured
    verdict: str  # "defensible" | "defensible_with_gaps" | "indefensible"
    binding_axis: str | None  # the measured soft axis with the lowest score; None if none measured
    gated: bool  # did the fatal gate fire?
    measured_axis_count: int  # soft axes with a non-None score
    total_axis_count: int  # all contributions
    contributions: tuple[AxisContribution, ...]
    notes: tuple[str, ...]
    authority: str = "advisory"


def _clamp01(value: float) -> float:
    if value != value:  # NaN
        return 0.0
    if value < 0.0:
        return 0.0
    if value > 1.0:
        return 1.0
    return value


def compose_quality_verdict(
    *,
    investigation_id: str,
    contributions: list[AxisContribution],
    weights: dict[str, float] | None = None,
    defensible_threshold: float = _DEFENSIBLE_THRESHOLD,
) -> DRQualityVerdict:
    """Compose heterogeneous axis results into one advisory defensibility verdict.

    Applies the fatal gate first (any ``fatal=True`` axis -> ``indefensible`` at
    the floor), then a weighted mean of the MEASURED soft scores. ``binding_axis``
    is the lowest-scoring measured soft axis. Pure, deterministic, advisory.
    """
    if not investigation_id.strip():
        raise QualityVerdictError(
            "investigation_id must be non-empty (provenance is load-bearing)"
        )
    if not defensible_threshold or not 0.0 < defensible_threshold < 1.0:
        raise QualityVerdictError(
            "defensible_threshold must be in (0.0, 1.0), got "
            f"{defensible_threshold!r}"
        )

    contribs = tuple(contributions)
    if not contribs:
        raise QualityVerdictError(
            "at least one AxisContribution is required; a verdict over nothing "
            "is unmeasurable"
        )

    # Validate axis names + scores once.
    seen_names: set[str] = set()
    for contrib in contribs:
        if not contrib.axis.strip():
            raise QualityVerdictError("every AxisContribution must name a non-empty axis")
        if contrib.axis in seen_names:
            raise QualityVerdictError(
                f"duplicate axis {contrib.axis!r}; each axis contributes once"
            )
        seen_names.add(contrib.axis)
        if contrib.score is not None and (
            contrib.score != contrib.score or not (0.0 <= contrib.score <= 1.0)
        ):
                raise QualityVerdictError(
                    f"axis {contrib.axis!r} score must be finite in [0, 1] or None, "
                    f"got {contrib.score!r}"
                )

    wt = weights or {}
    for name, value in wt.items():
        if value < 0.0:
            raise QualityVerdictError(
                f"weight for {name!r} must be >= 0.0, got {value!r}"
            )

    notes: list[str] = [
        "overall_score is a weighted mean of MEASURED soft axes; a fatal axis "
        "drops it to the floor (0.0) regardless of soft scores",
        "binding_axis is the lowest-scoring measured soft axis — the constraint "
        "to fix first",
    ]

    # --- the fatal gate: decisive, no partial credit ---
    fatal_axes = [c for c in contribs if c.fatal]
    if fatal_axes:
        gate = fatal_axes[0]
        return DRQualityVerdict(
            investigation_id=investigation_id,
            overall_score=0.0,
            verdict="indefensible",
            binding_axis=gate.axis,
            gated=True,
            measured_axis_count=sum(1 for c in contribs if c.score is not None),
            total_axis_count=len(contribs),
            contributions=contribs,
            notes=tuple(
                notes
                + [
                    f"FATAL: axis {gate.axis!r} is a structural failure "
                    f"({gate.reason or 'no reason given'}) — the verdict is "
                    "indefensible regardless of soft-axis scores"
                ]
                + (
                    [f"additional fatal axis(e): {', '.join(c.axis for c in fatal_axes[1:])}"]
                    if len(fatal_axes) > 1
                    else []
                )
            ),
        )

    # --- soft combination: weighted mean of measured only ---
    measured = [c for c in contribs if c.score is not None]
    total_weight = 0.0
    weighted_sum = 0.0
    for contrib in measured:
        score = contrib.score
        if score is None:
            continue  # defensive: ``measured`` is filtered, but keeps narrowing honest
        w = wt.get(contrib.axis, 1.0)
        weighted_sum += score * w
        total_weight += w

    unmeasured = [c for c in contribs if c.score is None]

    if not measured or total_weight <= 0.0:
        return DRQualityVerdict(
            investigation_id=investigation_id,
            overall_score=0.0,
            verdict="defensible_with_gaps",
            binding_axis=None,
            gated=False,
            measured_axis_count=0,
            total_axis_count=len(contribs),
            contributions=contribs,
            notes=tuple(
                notes
                + [
                    "no soft axis could be measured; the verdict is partial — "
                    "defensibility is unproven, not affirmed"
                ]
            ),
        )

    overall = _clamp01(weighted_sum / total_weight)

    # binding axis: the lowest-scoring MEASURED soft axis (first-seen tie-break).
    binding = min(measured, key=lambda c: (c.score,))

    if overall >= defensible_threshold and not unmeasured:
        verdict = "defensible"
        notes.append(
            f"overall {overall:.2f} >= {defensible_threshold:.2f} with all "
            f"{len(measured)} axis(e) measured"
        )
    else:
        verdict = "defensible_with_gaps"
        if overall < defensible_threshold:
            notes.append(
                f"overall {overall:.2f} < {defensible_threshold:.2f} — below the "
                "defensibility threshold"
            )
        if unmeasured:
            notes.append(
                f"{len(unmeasured)} axis(e) unmeasured: "
                + ", ".join(c.axis for c in unmeasured)
                + " — verdict is partial"
            )

    notes.append(
        f"binding axis: {binding.axis!r} (score {binding.score:.2f}) is the "
        "lowest-scoring measured axis — the first constraint to address"
    )

    return DRQualityVerdict(
        investigation_id=investigation_id,
        overall_score=overall,
        verdict=verdict,
        binding_axis=binding.axis,
        gated=False,
        measured_axis_count=len(measured),
        total_axis_count=len(contribs),
        contributions=contribs,
        notes=tuple(notes),
    )


__all__ = [
    "QualityVerdictError",
    "AxisContribution",
    "DRQualityVerdict",
    "compose_quality_verdict",
]
