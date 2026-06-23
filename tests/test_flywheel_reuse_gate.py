"""AFF SPR-08 — the trust gate on reuse, proven mechanically.

The flywheel reuses prior knowledge units into NEW investigations (SPR-06), so
an ungrounded or non-servable unit does not just sit in the graph — it seeds the
next synthesis. This gate excludes a unit from reuse UNLESS its groundedness
score ≥ ``REUSE_GROUNDEDNESS_THRESHOLD`` AND it serves full text (§9.0). The two
conditions are INDEPENDENT, and every excluded unit emits exactly one
``reuse.gated`` event.

What this proves (and what it does NOT):
  * COMPOSE — the score is the shipped #27 lexical scorer's verdict, read off
    the unit's slot (filled at projection time) or re-scored deterministically;
    servability is the §9.0 answer recorded at deposit, read never re-derived.
  * M1 the slot holds the scorer's float; scorer_id attributable; a no-chunk
    unit floors at 0.0 / not-supported (the #27 no-evidence floor).
  * M2 the two conditions are independent (high-but-non-servable excluded;
    servable-but-below excluded), enforced BEFORE any text reaches the pack.
  * M3 one threshold knob; override=0.9 excludes a 0.6 unit that 0.5 admits.
  * M4 a mutation test through the REAL filter (0.7→in, 0.3→out, 0.7→in) +
    seed-and-catch: a no-op gate body makes the test RED.
  * M5 one reuse.gated event per excluded unit, both reasons when both apply;
    admitted units emit NO event.

The gate does NOT make reuse "safe" — the lexical proxy is a coverage + polarity
+ number proxy, not a judge. It excludes below-threshold + non-servable units,
mutation-proven and logged. That is its whole claim.
"""

from __future__ import annotations

import os

import pytest

import substrate.context_pack.knowledge_reuse as kr
import substrate.flywheel.reuse_gate as rg
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from substrate.context_pack.assembler import LayerSource
from substrate.contracts.nodes import (
    KnowledgeUnitContract,
    ProvenanceLink,
    ServabilityTag,
)
from substrate.eval.groundedness import DEFAULT_SCORER_ID, DEFAULT_SUPPORTED_THRESHOLD
from substrate.event_log.events import trajectory
from substrate.graph.insight_question import knowledge_unit_of, promote_insight
from substrate.graph.ops import insert_node
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database

# ---------------------------------------------------------------------------
# Fixtures — point the event log at a temp dir; deterministic embedder.
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch, tmp_path):
    d = os.path.join(tmp_path, "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", d)
    return d


@pytest.fixture(autouse=True)
def _no_env_threshold(monkeypatch):
    """The gate's module-level threshold is sourced from the environment at
    IMPORT time; the tests pass an explicit ``threshold=`` so they never depend
    on a stray env var. Clear it here so the DEFAULT-equals-scorer assertion is
    meaningful regardless of the shell."""
    monkeypatch.delenv("REUSE_GROUNDEDNESS_THRESHOLD", raising=False)


@pytest.fixture
def emb():
    return HashEmbedding()


# A chunk that genuinely supports its claim (high lexical coverage → grounded),
# and a unit text that flips the chunk's polarity + fabricates a number (low
# coverage / contradiction → ungrounded), mirroring the #27 scorer fixtures.
_GROUNDED_TEXT = "neutral atom qubit error rate suppression scaling milestone"
_GROUNDED_CHUNK = (
    "The neutral atom platform demonstrated qubit error rate suppression and a "
    "scaling milestone across the array."
)
_UNGROUNDED_TEXT = "the platform did not achieve suppression failing at 999 qubits"
_UNGROUNDED_CHUNK = (
    "The neutral atom platform demonstrated qubit error rate suppression and a "
    "scaling milestone across the array."
)


def _ru(
    *,
    node_id: str = "node-1",
    text: str = _GROUNDED_TEXT,
    score: float | None = 0.9,
    serves: bool = True,
    content_class: str | None = "public_domain",
    chunk_id: str = "chunk-1",
    similarity: float = 0.8,
    inv: str = "inv-prior",
) -> kr.RetrievedUnit:
    """A RetrievedUnit with the trust-relevant fields set directly (no DB)."""
    unit = KnowledgeUnitContract(
        node_id=node_id, node_type="insight", text=text, investigation_id=inv,
        confidence="high", retrieval_key=node_id,
        provenance=ProvenanceLink(source_document_id="doc-1", chunk_id=chunk_id),
        servability=ServabilityTag(content_class=content_class, serves_full_text=serves),
        groundedness_score=score,
    )
    return kr.RetrievedUnit(unit=unit, similarity=similarity)


def _seed_unit(db_path, emb, *, text, content_class="public_domain", chunk_text,
               inv="inv-prior", idx=0):
    """Seed ONE insight knowledge unit grounded on a claim + a document of the
    given content_class, with a chunk carrying ``chunk_text``. Returns node_id.
    All writes in one transaction (the single writer)."""
    con = connect_write(db_path, purpose="spr08_seed")
    try:
        init_database(con)
        con.execute("BEGIN")
        doc_id = f"doc-{content_class}"
        chunk_id = f"chunk-{idx}"
        exists = con.execute(
            "SELECT 1 FROM documents WHERE document_id = ?", [doc_id]
        ).fetchone()
        if not exists:
            con.execute(
                "INSERT INTO documents (document_id, title, source_tier, "
                "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                [doc_id, f"Title {content_class}", content_class],
            )
        con.execute(
            "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
            "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
            [chunk_id, doc_id, idx, chunk_text, emb.encode(chunk_text), 8],
        )
        claim_id = insert_node(
            con, canonical_label=f"claim {idx}: {chunk_text}", node_type="claim",
            graph_scope="depth", investigation_id=inv,
            embedding=emb.encode(chunk_text), on_conflict="ignore",
        )
        nid = promote_insight(
            text=text, investigation_id=inv, confidence="high",
            supported_by=[claim_id], source_document_id=doc_id, chunk_id=chunk_id,
            embedding_provider=emb, con=con,
        )
        con.execute("COMMIT")
    finally:
        con.close()
    return nid


# ---------------------------------------------------------------------------
# M1 — score units with the #27 scorer → fill the groundedness slot
# ---------------------------------------------------------------------------


def test_m1_projection_fills_slot_with_scorer_return(emb, tmp_path):
    """The slot holds EXACTLY the #27 scorer's float for the same (claim,
    chunk_texts), and scorer_id is attributable."""
    from substrate.eval.groundedness import score_claim

    db = os.path.join(tmp_path, "m1.duckdb")
    nid = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK)
    con = connect_write(db, purpose="m1_read")
    try:
        unit = knowledge_unit_of(con, nid, content_class="public_domain",
                                 score_groundedness=True)
    finally:
        con.close()
    # the slot equals score_claim's return for the same claim + chunk text
    expected = score_claim(_GROUNDED_TEXT, [_GROUNDED_CHUNK],
                           cited_chunk_ids=[unit.provenance.chunk_id]).score
    assert unit.groundedness_score == expected
    assert unit.groundedness_score >= DEFAULT_SUPPORTED_THRESHOLD  # a real match
    # The slot deliberately holds only the float (Decision A;
    # docs/decisions/spr-08-reuse-threshold.md). scorer_id attribution on the
    # EMITTED record for a REAL deposited unit is proven (non-tautologically) by
    # test_m1_emitted_event_carries_real_deposited_score_and_scorer_id below.


def test_m1_emitted_event_carries_real_deposited_score_and_scorer_id(emb, tmp_path):
    """M1's 'attributable' criterion proven on a REAL record, not a constant: a
    deposited+projected unit's emitted reuse.gated event carries the scorer_id
    AND the unit's actual stored groundedness score. The unit is excluded on §9.0
    (non-servable source) so the proof does NOT depend on the score being below
    any bar — the score is grounded (≥0.5) and still recorded on the event, and
    the only exclusion reason is non-servable."""
    db = os.path.join(tmp_path, "m1attr.duckdb")
    nid = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK,
                     content_class="restricted_pending_opt_in")  # → gated → non-servable
    con = connect_write(db, purpose="m1attr_read")
    try:
        unit = knowledge_unit_of(con, nid, content_class="restricted_pending_opt_in",
                                 score_groundedness=True)
    finally:
        con.close()
    assert unit.groundedness_score is not None and unit.groundedness_score >= 0.5
    assert not unit.servability.serves_full_text  # gated content class → non-servable
    rg.filter_reusable(
        [kr.RetrievedUnit(unit=unit, similarity=0.9)],
        investigation_id="inv-m1attr", threshold=0.5, context_pack_event_id="pk-m1attr",
    )
    gated = [r for r in trajectory("inv-m1attr") if r["action_type"] == "reuse.gated"]
    assert len(gated) == 1
    p = gated[0]["payload"]
    assert p["scorer_id"] == DEFAULT_SCORER_ID
    assert p["groundedness_score"] == round(unit.groundedness_score, 6)
    assert p["reasons"] == ["non-servable"]  # grounded ≥ threshold, so NOT below-threshold


def test_m1_unflagged_projection_leaves_slot_none(emb, tmp_path):
    """Decision B is OPT-IN: without score_groundedness the slot stays None, so
    SPR-04 conformance (a unit with None conforms) is untouched."""
    db = os.path.join(tmp_path, "m1none.duckdb")
    nid = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK)
    con = connect_write(db, purpose="m1none_read")
    try:
        unit = knowledge_unit_of(con, nid, content_class="public_domain")
    finally:
        con.close()
    assert unit.groundedness_score is None


def test_m1_no_chunk_text_floors_at_zero_not_supported(emb, tmp_path):
    """The #27 no-evidence floor is preserved: a unit whose chunk text cannot be
    resolved scores 0.0 (not-supported), never worked around. We exercise this
    via the gate's lazy resolver returning None for the chunk."""
    ru = _ru(score=None, chunk_id="missing-chunk")
    # lazy score with a resolver that knows no chunk text → empty evidence → 0.0
    score = rg.groundedness_of(ru, chunk_text_for=lambda cid: None)
    assert score == 0.0
    # and a 0.0 unit is below the supported threshold → not reusable
    decision = rg.evaluate_unit(ru, threshold=DEFAULT_SUPPORTED_THRESHOLD,
                                chunk_text_for=lambda cid: None)
    assert not decision.reusable
    assert "below-threshold" in decision.reasons


def test_m1_lazy_rescore_equals_deposit_time_score(emb, tmp_path):
    """The lazy branch's load-bearing claim — 'the lexical backend is
    deterministic, so a deposit-time score and a gate-time re-score are
    identical' — proven: deposit a unit (slot filled), then re-score the SAME
    unit with the slot cleared and a resolver returning its real chunk text; the
    lazy score must equal the deposit-time score exactly. Covers the lazy
    re-score branch that production's pre-filled-slot path never exercises."""
    db = os.path.join(tmp_path, "m1lazy.duckdb")
    nid = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK)
    con = connect_write(db, purpose="m1lazy_read")
    try:
        deposited = knowledge_unit_of(con, nid, content_class="public_domain",
                                      score_groundedness=True)
    finally:
        con.close()
    deposit_score = deposited.groundedness_score
    assert deposit_score is not None
    # same unit, slot cleared, lazy re-score from the real chunk text
    cleared = deposited.model_copy(update={"groundedness_score": None})
    ru = kr.RetrievedUnit(unit=cleared, similarity=0.8)
    lazy = rg.groundedness_of(ru, chunk_text_for=lambda cid: _GROUNDED_CHUNK)
    assert lazy == deposit_score


# ---------------------------------------------------------------------------
# M2 — gate on groundedness AND §9.0 servability, INDEPENDENT
# ---------------------------------------------------------------------------


def test_m2_servable_and_grounded_is_reusable():
    decision = rg.evaluate_unit(_ru(score=0.7, serves=True), threshold=0.5)
    assert decision.reusable
    assert decision.reasons == ()


def test_m2_high_groundedness_but_non_servable_excluded():
    """A unit can be perfectly grounded and STILL excluded on §9.0 alone — the
    conditions are independent."""
    decision = rg.evaluate_unit(
        _ru(score=0.99, serves=False, content_class=None), threshold=0.5,
    )
    assert not decision.reusable
    assert "non-servable" in decision.reasons
    assert "below-threshold" not in decision.reasons  # groundedness is fine


def test_m2_servable_but_below_threshold_excluded():
    """A unit can be fully servable and STILL excluded on groundedness alone."""
    decision = rg.evaluate_unit(_ru(score=0.30, serves=True), threshold=0.5)
    assert not decision.reusable
    assert "below-threshold" in decision.reasons
    assert "non-servable" not in decision.reasons  # servability is fine


def test_m2_both_conditions_fail_records_both_reasons():
    decision = rg.evaluate_unit(
        _ru(score=0.10, serves=False, content_class=None), threshold=0.5,
    )
    assert not decision.reusable
    assert set(decision.reasons) == {"below-threshold", "non-servable"}


def test_m2_gate_runs_before_text_reaches_pack(emb, tmp_path):
    """An excluded unit is absent from the assembled pack text — the gate runs
    BEFORE the reuse layer is rendered, so no excluded text ever reaches the
    model."""
    db = os.path.join(tmp_path, "m2pack.duckdb")
    # a grounded+servable unit and a grounded-but-NON-servable unit on the topic
    servable_id = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK,
                             content_class="public_domain", idx=0)
    nonservable_id = _seed_unit(db, emb, text=_GROUNDED_TEXT + " gated",
                                chunk_text=_GROUNDED_CHUNK,
                                content_class="restricted_pending_opt_in", idx=1)
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression scaling",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-m2pack",
            layers=[LayerSource(kind="session", source="task", content="research")],
            units=units,
        )
    finally:
        sub.close()
    injected_ids = {ru.unit_id for ru in result.injected}
    assert servable_id in injected_ids
    assert nonservable_id not in injected_ids
    assert nonservable_id not in result.pack.text


# ---------------------------------------------------------------------------
# M3 — ONE threshold knob; override changes the bar, single source
# ---------------------------------------------------------------------------


def test_m3_default_threshold_anchored_to_scorer():
    assert rg.REUSE_GROUNDEDNESS_THRESHOLD == DEFAULT_SUPPORTED_THRESHOLD == 0.5


def test_m3_override_excludes_a_unit_the_default_admits():
    """A 0.6-grounded unit: default 0.5 admits it, override 0.9 excludes it.
    The threshold is the ONLY knob and it is honored everywhere it is passed."""
    ru = _ru(score=0.6, serves=True)
    assert rg.evaluate_unit(ru, threshold=0.5).reusable
    strict = rg.evaluate_unit(ru, threshold=0.9)
    assert not strict.reusable
    assert "below-threshold" in strict.reasons


def test_m3_env_override_is_read(monkeypatch):
    """The single knob is env-overridable (sourced through one helper). A 0.9
    env bar excludes a 0.6 unit that the 0.5 default admits."""
    monkeypatch.setenv("REUSE_GROUNDEDNESS_THRESHOLD", "0.9")
    import importlib
    reloaded = importlib.reload(rg)
    try:
        assert reloaded.REUSE_GROUNDEDNESS_THRESHOLD == 0.9
        ru = _ru(score=0.6, serves=True)
        assert not reloaded.evaluate_unit(ru, threshold=reloaded.REUSE_GROUNDEDNESS_THRESHOLD).reusable
    finally:
        monkeypatch.delenv("REUSE_GROUNDEDNESS_THRESHOLD", raising=False)
        importlib.reload(rg)  # restore the module default for later tests


def test_m3_garbage_env_fails_loud(monkeypatch):
    monkeypatch.setenv("REUSE_GROUNDEDNESS_THRESHOLD", "not-a-number")
    import importlib
    with pytest.raises(ValueError):
        importlib.reload(rg)
    monkeypatch.delenv("REUSE_GROUNDEDNESS_THRESHOLD", raising=False)
    importlib.reload(rg)  # restore


# ---------------------------------------------------------------------------
# M4 — the mutation test through the REAL filter + the seed-and-catch
# ---------------------------------------------------------------------------


def test_below_threshold_unit_excluded_then_restored():
    """A unit at 0.7 is reusable; the SAME unit at 0.3 is excluded; back at 0.7
    it is reusable again — proven through the REAL ``filter_reusable`` path (no
    mock). This is the gate's load-bearing behaviour: the groundedness score is
    what decides, and nothing else changed between the three calls."""
    threshold = 0.5

    def reusable_ids(score):
        units = [_ru(node_id="mut-unit", score=score, serves=True)]
        kept, _ = rg.filter_reusable(
            units, investigation_id="inv-mut", threshold=threshold, emit=False,
        )
        return {ru.unit_id for ru in kept}

    assert reusable_ids(0.7) == {"mut-unit"}   # grounded → in
    assert reusable_ids(0.3) == set()          # below threshold → out
    assert reusable_ids(0.7) == {"mut-unit"}   # restored → in again


# ---------------------------------------------------------------------------
# M5 — one reuse.gated event per excluded unit; admitted units emit none
# ---------------------------------------------------------------------------


def test_m5_excluded_unit_emits_exactly_one_event():
    units = [_ru(node_id="excl", score=0.2, serves=True)]
    kept, decisions = rg.filter_reusable(
        units, investigation_id="inv-m5one", threshold=0.5,
        context_pack_event_id="pack-1",
    )
    assert kept == []
    rows = [r for r in trajectory("inv-m5one") if r["action_type"] == "reuse.gated"]
    assert len(rows) == 1
    payload = rows[0]["payload"]
    assert payload["unit_id"] == "excl"
    assert payload["groundedness_score"] == 0.2
    assert payload["threshold"] == 0.5
    assert payload["scorer_id"] == DEFAULT_SCORER_ID
    assert payload["reasons"] == ["below-threshold"]
    assert payload["context_pack_event_id"] == "pack-1"


def test_m5_both_reasons_on_one_event():
    units = [_ru(node_id="both", score=0.1, serves=False, content_class=None)]
    rg.filter_reusable(units, investigation_id="inv-m5both", threshold=0.5)
    rows = [r for r in trajectory("inv-m5both") if r["action_type"] == "reuse.gated"]
    assert len(rows) == 1
    assert set(rows[0]["payload"]["reasons"]) == {"below-threshold", "non-servable"}


def test_m5_admitted_unit_emits_no_event():
    units = [_ru(node_id="ok", score=0.9, serves=True)]
    kept, _ = rg.filter_reusable(units, investigation_id="inv-m5ok", threshold=0.5)
    assert [ru.unit_id for ru in kept] == ["ok"]
    rows = [r for r in trajectory("inv-m5ok") if r["action_type"] == "reuse.gated"]
    assert rows == []  # admitted → no reuse.gated event


def test_m5_one_event_per_excluded_unit_via_assemble(emb, tmp_path):
    """Through the FULL assemble path: a non-servable unit produces exactly one
    reuse.gated event AND is absent from the pack — never two conflicting
    decisions for the same unit (Decision C)."""
    db = os.path.join(tmp_path, "m5assemble.duckdb")
    _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK,
               content_class="public_domain", idx=0)
    nonservable_id = _seed_unit(db, emb, text=_GROUNDED_TEXT + " gated",
                                chunk_text=_GROUNDED_CHUNK,
                                content_class="restricted_pending_opt_in", idx=1)
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression scaling",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-m5asm", layers=[], units=units,
        )
    finally:
        sub.close()
    rows = trajectory("inv-m5asm")
    gated = [r for r in rows if r["action_type"] == "reuse.gated"]
    # exactly one reuse.gated event for the non-servable unit
    gated_for_nonservable = [g for g in gated if g["payload"]["unit_id"] == nonservable_id]
    assert len(gated_for_nonservable) == 1
    assert "non-servable" in gated_for_nonservable[0]["payload"]["reasons"]
    # carries the assembled pack id (joinable to what the model did NOT see)
    assert gated_for_nonservable[0]["payload"]["context_pack_event_id"] == result.pack.event_id
    # the non-servable unit is absent from the pack AND not in the injected set
    assert nonservable_id not in result.pack.text
    assert nonservable_id not in {ru.unit_id for ru in result.injected}


def test_m5_admitted_unit_not_in_gated_events_via_assemble(emb, tmp_path):
    """The grounded+servable unit that IS reused emits no reuse.gated event."""
    db = os.path.join(tmp_path, "m5admit.duckdb")
    servable_id = _seed_unit(db, emb, text=_GROUNDED_TEXT, chunk_text=_GROUNDED_CHUNK,
                             content_class="public_domain", idx=0)
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression scaling",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-m5admit", layers=[], units=units,
        )
    finally:
        sub.close()
    assert servable_id in {ru.unit_id for ru in result.injected}
    gated = [r for r in trajectory("inv-m5admit") if r["action_type"] == "reuse.gated"]
    assert servable_id not in {g["payload"]["unit_id"] for g in gated}


# ---------------------------------------------------------------------------
# Composition guard — the gate carries the §9.0 answer, never re-derives it
# ---------------------------------------------------------------------------


def test_gate_reads_servability_does_not_rederive():
    """The gate's servability verdict is exactly what the unit's tag says — it
    never recomputes deny-by-default. A servable tag passes that condition; a
    non-servable tag fails it; the gate does not re-classify content_class."""
    assert rg.evaluate_unit(_ru(score=0.9, serves=True)).reusable
    # a tag that says non-servable fails §9.0 regardless of content_class string
    d = rg.evaluate_unit(_ru(score=0.9, serves=False, content_class=None))
    assert "non-servable" in d.reasons
