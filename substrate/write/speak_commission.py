"""Write -> Speak commission flow.

An honest Write gap can become a Speak interview request without copying the
gap text into a parallel task system:

1. Write promotes the gap to the shared graph as a stable ``question`` node.
2. Speak creates a private project whose interview guide contains that exact
   question id.
3. The handoff is recorded as ``seam.write_to_speak`` carrying the question
   node by reference.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from substrate.event_log import emit_typed
from substrate.graph.insight_question import promote_question
from substrate.schemas.events import SeamWriteToSpeakPayload
from substrate.speak import invitations, project


@dataclass(frozen=True)
class SpeakCommissionResult:
    question_node_id: str
    speak_project_id: str
    invite_id: str | None = None
    interview_id: str | None = None
    invite_link: str | None = None
    seam_event_id: str | None = None


def commission_interview_from_outline_gap(
    con: Any,
    *,
    section_id: str,
    question_text: str,
    deliverable_id: str,
    deliverable_title: str,
    section_title: str | None = None,
    investigation_id: str = "__operator__",
    informant_email: str | None = None,
    informant_handle: str | None = None,
    project_title: str | None = None,
) -> SpeakCommissionResult:
    """Commission a Speak project from a Write section gap.

    The gap becomes a first-class question node and the Speak project guide
    references that same id. If an informant is supplied, the function also
    creates the private invite link. The seam event is the cross-workflow
    warrant; no body/content field is emitted.
    """
    text = question_text.strip()
    if not text:
        raise ValueError("question_text is required")

    title = project_title or f"Interview for {section_title or deliverable_title}"
    question_node_id = promote_question(
        text=text,
        investigation_id=investigation_id,
        metadata={
            "source_workflow": "write",
            "source_kind": "outline_gap",
            "section_id": section_id,
            "deliverable_id": deliverable_id,
        },
        con=con,
    )
    guide = {
        "source": "write_outline_gap",
        "deliverable_id": deliverable_id,
        "section_id": section_id,
        "must_cover": [{"id": question_node_id, "text": text}],
    }
    speak_project = project.create_project(
        con,
        title=title,
        publish_intent="private_never_published",
        topic_description=(
            f"Commissioned from Write section {section_title or section_id} "
            f"in {deliverable_title}."
        ),
        interview_guide=guide,
    )

    invite = None
    if informant_email or informant_handle:
        invite = invitations.invite_stakeholder(
            con,
            project_id=speak_project.project_id,
            informant_email=informant_email,
            informant_handle=informant_handle,
        )

    seam_event_id = emit_typed(
        investigation_id,
        SeamWriteToSpeakPayload(
            entity_id=question_node_id,
            provenance_ref=section_id,
            outline_section_id=section_id,
        ),
        role="write_speak_commission",
    )
    return SpeakCommissionResult(
        question_node_id=question_node_id,
        speak_project_id=speak_project.project_id,
        invite_id=invite.invite_id if invite else None,
        interview_id=invite.interview_id if invite else None,
        invite_link=invite.link if invite else None,
        seam_event_id=seam_event_id,
    )
