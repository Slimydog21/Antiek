"""Deposit Midnight Oil results as HTML + twin notes via engagement_spine.

Called on complete / timeout / budget_halt so partial work is never lost.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.engagement_spine import (
    InMemoryEngagementStore,
    complete_spawn,
    list_twin_notes,
    merge_spawn_outputs,
    project_to_html,
    record_twin_insight,
    record_twin_question,
    spawn_from_highlight,
)
from substrate.engagement_spine.spawn import HighlightSelection
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

    If ``step_outputs`` are provided, ensures corresponding spawns are
    reserved and completed under the job asset. Idempotent twin writes use
    content-addressed note ids from engagement_spine.
    """
    row = job_store.get_job(job_id)
    if row is None:
        raise KeyError(f"unknown job_id: {job_id}")
    job = _job_from_row(row)
    asset_id = job.asset_id or f"moil_asset_{job.job_id}"

    spawn_ids: list[str] = list(job.spawn_ids)
    for i, step in enumerate(step_outputs):
        if step.spawn_id and step.spawn_id in spawn_ids:
            # Already tracked — still ensure complete status if output present.
            try:
                complete_spawn(
                    step.spawn_id,
                    store=engagement_store,
                    output_text=step.output_text or f"Midnight oil step {i}",
                    insights=list(step.insights),
                    questions=list(step.questions),
                    status="complete",
                )
            except KeyError:
                pass
            continue
        goal_text = job.goals[i] if i < len(job.goals) else (job.goals[0] if job.goals else "research")
        sel = HighlightSelection(
            asset_id=asset_id,
            selection_text=goal_text,
            region_id=f"moil-{job.job_id}-step-{i}",
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
            output_text=step.output_text or f"Partial result for: {goal_text}",
            insights=list(step.insights) or [f"Progress on: {goal_text}"],
            questions=list(step.questions) or [f"What remains open for: {goal_text}?"],
            status="complete",
        )
        for insight in step.insights or (f"Progress on: {goal_text}",):
            record_twin_insight(
                asset_id,
                insight,
                store=engagement_store,
                source_spawn_id=spawn.spawn_id,
                investigation_id=spawn.investigation_id,
            )
        for question in step.questions or (f"What remains open for: {goal_text}?",):
            record_twin_question(
                asset_id,
                question,
                store=engagement_store,
                source_spawn_id=spawn.spawn_id,
                investigation_id=spawn.investigation_id,
            )
        if spawn.spawn_id not in spawn_ids:
            spawn_ids.append(spawn.spawn_id)

    # If no step_outputs, still deposit from job goals + any complete spawns.
    if not step_outputs and not spawn_ids:
        for i, goal in enumerate(job.goals):
            sel = HighlightSelection(
                asset_id=asset_id,
                selection_text=goal,
                region_id=f"moil-{job.job_id}-goal-{i}",
                goal_hint=goal,
            )
            spawn = spawn_from_highlight(sel, store=engagement_store, model_id=job.model_id)
            complete_spawn(
                spawn.spawn_id,
                store=engagement_store,
                output_text=f"Midnight oil deposit for goal: {goal}",
                insights=[f"Investigated: {goal}"],
                questions=[f"Open: {goal}?"],
                status="complete",
            )
            record_twin_insight(
                asset_id,
                f"Investigated: {goal}",
                store=engagement_store,
                source_spawn_id=spawn.spawn_id,
            )
            record_twin_question(
                asset_id,
                f"Open: {goal}?",
                store=engagement_store,
                source_spawn_id=spawn.spawn_id,
            )
            spawn_ids.append(spawn.spawn_id)

    # Merge completed spawns into draft-combined (or parent) document.
    mode = "draft_combined" if draft_combined else "into_parent"
    title = parent_title or f"Midnight Oil: {job.goals[0][:80] if job.goals else job.job_id}"
    # Parent body for empty store
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
    # Persist spawn_ids back on job for observability
    from dataclasses import replace

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
