"""Synquery API client + mock for tests."""

from __future__ import annotations

import os
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, Protocol


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


class SynqueryAPIError(Exception):
    """Raised on Synquery API failure or feature-flag refusal."""


@dataclass(frozen=True)
class SynqueryExpert:
    """An expert matched by Synquery against a topic query."""

    expert_id: str
    display_name: str
    credentials: str
    rate_usd_per_hour: float
    availability_summary: str


@dataclass(frozen=True)
class SynqueryInterview:
    """A scheduled Synquery interview, returned by booking. The
    transcript flows back into Antiek as a `document_kind: 'interview'`
    document once the interview completes per master-spec §11.6."""

    interview_id: str
    expert_id: str
    scheduled_at: str
    duration_minutes: int
    booking_status: str  # "pending" | "confirmed" | "cancelled" | "completed"
    transcript_document_id: Optional[str] = None


class SynqueryClient(Protocol):
    """Production client speaks the real Synquery REST API; tests
    use MockSynqueryClient."""

    def search_experts(self, *, topic_query: str, limit: int = 5) -> list[SynqueryExpert]: ...

    def book_interview(
        self,
        *,
        expert_id: str,
        duration_minutes: int,
        scheduling_window_iso: str,
    ) -> SynqueryInterview: ...


@dataclass
class MockSynqueryClient:
    """Returns deterministic stub responses for testing. Operator
    feature-flags this via ANTIEK_SYNQUERY_ENABLED=0 during dev
    so real Synquery credits aren't burned."""

    canned_experts: list[SynqueryExpert] = field(default_factory=list)
    interviews: dict[str, SynqueryInterview] = field(default_factory=dict)

    def search_experts(self, *, topic_query: str, limit: int = 5) -> list[SynqueryExpert]:
        if not self.canned_experts:
            # Deterministic placeholder based on topic.
            return [
                SynqueryExpert(
                    expert_id=f"expert-mock-{i}",
                    display_name=f"Expert #{i} on {topic_query[:30]}",
                    credentials="PhD, 10+ years industry",
                    rate_usd_per_hour=1500.0,
                    availability_summary="weekday afternoons",
                )
                for i in range(min(limit, 3))
            ]
        return self.canned_experts[:limit]

    def book_interview(
        self,
        *,
        expert_id: str,
        duration_minutes: int,
        scheduling_window_iso: str,
    ) -> SynqueryInterview:
        interview_id = f"interview-synquery-{uuid.uuid4().hex[:12]}"
        interview = SynqueryInterview(
            interview_id=interview_id,
            expert_id=expert_id,
            scheduled_at=scheduling_window_iso,
            duration_minutes=duration_minutes,
            booking_status="pending",
        )
        self.interviews[interview_id] = interview
        return interview


def feature_flag_enabled() -> bool:
    """Per master-spec §11.6 + §14.1: Synquery activates only after
    creation-surface PMF signal. The feature flag default is OFF;
    operator sets ANTIEK_SYNQUERY_ENABLED=1 to enable."""
    return os.environ.get("ANTIEK_SYNQUERY_ENABLED", "0") == "1"
