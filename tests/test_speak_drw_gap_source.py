"""Speak ↔ DRW SPR-07 — the gap-detection drop-in.

Verifies the cross-spec closure that DRW SPR-07's landing enables: the
compounding interviewer's GapSource composes DRW's centrality-ranked
shared-graph gaps (project-scoped) with Speak's consent-aware project-local
source — degrading cleanly to SpeakGraphGapSource when no Speak content is in
the shared graph (today's reality), and lighting up, scoped to the project,
when it is. Existing Speak conditioning behavior is preserved.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph import ops
from substrate.graph.insight_question import promote_question
from substrate.graph.schema import init_database
from substrate.speak import invitations, project
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.drw_gap_source import (
    SPEAK_PROJECT_NODE_KEY,
    CompositeGapSource,
    DRWGapSource,
    default_gap_source,
)
from substrate.speak.interviewer_context import SpeakGraphGapSource, build_conditioning_context
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


class StubEmbedding:
    dimension = 4

    def encode(self, text):
        h = sum(ord(c) for c in text) or 1
        return [float(h % 7), float((h >> 2) % 5), 1.0, 0.0]


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-drw-gap-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="drw_gap_test")


def _project(con):
    return project.create_project(con, title="Dad's biography").project_id


def _tagged_question(con, project_id, text):
    """Promote a DRW question node tagged to a Speak project (the convention a
    sanctioned promotion would follow), with no resolved_by edge → an
    unanswered-question gap."""
    return promote_question(
        con=con, text=text, investigation_id=project_id,
        metadata={SPEAK_PROJECT_NODE_KEY: project_id},
        embedding_provider=StubEmbedding(),
    )


# --------------------------------------------------------------------------
# Graceful degradation: no shared-graph content → DRW returns nothing
# --------------------------------------------------------------------------


def test_drw_gap_source_empty_without_promoted_nodes(db):
    with _con(db) as con:
        pid = _project(con)
        assert DRWGapSource(con).open_questions(pid) == []


def test_speak_gap_source_preserves_legacy_string_guide(db):
    with _con(db) as con:
        pid = project.create_project(
            con,
            title="Legacy guide",
            interview_guide={"must_cover": ["What should we remember?"]},
        ).project_id
        gaps = SpeakGraphGapSource(con).open_questions(pid)
    assert any(gap.text == "What should we remember?" for gap in gaps)


# --------------------------------------------------------------------------
# Project-scoped, centrality-ranked gaps when content IS in the shared graph
# --------------------------------------------------------------------------


def test_drw_gap_source_returns_project_scoped_open_questions(db):
    with _con(db) as con:
        pid = _project(con)
        _tagged_question(con, pid, "What was the turning point in his career?")
        gaps = DRWGapSource(con).open_questions(pid)
    assert len(gaps) == 1
    g = gaps[0]
    assert g.kind == "open_question"               # DRW unanswered_question → open_question
    assert "turning point" in g.text
    assert g.anchor_id is not None


def test_drw_gap_source_scopes_out_other_projects(db):
    with _con(db) as con:
        pid = _project(con)
        other = _project(con)
        _tagged_question(con, other, "A question about a different project?")
        # The gap belongs to `other`, so it must not surface for `pid`.
        assert DRWGapSource(con).open_questions(pid) == []
        assert len(DRWGapSource(con).open_questions(other)) == 1


def test_unsupported_claim_maps_to_deepen(db):
    with _con(db) as con:
        pid = _project(con)
        # A claim node tagged to the project, with no evidence edge → DRW
        # unsupported_claim → Speak 'deepen'.
        ops.insert_node(con, canonical_label="An unsupported assertion.",
                        node_type="claim", graph_scope="depth", investigation_id=pid,
                        metadata={SPEAK_PROJECT_NODE_KEY: pid})
        gaps = DRWGapSource(con).open_questions(pid)
    assert gaps and all(g.kind == "deepen" for g in gaps)


# --------------------------------------------------------------------------
# Composite: DRW + Speak, deduped + ranked
# --------------------------------------------------------------------------


def test_composite_merges_drw_and_speak_sources(db):
    with _con(db) as con:
        pid = _project(con)
        # Speak side: a single-sourced third-party claim → a corroborate gap.
        iv = invitations.invite_stakeholder(con, project_id=pid, informant_email="a@x.com")
        record_consent(con, interview_id=iv.interview_id, scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        record_claim(con, project_id=pid, interview_id=iv.interview_id,
                     text="He won the regional prize in 1981.", about_subject=True, subject_ref="the-dad")
        # DRW side: an unanswered question in the shared graph for this project.
        _tagged_question(con, pid, "What drove that 1981 achievement?")

        composite = CompositeGapSource(DRWGapSource(con), SpeakGraphGapSource(con))
        gaps = composite.open_questions(pid)
        kinds = {g.kind for g in gaps}
    # Both sources contributed: DRW open_question + Speak corroborate.
    assert "open_question" in kinds                # from DRW
    assert "corroborate" in kinds                  # from Speak
    # Deterministic ordering by salience desc.
    sal = [g.salience for g in gaps]
    assert sal == sorted(sal, reverse=True)


def test_composite_dedupes_by_question_id(db):
    with _con(db) as con:
        pid = _project(con)
        _tagged_question(con, pid, "A shared question?")
        # Same DRWGapSource twice → its gaps must appear once.
        composite = CompositeGapSource(DRWGapSource(con), DRWGapSource(con))
        gaps = composite.open_questions(pid)
    ids = [g.question_id for g in gaps]
    assert len(ids) == len(set(ids))


# --------------------------------------------------------------------------
# Wiring: build_conditioning_context default now uses the composite, and
# existing Speak conditioning behavior is preserved
# --------------------------------------------------------------------------


def test_default_gap_source_is_composite_when_drw_present(db):
    with _con(db) as con:
        assert isinstance(default_gap_source(con), CompositeGapSource)


def test_conditioning_context_surfaces_drw_gap_and_preserves_speak(db):
    with _con(db) as con:
        pid = _project(con)
        a = invitations.invite_stakeholder(con, project_id=pid, informant_email="a@x.com").interview_id
        record_consent(con, interview_id=a, scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
        b = invitations.invite_stakeholder(con, project_id=pid, informant_email="b@x.com").interview_id
        record_consent(con, interview_id=b, scopes=[ConsentScope.RECORD])
        record_claim(con, project_id=pid, interview_id=a,
                     text="He ran the village bakery for thirty years.",
                     about_subject=True, subject_ref="the-dad")
        _tagged_question(con, pid, "What was his proudest professional moment?")
        # Default gap source (no explicit pass) — now the composite.
        ctx = build_conditioning_context(con, project_id=pid, for_interview_id=b)
    # Speak behavior preserved: A's attribute-consented claim still informs B.
    assert any("bakery" in s for s in ctx.accumulated_insights)
    # DRW gap now also surfaces as an open question.
    assert any("proudest professional moment" in g.text for g in ctx.open_questions)
