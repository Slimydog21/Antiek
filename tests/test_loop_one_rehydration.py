from __future__ import annotations

import pytest

from interfaces.research.api.broadcast import EventBroadcaster
from orchestration.loop_one.orchestrator import InvestigationContext, _run_phase_2
from orchestration.loop_one.rehydration import (
    InvestigationRehydrationConflict,
    project_loop_one_phase_state,
)
from substrate.event_log import prepare_typed_event
from substrate.schemas import (
    ConnectorDeliveredPayload,
    DecomposeQuestionDeliveredPayload,
    DecomposeQuestionRequestedPayload,
    EvidenceRetrieveDeliveredPayload,
    ParameterExtractDeliveredPayload,
    SubQuestion,
)


def _row(payload, *, generation: int = 2):
    return prepare_typed_event(
        "inv-rehydrate", payload, execution_generation=generation
    ).model_dump(mode="json")


def _sub_question(text: str) -> SubQuestion:
    return SubQuestion(
        sub_question=text,
        category="technology_risk",
        rationale=f"Why {text} matters",
        evidence_type_required="mixed",
    )


def test_projector_restores_ordered_prefix_and_ignores_stale_generation():
    decomposition = DecomposeQuestionDeliveredPayload(
        decomposition=[
            _sub_question("Q1"),
            _sub_question("Q2"),
        ],
        keywords=[],
    )
    rows = [
        _row(decomposition, generation=1),
        _row(decomposition),
        _row(
            EvidenceRetrieveDeliveredPayload(
                sub_question="Q1", answer="A1", supporting_claims=[],
                evidentiary_gaps=[], insufficient_evidence=False,
            )
        ),
    ]
    projection = project_loop_one_phase_state(rows, generation=2)
    assert projection.completed_phases == (1,)
    assert projection.next_phase == 2
    assert [event.payload.sub_question for event in projection.evidence] == ["Q1"]


def test_projector_rejects_conflicting_singletons_and_impossible_prerequisites():
    rows = [
        _row(DecomposeQuestionDeliveredPayload(decomposition=[_sub_question("A")], keywords=[])),
        _row(DecomposeQuestionDeliveredPayload(decomposition=[_sub_question("B")], keywords=[])),
    ]
    with pytest.raises(InvestigationRehydrationConflict, match="conflicting"):
        project_loop_one_phase_state(rows, generation=2)

    orphan = _row(ParameterExtractDeliveredPayload(parameters=[], constraints=[]))
    with pytest.raises(InvestigationRehydrationConflict, match="without complete evidence"):
        project_loop_one_phase_state([orphan], generation=2)


def test_projector_restores_out_of_order_partial_parallel_fanout():
    decomposition = _row(
        DecomposeQuestionDeliveredPayload(
            decomposition=[
                _sub_question("Q1"),
                _sub_question("Q2"),
            ],
            keywords=[],
        )
    )
    q2_first = _row(
        EvidenceRetrieveDeliveredPayload(
            sub_question="Q2", answer="A2", supporting_claims=[],
            evidentiary_gaps=[], insufficient_evidence=False,
        )
    )
    projection = project_loop_one_phase_state(
        [decomposition, q2_first], generation=2
    )
    assert projection.completed_phases == (1,)
    assert [event.payload.sub_question for event in projection.evidence] == ["Q2"]


def test_projector_rejects_connector_without_prior_canonical_results():
    connector = _row(
        ConnectorDeliveredPayload(selected_algorithm="top_n_shortest_paths")
    )
    with pytest.raises(InvestigationRehydrationConflict, match="without parameters"):
        project_loop_one_phase_state([connector], generation=2)


def test_projector_marks_capped_evidence_fanout_complete():
    decomposition = _row(
        DecomposeQuestionDeliveredPayload(
            decomposition=[
                _sub_question("Q1"),
                _sub_question("Q2"),
                _sub_question("Q3"),
            ],
            keywords=[],
        )
    )
    evidence = [
        _row(
            EvidenceRetrieveDeliveredPayload(
                sub_question=question,
                answer=f"A-{question}",
                supporting_claims=[],
                evidentiary_gaps=[],
                insufficient_evidence=False,
            )
        )
        for question in ("Q1", "Q2")
    ]
    projection = project_loop_one_phase_state(
        [decomposition, *evidence], generation=2, max_sub_questions=2
    )
    assert projection.completed_phases == (1, 2)
    assert projection.next_phase == 3


def test_projector_resumes_provider_request_without_delivery():
    request = _row(
        DecomposeQuestionRequestedPayload(question="Q", context="")
    )
    projection = project_loop_one_phase_state([request], generation=2)
    assert projection.completed_phases == ()
    assert projection.next_phase == 1


@pytest.mark.asyncio
async def test_phase_two_resume_requests_only_missing_member_and_restores_order(
    monkeypatch,
):
    decomposition = DecomposeQuestionDeliveredPayload(
        decomposition=[_sub_question("Q1"), _sub_question("Q2")],
        keywords=[],
    )
    q2 = EvidenceRetrieveDeliveredPayload(
        sub_question="Q2",
        answer="A2",
        supporting_claims=[],
        evidentiary_gaps=[],
        insufficient_evidence=False,
    )
    q1 = EvidenceRetrieveDeliveredPayload(
        sub_question="Q1",
        answer="A1",
        supporting_claims=[],
        evidentiary_gaps=[],
        insufficient_evidence=False,
    )
    ctx = InvestigationContext(
        investigation_id="inv-partial-resume",
        question="Q",
        decomposition=decomposition,
        evidence=[q2],
        max_sub_questions=2,
    )
    requested: list[str] = []

    async def fake_broadcast(_bus, investigation_id, payload, **_kwargs):
        assert investigation_id == ctx.investigation_id
        requested.append(payload.sub_question)
        return "evt-request-q1"

    class Coordinator:
        async def wait_for(self, *_args, **kwargs):
            assert kwargs["correlation"] == "Q1"
            return prepare_typed_event(ctx.investigation_id, q1)

    async def fake_drive(_ctx, *, phase, work):
        assert phase == 2
        await work
        return True

    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator.broadcast_emit", fake_broadcast
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._drive_phase", fake_drive
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_chunks_block_for_sub_question",
        lambda *_args, **_kwargs: "chunks",
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._render_subgraph_block_for_sub_question",
        lambda *_args, **_kwargs: "graph",
    )
    monkeypatch.setattr(
        "orchestration.loop_one.orchestrator._write_marker",
        lambda *_args, **_kwargs: None,
    )

    assert await _run_phase_2(ctx, EventBroadcaster(), Coordinator())
    assert requested == ["Q1"]
    assert [item.sub_question for item in ctx.evidence] == ["Q1", "Q2"]
