"""Speak SPR-08 — biography authoring orchestration tests.

Rigor #3: a sparse project (thin outline, no padding), contradictory/
unverified accounts (present honestly — excluded from public, marked in
private), a never-ending deepening loop (explicit halt criteria), and
contributor provenance for the SPR-06 split. Reuses Write's
creative_writer; this is orchestration only.
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import biography, project, publish_gate
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-bio-test-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="bio_test")


def _seed_project(con):
    p = project.create_project(con, title="Dad's biography")
    # A publishable first-party claim.
    record_claim(con, project_id=p.project_id, interview_id="iv-a",
                 text="I learned to bake at his side every morning.", about_subject=False)
    # A publishable third-party claim (operator-attested).
    c2 = record_claim(con, project_id=p.project_id, interview_id="iv-a",
                      text="He ran the village bakery for thirty years.",
                      about_subject=True, subject_ref="the-dad")
    publish_gate.operator_attest_claim(con, c2.claim_id, project_id=p.project_id)
    # An UNcorroborated third-party claim (not publishable).
    c3 = record_claim(con, project_id=p.project_id, interview_id="iv-b",
                      text="He secretly funded a rival bakery.",
                      about_subject=True, subject_ref="the-dad")
    return p.project_id, c2.claim_id, c3.claim_id


# ── M1 outline from multi-party insights ────────────────────────────────


def test_outline_blocks_carry_contributor_provenance(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(db_con := con)
        outline = biography.assemble_outline(con, project_id=project_id, title="Dad's biography")
        assert len(outline.blocks) == 3
        # Every block knows its contributing interviewee(s).
        assert all(b.contributor_interview_ids for b in outline.blocks)


# ── M2 recursive deepening loop — bounded ───────────────────────────────


def test_deepening_halts_with_static_gaps(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(con)
        # Static gap source → must halt (diminishing returns or max_rounds),
        # never loop forever.
        result = biography.run_deepening(con, project_id=project_id, max_rounds=5)
        assert result.rounds_run <= 5
        assert result.halt_reason in ("diminishing_returns", "no_gaps", "max_rounds")
        assert len(result.prompts_generated) >= 1  # a gap triggered a prompt


def test_deepening_converges_when_gaps_resolved(db):
    with _con(db) as con:
        project_id, _, c3 = _seed_project(con)

        def gather(round_no: int) -> None:
            # Simulate gathering corroboration: attest the open claim so
            # the gap closes.
            publish_gate.operator_attest_claim(con, c3, project_id=project_id)

        result = biography.run_deepening(con, project_id=project_id, max_rounds=5, gather_fn=gather)
        assert result.halt_reason in ("no_gaps", "diminishing_returns")


def test_deepening_respects_operator_stop(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(con)
        result = biography.run_deepening(
            con, project_id=project_id, max_rounds=5, operator_stop=lambda r: True,
        )
        assert result.halt_reason == "operator_stop"
        assert result.rounds_run == 0


# ── M3 draft generation (reuse creative_writer + voice_style gate) ──────


def test_draft_stub_assembles_cited_prose(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(con)
        outline = biography.assemble_outline(con, project_id=project_id)
        draft = biography.generate_draft(con, project_id=project_id, outline=outline, public=False)
        assert draft.prose_text.strip()
        assert "iv-a" in draft.cited_interview_ids
        assert draft.voice_style_ok is True


def test_draft_via_creative_writer_dispatch(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(con)
        outline = biography.assemble_outline(con, project_id=project_id)

        def fake_dispatch(*, prompt, system, role, investigation_id):
            assert role == "creative_writer"
            return json.dumps({
                "prose_text": "He ran the village bakery for thirty years, and his "
                              "child learned the craft at his side.",
                "prose_provenance": {},
                "uncited_blocks": [],
            })

        draft = biography.generate_draft(con, project_id=project_id, outline=outline,
                                         public=True, dispatch_fn=fake_dispatch)
        assert "bakery" in draft.prose_text


# ── M4 publish only corroborated / attested ─────────────────────────────


def test_public_draft_excludes_uncorroborated_third_party(db):
    with _con(db) as con:
        project_id, attested, uncorroborated = _seed_project(con)
        outline = biography.assemble_outline(con, project_id=project_id)
        draft = biography.generate_draft(con, project_id=project_id, outline=outline, public=True)
        assert uncorroborated in draft.excluded_claim_ids
        assert "secretly funded a rival" not in draft.prose_text  # not published
        assert "thirty years" in draft.prose_text  # the attested one stays


def test_private_draft_marks_unverified_not_excludes(db):
    with _con(db) as con:
        project_id, _, uncorroborated = _seed_project(con)
        outline = biography.assemble_outline(con, project_id=project_id)
        draft = biography.generate_draft(con, project_id=project_id, outline=outline, public=False)
        assert uncorroborated in draft.unverified_marked_claim_ids
        assert uncorroborated not in draft.excluded_claim_ids
        assert "[unverified]" in draft.prose_text


# ── M5 contributor provenance feeds SPR-06 ──────────────────────────────


def test_draft_block_contributors_consumable_by_split(db):
    with _con(db) as con:
        project_id, _, _ = _seed_project(con)
        outline = biography.assemble_outline(con, project_id=project_id)
        draft = biography.generate_draft(con, project_id=project_id, outline=outline, public=True)
        # Every published block maps to its contributing interviewee(s).
        assert all(ivs for ivs in draft.block_contributors.values())
        assert set(draft.cited_interview_ids) <= {"iv-a", "iv-b"}
