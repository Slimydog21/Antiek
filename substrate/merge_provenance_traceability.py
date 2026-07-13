r"""Merge provenance traceability — can every insight be traced to its source?

Operator vision (ask #3, the merge surface): *"...maybe even I want to merge various
sub-agent deep researches after they come to completion to create a written analysis,
or maybe I want to click on multiple of these sub agents to engage in a collective
deep reseach where I merge those instances and prompt them as a cohesive unit...then
that substrate of information can be merged, referenced, and leveraged in combining
contexts."* The merge is where N instances become one analysis. The operator's
"reference and leverage" directive is load-bearing: to REFERENCE a finding's origin,
the merged artifact must record which parent instance each insight came from — its
PROVENANCE. Without traceable provenance, a merged analysis is an opaque lump whose
findings can't be traced to their source instance, defeating the substrate's
purpose.

**The three honest provenance states of a merged insight (NOT binary):**

A merged insight falls into exactly one of three provenance states — and crucially,
only ONE is a failure mode. This is what makes the axis genuinely distinct from a
naive "does the field exist" presence check:

* **TRACEABLE** — the insight carries a ``parent_instance_id`` that RESOLVES to one of
  the declared merge parents. Its origin is known and valid. The healthy inherited
  shape: the finding came from a specific parent instance, intact.
* **SYNTHESIZED** — the insight carries NO ``parent_instance_id``. It EMERGED from the
  combination — the merge's GENERATIVE output (a finding that arose from prompting the
  instances "as a cohesive unit," belonging to no single parent). This is NOT a
  failure: it is exactly the valuable new insight a good merge produces. The operator
  asked for a merge that "creates a written analysis" — synthesized insights ARE that
  analysis.
* **MISATTRIBUTED** — the insight carries a ``parent_instance_id`` that does NOT resolve
  to any declared parent. This is the integrity failure: a claim of origin that cannot
  be honored. The operator cannot reference it (the parent doesn't exist in this
  merge). A broken trace.

The naively-distinct presence axis (``provenance_coverage`` #1940) collapses these
three into "has source / no source" — it cannot tell synthesized (legitimate, the
merge's purpose) from misattributed (broken, the failure), nor can it tell
traceable-to-THIS-merge from a generic external source. THIS axis operates on the
merge's OWN parent set: it is the only axis that asks "of THIS merge's declared
parents, how is each insight's provenance constituted?"

**Genuinely distinct from the entire merge + provenance surface:**

* ``collective_coherence`` (#1976): do the N INPUT instances share a common subject
  (narrative coherence of the parents BEFORE merging).
* ``draft_divergence`` (#1974): how much NEW CONTENT did the draft add beyond its
  parents (content novelty of the draft stage).
* merge-fidelity (on main): did the merge PRESERVE content (nothing lost).
* merge-drift: post-merge content divergence.
* ``provenance_coverage`` (#1940): does a single-artifact insight cite ANY external
  source document (generic source presence — not the merge's parent-instance set).
* ``validate_refs`` (on main): do source ids RESOLVE to real documents (generic
  reference validity — not the traceable/synthesized/misattributed balance).

NONE measures the merge's OWN provenance constitution. This is the only axis that
takes the declared parent-instance set and classifies every merged insight as
traceable / synthesized / misattributed — the three-way balance the operator's
"reference and leverage" directive demands.

**The measurement (hard to vary).** Given the merged artifact's insights (each with
an optional ``parent_instance_id``) and the declared set of N parent instance ids:

* ``traceable_count`` — insights whose ``parent_instance_id`` resolves to a declared
  parent. Provenance known and valid.
* ``synthesized_count`` — insights with NO ``parent_instance_id`` (emerged from the
  combination — generative, NOT failure).
* ``misattributed_count`` — insights whose ``parent_instance_id`` does NOT resolve to
  any declared parent (broken origin claim — the integrity failure).
* ``traceability_rate`` — traceable / total (the share of the merge that is
  traceably inherited).
* ``synthesis_rate`` — synthesized / total (the share that is generative).
* ``unresolved_parent_ids`` — every claimed-but-unresolvable id (auditable: insight
  id + the claimed parent — no black-box misattribution).
* ``parent_coverage`` — declared parents that contributed at least one traceable
  insight (a parent contributing nothing was a no-op input — surfaced for review).

**Verdict (distinct honest states, never collapsed):**

* zero insights OR zero declared parents (nothing to trace against) -> ``unknown``
  (defer — never fabricated).
* ``misattributed_count >= 1`` -> ``misattributed`` (broken origin claims present —
  the integrity failure; provenance cannot be trusted).
* else (no misattribution), classified by the traceable/synthesized balance:
  * ``traceable_count == 0`` (all synthesized, zero traceable) -> ``provenance_lost``
    (the merge discarded all parent provenance — every finding is unattributed; the
    operator cannot reference any origin). A REAL measured verdict: synthesized-only
    is legitimate per-insight, but a merge where NOTHING is traceable has lost the
    substrate's reference purpose entirely.
  * ``synthesized_count == 0`` (all traceable, zero synthesized) -> ``fully_traceable``
    (pure inheritance — every finding came from a specific parent; provenance perfect
    but nothing generated).
  * both present -> ``generative`` (the healthy merge: provenance preserved AND new
    insight synthesized — the operator's stated ideal shape).

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when there is nothing to measure (no insights, or no
  declared parents to trace against).
* ``misattributed`` is a REAL measured verdict (a claimed parent was checked against
  the declared set and failed) — distinct from ``unknown`` (nothing to check).
* ``synthesized`` is NEVER treated as a failure (it is the merge's generative output);
  only ``provenance_lost`` (ALL synthesized) is flagged, because total provenance loss
  defeats the reference purpose — a per-insight synthesized finding is fine, a
  fully-unattributed merge is not. This distinction is the keystone.
* ``traceability_rate`` / ``synthesis_rate`` are ``None`` when ``unknown`` (defer —
  never ``0.0``).
* every misattributed insight carries its claimed-but-unresolved id verbatim
  (auditable — the operator sees exactly which origins are broken).
* ``parent_coverage`` surfaces no-op parents (a declared parent contributing nothing
  is not an error, but is surfaced — it may be a redundant input or a sign the merge
  ignored it).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (own ``MergedInsight`` shape; the route layer
  adapts 1:1 from the merge result + declared parent instance ids).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "MergedInsight",
    "MergeProvenanceReport",
    "measure_merge_provenance_traceability",
]


@dataclass(frozen=True)
class MergedInsight:
    """An insight in a merged artifact, with optional parent-instance provenance.

    Attributes:
        insight_id: stable identifier (for provenance / audit).
        parent_instance_id: the source-instance id this insight was inherited from;
            ``None`` means the insight was SYNTHESIZED (emerged from the combination).
    """

    insight_id: str
    parent_instance_id: str | None


@dataclass(frozen=True)
class UnresolvedClaim:
    """A misattributed insight: claims a parent that is not in the declared set.

    Attributes:
        insight_id: the insight making the claim.
        claimed_parent_id: the parent-instance id it claims (unresolvable).
    """

    insight_id: str
    claimed_parent_id: str


@dataclass(frozen=True)
class MergeProvenanceReport:
    """The merge-provenance-traceability verdict. Advisory, pure.

    Attributes:
        total_insights: insights measured.
        traceable_count: insights resolving to a declared parent.
        synthesized_count: insights with no parent (emerged from the merge).
        misattributed_count: insights claiming an unresolvable parent.
        traceability_rate: traceable / total; ``None`` when ``unknown``.
        synthesis_rate: synthesized / total; ``None`` when ``unknown``.
        unresolved_claims: every misattributed (insight, claimed-parent) pair,
            sorted by insight id.
        contributing_parent_ids: declared parents that contributed >= 1 traceable
            insight, sorted.
        no_op_parent_ids: declared parents contributing zero traceable insights,
            sorted.
        verdict: ``misattributed`` / ``provenance_lost`` / ``fully_traceable`` /
            ``generative`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    total_insights: int
    traceable_count: int
    synthesized_count: int
    misattributed_count: int
    traceability_rate: float | None
    synthesis_rate: float | None
    unresolved_claims: tuple[UnresolvedClaim, ...]
    contributing_parent_ids: tuple[str, ...]
    no_op_parent_ids: tuple[str, ...]
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_merge_provenance_traceability(
    insights: Sequence[MergedInsight],
    parent_instance_ids: Sequence[str],
) -> MergeProvenanceReport:
    r"""Measure the provenance constitution of a merged artifact.

    ``insights`` are the merged artifact's insights (each with an optional
    ``parent_instance_id``). ``parent_instance_ids`` are the declared ids of the N
    instances that were merged. Returns a :class:`MergeProvenanceReport` classifying
    every insight as traceable / synthesized / misattributed.
    """
    declared = frozenset(parent_instance_ids)

    total = len(insights)

    if total == 0 or not declared:
        return MergeProvenanceReport(
            total_insights=total,
            traceable_count=0,
            synthesized_count=0,
            misattributed_count=0,
            traceability_rate=None,
            synthesis_rate=None,
            unresolved_claims=(),
            contributing_parent_ids=(),
            no_op_parent_ids=tuple(sorted(declared)),
            verdict="unknown",
            notes=(
                "no insights to trace"
                if total == 0
                else "no declared parents to trace against",
            ),
        )

    traceable = 0
    synthesized = 0
    unresolved: list[UnresolvedClaim] = []
    contributors: set[str] = set()

    for ins in insights:
        if ins.parent_instance_id is None:
            synthesized += 1
        elif ins.parent_instance_id in declared:
            traceable += 1
            contributors.add(ins.parent_instance_id)
        else:
            unresolved.append(
                UnresolvedClaim(
                    insight_id=ins.insight_id,
                    claimed_parent_id=ins.parent_instance_id,
                )
            )

    unresolved.sort(key=lambda u: (u.insight_id, u.claimed_parent_id))
    misattributed_count = len(unresolved)
    no_op = sorted(declared - contributors)

    traceability_rate = traceable / total
    synthesis_rate = synthesized / total

    note_parts = [
        f"{traceable} traceable, {synthesized} synthesized, "
        f"{misattributed_count} misattributed of {total} insight(s)",
    ]
    if no_op:
        note_parts.append(
            f"{len(no_op)} declared parent(s) contributed nothing: "
            + ", ".join(no_op[:5])
        )

    if misattributed_count >= 1:
        verdict = "misattributed"
        note_parts.append(
            f"{misattributed_count} broken origin claim(s) — provenance untrustworthy"
        )
    elif traceable == 0:
        verdict = "provenance_lost"
        note_parts.append("zero traceable — all findings unattributed")
    elif synthesized == 0:
        verdict = "fully_traceable"
        note_parts.append("pure inheritance — nothing synthesized")
    else:
        verdict = "generative"
        note_parts.append("provenance preserved AND new insight synthesized")

    return MergeProvenanceReport(
        total_insights=total,
        traceable_count=traceable,
        synthesized_count=synthesized,
        misattributed_count=misattributed_count,
        traceability_rate=traceability_rate,
        synthesis_rate=synthesis_rate,
        unresolved_claims=tuple(unresolved),
        contributing_parent_ids=tuple(sorted(contributors)),
        no_op_parent_ids=tuple(no_op),
        verdict=verdict,
        notes=tuple(note_parts),
    )
