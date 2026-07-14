"""Tests for the Write REST surface (specs/write/, interfaces/research/api/write_routes.py).

Exercises the router end-to-end via TestClient against a temp DB:
  • outline composition (place / move / remove / outline tree) — SPR-01
  • provenance + trace target, incl. the gated-source-no-leak gate — SPR-01/07
  • folders (views over nodes) + search — SPR-03
  • brainstorm → user-originated blocks — SPR-05
  • context promote — SPR-08
  • generation: the no-blocks→gap path (no model needed) — SPR-06

The live generation path (a real model call) needs creative_writer wired
into the dispatch config + credentials; that path returns 503 here rather
than fabricating prose, and is not asserted.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import interfaces.research.api.write_routes as write_routes
from interfaces.research.api import create_app
from runtime.db_lock import connect_write
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.ops import (
    insert_chunk,
    insert_deliverable,
    insert_document,
    insert_node,
    insert_section,
)
from substrate.speak.interviewer_context import SpeakGraphGapSource


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point the app + substrate at a temp DB + events dir."""
    db = str(tmp_path / "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(default_db_path())
    return db


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


@pytest.fixture
def seed():
    """A deliverable + section + a document→chunk→node provenance chain."""
    with connect_write(default_db_path(), purpose="test/seed") as con:
        did = insert_deliverable(con, title="Memo", deliverable_kind="research_memo")
        sec = insert_section(con, deliverable_id=did, section_index=0, title="S1")
        doc = insert_document(con, document_id="doc-1", source_tier=2,
                              document_type="book", title="Source Book")
        con.execute("UPDATE documents SET content_class='public_domain' WHERE document_id=?", [doc])
        ch = insert_chunk(con, document_id=doc, chunk_index=0, text="evidence")
        node = insert_node(con, canonical_label="a sourced insight", node_type="claim",
                           graph_scope="cross_domain", investigation_id="__operator__",
                           metadata={"chunk_id": ch})
        question = insert_node(
            con,
            canonical_label="What changed after the first prototype?",
            node_type="question",
            graph_scope="cross_domain",
            investigation_id="__operator__",
            metadata={"chunk_id": ch},
        )
        gated_doc = insert_document(con, document_id="doc-gated", source_tier=2,
                                    document_type="book", title="Gated Book")
        con.execute("UPDATE documents SET content_class='restricted_pending_opt_in' "
                    "WHERE document_id=?", [gated_doc])
        gch = insert_chunk(con, document_id=gated_doc, chunk_index=0, text="gated passage")
        gnode = insert_node(con, canonical_label="a gated insight", node_type="claim",
                            graph_scope="cross_domain", investigation_id="__operator__",
                            metadata={"chunk_id": gch})
    return {"deliverable_id": did, "section_id": sec, "node": node,
            "question": question,
            "document": doc, "gated_node": gnode}


def _place_question(client: TestClient, seed: dict) -> str:
    response = client.post("/write/blocks", json={
        "section_id": seed["section_id"],
        "block_kind": "open_question",
        "provenance_kind": "graph_node",
        "node_id": seed["question"],
        "block_index": 0,
    })
    assert response.status_code == 201, response.text
    return response.json()["outline_block_id"]


def _all_events() -> list[dict]:
    rows: list[dict] = []
    for path in Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]).rglob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return rows


# ── Write → Speak committed seam ──


def test_question_commission_is_reference_only_and_hydrates_at_read_time(client, seed):
    block_id = _place_question(client, seed)
    response = client.post(
        f"/write/blocks/{block_id}/speak-handoffs",
        headers={"Idempotency-Key": "commission-1"},
        json={"deliverable_id": seed["deliverable_id"]},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["question_node_id"] == seed["question"]
    assert body["speak_path"] == f"/speak/{body['speak_project_id']}"

    with connect_write(default_db_path(), purpose="test/commission") as con:
        row = con.execute(
            "SELECT ip.interview_guide, sp.publish_intent, sp.invitation_mode "
            "FROM interview_projects ip JOIN speak_projects sp USING (project_id) "
            "WHERE ip.project_id = ?",
            [body["speak_project_id"]],
        ).fetchone()
        stored = json.loads(row[0])
        assert stored == {"must_cover": [{
            "id": seed["question"], "question_node_id": seed["question"],
        }]}
        assert "first prototype" not in row[0]
        assert row[1:] == ("private_never_published", "private")

        gaps = SpeakGraphGapSource(con).open_questions(body["speak_project_id"])
        assert any("first prototype" in gap.text for gap in gaps)

    seam_events = [e for e in _all_events() if e["action_type"] == "seam.write_to_speak"]
    assert len(seam_events) == 1
    assert seam_events[0]["payload"]["entity_id"] == seed["question"]
    assert "first prototype" not in json.dumps(seam_events[0])


def test_question_commission_replays_once_and_rejects_key_reuse(client, seed):
    block_id = _place_question(client, seed)
    path = f"/write/blocks/{block_id}/speak-handoffs"
    headers = {"Idempotency-Key": "commission-replay"}
    payload = {"deliverable_id": seed["deliverable_id"]}
    first = client.post(path, headers=headers, json=payload)
    replay = client.post(path, headers=headers, json=payload)
    assert replay.status_code == 201
    assert replay.json() == first.json()
    assert len([e for e in _all_events() if e["action_type"] == "seam.write_to_speak"]) == 1

    new_command = client.post(
        path,
        headers={"Idempotency-Key": "commission-replay-after-reload"},
        json=payload,
    )
    assert new_command.status_code == 201
    assert new_command.json() == first.json()
    assert len([e for e in _all_events() if e["action_type"] == "seam.write_to_speak"]) == 1

    other = client.post("/deliverables", json={
        "title": "Other", "deliverable_kind": "research_memo",
    }).json()["deliverable_id"]
    conflict = client.post(path, headers=headers, json={"deliverable_id": other})
    assert conflict.status_code == 409
    with connect_write(default_db_path(), purpose="test/commission-count") as con:
        assert con.execute("SELECT count(*) FROM speak_projects").fetchone()[0] == 1


def test_question_commission_repairs_event_after_append_failure(client, seed, monkeypatch):
    block_id = _place_question(client, seed)
    path = f"/write/blocks/{block_id}/speak-handoffs"
    headers = {"Idempotency-Key": "commission-repair"}
    real_append = write_routes.append_event_once
    monkeypatch.setattr(
        write_routes,
        "append_event_once",
        lambda _event: (_ for _ in ()).throw(RuntimeError("event store unavailable")),
    )
    with pytest.raises(RuntimeError, match="event store unavailable"):
        client.post(path, headers=headers, json={"deliverable_id": seed["deliverable_id"]})
    monkeypatch.setattr(write_routes, "append_event_once", real_append)
    repaired = client.post(
        path, headers=headers, json={"deliverable_id": seed["deliverable_id"]}
    )
    assert repaired.status_code == 201
    with connect_write(default_db_path(), purpose="test/commission-repair") as con:
        assert con.execute("SELECT count(*) FROM speak_projects").fetchone()[0] == 1
    assert len([e for e in _all_events() if e["action_type"] == "seam.write_to_speak"]) == 1


def test_question_commission_rejects_non_question_before_mutation(client, seed):
    block = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    response = client.post(
        f"/write/blocks/{block}/speak-handoffs",
        headers={"Idempotency-Key": "not-a-question"},
        json={"deliverable_id": seed["deliverable_id"]},
    )
    assert response.status_code == 409
    with connect_write(default_db_path(), purpose="test/no-commission") as con:
        assert con.execute("SELECT count(*) FROM interview_projects").fetchone()[0] == 0


# ── SPR-09 M1 — the piece↔research link, verified by reading it back ──


def test_create_deliverable_persists_investigation_root_link(client):
    """M1 (decision D-1): the piece↔research link is the pre-shipped
    `deliverables.investigation_root_id`. The acceptance bar is "verified by the
    link EXISTING, not just the UI claiming it" — so assert the round trip: the
    link given on create comes back on BOTH the create response and the detail
    read from the substrate (not a UI mock)."""
    created = client.post("/deliverables", json={
        "title": "A connected piece", "deliverable_kind": "research_memo",
        "investigation_root_id": "inv-root-xyz",
    })
    assert created.status_code == 201, created.text
    body = created.json()
    did = body["deliverable_id"]
    assert body["investigation_root_id"] == "inv-root-xyz"
    # Read it back from the substrate via the detail endpoint — the link exists.
    detail = client.get(f"/deliverables/{did}").json()
    assert detail["investigation_root_id"] == "inv-root-xyz"


# ── SPR-01 — outline composition ───────────────────────────────────


def test_place_and_list_blocks(client, seed):
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    assert r.status_code == 201
    obid = r.json()["outline_block_id"]

    blocks = client.get(f"/write/sections/{seed['section_id']}/blocks").json()
    assert blocks["count"] == 1
    assert blocks["blocks"][0]["outline_block_id"] == obid
    assert blocks["blocks"][0]["node_id"] == seed["node"]


def test_move_requires_command_identity_and_replays_without_mutation(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    path = f"/write/blocks/{obid}/move"
    assert client.post(path, json={
        "to_section_id": seed["section_id"], "to_index": 2,
    }).status_code == 422
    assert client.post(path, headers={"Idempotency-Key": "   "}, json={
        "to_section_id": seed["section_id"], "to_index": 2,
    }).status_code == 422

    headers = {"Idempotency-Key": "route-move-1"}
    first = client.post(path, headers=headers, json={
        "to_section_id": seed["section_id"], "to_index": 2,
    })
    assert first.status_code == 202
    replay = client.post(path, headers=headers, json={
        "to_section_id": seed["section_id"], "to_index": 2,
    })
    assert replay.status_code == 202
    conflict = client.post(path, headers=headers, json={
        "to_section_id": seed["section_id"], "to_index": 3,
    })
    assert conflict.status_code == 409

    block = client.get(
        f"/write/sections/{seed['section_id']}/blocks"
    ).json()["blocks"][0]
    assert block["block_index"] == 2


def test_remove_command_retry_stays_successful_but_new_command_is_404(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    path = f"/write/blocks/{obid}"
    assert client.delete(path).status_code == 422

    headers = {"Idempotency-Key": "route-remove-1"}
    assert client.delete(path, headers=headers).status_code == 200
    assert client.delete(path, headers=headers).status_code == 200
    assert client.delete(
        path, headers={"Idempotency-Key": "route-remove-2"},
    ).status_code == 404


def test_list_blocks_carries_node_label_for_id_free_render(client, seed):
    """The routed outline (Product Depth SPR-07) renders block TEXT, never an
    id. A graph-node block carries no `content` (its text is on the node), so
    the list endpoint resolves the node's canonical label as `node_label` so
    the UI has text to show without ever surfacing the node_id."""
    client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    b = client.get(f"/write/sections/{seed['section_id']}/blocks").json()["blocks"][0]
    # content is null for a graph-node block; node_label carries the text.
    assert b["content"] is None
    assert b["node_label"] == "a sourced insight"


def test_place_block_rejects_orphan_prose(client, seed):
    """The no-orphan-prose invariant surfaces as a 400 over HTTP."""
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": None, "block_index": 0,
    })
    assert r.status_code == 400
    assert "no-orphan-prose" in r.json()["detail"]


def test_user_authored_block_rejects_fabricated_citation(client, seed):
    r = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "user_authored",
        "provenance_kind": "user_authored", "node_id": seed["node"],
        "content": "x", "block_index": 0,
    })
    assert r.status_code == 400
    assert "fabricates a citation" in r.json()["detail"]


def test_outline_tree(client, seed):
    client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    })
    tree = client.get(f"/write/deliverables/{seed['deliverable_id']}/outline").json()
    assert len(tree["roots"]) == 1
    assert tree["roots"][0]["section_id"] == seed["section_id"]
    assert len(tree["roots"][0]["blocks"]) == 1


def test_provenance_endpoint(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    prov = client.get(f"/write/blocks/{obid}/provenance").json()
    assert prov["status"] == "resolved"
    assert prov["document_id"] == seed["document"]


# ── SPR-07 — trace target (gated-source-no-leak over HTTP) ──────────


def test_trace_public_domain_opens_at_span(client, seed):
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0,
    }).json()["outline_block_id"]
    trace = client.get(f"/write/blocks/{obid}/trace").json()
    assert trace["kind"] == "source_span"
    assert trace["full_text_allowed"] is True


def test_trace_gated_book_no_leak(client, seed):
    """A gated-license source must return servable-snippet, never full text."""
    obid = client.post("/write/blocks", json={
        "section_id": seed["section_id"], "block_kind": "claim",
        "provenance_kind": "graph_node", "node_id": seed["gated_node"], "block_index": 1,
    }).json()["outline_block_id"]
    trace = client.get(f"/write/blocks/{obid}/trace").json()
    assert trace["kind"] == "servable_snippet"
    assert trace["full_text_allowed"] is False  # the gate, over HTTP


# ── SPR-03 — folders + search ──────────────────────────────────────


def test_folders_and_multi_membership(client, seed):
    f1 = client.post("/write/folders", json={"name": "one"}).json()["folder_id"]
    f2 = client.post("/write/folders", json={"name": "two"}).json()["folder_id"]
    assert client.post(f"/write/folders/{f1}/blocks", json={"node_id": seed["node"]}).json()["status"] == "added"
    assert client.post(f"/write/folders/{f1}/blocks", json={"node_id": seed["node"]}).json()["status"] == "already_member"
    client.post(f"/write/folders/{f2}/blocks", json={"node_id": seed["node"]})
    folders = {f["folder_id"]: f for f in client.get("/write/folders").json()["folders"]}
    assert folders[f1]["member_count"] == 1
    assert folders[f2]["member_count"] == 1  # same node, two folders, no copy


def test_search_endpoint(client, seed):
    hits = client.get("/write/blocks/search", params={"q": "sourced insight"}).json()
    assert hits["count"] >= 1
    assert hits["hits"][0]["node_id"] == seed["node"]


# ── SPR-05 — brainstorm → user-originated blocks ───────────────────


def test_brainstorm_emit_blocks(client, seed):
    r = client.post("/write/brainstorm/emit-blocks", json={
        "section_id": seed["section_id"], "deliverable_id": seed["deliverable_id"],
        "insights": ["the moat is data"], "questions": ["does it scale?"],
        "data_points": ["80% margin"],
    })
    assert r.status_code == 201
    body = r.json()
    assert body["insight_count"] == 1 and body["question_count"] == 1 and body["data_count"] == 1
    assert len(body["flagged_unverified"]) == 1  # asserted data flagged
    # All brainstorm blocks are user-originated (no node_id / fabricated source).
    blocks = client.get(f"/write/sections/{seed['section_id']}/blocks").json()["blocks"]
    assert all(b["provenance_kind"] == "brainstorm" and b["node_id"] is None for b in blocks)


# ── SPR-08 — context promote ───────────────────────────────────────


def test_context_promote(client, seed):
    r = client.post("/write/context/promote", json={
        "title": "From context", "deliverable_kind": "general_essay",
        "objective": "argue the thesis",
        "blocks": [
            {"section_id": "ignored", "block_kind": "insight",
             "provenance_kind": "graph_node", "node_id": seed["node"], "block_index": 0},
            {"section_id": "ignored", "block_kind": "user_authored",
             "provenance_kind": "brainstorm", "content": "a thought", "block_index": 1},
        ],
    })
    assert r.status_code == 201
    body = r.json()
    assert len(body["block_ids"]) == 2
    blocks = client.get(f"/write/sections/{body['section_id']}/blocks").json()
    assert blocks["count"] == 2


# ── SPR-06 — generation no-blocks → gap (no model) ─────────────────


def test_generate_empty_section_returns_gap(client, seed):
    r = client.post(f"/write/sections/{seed['section_id']}/generate")
    assert r.status_code == 200
    assert r.json()["status"] == "gap"  # never fabricated prose


def test_citation_failure_preserves_existing_draft_and_emits_no_event(
    client, seed, monkeypatch,
):
    from substrate.event_log import trajectory
    from substrate.write import draft_generation

    sec = seed["section_id"]
    node = seed["node"]
    client.post("/write/blocks", json={
        "section_id": sec, "block_kind": "insight",
        "provenance_kind": "graph_node", "node_id": node, "block_index": 0,
    })
    with connect_write(default_db_path(), purpose="test/existing_draft") as con:
        con.execute(
            "UPDATE deliverable_sections SET prose_text = ?, prose_provenance = ? "
            "WHERE section_id = ?",
            ["Previously accepted prose.", '{"0":["existing-node"]}', sec],
        )

    raw = (
        '{"prose_text": "This substantive replacement makes a material claim without '
        'any inline citation to the attached evidence.", '
        f'"prose_provenance": {{}}, "uncited_blocks": ["{node}"]}}'
    )
    monkeypatch.setattr(
        draft_generation,
        "default_dispatch_fn",
        lambda **_kwargs: lambda _system, _user: raw,
    )

    response = client.post(f"/write/sections/{sec}/generate")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "citation_failed"
    assert body["unsupported_paragraphs"] == [0]
    assert body["prose_provenance"] == {}
    assert _section_prose_row(seed["deliverable_id"]) == (
        "Previously accepted prose.", '{"0":["existing-node"]}',
    )
    assert not any(
        event.get("action_type") == "section.draft_generated"
        for event in trajectory(seed["deliverable_id"])
    )


# ── SPR-09 M3 — persist prose_provenance through the funnel + X-ray read-back ──


def _section_prose_row(deliverable_id: str):
    import duckdb
    con = duckdb.connect(default_db_path(), read_only=True)
    try:
        return con.execute(
            "SELECT prose_text, prose_provenance FROM deliverable_sections "
            "WHERE deliverable_id = ?", [deliverable_id],
        ).fetchone()
    finally:
        con.close()


def _place_seed_block(con, seed):
    from substrate.write.outline_block import place_block

    return place_block(
        con,
        section_id=seed["section_id"],
        block_kind="insight",
        provenance_kind="graph_node",
        node_id=seed["node"],
        block_index=0,
        emit_event=False,
    )


def test_persist_section_draft_round_trips_provenance_and_emits_event(seed, tmp_path):
    """A generated draft's paragraph→blocks map must SURVIVE the request:
    persisted to the section row AND emitted as a SECTION_DRAFT_GENERATED
    event, both through the single-writer funnel. The X-ray reads it back."""
    import json

    from substrate.event_log import trajectory as read_trajectory
    from substrate.write.draft_generation import (
        CitationReport,
        GateResult,
        GenerationResult,
        persist_section_draft,
    )

    sec, node = seed["section_id"], seed["node"]
    result = GenerationResult(
        status="generated", section_id=sec,
        prose_text=f"The thesis holds [b: {node}].\n\nA second paragraph [b: {node}].",
        citation_report=None, gate=GateResult(score=0.92, passed=True, violations=[]),
        prose_provenance={0: [node], 1: [node]},
    )
    report = CitationReport(
        supported_paragraphs=[0, 1], unsupported_paragraphs=[],
        fabricated_citations=[], uncited_blocks=[], cited_block_ids=[node],
    )
    with connect_write(default_db_path(), purpose="test/persist_draft") as con:
        _place_seed_block(con, seed)
        event_id = persist_section_draft(
            con, section_id=sec, deliverable_id=seed["deliverable_id"],
            result=result, report=report, investigation_id=seed["deliverable_id"],
        )
    assert event_id is not None

    # (1) The section row carries the persisted prose + provenance (the X-ray
    #     reads THIS back — not an on-screen claim).
    row = _section_prose_row(seed["deliverable_id"])
    assert row[0].startswith("The thesis holds")
    persisted = json.loads(row[1])
    assert persisted == {"0": [node], "1": [node]}  # string keys, round-tripped

    # (2) The audit event EXISTS in the graph (the §9 link is a persisted
    #     event, not just a UI render).
    events = read_trajectory(seed["deliverable_id"])
    drafted = [e for e in events if e.get("action_type") == "section.draft_generated"]
    assert len(drafted) == 1
    payload = drafted[0]["payload"]
    assert payload["section_id"] == sec
    assert payload["prose_provenance"] == {"0": [node], "1": [node]}
    assert payload["all_claims_cited"] is True
    assert node in payload["cited_block_ids"]


def test_persist_refuses_gate_failed_draft(seed):
    """A gate_failed/invalid draft never ships, so it must never persist
    provenance (no half-written draft in the graph)."""
    from substrate.write.draft_generation import GenerationResult, persist_section_draft
    bad = GenerationResult(
        status="gate_failed", section_id=seed["section_id"],
        prose_text="slop", citation_report=None, gate=None,
    )
    with connect_write(default_db_path(), purpose="test/persist_bad") as con:
        with pytest.raises(ValueError, match="only persists a citation-clean 'generated'"):
            persist_section_draft(
                con, section_id=seed["section_id"],
                deliverable_id=seed["deliverable_id"], result=bad,
                report=None,  # type: ignore[arg-type]
            )
    # Nothing was written.
    row = _section_prose_row(seed["deliverable_id"])
    assert row[0] is None


def test_persist_refuses_generated_result_with_failed_citation_report(seed):
    from substrate.write.draft_generation import (
        CitationReport,
        GenerationResult,
        persist_section_draft,
    )

    result = GenerationResult(
        status="generated", section_id=seed["section_id"], prose_text="unsupported",
        citation_report=None, gate=None,
    )
    report = CitationReport(
        supported_paragraphs=[], unsupported_paragraphs=[0],
        fabricated_citations=[], uncited_blocks=[seed["node"]], cited_block_ids=[],
    )
    with connect_write(default_db_path(), purpose="test/persist_uncited") as con:
        with pytest.raises(ValueError, match="all_claims_cited=False"):
            persist_section_draft(
                con, section_id=seed["section_id"],
                deliverable_id=seed["deliverable_id"], result=result, report=report,
            )
    assert _section_prose_row(seed["deliverable_id"])[0] is None


def test_persist_revalidates_result_instead_of_trusting_unrelated_clean_report(seed):
    from substrate.write.draft_generation import (
        CitationReport,
        GateResult,
        GenerationResult,
        persist_section_draft,
    )

    result = GenerationResult(
        status="generated", section_id=seed["section_id"],
        prose_text="This material claim cites an unattached block [b: node-ghost].",
        citation_report=None, gate=GateResult(score=0.9, passed=True, violations=[]),
        prose_provenance={0: ["node-ghost"]},
    )
    unrelated_clean_report = CitationReport(
        supported_paragraphs=[0], unsupported_paragraphs=[], fabricated_citations=[],
        uncited_blocks=[], cited_block_ids=["node-ghost"],
    )
    with connect_write(default_db_path(), purpose="test/persist_unrelated_report") as con:
        _place_seed_block(con, seed)
        with pytest.raises(ValueError, match="all_claims_cited=False"):
            persist_section_draft(
                con, section_id=seed["section_id"],
                deliverable_id=seed["deliverable_id"], result=result,
                report=unrelated_clean_report,
            )
    assert _section_prose_row(seed["deliverable_id"])[0] is None


def test_persist_refuses_voice_failed_generated_result(seed):
    from substrate.write.draft_generation import (
        CitationReport,
        GateResult,
        GenerationResult,
        persist_section_draft,
    )

    node = seed["node"]
    result = GenerationResult(
        status="generated", section_id=seed["section_id"],
        prose_text=f"The mechanism is grounded in attached evidence [b: {node}].",
        citation_report=None, gate=GateResult(score=0.2, passed=False, violations=["slop"]),
        prose_provenance={0: [node]},
    )
    report = CitationReport(
        supported_paragraphs=[0], unsupported_paragraphs=[], fabricated_citations=[],
        uncited_blocks=[], cited_block_ids=[node],
    )
    with connect_write(default_db_path(), purpose="test/persist_voice_failed") as con:
        with pytest.raises(ValueError, match="gate_passed=False"):
            persist_section_draft(
                con, section_id=seed["section_id"],
                deliverable_id=seed["deliverable_id"], result=result, report=report,
            )
    assert _section_prose_row(seed["deliverable_id"])[0] is None


def test_xray_reads_persisted_provenance_via_get_deliverable(client, seed):
    """After persistence, GET /deliverables/{id} surfaces prose_provenance on
    the section — the contract the X-ray view consumes."""
    from substrate.write.draft_generation import (
        CitationReport,
        GateResult,
        GenerationResult,
        persist_section_draft,
    )
    sec, node = seed["section_id"], seed["node"]
    result = GenerationResult(
        status="generated", section_id=sec,
        prose_text=f"Grounded prose [b: {node}].",
        citation_report=None, gate=GateResult(score=0.9, passed=True, violations=[]),
        prose_provenance={0: [node]},
    )
    report = CitationReport(
        supported_paragraphs=[0], unsupported_paragraphs=[], fabricated_citations=[],
        uncited_blocks=[], cited_block_ids=[node],
    )
    with connect_write(default_db_path(), purpose="test/persist_xray") as con:
        _place_seed_block(con, seed)
        persist_section_draft(
            con, section_id=sec, deliverable_id=seed["deliverable_id"],
            result=result, report=report, investigation_id=seed["deliverable_id"],
        )
    detail = client.get(f"/deliverables/{seed['deliverable_id']}").json()
    section = next(s for s in detail["sections"] if s["section_id"] == sec)
    assert section["prose_provenance"] == {"0": [node]}
    # And the block resolves through to its chunk → document (resolve_provenance
    # chains the X-ray to source — not just block ids).
    blk = client.post("/write/blocks", json={
        "section_id": sec, "block_kind": "claim", "provenance_kind": "graph_node",
        "node_id": node, "block_index": 0,
    }).json()["outline_block_id"]
    prov = client.get(f"/write/blocks/{blk}/provenance").json()
    assert prov["status"] == "resolved"
    assert prov["document_id"] == seed["document"]


# ── GPW SPR-04 — the deliverable export carries its provenance (JSON floor) ──


def test_export_json_carries_prose_provenance(client, seed):
    """The /deliverables/{id}/export?format=json bundle must include each
    section's prose_provenance (the paragraph→blocks map the substrate stores),
    instead of stripping all attribution from the sellable artifact. NULL
    provenance surfaces as None, never fabricated."""
    import json

    from substrate.graph.ops import update_section_prose

    sec, node, did = seed["section_id"], seed["node"], seed["deliverable_id"]
    with connect_write(default_db_path(), purpose="test/seed-prov") as con:
        update_section_prose(
            con, section_id=sec, prose_text="the finding",
            prose_provenance={0: [node]},
        )

    r = client.get(f"/deliverables/{did}/export", params={"format": "json"})
    assert r.status_code == 200, r.text
    bundle = json.loads(r.json()["content"])
    section = next(s for s in bundle["sections"] if s["title"] == "S1")
    assert section["prose_provenance"] == {"0": [node]}  # carried, not stripped


def test_export_json_null_provenance_is_none_not_fabricated(client, seed):
    """A section with no stored provenance exports prose_provenance: null —
    honest absence, never an invented source."""
    import json

    did = seed["deliverable_id"]
    r = client.get(f"/deliverables/{did}/export", params={"format": "json"})
    assert r.status_code == 200, r.text
    bundle = json.loads(r.json()["content"])
    section = next(s for s in bundle["sections"] if s["title"] == "S1")
    assert section["prose_provenance"] is None


def test_export_json_no_misattribution_across_colliding_section_index(client, seed):
    """section_index is NOT unique per deliverable (only section_id is; several
    callers hardcode index 0). Two sections sharing an index must each carry
    THEIR OWN provenance in the JSON export — the provenanced one keeps its map,
    the NULL one stays None (no fabrication, no cross-section bleed)."""
    import json

    from substrate.graph.ops import insert_section, update_section_prose

    node, did = seed["node"], seed["deliverable_id"]
    with connect_write(default_db_path(), purpose="test/collide") as con:
        # A SECOND section at the SAME section_index (0) as the seed's "S1".
        sec2 = insert_section(con, deliverable_id=did, section_index=0, title="S2")
        update_section_prose(con, section_id=sec2, prose_text="p2", prose_provenance={0: [node]})
        # seed's "S1" section keeps NULL provenance.

    r = client.get(f"/deliverables/{did}/export", params={"format": "json"})
    assert r.status_code == 200, r.text
    bundle = json.loads(r.json()["content"])
    by_title = {s["title"]: s for s in bundle["sections"]}
    assert by_title["S2"]["prose_provenance"] == {"0": [node]}  # keeps its own
    assert by_title["S1"]["prose_provenance"] is None            # NOT fabricated from S2

# ── GPW SPR-05 — a prose EDIT preserves provenance instead of NULLing it ──


def test_prose_edit_preserves_provenance(seed):
    """update_section_prose is preserve-unless-supplied: an edit that passes
    ONLY prose_text (as patch_section_prose does) must leave the section's
    prose_provenance intact — a one-paragraph typo fix no longer wipes the
    whole section's X-ray/citation map. Passing provenance explicitly still
    replaces it (the generation/regeneration path)."""
    import json

    from substrate.graph.ops import update_section_prose

    sec, node = seed["section_id"], seed["node"]

    # 1) Generation sets provenance.
    with connect_write(default_db_path(), purpose="test/seed-prov") as con:
        update_section_prose(
            con, section_id=sec, prose_text="original prose",
            prose_provenance={0: [node], 1: [node]},
        )
    row = _section_prose_row(seed["deliverable_id"])
    assert json.loads(row[1]) == {"0": [node], "1": [node]}

    # 2) EDIT path — prose_text only, NO prose_provenance. Provenance PRESERVED.
    with connect_write(default_db_path(), purpose="test/edit") as con:
        update_section_prose(con, section_id=sec, prose_text="fixed a typo in the prose")
    row = _section_prose_row(seed["deliverable_id"])
    assert row[0] == "fixed a typo in the prose"           # text updated
    assert json.loads(row[1]) == {"0": [node], "1": [node]}  # provenance INTACT (was NULLed before)

    # 3) Explicit provenance still REPLACES (regeneration path).
    with connect_write(default_db_path(), purpose="test/regen") as con:
        update_section_prose(
            con, section_id=sec, prose_text="regenerated", prose_provenance={0: [node]},
        )
    row = _section_prose_row(seed["deliverable_id"])
    assert json.loads(row[1]) == {"0": [node]}             # replaced


def test_patch_section_prose_endpoint_preserves_provenance(client, seed):
    """End-to-end through the real PATCH endpoint: editing a section's prose
    via the API must not wipe its provenance (the bug this sprint closes)."""
    import json

    from substrate.graph.ops import update_section_prose

    sec, node = seed["section_id"], seed["node"]
    with connect_write(default_db_path(), purpose="test/seed-prov") as con:
        update_section_prose(
            con, section_id=sec, prose_text="original", prose_provenance={0: [node]},
        )

    r = client.patch(f"/sections/{sec}/prose",
                     json={"prose_text": "operator fixed a typo"})
    assert r.status_code == 202, r.text

    row = _section_prose_row(seed["deliverable_id"])
    assert row[0] == "operator fixed a typo"
    assert json.loads(row[1]) == {"0": [node]}  # provenance survived the edit
