"""Connectedness profile — how does an artifact relate to the knowledge base?

Operator vision (ask #4): the twin substrate makes the platform an *"infinite
information platform"* where insights and questions *"can be merged, referenced,
and leveraged."* The four cross-reference modules surface the EDGES of that graph:

* **discovery (#1945)** — insight↔insight subject connections
* **resolution_candidates (#1946)** — insight→question candidate resolutions
* **polarity (#1947)** — insight↔insight contradictions / compatibles
* **question_links (#1948)** — question↔question clusters

Each is a separate report. The operator — *"interrogate, assess, and wrestle with
the information"* (ask #1) — should not have to mentally aggregate four reports to
answer the basic question: **how does this artifact relate to my knowledge base?**
Is it well-integrated (richly connected to prior work), isolated (an island),
conflicting (contradicts established findings), or unknown (nothing to compare
against)? That aggregate verdict is THIS module.

**The verdict (hard to vary).** Composed from the four edge-type counts against the
number of priors examined:

* ``well_integrated`` — the artifact has connections to multiple prior
  investigations AND no contradictions. It builds on established work coherently.
* ``conflicting`` — the artifact has ≥1 cross-artifact contradiction. It disagrees
  with prior findings — the operator must resolve the conflict (the "wrestle"
  surface). Contradiction takes priority over integration: an artifact that both
  connects and conflicts is flagged conflicting so the conflict is not buried.
* ``partially_integrated`` — some connections but to few priors, or connections
  without resolution candidates / cluster participation. Partially woven in.
* ``isolated`` — zero connections of any edge type, BUT priors were examined. The
  artifact is an island in the knowledge base — its findings don't connect to
  prior work. This may be fine (genuinely novel) or a signal (the investigation
  didn't engage with existing knowledge).
* ``unknown`` — no priors were examined. Connectedness is not measurable (there
  was nothing to compare against). Never fabricated as isolated.

**Honesty rules (load-bearing):**
* ``unknown`` when ``prior_investigation_count == 0`` — connectedness is not
  measurable without priors to compare against. Never fabricate ``isolated`` (an
  artifact with no priors is not an island; it is unmeasurable).
* ``conflicting`` takes PRIORITY over ``well_integrated`` — an artifact with both
  connections and contradictions is flagged conflicting so the conflict surfaces.
  The conflict count and the connection count are both carried in the report.
* The verdict is DESCRIPTIVE, not normative. ``isolated`` is not "bad" (the
  finding may be genuinely novel); ``well_integrated`` is not "good" (the findings
  may merely repeat prior work — redundancy #1939 catches that). The verdict
  describes the TOPOLOGY; the operator judges the value.
* Every count is carried through verbatim (auditable breakdown). The operator can
  see exactly how the verdict was derived.
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation.
* ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings (load-bearing).** This module takes the edge
counts as a frozen :class:`ConnectednessInputs` dataclass. The route layer
extracts the counts from the four reference reports (#1945–#1948) and passes them
in. No import of off-main modules — each reference PR stays bar-clean on frozen
main independently. This mirrors the compatible-shape pattern (#1937
``PlanQuestion`` Protocol): define the input shape locally, let the route layer
adapt 1:1 when the foundation merges.
"""

from __future__ import annotations

from dataclasses import dataclass

_DEFAULT_INTEGRATION_PRIOR_FLOOR: int = 2
_DEFAULT_PARTIAL_PRIOR_FLOOR: int = 1


class ConnectednessError(ValueError):
    """A connectedness input violates a load-bearing invariant."""


@dataclass(frozen=True)
class ConnectednessInputs:
    """The four reference-edge counts for one focus artifact.

    The route layer fills this from the four reference reports (#1945–#1948).
    Every field is a raw count — no report objects, no off-main imports.
    """

    focus_investigation_id: str
    prior_investigation_count: int  # distinct priors examined (denominator)
    connection_count: int  # insight↔insight subject links (#1945)
    connected_via_connections: int  # distinct priors with ≥1 connection (#1945)
    contradiction_count: int  # cross-artifact contradictions (#1947)
    compatible_count: int  # cross-artifact compatibles (#1947)
    resolution_candidate_count: int  # insight→question candidates (#1946)
    question_link_count: int  # question↔question links (#1948)
    question_cluster_count: int  # transitive-closure clusters of size ≥2 (#1948)


@dataclass(frozen=True)
class ConnectednessProfile:
    """How the focus artifact relates to the knowledge base. Advisory, pure."""

    focus_investigation_id: str
    verdict: str  # well_integrated | conflicting | partially_integrated | isolated | unknown
    prior_investigation_count: int
    total_edges: int  # sum of all edge counts (the connection density)
    connection_count: int
    contradiction_count: int
    compatible_count: int
    resolution_candidate_count: int
    question_link_count: int
    question_cluster_count: int
    connected_prior_count: int  # distinct priors connected via ANY edge type
    notes: tuple[str, ...]
    authority: str = "advisory"


def build_connectedness_profile(
    inputs: ConnectednessInputs,
    *,
    integration_prior_floor: int = _DEFAULT_INTEGRATION_PRIOR_FLOOR,
    partial_prior_floor: int = _DEFAULT_PARTIAL_PRIOR_FLOOR,
) -> ConnectednessProfile:
    """Compose the four reference-edge counts into one connectedness verdict.

    Pure: no DB, no LLM, no clock, no mutation. The verdict priority is:
    unknown (no priors) > conflicting (≥1 contradiction) > well_integrated
    (≥floor priors connected, no contradiction) > partially_integrated >
    isolated (zero edges but priors examined).
    """
    if integration_prior_floor < 1:
        raise ConnectednessError(
            f"integration_prior_floor must be >= 1, got {integration_prior_floor!r}"
        )
    if partial_prior_floor < 0 or partial_prior_floor >= integration_prior_floor:
        raise ConnectednessError(
            f"partial_prior_floor must be in [0, integration_prior_floor), got "
            f"{partial_prior_floor!r} (integration_prior_floor={integration_prior_floor!r})"
        )

    total_edges = (
        inputs.connection_count
        + inputs.contradiction_count
        + inputs.compatible_count
        + inputs.resolution_candidate_count
        + inputs.question_link_count
    )
    # Connected priors: approximated by the max distinct-prior count across edge
    # types (the route layer can refine, but this is a sound lower-bound proxy
    # from the available counts).
    connected_prior_count = max(
        inputs.connected_via_connections,
        # Each contradiction/resolution implies ≥1 distinct prior; cap at total.
        min(inputs.contradiction_count, inputs.prior_investigation_count),
        min(inputs.resolution_candidate_count, inputs.prior_investigation_count),
    )
    connected_prior_count = min(connected_prior_count, inputs.prior_investigation_count)

    notes: list[str] = [
        "connectedness is a TOPOLOGICAL description, not a quality judgment — "
        "'isolated' may mean genuinely novel; 'well_integrated' may mean redundant "
        "(redundancy #1939 catches that); the operator judges the value",
        "the verdict priority is unknown > conflicting > well_integrated > "
        "partially_integrated > isolated — a conflict is never buried under "
        "integration",
    ]

    if inputs.prior_investigation_count == 0:
        verdict = "unknown"
        notes.append(
            "no prior investigations examined; connectedness is not measurable "
            "(defer — never fabricated as isolated)"
        )
    elif inputs.contradiction_count > 0:
        verdict = "conflicting"
        notes.append(
            f"{inputs.contradiction_count} cross-artifact contradiction(s) found — "
            f"the artifact disagrees with prior findings (the 'wrestle' surface); "
            f"conflict takes priority over the {inputs.connection_count} "
            f"connection(s) and {inputs.compatible_count} compatible pair(s)"
        )
    elif (
        connected_prior_count >= integration_prior_floor
        and inputs.connection_count > 0
    ):
        verdict = "well_integrated"
        notes.append(
            f"connected to {connected_prior_count} of "
            f"{inputs.prior_investigation_count} prior investigation(s) via "
            f"{inputs.connection_count} connection(s), "
            f"{inputs.resolution_candidate_count} resolution candidate(s), "
            f"{inputs.question_link_count} question link(s) — no contradictions"
        )
    elif total_edges > 0:
        verdict = "partially_integrated"
        notes.append(
            f"{total_edges} edge(s) across {connected_prior_count} prior(s) — "
            f"some connection but below the integration floor "
            f"({integration_prior_floor} priors); partially woven into the "
            f"knowledge base"
        )
    else:
        verdict = "isolated"
        notes.append(
            f"zero reference edges despite {inputs.prior_investigation_count} "
            f"prior investigation(s) examined — the artifact is an island; "
            f"this may indicate genuine novelty or a failure to engage with "
            f"existing knowledge"
        )

    return ConnectednessProfile(
        focus_investigation_id=inputs.focus_investigation_id,
        verdict=verdict,
        prior_investigation_count=inputs.prior_investigation_count,
        total_edges=total_edges,
        connection_count=inputs.connection_count,
        contradiction_count=inputs.contradiction_count,
        compatible_count=inputs.compatible_count,
        resolution_candidate_count=inputs.resolution_candidate_count,
        question_link_count=inputs.question_link_count,
        question_cluster_count=inputs.question_cluster_count,
        connected_prior_count=connected_prior_count,
        notes=tuple(notes),
        authority="advisory",
    )


__all__ = [
    "ConnectednessError",
    "ConnectednessInputs",
    "ConnectednessProfile",
    "build_connectedness_profile",
]
