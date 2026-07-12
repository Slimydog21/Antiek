"""Week-over-week bench diff — the "what changed" signal (ask #11 recursion).

The operator's vision (ask #11): *"...a benchmark... that benchmarked
performance... so that I can know on a weekly basis what models are best at what
tasks; I would like for the benchmark to be recursive where it learns from usage
patterns to understand what worked and what didn't in a given week to re-write
the benchmark..."* The execution stack scores runs; the weekly render (#1858)
presents one week. But the RECURSION needs a comparison: what CHANGED week over
week — which models improved, which regressed, which task families shifted? THAT
signal is what the rewrite loops (#1831 weights, #1843 structure) learn from.
This module is the pure diff that turns two weekly snapshots into that signal.

**Why pure + import-free of #1858.** #1858 (the renderer) ships in a separate
off-main PR. Hard-importing its snapshot shapes would stack two PRs and break
independent bar-cleanliness on a frozen main. Instead this module defines
compatible input shapes (the minimal ``WeeklyModelResult`` interface) that the
route layer adapts from #1858's ``WeeklyBenchSnapshot``. The diff owns the ONE
thing no other module does: the **pairwise comparison** with honest handling of
unknowns, new entries, and dropped entries.

**The load-bearing invariants (each is a test):**

1. **A model present in only one week is NEVER compared against a fabricated
   zero.** A model new this week → ``direction="new"`` (delta ``None``). A model
   absent this week → ``direction="dropped"`` (delta ``None``). Inventing a 0 for
   the missing side would fabricate a 100% regression/improvement — a lie.
2. **An unknown never produces a numeric delta.** If EITHER week's score is
   ``None`` (pending/incomplete run), the delta is ``None`` and the direction is
   ``"unknown"``. "We don't know this week" is not "-0.0 change."
3. **Direction uses a noise floor (epsilon).** A delta within ``±epsilon`` is
   ``"unchanged"`` — floating-point noise and genuinely stable scores are not
   misreported as movement. Default epsilon is ``1e-9`` (exact-equality stable);
   a caller may raise it to suppress sub-percentage noise.
4. **Every delta is auditable.** Both the previous and current scores survive on
   the :class:`ScoreDelta` alongside the computed delta and direction — a
   reviewer can reproduce the verdict, not trust a black-box label.
5. **Task-family churn is surfaced separately.** A task family present in one
   week but not the other is ``new_task_families`` / ``dropped_task_families``,
   not silently merged into model-level deltas (a new family is a structure
   change, which the #1843 structure loop acts on).
6. **The summary counts are real.** ``improved_count`` / ``regressed_count`` /
   ``unchanged_count`` / ``unknown_count`` / ``new_count`` / ``dropped_count``
   partition every comparable exactly once — no double-counting, no omission.
7. **Deterministic + pure.** Same two snapshots → byte-identical diff. No I/O,
   no clock, no dispatch. Ordered by (task_family, model_id) for stable output.

**Composition (the recursive loop):**

    week N snapshot  ─┐
                      ├─→ diff_weeks(prev, current) → WeekOverWeekDiff (THIS)
    week N+1 snapshot ─┘                    │
                                            ├─→ #1831 weight loop (regressed task → down-weight)
                                            ├─→ #1843 structure loop (new family → expand)
                                            └─→ #1858 render (show the delta to the operator)

The diff is the connective tissue between "scored the runs" and "rewrote the
benchmark" — without it the loop has no gradient to descend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

# A delta within ±epsilon is "unchanged" (float-noise / genuinely stable).
DEFAULT_EPSILON: float = 1e-9


class WeekDiffError(ValueError):
    """A diff input violates a load-bearing invariant."""


@dataclass(frozen=True)
class WeeklyModelResult:
    """One model's result in one task family for one week.

    Compatible with #1858's ``ModelScore`` (the route layer adapts). ``mean_score``
    is ``None`` when the model had no completed runs that week (pending/unknown).
    """

    task_family: str
    model_id: str
    mean_score: float | None
    completed_runs: int = 0
    pending_runs: int = 0


@dataclass(frozen=True)
class WeekSnapshot:
    """One week's bench results, keyed by (task_family, model_id)."""

    week_id: str
    results: tuple[WeeklyModelResult, ...]
    incomplete: bool = False


@dataclass(frozen=True)
class ScoreDelta:
    """One (task_family, model_id) comparison across two weeks.

    ``delta`` is ``current - previous`` when both known; ``None`` when either is
    unknown OR the entry is new/dropped. ``direction`` is the human-readable
    verdict. Both raw scores survive for auditability.
    """

    task_family: str
    model_id: str
    previous_score: float | None
    current_score: float | None
    delta: float | None
    direction: str  # improved / regressed / unchanged / unknown / new / dropped


@dataclass(frozen=True)
class WeekOverWeekDiff:
    """The full week-over-week comparison."""

    previous_week_id: str
    current_week_id: str
    deltas: tuple[ScoreDelta, ...]  # ordered by (task_family, model_id)
    new_task_families: tuple[str, ...]
    dropped_task_families: tuple[str, ...]
    improved_count: int = 0
    regressed_count: int = 0
    unchanged_count: int = 0
    unknown_count: int = 0
    new_count: int = 0
    dropped_count: int = 0
    honesty_notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_comparables(self) -> int:
        return (
            self.improved_count
            + self.regressed_count
            + self.unchanged_count
            + self.unknown_count
            + self.new_count
            + self.dropped_count
        )


def _index_by_key(
    snapshot: WeekSnapshot,
) -> dict[tuple[str, str], WeeklyModelResult]:
    """Index results by (task_family, model_id)."""
    index: dict[tuple[str, str], WeeklyModelResult] = {}
    for result in snapshot.results:
        key = (result.task_family, result.model_id)
        if key in index:
            raise WeekDiffError(
                f"duplicate (task_family, model_id) in week {snapshot.week_id!r}: {key}"
            )
        index[key] = result
    return index


def _task_families(snapshot: WeekSnapshot) -> set[str]:
    return {result.task_family for result in snapshot.results}


def _direction_and_delta(
    previous: float | None, current: float | None, epsilon: float
) -> tuple[float | None, str]:
    if previous is None or current is None:
        return None, "unknown"
    delta = current - previous
    if delta > epsilon:
        return delta, "improved"
    if delta < -epsilon:
        return delta, "regressed"
    return delta, "unchanged"


def diff_weeks(
    previous: WeekSnapshot,
    current: WeekSnapshot,
    *,
    epsilon: float = DEFAULT_EPSILON,
) -> WeekOverWeekDiff:
    """Compare two weekly bench snapshots; surface improvements/regressions/churn.

    Returns a :class:`WeekOverWeekDiff` partitioning every (task_family, model_id)
    entry into exactly one direction. Pure + deterministic.

    ``epsilon`` is the noise floor: a delta within ±epsilon is "unchanged".
    """
    if epsilon < 0:
        raise WeekDiffError(f"epsilon must be >= 0 (got {epsilon})")
    if not previous.week_id.strip() or not current.week_id.strip():
        raise WeekDiffError("week_id must be non-empty on both snapshots")
    if previous.week_id == current.week_id:
        raise WeekDiffError(
            "previous and current week_id must differ "
            f"(both {previous.week_id!r}); cannot diff a week against itself"
        )

    prev_index = _index_by_key(previous)
    curr_index = _index_by_key(current)

    prev_families = _task_families(previous)
    curr_families = _task_families(current)
    new_families = tuple(sorted(curr_families - prev_families))
    dropped_families = tuple(sorted(prev_families - curr_families))

    all_keys = sorted(set(prev_index) | set(curr_index))

    deltas: list[ScoreDelta] = []
    counts = {"improved": 0, "regressed": 0, "unchanged": 0, "unknown": 0, "new": 0, "dropped": 0}
    notes: list[str] = []

    for key in all_keys:
        task_family, model_id = key
        prev_result = prev_index.get(key)
        curr_result = curr_index.get(key)
        prev_score = prev_result.mean_score if prev_result else None
        curr_score = curr_result.mean_score if curr_result else None

        if prev_result is None and curr_result is not None:
            direction = "new"
            delta = None
        elif curr_result is None and prev_result is not None:
            direction = "dropped"
            delta = None
        else:
            assert prev_result is not None and curr_result is not None
            delta, direction = _direction_and_delta(prev_score, curr_score, epsilon)

        counts[direction] += 1
        deltas.append(
            ScoreDelta(
                task_family=task_family,
                model_id=model_id,
                previous_score=prev_score,
                current_score=curr_score,
                delta=delta,
                direction=direction,
            )
        )

    if previous.incomplete or current.incomplete:
        notes.append(
            "one or both weeks are incomplete — unknown deltas may resolve when "
            "pending runs complete"
        )

    return WeekOverWeekDiff(
        previous_week_id=previous.week_id,
        current_week_id=current.week_id,
        deltas=tuple(deltas),
        new_task_families=new_families,
        dropped_task_families=dropped_families,
        improved_count=counts["improved"],
        regressed_count=counts["regressed"],
        unchanged_count=counts["unchanged"],
        unknown_count=counts["unknown"],
        new_count=counts["new"],
        dropped_count=counts["dropped"],
        honesty_notes=tuple(notes),
    )


def regressions(diff: WeekOverWeekDiff) -> tuple[ScoreDelta, ...]:
    """Return only the regressed entries (the rewrite loops' primary signal).

    A regression is the strongest "what didn't work" signal: a model that got
    worse at a task family. The weight loop (#1831) down-weights; the operator
    investigates. Convenience filter over ``diff.deltas``.
    """
    return tuple(d for d in diff.deltas if d.direction == "regressed")


def improvements(diff: WeekOverWeekDiff) -> tuple[ScoreDelta, ...]:
    """Return only the improved entries (the "what worked" signal)."""
    return tuple(d for d in diff.deltas if d.direction == "improved")


__all__ = [
    "DEFAULT_EPSILON",
    "WeekDiffError",
    "WeeklyModelResult",
    "WeekSnapshot",
    "ScoreDelta",
    "WeekOverWeekDiff",
    "diff_weeks",
    "regressions",
    "improvements",
]
