r"""Twin-recursion coverage — does EVERY asset have a twin? (the universality invariant)

Operator vision (ask #4): *"every information asset created on my platform has a
twin document with all the insights and questions proposed by that information
document written by an LLM as LLMs are perfect note takers, then that substrate
of information can be merged, referenced, and leveraged in combining contexts or
doing intelligent search over my dream of an infinite information platform."* The
invariant is **UNIVERSALITY** — every asset, by virtue of existing on the platform,
must have a twin. The twin RECURSION is what makes the platform an *infinite*
information platform: each asset generates a twin-note, and that substrate is what
intelligent search, merge, and cross-context leverage operate over. A gap in the
recursion (an asset with no twin) is a hole in the searchable substrate — that
asset's distilled insights/questions are invisible to every downstream feature.

**Genuinely distinct (different object + different question):**

Every existing twin axis takes a SINGLE ``(source, twin)`` pair and judges the
twin's CONTENT quality:

* ``twin_coverage`` (#1964): did ONE twin capture its source's content (recall
  over the source's distinctive terms)?
* ``twin_question_coverage`` (#2028): did ONE twin recall the source's questions?
* ``twin_fidelity`` (#1954): did ONE twin hallucinate?
* ``twin_staleness`` (#1975): is ONE twin out of date with its source?
* ``twin_internal_coherence`` (#1988): do ONE twin's insights connect?

ALL of these PRESUPPOSE the twin exists and measure its quality. NONE asks whether
the twin EXISTS for every asset. THIS axis operates on the WHOLE asset set and
measures the recursion's COMPLETENESS — of every asset in the knowledge base, how
many have a twin at all? A knowledge base can have perfect twins (every existing
twin faithful, fresh, complete) yet be 30% orphaned — and that violates the
foundational promise regardless of how good the existing twins are. The recursion's
completeness is the precondition for every twin-quality axis to even apply.

**The measurement (hard to vary).** Given the knowledge base's assets and the set
of twin bindings (each binding says "asset ``a`` has twin ``t``"):

* **ORPHAN ASSET** — an asset named by NO binding. The recursion gap: this asset's
  distilled insights/questions were never generated, so it is invisible to
  twin-substrate search (#1844), merge leverage, and cross-context combination.
  The primary failure mode.
* **DANGLING TWIN** — a binding whose ``asset_id`` is NOT in the asset set. A twin
  pointing at nothing — an integrity leak (a twin-note whose source has vanished
  or was never declared). Surfaced separately; it is NOT the same failure as an
  orphan asset.
* **MULTI-BOUND ASSET** — an asset named by >=2 DISTINCT bindings. The operator's
  invariant is "a twin document" (singular); >1 twin per asset is a structural
  anomaly (which twin is authoritative?). Surfaced, not collapsed into the verdict.

* ``twin_coverage_rate = bound_assets / asset_count`` in ``[0,1]`` — the
  universality ratio (1.0 = every asset has a twin); ``None`` when there are zero
  assets (defer — never fabricated as perfectly covered).
* ``binding_rate = bound_bindings / total_bindings`` in ``[0,1]`` — do twins
  resolve to real assets (1.0 = no dangling); ``None`` when there are zero twins.

**Verdict (distinct honest states, never collapsed):**

* zero assets -> ``unknown`` (defer — nothing to cover; ``twin_coverage_rate`` and
  ``binding_rate`` are ``None``, never fabricated).
* ``orphan_asset_count >= 1`` -> ``partial`` (the recursion is INCOMPLETE: at
  least one asset has no twin; the substrate has a hole). This is the primary
  failure mode and dominates the verdict.
* ``orphan_asset_count == 0`` -> ``universal`` (every asset has at least one twin;
  the universality invariant holds on the asset side).

The dangling-twin and multi-bind anomalies are carried as SEPARATE auditable
fields (``dangling_twin_*``, ``multi_bound_asset_*``) and never collapsed into the
verdict — they answer a DIFFERENT question (twin-side integrity / structural
anomaly), not the recursion-completeness question.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates coverage when there are no assets to cover.
* ``twin_coverage_rate == 0.0`` is a REAL verdict (``partial``): assets were
  measured and NONE has a twin — measured absence, NOT ``unknown``.
* ``binding_rate`` is ``None`` only when there are zero twins (a binding rate over
  zero twins is undefined, defer).
* Duplicate ``(asset_id, twin_id)`` bindings are de-duplicated before counting
  (listing the same twin twice is one twin, not multi-bind).
* Empty/blank ``asset_id`` or ``twin_id`` rejected (integrity); duplicate asset
  ids in the ``assets`` input rejected (caller error).
* Deterministic and pure: same inputs -> same report. No LLM, no network, no
  clock, no mutation. ``authority`` is always ``"advisory"``.

**Import-free of off-main siblings.** No twin substrate is on frozen
``origin/main``; this module takes plain asset-id strings and ``TwinBinding``
records (the route layer adapts 1:1 from the persistence twin-link table).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TwinBinding",
    "TwinRecursionReport",
    "TwinRecursionCoverageError",
    "measure_twin_recursion_coverage",
]


@dataclass(frozen=True)
class TwinBinding:
    """One declared twin link: asset ``asset_id`` has twin ``twin_id``.

    Attributes:
        asset_id: the source asset's id (must be a declared asset to be bound).
        twin_id: the twin document's id.
    """

    asset_id: str
    twin_id: str


@dataclass(frozen=True)
class TwinRecursionReport:
    """The twin-recursion-coverage verdict. Advisory, pure.

    Attributes:
        asset_count: assets in the knowledge base.
        twin_count: distinct twins declared (after de-duplication).
        orphan_asset_count: assets named by NO binding (the recursion gap).
        orphan_asset_ids: ids of orphan assets, sorted.
        dangling_twin_count: bindings whose asset is NOT in the asset set.
        dangling_twin_ids: ids of dangling twins, sorted.
        multi_bound_asset_count: assets named by >=2 distinct bindings.
        multi_bound_asset_ids: ids of multi-bound assets, sorted.
        twin_coverage_rate: bound_assets / asset_count; ``None`` when unknown.
        binding_rate: bound_bindings / total_bindings; ``None`` when no twins.
        verdict: ``universal`` / ``partial`` / ``unknown``.
        notes: human-readable accountability strings.
        authority: always ``"advisory"``.
    """

    asset_count: int
    twin_count: int
    orphan_asset_count: int
    orphan_asset_ids: tuple[str, ...]
    dangling_twin_count: int
    dangling_twin_ids: tuple[str, ...]
    multi_bound_asset_count: int
    multi_bound_asset_ids: tuple[str, ...]
    twin_coverage_rate: float | None
    binding_rate: float | None
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


class TwinRecursionCoverageError(ValueError):
    """Malformed twin-recursion input (blank id, duplicate asset ids)."""


def measure_twin_recursion_coverage(
    assets: Sequence[str],
    twin_bindings: Sequence[TwinBinding],
) -> TwinRecursionReport:
    """Measure the completeness of the twin recursion across the asset set.

    ``assets`` are the ids of every asset in the knowledge base.
    ``twin_bindings`` are the declared asset->twin links. Returns a
    :class:`TwinRecursionReport` stating whether the recursion is universal
    (every asset has a twin) or partial (at least one orphan), plus the
    dangling-twin and multi-bind anomaly counts.

    Raises:
        TwinRecursionCoverageError: if an asset id is blank, the ``assets``
            input contains duplicates, or a binding carries a blank id.
    """
    # Validate + de-duplicate the asset set (caller supplies the canonical list).
    asset_set: set[str] = set()
    for asset_id in assets:
        if not isinstance(asset_id, str) or not asset_id.strip():
            raise TwinRecursionCoverageError("asset ids must be non-blank strings")
        if asset_id in asset_set:
            raise TwinRecursionCoverageError(
                f"duplicate asset id in input: {asset_id!r}"
            )
        asset_set.add(asset_id)

    # Validate + de-duplicate bindings on (asset_id, twin_id).
    seen_pairs: set[tuple[str, str]] = set()
    bindings: list[TwinBinding] = []
    for binding in twin_bindings:
        if not binding.asset_id.strip() or not binding.twin_id.strip():
            raise TwinRecursionCoverageError(
                "twin bindings must carry non-blank asset_id and twin_id"
            )
        pair = (binding.asset_id, binding.twin_id)
        if pair in seen_pairs:
            continue  # identical binding listed twice = one twin
        seen_pairs.add(pair)
        bindings.append(binding)

    total_assets = len(asset_set)
    total_twins = len(bindings)

    if total_assets == 0:
        return TwinRecursionReport(
            asset_count=0,
            twin_count=total_twins,
            orphan_asset_count=0,
            orphan_asset_ids=(),
            dangling_twin_count=total_twins,
            dangling_twin_ids=tuple(sorted(b.twin_id for b in bindings)),
            multi_bound_asset_count=0,
            multi_bound_asset_ids=(),
            twin_coverage_rate=None,
            binding_rate=None,
            verdict="unknown",
            notes=(
                "no assets to cover — twin_coverage_rate and binding_rate are "
                "None, never fabricated",
            ),
        )

    # Classify bindings: bound (asset exists) vs dangling (asset absent).
    bound_assets: set[str] = set()
    multi_bound: set[str] = set()
    dangling_twins: list[str] = []
    asset_hit: dict[str, int] = {}

    for binding in bindings:
        if binding.asset_id in asset_set:
            bound_assets.add(binding.asset_id)
            hits = asset_hit.get(binding.asset_id, 0) + 1
            asset_hit[binding.asset_id] = hits
            if hits >= 2:
                multi_bound.add(binding.asset_id)
        else:
            dangling_twins.append(binding.twin_id)

    orphan_assets = asset_set - bound_assets

    twin_coverage_rate = len(bound_assets) / total_assets
    binding_rate = (
        (total_twins - len(dangling_twins)) / total_twins
        if total_twins
        else None
    )

    orphan_asset_ids = tuple(sorted(orphan_assets))
    dangling_twin_ids = tuple(sorted(dangling_twins))
    multi_bound_ids = tuple(sorted(multi_bound))

    note_parts: list[str] = [
        f"{len(bound_assets)}/{total_assets} assets have a twin "
        f"(twin_coverage_rate {twin_coverage_rate:.0%})",
        f"{len(orphan_assets)} orphan asset(s), {len(dangling_twins)} dangling "
        f"twin(s), {len(multi_bound)} multi-bound asset(s)",
    ]

    if orphan_assets:
        verdict = "partial"
        note_parts.append(
            f"recursion INCOMPLETE — {len(orphan_assets)} asset(s) have no twin "
            f"(the substrate has holes invisible to twin-substrate search)"
        )
    else:
        verdict = "universal"
        note_parts.append(
            "universality invariant HOLDS — every asset has at least one twin"
        )

    if dangling_twins:
        note_parts.append(
            f"{len(dangling_twins)} dangling twin(s) point at undeclared assets "
            f"(integrity leak — separate from the coverage verdict)"
        )
    if multi_bound:
        note_parts.append(
            f"{len(multi_bound)} asset(s) have >1 twin (structural anomaly — "
            f"the invariant is 'a twin' singular)"
        )

    return TwinRecursionReport(
        asset_count=total_assets,
        twin_count=total_twins,
        orphan_asset_count=len(orphan_assets),
        orphan_asset_ids=orphan_asset_ids,
        dangling_twin_count=len(dangling_twins),
        dangling_twin_ids=dangling_twin_ids,
        multi_bound_asset_count=len(multi_bound),
        multi_bound_asset_ids=multi_bound_ids,
        twin_coverage_rate=twin_coverage_rate,
        binding_rate=binding_rate,
        verdict=verdict,
        notes=tuple(note_parts),
    )
