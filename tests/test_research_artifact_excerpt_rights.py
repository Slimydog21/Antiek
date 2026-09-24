"""The research artifact's synthesis excerpt is cleared against its sources.

The excerpt is the investigation's thesis prose, and that prose is written from
the investigation's sources: it can repeat a paywalled passage verbatim. So the
excerpt passes a source-aware gate before it reaches any export surface: it is
shown only when the investigation has sources and every one of them resolves to
a servable document. A non-servable source, a source whose rights cannot be
resolved (a vanished node, a dangling synthesis pin) or no traceable source at
all withholds it, with the visible §9.0 notice rather than a silent gap.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.event_log import log_event
from substrate.graph import ensure_initialized
from substrate.graph.insight_question import promote_insight
from substrate.research_artifact import build_body, export_research_artifact
from substrate.schemas.events import ActionType

PASSAGE = "VERBATIM PAYWALLED PASSAGE that only a personal-reading source holds"
PUBLIC = "Public-domain finding that is servable in full."
WITHHELD_NOTICE = "Synthesis not available to display"


@pytest.fixture
def env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="ra-excerpt-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", os.path.join(tmpdir, "arts"))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(db)
    con = connect_write(db)
    try:
        for doc_id, cls, holder, title in (
            ("doc-pr", "personal_reading", "holder-x", "Paywalled essay"),
            ("doc-rs", "restricted_pending_opt_in", "holder-y", "Gated book"),
            ("doc-pd", "public_domain", None, "Old pamphlet"),
        ):
            con.execute(
                "INSERT INTO documents (document_id, source_tier, document_type, "
                "content_class, ip_holder_id, title) VALUES (?,?,?,?,?,?)",
                [doc_id, 1, "article", cls, holder, title],
            )
        for chunk_id, doc_id, text in (
            ("c-rs", "doc-rs", PASSAGE),
            ("c-pd", "doc-pd", PUBLIC),
        ):
            con.execute(
                "INSERT INTO chunks (chunk_id, document_id, chunk_index, text) "
                "VALUES (?,?,0,?)",
                [chunk_id, doc_id, text],
            )
    finally:
        con.close()
    return {"db": db, "events": events}


def _public_insight(inv: str) -> str:
    return promote_insight(
        text=f"{PUBLIC} [{inv}]",
        investigation_id=inv,
        confidence="moderate",
        source_document_id="doc-pd",
    )


def _complete(inv: str, events: str, summary: str) -> None:
    log_event(
        inv,
        ActionType.INVESTIGATION_COMPLETED,
        payload={"thesis_summary": summary},
        events_dir=events,
    )


def _archive(env: dict, inv: str, sid: str, pins: list[tuple[str, str]]) -> None:
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO syntheses (synthesis_id, investigation_id, target_question, "
            "synthesis_timestamp, status, implicit_recommendation, thesis_text) "
            "VALUES (?, ?, 'Q', now(), 'passed', 'proceed', ?)",
            [sid, inv, f"Thesis. {PASSAGE}"],
        )
        for kind, eid in pins:
            con.execute(
                "INSERT INTO synthesis_substrate_manifest "
                "(synthesis_id, entity_kind, entity_id) VALUES (?, ?, ?)",
                [sid, kind, eid],
            )
    finally:
        con.close()


def _body(env: dict, inv: str):
    return build_body(inv, db_path=env["db"], events_dir=env["events"])


def _assert_withheld(env: dict, inv: str) -> None:
    body = _body(env, inv)
    assert body.synthesis_excerpt is None, body.synthesis_excerpt
    assert body.synthesis_withheld is True
    assert PASSAGE not in body.model_dump_json()


def test_excerpt_repeating_a_cite_only_insight_is_withheld_on_every_surface(env):
    # codex's reproduction: the insight goes cite-only, the thesis summary that
    # repeats its passage verbatim must not carry it out instead.
    inv = "inv-x1"
    promote_insight(
        text=PASSAGE, investigation_id=inv, confidence="moderate",
        source_document_id="doc-pr",
    )
    _public_insight(inv)
    _complete(inv, env["events"], f"The thesis holds. {PASSAGE}")

    body = _body(env, inv)
    assert any(i.text.startswith("[cite-only") for i in body.insights)
    _assert_withheld(env, inv)

    res = export_research_artifact(
        inv, db_path=env["db"], events_dir=env["events"], emit_event=False
    )
    exported = res.path.read_text(encoding="utf-8")
    assert PASSAGE not in exported
    assert WITHHELD_NOTICE in exported
    assert PASSAGE not in res.twin_notes_path.read_text(encoding="utf-8")

    # A clean sibling: the compose surface needs two members, and the clean
    # artifact proves the route does render a cleared excerpt.
    clean = "inv-x1-clean"
    _public_insight(clean)
    clean_summary = "A clean thesis over the public-domain pamphlet."
    _complete(clean, env["events"], clean_summary)

    client = TestClient(create_app(register_wrestling=False))
    artifact = client.get(f"/research/{inv}/artifact.html")
    assert artifact.status_code == 200, artifact.text[:300]
    assert PASSAGE not in artifact.text
    assert WITHHELD_NOTICE in artifact.text
    twin = client.get(f"/research/{inv}/artifact/twin-notes.html")
    assert twin.status_code == 200, twin.text[:300]
    assert PASSAGE not in twin.text
    merged = client.get(
        "/research/artifacts/compose/draft-merge.html",
        params=[("investigation_ids", inv), ("investigation_ids", clean)],
    )
    assert merged.status_code == 200, merged.text[:300]
    assert PASSAGE not in merged.text
    assert clean_summary in client.get(f"/research/{clean}/artifact.html").text


def test_excerpt_withheld_when_an_archived_synthesis_pins_a_restricted_chunk(env):
    # No insight carries the passage: only the synthesis manifest knows the
    # thesis stood on a gated chunk.
    inv = "inv-x2"
    _public_insight(inv)
    _archive(env, inv, "syn-x2", [("chunk", "c-rs"), ("chunk", "c-pd")])
    log_event(
        inv, ActionType.SYNTHESIS_ARCHIVED, synthesis_id="syn-x2",
        payload={"thesis_summary": f"Archived. {PASSAGE}"}, events_dir=env["events"],
    )
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_synthesis_pin_dangles(env):
    inv = "inv-x3"
    _public_insight(inv)
    _archive(env, inv, "syn-x3", [("chunk", "c-pd"), ("chunk", "c-deleted")])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_the_investigation_gathered_a_non_servable_document(env):
    inv = "inv-x4"
    _public_insight(inv)
    con = connect_write(env["db"])
    try:
        con.execute(
            "UPDATE documents SET investigation_id = ? WHERE document_id = 'doc-pr'",
            [inv],
        )
    finally:
        con.close()
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_distilled_insight_vanished(env):
    # The distillation skips a node whose row is gone; its rights are then
    # unknown, and the thesis written from it cannot be cleared.
    inv = "inv-x5"
    _public_insight(inv)
    gone = promote_insight(
        text=PASSAGE, investigation_id=inv, confidence="moderate",
        source_document_id="doc-pr",
    )
    con = connect_write(env["db"])
    try:
        con.execute(
            "DELETE FROM edges WHERE source_node_id = ? OR target_node_id = ?",
            [gone, gone],
        )
        con.execute("DELETE FROM nodes WHERE node_id = ?", [gone])
    finally:
        con.close()
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_with_no_traceable_source_is_withheld(env):
    inv = "inv-x6"
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_whose_every_source_is_servable_is_exported(env):
    inv = "inv-x7"
    _public_insight(inv)
    _archive(env, inv, "syn-x7", [("chunk", "c-pd"), ("document", "doc-pd")])
    summary = "A thesis grounded only in the public-domain pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_no_synthesis_is_not_reported_as_withheld(env):
    inv = "inv-x8"
    _public_insight(inv)
    body = _body(env, inv)
    assert body.synthesis_excerpt is None
    assert body.synthesis_withheld is False


def test_excerpt_withheld_when_an_investigation_edge_grounds_on_a_restricted_chunk(env):
    # Extraction wrote an edge from the gated chunk during this investigation;
    # no insight or synthesis pin names it.
    inv = "inv-x9"
    _public_insight(inv)
    con = connect_write(env["db"])
    try:
        for node_id in ("n-a", "n-b"):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, 'entity', 'depth')",
                [node_id, node_id],
            )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_tier, extraction_confidence, graph_scope, "
            "investigation_id) VALUES ('e-rs', 'n-a', 'n-b', 'rel', 'c-rs', 1, 0.9, "
            "'depth', ?)",
            [inv],
        )
    finally:
        con.close()
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_an_event_anchors_to_a_non_servable_document(env):
    # A reading-loop event anchors the investigation to the paywalled essay.
    inv = "inv-x10"
    _public_insight(inv)
    log_event(
        inv, ActionType.DOCUMENT_LOADED, document_id="doc-pr",
        payload={"media_type": "pdf", "content_hash": "h", "size_bytes": 1},
        events_dir=env["events"],
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_an_inserted_claim_names_no_source(env):
    # The trajectory records a claim node the investigation inserted; the
    # claim names no source, so its rights (and the thesis's) are unknown.
    inv = "inv-x11"
    _public_insight(inv)
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-claim-x11', 'an unsupported claim', 'claim', 'depth')"
        )
    finally:
        con.close()
    log_event(
        inv, ActionType.GRAPH_NODE_INSERTED,
        payload={"node_id": "n-claim-x11", "canonical_label": "an unsupported claim",
                 "node_type": "claim", "graph_scope": "depth", "has_embedding": False},
        events_dir=env["events"],
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_gate_reads_the_events_dir_it_is_given(env, monkeypatch, tmp_path):
    # build_body's events_dir, not the environment's, decides what the
    # investigation stood on.
    inv = "inv-x12"
    promote_insight(
        text=PASSAGE, investigation_id=inv, confidence="moderate",
        source_document_id="doc-pr",
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "elsewhere"))
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    assert body.synthesis_withheld is True
    assert PASSAGE not in body.model_dump_json()


# ── every grounding pointer of a node, and every recorded synthesis ──


def test_excerpt_withheld_when_a_public_insight_also_rests_on_an_earlier_restricted_edge(env):
    # codex's reproduction: the insight's metadata names a public document, but
    # a supported_by edge written by an EARLIER investigation grounds it on the
    # paywalled essay too. Metadata alone cleared both the insight and the
    # excerpt; every grounding pointer has to clear.
    inv = "inv-x13"
    node = _public_insight(inv)
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-x13-target', 'target', 'entity', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope, "
            "investigation_id) VALUES ('e-x13', ?, 'n-x13-target', 'supported_by', "
            "'doc-pr', 1, 0.9, 'depth', 'inv-earlier')",
            [node],
        )
    finally:
        con.close()
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_node_metadata_chunk_is_gone(env):
    # The node names a public document AND a grounding chunk; the chunk row is
    # gone, so that pointer's rights are unknown.
    inv = "inv-x14"
    _public_insight(inv)
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata) VALUES ('n-x14', 'a claim', 'claim', 'depth', ?)",
            ['{"source_document_id": "doc-pd", "chunk_id": "c-deleted"}'],
        )
    finally:
        con.close()
    log_event(
        inv, ActionType.GRAPH_NODE_INSERTED,
        payload={"node_id": "n-x14", "canonical_label": "a claim",
                 "node_type": "claim", "graph_scope": "depth", "has_embedding": False},
        events_dir=env["events"],
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_recorded_synthesis_is_missing(env):
    # codex's reproduction: one public insight, and a synthesis.archived event
    # naming a synthesis whose row is gone. Its provenance is unknown, so the
    # public insight must not clear the thesis written from it.
    inv = "inv-x15"
    _public_insight(inv)
    log_event(
        inv, ActionType.SYNTHESIS_ARCHIVED, synthesis_id="syn-gone",
        payload={"thesis_summary": f"Archived. {PASSAGE}"}, events_dir=env["events"],
    )
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_synthesis_manifest_is_empty(env):
    inv = "inv-x16"
    _public_insight(inv)
    _archive(env, inv, "syn-x16", [])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


# ── round 2: every pointer-shaped field, wherever it is recorded ──
#
# The gate does not enumerate provenance fields. It walks every node's metadata
# and every event payload on the trajectory and follows every value under a key
# that names a chunk, document, edge or source. These tests pin the two
# encodings codex found unread (retrieval-event supporting_claims and node
# metadata source_chunk_ids), then prove a pointer field nobody has written yet
# is caught with no code change.


def _retrieval(inv: str, events: str, *, chunk_ids=(), edge_ids=()) -> None:
    from substrate.event_log import emit_typed
    from substrate.schemas.events import EvidenceRetrieveDeliveredPayload

    emit_typed(
        inv,
        EvidenceRetrieveDeliveredPayload(
            sub_question="What does the record say?",
            answer="An answer.",
            supporting_claims=[{
                "claim": "A claim.", "evidence_type": "direct",
                "chunk_ids": list(chunk_ids), "edge_ids": list(edge_ids),
                "confidence": "high", "confidence_basis": "quoted",
            }],
        ),
        role="evidence_retriever",
        events_dir=events,
    )


def _edge(env: dict, edge_id: str, *, chunk_id: str | None) -> None:
    con = connect_write(env["db"])
    try:
        for node_id in (f"{edge_id}-a", f"{edge_id}-b"):
            con.execute(
                "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
                "VALUES (?, ?, 'entity', 'depth')",
                [node_id, node_id],
            )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES (?, ?, ?, 'rel', ?, 1, 0.9, 'depth')",
            [edge_id, f"{edge_id}-a", f"{edge_id}-b", chunk_id],
        )
    finally:
        con.close()


def _metadata_insight(env: dict, inv: str, node_id: str, meta: str) -> None:
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata) VALUES (?, ?, 'insight', 'depth', ?)",
            [node_id, PASSAGE, meta],
        )
    finally:
        con.close()
    log_event(
        inv, ActionType.GRAPH_NODE_INSERTED,
        payload={"node_id": node_id, "canonical_label": PASSAGE,
                 "node_type": "insight", "graph_scope": "depth", "has_embedding": False},
        events_dir=env["events"],
    )


def test_excerpt_withheld_when_a_retrieval_event_cites_a_restricted_chunk(env):
    # codex's reproduction: one public insight, and the retriever's delivered
    # event cites the gated chunk through supporting_claims[].chunk_ids.
    inv = "inv-r1"
    _public_insight(inv)
    _retrieval(inv, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_retrieval_event_cites_a_missing_chunk(env):
    inv = "inv-r2"
    _public_insight(inv)
    _retrieval(inv, env["events"], chunk_ids=["c-pd", "c-gone"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_retrieval_event_cites_a_restricted_edge(env):
    inv = "inv-r3"
    _public_insight(inv)
    _edge(env, "e-r3", chunk_id="c-rs")
    _retrieval(inv, env["events"], edge_ids=["e-r3"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_retrieval_event_cites_a_missing_edge(env):
    inv = "inv-r4"
    _public_insight(inv)
    _retrieval(inv, env["events"], chunk_ids=["c-pd"], edge_ids=["e-gone"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_cleared_when_every_retrieval_pointer_is_public(env):
    # Positive control: the walker does not withhold what it can clear.
    inv = "inv-r5"
    _public_insight(inv)
    _edge(env, "e-r5", chunk_id="c-pd")
    _retrieval(inv, env["events"], chunk_ids=["c-pd"], edge_ids=["e-r5"])
    summary = "A thesis the retriever grounded on the public pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_insight_and_excerpt_withheld_when_source_chunk_ids_names_a_missing_chunk(env):
    # codex's reproduction: document_pass persists source_chunk_ids beside a
    # public source_document_id; one listed chunk is gone.
    inv = "inv-r6"
    _metadata_insight(
        env, inv, "n-r6",
        '{"source_document_id": "doc-pd", "source_chunk_ids": ["c-pd", "c-gone"]}',
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    _assert_withheld(env, inv)


def test_insight_and_excerpt_withheld_when_source_chunk_ids_names_a_restricted_chunk(env):
    inv = "inv-r7"
    _metadata_insight(
        env, inv, "n-r7",
        '{"source_document_id": "doc-pd", "source_chunk_ids": ["c-pd", "c-rs"]}',
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    _assert_withheld(env, inv)


def test_public_source_chunk_ids_export_the_insight_and_the_excerpt(env):
    inv = "inv-r8"
    _metadata_insight(
        env, inv, "n-r8",
        '{"source_document_id": "doc-pd", "source_chunk_ids": ["c-pd"]}',
    )
    summary = "A thesis over the pamphlet's chunks."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert [i.text for i in body.insights] == [PASSAGE]
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


# ── the hard-to-vary proof: a pointer field no code names ──


def test_an_unnamed_metadata_pointer_field_is_caught_without_code_changes(env):
    # backup_chunk_ids appears nowhere in the codebase. It names the gated
    # chunk, nested one level down, and both the insight and the excerpt stay
    # withheld because the gate reads pointer-shaped keys, not a field list.
    inv = "inv-r9"
    _metadata_insight(
        env, inv, "n-r9",
        '{"source_document_id": "doc-pd", '
        '"provenance": {"backup_chunk_ids": ["c-rs"]}}',
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    _assert_withheld(env, inv)


def test_an_unnamed_event_pointer_field_is_caught_without_code_changes(env):
    # An event type and payload shape no code names, with the pointer buried in
    # a list of objects: an alternate document id for the paywalled essay.
    inv = "inv-r10"
    _public_insight(inv)
    log_event(
        inv, "experimental.reading.note",
        payload={"trail": [{"step": 1, "alt_doc_id": "doc-pr"}]},
        events_dir=env["events"],
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_sub_investigation_retrieved_a_restricted_chunk(env):
    # The parent escalated a question into a child investigation; the child's
    # retrieval stood on the gated chunk, and the parent thesis draws on it.
    inv, child = "inv-r11", "inv-r11-child"
    _public_insight(inv)
    log_event(
        inv, ActionType.QUESTION_ESCALATED_TO_RESEARCH,
        payload={"question_id": "q-r11", "child_investigation_id": child},
        events_dir=env["events"],
    )
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def _escalate(inv: str, child: str, events: str) -> None:
    log_event(
        inv, ActionType.QUESTION_ESCALATED_TO_RESEARCH,
        payload={"question_id": f"q-{inv}", "child_investigation_id": child},
        events_dir=events,
    )


@pytest.mark.parametrize("lost", ["missing", "corrupt", "torn"])
def test_excerpt_withheld_when_a_sub_investigations_events_cannot_be_read(env, lost):
    # The child's events are the only record of what it stood on. A deleted
    # log, a log that no longer parses, or one record that no longer parses
    # beside a readable public one leaves that record unknown, so the child
    # stays unresolved instead of dropping out and letting the public parent
    # clear the thesis.
    inv, child = f"inv-lost-{lost}", f"inv-lost-{lost}-child"
    _public_insight(inv)
    _escalate(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)
    log = Path(env["events"]) / f"{child}.jsonl"
    if lost == "missing":
        log.unlink()
    elif lost == "corrupt":
        log.write_text("{broken JSON\n")
    else:
        log.unlink()
        _retrieval(child, env["events"], chunk_ids=["c-pd"])
        with log.open("a") as f:
            f.write("{torn record\n")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_record_of_its_own_trajectory_cannot_be_read(env):
    inv = "inv-own-torn"
    _public_insight(inv)
    _retrieval(inv, env["events"], chunk_ids=["c-pd"])
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    with (Path(env["events"]) / f"{inv}.jsonl").open("a") as f:
        f.write("{torn record\n")
    _assert_withheld(env, inv)


def test_a_child_id_that_is_not_an_event_storage_name_is_unresolved(env, tmp_path):
    # Child ids come from event payloads. An absolute path used to be joined
    # onto the events dir (os.path.join keeps the absolute part) and read, so
    # a public-only log planted outside the events dir cleared the thesis.
    outside = tmp_path / "outside"
    outside.mkdir()
    _retrieval("decoy", str(outside), chunk_ids=["c-pd"])
    inv = "inv-escape"
    _public_insight(inv)
    _escalate(inv, str(outside / "decoy"), env["events"])
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    _assert_withheld(env, inv)


def test_excerpt_cleared_when_a_readable_sub_investigation_stood_on_public_sources(env):
    # Positive control for the three tests above: a child whose events all
    # read, and whose sources are public, does not withhold.
    inv, child = "inv-child-ok", "inv-child-ok-child"
    _public_insight(inv)
    _escalate(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-pd"])
    summary = "A thesis the child grounded on the public pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


@pytest.mark.parametrize(
    "content",
    ["", "{}\n", '{"event_id": "e-1"}\n',
     '{"event_id": "e-1", "action_type": "evidence.retrieve.delivered", "payload": "{not json"}\n'],
    ids=["empty", "empty-object", "no-action-type", "undecodable-payload"],
)
def test_excerpt_withheld_when_a_sub_investigations_log_holds_no_usable_event(env, content):
    # A stored log proves the child existed; one that holds nothing usable as
    # an event says nothing about what it stood on, so it stays unresolved.
    inv, child = "inv-odd", "inv-odd-child"
    _public_insight(inv)
    _escalate(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)
    (Path(env["events"]) / f"{child}.jsonl").write_text(content)
    _assert_withheld(env, inv)


@pytest.mark.parametrize(("key", "payload"), [
    ("null", None), ("empty", {}), ("partial", {"sub_question": "q"}),
])
def test_excerpt_withheld_when_a_childs_evidence_event_lost_its_required_fields(env, key, payload):
    # A retrieval event whose envelope is intact but whose payload no longer
    # carries what its schema requires records no evidence we can read.
    inv, child = f"inv-hollow-{key}", f"inv-hollow-{key}-child"
    _public_insight(inv)
    _escalate(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)
    import json as _json
    (Path(env["events"]) / f"{child}.jsonl").write_text(_json.dumps({
        "event_id": "e-hollow", "investigation_id": child,
        "action_type": "evidence.retrieve.delivered", "payload": payload,
        "emitted_at": "2026-09-24T00:00:00Z"}) + "\n")
    _assert_withheld(env, inv)


def test_a_leaf_whose_lineage_events_carry_runner_extras_still_clears(env):
    # The research runners write investigation.start_requested as
    # {"sub_question": ...} and spawned_from with an extra sub_question, which
    # their typed models reject. Those events carry no evidence, so they must
    # not withhold a session whose leaf stood on public sources.
    session, leaf = "sess-runner", "sess-runner-leaf"
    _public_insight(session)
    log_event(leaf, ActionType.INVESTIGATION_SPAWNED_FROM,
              payload={"parent_investigation_id": session, "sub_question": "Sub?"},
              events_dir=env["events"])
    log_event(leaf, ActionType.INVESTIGATION_START_REQUESTED,
              payload={"sub_question": "Sub?"}, events_dir=env["events"])
    _retrieval(leaf, env["events"], chunk_ids=["c-pd"])
    summary = "A session thesis its runner leaf grounded on the public pamphlet."
    _complete(session, env["events"], summary)
    body = _body(env, session)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_an_unrelated_log_with_malformed_timestamps_does_not_break_a_healthy_export(env):
    (Path(env["events"]) / "inv-unrelated.jsonl").write_text(
        '{"event_id": "a", "action_type": "investigation.completed", "emitted_at": 1, "payload": {}}\n'
        '{"event_id": "b", "action_type": "investigation.completed", "emitted_at": "x", "payload": {}}\n')
    inv = "inv-healthy"
    _public_insight(inv)
    _retrieval(inv, env["events"], chunk_ids=["c-pd"])
    summary = "A healthy thesis grounded on the public pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_a_child_with_malformed_timestamps_withholds_without_raising(env):
    inv, child = "inv-ts", "inv-ts-child"
    _public_insight(inv)
    _escalate(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-pd"])
    with (Path(env["events"]) / f"{child}.jsonl").open("a") as f:
        f.write('{"event_id": "t1", "action_type": "investigation.completed", "emitted_at": 7, "payload": {}}\n')
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    _assert_withheld(env, inv)


def test_an_undecodable_payload_in_its_own_log_withholds_without_raising(env):
    inv = "inv-own-payload"
    _public_insight(inv)
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    with (Path(env["events"]) / f"{inv}.jsonl").open("a") as f:
        f.write('{"event_id": "e-bad", "action_type": "graph.node_inserted", '
                '"emitted_at": "9999", "payload": "{not json"}\n')
    _assert_withheld(env, inv)


def _reserve(inv: str, child: str, events: str) -> None:
    # What the note-taker emits for an unresolvable challenge: a child id
    # reserved for a chase that may never happen.
    from substrate.event_log import emit_typed
    from substrate.schemas.events import QuestionEscalatedToResearchPayload

    emit_typed(inv, QuestionEscalatedToResearchPayload(
        question_id=f"q-{child}", child_investigation_id=child, launched=False),
        role="note_taker", document_id="doc-pd", events_dir=events)


def test_a_reserved_child_that_never_ran_does_not_withhold(env):
    inv = "inv-reserve"
    _public_insight(inv)
    _reserve(inv, "inv-reserve-child", env["events"])
    summary = "A thesis grounded on the public pamphlet, with a challenge parked."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_a_reserved_child_that_later_ran_is_walked(env):
    inv, child = "inv-reserve-ran", "inv-reserve-ran-child"
    _public_insight(inv)
    _reserve(inv, child, env["events"])
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_a_reserved_child_with_a_stored_but_empty_log_withholds(env):
    inv, child = "inv-reserve-empty", "inv-reserve-empty-child"
    _public_insight(inv)
    _reserve(inv, child, env["events"])
    (Path(env["events"]) / f"{child}.jsonl").write_text("")
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    _assert_withheld(env, inv)


def test_a_reservation_also_referenced_as_launched_withholds_when_its_log_is_missing(env):
    # Only a child every reference calls reserved may be absent; one launch
    # reference (here an escalation that predates the marker) means it ran.
    inv, child = "inv-reserve-both", "inv-reserve-both-child"
    _public_insight(inv)
    _reserve(inv, child, env["events"])
    _escalate(inv, child, env["events"])
    _complete(inv, env["events"], f"Thesis. {PUBLIC}")
    _assert_withheld(env, inv)


def _spawn(child: str, parent: str, events: str, *, via: str) -> None:
    from substrate.event_log import emit_typed
    from substrate.schemas.events import (
        InvestigationSpawnedFromPayload,
        InvestigationStartRequestedPayload,
    )

    payload = (
        InvestigationSpawnedFromPayload(parent_investigation_id=parent, spawn_context="sub-question")
        if via == "spawned_from"
        else InvestigationStartRequestedPayload(question="Sub-question?", parent_investigation_id=parent)
    )
    emit_typed(child, payload, role="operator", events_dir=events)


@pytest.mark.parametrize("via", ["spawned_from", "start_requested"])
def test_excerpt_withheld_when_a_leaf_linked_only_from_its_own_log_retrieved_a_restricted_chunk(env, via):
    # A cascade leaf or chase child records its parent in its own log; the
    # parent's events never name it. Its evidence feeds the parent's synthesis.
    session, leaf = f"sess-{via}", f"sess-{via}-leaf"
    _public_insight(session)
    _spawn(leaf, session, env["events"], via=via)
    _retrieval(leaf, env["events"], chunk_ids=["c-rs"])
    _complete(session, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, session)


def test_excerpt_withheld_when_a_backward_linked_leaf_has_an_unreadable_record(env):
    session, leaf = "sess-torn", "sess-torn-leaf"
    _public_insight(session)
    _spawn(leaf, session, env["events"], via="spawned_from")
    _retrieval(leaf, env["events"], chunk_ids=["c-pd"])
    with (Path(env["events"]) / f"{leaf}.jsonl").open("a") as f:
        f.write("{torn record\n")
    _complete(session, env["events"], f"Thesis. {PUBLIC}")
    _assert_withheld(env, session)


def test_excerpt_cleared_when_a_backward_linked_leaf_stood_on_public_sources(env):
    session, leaf = "sess-public", "sess-public-leaf"
    _public_insight(session)
    _spawn(leaf, session, env["events"], via="spawned_from")
    _retrieval(leaf, env["events"], chunk_ids=["c-pd"])
    summary = "A session thesis its leaf grounded on the public pamphlet."
    _complete(session, env["events"], summary)
    body = _body(env, session)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def _branch(parent: str, child: str, events: str, *, via: str) -> None:
    # What every launch path now writes into the parent before the child's
    # first event (THREAD-CONTRACT §1.3).
    from substrate.event_log import record_branch

    record_branch(parent, child, via=via, events_dir=events)


def test_a_reserved_child_that_ran_and_lost_its_log_withholds(env):
    # Codex round 6: a reservation became an exemption again once the child
    # that actually ran lost its log. The chase into the reserved id now
    # records a branch in the parent, so the lost child stays unresolved.
    inv, child = "inv-reserve-lost", "inv-reserve-lost-child"
    _public_insight(inv)
    _reserve(inv, child, env["events"])
    _branch(inv, child, env["events"], via="reserved_launch")
    _retrieval(child, env["events"], chunk_ids=["c-rs"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)
    (Path(env["events"]) / f"{child}.jsonl").unlink()
    _assert_withheld(env, inv)


@pytest.mark.parametrize("damage", ["deleted", "emptied", "corrupted"])
def test_a_branched_cascade_leaf_whose_log_is_damaged_withholds(env, damage):
    # Codex round 6: a leaf linked only from its own log vanished when that log
    # was emptied or corrupted. The session now holds the branch.
    session, leaf = f"sess-branch-{damage}", f"sess-branch-{damage}-leaf"
    _public_insight(session)
    _branch(session, leaf, env["events"], via="cascade_leaf")
    _spawn(leaf, session, env["events"], via="spawned_from")
    _retrieval(leaf, env["events"], chunk_ids=["c-rs"])
    _complete(session, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, session)
    log = Path(env["events"]) / f"{leaf}.jsonl"
    if damage == "deleted":
        log.unlink()
    elif damage == "emptied":
        log.write_text("")
    else:
        log.write_text("{not json\n")
    _assert_withheld(env, session)


def test_excerpt_cleared_when_a_branched_child_stood_on_public_sources(env):
    session, leaf = "sess-branch-public", "sess-branch-public-leaf"
    _public_insight(session)
    _branch(session, leaf, env["events"], via="cascade_leaf")
    _spawn(leaf, session, env["events"], via="spawned_from")
    _retrieval(leaf, env["events"], chunk_ids=["c-pd"])
    summary = "A session thesis its branched leaf grounded on the public pamphlet."
    _complete(session, env["events"], summary)
    body = _body(env, session)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_excerpt_withheld_when_a_cited_edge_endpoint_names_a_restricted_document(env):
    # The retrieved edge carries no chunk of its own; one endpoint node's
    # metadata records the paywalled essay. An edge stands on its endpoints.
    inv = "inv-r12"
    _public_insight(inv)
    _edge(env, "e-r12", chunk_id="c-pd")
    con = connect_write(env["db"])
    try:
        con.execute(
            "UPDATE nodes SET metadata = ? WHERE node_id = 'e-r12-b'",
            ['{"source_document_id": "doc-pr"}'],
        )
    finally:
        con.close()
    _retrieval(inv, env["events"], edge_ids=["e-r12"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_source_pointer_names_no_row(env):
    # A source_id's key does not say what it names; one that names no
    # document, chunk or edge cannot be cleared.
    inv = "inv-r13"
    _public_insight(inv)
    log_event(
        inv, "experimental.reading.note",
        payload={"source_ids": ["c-pd", "nowhere-1"]},
        events_dir=env["events"],
    )
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_unparseable_node_metadata_withholds_rather_than_hiding_its_pointers(env):
    # Truncated metadata cannot be read, and what it cannot show may be the
    # gated chunk; it counts as an unresolved pointer, not as no pointer.
    inv = "inv-r14"
    _metadata_insight(
        env, inv, "n-r14",
        '{"source_document_id": "doc-pd", "source_chunk_ids": ["c-rs"',
    )
    # A public supported_by edge, so the node is not merely source-less.
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('n-r14-target', 'target', 'entity', 'depth')"
        )
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "source_document_id, source_tier, extraction_confidence, graph_scope) "
            "VALUES ('e-r14', 'n-r14', 'n-r14-target', 'supported_by', 'doc-pd', "
            "1, 0.9, 'depth')"
        )
    finally:
        con.close()
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    body = _body(env, inv)
    assert [i.text[:10] for i in body.insights] == ["[cite-only"]
    _assert_withheld(env, inv)



# ── round 3: an edge stands on its endpoints' complete grounding ──
#
# A cited edge (from a retrieval event or a synthesis manifest pin) grounds on
# its endpoint nodes, and an endpoint grounds by the same rules as any node:
# every metadata pointer AND every supported_by edge out of it, followed
# transitively with cycle protection. Round 2 read only the endpoints'
# metadata, so an endpoint whose restricted or missing source was recorded on
# an earlier supported_by edge exported the thesis.


def _endpoint_support(
    env: dict, edge_id: str, node_id: str, *,
    chunk_id: str | None = None, meta: str | None = None, target: str | None = None,
) -> None:
    """A supported_by edge out of ``node_id`` that an earlier investigation
    wrote, grounded on ``chunk_id`` and/or pointers in ``meta``."""
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO edges (edge_id, source_node_id, target_node_id, relation, "
            "chunk_id, metadata, source_tier, extraction_confidence, graph_scope, "
            "investigation_id) VALUES (?, ?, ?, 'supported_by', ?, ?, 1, 0.9, "
            "'depth', 'earlier-investigation')",
            [edge_id, node_id, target or node_id, chunk_id, meta],
        )
    finally:
        con.close()


def _node(env: dict, node_id: str, node_type: str = "entity", meta: str | None = None) -> None:
    con = connect_write(env["db"])
    try:
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope, "
            "metadata) VALUES (?, ?, ?, 'depth', ?)",
            [node_id, node_id, node_type, meta],
        )
    finally:
        con.close()


@pytest.mark.parametrize(
    ("chunk_id", "meta"),
    [("c-rs", None), (None, '{"source_chunk_ids": ["c-gone"]}')],
    ids=["restricted-chunk", "missing-source-chunk"],
)
def test_excerpt_withheld_when_a_retrieved_edge_endpoint_rests_on_an_earlier_edge(
    env, chunk_id, meta
):
    # codex's reproduction: the retrieved edge's own chunk is public; its
    # endpoint's earlier supported_by edge references the gated chunk, or a
    # chunk that is gone.
    inv = "inv-e1"
    _public_insight(inv)
    _edge(env, "e-read", chunk_id="c-pd")
    _endpoint_support(env, "e-support", "e-read-b", chunk_id=chunk_id, meta=meta,
                      target="e-read-a")
    _retrieval(inv, env["events"], edge_ids=["e-read"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


@pytest.mark.parametrize(
    ("chunk_id", "meta"),
    [("c-rs", None), (None, '{"source_chunk_ids": ["c-gone"]}')],
    ids=["restricted-chunk", "missing-source-chunk"],
)
def test_excerpt_withheld_when_a_pinned_edge_endpoint_rests_on_an_earlier_edge(
    env, chunk_id, meta
):
    # The manifest-edge entrypoint: an archived synthesis pins the public
    # edge, and nothing else on the trajectory names the endpoint's support.
    inv = "inv-e2"
    _public_insight(inv)
    _edge(env, "e-pin", chunk_id="c-pd")
    _endpoint_support(env, "e-pin-support", "e-pin-a", chunk_id=chunk_id, meta=meta,
                      target="e-pin-b")
    _archive(env, inv, "syn-e2", [("edge", "e-pin")])
    log_event(
        inv, ActionType.SYNTHESIS_ARCHIVED, synthesis_id="syn-e2",
        payload={"thesis_summary": f"Archived. {PASSAGE}"}, events_dir=env["events"],
    )
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_the_restricted_support_is_two_hops_from_the_edge(env):
    # e-read-b is supported by a claim node whose own supported_by edge
    # stands on the gated chunk: grounding is followed transitively.
    inv = "inv-e3"
    _public_insight(inv)
    _edge(env, "e-read", chunk_id="c-pd")
    _node(env, "n-evidence", "claim")
    _node(env, "n-quote")
    _endpoint_support(env, "e-hop-1", "e-read-b", chunk_id="c-pd", target="n-evidence")
    _endpoint_support(env, "e-hop-2", "n-evidence", chunk_id="c-rs", target="n-quote")
    _retrieval(inv, env["events"], edge_ids=["e-read"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_an_unnamed_pointer_field_two_hops_from_the_edge_is_caught(env):
    # The hard-to-vary proof at the endpoint: a pointer key no code names
    # (backup_chunk_ids), nested in the metadata of the node an endpoint's
    # supported_by edge leads to.
    inv = "inv-e4"
    _public_insight(inv)
    _edge(env, "e-read", chunk_id="c-pd")
    _node(env, "n-evidence", "claim",
          '{"source_document_id": "doc-pd", "notes": [{"backup_chunk_ids": ["c-rs"]}]}')
    _endpoint_support(env, "e-hop-1", "e-read-b", chunk_id="c-pd", target="n-evidence")
    _retrieval(inv, env["events"], edge_ids=["e-read"])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_cleared_when_every_endpoint_support_is_public(env):
    # Positive control: the transitive walk withholds nothing it can clear,
    # and a supported_by cycle between the endpoints terminates. Both
    # entrypoints (a retrieval event and a manifest pin) name the edge.
    inv = "inv-e5"
    _public_insight(inv)
    _edge(env, "e-read", chunk_id="c-pd")
    _endpoint_support(env, "e-cycle-1", "e-read-b", chunk_id="c-pd", target="e-read-a")
    _endpoint_support(env, "e-cycle-2", "e-read-a", chunk_id="c-pd", target="e-read-b")
    _archive(env, inv, "syn-e5", [("edge", "e-read")])
    _retrieval(inv, env["events"], edge_ids=["e-read"])
    summary = "A thesis standing only on the public pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


def test_a_claim_endpoint_grounded_only_by_the_followed_edge_is_not_unsupported(env):
    # Positive control: the retrieved edge IS the claim's supported_by edge.
    # Reaching the claim through that edge must not read the claim as having
    # no source just because its only edge is already being followed.
    inv = "inv-e6"
    _public_insight(inv)
    _node(env, "n-claim-e6", "claim")
    _node(env, "n-evidence-e6", "entity", '{"source_document_id": "doc-pd"}')
    _endpoint_support(env, "e-claim-e6", "n-claim-e6", chunk_id="c-pd",
                      target="n-evidence-e6")
    _retrieval(inv, env["events"], edge_ids=["e-claim-e6"])
    summary = "A thesis over the supported claim."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary


# ── round 4: a visited pointer is not a grounded one ──
#
# The walk's seen-set stops cycles, but a row already on the walk is not a
# source. Round 3 read an unsupported claim reached through its own
# supported_by edge as grounded "where the walk reaches it", and nothing did:
# the edge reported no source and the public insight cleared the excerpt.


def _unsupported_claim_edge(env: dict, prefix: str) -> str:
    """Claim ``{prefix}-claim`` (no pointer) supported_by an entity over an
    edge that names no chunk, document or pointer. Returns the edge id."""
    _node(env, f"{prefix}-claim", "claim")
    _node(env, f"{prefix}-entity")
    _endpoint_support(env, f"{prefix}-edge", f"{prefix}-claim",
                      target=f"{prefix}-entity")
    return f"{prefix}-edge"


def test_excerpt_withheld_when_a_retrieved_edge_is_an_unsupported_claims_own_edge(env):
    # codex's retrieval-event reproduction.
    inv = "inv-v1"
    _public_insight(inv)
    edge_id = _unsupported_claim_edge(env, "v1")
    _retrieval(inv, env["events"], edge_ids=[edge_id])
    _complete(inv, env["events"], f"Thesis. {PASSAGE}")
    _assert_withheld(env, inv)


def test_excerpt_withheld_when_a_pinned_edge_is_an_unsupported_claims_own_edge(env):
    # The manifest-edge entrypoint, with a public document pin beside the edge.
    inv = "inv-v2"
    _public_insight(inv)
    edge_id = _unsupported_claim_edge(env, "v2")
    _archive(env, inv, "syn-v2", [("document", "doc-pd"), ("edge", edge_id)])
    log_event(
        inv, ActionType.SYNTHESIS_ARCHIVED, synthesis_id="syn-v2",
        payload={"thesis_summary": f"Archived. {PASSAGE}"}, events_dir=env["events"],
    )
    _assert_withheld(env, inv)


def test_excerpt_cleared_through_a_public_grounded_claim_cycle(env):
    # Positive control: two claims supported only by each other, one of the
    # two edges over the public chunk. Both entrypoints name the edge that
    # carries no chunk itself; the cycle is grounded and the excerpt exports.
    inv = "inv-v3"
    _public_insight(inv)
    _node(env, "v3-a", "claim")
    _node(env, "v3-b", "claim")
    _endpoint_support(env, "v3-ab", "v3-a", target="v3-b")
    _endpoint_support(env, "v3-ba", "v3-b", chunk_id="c-pd", target="v3-a")
    _archive(env, inv, "syn-v3", [("edge", "v3-ab")])
    _retrieval(inv, env["events"], edge_ids=["v3-ab"])
    summary = "A thesis over a cycle that rests on the public pamphlet."
    _complete(inv, env["events"], summary)
    body = _body(env, inv)
    assert body.synthesis_withheld is False
    assert body.synthesis_excerpt == summary
