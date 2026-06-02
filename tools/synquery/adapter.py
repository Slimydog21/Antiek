"""Synquery adapter — translates Antiek open-questions into Synquery
expert searches + ingests returned transcripts."""

from __future__ import annotations

from dataclasses import dataclass

from .client import (
    SynqueryAPIError,
    SynqueryClient,
    SynqueryExpert,
    SynqueryInterview,
    feature_flag_enabled,
)


@dataclass(frozen=True)
class SynqueryRequest:
    """Input to the adapter: an Antiek open-question that the
    operator decided is worth chasing through an expert call rather
    than autonomous research."""

    question_id: str
    question_text: str
    investigation_id: str | None
    operator_budget_usd: float  # operator's cap on this expert call


@dataclass(frozen=True)
class SynqueryResponse:
    """Output of the adapter: matched experts + booking handle if
    the operator confirmed a specific expert."""

    request_question_id: str
    matched_experts: list[SynqueryExpert]
    booking_handle: SynqueryInterview | None = None


@dataclass
class SynqueryAdapter:
    """Wraps the SynqueryClient with Antiek-side logic:
    - feature-flag enforcement
    - budget filtering (drops experts above operator_budget_usd)
    - book → transcript ingestion (Sprint 21 follow-on)
    """

    client: SynqueryClient

    def request_experts(self, request: SynqueryRequest) -> SynqueryResponse:
        """Search experts for the question; filter by budget."""
        if not feature_flag_enabled():
            raise SynqueryAPIError(
                "Synquery is feature-flag-disabled. Set "
                "ANTIEK_SYNQUERY_ENABLED=1 to enable. Per master-spec "
                "§14.1: Synquery activates only after creation-surface "
                "PMF signal."
            )
        experts = self.client.search_experts(
            topic_query=request.question_text,
            limit=10,
        )
        # Filter to experts whose hour rate fits the operator's budget.
        affordable = [
            e for e in experts
            if e.rate_usd_per_hour * 1.0 <= request.operator_budget_usd
        ]
        return SynqueryResponse(
            request_question_id=request.question_id,
            matched_experts=affordable,
        )

    def book_expert_interview(
        self,
        *,
        request: SynqueryRequest,
        expert_id: str,
        scheduling_window_iso: str,
        duration_minutes: int = 60,
    ) -> SynqueryResponse:
        """Operator picks an expert; the adapter books the interview.
        Booking handle returned; transcript ingestion happens when
        the interview completes (Synquery webhook → Antiek
        ingest pipeline; Sprint 21 follow-on)."""
        if not feature_flag_enabled():
            raise SynqueryAPIError("Synquery feature-flag disabled")
        booking = self.client.book_interview(
            expert_id=expert_id,
            duration_minutes=duration_minutes,
            scheduling_window_iso=scheduling_window_iso,
        )
        return SynqueryResponse(
            request_question_id=request.question_id,
            matched_experts=[],
            booking_handle=booking,
        )
