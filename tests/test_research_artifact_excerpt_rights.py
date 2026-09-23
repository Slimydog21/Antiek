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
