r"""Bench task-novelty — is the benchmark evolving or frozen on a stale task set?

Operator vision (ask #11): *"a benchmark ... recursive where it learns from usage
patterns to understand what worked and what didn't in a given week to re-write the
benchmark (and sub-benchmarks within it of differentiating tasks as the platform
expands)."* The recursive rewrite's OUTPUT is a rotating task set. A benchmark that
FREEZES its tasks — running the exact same set every week — stops learning: it
optimizes for a fixed snapshot while the platform evolves around it. The signal that
the structure loop (#1843) is ACTUALLY working is task-set NOVELTY: what fraction of
this week's tasks are BRAND-NEW (never seen in ANY prior week) vs recycled from the
history. A high novelty rate means the bench is actively evolving — graduating stale
tasks and introducing new ones as the platform expands. A frozen task set (novelty
0) means the structure loop stalled — the rewrite isn't producing new tasks, or the
operator isn't consuming them. Nothing measures this against the FULL cumulative
history.

**Genuinely distinct from every bench axis (load-bearing):**

* ``task_rewrite`` (#1843): the PRODUCER — it emits/revises/graduates task diffs
  (the engine that rotates tasks). This measures the OUTCOME — did the rotation
  actually happen (what fraction of current tasks are brand-new)?
* ``week_diff`` (#1862): PAIRWISE comparison (this week vs LAST week — model score
  deltas + family churn). This measures against the FULL cumulative history (has a
  task EVER appeared in any prior week?). A task dropped in week 2 and re-introduced
  in week 3 is "new" in a pairwise diff (#1862 — absent last week) but "recycled"
  here (present in the full history). Full-history age is a different question from
  consecutive-week churn.
* ``task_redundancy`` (#1984): do two tasks measure the same CAPABILITY (inter-task
  correlation)? This measures whether tasks are NEW vs RECYCLED (set membership).
* ``surface_coverage`` (#1889): does the bench touch each surface AT ALL? This
  measures whether tasks are fresh (rotating) vs stale (frozen).
* ``bench_usage_alignment`` (#2003): does the task-MIX match usage distribution?
  This measures whether the task SET is evolving (regardless of mix).

NONE measures task-set age against the full history. That is the recursion-activeness
signal.

**The measurement (hard to vary).** Given the current week's task ids and the
cumulative set of task ids from ALL prior weeks (the route layer supplies both from
the task registry's versioned history):

* ``new_task_count`` — current tasks that NEVER appeared in any prior week.
* ``recycled_task_count`` — current tasks that appeared in at least one prior week.
* ``novelty_rate`` = ``new_task_count / current_task_count`` — the freshness fraction
  (``0.0`` = fully frozen, ``1.0`` = fully new rotation). ``None`` when no prior
  history exists (first week — defer, never fabricated: every task is trivially "new"
  when there's nothing to compare against).
* ``max_task_age_weeks`` — the oldest current task's age (how long the most-stale task
  has lingered). ``None`` when unmeasurable (no history or no recycled tasks).
* ``mean_task_age_weeks`` — average age of recycled tasks (the typical staleness).
  ``None`` when no recycled tasks or no history.
* per-task ``TaskAge`` (``task_id``, ``age_weeks`` — 0 for brand-new, cumulative for
  recycled; ``is_new`` — auditable: the operator sees exactly which tasks are fresh vs
  stale).

**Verdict (distinct honest states, never collapsed, DESCRIPTIVE not normative):**

* zero current tasks -> ``unknown`` (nothing to measure — defer, never fabricated).
* prior history empty (first week or no cumulative state) -> ``unknown`` (every task
  is trivially "new" when there's nothing to compare against — defer, never fabricated
  ``evolving`` or ``fully_novel``).
* ``novelty_rate == 0.0`` (WITH prior history) -> ``frozen`` (every task recycled —
  the structure loop stalled; the bench is a stale snapshot).
* ``novelty_rate < evolving_threshold`` (default ``0.30``) -> ``stagnant`` (mostly
  recycled — slow evolution; the bench rotates reluctantly).
* ``0.0 < novelty_rate < 1.0`` AND ``>= evolving_threshold`` -> ``evolving`` (a healthy
  blend of carried-over proven tasks and brand-new ones; the bench is actively learning.
  A REAL measured verdict, NOT the default).
* ``novelty_rate == 1.0`` -> ``fully_novel`` (complete rotation — every task brand-new;
  either a deliberate full refresh or a sign of over-churn where proven tasks were
  discarded wholesale).

**DESCRIPTIVE NOT NORMATIVE:** ``frozen`` does NOT mean "bad" — a stable benchmark may
LEGITIMATELY retain proven tasks for longitudinal model comparison (you NEED some
carry-over to compare models across weeks). ``fully_novel`` does NOT mean "good" —
complete rotation discards the longitudinal signal (no task spans weeks, so no
cross-week model comparison is possible). The operator (and the recursive-rewrite
authority layer) judges whether the novelty rate reflects healthy evolution (new
surfaces tested as the platform expands) or unhealthy churn (proven tasks discarded)
or unhealthy stagnation (frozen on a stale snapshot). This axis surfaces the FACT of
task-set age; it does not prescribe the right rotation rate.

**Honesty rules (load-bearing):**

* ``unknown`` never fabricates when zero current tasks OR zero prior history (first
  week — every task is trivially "new", defer, never fabricated ``evolving``).
* ``frozen`` is a REAL measured verdict (novelty_rate == 0.0 WITH prior history AND
  current tasks), never the default — distinct from ``unknown`` (no history) and from
  ``stagnant`` (some new tasks exist).
* ``evolving`` is a REAL measured verdict (healthy blend WITH history), never the
  default — ``unknown`` and ``frozen`` are the defer/stale states.
* ``novelty_rate`` is bounded ``[0.0, 1.0]`` by construction.
* ``max_task_age_weeks`` / ``mean_task_age_weeks`` are ``None`` when no prior history
  (defer — never ``0.0``; age is undefined without history to measure against) or when
  no recycled tasks exist (all-new set has no aged tasks).
* absolute thresholds (fraction of tasks, not normalized to task count or platform
  size): a 30% novelty rate is 30% whether the bench has 10 or 1000 tasks.
* every task auditable via ``task_ages`` (task_id + age + is_new — no black-box
  novelty); ``new_task_ids`` / ``recycled_task_ids`` surfaced as the actionable sets.
* task ids are de-duplicated (a repeated task in one week is one task, not many —
  mirrors graph edge-dedup discipline).
* ``authority = "advisory"`` — pure layer proposes; operator consent (or the
  recursive-rewrite authority layer) executes. The axis NEVER dispatches a rewrite;
  it reports whether the rewrite is happening.
* deterministic + immutable (frozen dataclasses; sorted, reproducible output).
* import-free of off-main siblings (plain id-set inputs; route layer adapts 1:1 from
  the task registry's versioned history).
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

__all__ = [
    "TaskAge",
    "BenchTaskNoveltyReport",
    "measure_bench_task_novelty",
]

_DEFAULT_EVOLVING_THRESHOLD = 0.30


@dataclass(frozen=True)
class TaskAge:
    """One current task's age/audit record."""

    task_id: str
    age_weeks: int  # 0 for brand-new; cumulative weeks present in history for recycled
    is_new: bool


@dataclass(frozen=True)
class BenchTaskNoveltyReport:
    """The bench task-set novelty surface for the current week. Advisory, pure."""

    current_task_count: int
    prior_history_count: int
    new_task_count: int | None
    recycled_task_count: int | None
    novelty_rate: float | None
    max_task_age_weeks: int | None
    mean_task_age_weeks: float | None
    task_ages: tuple[TaskAge, ...]
    new_task_ids: tuple[str, ...]
    recycled_task_ids: tuple[str, ...]
    evolving_threshold: float
    verdict: str
    notes: tuple[str, ...]
    authority: str = "advisory"


def measure_bench_task_novelty(
    current_task_ids: Sequence[str],
    prior_weekly_task_sets: Sequence[Sequence[str]],
    *,
    evolving_threshold: float = _DEFAULT_EVOLVING_THRESHOLD,
) -> BenchTaskNoveltyReport:
    r"""Measure the task-set novelty of the current bench week.

    ``current_task_ids`` are this week's task ids. ``prior_weekly_task_sets`` is the
    list of task-id lists from ALL prior weeks (index 0 = oldest; the route layer
    supplies these from the task registry's versioned history). Returns a
    :class:`BenchTaskNoveltyReport` with novelty statistics and verdict.

    Raises:
        ValueError: if ``evolving_threshold`` is outside ``(0.0, 1.0]``.
    """
    if not 0.0 < evolving_threshold <= 1.0:
        raise ValueError(
            f"evolving_threshold must be in (0.0, 1.0]; got {evolving_threshold}"
        )

    current = sorted(set(current_task_ids))
    current_count = len(current)

    # Build cumulative prior-history set and per-task age (weeks since first appearance).
    prior_history: set[str] = set()
    task_first_seen: dict[str, int] = {}  # task -> week index of earliest appearance
    prior_week_count = len(prior_weekly_task_sets)
    for week_idx, week_tasks in enumerate(prior_weekly_task_sets):
        for tid in week_tasks:
            prior_history.add(tid)
            if tid not in task_first_seen:
                task_first_seen[tid] = week_idx

    if current_count == 0:
        return BenchTaskNoveltyReport(
            current_task_count=0,
            prior_history_count=len(prior_history),
            new_task_count=None,
            recycled_task_count=None,
            novelty_rate=None,
            max_task_age_weeks=None,
            mean_task_age_weeks=None,
            task_ages=(),
            new_task_ids=(),
            recycled_task_ids=(),
            evolving_threshold=evolving_threshold,
            verdict="unknown",
            notes=("no current tasks — novelty unmeasurable",),
        )

    if not prior_history:
        return BenchTaskNoveltyReport(
            current_task_count=current_count,
            prior_history_count=0,
            new_task_count=None,
            recycled_task_count=None,
            novelty_rate=None,
            max_task_age_weeks=None,
            mean_task_age_weeks=None,
            task_ages=(),
            new_task_ids=(),
            recycled_task_ids=(),
            evolving_threshold=evolving_threshold,
            verdict="unknown",
            notes=(
                "no prior history — every current task is trivially 'new' (nothing "
                "to compare against); defer, never fabricated evolving",
            ),
        )

    new_ids: list[str] = []
    recycled_ids: list[str] = []
    ages: list[TaskAge] = []
    recycled_ages: list[int] = []

    for tid in current:
        if tid in prior_history:
            recycled_ids.append(tid)
            first_week = task_first_seen[tid]
            age = prior_week_count - first_week
            recycled_ages.append(age)
            ages.append(TaskAge(task_id=tid, age_weeks=age, is_new=False))
        else:
            new_ids.append(tid)
            ages.append(TaskAge(task_id=tid, age_weeks=0, is_new=True))

    new_count = len(new_ids)
    recycled_count = len(recycled_ids)
    novelty_rate = new_count / current_count
    max_age = max(recycled_ages) if recycled_ages else 0
    mean_age = sum(recycled_ages) / recycled_count if recycled_count else 0.0

    if novelty_rate == 0.0:
        verdict = "frozen"
    elif novelty_rate == 1.0:
        verdict = "fully_novel"
    elif novelty_rate >= evolving_threshold:
        verdict = "evolving"
    else:
        verdict = "stagnant"

    note_parts: list[str] = [
        f"{current_count} current task(s), {len(prior_history)} in prior history; "
        f"{new_count} new, {recycled_count} recycled; novelty_rate {novelty_rate:.2f}, "
        f"max_age {max_age} week(s), mean_age {mean_age:.1f} week(s); verdict {verdict}",
        "task-novelty measures task-set AGE against the FULL cumulative history — "
        "what fraction of current tasks are brand-new (never seen in ANY prior week) "
        "vs recycled? ORTHOGONAL to task_rewrite #1843 (the PRODUCER), week_diff #1862 "
        "(PAIRWISE last-week comparison), task_redundancy #1984 (capability "
        "correlation), surface_coverage #1889 (surface presence), bench_usage_"
        "alignment #2003 (mix match). A task dropped in week 2 and re-introduced in "
        "week 3 is 'new' in #1862 pairwise but 'recycled' here (present in full "
        "history). Full-history age is a different question from consecutive-week churn",
    ]
    if verdict == "frozen":
        note_parts.append(
            "frozen: every task recycled — the structure loop stalled; the bench is "
            "a stale snapshot not evolving"
        )
    elif verdict == "stagnant":
        note_parts.append(
            "stagnant: mostly recycled tasks — slow evolution; the bench rotates "
            "reluctantly"
        )
    elif verdict == "evolving":
        note_parts.append(
            "evolving: a healthy blend of carried-over proven tasks and brand-new "
            "ones — the bench is actively learning; a REAL measured verdict not default"
        )
    else:  # fully_novel
        note_parts.append(
            "fully_novel: complete rotation — every task brand-new; either a "
            "deliberate full refresh or over-churn discarding proven tasks (no "
            "cross-week longitudinal signal)"
        )
    note_parts.append(
        f"verdict {verdict}: evolving_threshold {evolving_threshold}; DESCRIPTIVE not "
        "normative — frozen may legitimately retain proven tasks for longitudinal "
        "model comparison; fully_novel may discard the cross-week signal; the operator "
        "/ recursive-rewrite authority judges healthy evolution vs over-churn vs "
        "stagnation"
    )

    return BenchTaskNoveltyReport(
        current_task_count=current_count,
        prior_history_count=len(prior_history),
        new_task_count=new_count,
        recycled_task_count=recycled_count,
        novelty_rate=novelty_rate,
        max_task_age_weeks=max_age,
        mean_task_age_weeks=mean_age,
        task_ages=tuple(ages),
        new_task_ids=tuple(new_ids),
        recycled_task_ids=tuple(recycled_ids),
        evolving_threshold=evolving_threshold,
        verdict=verdict,
        notes=tuple(note_parts),
    )
