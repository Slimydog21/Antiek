"""Cross-user 'ask an expert' flow (master-spec §13.9 Sprint 25+).

The substrate identifies a user whose public-graph contributions
overlap a topic User B is researching. With opt-in, the substrate
surfaces User A as a candidate interview subject for User B.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


class OptInRequired(Exception):
    """Raised when the substrate would surface a user as an expert
    candidate without their explicit opt-in for cross-user
    interview requests."""


@dataclass(frozen=True)
class ExpertCandidate:
    """A user surfaced as a potential expert based on their public-
    graph contributions overlapping the requesting user's topic."""

    candidate_user_id: str
    display_name: str | None
    public_note_count: int  # how many of their public notes overlap the topic
    opt_in_status: str  # 'opted_in' | 'opted_out' | 'not_set'
    estimated_topic_authority: float  # 0..1 substrate-side heuristic


@dataclass(frozen=True)
class AskExpertRequest:
    """User B's request to find experts on a topic."""

    requesting_user_id: str
    topic_query: str
    investigation_id: str | None
    limit: int = 5


@dataclass(frozen=True)
class AskExpertResponse:
    """Substrate response with opt-in-respecting candidates."""

    requesting_user_id: str
    topic_query: str
    candidates: list[ExpertCandidate]
    excluded_opt_out_count: int


def find_user_experts(
    request: AskExpertRequest,
    *,
    public_graph_contributions: dict[str, list[str]],
    opt_in_status_by_user: dict[str, str],
    authority_by_user: dict[str, float],
    display_names: dict[str, str | None] | None = None,
) -> AskExpertResponse:
    """Surface ExpertCandidates whose public-graph contributions
    overlap the topic. Respects opt-in: users with status='opted_out'
    are never surfaced regardless of authority.

    Args:
        public_graph_contributions: user_id → list of public_note_ids
            whose topics overlap the request topic_query
        opt_in_status_by_user: user_id → 'opted_in' | 'opted_out' |
            'not_set'
        authority_by_user: user_id → 0..1 authority score
        display_names: user_id → opt-in display name (None if private)
    """
    display_names = display_names or {}
    candidates: list[ExpertCandidate] = []
    excluded = 0

    for user_id, note_ids in public_graph_contributions.items():
        if user_id == request.requesting_user_id:
            continue  # don't surface the user to themselves
        status = opt_in_status_by_user.get(user_id, "not_set")
        if status == "opted_out":
            excluded += 1
            continue
        # 'not_set' is treated as NOT visible — per §13.9 opt-in,
        # the platform must NOT surface a user as expert without
        # affirmative opt-in.
        if status != "opted_in":
            continue
        candidates.append(ExpertCandidate(
            candidate_user_id=user_id,
            display_name=display_names.get(user_id),
            public_note_count=len(note_ids),
            opt_in_status=status,
            estimated_topic_authority=authority_by_user.get(user_id, 0.5),
        ))

    candidates.sort(key=lambda c: c.estimated_topic_authority, reverse=True)
    candidates = candidates[:request.limit]

    return AskExpertResponse(
        requesting_user_id=request.requesting_user_id,
        topic_query=request.topic_query,
        candidates=candidates,
        excluded_opt_out_count=excluded,
    )


def request_user_interview(
    *,
    requester_user_id: str,
    expert_user_id: str,
    expert_opt_in_status: str,
    topic: str,
    investigation_id: str | None = None,
) -> dict:
    """Create an interview-request handle. Refuses unless expert has
    affirmatively opted in (opt_in_status='opted_in')."""
    if expert_opt_in_status != "opted_in":
        raise OptInRequired(
            f"expert user {expert_user_id!r} has not opted in to "
            f"cross-user interview requests (status={expert_opt_in_status!r}); "
            f"the substrate refuses to surface them"
        )
    return {
        "request_id": f"interview-req-{uuid.uuid4().hex[:12]}",
        "requester_user_id": requester_user_id,
        "expert_user_id": expert_user_id,
        "topic": topic,
        "investigation_id": investigation_id,
        "status": "pending_expert_acceptance",
        "created_at": _now_iso(),
    }
