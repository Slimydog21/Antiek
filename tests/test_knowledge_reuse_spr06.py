"""AFF SPR-06 — retrieve + reuse prior knowledge units into new research.

The flywheel's reuse half, proven mechanically (rigor #3 — a test that passes on
an empty retriever is vacuous and is itself a defect, so the seed-and-catch case
proves the positive test would FAIL if retrieval were broken).

Coverage by milestone:
  M1 retrieval invoked with the question text; empty graph → [].
  M2 §9.0 deny-by-default (non-servable unit absent from the pack); provenance
     markers (src investigation + unit id + score) on every injected unit.
  M3 exactly one knowledge.reused event per start; reused_unit_ids + scores
     equal-length, match the injected set; carries the CONTEXT_PACK_ASSEMBLED id.
  M4 deterministic select-within-budget (run twice, identical); over-budget set →
     rendered reuse layer ≤ budget AND overflow recorded dropped-over-budget.
  M5 two polarities (relevant→injected, unrelated→empty+zero-id event STILL
     emitted) + seed-and-catch non-vacuity.

The embedder is the substrate's word-bag ``HashEmbedding`` (token-overlap aware,
deterministic, no API key) so similarity is REAL: a question that shares
vocabulary with a seeded unit scores high (~0.75-0.94), while a genuinely-
unrelated (zero-shared-token) question scores only ~0.13 hash-collision noise —
below RELEVANCE_FLOOR, so it injects nothing. Non-vacuity is carried by the
POSITIVE direction: the seed-and-catch moves the seeded units' topic so the SAME
question's top similarity collapses ~0.94->~0.14 and injection stops (a no-op
retriever would fail the BEFORE assertion). The negative polarity asserts the
floor suppresses collision-grade similarity, NOT that unrelated similarity is 0.
"""

from __future__ import annotations

import os
import re
from datetime import datetime

import pytest

import substrate.context_pack.knowledge_reuse as kr
from processing.embedding.embed import HashEmbedding
from runtime.db_lock import connect_write
from substrate.context_pack.assembler import (
    CANONICAL_RENDER_ORDER,
    DEFAULT_KIND_PRIORITY,
    DefaultTokenCounter,
    LayerSource,
)
from substrate.event_log.events import trajectory
from substrate.graph.insight_question import promote_insight
from substrate.graph.ops import insert_edge, insert_node
from substrate.graph.retrieval_substrate import make_substrate
from substrate.graph.schema import init_database

# ---------------------------------------------------------------------------
# Seed helpers — a graph with depositable, §9.0-servable prior knowledge units.
# ---------------------------------------------------------------------------


# (unit_text, content_class, servable?) — the content_class drives the §9.0 tag.
_TOPIC_QUANTUM = "neutral atom qubit error rate suppression scaling milestone"


def _seed_graph(
    db_path: str,
    emb: HashEmbedding,
    *,
    units: list[tuple[str, str]],
    prior_investigation: str = "inv-prior",
) -> list[str]:
    """Seed a graph with insight knowledge units, each grounded on a claim node +
    a document of the given content_class (so §9.0 servability is real). Returns
    the seeded node ids. All writes in ONE transaction (the single writer)."""
    con = connect_write(db_path, purpose="spr06_test_seed")
    node_ids: list[str] = []
    try:
        init_database(con)
        con.execute("BEGIN")
        seen_classes: set[str] = set()
        for i, (text, content_class) in enumerate(units):
            doc_id = f"doc-{content_class}"
            chunk_id = f"chunk-{i}"
            if content_class not in seen_classes:
                con.execute(
                    "INSERT INTO documents (document_id, title, source_tier, "
                    "document_type, content_class) VALUES (?, ?, 1, 'paper', ?)",
                    [doc_id, f"Title {content_class}", content_class],
                )
                seen_classes.add(content_class)
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text, "
                "embedding, token_count) VALUES (?, ?, ?, ?, ?, ?)",
                [chunk_id, doc_id, i, text, emb.encode(text), max(1, len(text) // 4)],
            )
            claim_id = insert_node(
                con, canonical_label=f"claim {i}: {text}", node_type="claim",
                graph_scope="depth", investigation_id=prior_investigation,
                embedding=emb.encode(text), on_conflict="ignore",
            )
            nid = promote_insight(
                text=text, investigation_id=prior_investigation, confidence="high",
                supported_by=[claim_id], source_document_id=doc_id, chunk_id=chunk_id,
                embedding_provider=emb, con=con,
            )
            node_ids.append(nid)
        con.execute("COMMIT")
    finally:
        con.close()
    return node_ids


@pytest.fixture(autouse=True)
def _events_dir(monkeypatch, tmp_path):
    """Point the event log at a per-test temp dir. The assembler emits
    CONTEXT_PACK_ASSEMBLED via ``default_events_dir()`` (env-overridable, no
    param), so setting ``ANTIEK_RESEARCH_EVENTS_DIR`` is what co-locates the pack
    event and the knowledge.reused event in ONE queryable trajectory — without
    touching the assembler signature (spec: assembler reused unchanged)."""
    d = os.path.join(tmp_path, "events")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", d)
    return d


@pytest.fixture
def emb():
    return HashEmbedding()


@pytest.fixture
def seeded_quantum_db(emb, tmp_path):
    db = os.path.join(tmp_path, "graph.duckdb")
    node_ids = _seed_graph(
        db, emb,
        units=[
            (_TOPIC_QUANTUM, "public_domain"),
            ("error rate scaling neutral atom platform crossing thousand qubit", "public_domain"),
        ],
    )
    return db, emb, node_ids


# ---------------------------------------------------------------------------
# M1 — retrieval at investigation start
# ---------------------------------------------------------------------------


def test_m1_retrieve_uses_question_text_and_returns_units(seeded_quantum_db):
    db, emb, node_ids = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        assert units, "a question overlapping the seeded units must retrieve them"
        got = {u.unit_id for u in units}
        assert got <= set(node_ids)
        # ranked similarity-desc
        sims = [u.similarity for u in units]
        assert sims == sorted(sims, reverse=True)
        assert units[0].similarity > 0.5
    finally:
        sub.close()


def test_m1_empty_graph_returns_empty_no_crash(emb, tmp_path):
    db = os.path.join(tmp_path, "empty.duckdb")
    con = connect_write(db, purpose="spr06_empty")
    try:
        init_database(con)
    finally:
        con.close()
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(sub, question_text="anything at all")
        assert units == []  # no crash, no synthetic padding
    finally:
        sub.close()


def test_m1_blank_question_returns_empty(seeded_quantum_db):
    db, emb, _ = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        assert kr.retrieve_prior_units(sub, question_text="   ") == []
    finally:
        sub.close()


# ---------------------------------------------------------------------------
# M2 — §9.0 servability deny-by-default + provenance markers
# ---------------------------------------------------------------------------


def _provenance_regex(ru):
    """Match the three required provenance fields for one injected RetrievedUnit
    in the rendered pack text: source investigation_id, unit id, similarity."""
    return re.compile(
        r"src_investigation="
        + re.escape(ru.source_investigation_id)
        + r"\s+unit_id="
        + re.escape(ru.unit_id)
        + r"\s+similarity=([0-9.]+)"
    )


def test_m2_servable_units_injected_with_full_provenance(seeded_quantum_db):
    db, emb, _ = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-new",
            layers=[LayerSource(kind="session", source="task", content="research the topic")],
            units=units,
        )
    finally:
        sub.close()
    assert result.reuse_injected
    assert result.injected
    text = result.pack.text
    # every injected unit carries all three provenance fields, AND the rendered
    # similarity equals its real score (not a floor).
    for ru in result.injected:
        m = _provenance_regex(ru).search(text)
        assert m, f"missing provenance marker for {ru.unit_id} in pack"
        assert abs(float(m.group(1)) - ru.similarity) < 1e-3


def test_m2_servability_deny_by_default_non_servable_absent(emb, tmp_path):
    # Seed one SERVABLE unit and one NON-servable unit (gated content_class →
    # unknown to the §9.0 allowlist) on the SAME relevant topic, so relevance is
    # not what excludes the non-servable one — only §9.0 is.
    db = os.path.join(tmp_path, "mixed.duckdb")
    node_ids = _seed_graph(
        db, emb,
        units=[
            ("neutral atom qubit error rate suppression servable unit", "public_domain"),
            ("neutral atom qubit error rate suppression gated unit", "restricted_pending_opt_in"),
        ],
    )
    servable_id, nonservable_id = node_ids
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
    finally:
        sub.close()
    # both are retrieved (relevance is high for both); §9.0 must drop the gated one.
    retrieved_ids = {u.unit_id for u in units}
    assert servable_id in retrieved_ids
    assert nonservable_id in retrieved_ids

    result = kr.assemble_context_pack_with_reuse(
        role="user_agent", investigation_id="inv-new", layers=[],
            units=units,
    )
    injected_ids = {ru.unit_id for ru in result.injected}
    assert servable_id in injected_ids
    assert nonservable_id not in injected_ids, "non-servable unit must NOT be injected"
    # absent from the rendered pack text
    assert nonservable_id not in result.pack.text
    # AFF SPR-08: the trust gate now OWNS servability and removes the non-servable
    # unit BEFORE SPR-06's budget partition, so it never appears in
    # ``result.decisions`` (partition_units' §9.0 check is now defense-in-depth
    # that no longer fires). The exclusion is recorded on the SPR-08 gate
    # decision instead — one exclusion, one place. (The honest, queryable record
    # of the drop is the reuse.gated event; see test_flywheel_reuse_gate.py.)
    gate_drop = next(d for d in result.gate_decisions if d.unit.unit_id == nonservable_id)
    assert not gate_drop.reusable
    assert "non-servable" in gate_drop.reasons


def test_m2_reuse_layer_kind_registered_in_assembler():
    assert "reuse" in CANONICAL_RENDER_ORDER
    assert DEFAULT_KIND_PRIORITY["reuse"] == 60
    # rendered before graph_evidence, after long_term_skill
    order = list(CANONICAL_RENDER_ORDER)
    assert order.index("long_term_skill") < order.index("reuse") < order.index("graph_evidence")


def test_m2_stale_source_edges_are_advisory_not_a_drop(seeded_quantum_db):
    db, emb, _ = seeded_quantum_db
    with connect_write(db, purpose="spr06_staleness_seed") as con:
        stale_source = insert_node(
            con,
            canonical_label="operator",
            node_type="person",
            graph_scope="depth",
            investigation_id="inv-prior",
            on_conflict="ignore",
        )
        stale_target = insert_node(
            con,
            canonical_label="old employer",
            node_type="organization",
            graph_scope="depth",
            investigation_id="inv-prior",
            on_conflict="ignore",
        )
        insert_edge(
            con,
            edge_id="edge-stale-personnel",
            source_node_id=stale_source,
            target_node_id=stale_target,
            relation="led_by",
            source_tier=1,
            extraction_confidence=0.9,
            graph_scope="depth",
            investigation_id="inv-prior",
            source_document_id="doc-public_domain",
            valid_from=datetime(2025, 1, 1),
            on_conflict="ignore",
        )

    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub,
            question_text="neutral atom qubit error rate suppression",
            staleness_as_of=datetime(2026, 7, 1),
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent",
            investigation_id="inv-stale-advisory",
            layers=[],
            units=units,
        )
    finally:
        sub.close()

    advisory_units = [u for u in result.injected if u.staleness_advisories]
    assert advisory_units, "stale source edges should mark injected reuse units"
    assert any(
        a.edge_id == "edge-stale-personnel" and a.claim_class == "personnel"
        for unit in advisory_units
        for a in unit.staleness_advisories
    )
    assert kr.DECISION_INJECTED in [d.decision for d in result.decisions]
    assert "staleness_advisory=edge-stale-personnel:personnel" in result.pack.text

    payload = next(
        r for r in trajectory("inv-stale-advisory")
        if r["action_type"] == "knowledge.reused"
    )["payload"]
    assert set(payload["stale_advisory_unit_ids"]) == {
        u.unit_id for u in advisory_units
    }


# ---------------------------------------------------------------------------
# M3 — the typed knowledge.reused event
# ---------------------------------------------------------------------------


def test_m3_event_emitted_with_units_and_scores(seeded_quantum_db):
    db, emb, _ = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-event", layers=[],
            units=units,
        )
    finally:
        sub.close()

    rows = trajectory("inv-event")
    reused = [r for r in rows if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, "exactly one knowledge.reused event per investigation"
    payload = reused[0]["payload"]
    # reused_unit_ids + scores equal-length and match the injected set
    assert len(payload["reused_unit_ids"]) == len(payload["scores"])
    assert payload["reused_unit_ids"] == [ru.unit_id for ru in result.injected]
    assert len(payload["reused_unit_ids"]) == len(result.injected)
    assert payload["reused_unit_ids"], "relevant question must inject a non-empty set"
    # the event carries the CONTEXT_PACK_ASSEMBLED event id, and is parented to it
    assert payload["context_pack_event_id"] == result.pack.event_id
    assert reused[0]["parent_event_id"] == result.pack.event_id
    # ids are a subset of what was retrieved
    assert set(payload["reused_unit_ids"]) <= {ru.unit_id for ru in units}
    # there is exactly one CONTEXT_PACK_ASSEMBLED it points at
    packs = [r for r in rows if r["action_type"] == "context_pack.assembled"]
    assert any(p["event_id"] == result.pack.event_id for p in packs)


def test_m3_event_decisions_distinguish_drop_reasons(emb, tmp_path):
    db = os.path.join(tmp_path, "reasons.duckdb")
    _seed_graph(
        db, emb,
        units=[
            ("neutral atom qubit error rate suppression servable", "public_domain"),
            ("neutral atom qubit error rate suppression gated", "restricted_pending_opt_in"),
        ],
    )
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-reasons", layers=[],
            units=units,
        )
    finally:
        sub.close()
    rows = trajectory("inv-reasons")
    payload = next(r for r in rows if r["action_type"] == "knowledge.reused")["payload"]
    # AFF SPR-08: the non-servable unit is removed by the trust gate BEFORE the
    # SPR-06 partition, so the knowledge.reused event now records only the units
    # that cleared the gate. The servable+grounded one is injected; the gated
    # one is recorded on a reuse.gated event, not here. The knowledge.reused
    # decisions cover only the gate-passing candidates (one, here).
    assert kr.DECISION_INJECTED in payload["decisions"]
    assert kr.DECISION_NOT_SERVABLE not in payload["decisions"]
    n_passed_gate = sum(1 for d in result.gate_decisions if d.reusable)
    assert len(payload["decisions"]) == n_passed_gate
    assert len(payload["source_investigation_ids"]) == n_passed_gate
    # the non-servable unit's exclusion is recorded as a reuse.gated event
    gated = [r for r in rows if r["action_type"] == "reuse.gated"]
    assert len(gated) == 1
    assert "non-servable" in gated[0]["payload"]["reasons"]


# ---------------------------------------------------------------------------
# M4 — token budget + determinism
# ---------------------------------------------------------------------------


def _fake_units(n: int, *, prefix: str = "unit", inv: str = "inv-prior", sim_start: float = 0.9):
    """Build n RetrievedUnits with descending similarity + servable tags, without
    touching the DB. Uses a tiny stand-in unit object carrying the fields
    RetrievedUnit reads."""
    from substrate.contracts.nodes import (
        KnowledgeUnitContract,
        ProvenanceLink,
        ServabilityTag,
    )

    out = []
    for i in range(n):
        text = f"{prefix} number {i} " + ("lorem ipsum dolor sit amet " * 8)
        nid = f"node-{prefix}-{i:03d}"
        unit = KnowledgeUnitContract(
            node_id=nid, node_type="insight", text=text, investigation_id=inv,
            confidence="high", retrieval_key=nid,
            provenance=ProvenanceLink(source_document_id="d1", chunk_id="c1"),
            servability=ServabilityTag(content_class="public_domain", serves_full_text=True),
            # AFF SPR-08: these synthetic budget-test units carry a passing
            # groundedness score so they clear the trust gate and reach the
            # budget partition (which is what these tests exercise). The slot is
            # filled at projection time on the real-DB path (score_groundedness);
            # the fake path sets it directly to stay above REUSE_GROUNDEDNESS_THRESHOLD.
            groundedness_score=0.9,
        )
        out.append(kr.RetrievedUnit(unit=unit, similarity=sim_start - i * 0.001))
    return out


def test_m4_select_within_budget_is_deterministic():
    units = _fake_units(30)
    counter = DefaultTokenCounter()
    a, da = kr.select_units_within_budget(units, budget=500, counter=counter, header_text=kr._REUSE_HEADER)
    b, db_ = kr.select_units_within_budget(units, budget=500, counter=counter, header_text=kr._REUSE_HEADER)
    assert [u.unit_id for u in a] == [u.unit_id for u in b]  # identical set AND order
    assert [d.decision for d in da] == [d.decision for d in db_]
    # ties broken by unit id ascending: feed equal-similarity units shuffled
    eq = _fake_units(10, sim_start=0.5)
    eq = [kr.RetrievedUnit(unit=u.unit, similarity=0.5) for u in eq]
    import random
    shuffled = list(eq)
    random.Random(7).shuffle(shuffled)
    sel, _ = kr.select_units_within_budget(shuffled, budget=10_000, counter=counter)
    assert [u.unit_id for u in sel] == sorted(u.unit_id for u in sel)


def test_m4_over_budget_layer_bounded_and_overflow_recorded(emb, tmp_path):
    # Many servable, relevant units; a tight budget forces overflow. Each fake
    # unit renders to ~80 tokens, so 40 units (~3200 tokens) comfortably exceed
    # this 500-token budget and several must be dropped.
    units = _fake_units(40, sim_start=0.95)
    counter = DefaultTokenCounter()
    budget = 500
    layer, injected, decisions, coverage = kr.build_reuse_layer(
        units, token_budget=budget, counter=counter,
    )
    assert layer is not None and injected
    # (a) rendered reuse layer token count ≤ the reuse budget
    rendered_tokens = counter.count(layer.content)
    assert rendered_tokens <= budget, f"{rendered_tokens} > {budget}"
    # (b) overflow units recorded dropped-over-budget
    over = [d for d in decisions if d.decision == kr.DECISION_OVER_BUDGET]
    assert over, "an over-budget set must record dropped-over-budget"
    assert coverage.dropped_over_budget == len(over)
    # the dropped ones are the LOWEST-ranked (highest-scored never dropped)
    injected_ids = {u.unit_id for u in injected}
    over_ids = {d.unit_id for d in over}
    assert injected_ids.isdisjoint(over_ids)
    # the highest-similarity unit is injected, never over-budget-dropped
    top = max(units, key=lambda u: (u.similarity, u.unit_id))
    assert top.unit_id in injected_ids


def test_m4_over_budget_event_decisions_carry_overflow(emb, tmp_path):
    # ~80 units × ~80 tokens ≈ 6400 tokens — exceeds the role's 4000-token reuse
    # budget cap, so the assemble path must drop some over-budget.
    units = _fake_units(80, sim_start=0.95)
    result = kr.assemble_context_pack_with_reuse(
        role="user_agent", investigation_id="inv-budget", layers=[],
        units=units,
    )
    rows = trajectory("inv-budget")
    payload = next(r for r in rows if r["action_type"] == "knowledge.reused")["payload"]
    assert kr.DECISION_OVER_BUDGET in payload["decisions"]
    # the injected set is exactly reused_unit_ids
    assert payload["reused_unit_ids"] == [u.unit_id for u in result.injected]


def test_m4_budget_fraction_leaves_room_for_rest_of_pack():
    # the fraction is a strict minority of the pack budget (room for the rest)
    from substrate.context_pack.assembler import default_budget_for
    base = default_budget_for("user_agent")
    assert kr.reuse_token_budget("user_agent") <= int(base * kr.REUSE_BUDGET_FRACTION)
    assert kr.REUSE_BUDGET_FRACTION < 0.5
    assert kr.reuse_token_budget("user_agent") <= kr.REUSE_BUDGET_CAP_TOKENS


# ---------------------------------------------------------------------------
# M5 — the falsifiable two-polarity test + seed-and-catch
# ---------------------------------------------------------------------------


def test_m5_relevant_injects(seeded_quantum_db):
    db, emb, node_ids = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="neutral atom qubit error rate suppression scaling",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-pos", layers=[],
            units=units,
        )
    finally:
        sub.close()
    assert result.reuse_injected
    assert result.injected
    # seeded units appear in the pack text with provenance
    for ru in result.injected:
        assert _provenance_regex(ru).search(result.pack.text)
    rows = trajectory("inv-pos")
    payload = next(r for r in rows if r["action_type"] == "knowledge.reused")["payload"]
    assert payload["reused_unit_ids"], "positive polarity: non-empty reused_unit_ids"


def test_m5_unrelated_injects_none_but_event_still_emitted(seeded_quantum_db):
    db, emb, _ = seeded_quantum_db
    sub = make_substrate("brute_force", db, model=emb)
    try:
        units = kr.retrieve_prior_units(
            sub, question_text="medieval cathedral architecture flying buttress stained glass",
        )
        result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-neg", layers=[],
            units=units,
        )
    finally:
        sub.close()
    assert not result.reuse_injected, "unrelated question: empty reuse layer"
    assert result.injected == []
    # the reuse layer is absent from the pack
    assert kr.REUSE_LAYER_SOURCE not in result.pack.text
    # but the event is STILL emitted with zero ids (reuse-of-nothing recorded)
    rows = trajectory("inv-neg")
    reused = [r for r in rows if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1
    assert reused[0]["payload"]["reused_unit_ids"] == []


def test_m5_seed_and_catch_proves_non_vacuity(emb, tmp_path):
    """Mutate the seeded units to an unrelated topic; the previously-relevant
    question must then inject NOTHING. If retrieval were a no-op (always []), the
    positive test would ALSO pass for the wrong reason — this proves the positive
    test depends on real, question-keyed retrieval.

    Mechanism: hold the QUESTION fixed and move the seeded units' TOPIC. The
    BEFORE graph seeds units on the question's topic (relevant → must inject).
    The MUTATED graph seeds the SAME grounding shape but on an unrelated topic
    (the units' "topic" is mutated) → the same question must now inject nothing.
    (Two graphs rather than an in-place UPDATE because DuckDB forbids mutating a
    node row referenced by an FK edge; the falsification logic is identical.)"""
    question = "neutral atom qubit error rate suppression scaling"

    # BEFORE: units on the question's topic — the question injects them (live).
    db_before = os.path.join(tmp_path, "catch_before.duckdb")
    _seed_graph(db_before, emb, units=[(_TOPIC_QUANTUM, "public_domain")])
    sub = make_substrate("brute_force", db_before, model=emb)
    try:
        before = kr.retrieve_prior_units(sub, question_text=question)
        before_result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-before", layers=[],
            units=before,
        )
    finally:
        sub.close()
    assert before_result.injected, "pre-mutation: the relevant question MUST inject"

    # MUTATED: the seeded units now carry an UNRELATED topic (same grounding
    # shape, servable). The SAME previously-relevant question must inject nothing.
    db_after = os.path.join(tmp_path, "catch_after.duckdb")
    _seed_graph(
        db_after, emb,
        units=[("tropical coral reef bleaching ocean temperature acidification", "public_domain")],
    )
    sub2 = make_substrate("brute_force", db_after, model=emb)
    try:
        after = kr.retrieve_prior_units(sub2, question_text=question)
        after_result = kr.assemble_context_pack_with_reuse(
            role="user_agent", investigation_id="inv-after", layers=[],
            units=after,
        )
    finally:
        sub2.close()
    assert after_result.injected == [], (
        "post-mutation: the previously-relevant question must inject NOTHING — "
        "if this fails, retrieval is not actually keyed on the question/units "
        "(the positive test is vacuous)."
    )
    # The REAL non-vacuity discriminator: the SAME question's top retrieved
    # similarity collapses from a real match to collision noise when the seeded
    # topic moves — this (not the floor) is what proves retrieval is question-keyed.
    assert before and before[0].similarity > 0.5, (before[0].similarity if before else None)
    assert (not after) or after[0].similarity < kr.RELEVANCE_FLOOR, after[0].similarity
    # event still emitted, zero ids
    rows = trajectory("inv-after")
    payload = next(r for r in rows if r["action_type"] == "knowledge.reused")["payload"]
    assert payload["reused_unit_ids"] == []


# ---------------------------------------------------------------------------
# Runner wiring — §16: reuse rides host_local.start, no protocol method.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_runner_start_emits_reuse_before_first_step(seeded_quantum_db):
    """host_local.start, given a RetrievalSubstrate, emits knowledge.reused on
    the investigation's JSONL before the browse loop's first step — exercising
    the in-place start extension (no new protocol method)."""
    from runtime.research_runner.host_local import HostLocalRunner, make_demo_loop
    from runtime.research_runner.protocol import ResearchPlan

    db, emb, _ = seeded_quantum_db
    # events_dir left default so it follows ANTIEK_RESEARCH_EVENTS_DIR (the
    # autouse fixture) — the runner's lifecycle events, the assembler's pack
    # event, and the reuse event then all co-locate in one trajectory.
    sub = make_substrate("brute_force", db, model=emb)
    try:
        runner = HostLocalRunner(
            make_demo_loop(steps=1, delay_s=0.0),
            retrieval_substrate=sub,
        )
        plan = ResearchPlan(
            investigation_id="inv-runner",
            sub_question="neutral atom qubit error rate suppression scaling",
        )
        await runner.start("inv-runner", plan)
        await runner.join()
    finally:
        sub.close()

    rows = trajectory("inv-runner")
    reused = [r for r in rows if r["action_type"] == "knowledge.reused"]
    assert len(reused) == 1, "exactly one knowledge.reused emitted from start"
    assert reused[0]["payload"]["reused_unit_ids"], "relevant question injects units"


@pytest.mark.asyncio
async def test_runner_start_without_substrate_is_unchanged(seeded_quantum_db):
    """No RetrievalSubstrate → no reuse event; start behaves exactly as before."""
    from runtime.research_runner.host_local import HostLocalRunner, make_demo_loop
    from runtime.research_runner.protocol import ResearchPlan

    db, emb, _ = seeded_quantum_db
    runner = HostLocalRunner(make_demo_loop(steps=1))
    plan = ResearchPlan(investigation_id="inv-nosub", sub_question="anything")
    await runner.start("inv-nosub", plan)
    await runner.join()

    rows = trajectory("inv-nosub")
    assert [r for r in rows if r["action_type"] == "knowledge.reused"] == []
