"""Canonical Loop One restart projection from the authorized event stream.

The projector is deliberately pure: callers supply already-authorized rows and
receive an immutable snapshot.  It never consults ``PhaseLog`` or process
memory, and it rejects ambiguity instead of selecting an arbitrary result.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from substrate.schemas import Event


class InvestigationRehydrationConflict(ValueError):
    """The durable trajectory cannot describe one deterministic execution."""


@dataclass(frozen=True)
class LoopOnePhaseProjection:
    generation: int
    completed_phases: tuple[int, ...]
    next_phase: int
    decomposition: Event | None
    evidence: tuple[Event, ...]
    parameters: Event | None
    connector: Event | None
    synthesis: Event | None
    master_md: Event | None
    skill_patches: tuple[Event, ...]
    terminal: Event | None


def _action(event: Event) -> str:
    value = event.action_type
    return value.value if hasattr(value, "value") else str(value)


def _one(events: Sequence[Event], action: str) -> Event | None:
    matches = [event for event in events if _action(event) == action]
    if not matches:
        return None
    fingerprints = {event.payload.model_dump_json() for event in matches}
    if len(fingerprints) != 1:
        raise InvestigationRehydrationConflict(
            f"conflicting canonical results for {action}"
        )
    return matches[0]


def project_loop_one_phase_state(
    rows: Sequence[Mapping[str, Any]],
    *,
    generation: int,
    max_sub_questions: int | None = None,
) -> LoopOnePhaseProjection:
    """Reconstruct one execution generation from canonical typed events.

    Fenced rows from the complete lease lineage are eligible; unfenced rows and
    future generations are ignored. Conflicting retries across generations are
    rejected rather than allowing a takeover to silently change prior truth.
    """
    parsed = tuple(Event.model_validate(dict(row)) for row in rows)
    lifecycle = {
        "investigation.start_requested",
        "investigation.execution_claimed",
        "investigation.execution_renewed",
        "investigation.execution_taken_over",
        "investigation.execution_completed",
    }
    relevant = tuple(
        event
        for event in parsed
        if event.execution_generation is not None
        and event.execution_generation <= generation
        and _action(event) not in lifecycle
    )

    terminal_actions = {"investigation.completed", "investigation.failed"}
    terminals = [event for event in relevant if _action(event) in terminal_actions]
    if len(terminals) > 1:
        raise InvestigationRehydrationConflict("multiple terminal events")

    decomposition = _one(relevant, "decompose.delivered")
    parameters = _one(relevant, "parameter_extract.delivered")
    connector = _one(relevant, "connector.delivered")
    synthesis = _one(relevant, "synthesize.delivered")
    master_md = _one(relevant, "synthesis.master_md_written")
    evidence_rows = tuple(
        event for event in relevant if _action(event) == "evidence.retrieve.delivered"
    )
    evidence_by_question: dict[str, Event] = {}
    for event in evidence_rows:
        question = event.payload.sub_question  # type: ignore[union-attr]
        prior = evidence_by_question.get(question)
        if prior is not None and prior.payload.model_dump_json() != event.payload.model_dump_json():
            raise InvestigationRehydrationConflict(
                "conflicting evidence result for sub-question"
            )
        evidence_by_question[question] = prior or event
    evidence: tuple[Event, ...] = ()
    patches = tuple(
        event for event in relevant if _action(event) == "skill.auto_patch_applied"
    )

    completed: list[int] = []
    if decomposition is not None:
        completed.append(1)
    if evidence_by_question and decomposition is not None:
        expected = [row.sub_question for row in decomposition.payload.decomposition]  # type: ignore[union-attr]
        if max_sub_questions is not None:
            if max_sub_questions < 1:
                raise ValueError("max_sub_questions must be positive")
            expected = expected[:max_sub_questions]
        extras = set(evidence_by_question).difference(expected)
        if extras:
            raise InvestigationRehydrationConflict("evidence fan-out membership mismatch")
        evidence = tuple(
            evidence_by_question[question]
            for question in expected
            if question in evidence_by_question
        )
        if len(evidence) == len(expected):
            completed.append(2)
    if parameters is not None:
        if 2 not in completed:
            raise InvestigationRehydrationConflict("parameters without complete evidence")
        completed.append(3)
    if connector is not None:
        if 3 not in completed:
            raise InvestigationRehydrationConflict("connector without parameters")
        completed.extend((4, 5))
    if synthesis is not None:
        if 5 not in completed:
            raise InvestigationRehydrationConflict("synthesis without connector")
        completed.append(6)
    if master_md is not None:
        if 6 not in completed:
            raise InvestigationRehydrationConflict("delivery artifact without synthesis")
        completed.append(7)
    if patches:
        if 7 not in completed:
            raise InvestigationRehydrationConflict("skill patch without delivery artifact")
        completed.append(8)
    if terminals and 8 not in completed:
        raise InvestigationRehydrationConflict("terminal event before phase 8")

    return LoopOnePhaseProjection(
        generation=generation,
        completed_phases=tuple(completed),
        next_phase=min(9, (completed[-1] + 1) if completed else 1),
        decomposition=decomposition,
        evidence=evidence,
        parameters=parameters,
        connector=connector,
        synthesis=synthesis,
        master_md=master_md,
        skill_patches=patches,
        terminal=terminals[0] if terminals else None,
    )
