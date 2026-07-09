"""Deposit Midnight Oil results as HTML + twin notes via engagement_spine.

Called on complete / timeout / budget_halt so partial work is never lost.

Worker step_fn may return a caller-chosen ``spawn_id`` that is only recorded
on the job (not yet in engagement_spine). Deposit **must** materialize those
rows via ``ensure_spawn`` before ``complete_spawn`` / ``merge_spawn_outputs``.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from substrate.engagement_spine import (
    InMemoryEngagementStore,
    complete_spawn,
    ensure_spawn,
    get_spawn,
    list_twin_notes,
    merge_spawn_outputs,
    project_to_html,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)
from substrate.engagement_spine.spawn import HighlightSelection, ResearchSpawn
from substrate.engagement_spine.store import EngagementStore

from .job import JobStore, MidnightOilJob, _job_from_row, put_job_state
from .worker import WorkerStepResult


@dataclass(frozen=True)
class DepositResult:
    job_id: str
    asset_id: str
    html: str
    twin_count: int
    spawn_ids: tuple[str, ...]
    document_id: str
    draft_combined: bool


def _goal_for_index(job: MidnightOilJob, index: int) -> str:
    if job.goals:
        return job.goals[index] if index < len(job.goals) else job.goals[0]
    return f"Midnight oil work for {job.job_id}"


def _materialize_and_complete(
    *,
    spawn_id: str | None,
    asset_id: str,
    goal_text: str,
    job: MidnightOilJob,
    engagement_store: EngagementStore,
    output_text: str,
    insights: tuple[str, ...] | list[str],
    questions: tuple[str, ...] | list[str],
    region_id: str | None,
    step_index: int,
) -> ResearchSpawn:
    """Ensure a spawn row exists (caller id or fresh), complete it, write twins."""
    ins = list(insights) if insights else [f"Progress on: {goal_text}"]
    qs = list(questions) if questions else [f"What remains open for: {goal_text}?"]
    body = output_text or f"Partial result for: {goal_text}"

    if spawn_id:
        spawn = ensure_spawn(
            spawn_id,
            store=engagement_store,
            parent_asset_id=asset_id,
            goal=goal_text,
            selection_text=goal_text,
            model_id=job.model_id,
            region_id=region_id or f"moil-{job.job_id}-step-{step_index}",
        )
    else:
        sel = HighlightSelection(
            asset_id=asset_id,
            selection_text=goal_text,
            region_id=region_id or f"moil-{job.job_id}-step-{step_index}",
            goal_hint=goal_text,
        )
        spawn = spawn_from_highlight(
            sel,
            store=engagement_store,
            model_id=job.model_id,
            force_new=False,
        )

    complete_spawn(
        spawn.spawn_id,
        store=engagement_store,
        output_text=body,
        insights=ins,
        questions=qs,
        status="complete",
    )
    for insight in ins:
        record_twin_insight(
            asset_id,
            insight,
            store=engagement_store,
            source_spawn_id=spawn.spawn_id,
            investigation_id=spawn.investigation_id,
        )
    for question in qs:
        record_twin_question(
            asset_id,
            question,
            store=engagement_store,
            source_spawn_id=spawn.spawn_id,
            investigation_id=spawn.investigation_id,
        )
    completed = get_spawn(spawn.spawn_id, store=engagement_store)
    if completed is None:
        raise RuntimeError(f"spawn {spawn.spawn_id} missing after complete_spawn")
    return completed


def deposit_job_results(
    job_id: str,
    *,
    job_store: JobStore,
    engagement_store: EngagementStore,
    step_outputs: list[WorkerStepResult] | tuple[WorkerStepResult, ...] = (),
    draft_combined: bool = True,
    parent_title: str | None = None,
) -> DepositResult:
    """Write twins + project HTML for a finished (or halted) job.

    Materializes any worker-reported ``spawn_id`` that is not yet in the
    engagement store (via ``ensure_spawn``), then completes and merges.
    Twin writes are content-addressed (idempotent note_ids).
    """
    row = job_store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    asset_id = job.asset_id or f"moil_asset_{job.job_id}"

    spawn_ids: list[str] = []
    seen: set[str] = set()

    def _track(sid: str) -> None:
        if sid and sid not in seen:
            seen.add(sid)
            spawn_ids.append(sid)

    # 1) Process explicit step outputs (may carry worker-chosen spawn ids).
    for i, step in enumerate(step_outputs):
        goal_text = _goal_for_index(job, i)
        spawn = _materialize_and_complete(
            spawn_id=step.spawn_id,
            asset_id=asset_id,
            goal_text=goal_text,
            job=job,
            engagement_store=engagement_store,
            output_text=step.output_text,
            insights=step.insights,
            questions=step.questions,
            region_id=f"moil-{job.job_id}-step-{i}",
            step_index=i,
        )
        _track(spawn.spawn_id)

    # 2) Materialize any job.spawn_ids not covered by step_outputs
    #    (worker recorded ids; deposit-only path with no step list).
    for i, sid in enumerate(job.spawn_ids):
        if sid in seen:
            # Still ensure complete if only reserved
            existing = engagement_store.get_spawn(sid)
            if existing is not None and existing.get("status") != "complete":
                goal_text = _goal_for_index(job, i)
                complete_spawn(
                    sid,
                    store=engagement_store,
                    output_text=existing.get("output_text")
                    or f"Partial result for: {goal_text}",
                    insights=list(existing.get("output_insights") or ()),
                    questions=list(existing.get("output_questions") or ()),
                    status="complete",
                )
            continue
        goal_text = _goal_for_index(job, i)
        spawn = _materialize_and_complete(
            spawn_id=sid,
            asset_id=asset_id,
            goal_text=goal_text,
            job=job,
            engagement_store=engagement_store,
            output_text=f"Partial result for: {goal_text}",
            insights=(f"Progress on: {goal_text}",),
            questions=(f"What remains open for: {goal_text}?",),
            region_id=f"moil-{job.job_id}-jobspawn-{i}",
            step_index=i,
        )
        _track(spawn.spawn_id)

    # 3) No steps and no job spawn_ids → deposit from goals alone.
    if not spawn_ids:
        for i, goal in enumerate(job.goals):
            spawn = _materialize_and_complete(
                spawn_id=None,
                asset_id=asset_id,
                goal_text=goal,
                job=job,
                engagement_store=engagement_store,
                output_text=f"Midnight oil deposit for goal: {goal}",
                insights=(f"Investigated: {goal}",),
                questions=(f"Open: {goal}?",),
                region_id=f"moil-{job.job_id}-goal-{i}",
                step_index=i,
            )
            _track(spawn.spawn_id)

    mode = "draft_combined" if draft_combined else "into_parent"
    title = parent_title or f"Midnight Oil: {job.goals[0][:80] if job.goals else job.job_id}"
    engagement_store.put_document(
        asset_id,
        {
            "title": title,
            "body_text": "\n".join(f"- {g}" for g in job.goals),
            "status": job.status,
        },
    )
    if spawn_ids:
        merge = merge_spawn_outputs(
            asset_id,
            spawn_ids,
            store=engagement_store,
            mode=mode,
            parent_title=title,
        )
        doc_model = merge.doc_model
        document_id = merge.document_id
    else:
        doc_model = {
            "type": "doc",
            "content": [
                {
                    "type": "paragraph",
                    "content": [{"type": "text", "text": title}],
                }
            ],
        }
        document_id = asset_id

    html = project_to_html(doc_model, document_id=document_id, creator="midnight_oil")
    if "pdf" in html.lower() and "<html" not in html.lower():
        raise RuntimeError("deposit produced PDF-like surface; HTML required")

    twins = list_twin_notes(asset_id, store=engagement_store)
    updated = replace(
        job,
        asset_id=asset_id,
        spawn_ids=tuple(spawn_ids),
        notes=(job.notes + " | deposited" if job.notes else "deposited"),
    )
    put_job_state(updated, store=job_store)

    return DepositResult(
        job_id=job.job_id,
        asset_id=asset_id,
        html=html,
        twin_count=len(twins),
        spawn_ids=tuple(spawn_ids),
        document_id=document_id,
        draft_combined=draft_combined,
    )


def default_engagement_store() -> InMemoryEngagementStore:
    return InMemoryEngagementStore()
