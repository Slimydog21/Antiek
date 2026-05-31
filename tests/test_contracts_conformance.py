"""Tests for the conformance harness (antiek-unified SPR-01 M7).

The harness is the mechanism that makes "no product forks a contract"
enforceable in CI (SPR-08 wires it). It must pass against real in-tree
implementations and fail *loudly, with a useful diff* against a divergent fake.
"""

from __future__ import annotations

from dataclasses import dataclass

import pytest

from substrate.contracts import (
    NoteTakerOutputContract,
    assert_conformance,
    verify_conformance,
)
from substrate.contracts.conformance import ConformanceError


def test_real_extracted_note_conforms():
    # The live note-taker output dataclass must satisfy the contract — this is
    # the proof the contract mirrors reality, not an invented shape.
    from roles.note_taker.parser import ExtractedNote

    result = verify_conformance(ExtractedNote, NoteTakerOutputContract)
    assert result.ok, result.diff
    assert result.missing == ()


def test_divergent_fake_fails_with_diff():
    @dataclass
    class FakeNote:
        note_id: str
        text: str
        # missing: confidence, source_event_ids

    result = verify_conformance(FakeNote, NoteTakerOutputContract)
    assert not result.ok
    assert set(result.missing) == {"confidence", "source_event_ids"}
    # the diff must name the missing fields so a CI log is actionable
    assert "confidence" in result.diff and "source_event_ids" in result.diff
    assert "FakeNote" in result.diff


def test_assert_conformance_raises_on_divergence():
    @dataclass
    class FakeNote:
        note_id: str

    with pytest.raises(ConformanceError) as exc:
        assert_conformance(FakeNote, NoteTakerOutputContract)
    assert "missing fields" in str(exc.value)


def test_superset_conforms():
    @dataclass
    class RicherNote:
        note_id: str
        text: str
        confidence: str
        source_event_ids: tuple
        extra_field: str = "ok"  # extra fields are allowed (a superset conforms)

    result = verify_conformance(RicherNote, NoteTakerOutputContract)
    assert result.ok, result.diff
    assert "extra" in result.diff.lower()


def test_dict_impl_conforms():
    record = {
        "note_id": "n1",
        "text": "x",
        "confidence": "high",
        "source_event_ids": ("e1",),
    }
    assert verify_conformance(record, NoteTakerOutputContract).ok


def test_contract_instance_conforms_to_itself():
    note = NoteTakerOutputContract(
        note_id="n1", text="x", confidence="high", source_event_ids=("e1",)
    )
    assert verify_conformance(note, NoteTakerOutputContract).ok


# ===========================================================================
# AFF SPR-04 — the knowledge-unit deposit contract (extension of the
# insight/question node contracts). Proves a REAL deposit (through the only
# sanctioned writer + single-writer path) carries every required field, and
# that dropping a required field REDS with the field named in .missing
# (non-vacuity), and that the nullable groundedness slot tolerates None.
# ===========================================================================

import hashlib
import os
import tempfile
from dataclasses import dataclass as _dataclass

from substrate.contracts.nodes import (
    KnowledgeUnitContract,
    ProvenanceLink,
    ServabilityTag,
)


class _FakeEmbedding:
    """Deterministic, dependency-free embedding (mirrors the graph tests)."""

    dimension = 8

    def encode(self, text: str) -> list[float]:
        digest = hashlib.sha256(text.encode("utf-8")).digest()
        return [b / 255.0 for b in digest[: self.dimension]]


@pytest.fixture
def deposited_unit(monkeypatch):
    """Drive a REAL deposit through ``promote_insight`` (the only sanctioned
    writer, single-writer path) grounded on a real document/chunk/claim, then
    project it onto a ``KnowledgeUnitContract`` via ``knowledge_unit_of``.

    Returns the validated contract instance so the conformance tests assert
    against a unit that came out of the actual deposit path, not a hand-built
    fixture (the non-vacuity guard rests on this being real)."""
    from processing.embedding import (
        _reset_default_provider,
        set_default_embedding_provider,
    )
    from runtime.db_lock import connect_write
    from substrate.graph import insight_question as iq
    from substrate.graph import ops
    from substrate.graph.insight_question import knowledge_unit_of, promote_insight
    from substrate.graph.schema import init_database_at_path

    set_default_embedding_provider(_FakeEmbedding())
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "graph.duckdb")
    events_dir = os.path.join(d, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    init_database_at_path(db_path)

    # Seed a real document + chunk + claim so the supported_by edge can carry
    # genuine claim→chunk→doc grounding (FKs are enforced in DuckDB).
    con = connect_write(db_path, purpose="seed")
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_tier, document_type, content_class) "
            "VALUES (?, ?, ?, ?)",
            ["doc-1", 3, "research_source", "public_domain"],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES (?, ?, ?, ?)",
            ["chunk-1", "doc-1", 0, "Acme raised $5M in 2021."],
        )
        claim_id = ops.insert_node(
            con, canonical_label="Acme raised $5M", node_type="claim",
            graph_scope="depth", investigation_id="inv1",
        )
    finally:
        con.close()

    # The deposit itself — through the sanctioned single writer.
    nid = promote_insight(
        text="Acme is well funded.",
        investigation_id="inv1",
        confidence="high",
        supported_by=[claim_id],
        source_document_id="doc-1",
        chunk_id="chunk-1",
    )

    # Project the deposited node onto the contract, reading §9.0 from the
    # classifier (public_domain ⇒ servable). Read on the same DB.
    con = connect_write(db_path, purpose="assemble")
    try:
        unit = knowledge_unit_of(con, nid, content_class="public_domain")
    finally:
        con.close()
    try:
        yield {"unit": unit, "node_id": nid, "db_path": db_path}
    finally:
        _reset_default_provider()


def test_knowledge_unit_complete_deposit_conforms(deposited_unit):
    # A fully-populated, REAL deposited unit satisfies the contract.
    unit = deposited_unit["unit"]
    result = verify_conformance(unit, KnowledgeUnitContract)
    assert result.ok, result.diff
    assert result.missing == ()
    # The reused + added fields are all populated from the real deposit.
    assert unit.node_id == deposited_unit["node_id"]
    assert unit.retrieval_key == unit.node_id  # stable retrieval key == node_id
    assert unit.provenance.source_document_id == "doc-1"
    assert unit.provenance.chunk_id == "chunk-1"
    assert unit.servability.serves_full_text is True  # public_domain serves
    assert unit.groundedness_score is None  # nullable slot, None until SPR-08


def test_knowledge_unit_dropped_chunk_id_reds(deposited_unit):
    # Non-vacuity: drop chunk_id from the provenance link and assert the
    # harness reds with chunk_id named in .missing. The provenance link is
    # checked at the ProvenanceLink contract level (where chunk_id lives).
    @_dataclass
    class _ProvenanceMissingChunk:
        source_document_id: str  # chunk_id deliberately dropped

    result = verify_conformance(_ProvenanceMissingChunk, ProvenanceLink)
    assert result.ok is False
    assert "chunk_id" in result.missing
    assert "chunk_id" in result.diff  # the diff names it → actionable gate


def test_knowledge_unit_dropped_servability_reds(deposited_unit):
    # Non-vacuity (second required field): drop the servability tag from the
    # top-level unit and assert it reds with `servability` in .missing.
    unit = deposited_unit["unit"]
    impl = unit.model_dump()
    del impl["servability"]
    result = verify_conformance(impl, KnowledgeUnitContract)
    assert result.ok is False
    assert "servability" in result.missing
    assert "servability" in result.diff


def test_knowledge_unit_sanity_dropped_field_is_caught_only_when_dropped(deposited_unit):
    # Sanity-check the negative test is not vacuous: with chunk_id PRESENT the
    # same check must pass — proving the red above was caused by the drop, not
    # by an always-failing assertion.
    full = deposited_unit["unit"].provenance.model_dump()
    assert verify_conformance(full, ProvenanceLink).ok is True


def test_knowledge_unit_nullable_groundedness_conforms(deposited_unit):
    # The groundedness_score slot is nullable: a unit with it None conforms,
    # so SPR-08 can land a value without re-cutting this contract.
    unit = deposited_unit["unit"]
    assert unit.groundedness_score is None
    assert verify_conformance(unit, KnowledgeUnitContract).ok
    # And a unit WITH a float also validates (forward-compat for SPR-08).
    scored = unit.model_copy(update={"groundedness_score": 0.83})
    assert scored.groundedness_score == 0.83
    assert verify_conformance(scored, KnowledgeUnitContract).ok


def test_servability_deny_by_default_for_unknown_source(deposited_unit):
    # §9.0 deny-by-default sourced from servable.py: an unknown / restricted
    # content_class yields a non-servable tag, and a tag may NOT claim
    # full-text serving for a non-allowlisted class.
    from substrate.graph.insight_question import servability_tag_for

    assert servability_tag_for(None).serves_full_text is False
    assert servability_tag_for("restricted_pending_opt_in").serves_full_text is False
    assert servability_tag_for("public_domain").serves_full_text is True
    with pytest.raises(ValueError):
        # An unknown class cannot be marked servable — deny-by-default guard.
        ServabilityTag(content_class=None, serves_full_text=True)


def test_knowledge_unit_retrieval_key_must_equal_node_id():
    # The surfaced retrieval key is the content-addressed node_id by
    # construction; a mismatch is rejected (the key is not free-form).
    with pytest.raises(ValueError):
        KnowledgeUnitContract(
            node_id="nid-1",
            node_type="insight",
            text="x",
            investigation_id="inv1",
            confidence="high",
            retrieval_key="something-else",
            provenance=ProvenanceLink(source_document_id="doc-1", chunk_id="chunk-1"),
            servability=ServabilityTag(content_class="public_domain", serves_full_text=True),
        )


# ===========================================================================
# AFF SPR-04 SHARPEN — the cases the happy-path fixture hid.
#
# The original fixture only ever seeded a real claim node + supported_by edge
# + public_domain source, which is exactly why the two SEND-BACK blockers were
# invisible. These cases drive the previously-uncovered paths:
#   (a) a source_declared_open (CC-BY) source — BLOCKER 1: the contract's
#       servable allowlist had drifted from the §9.0 classifier and crashed.
#   (b) a marginalia insight with supported_by=[] grounded only on metadata —
#       BLOCKER 2: investigation_id used to project as '' (SPR-07 mis-bucket).
#   (c) a question-node projection — BLOCKER 2: a question never carries a
#       supported_by edge, so its investigation_id + grounding come from the
#       metadata mirror.
# Each asserts investigation_id AND servability are CORRECT, not merely
# non-crashing. Plus the drift-guard that keeps the two allowlists welded.
# ===========================================================================


def _seed_db(monkeypatch, *, content_class: str = "public_domain"):
    """Spin up an isolated graph DB with a real document + chunk + claim node
    so a deposit can carry genuine claim→chunk→doc grounding (FK-enforced).
    Returns ``(db_path, claim_id, reset)``; caller closes nothing (helper owns
    the seed connection) and calls ``reset()`` when done."""
    import os
    import tempfile

    from processing.embedding import (
        _reset_default_provider,
        set_default_embedding_provider,
    )
    from runtime.db_lock import connect_write
    from substrate.graph import insight_question as iq
    from substrate.graph import ops
    from substrate.graph.schema import init_database_at_path

    set_default_embedding_provider(_FakeEmbedding())
    d = tempfile.mkdtemp()
    db_path = os.path.join(d, "graph.duckdb")
    events_dir = os.path.join(d, "events")
    os.makedirs(events_dir, exist_ok=True)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    monkeypatch.setattr(iq, "graph_db_path", lambda: db_path)
    init_database_at_path(db_path)

    con = connect_write(db_path, purpose="seed")
    try:
        con.execute(
            "INSERT INTO documents "
            "(document_id, source_tier, document_type, content_class) "
            "VALUES (?, ?, ?, ?)",
            ["doc-1", 3, "research_source", content_class],
        )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
            "VALUES (?, ?, ?, ?)",
            ["chunk-1", "doc-1", 0, "Acme raised $5M in 2021."],
        )
        claim_id = ops.insert_node(
            con, canonical_label="Acme raised $5M", node_type="claim",
            graph_scope="depth", investigation_id="inv1",
        )
    finally:
        con.close()
    return db_path, claim_id, _reset_default_provider


def test_source_declared_open_is_servable_no_crash(monkeypatch):
    # (a) BLOCKER 1 regression: a CC-BY (source_declared_open) source must
    # project a SERVABLE tag without raising. Before the drift-guard fix the
    # contract's FULL_TEXT_SERVABLE lacked source_declared_open, so the
    # classifier said serves=True while the contract forced content_class=None,
    # tripping the deny-by-default validator → ValidationError. It must serve.
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import (
        knowledge_unit_of,
        promote_insight,
        servability_tag_for,
    )

    # Direct classifier call (the exact line that crashed) — servable, no raise.
    tag = servability_tag_for("source_declared_open")
    assert tag.serves_full_text is True
    assert tag.content_class == "source_declared_open"

    # And through a real deposit + projection end-to-end.
    db_path, claim_id, reset = _seed_db(monkeypatch, content_class="source_declared_open")
    try:
        nid = promote_insight(
            text="Acme is well funded.",
            investigation_id="inv1",
            confidence="high",
            supported_by=[claim_id],
            source_document_id="doc-1",
            chunk_id="chunk-1",
        )
        con = connect_write(db_path, purpose="assemble")
        try:
            unit = knowledge_unit_of(con, nid, content_class="source_declared_open")
        finally:
            con.close()
        assert verify_conformance(unit, KnowledgeUnitContract).ok
        assert unit.servability.serves_full_text is True
        assert unit.servability.content_class == "source_declared_open"
        assert unit.investigation_id == "inv1"
    finally:
        reset()


def test_marginalia_insight_metadata_only_grounding_yields_real_investigation(monkeypatch):
    # (b) BLOCKER 2: a user-authored marginalia insight has NO supported_by
    # edge (supported_by=[]) — it grounds purely on metadata.chunk_id. The
    # projection must recover the REAL deposit investigation from the node
    # metadata mirror, not fall through to ''.
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import knowledge_unit_of, promote_insight

    db_path, _claim_id, reset = _seed_db(monkeypatch)
    try:
        nid = promote_insight(
            text="My note in the margin.",
            investigation_id="inv1",
            confidence="moderate",
            supported_by=[],  # no claim target — pure marginalia path
            source_document_id="doc-1",
            chunk_id="chunk-1",
            source_kind="user",
        )
        con = connect_write(db_path, purpose="assemble")
        try:
            unit = knowledge_unit_of(con, nid, content_class="public_domain")
        finally:
            con.close()
        assert verify_conformance(unit, KnowledgeUnitContract).ok
        # The load-bearing assertion: real investigation, NOT ''.
        assert unit.investigation_id == "inv1"
        assert unit.provenance.chunk_id == "chunk-1"
        assert unit.provenance.source_document_id == "doc-1"
        assert unit.servability.serves_full_text is True
    finally:
        reset()


def test_question_node_projection_investigation_and_servability_correct(monkeypatch):
    # (c) BLOCKER 2: a question node grounds via asks_about/resolved_by, NEVER
    # supported_by — so knowledge_unit_of cannot read investigation_id or
    # grounding off a supported_by edge. Both must come from the metadata
    # mirror that promote_question now stamps.
    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import knowledge_unit_of, promote_question

    db_path, claim_id, reset = _seed_db(monkeypatch)
    try:
        nid = promote_question(
            text="How was Acme funded?",
            investigation_id="inv1",
            asks_about=[claim_id],
            source_document_id="doc-1",
            chunk_id="chunk-1",
        )
        con = connect_write(db_path, purpose="assemble")
        try:
            unit = knowledge_unit_of(con, nid, content_class="public_domain")
        finally:
            con.close()
        assert verify_conformance(unit, KnowledgeUnitContract).ok
        assert unit.node_type == "question"
        assert unit.investigation_id == "inv1"  # NOT '' — from metadata mirror
        assert unit.provenance.chunk_id == "chunk-1"
        assert unit.servability.serves_full_text is True
    finally:
        reset()


def test_empty_investigation_id_is_rejected_by_contract():
    # BLOCKER 2 part (b): an empty investigation_id must FAIL LOUD at the
    # contract boundary (min_length=1), not conform silently — so a future
    # projection gap reds instead of mis-bucketing under '' in SPR-07.
    with pytest.raises(ValueError):
        KnowledgeUnitContract(
            node_id="nid-1",
            node_type="insight",
            text="x",
            investigation_id="",  # empty — must be rejected
            confidence="high",
            retrieval_key="nid-1",
            provenance=ProvenanceLink(source_document_id="doc-1", chunk_id="chunk-1"),
            servability=ServabilityTag(content_class="public_domain", serves_full_text=True),
        )


def test_projection_raises_when_node_has_no_investigation_id(monkeypatch):
    # Defense in depth: if a node somehow carries grounding but no
    # investigation_id (neither on edge nor in metadata), the projection must
    # raise a clear error rather than emit a '' unit. We simulate the gap by
    # blanking the metadata mirror after a deposit.
    import json

    from runtime.db_lock import connect_write
    from substrate.graph.insight_question import knowledge_unit_of, promote_insight

    db_path, claim_id, reset = _seed_db(monkeypatch)
    try:
        nid = promote_insight(
            text="Acme is well funded.",
            investigation_id="inv1",
            confidence="high",
            supported_by=[claim_id],
            source_document_id="doc-1",
            chunk_id="chunk-1",
        )
        # Strip investigation_id off BOTH the supported_by edge and the node
        # metadata mirror to manufacture the gap.
        con = connect_write(db_path, purpose="break")
        try:
            con.execute(
                "UPDATE edges SET investigation_id = '' WHERE source_node_id = ?",
                [nid],
            )
            row = con.execute(
                "SELECT metadata FROM nodes WHERE node_id = ?", [nid]
            ).fetchone()
            meta = json.loads(row[0]) if row and row[0] else {}
            meta.pop("investigation_id", None)
            con.execute(
                "UPDATE nodes SET metadata = ? WHERE node_id = ?",
                [json.dumps(meta), nid],
            )
        finally:
            con.close()
        con = connect_write(db_path, purpose="assemble")
        try:
            with pytest.raises(ValueError, match="investigation_id"):
                knowledge_unit_of(con, nid, content_class="public_domain")
        finally:
            con.close()
    finally:
        reset()


def test_servable_allowlist_drift_guard_welds_contract_to_classifier():
    # The drift-guard that closes BLOCKER 1's actual defect: the contract's
    # FULL_TEXT_SERVABLE is DERIVED from the §9.0 classifier's servable status
    # set, and an import-time assertion welds them. This test proves (1) they
    # are equal today and (2) the guard would RED if they diverged.
    from substrate.books.servability import _SERVABLE_STATUSES
    from substrate.contracts.servable import FULL_TEXT_SERVABLE

    classifier_set = frozenset(s.value for s in _SERVABLE_STATUSES)
    # (1) Welded: the two allowlists are identical right now.
    assert FULL_TEXT_SERVABLE == classifier_set
    # source_declared_open is the class that exposed the drift — it must be in
    # both, or BLOCKER 1 recurs.
    assert "source_declared_open" in FULL_TEXT_SERVABLE
    assert "source_declared_open" in classifier_set
    # (2) The guard bites: simulate the classifier gaining a servable status
    # the contract didn't mirror — the identity assertion (reproduced here) reds.
    drifted_classifier = classifier_set | {"newly_servable_class"}
    assert FULL_TEXT_SERVABLE != drifted_classifier, (
        "if this ever holds, the drift-guard has gone vacuous"
    )
