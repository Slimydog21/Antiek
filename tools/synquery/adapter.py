"""Synquery adapter — translates Antiek open-questions into Synquery
expert searches + ingests returned transcripts."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass

from runtime.db_lock import LockedConnection
from substrate.graph.ops import content_addressed_id, insert_chunk, insert_document
from substrate.research_bridge.ingest import (
    CHUNK_TARGET_CHARS,
    _chunk_paragraphs,
    _split_paragraphs,
)

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


@dataclass(frozen=True)
class SynqueryTranscriptIngest:
    """Webhook-side payload once Synquery returns a completed transcript."""

    interview_id: str
    expert_id: str
    transcript_text: str
    question_id: str
    investigation_id: str | None = None
    expert_display_name: str | None = None
    completed_at_iso: str | None = None
    source_url: str | None = None


@dataclass(frozen=True)
class SynqueryTranscriptResult:
    """Persisted Antiek document produced from a Synquery transcript."""

    document_id: str
    source_tier: int
    document_type: str
    chunk_ids: tuple[str, ...]
    interview: SynqueryInterview


@dataclass
class SynqueryAdapter:
    """Wraps the SynqueryClient with Antiek-side logic:
    - feature-flag enforcement
    - budget filtering (drops experts above operator_budget_usd)
    - completed transcript → tier-2 source ingestion
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
        Booking returns a handle; completed transcripts enter through
        ``ingest_completed_transcript`` when Synquery calls back."""
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

    def ingest_completed_transcript(
        self,
        con: LockedConnection,
        transcript: SynqueryTranscriptIngest,
        *,
        duration_minutes: int = 60,
        do_chunk: bool = True,
    ) -> SynqueryTranscriptResult:
        """Persist a completed Synquery interview transcript as a tier-2 source.

        This is the local contract for the eventual Synquery webhook: it writes
        the returned transcript into the normal ``documents``/``chunks`` graph
        path under the single-writer lock, stamps source-tier 2, and is
        idempotent per Synquery interview id.
        """
        if not feature_flag_enabled():
            raise SynqueryAPIError("Synquery feature-flag disabled")
        if not isinstance(con, LockedConnection):
            raise TypeError("ingest_completed_transcript requires a LockedConnection")

        text = transcript.transcript_text.strip()
        if not text:
            raise ValueError("Synquery transcript text is empty")
        if len(text.split()) < 12:
            raise ValueError("Synquery transcript text is too short to ingest")
        if not transcript.interview_id.strip():
            raise ValueError("Synquery interview_id is required")
        if not transcript.expert_id.strip():
            raise ValueError("Synquery expert_id is required")
        if not transcript.question_id.strip():
            raise ValueError("Synquery question_id is required")

        document_id = content_addressed_id(
            "doc",
            f"synquery-transcript|{transcript.interview_id.strip()}",
        )
        was_new = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ? LIMIT 1",
            [document_id],
        ).fetchone() is None
        raw_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
        title = _title_for_transcript(transcript)

        insert_document(
            con,
            document_id=document_id,
            source_tier=2,
            document_type="expert_interview_transcript",
            source_uri=(
                transcript.source_url
                or f"synquery://interviews/{transcript.interview_id}/transcript"
            ),
            title=title,
            raw_text=text,
            investigation_id=transcript.investigation_id,
            content_class="user_owned",
            ip_holder_id="__operator__",
            metadata={
                "synquery": {
                    "interview_id": transcript.interview_id,
                    "expert_id": transcript.expert_id,
                    "expert_display_name": transcript.expert_display_name,
                    "question_id": transcript.question_id,
                    "completed_at_iso": transcript.completed_at_iso,
                    "source_tier": 2,
                    "document_kind": "interview",
                    "raw_sha256": raw_sha256,
                }
            },
            on_conflict="ignore",
        )

        chunk_ids: list[str] = []
        if do_chunk and was_new:
            chunks = _chunk_paragraphs(_split_paragraphs(text), CHUNK_TARGET_CHARS)
            for index, chunk_text in enumerate(chunks):
                chunk_ids.append(
                    insert_chunk(
                        con,
                        document_id=document_id,
                        chunk_index=index,
                        text=chunk_text,
                    )
                )

        completed = SynqueryInterview(
            interview_id=transcript.interview_id,
            expert_id=transcript.expert_id,
            scheduled_at=transcript.completed_at_iso or "",
            duration_minutes=duration_minutes,
            booking_status="completed",
            transcript_document_id=document_id,
        )
        return SynqueryTranscriptResult(
            document_id=document_id,
            source_tier=2,
            document_type="expert_interview_transcript",
            chunk_ids=tuple(chunk_ids),
            interview=completed,
        )


def _title_for_transcript(transcript: SynqueryTranscriptIngest) -> str:
    expert = transcript.expert_display_name or transcript.expert_id
    return f"Synquery expert interview: {expert}"[:200]
