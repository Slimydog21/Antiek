"""Speak SPR-02 — async voice-note interview.

The operator's actual DeepBlu flow is asynchronous: send a link to
friends and family; each records voice notes when convenient — not a
scheduled live call. This module completes that flow on top of the
existing substrate:

  • the ``interviews`` table (lifecycle invited/in_progress/completed/
    declined/incomplete — already has ``incomplete``);
  • ``acquisition/voice`` (``WhisperTranscriber``, ``ingest_voice_note``);
  • the ``roles/interviewer/`` role (next-question generation).

It is db_path-based (not a held connection) because ``ingest_voice_note``
acquires its OWN write lock — async_interview takes short-lived,
*sequential* locks and interleaves them, never nesting (the single-
writer invariant: one flock holder at a time).

Explicitly out of scope: live spoken turn-taking. TTS still raises
``NotImplementedError`` (``acquisition/voice/openai_tts.py``); this is
async voice NOTES, not a live conversation. The live path stays a
deferred option.

The transcript-correction discipline (rigor #1: don't distill a
misheard memory into a confident fact): ASR errors on names/places/
dates are exactly what a biography gets wrong. ``transcribe`` returns
RAW text; the interviewee corrects it (``PendingTranscript``); and
``submit_answer`` distills from the text you pass it — there is no code
path that distills the raw transcript behind the corrected one.
"""

from __future__ import annotations

import json
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

# Reused, NOT forked: the voice substrate + interviewer role.
from acquisition.voice import ingest_voice_note  # noqa: E402
from orchestration.interview.orchestrator import ConsentRequired
from runtime.db_lock import connect_write

from .schema import ensure_speak_schema

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class AsrError(RuntimeError):
    """Transcription failed. Surfaced to the interviewee for retry /
    manual entry — never swallowed and silently distilled."""


# ---------------------------------------------------------------------------
# Transcript correction (M5) — distill from corrected, never raw
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PendingTranscript:
    """A transcribed-but-not-yet-distilled answer. The interviewee may
    correct ``raw_text`` before it is distilled; ``final_text`` is what
    ``submit_answer`` ingests."""

    question_id: str
    raw_text: str
    corrected_text: str | None = None

    def correct(self, text: str) -> PendingTranscript:
        return PendingTranscript(self.question_id, self.raw_text, text)

    @property
    def final_text(self) -> str:
        return self.corrected_text if self.corrected_text is not None else self.raw_text

    @property
    def was_corrected(self) -> bool:
        return self.corrected_text is not None and self.corrected_text != self.raw_text


# ---------------------------------------------------------------------------
# Session model (M1)
# ---------------------------------------------------------------------------


@dataclass
class AsyncInterviewSession:
    """The persisted state of one async interview, reconstructed from
    the ``interviews`` row + the project's guide. Resume = re-read."""

    interview_id: str
    project_id: str
    status: str
    turns: list[dict] = field(default_factory=list)
    must_cover: list[dict] = field(default_factory=list)

    @property
    def answered_question_ids(self) -> set[str]:
        return {
            t["question_id"]
            for t in self.turns
            if t.get("role") == "informant" and t.get("question_id")
        }

    @property
    def asked_question_ids(self) -> set[str]:
        return {
            t["question_id"]
            for t in self.turns
            if t.get("role") == "interviewer" and t.get("question_id")
        }

    def pending_questions(self) -> list[dict]:
        """Questions awaiting an answer: must-cover items not yet
        answered, plus interviewer follow-ups asked but not answered."""
        answered = self.answered_question_ids
        pending: list[dict] = []
        for q in self.must_cover:
            if q.get("id") and q["id"] not in answered:
                pending.append({"id": q["id"], "text": q.get("text", "")})
        for t in self.turns:
            if (
                t.get("role") == "interviewer"
                and t.get("question_id")
                and t["question_id"] not in answered
                and not any(p["id"] == t["question_id"] for p in pending)
            ):
                pending.append({"id": t["question_id"], "text": t.get("text", "")})
        return pending


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _load_turns(con: Any, interview_id: str) -> list[dict]:
    row = con.execute(
        "SELECT transcript_turns FROM interviews WHERE interview_id = ?",
        [interview_id],
    ).fetchone()
    if row is None:
        raise ValueError(f"interview {interview_id!r} not found")
    if not row[0]:
        return []
    try:
        return json.loads(row[0])
    except (TypeError, ValueError):
        return []


def _save_turns(con: Any, interview_id: str, turns: list[dict], *, status: str | None = None) -> None:
    if status is not None:
        con.execute(
            "UPDATE interviews SET transcript_turns = ?, status = ?, "
            "started_at = COALESCE(started_at, CURRENT_TIMESTAMP) "
            "WHERE interview_id = ?",
            [json.dumps(turns), status, interview_id],
        )
    else:
        con.execute(
            "UPDATE interviews SET transcript_turns = ? WHERE interview_id = ?",
            [json.dumps(turns), interview_id],
        )


def _project_guide(con: Any, project_id: str) -> dict:
    row = con.execute(
        "SELECT interview_guide FROM interview_projects WHERE project_id = ?",
        [project_id],
    ).fetchone()
    if row is None or not row[0]:
        return {}
    try:
        guide = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    hydrated: list[dict] = []
    for index, item in enumerate(guide.get("must_cover", [])):
        if isinstance(item, str):
            hydrated.append({"id": f"legacy-{index}", "text": item})
            continue
        if not isinstance(item, dict):
            continue
        question_node_id = item.get("question_node_id")
        if not question_node_id:
            hydrated.append(item)
            continue
        question = con.execute(
            "SELECT canonical_label FROM nodes "
            "WHERE node_id = ? AND node_type = 'question'",
            [question_node_id],
        ).fetchone()
        if question is not None:
            hydrated.append({**item, "id": question_node_id, "text": question[0]})
    return {**guide, "must_cover": hydrated}


def _consent_recorded(con: Any, interview_id: str) -> bool:
    row = con.execute(
        "SELECT consent_recorded FROM interviews WHERE interview_id = ?",
        [interview_id],
    ).fetchone()
    return bool(row and row[0])


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def start_async_interview(
    db_path: str,
    *,
    project_id: str,
    interview_guide: dict | None = None,
    informant_handle: str | None = None,
    interview_id: str | None = None,
) -> AsyncInterviewSession:
    """Create an async interview under a project. If ``interview_guide``
    is given and the project has none, persist it on the project (the
    guide is project-scoped so it survives resume)."""
    iid = interview_id or f"interview-{uuid.uuid4().hex[:12]}"
    with connect_write(db_path, purpose="speak/async_interview.start") as con:
        ensure_speak_schema(con)
        if interview_guide is not None and not _project_guide(con, project_id):
            con.execute(
                "UPDATE interview_projects SET interview_guide = ? WHERE project_id = ?",
                [json.dumps(interview_guide), project_id],
            )
        con.execute(
            "INSERT INTO interviews (interview_id, project_id, informant_handle, status) "
            "VALUES (?, ?, ?, 'invited') ON CONFLICT (interview_id) DO NOTHING",
            [iid, project_id, informant_handle],
        )
    return resume(db_path, iid)


def resume(db_path: str, interview_id: str) -> AsyncInterviewSession:
    """Reconstruct an interview's state from persisted storage — the
    whole point of an async interview is that you can leave and return."""
    with connect_write(db_path, purpose="speak/async_interview.resume") as con:
        row = con.execute(
            "SELECT project_id, status FROM interviews WHERE interview_id = ?",
            [interview_id],
        ).fetchone()
        if row is None:
            raise ValueError(f"interview {interview_id!r} not found")
        project_id, status = row[0], row[1]
        turns = _load_turns(con, interview_id)
        guide = _project_guide(con, project_id)
    return AsyncInterviewSession(
        interview_id=interview_id,
        project_id=project_id,
        status=status,
        turns=turns,
        must_cover=guide.get("must_cover", []),
    )


def transcribe(
    audio_bytes: bytes,
    *,
    filename: str,
    transcriber: Any | None = None,
    language: str | None = None,
) -> str:
    """Transcribe a voice note to RAW text (reuse WhisperTranscriber).
    Raises ``AsrError`` on failure — the caller surfaces it for retry,
    and the raw text is never distilled silently."""
    if transcriber is None:
        from acquisition.voice import WhisperTranscriber
        transcriber = WhisperTranscriber()
    try:
        result = transcriber.transcribe(audio_bytes, filename=filename, language=language)
    except Exception as exc:  # noqa: BLE001 — re-raised as a typed, surfaced error
        raise AsrError(f"transcription failed for {filename!r}: {exc}") from exc
    return getattr(result, "text", str(result))


@dataclass(frozen=True)
class AnswerResult:
    interview_id: str
    question_id: str
    document_id: str | None
    skipped_reason: str | None
    distilled_text: str


def submit_answer(
    db_path: str,
    *,
    interview_id: str,
    question_id: str,
    transcript: str,
    recorded_at: datetime | None = None,
    duration_seconds: float = 0.0,
    embedder: Any | None = None,
    min_word_count: int = 1,
) -> AnswerResult:
    """Submit a (corrected) transcript as the answer to ``question_id``.

    Consent gate (M4): substantive answers require ``consent_recorded``
    (the existing gate; SPR-01's ``record`` scope sets it). Raises
    ``ConsentRequired`` otherwise.

    ``transcript`` is the text to distill — pass the CORRECTED text.
    Distillation (note-taking over the voice note) happens inside
    ``ingest_voice_note``; there is no path that distills a different,
    raw transcript.
    """
    # Consent + project lookup under a short read/write lock.
    with connect_write(db_path, purpose="speak/async_interview.consent_check") as con:
        ensure_speak_schema(con)
        prow = con.execute(
            "SELECT project_id FROM interviews WHERE interview_id = ?", [interview_id]
        ).fetchone()
        if prow is None:
            raise ValueError(f"interview {interview_id!r} not found")
        project_id = prow[0]
        if not _consent_recorded(con, interview_id):
            raise ConsentRequired(
                f"interview {interview_id} has no consent recorded; record "
                "consent (SPR-01 'record' scope) before submitting answers"
            )

    # ingest_voice_note acquires its OWN write lock — do it OUTSIDE ours.
    ingest = ingest_voice_note(
        transcript,
        investigation_id=project_id,
        title=f"Interview {interview_id} — answer to {question_id}",
        recorded_at=recorded_at,
        duration_seconds=duration_seconds,
        db_path=db_path,
        embedder=embedder,
        min_word_count=min_word_count,
    )

    # Now record the answer turn under our own (sequential) lock.
    with connect_write(db_path, purpose="speak/async_interview.answer") as con:
        turns = _load_turns(con, interview_id)
        turns.append({
            "role": "informant",
            "text": transcript,
            "ts": _now_iso(),
            "question_id": question_id,
            "document_id": ingest.document_id,
        })
        _save_turns(con, interview_id, turns, status="in_progress")

    return AnswerResult(
        interview_id=interview_id,
        question_id=question_id,
        document_id=ingest.document_id,
        skipped_reason=ingest.skipped_reason,
        distilled_text=transcript,
    )


@dataclass(frozen=True)
class FollowupQuestion:
    question_id: str
    text: str
    follow_up_for_prior_turn: bool


def next_followups(
    db_path: str,
    *,
    interview_id: str,
    dispatch_fn: Callable[..., Any] | None = None,
    max_followups: int = 3,
) -> list[FollowupQuestion]:
    """Generate the next async follow-up question(s) from accumulated
    answers via the interviewer role, persist them as pending
    interviewer turns, and return them.

    ``dispatch_fn`` is injected for testability (production passes
    ``substrate.dispatch.dispatch``); with ``None`` a deterministic stub
    drives the next must-cover item or a generic deepening follow-up so
    the lifecycle is testable without a live model.
    """
    session = resume(db_path, interview_id)
    pending = session.pending_questions()

    generated: list[FollowupQuestion] = []
    if dispatch_fn is not None:
        from roles.interviewer import (
            InterviewerContext,
            TranscriptTurn,
            parse_interviewer_response,
            render_full_prompt,
        )
        ctx = InterviewerContext(
            project_title=session.project_id,
            topic_description="",
            framing="",
            must_cover=[q.get("text", "") for q in session.must_cover],
            consent_recorded=True,
            transcript=[
                TranscriptTurn(role=t.get("role", ""), text=t.get("text", ""))
                for t in session.turns
            ],
        )
        system, user = render_full_prompt(ctx)
        raw = dispatch_fn(prompt=user, system=system, role="interviewer",
                          investigation_id=f"speak-followup-{interview_id}")
        result = parse_interviewer_response(raw if isinstance(raw, str) else getattr(raw, "text", str(raw)))
        if not result.should_end and result.interviewer_text:
            generated.append(FollowupQuestion(
                question_id=f"fu-{uuid.uuid4().hex[:8]}",
                text=result.interviewer_text,
                follow_up_for_prior_turn=result.follow_up_for_prior_turn,
            ))
    else:
        # Deterministic stub: prefer an unanswered must-cover; else a
        # generic deepening follow-up referencing the last answer.
        for q in pending[:max_followups]:
            generated.append(FollowupQuestion(
                question_id=q["id"],
                text=q["text"] or f"[must-cover {q['id']}]",
                follow_up_for_prior_turn=False,
            ))
        if not generated and session.turns:
            last = session.turns[-1]
            if last.get("role") == "informant":
                generated.append(FollowupQuestion(
                    question_id=f"fu-{uuid.uuid4().hex[:8]}",
                    text="You mentioned something there — can you tell me more about that?",
                    follow_up_for_prior_turn=True,
                ))

    # Persist generated questions as pending interviewer turns (dedupe
    # already-asked must-cover ids).
    if generated:
        with connect_write(db_path, purpose="speak/async_interview.followups") as con:
            turns = _load_turns(con, interview_id)
            asked = {t["question_id"] for t in turns
                     if t.get("role") == "interviewer" and t.get("question_id")}
            for fq in generated:
                if fq.question_id in asked:
                    continue
                turns.append({
                    "role": "interviewer",
                    "text": fq.text,
                    "ts": _now_iso(),
                    "question_id": fq.question_id,
                    "follow_up_for_prior_turn": fq.follow_up_for_prior_turn,
                })
            _save_turns(con, interview_id, turns, status="in_progress")
    return generated


def mark_incomplete(db_path: str, interview_id: str) -> None:
    """An interviewee who never finishes. Status → 'incomplete' — their
    partial contribution is kept (it may still be useful), but the
    interview isn't treated as done."""
    with connect_write(db_path, purpose="speak/async_interview.incomplete") as con:
        con.execute(
            "UPDATE interviews SET status = 'incomplete' WHERE interview_id = ? "
            "AND status NOT IN ('completed', 'declined')",
            [interview_id],
        )


def decline(db_path: str, interview_id: str) -> None:
    """The invitee declines. Status → 'declined'."""
    with connect_write(db_path, purpose="speak/async_interview.decline") as con:
        con.execute(
            "UPDATE interviews SET status = 'declined' WHERE interview_id = ?",
            [interview_id],
        )


def complete_if_done(db_path: str, interview_id: str) -> bool:
    """Mark the interview complete iff there are no pending questions.
    Returns whether it completed."""
    session = resume(db_path, interview_id)
    if session.pending_questions():
        return False
    if not session.turns:
        return False  # nothing answered yet — not "done"
    with connect_write(db_path, purpose="speak/async_interview.complete") as con:
        con.execute(
            "UPDATE interviews SET status = 'completed', "
            "completed_at = CURRENT_TIMESTAMP WHERE interview_id = ?",
            [interview_id],
        )
    return True
