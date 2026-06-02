"""Cross-graph network effects tests (Sprint 25+, master-spec §13.9)."""

from __future__ import annotations

import pytest

from substrate.cross_graph import (
    AskExpertRequest,
    FederationConfig,
    OptInRequired,
    federate_search,
    find_user_experts,
    record_cross_graph_citation,
    request_user_interview,
)

# ── 'Ask an expert' opt-in discipline ────────────────────────────────


def test_find_experts_includes_opted_in():
    request = AskExpertRequest(
        requesting_user_id="user-B",
        topic_query="quantum",
        investigation_id=None,
    )
    response = find_user_experts(
        request,
        public_graph_contributions={
            "user-A": ["note-1", "note-2", "note-3"],
            "user-C": ["note-4"],
        },
        opt_in_status_by_user={
            "user-A": "opted_in",
            "user-C": "opted_in",
        },
        authority_by_user={"user-A": 0.9, "user-C": 0.3},
    )
    candidate_ids = [c.candidate_user_id for c in response.candidates]
    assert "user-A" in candidate_ids
    assert "user-C" in candidate_ids
    # Highest authority first.
    assert response.candidates[0].candidate_user_id == "user-A"


def test_find_experts_excludes_opted_out():
    """A user with status='opted_out' is NEVER surfaced regardless of
    authority. The substrate respects the user's privacy decision."""
    request = AskExpertRequest(
        requesting_user_id="user-B",
        topic_query="quantum",
        investigation_id=None,
    )
    response = find_user_experts(
        request,
        public_graph_contributions={
            "user-A": ["note-1"], "user-X": ["note-99"],
        },
        opt_in_status_by_user={"user-A": "opted_in", "user-X": "opted_out"},
        authority_by_user={"user-A": 0.1, "user-X": 0.99},  # X has high authority
    )
    candidate_ids = [c.candidate_user_id for c in response.candidates]
    assert "user-X" not in candidate_ids
    assert response.excluded_opt_out_count == 1


def test_find_experts_excludes_not_set():
    """Per master-spec §13.9: 'with A's opt-in'. Users with
    opt_in_status='not_set' are NOT surfaced — the platform requires
    affirmative opt-in, not default-in."""
    request = AskExpertRequest(
        requesting_user_id="user-B",
        topic_query="quantum",
        investigation_id=None,
    )
    response = find_user_experts(
        request,
        public_graph_contributions={"user-A": ["note-1"]},
        opt_in_status_by_user={"user-A": "not_set"},
        authority_by_user={"user-A": 0.5},
    )
    assert response.candidates == []


def test_find_experts_excludes_requester():
    """Don't surface the requesting user to themselves."""
    request = AskExpertRequest(
        requesting_user_id="user-B",
        topic_query="quantum",
        investigation_id=None,
    )
    response = find_user_experts(
        request,
        public_graph_contributions={"user-B": ["note-1"]},
        opt_in_status_by_user={"user-B": "opted_in"},
        authority_by_user={"user-B": 0.9},
    )
    assert response.candidates == []


def test_request_interview_refuses_non_opted_in():
    with pytest.raises(OptInRequired):
        request_user_interview(
            requester_user_id="user-B",
            expert_user_id="user-A",
            expert_opt_in_status="not_set",
            topic="quantum",
        )


def test_request_interview_succeeds_with_opt_in():
    handle = request_user_interview(
        requester_user_id="user-B",
        expert_user_id="user-A",
        expert_opt_in_status="opted_in",
        topic="quantum",
        investigation_id="inv-x",
    )
    assert handle["status"] == "pending_expert_acceptance"
    assert handle["requester_user_id"] == "user-B"


# ── Federation ──────────────────────────────────────────────────────


def test_federate_search_includes_allowed_partners():
    config = FederationConfig(
        allowed_partner_substrates=("partner-research-org",),
    )
    merged = federate_search(
        topic_query="quantum",
        local_results=[{"chunk_id": "c-1", "text": "local result"}],
        federated_partner_results={
            "partner-research-org": [{"chunk_id": "c-2", "text": "partner result"}],
            "untrusted-partner": [{"chunk_id": "c-bad", "text": "should not appear"}],
        },
        config=config,
    )
    sources = {r.get("source_substrate") for r in merged}
    assert "local" in sources
    assert "partner-research-org" in sources
    assert "untrusted-partner" not in sources


def test_record_cross_graph_citation_carries_provenance():
    ref = record_cross_graph_citation(
        referencing_user_id="user-B",
        referencing_investigation_id="inv-B-1",
        referenced_user_id="user-A",
        referenced_note_id="note-A-7",
    )
    assert ref.referencing_user_id == "user-B"
    assert ref.referenced_user_id == "user-A"
    assert ref.federated_substrate_id is None  # same-substrate citation


def test_cross_graph_citation_federated_carries_substrate_id():
    ref = record_cross_graph_citation(
        referencing_user_id="user-B",
        referencing_investigation_id="inv-B-1",
        referenced_user_id="partner-user-Z",
        referenced_note_id="partner-note-1",
        federated_substrate_id="partner-research-org",
    )
    assert ref.federated_substrate_id == "partner-research-org"
