"""Speak ↔ Write SPR-01 — the OutlineComposer drop-in.

Verifies the cross-spec closure that Write's landing enables: biography
outlines compose through Write's canonical ``outline_blocks`` layer (not the
legacy ``section_blocks``), with the speak_claim provenance + contributor
attribution preserved inside the canonical layer, and consent-safely (no
speak_claim promoted to the shared graph). Existing biography behavior is
preserved.
"""

from __future__ import annotations

import os
import tempfile

import pytest

from runtime.db_lock import connect_write
from substrate.graph.schema import init_database
from substrate.speak import biography, invitations, project
from substrate.speak.consent import ConsentScope, record_consent
from substrate.speak.contracts import OutlineComposer
from substrate.speak.schema import ensure_speak_schema
from substrate.speak.third_party import record_claim
from substrate.speak.write_composer import WriteOutlineComposer, default_outline_composer
from substrate.write.outline_block import list_section_blocks


@pytest.fixture
def db(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="speak-write-composer-")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", os.path.join(tmpdir, "events"))
    db_path = os.path.join(tmpdir, "t.duckdb")
    with connect_write(db_path, purpose="setup") as con:
        init_database(con)
        ensure_speak_schema(con)
    return db_path


def _con(db):
    return connect_write(db, purpose="write_composer_test")


def _project_with_claims(con, n=3):
    pid = project.create_project(con, title="Dad's biography").project_id
    iv = invitations.invite_stakeholder(con, project_id=pid, informant_email="a@x.com")
    record_consent(con, interview_id=iv.interview_id, scopes=[ConsentScope.RECORD, ConsentScope.ATTRIBUTE])
    for i in range(n):
        record_claim(con, project_id=pid, interview_id=iv.interview_id,
                     text=f"He did notable thing number {i} in the village.",
                     about_subject=True, subject_ref="the-dad")
    return pid, iv.interview_id


# --------------------------------------------------------------------------
# Protocol conformance + default selection
# --------------------------------------------------------------------------


def test_write_composer_satisfies_contract(db):
    with _con(db) as con:
        assert isinstance(WriteOutlineComposer(con), OutlineComposer)


def test_default_composer_is_write_when_present(db):
    with _con(db) as con:
        assert isinstance(default_outline_composer(con), WriteOutlineComposer)


# --------------------------------------------------------------------------
# Composition lands in the canonical outline_blocks layer with provenance
# --------------------------------------------------------------------------


def test_assemble_outline_uses_write_outline_blocks(db):
    with _con(db) as con:
        pid, iv = _project_with_claims(con, n=3)
        outline = biography.assemble_outline(con, project_id=pid, title="Dad's biography")
        blocks = list_section_blocks(con, outline.section_id)
    # Composed into Write's canonical layer, one outline_block per claim.
    assert len(blocks) == 3
    for b in blocks:
        assert b.provenance_kind == "synthesized"      # non-node, consent-safe
        assert b.node_id is None                        # no shared-graph promotion
        assert b.source_block_kind == "speak_claim"     # provenance to the claim of record
        assert b.source_block_id                        # the claim_id
        assert b.content                                # claim text rides inline


def test_contributor_provenance_preserved_in_canonical_layer(db):
    with _con(db) as con:
        pid, iv = _project_with_claims(con, n=2)
        outline = biography.assemble_outline(con, project_id=pid)
        blocks = list_section_blocks(con, outline.section_id)
    # The SPR-06 split provenance is self-describing inside outline_blocks.
    for b in blocks:
        meta = b.metadata or {}
        assert iv in (meta.get("contributor_interview_ids") or [])
        assert meta.get("speak_block_kind") == "claim"


# --------------------------------------------------------------------------
# Regression — the Speak Outline object is unchanged; downstream still works
# --------------------------------------------------------------------------


def test_outline_object_unchanged_and_draft_still_works(db):
    with _con(db) as con:
        pid, iv = _project_with_claims(con, n=3)
        outline = biography.assemble_outline(con, project_id=pid)
        # The Speak Outline projection is independent of the composer.
        assert len(outline.blocks) == 3
        assert all(b.contributor_interview_ids for b in outline.blocks)
        # Draft generation (deterministic stub) still assembles cited prose.
        draft = biography.generate_draft(con, project_id=pid, outline=outline, public=False)
    assert draft.prose_text
    assert iv in draft.cited_interview_ids


def test_explicit_composer_override_still_honored(db):
    # Passing a composer explicitly must bypass the default (contract intact).
    captured = {}

    class _Spy:
        def compose(self, *, deliverable_id, section_title, blocks):
            captured["n"] = len(blocks)
            return "sec-spy"

    with _con(db) as con:
        pid, iv = _project_with_claims(con, n=2)
        outline = biography.assemble_outline(con, project_id=pid, composer=_Spy())
    assert outline.section_id == "sec-spy"
    assert captured["n"] == 2
