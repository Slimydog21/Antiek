"""Speak SPR-02 — async voice-note interview tests.

Covers the rigor #3 enumeration: a multi-session resume, an
abandoned interview (incomplete), ASR failure, the consent gate, and
transcript correction (distill from corrected, not raw).
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from orchestration.interview.orchestrator import ConsentRequired
from runtime.db_lock import connect_write
from substrate.graph.ops import insert_interview_project
from substrate.graph.schema import init_database
from substrate.speak import async_interview as ai
from substrate.speak.async_interview import AsrError, PendingTranscript
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.schema import ensure_speak_schema


class StubEmbedding:
    dimension = 4

    def encode(self, text: str) -> list[float]:
        h = sum(ord(c) * (i + 1) for i, c in enumerate(text)) or 1
        return [float(h % 7) / 7.0, float((h >> 3) % 11) / 11.0,
                float((h >> 5) % 13) / 13.0, float((h >> 7) % 17) / 17.0]


class StubTranscriber:
    def __init__(self, text="transcribed words here"):
        self._text = text

    def transcribe(self, audio_bytes, *, filename, language=None):
        class _T:
            text = self._text
        return _T()


class FailingTranscriber:
    def transcribe(self, audio_bytes, *, filename, language=None):
        raise RuntimeError("whisper backend unavailable")


GUIDE = {"must_cover": [
    {"id": "q1", "text": "What is your earliest memory of him?"},
    {"id": "q2", "text": "Tell me about his work."},
]}


@pytest.fixture
def speak_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-async-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="async_test_setup") as con:
        init_database(con)
        ensure_speak_schema(con)
        insert_interview_project(con, title="Dad's biography", project_id="proj-dad")
    return {"db_path": db_path, "project_id": "proj-dad"}


def _consent(db_path, interview_id):
    with connect_write(db_path, purpose="grant_consent") as con:
        record_consent(con, interview_id=interview_id, scopes=[ConsentScope.RECORD])


# ── M1 session + resume + incomplete ────────────────────────────────────


def test_resume_across_sessions(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE, informant_handle="aunt-mona")
    iid = s.interview_id
    _consent(db, iid)
    ai.submit_answer(db, interview_id=iid, question_id="q1",
                     transcript="My earliest memory is the smell of his workshop in winter.",
                     embedder=StubEmbedding())
    # Simulate leaving and returning: brand-new session object from storage.
    resumed = ai.resume(db, iid)
    assert resumed.status == "in_progress"
    assert "q1" in resumed.answered_question_ids
    assert any(p["id"] == "q2" for p in resumed.pending_questions())


def test_resume_preserves_legacy_string_must_cover(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    session = ai.start_async_interview(
        db,
        project_id=proj,
        interview_guide={"must_cover": ["What should we remember?"]},
    )
    assert session.pending_questions() == [
        {"id": "legacy-0", "text": "What should we remember?"}
    ]


def test_abandoned_interview_marked_incomplete(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    ai.mark_incomplete(db, s.interview_id)
    assert ai.resume(db, s.interview_id).status == "incomplete"


def test_complete_when_all_answered(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    iid = s.interview_id
    _consent(db, iid)
    for qid in ("q1", "q2"):
        ai.submit_answer(db, interview_id=iid, question_id=qid,
                         transcript=f"A reasonably long answer to {qid} with several words.",
                         embedder=StubEmbedding())
    assert ai.complete_if_done(db, iid) is True
    assert ai.resume(db, iid).status == "completed"


# ── M2 capture + transcribe + anchor ────────────────────────────────────


def test_voice_note_anchored_to_interview_and_question(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    iid = s.interview_id
    _consent(db, iid)
    res = ai.submit_answer(db, interview_id=iid, question_id="q1",
                           transcript="He built furniture by hand for forty years in that workshop.",
                           embedder=StubEmbedding())
    assert res.document_id is not None
    resumed = ai.resume(db, iid)
    answer_turns = [t for t in resumed.turns if t.get("role") == "informant"]
    assert answer_turns[0]["question_id"] == "q1"
    assert answer_turns[0]["document_id"] == res.document_id


def test_transcribe_reuses_transcriber(speak_env):
    text = ai.transcribe(b"\x00\x01", filename="note.wav", transcriber=StubTranscriber("hello world"))
    assert text == "hello world"


# ── M3 async follow-ups ─────────────────────────────────────────────────


def test_followups_generated_and_must_cover_tracked(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    iid = s.interview_id
    _consent(db, iid)
    ai.submit_answer(db, interview_id=iid, question_id="q1",
                     transcript="My earliest memory is his workshop.", embedder=StubEmbedding())
    fus = ai.next_followups(db, interview_id=iid)
    # Should chase the unanswered must-cover q2.
    assert any(fu.question_id == "q2" for fu in fus)
    # q1 answered, so it is no longer pending.
    assert "q1" not in {p["id"] for p in ai.resume(db, iid).pending_questions()}


def test_followups_from_dispatch(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    iid = s.interview_id
    _consent(db, iid)
    ai.submit_answer(db, interview_id=iid, question_id="q1",
                     transcript="He emigrated in 1971 with two suitcases.", embedder=StubEmbedding())

    def fake_dispatch(*, prompt, system, role, investigation_id):
        return json.dumps({
            "interviewer_text": "What did he tell you about the journey itself?",
            "should_end": False,
            "must_cover_remaining_indices": [1],
            "follow_up_for_prior_turn": True,
        })

    fus = ai.next_followups(db, interview_id=iid, dispatch_fn=fake_dispatch)
    assert len(fus) == 1
    assert "journey" in fus[0].text
    assert fus[0].follow_up_for_prior_turn is True


# ── M4 consent gate ─────────────────────────────────────────────────────


def test_answer_requires_consent(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    with pytest.raises(ConsentRequired):
        ai.submit_answer(db, interview_id=s.interview_id, question_id="q1",
                         transcript="An answer given before consent.", embedder=StubEmbedding())


# ── M5 transcript correction (distill from corrected, not raw) ──────────


def test_pending_transcript_correction():
    pt = PendingTranscript(question_id="q1", raw_text="he was born in Kyro in 1940")
    assert pt.final_text == "he was born in Kyro in 1940"
    corrected = pt.correct("he was born in Cairo in 1940")
    assert corrected.final_text == "he was born in Cairo in 1940"
    assert corrected.was_corrected is True


def test_distillation_uses_corrected_text_not_raw(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    iid = s.interview_id
    _consent(db, iid)
    pt = PendingTranscript(question_id="q1", raw_text="he was born in Kyro").correct("he was born in Cairo")
    res = ai.submit_answer(db, interview_id=iid, question_id="q1",
                           transcript=pt.final_text, embedder=StubEmbedding())
    # The distilled document carries the CORRECTED text, never the raw misheard one.
    with connect_write(db, purpose="verify") as con:
        raw_text = con.execute(
            "SELECT raw_text FROM documents WHERE document_id = ?", [res.document_id]
        ).fetchone()[0]
    assert "Cairo" in raw_text
    assert "Kyro" not in raw_text


# ── ASR failure surfaced, not silently distilled ───────────────────────


def test_asr_failure_surfaced(speak_env):
    with pytest.raises(AsrError):
        ai.transcribe(b"\x00", filename="bad.wav", transcriber=FailingTranscriber())


def test_asr_failure_creates_no_document(speak_env):
    db, proj = speak_env["db_path"], speak_env["project_id"]
    s = ai.start_async_interview(db, project_id=proj, interview_guide=GUIDE)
    _consent(db, s.interview_id)
    # The interviewee's mic produced unusable audio: transcription raises
    # BEFORE any ingest/distill, so no document is created.
    with pytest.raises(AsrError):
        ai.transcribe(b"\x00", filename="bad.wav", transcriber=FailingTranscriber())
    with connect_write(db, purpose="verify") as con:
        n = con.execute("SELECT count(*) FROM documents WHERE document_type = 'voice_note'").fetchone()[0]
    assert n == 0
