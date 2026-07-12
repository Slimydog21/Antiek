"""Benchmark self-rewriting engine — the task-STRUCTURE recursion (ask #11).

The operator's ask #11: *"...recursive where it learns from usage patterns to
understand what worked and what didn't in a given week to re-write the benchmark
(and sub-benchmarks within it of differentiating tasks as the platform
expands)."* This is **two** loops, not one:

  * **Weight loop** — #1831 ``weekly.close_week`` (and #810
    ``propose_next_week_weights``): continuous redistribution of emphasis across
    the *existing* task set (failure-driven Laplace weights, summing to 1.0).
  * **Structure loop** — THIS module: discrete task *diffs* — emit a task for a
    new platform surface, revise a task whose scores are too noisy to be a fair
    signal, graduate a task every model aces (no longer differentiating), or
    retire one that no longer earns its place.

The two are complementary: weights answer "how much to run each task"; the
structure loop answers "which tasks should exist at all." Both feed
"re-write the benchmark"; conflating them would hide the structure decisions
behind a continuous knob (hard to vary → wrong).

**Pure — no I/O, no clock, no dispatch, no LLM.** A pure function over the
evidence and surface signals handed to it. The caller records the proposed diffs
and (with operator authority) applies them to the registry — this module only
*proposes*, never mutates. That mirrors the authority split everywhere in the
bench lane: the pure layer never dispatches or commits.

**Honesty rules (load-bearing):**

  * **No evidence → no diff.** A task with fewer than ``min_runs_for_evidence``
    measured runs produces no structural verdict — "we haven't measured this
    enough to rewrite it" is honest silence, not a guess. (Inventing a graduate
    or retire verdict from thin air would corrupt the benchmark.)
  * **EMIT only from an explicit surface signal.** A new task family is emitted
    ONLY when the caller hands a ``PlatformSurfaceSignal`` naming it (the
    platform gained a new capability). The engine never invents a family from
    nothing — "as the platform expands" is operator/caller-grounded, not
    LLM-fabricated.
  * **Cannot retire the last task in a family.** Retiring the only task in a
    family would erase that family's coverage with nothing to replace it. The
    engine refuses (the diff is dropped with a note) rather than silently
    producing an empty family.
  * **A saturated task GRADUATES, it is not silently dropped.** A task every
    model aces (``success_rate >= graduate_threshold`` over enough runs) is
    marked ``graduate`` with a rationale, not removed — the operator decides
    whether to replace it. Saturated ≠ irrelevant.
  * **Version bumps iff the proposal is non-empty.** An empty diff keeps the
    benchmark version (cross-week scores stay comparable). A non-empty diff
    bumps it and the bump is recorded — honest about *when* comparability breaks.
  * **Variance → revise, not blame.** A task whose scores have high variance is
    flagged ``revise`` (the task definition is ambiguous, not the model bad).
    This is the "understand what worked and what didn't" the operator named.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from statistics import variance


class TaskRewriteError(ValueError):
    """A rewrite input violates a load-bearing invariant."""


@dataclass(frozen=True)
class TaskEvidence:
    """One task's measured outcomes for a week.

    ``scores`` are the finite per-run scores (the same float the bench scorer
    produced). ``n_runs`` is kept explicit so an evidence record with zero runs
    (a task that exists but was not measured this week) is representable and
    distinguishable from "not enough runs."
    """

    task_id: str
    family: str
    n_runs: int
    n_success: int
    scores: tuple[float, ...] = ()

    @property
    def success_rate(self) -> float | None:
        if self.n_runs <= 0:
            return None
        return self.n_success / self.n_runs

    @property
    def score_variance(self) -> float | None:
        if len(self.scores) < 2:
            return None
        return variance(self.scores)


@dataclass(frozen=True)
class PlatformSurfaceSignal:
    """A new platform capability the benchmark should grow to cover.

    ``proposed_task_id`` is a stable id (``{family}::{slug}``, matching the
    registry convention); ``prompt``/``scoring`` are advisory seeds the operator
    may revise. The engine emits a ``TaskDiff(kind="emit")`` for each signal —
    it never fabricates one without a signal.
    """

    family: str
    proposed_task_id: str
    rationale: str
    prompt: str | None = None
    scoring: str | None = None


@dataclass(frozen=True)
class TaskDiff:
    """One proposed structural change to the benchmark task set."""

    kind: str  # "emit" | "revise" | "retire" | "graduate"
    family: str
    task_id: str
    rationale: str
    proposed_prompt: str | None = None
    proposed_scoring: str | None = None


@dataclass(frozen=True)
class RewriteThresholds:
    """Hard-to-vary knobs governing when a structural verdict fires."""

    min_runs_for_evidence: int = 3
    graduate_success_rate: float = 1.0
    revise_variance: float = 0.25

    def __post_init__(self) -> None:
        if self.min_runs_for_evidence < 1:
            raise TaskRewriteError("min_runs_for_evidence must be >= 1")
        if not (0.0 <= self.graduate_success_rate <= 1.0):
            raise TaskRewriteError(
                f"graduate_success_rate must be in [0.0, 1.0], got {self.graduate_success_rate}"
            )
        if self.revise_variance < 0:
            raise TaskRewriteError("revise_variance must be >= 0")


@dataclass(frozen=True)
class TaskRewriteProposal:
    """A week's structural rewrite proposal. Pure value; never mutates a registry."""

    benchmark_version_from: int
    benchmark_version_to: int
    diffs: tuple[TaskDiff, ...] = ()
    notes: tuple[str, ...] = ()
    families_affected: tuple[str, ...] = field(default_factory=tuple)

    @property
    def has_changes(self) -> bool:
        return len(self.diffs) > 0


def _validate_evidence(ev: TaskEvidence) -> TaskEvidence:
    if ev.n_runs < 0 or ev.n_success < 0:
        raise TaskRewriteError(
            f"task {ev.task_id!r}: n_runs/n_success must be >= 0 "
            f"(got {ev.n_runs}/{ev.n_success})"
        )
    if ev.n_success > ev.n_runs:
        raise TaskRewriteError(
            f"task {ev.task_id!r}: n_success ({ev.n_success}) > n_runs ({ev.n_runs})"
        )
    return ev


def propose_task_rewrite(
    *,
    registry_ids: dict[str, str],
    week_evidence: list[TaskEvidence],
    surface_signals: list[PlatformSurfaceSignal] | None = None,
    current_version: int = 1,
    thresholds: RewriteThresholds | None = None,
) -> TaskRewriteProposal:
    """Propose structural task diffs for next week's benchmark.

    ``registry_ids`` is the current task set as ``{task_id: family}``.
    ``week_evidence`` is this week's per-task outcomes. ``surface_signals`` are
    new platform capabilities to cover. Returns a ``TaskRewriteProposal`` (pure
    value; the caller applies diffs with operator authority).

    Ordering of diffs is deterministic: emit (surface growth) → graduate
    (saturated) → revise (noisy) → retire (operator-redundant), then by family.
    """
    if current_version < 1:
        raise TaskRewriteError(f"current_version must be >= 1, got {current_version}")
    th = thresholds or RewriteThresholds()
    signals = surface_signals or ()

    evidence_by_id: dict[str, TaskEvidence] = {}
    for record in week_evidence:
        _validate_evidence(record)
        evidence_by_id[record.task_id] = record

    diffs: list[TaskDiff] = []
    notes: list[str] = []

    # 1. EMIT — new platform surface (never invented without a signal).
    existing_ids = set(registry_ids)
    for sig in signals:
        if not sig.family.strip() or not sig.proposed_task_id.strip():
            raise TaskRewriteError(
                "PlatformSurfaceSignal must name a non-empty family and proposed_task_id"
            )
        if sig.proposed_task_id in existing_ids:
            notes.append(
                f"emit skipped: task {sig.proposed_task_id!r} already in registry"
            )
            continue
        diffs.append(
            TaskDiff(
                kind="emit",
                family=sig.family,
                task_id=sig.proposed_task_id,
                rationale=sig.rationale,
                proposed_prompt=sig.prompt,
                proposed_scoring=sig.scoring,
            )
        )

    # 2/3/4. Per existing task: graduate / revise / retire (one verdict each).
    for task_id in sorted(registry_ids):
        family = registry_ids[task_id]
        ev: TaskEvidence | None = evidence_by_id.get(task_id)
        if ev is None or ev.n_runs < th.min_runs_for_evidence:
            notes.append(
                f"no structural verdict for {task_id!r}: insufficient evidence "
                f"(< {th.min_runs_for_evidence} runs)"
            )
            continue
        rate = ev.success_rate
        assert rate is not None  # n_runs >= min_runs_for_evidence >= 1

        # GRADUATE — saturated: lost differentiating power. This is an OBSERVATION
        # the operator acts on (replace/retire), not a destruction. The pure
        # proposer never retires (retirement is destructive operator authority,
        # enforced by ``can_retire`` at the apply boundary).
        if rate >= th.graduate_success_rate:
            diffs.append(
                TaskDiff(
                    kind="graduate",
                    family=family,
                    task_id=task_id,
                    rationale=(
                        f"success rate {rate:.0%} over {ev.n_runs} run(s) — saturated; "
                        "no longer differentiates models"
                    ),
                )
            )
            continue

        # REVISE — high score variance: the task definition is ambiguous, not the
        # model bad. "Understand what worked and what didn't" (operator ask #11).
        var = ev.score_variance
        if var is not None and var >= th.revise_variance:
            diffs.append(
                TaskDiff(
                    kind="revise",
                    family=family,
                    task_id=task_id,
                    rationale=(
                        f"score variance {var:.3f} >= {th.revise_variance} — task "
                        "definition is ambiguous; sharpen prompt/rubric"
                    ),
                )
            )

    families_affected = tuple(sorted({d.family for d in diffs}))
    version_to = current_version + 1 if diffs else current_version
    if not diffs:
        notes.append("no structural changes proposed this week — benchmark stable")
    return TaskRewriteProposal(
        benchmark_version_from=current_version,
        benchmark_version_to=version_to,
        diffs=tuple(diffs),
        notes=tuple(notes),
        families_affected=families_affected,
    )


def can_retire(task_id: str, registry_ids: dict[str, str]) -> tuple[bool, str]:
    """Coverage guard for the destructive retire action (apply boundary).

    The pure proposer never retires — it graduates (flags saturation). When the
    authorized applier acts on a graduate verdict to RETIRE, it MUST call this
    first: retiring the last task in a family would erase that family's coverage
    with nothing to replace it. Returns ``(allowed, reason)`` — never raises, so
    the applier can present the refusal to the operator as a normal decision.
    """
    if task_id not in registry_ids:
        return False, f"task {task_id!r} not in registry"
    family = registry_ids[task_id]
    siblings = [t for t, f in registry_ids.items() if f == family and t != task_id]
    if not siblings:
        return False, (
            f"cannot retire {task_id!r}: it is the last task in family "
            f"{family!r}; retiring would erase coverage"
        )
    return True, f"family {family!r} retains {len(siblings)} task(s) after retire"


__all__ = [
    "TaskRewriteError",
    "TaskEvidence",
    "PlatformSurfaceSignal",
    "TaskDiff",
    "RewriteThresholds",
    "TaskRewriteProposal",
    "propose_task_rewrite",
    "can_retire",
]
