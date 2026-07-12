"""Research-artifact provenance coverage — do the insights trace to sources?

Operator vision (the honesty keystone stated across asks #1/#4/#7): the
workstation records *"valuable data, insights, and questions"* and every finding
must be *"traceable to source."* The canonical ``ResearchArtifactBody`` schema
makes ``ArtifactInsight.source_document_id`` an Optional by design: ``None`` is an
honest *"provenance unknown"* — the insight is a FLOATING CLAIM with no anchor.
The keystone is that unknowns surface as ``None``, never fabricated. But an
artifact full of floating claims is structurally untrustworthy: nothing in it can
be verified, and downstream merge (#1852), search (#1844), and synthesis (#1835)
would propagate unanchored assertions as if sourced.

THIS module measures how many insights carry provenance — the INTEGRITY axis.

**Distinct from ``citation_grounding`` (#1848).** That module takes one insight
+ its cited source's text and asks *"does the source actually support the claim?"*
(CONTENT fidelity — fabricated citations). It PRESUPPOSES a source exists. This
module asks the logically PRIOR question: *"does the insight cite a source AT
ALL?"* (STRUCTURAL fidelity — the floating-claim axis). An insight that cites no
source is invisible to citation_grounding (nothing to ground); provenance coverage
surfaces it. The two compose: coverage finds unsourced claims, grounding audits
the sourced ones.

**Distinct from ``source_diversity`` (#1921).** That measures the SPREAD of
sources behind the sourced evidence (a monoculture). This measures whether sources
EXIST per insight. An artifact where every insight cites the same single source
has perfect coverage but zero diversity; an artifact where half cite nothing has
50% coverage regardless of diversity. Complementary, not overlapping.

**The fabrication-risk intersection (load-bearing).** An insight that is BOTH
unsourced AND carries a ``confidence`` value is the highest fabrication-risk
surface: a confident claim with no anchor cannot be checked. ``confidence`` is
free-text in the schema (opaque to this module — it is NOT parsed or ranked), so
the module does not interpret "high"/"medium"/"low"; it surfaces the INTERSECTION
(unsourced ∧ confidence-present) as the risk set the operator should review first.

**Honesty rules (load-bearing):**
* An artifact with no insights has ``sourcing_coverage = None`` (never fabricated
  0) — coverage of nothing is unknown, not zero. ``confidence_transparency`` is
  likewise ``None``.
* An unsourced insight's ``source_document_id`` stays ``None`` on the report —
  never coerced to a placeholder. The ``unsourced_insight_ids`` list is the
  accountability surface.
* ``confidence`` is treated as opaque presence/absence (``is None``); its value
  is NEVER parsed, ranked, or compared — that would be inventing a calibration
  contract the schema does not define.
* ``sourcing_coverage`` is ``sourced / total`` over the insights that exist — a
  ratio in ``[0.0, 1.0]``.
* Deterministic and pure: same artifact -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.
* Every insight's sourcing status is carried through (auditable): the insight is
  in ``sourced_insight_ids`` or ``unsourced_insight_ids``, never lost.
"""

from __future__ import annotations

from dataclasses import dataclass

from substrate.research_artifact.schema import ResearchArtifactBody


@dataclass(frozen=True)
class ProvenanceCoverageReport:
    """The artifact's provenance-integrity surface. Advisory, pure."""

    artifact_id: str  # the artifact's investigation_id (traceability)
    insight_count: int
    sourced_count: int  # insights with source_document_id is not None
    unsourced_count: int  # insights with source_document_id is None
    sourcing_coverage: float | None  # sourced/total in [0,1]; None if no insights
    unsourced_insight_ids: tuple[str, ...]  # accountability surface, sorted
    sourced_insight_ids: tuple[str, ...]  # sorted
    # The fabrication-risk intersection: unsourced AND confidence is present.
    unsourced_confident_count: int
    unsourced_confident_insight_ids: tuple[str, ...]  # sorted
    # Insights that declare a confidence value at all (calibration transparency).
    confidence_present_count: int
    confidence_transparency: float | None  # confidence_present/total; None if none
    notes: tuple[str, ...]
    authority: str = "advisory"


def _is_sourced(value: object) -> bool:
    """An insight is sourced iff its source_document_id is a non-empty string.

    A None or whitespace-only id is an honest unknown (unsourced), never coerced
    to a placeholder source.
    """
    if not isinstance(value, str):
        return False
    return bool(value.strip())


def measure_provenance_coverage(
    artifact: ResearchArtifactBody,
) -> ProvenanceCoverageReport:
    """Measure how many of an artifact's insights carry source provenance.

    ``artifact`` is the canonical knowledge-asset body. Returns a
    :class:`ProvenanceCoverageReport` with the sourcing coverage, the unsourced
    accountability surface, and the fabrication-risk intersection (unsourced ∧
    confidence-present).

    Pure: no DB, no LLM, no clock, no mutation.
    """
    insights = artifact.insights
    n = len(insights)

    sourced_ids: list[str] = []
    unsourced_ids: list[str] = []
    unsourced_confident_ids: list[str] = []
    confidence_present = 0

    for ins in insights:
        has_confidence = ins.confidence is not None
        if has_confidence:
            confidence_present += 1
        if _is_sourced(ins.source_document_id):
            sourced_ids.append(ins.node_id)
        else:
            unsourced_ids.append(ins.node_id)
            if has_confidence:
                unsourced_confident_ids.append(ins.node_id)

    sourced_ids.sort()
    unsourced_ids.sort()
    unsourced_confident_ids.sort()

    sourcing_coverage: float | None = (len(sourced_ids) / n) if n else None
    confidence_transparency: float | None = (confidence_present / n) if n else None

    notes: list[str] = [
        "provenance coverage is a STRUCTURAL check (does an insight cite a source "
        "at all); it composes with citation_grounding (#1848, which audits whether "
        "a CITED source supports the claim) — coverage finds unsourced claims, "
        "grounding audits the sourced ones",
        "confidence is treated as opaque presence/absence; its value is never "
        "parsed or ranked (the schema defines no calibration contract)",
    ]
    if n == 0:
        notes.append(
            "no insights; provenance coverage is not measurable (defer to the "
            "operator's own review)"
        )
    else:
        notes.append(
            f"provenance coverage {sourcing_coverage:.0%}: {len(sourced_ids)} "
            f"sourced, {len(unsourced_ids)} unsourced of {n} insight(s)"
        )
        if unsourced_confident_ids:
            notes.append(
                f"FABRICATION-RISK INTERSECTION: {len(unsourced_confident_ids)} "
                "unsourced insight(s) carry a confidence value (confident claim "
                "with no anchor — highest fabrication-risk surface)"
            )
        if confidence_transparency is not None and confidence_transparency < 1.0:
            notes.append(
                f"confidence transparency {confidence_transparency:.0%}: "
                f"{confidence_present}/{n} insight(s) declare a confidence value"
            )

    return ProvenanceCoverageReport(
        artifact_id=artifact.investigation_id,
        insight_count=n,
        sourced_count=len(sourced_ids),
        unsourced_count=len(unsourced_ids),
        sourcing_coverage=sourcing_coverage,
        unsourced_insight_ids=tuple(unsourced_ids),
        sourced_insight_ids=tuple(sourced_ids),
        unsourced_confident_count=len(unsourced_confident_ids),
        unsourced_confident_insight_ids=tuple(unsourced_confident_ids),
        confidence_present_count=confidence_present,
        confidence_transparency=confidence_transparency,
        notes=tuple(notes),
    )


__all__ = [
    "ProvenanceCoverageReport",
    "measure_provenance_coverage",
]
