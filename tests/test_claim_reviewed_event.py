"""Living Roadmap SPR-08 follow-up — ``claim.reviewed`` typed event.

This is the review-history signal the review-due augmentation needs. It records
the reader's review gesture and the scheduler's next_due_at verdict through the
single-writer funnel, carrying no claim/source body.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from substrate.event_log import emit_typed, trajectory
from substrate.schemas.events import (
    EVENT_SCHEMA_VERSION,
    TYPED_PAYLOAD_ACTION_TYPES,
    ClaimReviewedPayload,
)


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch):
    tmp = tempfile.mkdtemp(prefix="antiek-claim-reviewed-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmp, "events"))


def test_claim_reviewed_payload_defaults_and_union_registration():
    payload = ClaimReviewedPayload(
        claim_id="1",
        reviewed_at="2026-06-30T10:00:00Z",
        next_due_at="2026-07-01T10:00:00Z",
    )

    assert payload.action_type == "claim.reviewed"
    assert payload.rating is None
    assert "claim.reviewed" in TYPED_PAYLOAD_ACTION_TYPES


def test_claim_reviewed_rejects_empty_claim_id_and_negative_scheduler_values():
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ClaimReviewedPayload(
            claim_id="",
            reviewed_at="2026-06-30T10:00:00Z",
            next_due_at="2026-07-01T10:00:00Z",
        )
    with pytest.raises(ValidationError):
        ClaimReviewedPayload(
            claim_id="1",
            reviewed_at="2026-06-30T10:00:00Z",
            next_due_at="2026-07-01T10:00:00Z",
            ease=-1,
        )
    with pytest.raises(ValidationError):
        ClaimReviewedPayload(
            claim_id="1",
            reviewed_at="2026-06-30T10:00:00Z",
            next_due_at="2026-07-01T10:00:00Z",
            interval_days=-1,
        )


def test_claim_reviewed_carries_no_body_field():
    fields = set(ClaimReviewedPayload.model_fields)
    for forbidden in ("excerpt", "text", "body", "full_text", "snippet", "content"):
        assert forbidden not in fields
    assert {"claim_id", "reviewed_at", "next_due_at"} <= fields


def test_emitted_claim_reviewed_round_trips_through_the_funnel():
    event_id = emit_typed(
        "read-syn-1",
        ClaimReviewedPayload(
            claim_id="2",
            reviewed_at="2026-06-30T10:00:00Z",
            next_due_at="2026-07-01T10:00:00Z",
            rating="good",
            ease=2.5,
            interval_days=1,
            due_label="Due tomorrow",
        ),
        synthesis_id="syn-1",
        role="reader/review",
        policy_id="reader/review",
    )
    assert event_id is not None

    events = trajectory("read-syn-1")
    reviewed = [e for e in events if e.get("action_type") == "claim.reviewed"]
    assert len(reviewed) == 1
    payload = reviewed[0]["payload"]
    assert payload["claim_id"] == "2"
    assert payload["reviewed_at"] == "2026-06-30T10:00:00Z"
    assert payload["next_due_at"] == "2026-07-01T10:00:00Z"
    assert payload["due_label"] == "Due tomorrow"
    assert reviewed[0]["synthesis_id"] == "syn-1"
    assert reviewed[0]["schema_version"] == EVENT_SCHEMA_VERSION
