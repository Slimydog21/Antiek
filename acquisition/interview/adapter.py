"""Interview transcript → Antiek substrate adapter.

Sprint 16 / master-spec §4.4 + §11 — once an interview reaches
``status="completed"`` in ``orchestration.interview.orchestrator``,
this adapter writes the conversation transcript into the substrate
graph the same way a voice note or YouTube transcript would land.
The note_taker role can then run the operator-self-talk-style prompt
on the chunks and extract insights + open questions.

The transcript is multi-speaker — operator's AI interviewer + the
human informant — so the markdown format preserves speaker labels.
Source tier defaults to 2 (primary, operator-acquired) matching the
voice-note adapter.

Stable doc id: ``doc-iv-<sha256[:16]>`` keyed on the interview_id so
re-ingesting the same completed interview is idempotent. If the
interview is ingested mid-conversation (status="in_progress"), the
adapter refuses — partial transcripts pollute the graph.
"""

from __future__ import annotations

import hashlib
import os
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING

# Repo root on path for direct invocation.
_PKG_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if _PKG_ROOT not in sys.path:
    sys.path.insert(0, _PKG_ROOT)

from processing.chunking.chunker import (  # noqa: E402
    Chunk,
    chunk_markdown,
    content_hash,
)
from processing.embedding.embed import (  # noqa: E402
    EmbeddingProvider,
    default_embedding_provider,
)
from substrate.event_log import emit_typed  # noqa: E402
from substrate.graph import (  # noqa: E402
    default_db_path,
    ensure_initialized,
)
from substrate.graph.ops import (  # noqa: E402
    insert_chunk,
    insert_document,
    insert_node,
)
from substrate.schemas import DocumentLoadedPayload  # noqa: E402

if TYPE_CHECKING:
    from orchestration.interview.orchestrator import InterviewState

DEFAULT_INTERVIEW_SOURCE_TIER = 2  # operator-acquired primary source
_NODE_LABEL_MAX = 160
MIN_INGEST_WORD_COUNT = 8  # interviews are sometimes short; lower bar


class InterviewIngestError(RuntimeError):
    """Raised when the adapter refuses to ingest — e.g., the interview
    is still in progress, no consent was recorded, or the transcript
    is empty after speaker filtering."""


@dataclass(frozen=True)
class IngestInterviewResult:
    document_id: str
    chunk_ids: list[str] = field(default_factory=list)
    node_ids: list[str] = field(default_factory=list)
    document_loaded_event_id: str | None = None
    chunks_written: int = 0
    skipped_reason: str | None = None
    title: str | None = None
    transcript_text: str | None = None
    turn_count: int = 0


def interview_doc_id(interview_id: str) -> str:
    """Stable doc id keyed on the interview_id. The interview_id is
    already a UUID slug; we hash it so the doc id format matches the
    voice-note pattern ``doc-iv-<sha256[:16]>``."""
    if not interview_id:
        raise ValueError("empty interview_id")
    h = hashlib.sha256(interview_id.encode("utf-8")).hexdigest()[:16]
    return f"doc-iv-{h}"


def _format_interview_markdown(
    *,
    title: str,
    state: InterviewState,
    recorded_at: datetime,
) -> str:
    """Render an interview transcript as chunker-friendly markdown.

    Each turn is a level-3 heading naming the speaker, followed by the
    text body. The chunker splits on these headings so each turn lands
    as its own chunk with ``section_path="<speaker> · turn N"``.
    """
    project_id = state.project_id
    informant = state.informant_handle or "anonymous"
    lines = [
        f"# {title}",
        "",
        f"**Project:** {project_id}",
        f"**Informant:** {informant}",
        f"**Recorded:** {recorded_at.isoformat()}",
        f"**Status:** {state.status}",
        f"**Turns:** {len(state.turns)}",
        "",
        "## Transcript",
        "",
    ]
    for i, turn in enumerate(state.turns, start=1):
        speaker_label = (
            "🎙️ Interviewer" if turn.speaker == "interviewer" else "👤 Informant"
        )
        lines.append(f"### {speaker_label} · turn {i}")
        lines.append("")
        lines.append(turn.text.strip())
        lines.append("")
    return "\n".join(lines)


def ingest_interview(
    state: InterviewState,
    *,
    investigation_id: str,
    title: str | None = None,
    recorded_at: datetime | None = None,
    source_tier: int = DEFAULT_INTERVIEW_SOURCE_TIER,
    db_path: str | None = None,
    embedder: EmbeddingProvider | None = None,
    min_word_count: int = MIN_INGEST_WORD_COUNT,
) -> IngestInterviewResult:
    """Write a completed interview transcript into the substrate graph.

    The adapter does not perform transcription itself — the
    orchestrator's ``InterviewState`` already carries text per turn.
    Pair this with the voice-mode WebRTC capture (§15.3) when audio
    is the source: ASR runs upstream and populates ``InterviewTurn.text``.

    Refuses to ingest if:
    - ``state.status != "completed"`` (partial transcripts pollute
      the graph; ``InterviewIngestError`` is raised);
    - ``state.consent_recorded`` is False (§11 binding gate — no
      transcript writes without recorded consent);
    - the combined transcript word count is below ``min_word_count``
      (returned as ``skipped_reason="low_word_count"`` — softer than
      raising, since short interviews are legitimate).
    """
    if state.status != "completed":
        raise InterviewIngestError(
            f"interview {state.interview_id} status={state.status!r}; "
            "adapter only ingests status='completed' transcripts"
        )
    if not state.consent_recorded:
        raise InterviewIngestError(
            f"interview {state.interview_id} has no consent recorded; "
            "refusing to write transcript to substrate"
        )

    when = recorded_at or datetime.now(UTC)
    document_id = interview_doc_id(state.interview_id)
    auto_title = (
        title
        or (
            f"Interview {state.interview_id[:16]} · {state.informant_handle}"
            if state.informant_handle
            else f"Interview {state.interview_id[:16]}"
        )
    )
    full_text = _format_interview_markdown(
        title=auto_title,
        state=state,
        recorded_at=when,
    )
    chash = "sha256:" + content_hash(full_text)
    # Word count over informant + interviewer text only — markdown
    # scaffolding shouldn't count toward the minimum-content threshold.
    word_count = sum(len(turn.text.split()) for turn in state.turns)

    payload = DocumentLoadedPayload(
        media_type="markdown",
        content_hash=chash,
        size_bytes=len(full_text.encode("utf-8")),
        title=auto_title,
        page_count=None,
        source_uri=None,
    )
    event_id = emit_typed(
        investigation_id,
        payload,
        document_id=document_id,
        role="acquisition",
        policy_id="acquisition/interview",
    )

    if word_count < min_word_count:
        return IngestInterviewResult(
            document_id=document_id,
            document_loaded_event_id=event_id,
            skipped_reason="low_word_count",
            title=auto_title,
            transcript_text=full_text,
            turn_count=len(state.turns),
        )

    resolved_db_path = db_path or default_db_path()
    ensure_initialized(resolved_db_path)

    chunks: list[Chunk] = chunk_markdown(full_text)
    chunk_ids: list[str] = []
    node_ids: list[str] = []
    chunks_written = 0
    emb = embedder or default_embedding_provider()

    from runtime.db_lock import connect_write

    with connect_write(resolved_db_path, purpose="acquisition/interview") as con:
        insert_document(
            con,
            document_id=document_id,
            source_tier=int(source_tier),
            document_type="interview_transcript",
            source_uri=None,
            title=auto_title,
            author=state.informant_handle or "__informant__",
            published_at=when,
            investigation_id=investigation_id,
            raw_text=full_text,
            metadata={
                "interview_id": state.interview_id,
                "project_id": state.project_id,
                "informant_handle": state.informant_handle,
                "turn_count": len(state.turns),
                "consent_recorded": state.consent_recorded,
                "transcription_source": "orchestrator",
            },
            on_conflict="ignore",
        )
        for i, chunk in enumerate(chunks):
            chunk_id = insert_chunk(
                con,
                document_id=document_id,
                chunk_index=i,
                text=chunk.text,
                section_path=chunk.section or None,
                embedding=emb.encode(chunk.text),
                token_count=chunk.token_count,
            )
            chunk_ids.append(chunk_id)
            chunks_written += 1

            label = chunk.text.strip().splitlines()[0] if chunk.text.strip() else ""
            if len(label) > _NODE_LABEL_MAX:
                label = label[: _NODE_LABEL_MAX - 1] + "…"
            if not label:
                label = f"interview-turn#{i}"
            node_id = insert_node(
                con,
                canonical_label=label,
                node_type="entity",
                graph_scope="cross_domain",
                investigation_id=investigation_id,
                embedding=emb.encode(label),
                metadata={
                    "source": "interview_transcript",
                    "interview_id": state.interview_id,
                    "chunk_id": chunk_id,
                    "section": chunk.section,
                },
                parent_event_id=event_id,
                on_conflict="ignore",
            )
            node_ids.append(node_id)

    return IngestInterviewResult(
        document_id=document_id,
        chunk_ids=chunk_ids,
        node_ids=node_ids,
        document_loaded_event_id=event_id,
        chunks_written=chunks_written,
        title=auto_title,
        transcript_text=full_text,
        turn_count=len(state.turns),
    )


__all__ = [
    "DEFAULT_INTERVIEW_SOURCE_TIER",
    "IngestInterviewResult",
    "InterviewIngestError",
    "ingest_interview",
    "interview_doc_id",
]
