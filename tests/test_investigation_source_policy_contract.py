from __future__ import annotations

import pytest
from pydantic import ValidationError

from interfaces.research.api.app import (
    InvestigationStartRequest,
    InvestigationStatusResponse,
)
from substrate.schemas import InvestigationStartRequestedPayload


def test_investigation_start_request_accepts_closed_source_policy() -> None:
    req = InvestigationStartRequest(
        question="Which sources should this research prioritize?",
        source_policy=["arxiv", "substack", "operator_corpus"],
    )

    assert req.source_policy == ["arxiv", "substack", "operator_corpus"]


def test_start_event_payload_records_source_policy_without_runner_side_effects() -> None:
    payload = InvestigationStartRequestedPayload(
        question="Trace the claim across papers and newsletters.",
        source_policy=["arxiv", "substack"],
    )

    assert payload.source_policy == ["arxiv", "substack"]


def test_source_policy_rejects_unknown_entries() -> None:
    with pytest.raises(ValidationError):
        InvestigationStartRequestedPayload(
            question="Trace the claim across papers and newsletters.",
            source_policy=["arxiv", "private_torrent"],
        )


def test_status_response_surfaces_recorded_source_policy() -> None:
    status = InvestigationStatusResponse(
        investigation_id="inv-source-policy",
        status="in_progress",
        source_policy=["operator_corpus", "web"],
    )

    assert status.source_policy == ["operator_corpus", "web"]
