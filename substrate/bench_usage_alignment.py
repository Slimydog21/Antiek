r"""Bench usage-alignment — does the benchmark's task-mix match how the platform is used?

Operator vision (ask #11): *"a benchmark called Antiek-bench ... recursive where it
learns from usage patterns to understand what worked and what didn't in a given week
to re-write the benchmark (and sub-benchmarks within it of differentiating tasks as
the platform expands)."* The recursive rewrite's FIRST job is to keep the benchmark
HONEST about what the platform actually does. A benchmark whose task distribution
drifts away from real usage optimizes for the wrong thing: it may over-weight a
surface the operator rarely touches (polishing a capability nobody uses) while
leaving BLIND SPOTS on surfaces used daily (the platform ships untested on the
workhorse path). As the platform expands (new reading modes, new research surfaces,
new Midnight Oil tasks), the bench must re-align its task-mix to the new usage
distribution — and nothing measures that alignment. This axis is the feedback signal
that tells the recursive rewrite WHERE to add or rebalance tasks.

**Genuinely distinct from every bench axis (load-bearing):**

* ``surface_coverage`` (#1889): does the bench touch each platform surface AT ALL
  (binary presence / activation energy)? This measures whether the bench's task
  PROPORTIONS match the usage PROPORTIONS (distribution alignment). A bench can
  cover every surface (#1889 full) yet be wildly mis-aligned (1 task on the
  workhorse surface + 50 tasks on a niche one — present everywhere, weighted
  wrong).
* ``task_redundancy`` (#1984): do two TASKS measure the same capability
  (task-task correlation)? This measures bench-vs-USAGE distribution overlap.
* ``bench_difficulty_coverage`` (#1999): does the bench span the difficulty
  SPECTRUM? This measures the surface/usage spectrum.
* ``task_discrimination`` (#1960): does a task SEPARATE models (inter-model
  variance)? This measures bench-vs-usage distribution.

NONE compares the bench's task distribution to the platform's USAGE distribution.
That is the recursion-learning signal: the benchmark re-writes itself toward usage.

**The measurement (hard to vary).** Given the bench's per-family task counts (the
task registry) and the platform's per-family usage counts (the recent usage log —
how many prompts/events landed on each surface family), normalize both to share
distributions over the UNION of families:

* ``bench_share[f] = bench_count[f] / total_bench_tasks``
* ``usage_share[f] = usage_count[f] / total_usage_events``

Then compute the DISTRIBUTION OVERLAP:

* ``alignment = sum over families of min(bench_share[f], usage_share[f])`` — the
  overlap coefficient of the two distributions, in ``[0, 1]``; ``1.0`` means the
  bench's task-mix is a perfect mirror of usage (every family weighted exactly as
  used), ``0.0`` means total disjoint (the bench and usage touch no family in
  common). Equivalently ``alignment = 1 - total_variation_distance`` where
  ``TVD = 0.5 * sum |bench_share - usage_share|``.
* ``bench_only_families`` — families the bench tests that saw ZERO usage (over-
  built: the bench polishes a capability nobody uses). Auditable.
* ``usage_only_families`` — families the platform USES that the bench never tests
  (BLIND SPOTS: the workhorse path ships untested). Auditable — the most
  actionable signal for the recursive rewrite (it MUST add tasks here).
* per-family ``FamilyAlignment`` (``family``, ``bench_count``, ``usage_count``,
  ``bench_share``, ``usage_share``, ``share_gap`` — auditable: the operator sees
  exactly which families are over/under-weighted).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero bench tasks OR zero usage events -> ``unknown`` (cannot align a distribution
  against nothing — defer, never fabricated ``aligned``).
* ``usage_only_families`` non-empty -> ``blind_spots`` (the bench is missing tasks
  for surfaces the platform actively uses — the worst drift; the recursive rewrite
  must add tasks here first. The MOST actionable state).
* ``alignment >= alignment_threshold`` (default ``0.80``) -> ``aligned`` (the bench
  mirrors usage — the recursive rewrite has nothing to fix; a REAL measured verdict,
  NOT the default).
* ``alignment < alignment_threshold`` (no blind spots, but proportions are off) ->
  ``drifted`` (the bench over/under-weights families vs usage — the recursive rewrite
  should rebalance task counts toward usage).

**DESCRIPTIVE NOT NORMATIVE:** ``drifted`` does NOT mean "bad" — a bench may
LEGITIMATELY over-weight hard frontier surfaces (more discrimination signal) or
under-weight a trivial surface (low value to test). ``blind_spots`` does NOT mean
"bad" — a new surface may be intentionally untested until it stabilizes. The
operator (and the recursive rewrite's authority layer) decides whether the
mis-alignment is a defect to fix or a deliberate design. This axis surfaces the FACT
of distribution alignment; it does not prescribe the right mix.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when either distribution is empty (zero bench tasks
  OR zero usage — alignment undefined against nothing).
* ``blind_spots`` is a REAL measured verdict (usage exists on a family the bench
  never tests), never the default.
* ``aligned`` is a REAL measured verdict (alignment >= threshold with both
  distributions present), never the default — ``unknown`` is the only defer state.
* ``alignment`` is bounded ``[0, 1]`` by construction (sum of mins of two share
  distributions that each sum to 1).
* a family present in BOTH distributions but with ``bench_count == 0`` cannot exist
  (counts are non-negative; ``bench_only`` / ``usage_only`` are the clean
  zero-presence partitions).
* ``alignment_threshold`` in ``(0.0, 1.0]`` (raises outside).
* every family auditable via ``family_alignments`` (bench/usage counts + shares +
  gap — no black-box alignment); ``bench_only`` / ``usage_only`` families surfaced
  as the actionable gaps.
* ``authority = "advisory"`` — pure layer proposes; operator consent (or the
  recursive-rewrite authority layer) executes. The bench axis NEVER dispatches a
  rewrite; it reports where one is warranted.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain count-map inputs; route layer adapts 1:1
  from the task registry + usage log).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

__all__ = [
    "FamilyAlignment",
    "BenchUsageAlignmentReport",
    "measure_bench_usage_alignment",
]

_DEFAULT_ALIGNMENT_THRESHOLD = 0.80


@dataclass(frozen=True)
class FamilyAlignment:
    """One surface family's bench-vs-usage alignment (auditable)."""

    family: str
    bench_count: int
    usage_count: int
    bench_share: float
    usage_share: float
    share_gap: float  # bench_share - usage_share (positive = over-weighted in bench)


@dataclass(frozen=True)
class BenchUsageAlignmentReport:
    """The bench-vs-usage distribution-alignment surface. Advisory, pure."""

    bench_task_count: int
    usage_event_count: int
    family_count: int
    alignment: float | None
    total_variation_distance: float | None
    bench_only_families: tuple[str, ...]
    usage_only_families: tuple[str, ...]
    family_alignments: tuple[FamilyAlignment, ...]
    alignment_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_bench_usage_alignment(
    bench_task_counts: Mapping[str, int],
    usage_counts: Mapping[str, int],
    *,
    alignment_threshold: float = _DEFAULT_ALIGNMENT_THRESHOLD,
) -> BenchUsageAlignmentReport:
    r"""Measure how well the bench's task distribution matches platform usage.

    ``bench_task_counts`` maps each task family/surface to its task count in the
    benchmark. ``usage_counts`` maps each family to its recent usage-event count on
    the platform (the route layer fills both from the task registry + usage log).
    Returns a :class:`BenchUsageAlignmentReport` with overlap, gaps, and verdict.

    Raises:
        ValueError: if ``alignment_threshold`` is outside ``(0.0, 1.0]``.
    """
    if not 0.0 < alignment_threshold <= 1.0:
        raise ValueError(
            f"alignment_threshold must be in (0.0, 1.0]; got {alignment_threshold}"
        )

    total_bench = sum(c for c in bench_task_counts.values() if c > 0)
    total_usage = sum(c for c in usage_counts.values() if c > 0)

    if total_bench == 0 or total_usage == 0:
        return BenchUsageAlignmentReport(
            bench_task_count=total_bench,
            usage_event_count=total_usage,
            family_count=0,
            alignment=None,
            total_variation_distance=None,
            bench_only_families=(),
            usage_only_families=(),
            family_alignments=(),
            alignment_threshold=alignment_threshold,
            verdict="unknown",
            notes=(
                "no bench tasks or no usage events — cannot align a distribution "
                f"against nothing (bench={total_bench}, usage={total_usage})",
            ),
        )

    families = sorted(set(bench_task_counts) | set(usage_counts))
    per_family: list[FamilyAlignment] = []
    bench_only: list[str] = []
    usage_only: list[str] = []
    overlap = 0.0

    for fam in families:
        bc = bench_task_counts.get(fam, 0)
        uc = usage_counts.get(fam, 0)
        bs = bc / total_bench
        us = uc / total_usage
        per_family.append(
            FamilyAlignment(
                family=fam,
                bench_count=bc,
                usage_count=uc,
                bench_share=bs,
                usage_share=us,
                share_gap=bs - us,
            )
        )
        overlap += min(bs, us)
        if bc > 0 and uc == 0:
            bench_only.append(fam)
        elif bc == 0 and uc > 0:
            usage_only.append(fam)

    # Sort per-family by absolute share gap descending (biggest mis-weights first).
    per_family.sort(key=lambda fa: (abs(fa.share_gap), fa.family), reverse=True)

    alignment = overlap
    total_variation = 1.0 - overlap

    if usage_only:
        verdict = "blind_spots"
    elif alignment >= alignment_threshold:
        verdict = "aligned"
    else:
        verdict = "drifted"

    note_parts: list[str] = [
        f"{total_bench} bench task(s), {total_usage} usage event(s) across "
        f"{len(families)} family(ies); alignment {alignment:.2f} "
        f"(TVD {total_variation:.2f}); verdict {verdict}",
        "alignment is the distribution OVERLAP of the bench task-mix vs the "
        "platform usage-mix (sum of per-family min shares), bounded [0,1]; 1.0 = "
        "the bench mirrors usage, 0.0 = totally disjoint — ORTHOGONAL to "
        "surface_coverage #1889 (binary surface PRESENCE): a bench can cover every "
        "surface yet be mis-aligned (1 task on the workhorse + 50 on a niche "
        "surface — present everywhere, weighted wrong)",
    ]
    if usage_only:
        note_parts.append(
            "blind_spots: the bench never tests family(ies) the platform actively "
            "uses — the worst drift; the recursive rewrite must add tasks here "
            "first. Usage-only: " + ", ".join(usage_only)
        )
    if bench_only:
        note_parts.append(
            "over-built: the bench tests family(ies) with zero platform usage — "
            "polishing a capability nobody uses. Bench-only: "
            + ", ".join(bench_only)
        )
    note_parts.append(
        "DESCRIPTIVE not normative: drifted may be deliberate (a bench may "
        "legitimately over-weight hard frontier surfaces for discrimination); "
        "blind_spots may be intentional (a new surface untested until stable); "
        "the operator / recursive-rewrite authority decides whether mis-alignment "
        "is a defect to fix or deliberate design"
    )
    note_parts.append(
        f"verdict {verdict}: alignment_threshold {alignment_threshold}; "
        "family_alignments carries per-family bench/usage counts + shares + gap "
        "(auditable, sorted by biggest absolute mis-weight)"
    )

    return BenchUsageAlignmentReport(
        bench_task_count=total_bench,
        usage_event_count=total_usage,
        family_count=len(families),
        alignment=alignment,
        total_variation_distance=total_variation,
        bench_only_families=tuple(bench_only),
        usage_only_families=tuple(usage_only),
        family_alignments=tuple(per_family),
        alignment_threshold=alignment_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
