"""Bench snapshot assembler — recorder view records → weekly snapshot (ask #11 glue).

The operator wants the benchmark "presented in settings so that I can know on a
weekly basis what models are best at what tasks." The recorder (#1829) persists
tamper-evident per-run ``ViewRecord`` rows (task, model_id, score, n_runs, notes).
The weekly renderer (#1858) renders a :class:`WeeklyBenchSnapshot` to HTML. But
nothing turns N flat view records into that snapshot — grouping by task family,
aggregating per model, ranking, and computing the cross-task overall. THIS module
is that assembly: the pure glue that closes the gap between "recorded runs" and
"the rendered weekly report."

**Why pure + import-free of #1829/#1858.** Both ship in separate off-main PRs.
Hard-importing either would stack PRs and break independent bar-cleanliness on a
frozen main. Instead the assembler takes the view records as a minimal compatible
input shape (``RunView`` — mirrors #1829's ``ViewRecord`` fields) and a
task→family resolver as an injectable callable (the task registry #1828 owns that
mapping; the assembler never hard-codes it). It returns the
:class:`WeeklyBenchSnapshot` shape #1858 renders (defined HERE, compatibly, so
the route layer adapts). The assembler owns the ONE thing no other module does:
the **aggregation + ranking discipline** with honest handling of pending runs,
missing families, and zero-run models.

**The load-bearing invariants (each is a test):**

1. **A model's mean score is computed only from COMPLETED runs.** A pending run
   (score ``None`` — human-scored, awaiting confirmation) is counted as
   ``pending_runs`` but NEVER folded into the mean. A mean over [0.8, None] is
   ``0.8`` with ``pending_runs=1``, not ``0.4`` (averaging a None as 0 would
   fabricate a penalty) and not ``None`` (one pending run shouldn't null a real
   completed mean).
2. **A model with ZERO completed runs has mean_score = None.** Fabricating a 0
   mean from zero runs would rank a never-scored model as "worst" — a lie. It is
   flagged ``bench-unverified`` instead (the renderer lists it separately).
3. **The incomplete flag is the OR of every family's incompleteness.** If ANY
   model in ANY family has a pending run, the whole week is incomplete (the
   renderer's banner reflects this). A caller-set ``incomplete`` override is
   AND-ed in (never relaxed) so a caller can mark incomplete but never hide it.
4. **Overall ranking aggregates only completed scores across families.** A model
   scored in 3 families gets the mean of those 3 family-means; a family where it
   has no completed runs does NOT contribute a 0 (no fabricated penalty for
   breadth-gaps). A model with no completed runs anywhere is excluded from the
   overall ranking (listed in families only).
5. **Ranking is stable.** Ties preserve input order (no arbitrary reordering);
   the renderer's tie-handling (name all best) is downstream.
6. **Deterministic + pure.** Same view records → byte-identical snapshot. No I/O,
   no clock, no dispatch. ``generated_at_label`` is caller-resolved.

**Composition:**

    recorder view records (#1829) + task→family resolver (#1828)
        ↓
    assemble_weekly_snapshot(...) → WeeklyBenchSnapshot (THIS MODULE)
        ↓
    render_weekly_bench(snapshot) → HTML (#1858)
        ↓ (same snapshot also feeds)
    diff_weeks(prev, curr) (#1862) + rewrite loops (#1831/#1843)

The assembler is the single source of truth for "what did this week look like" —
both the human-facing render and the machine-facing recursion read from it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field


class SnapshotAssemblyError(ValueError):
    """An assembly input violates a load-bearing invariant."""


@dataclass(frozen=True)
class RunView:
    """One recorded run view (mirrors #1829's ``ViewRecord`` fields).

    ``score`` is ``None`` for a pending/incomplete run (human-scored, awaiting
    confirmation). ``task_id`` resolves to a family via the injected resolver.
    """

    task_id: str
    model_id: str
    score: float | None
    n_runs: int = 1
    notes: str = ""


@dataclass(frozen=True)
class ModelScore:
    """One model's aggregate in a family (or overall) — compatible with #1858."""

    model_id: str
    mean_score: float | None  # None = no completed runs
    completed_runs: int
    pending_runs: int = 0
    notes: str = ""


@dataclass(frozen=True)
class TaskFamilyResult:
    """One task family's ranked models — compatible with #1858."""

    task_family: str
    models: tuple[ModelScore, ...]
    scoring_method: str = ""


@dataclass(frozen=True)
class WeeklyBenchSnapshot:
    """A full week's assembled results — compatible with #1858's render input."""

    week_id: str
    generated_at_label: str
    task_families: tuple[TaskFamilyResult, ...]
    overall_ranking: tuple[ModelScore, ...]
    source_record_count: int
    incomplete: bool
    honesty_notes: tuple[str, ...] = field(default_factory=tuple)


# task_id → task_family resolver (the task registry #1828 owns the real mapping).
TaskFamilyResolver = Callable[[str], str]


def _identity_resolver(task_id: str) -> str:
    """Default resolver: the task_id IS the family (1:1). For single-family weeks."""
    return task_id


def _aggregate_model(
    views: tuple[RunView, ...],
) -> ModelScore:
    """Aggregate one (family, model)'s run views into a ModelScore.

    Mean is over COMPLETED runs only; pending runs counted separately. Zero
    completed runs → mean_score None (never fabricated 0).
    """
    completed_scores: list[float] = []
    pending = 0
    completed = 0
    notes_set: list[str] = []
    for view in views:
        if view.score is None:
            pending += view.n_runs if view.n_runs > 0 else 1
        else:
            completed += view.n_runs if view.n_runs > 0 else 1
            completed_scores.extend([view.score] * (view.n_runs if view.n_runs > 0 else 1))
        if view.notes.strip() and view.notes not in notes_set:
            notes_set.append(view.notes.strip())

    if not completed_scores:
        return ModelScore(
            model_id=views[0].model_id,
            mean_score=None,
            completed_runs=0,
            pending_runs=pending,
            notes="; ".join(notes_set),
        )

    mean = sum(completed_scores) / len(completed_scores)
    return ModelScore(
        model_id=views[0].model_id,
        mean_score=mean,
        completed_runs=completed,
        pending_runs=pending,
        notes="; ".join(notes_set),
    )


def assemble_weekly_snapshot(
    *,
    week_id: str,
    generated_at_label: str,
    run_views: list[RunView],
    family_resolver: TaskFamilyResolver | None = None,
    scoring_method: str = "",
    incomplete_override: bool = False,
) -> WeeklyBenchSnapshot:
    """Turn flat run views into a ranked weekly snapshot for the renderer.

    Pure: no I/O, no clock, no dispatch. Groups by (family, model), aggregates,
    ranks, and computes the cross-task overall ranking.

    ``family_resolver`` maps task_id → task_family (default: identity, 1:1).
    ``incomplete_override`` is AND-ed into the computed flag (a caller can mark
    incomplete but never relax it).
    """
    if not week_id.strip():
        raise SnapshotAssemblyError("week_id must be non-empty")
    if not generated_at_label.strip():
        raise SnapshotAssemblyError("generated_at_label must be non-empty")

    resolver = family_resolver or _identity_resolver
    views = tuple(run_views)

    # Group by (family, model).
    groups: dict[tuple[str, str], list[RunView]] = {}
    family_order: list[str] = []
    notes: list[str] = []
    has_pending = False

    for view in views:
        try:
            family = resolver(view.task_id)
        except Exception as exc:  # resolver failure is honest, not silent
            raise SnapshotAssemblyError(
                f"family_resolver raised for task_id {view.task_id!r}: {exc}"
            ) from exc
        if not family.strip():
            raise SnapshotAssemblyError(
                f"family_resolver returned empty family for task_id {view.task_id!r}"
            )
        key = (family, view.model_id)
        if family not in family_order:
            family_order.append(family)
        groups.setdefault(key, []).append(view)
        if view.score is None:
            has_pending = True

    # Build per-family results.
    families: list[TaskFamilyResult] = []
    family_means_by_model: dict[str, list[tuple[str, float]]] = {}  # model -> [(family, mean)]
    for family in family_order:
        # collect models in this family, in first-seen order
        family_models: list[str] = []
        for (fam, model) in groups:
            if fam == family and model not in family_models:
                family_models.append(model)
        model_scores: list[ModelScore] = []
        for model in family_models:
            key = (family, model)
            score = _aggregate_model(tuple(groups[key]))
            model_scores.append(score)
            if score.mean_score is not None:
                family_means_by_model.setdefault(model, []).append((family, score.mean_score))
        # rank within family: completed desc, None last, stable
        ranked = sorted(
            model_scores,
            key=lambda m: (m.mean_score is None, -(m.mean_score or 0.0)),
        )
        families.append(
            TaskFamilyResult(
                task_family=family,
                models=tuple(ranked),
                scoring_method=scoring_method,
            )
        )

    # Overall ranking: mean of each model's family-means (completed only).
    overall: list[ModelScore] = []
    for model, fam_means in family_means_by_model.items():
        means = [m for _, m in fam_means]
        overall.append(
            ModelScore(
                model_id=model,
                mean_score=sum(means) / len(means),
                completed_runs=len(means),
                pending_runs=0,
                notes=f"scored in {len(means)} family(ies)",
            )
        )
    overall_ranked = tuple(
        sorted(overall, key=lambda m: (m.mean_score is None, -(m.mean_score or 0.0)))
    )

    # Models with no completed runs anywhere — surfaced honestly.
    all_models = {v.model_id for v in views}
    unverified = sorted(all_models - {m.model_id for m in overall_ranked})
    if unverified:
        notes.append(
            "models with no completed runs (bench-unverified): "
            + ", ".join(unverified)
        )

    incomplete = has_pending or incomplete_override
    if has_pending:
        notes.append("week has pending/incomplete runs — verdicts are provisional")

    return WeeklyBenchSnapshot(
        week_id=week_id,
        generated_at_label=generated_at_label,
        task_families=tuple(families),
        overall_ranking=overall_ranked,
        source_record_count=len(views),
        incomplete=incomplete,
        honesty_notes=tuple(notes),
    )


__all__ = [
    "SnapshotAssemblyError",
    "RunView",
    "ModelScore",
    "TaskFamilyResult",
    "WeeklyBenchSnapshot",
    "TaskFamilyResolver",
    "assemble_weekly_snapshot",
]
