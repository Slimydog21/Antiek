r"""Highlight cluster topology — do highlights form thematic clusters or scatter?

Operator vision (ask #2): *"I want to read books or papers (and engage with it in the
same way I would the research workstation)..."* When a reader marks a document, the
POSITIONS of those highlights tell a structural story about HOW they read. Two
fundamentally different reading shapes emerge:

* CLUSTERED — highlights bunch into contiguous runs: the reader found a passage, dug in,
  and marked several adjacent lines (deep engagement with a specific argument, a proof
  they're wrestling with, a table they're cross-referencing). Each cluster is a thematic
  anchor — a passage the reader returned to and engaged densely.
* SCATTERED — highlights spread as isolated singletons across the document: the reader
  marked one key sentence per section, sampling broadly (survey reading, skimming for
  definitions, or a clean single-pass with light annotation). No passage drew sustained
  attention.

These shapes are behaviorally distinct and invisible to the existing highlight axes:
``highlight_density`` (#1973) measures how DENSELY a single passage is marked (per-passage
mark count); ``reading_engagement_distribution`` (#1998) measures Gini CONCENTRATION of
per-section touch counts (is mass uneven across sections). NEITHER measures the CONTIGUITY
structure of highlight positions — whether marks form contiguous runs (clusters) or
isolate as singletons. A document with 20 highlights evenly spread (one per section) and a
document with 20 highlights bunched in 3 tight clusters can share identical density (#1973
total) and even Gini distribution (#1998 — both can be "even" if sections are weighted by
count) yet differ wholly in cluster topology (one scattered, one clustered). Contiguity is
a third structural dimension of engagement.

**Genuinely distinct from every reading/highlight axis (load-bearing):**

* ``highlight_density`` (#1973): per-PASSAGE mark density (how many marks in one passage).
  This measures CROSS-PASSAGE cluster topology (how marks group across the whole document).
* ``reading_engagement_distribution`` (#1998): Gini concentration of per-SECTION touch
  counts (is attention mass uneven across sections). This measures whether marks form
  CONTIGUOUS RUNS vs scatter within/across sections.
* ``reading_flow_continuity`` (#1983): progress-vs-jump ordering within one session
  (reading-sequence pattern). This measures highlight-POSITION clustering (annotation
  pattern).
* ``reading_re_engagement`` (#2004): cross-session return. Different time axis entirely.

**The measurement (hard to vary).** Given the sorted list of highlight positions in a
document (each a normalized position ``[0.0, 1.0]`` — 0.0 = document start, 1.0 = end;
the route layer supplies these from the reading highlight log), build clusters via
gap-threshold contiguity:

* Sort positions ascending (deterministic).
* Two consecutive highlights belong to the SAME cluster if the gap between them
  (``position[i+1] - position[i]``) is ``<= cluster_gap_threshold`` (default ``0.05`` —
  within ~5% of the document, they're adjacent marks in the same passage). A gap above
  the threshold starts a NEW cluster.
* ``cluster_count`` — number of distinct highlight clusters.
* ``singleton_count`` — clusters of exactly size 1 (isolated highlights — the scattered
  marks).
* ``singleton_fraction`` = ``singleton_count / cluster_count`` — how much of the
  annotation is scattered singletons (``None`` when zero clusters — defer).
* ``mean_cluster_size`` — ``highlight_count / cluster_count`` (the typical cluster mass;
  ``None`` when zero clusters).
* ``largest_cluster_size`` — the biggest cluster's mark count (the deepest single
  passage engagement; auditable).
* ``cluster_spans`` — each cluster's position-span (last - first position), sorted desc
  (auditable: the operator sees the full cluster-size distribution).
* ``scatter_coefficient`` = ``singleton_count / highlight_count`` — the fraction of ALL
  highlights that are isolated (``0.0`` = fully clustered, ``1.0`` = fully scattered;
  ``None`` when zero highlights).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero highlights -> ``unknown`` (no annotation topology to measure — defer, never
  fabricated ``scattered`` or ``clustered``).
* ``highlight_count == 1`` -> ``single_highlight`` (one mark — honest base case distinct
  from ``unknown`` which has none; one mark is neither clustered nor scattered).
* ``scatter_coefficient >= scattered_threshold`` (default ``0.60``) -> ``scattered``
  (highlights spread as isolated singletons — survey/skim reading shape; the annotation
  samples broadly without sustained local engagement).
* ``scatter_coefficient <= clustered_threshold`` (default ``0.20``) -> ``clustered``
  (highlights bunch into contiguous runs — deep local engagement; the annotation dug into
  specific passages. A REAL measured verdict, NOT the default).
* otherwise -> ``mixed_topology`` (a blend — some clusters, some singletons; the common
  realistic shape).

**DESCRIPTIVE NOT NORMATIVE:** ``scattered`` does NOT mean "bad" — survey reading,
definition-gathering, or a clean single-pass with targeted key-sentence marks is a
legitimate and efficient engagement style. ``clustered`` does NOT mean "good" — a reader
may fixate on one passage obsessively while ignoring the rest (narrow engagement, not
deep). The operator judges whether the topology reflects the reading INTENT (survey vs
deep-study). This axis surfaces the FACT of annotation contiguity; it does not prescribe
the right shape.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero highlights are supplied.
* ``single_highlight`` is its own honest base case (one mark — distinct from ``unknown``
  which has none and from any multi-mark verdict).
* ``clustered`` is a REAL measured verdict (low scatter with >= 2 highlights), never the
  default — ``unknown`` and ``single_highlight`` are the defer/base states.
* ``singleton_fraction`` / ``mean_cluster_size`` / ``scatter_coefficient`` are ``None``
  when ``unknown`` (defer — never ``0.0``); ``mean_cluster_size`` is ``1.0`` for
  ``single_highlight`` (honest — one mark, one cluster, mean size 1).
* absolute gap threshold in document-position fraction (a 0.05 gap is 5% of the document
  whether it's 10 or 1000 pages — the contiguity question is scale-normalized by
  construction since positions are fractions).
* every cluster auditable via ``cluster_spans`` (position-span per cluster — no black-box
  topology); ``singleton_count`` / ``largest_cluster_size`` carried verbatim.
* positions are clamped to ``[0.0, 1.0]`` (a value outside is a data error, clamped not
  rewarded); duplicate positions merged (two marks at the exact same position are one
  highlight, mirroring graph edge-dedup discipline).
* ``authority = "advisory"`` — pure layer proposes; operator consent executes.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain float-position inputs; route layer adapts 1:1
  from the reading highlight position log).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "ClusterSpan",
    "HighlightClusterTopologyReport",
    "measure_highlight_cluster_topology",
]

_DEFAULT_CLUSTER_GAP_THRESHOLD = 0.05
_DEFAULT_SCATTERED_THRESHOLD = 0.60
_DEFAULT_CLUSTERED_THRESHOLD = 0.20


@dataclass(frozen=True)
class ClusterSpan:
    """One highlight cluster's auditable position-span."""

    size: int  # number of highlights in this cluster
    start_position: float  # first highlight position [0,1]
    end_position: float  # last highlight position [0,1]


@dataclass(frozen=True)
class HighlightClusterTopologyReport:
    """The highlight cluster-topology surface for one reading session/asset. Advisory, pure."""

    highlight_count: int
    cluster_count: int | None
    singleton_count: int | None
    singleton_fraction: float | None
    mean_cluster_size: float | None
    largest_cluster_size: int | None
    scatter_coefficient: float | None
    cluster_spans: tuple[ClusterSpan, ...]
    cluster_gap_threshold: float
    scattered_threshold: float
    clustered_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_highlight_cluster_topology(
    highlight_positions: Sequence[float],
    *,
    cluster_gap_threshold: float = _DEFAULT_CLUSTER_GAP_THRESHOLD,
    scattered_threshold: float = _DEFAULT_SCATTERED_THRESHOLD,
    clustered_threshold: float = _DEFAULT_CLUSTERED_THRESHOLD,
) -> HighlightClusterTopologyReport:
    r"""Measure the cluster topology of highlights in a document.

    ``highlight_positions`` are the normalized positions ``[0.0, 1.0]`` of each highlight
    (the route layer supplies these from the reading highlight log). Returns a
    :class:`HighlightClusterTopologyReport` with cluster statistics and verdict.

    Raises:
        ValueError: if thresholds are out of their valid ranges.
    """
    if not 0.0 < cluster_gap_threshold <= 1.0:
        raise ValueError(
            f"cluster_gap_threshold must be in (0.0, 1.0]; got {cluster_gap_threshold}"
        )
    if not 0.0 <= clustered_threshold <= 1.0:
        raise ValueError(
            f"clustered_threshold must be in [0.0, 1.0]; got {clustered_threshold}"
        )
    if not clustered_threshold <= scattered_threshold <= 1.0:
        raise ValueError(
            f"scattered_threshold ({scattered_threshold}) must be in "
            f"[clustered_threshold ({clustered_threshold}), 1.0]"
        )

    positions = sorted({min(max(p, 0.0), 1.0) for p in highlight_positions})
    highlight_count = len(positions)

    if highlight_count == 0:
        return HighlightClusterTopologyReport(
            highlight_count=0,
            cluster_count=None,
            singleton_count=None,
            singleton_fraction=None,
            mean_cluster_size=None,
            largest_cluster_size=None,
            scatter_coefficient=None,
            cluster_spans=(),
            cluster_gap_threshold=cluster_gap_threshold,
            scattered_threshold=scattered_threshold,
            clustered_threshold=clustered_threshold,
            verdict="unknown",
            notes=("no highlights — annotation topology unmeasurable",),
        )

    if highlight_count == 1:
        return HighlightClusterTopologyReport(
            highlight_count=1,
            cluster_count=1,
            singleton_count=1,
            singleton_fraction=1.0,
            mean_cluster_size=1.0,
            largest_cluster_size=1,
            scatter_coefficient=1.0,
            cluster_spans=(ClusterSpan(size=1, start_position=positions[0], end_position=positions[0]),),
            cluster_gap_threshold=cluster_gap_threshold,
            scattered_threshold=scattered_threshold,
            clustered_threshold=clustered_threshold,
            verdict="single_highlight",
            notes=(
                "one highlight — neither clustered nor scattered (honest base case "
                "distinct from unknown)",
            ),
        )

    clusters: list[list[float]] = []
    current: list[float] = [positions[0]]
    for pos in positions[1:]:
        gap = pos - current[-1]
        if gap <= cluster_gap_threshold:
            current.append(pos)
        else:
            clusters.append(current)
            current = [pos]
    clusters.append(current)

    cluster_count = len(clusters)
    singleton_count = sum(1 for c in clusters if len(c) == 1)
    singleton_fraction = singleton_count / cluster_count
    mean_cluster_size = highlight_count / cluster_count
    cluster_sizes = sorted((len(c) for c in clusters), reverse=True)
    largest_cluster_size = cluster_sizes[0]
    scatter_coefficient = singleton_count / highlight_count

    spans = tuple(
        sorted(
            (
                ClusterSpan(size=len(c), start_position=c[0], end_position=c[-1])
                for c in clusters
            ),
            key=lambda s: (s.size, s.start_position),
            reverse=True,
        )
    )

    if scatter_coefficient >= scattered_threshold:
        verdict = "scattered"
    elif scatter_coefficient <= clustered_threshold:
        verdict = "clustered"
    else:
        verdict = "mixed_topology"

    note_parts: list[str] = [
        f"{highlight_count} highlight(s), {cluster_count} cluster(s); "
        f"singleton_fraction {singleton_fraction:.2f} ({singleton_count} isolated), "
        f"mean_cluster_size {mean_cluster_size:.2f}, largest {largest_cluster_size}, "
        f"scatter_coefficient {scatter_coefficient:.2f}; verdict {verdict}",
        "cluster topology measures highlight CONTIGUITY — do marks form contiguous "
        "thematic clusters (deep local engagement) or scatter as isolated singletons "
        "(survey/skim)? ORTHOGONAL to highlight_density #1973 (per-passage mark DENSITY) "
        "and reading_engagement_distribution #1998 (Gini section CONCENTRATION): a doc "
        "with 20 highlights spread one-per-section and 20 bunched in 3 clusters can "
        "share density + distribution yet differ wholly in contiguity",
    ]
    if verdict == "scattered":
        note_parts.append(
            "scattered: highlights spread as isolated singletons — survey/skim reading "
            "shape, sampling broadly without sustained local engagement"
        )
    elif verdict == "clustered":
        note_parts.append(
            "clustered: highlights bunch into contiguous runs — deep local engagement "
            "with specific passages; a REAL measured verdict not default"
        )
    else:
        note_parts.append(
            "mixed_topology: a blend of clusters and singletons — the common realistic "
            "annotation shape"
        )
    note_parts.append(
        f"verdict {verdict}: cluster_gap_threshold {cluster_gap_threshold} "
        f"(two marks within {cluster_gap_threshold:.0%} of the doc are one cluster), "
        f"scattered_threshold {scattered_threshold}, clustered_threshold "
        f"{clustered_threshold}; DESCRIPTIVE not normative — scattered may be efficient "
        "survey reading; clustered may be narrow fixation; the operator judges reading "
        "intent"
    )

    return HighlightClusterTopologyReport(
        highlight_count=highlight_count,
        cluster_count=cluster_count,
        singleton_count=singleton_count,
        singleton_fraction=singleton_fraction,
        mean_cluster_size=mean_cluster_size,
        largest_cluster_size=largest_cluster_size,
        scatter_coefficient=scatter_coefficient,
        cluster_spans=spans,
        cluster_gap_threshold=cluster_gap_threshold,
        scattered_threshold=scattered_threshold,
        clustered_threshold=clustered_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
