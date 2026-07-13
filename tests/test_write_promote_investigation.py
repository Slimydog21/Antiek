"""Red-proven test for the research→writing flywheel arm
(specs/write WV-SPR-01 M4).

A completed investigation's synthesis promotes into a seed deliverable: one
graph-node block per synthesis-pinned source node, each carrying provenance
back to its graph node (resolve_provenance resolves node → document → chunks).
Both the substrate core AND the REST route are exercised against a hermetic
temp DB (never the real graph).

RED-PROOF: on pre-change main this module fails at collection —
``promote_investigation_to_deliverable`` does not exist on ``origin/main``
(verified 2026-07-02: grep returned no definition, no route) — so the suite is
red until the WV-SPR-01 build lands. The behavioral assertions then guard the
three honest ordering states a synthesis can be in:

  1. live      — pinned nodes still in the graph → blocks resolve;
  2. dangling  — a pinned node was since deleted  → block placed, provenance
                 status ``dangling`` (seeded, never dropped);
  3. none      — the investigation has no synthesis → ``None`` (route 404);

plus the dominant real case the dogfood finding named: a synthesis that pinned
zero nodes is refused before it can create an empty deliverable.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import duckdb
import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import create_app  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_chunk, insert_document, insert_node  # noqa: E402
from substrate.write import promote_context as promote_context_mod  # noqa: E402
from substrate.write.outline_block import list_section_blocks  # noqa: E402
from substrate.write.promote_context import (  # noqa: E402
    InvestigationPromotionRefusal,
    promote_investigation_to_deliverable,
)
from substrate.write.provenance import resolve_provenance  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point the app + substrate at a temp DB + events dir (hermetic)."""
    db = str(tmp_path / "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(default_db_path())
    return db


@pytest.fixture
def client() -> TestClient:
    return TestClient(create_app())


def _read():
    return duckdb.connect(default_db_path(), read_only=True)


def _events_with_action(action_type: str) -> list[dict]:
    events_dir = Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    rows = [
        json.loads(line)
        for path in events_dir.rglob("*.jsonl")
        for line in path.read_text().splitlines()
    ]
    return [row for row in rows if row["action_type"] == action_type]


def _seed_synthesis(
    *,
    investigation_id: str = "inv-1",
    synthesis_id: str = "syn-1",
    nodes: tuple[tuple[str, str], ...] = (
        ("a sourced insight", "insight"),
        ("an open question", "question"),
        ("a sourced claim", "claim"),
    ),
    recommendation: str = "proceed",
    status: str = "passed",
) -> list[str]:
    """Create one investigation synthesis with pinned source nodes, each
    backed by a document→chunk so its provenance resolves. Returns the
    node_ids in insertion order. ``nodes=()`` yields a synthesis that pinned
    nothing (the evidence-refusal case)."""
    with connect_write(default_db_path(), purpose="test/seed-synthesis") as con:
        node_ids: list[str] = []
        for index, (label, ntype) in enumerate(nodes):
            doc = insert_document(
                con, document_id=f"doc-{index}", source_tier=2,
                document_type="paper", title=label,
            )
            ch = insert_chunk(
                con, document_id=doc, chunk_index=0, text=f"evidence for {label}",
            )
            nid = insert_node(
                con, canonical_label=label, node_type=ntype,
                graph_scope="cross_domain", investigation_id=investigation_id,
                metadata={"chunk_id": ch},
            )
            node_ids.append(nid)
        con.execute(
            "INSERT INTO syntheses "
            "(synthesis_id, investigation_id, target_question, "
            " synthesis_timestamp, status, implicit_recommendation) "
            "VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?)",
            [
                synthesis_id, investigation_id,
                "What does the evidence support?", status, recommendation,
            ],
        )
        for nid in node_ids:
            con.execute(
                "INSERT INTO synthesis_substrate_manifest "
                "(synthesis_id, entity_kind, entity_id) VALUES (?, 'node', ?)",
                [synthesis_id, nid],
            )
    return node_ids


# ---------------------------------------------------------------------------
# Substrate core
# ---------------------------------------------------------------------------


def test_promote_creates_deliverable_with_one_block_per_pinned_node():
    node_ids = _seed_synthesis()
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert result is not None
    assert result.block_count == 3
    assert result.dangling_count == 0
    assert result.source_node_count == 3
    assert result.synthesis_id == "syn-1"
    assert result.synthesis_recommendation == "proceed"

    con = _read()
    try:
        # The deliverable is linked back to its source investigation.
        drow = con.execute(
            "SELECT deliverable_kind, investigation_root_id, title "
            "FROM deliverables WHERE deliverable_id = ?",
            [result.deliverable_id],
        ).fetchone()
        assert drow[0] == "research_memo"
        assert drow[1] == "inv-1"

        blocks = list_section_blocks(con, result.section_id)
        assert len(blocks) == 3
        assert {b.node_id for b in blocks} == set(node_ids)
        # node_type → block_kind mapping (insight/question/claim direct).
        kind_by_node = {b.node_id: b.block_kind for b in blocks}
        # node_ids were inserted in the order: insight, question, claim.
        assert kind_by_node[node_ids[0]] == "insight"
        assert kind_by_node[node_ids[1]] == "open_question"
        assert kind_by_node[node_ids[2]] == "claim"
        # Every block resolves to a real source document (the provenance moat).
        for block in blocks:
            chain = resolve_provenance(con, block)
            assert chain.status == "resolved"
            assert chain.document_id is not None
    finally:
        con.close()
    assert len(_events_with_action("outline_block.placed")) == 3


def test_promote_rolls_back_all_rows_when_block_placement_fails(monkeypatch):
    _seed_synthesis()
    original = promote_context_mod.place_block
    calls = 0

    def fail_on_second_block(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise RuntimeError("injected placement failure")
        return original(*args, **kwargs)

    monkeypatch.setattr(promote_context_mod, "place_block", fail_on_second_block)
    with (
        pytest.raises(RuntimeError, match="injected placement failure"),
        connect_write(default_db_path(), purpose="test/promote") as con,
    ):
        promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )

    con = _read()
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM deliverable_sections").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM outline_blocks").fetchone()[0] == 0
    finally:
        con.close()
    assert _events_with_action("outline_block.placed") == []


def test_promote_retry_reuses_rows_and_repairs_missing_events(monkeypatch):
    node_ids = _seed_synthesis()
    original_emit = promote_context_mod.emit_block_placed
    monkeypatch.setattr(promote_context_mod, "emit_block_placed", lambda **_: None)
    with connect_write(default_db_path(), purpose="test/promote-first") as con:
        first = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert _events_with_action("outline_block.placed") == []

    with connect_write(default_db_path(), purpose="test/delete-after-promotion") as con:
        con.execute(
            f"DELETE FROM nodes WHERE node_id IN ({', '.join(['?'] * len(node_ids))})",
            node_ids,
        )
    monkeypatch.setattr(promote_context_mod, "emit_block_placed", original_emit)
    with connect_write(default_db_path(), purpose="test/promote-retry") as con:
        replay = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert replay.deliverable_id == first.deliverable_id
    assert replay.block_ids == first.block_ids
    assert replay.dangling_count == 3
    assert len(_events_with_action("outline_block.placed")) == 3
    con = _read()
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 1
        assert con.execute("SELECT COUNT(*) FROM outline_blocks").fetchone()[0] == 3
    finally:
        con.close()


def test_promotion_identity_preserves_distinct_request_shapes():
    _seed_synthesis()
    with connect_write(default_db_path(), purpose="test/promote-memo") as con:
        memo = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo", title="Memo",
        )
    with connect_write(default_db_path(), purpose="test/promote-kind") as con:
        different_kind = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="book_chapter", title="Memo",
        )
    with connect_write(default_db_path(), purpose="test/promote-title") as con:
        different_title = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo", title="Chapter",
        )
    assert memo.deliverable_id != different_kind.deliverable_id
    assert memo.deliverable_id != different_title.deliverable_id
    assert different_kind.deliverable_id != different_title.deliverable_id


def test_promote_flags_dangling_source_node_seeded_not_dropped():
    node_ids = _seed_synthesis()  # three nodes pinned by the synthesis
    # Delete one pinned node (FK-safe: it has no edges). The manifest row has
    # no FK to nodes, so it keeps referencing the now-gone node_id.
    with connect_write(default_db_path(), purpose="test/delete-node") as con:
        con.execute("DELETE FROM nodes WHERE node_id = ?", [node_ids[1]])

    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert result is not None
    assert result.block_count == 3            # all three still placed
    assert result.dangling_count == 1         # one points at the deleted node
    assert result.source_node_count == 3

    con = _read()
    try:
        blocks = {b.node_id: b for b in list_section_blocks(con, result.section_id)}
        chains = {nid: resolve_provenance(con, b) for nid, b in blocks.items()}
    finally:
        con.close()
    # The deleted node's block is dangling (surfaced, not dropped).
    assert chains[node_ids[1]].status == "dangling"
    # The two live nodes still resolve to their source documents.
    live = {nid: c for nid, c in chains.items() if nid != node_ids[1]}
    assert len(live) == 2
    assert all(c.status == "resolved" and c.document_id is not None for c in live.values())


def test_promote_returns_none_when_investigation_has_no_synthesis():
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "investigation-with-no-synthesis",
            deliverable_kind="research_memo",
        )
    assert result is None  # the route maps this to 404, never an empty 200


def test_promote_empty_synthesis_is_insufficient_evidence():
    # Zero pinned source nodes was the dominant dogfood case. Refuse it before
    # writing rather than returning a nominally successful empty deliverable.
    _seed_synthesis(nodes=())
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert isinstance(result, InvestigationPromotionRefusal)
    assert result.gate_failed == "no_source_nodes"
    assert result.source_node_count == 0
    assert result.dangling_count == 0

    con = _read()
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM deliverable_sections").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM outline_blocks").fetchone()[0] == 0
    finally:
        con.close()


@pytest.mark.parametrize("recommendation", ["undetermined", "insufficient_evidence"])
def test_promote_rejects_non_writable_recommendations_before_any_write(recommendation):
    _seed_synthesis(recommendation=recommendation)
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert isinstance(result, InvestigationPromotionRefusal)
    assert result.gate_failed == "recommendation"
    assert result.synthesis_recommendation == recommendation

    con = _read()
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM deliverable_sections").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM outline_blocks").fetchone()[0] == 0
    finally:
        con.close()


def test_promote_allows_evidence_backed_pass_recommendation():
    _seed_synthesis(recommendation="pass")
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert not isinstance(result, InvestigationPromotionRefusal)
    assert result is not None
    assert result.block_count == 3
    assert result.synthesis_recommendation == "pass"


@pytest.mark.parametrize("status", ["regressed", "max_iterations_reached", "escalated"])
def test_promote_rejects_non_converged_status_before_any_write(status):
    _seed_synthesis(status=status, recommendation="proceed")
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert isinstance(result, InvestigationPromotionRefusal)
    assert result.gate_failed == "status"
    assert result.synthesis_status == status

    con = _read()
    try:
        assert con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM deliverable_sections").fetchone()[0] == 0
        assert con.execute("SELECT COUNT(*) FROM outline_blocks").fetchone()[0] == 0
    finally:
        con.close()


def test_promote_rejects_when_every_pinned_source_node_is_dangling():
    node_ids = _seed_synthesis()
    with connect_write(default_db_path(), purpose="test/delete-nodes") as con:
        con.execute(
            f"DELETE FROM nodes WHERE node_id IN ({', '.join(['?'] * len(node_ids))})",
            node_ids,
        )
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert isinstance(result, InvestigationPromotionRefusal)
    assert result.gate_failed == "all_dangling"
    assert result.live_source_node_count == 0
    assert result.dangling_count == 3


def test_promote_skips_draft_synthesis_as_not_depositable():
    # A draft synthesis is in-flight / unevaluated — not a completed conclusion,
    # so it is not promoted as a deliverable (codex review: don't treat a draft
    # as "completed"). If a draft is all that exists → None (route 404).
    _seed_synthesis(status="draft")
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert result is None


def test_promote_picks_most_recent_by_synthesis_timestamp_not_archive_time():
    # Two syntheses for one investigation: an OLD one archived LATE (archived_at
    # would wrongly win) and a NEW one archived EARLIER. promote must pick by
    # synthesis_timestamp (when it was made), not archived_at (codex review:
    # a late backfill/retry must not shadow a newer synthesis).
    with connect_write(default_db_path(), purpose="test/seed-two") as con:
        for sid, syn_ts, arch_ts in [
            ("syn-old", "2026-07-01 00:00:00", "2026-07-03 11:00:00"),
            ("syn-new", "2026-07-03 00:00:00", "2026-07-03 10:00:00"),
        ]:
            doc = insert_document(
                con, document_id=f"doc-{sid}", source_tier=2,
                document_type="paper", title=sid,
            )
            ch = insert_chunk(con, document_id=doc, chunk_index=0, text=sid)
            nid = insert_node(
                con, canonical_label=sid, node_type="insight",
                graph_scope="cross_domain", investigation_id="inv-1",
                metadata={"chunk_id": ch},
            )
            con.execute(
                "INSERT INTO syntheses "
                "(synthesis_id, investigation_id, target_question, "
                " synthesis_timestamp, archived_at, status, "
                " implicit_recommendation) "
                "VALUES (?, ?, ?, ?, ?, 'passed', 'proceed')",
                [sid, "inv-1", sid + " question", syn_ts, arch_ts],
            )
            con.execute(
                "INSERT INTO synthesis_substrate_manifest "
                "(synthesis_id, entity_kind, entity_id) VALUES (?, 'node', ?)",
                [sid, nid],
            )
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo",
        )
    assert result is not None
    assert result.synthesis_id == "syn-new"  # by synthesis_timestamp, not archived_at
    assert result.synthesis_status == "passed"


# ---------------------------------------------------------------------------
# REST route
# ---------------------------------------------------------------------------


def test_route_promotes_end_to_end(client):
    _seed_synthesis()
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1", "deliverable_kind": "research_memo"},
    )
    assert r.status_code == 201
    body = r.json()
    assert body["block_count"] == 3
    assert body["dangling_count"] == 0
    assert body["insufficient_evidence"] is False
    assert body["synthesis_id"] == "syn-1"

    con = _read()
    try:
        nblocks = con.execute(
            "SELECT COUNT(*) FROM outline_blocks WHERE section_id = ?",
            [body["section_id"]],
        ).fetchone()[0]
    finally:
        con.close()
    assert nblocks == 3


def test_route_404_when_no_synthesis(client):
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "no-such-investigation"},
    )
    assert r.status_code == 404
    detail = r.json()["detail"]
    assert detail["error"] == "no_synthesis"
    assert detail["investigation_id"] == "no-such-investigation"


def test_route_insufficient_evidence_for_empty_synthesis(client):
    _seed_synthesis(nodes=())
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "not_promotable"
    assert detail["gate_failed"] == "no_source_nodes"
    assert detail["source_node_count"] == 0
    assert detail["live_source_node_count"] == 0


def test_route_rejects_insufficient_evidence_recommendation(client):
    _seed_synthesis(recommendation="insufficient_evidence")
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["error"] == "not_promotable"
    assert detail["gate_failed"] == "recommendation"
    assert detail["synthesis_recommendation"] == "insufficient_evidence"


def test_route_rejects_non_converged_synthesis(client):
    _seed_synthesis(status="regressed", recommendation="proceed")
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1"},
    )
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert detail["gate_failed"] == "status"
    assert detail["synthesis_status"] == "regressed"


def test_promotion_error_contracts_are_typed_in_openapi():
    from fastapi import FastAPI

    from interfaces.research.api.write_routes import write_router

    app = FastAPI()
    app.include_router(write_router)
    responses = app.openapi()["paths"][
        "/write/deliverables/from-investigation"
    ]["post"]["responses"]
    assert responses["404"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PromotionNotFoundResponse"
    )
    assert responses["409"]["content"]["application/json"]["schema"]["$ref"].endswith(
        "/PromotionRefusalResponse"
    )


def test_route_422_for_unknown_deliverable_kind(client):
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1", "deliverable_kind": "not_a_kind"},
    )
    assert r.status_code == 422


def test_route_404_when_only_a_draft_synthesis_exists(client):
    # A draft is not depositable → 404, not a 201 with a half-baked deliverable.
    _seed_synthesis(status="draft")
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1"},
    )
    assert r.status_code == 404
    assert r.json()["detail"]["error"] == "no_synthesis"


def test_route_surfaces_synthesis_status(client):
    _seed_synthesis(status="passed")  # the default
    r = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1"},
    )
    assert r.status_code == 201
    assert r.json()["synthesis_status"] == "passed"
