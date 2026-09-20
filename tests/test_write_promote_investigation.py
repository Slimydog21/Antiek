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
zero nodes → ``insufficient_evidence`` (surfaced, not papered over).
"""

from __future__ import annotations

import os
import sys

import duckdb
import pytest
from fastapi.testclient import TestClient

_REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from interfaces.research.api import create_app  # noqa: E402
from runtime.db_lock import connect_write  # noqa: E402
from substrate.auth.magic_link import mint_session_cookie  # noqa: E402
from substrate.graph import default_db_path, ensure_initialized  # noqa: E402
from substrate.graph.ops import insert_chunk, insert_document, insert_node  # noqa: E402
from substrate.write.outline_block import list_section_blocks  # noqa: E402
from substrate.write.promote_context import promote_investigation_to_deliverable  # noqa: E402
from substrate.write.provenance import resolve_provenance  # noqa: E402


@pytest.fixture(autouse=True)
def _isolated_db(tmp_path, monkeypatch):
    """Point the app + substrate at a temp DB + events dir (hermetic)."""
    db = str(tmp_path / "antiek.duckdb")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(tmp_path / "events"))
    ensure_initialized(default_db_path())
    return db


def _cookie(user_id: str) -> dict[str, str]:
    value = mint_session_cookie(user_id=user_id, email=f"{user_id}@example.test")
    return {"ANTIEK_SESSION": value}


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTIEK_AUTH_SECRET", "write-route-test-secret-at-least-32-bytes")
    monkeypatch.setenv(
        "ANTIEK_OPERATOR_EMAIL",
        "__operator__@example.test,user-bob@example.test",
    )
    test_client = TestClient(create_app())
    test_client.cookies.update(_cookie("__operator__"))
    return test_client


def _read():
    return duckdb.connect(default_db_path(), read_only=True)


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
    nothing (the insufficient_evidence case)."""
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
            con, "inv-1", deliverable_kind="research_memo", owner_user_id="user-a",
        )
    assert result is not None
    assert result.block_count == 3
    assert result.dangling_count == 0
    assert result.source_node_count == 3
    assert result.insufficient_evidence is False
    assert result.synthesis_id == "syn-1"
    assert result.synthesis_recommendation == "proceed"

    con = _read()
    try:
        # The deliverable is linked back to its source investigation.
        drow = con.execute(
            "SELECT deliverable_kind, investigation_root_id, title, owner_user_id "
            "FROM deliverables WHERE deliverable_id = ?",
            [result.deliverable_id],
        ).fetchone()
        assert drow[0] == "research_memo"
        assert drow[1] == "inv-1"
        assert drow[3] == "user-a"

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


def test_promote_flags_dangling_source_node_seeded_not_dropped():
    node_ids = _seed_synthesis()  # three nodes pinned by the synthesis
    # Delete one pinned node (FK-safe: it has no edges). The manifest row has
    # no FK to nodes, so it keeps referencing the now-gone node_id.
    with connect_write(default_db_path(), purpose="test/delete-node") as con:
        con.execute("DELETE FROM nodes WHERE node_id = ?", [node_ids[1]])

    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo", owner_user_id="user-a",
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
            owner_user_id="user-a",
        )
    assert result is None  # the route maps this to 404, never an empty 200


def test_promote_empty_synthesis_is_insufficient_evidence():
    # A synthesis that pinned zero source nodes — the dogfood finding's
    # dominant real case. Surfaced as a flag, never papered over with blocks.
    _seed_synthesis(nodes=())
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo", owner_user_id="user-a",
        )
    assert result is not None
    assert result.block_count == 0
    assert result.source_node_count == 0
    assert result.insufficient_evidence is True
    assert result.dangling_count == 0


def test_promote_skips_draft_synthesis_as_not_depositable():
    # A draft synthesis is in-flight / unevaluated — not a completed conclusion,
    # so it is not promoted as a deliverable (codex review: don't treat a draft
    # as "completed"). If a draft is all that exists → None (route 404).
    _seed_synthesis(status="draft")
    with connect_write(default_db_path(), purpose="test/promote") as con:
        result = promote_investigation_to_deliverable(
            con, "inv-1", deliverable_kind="research_memo", owner_user_id="user-a",
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
            con, "inv-1", deliverable_kind="research_memo", owner_user_id="user-a",
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
        owner = con.execute(
            "SELECT owner_user_id FROM deliverables WHERE deliverable_id = ?",
            [body["deliverable_id"]],
        ).fetchone()[0]
    finally:
        con.close()
    assert nblocks == 3
    assert owner == "__operator__"


def test_route_binds_authenticated_owner(client):
    _seed_synthesis()
    client.cookies.update(_cookie("user-bob"))
    response = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1", "owner_user_id": "attacker"},
    )
    assert response.status_code == 201, response.text
    result = response.json()
    con = _read()
    try:
        owner = con.execute(
            "SELECT owner_user_id FROM deliverables WHERE deliverable_id = ?",
            [result["deliverable_id"]],
        ).fetchone()[0]
    finally:
        con.close()
    assert owner == "user-bob"


def test_route_rejects_missing_authenticated_identity_without_writing(client):
    _seed_synthesis()
    client.cookies.clear()
    response = client.post(
        "/write/deliverables/from-investigation",
        json={"investigation_id": "inv-1", "owner_user_id": "user-bob"},
        headers={"X-User-Id": "user-bob", "X-Auth-Method": "antiek_session_cookie"},
    )
    assert response.status_code == 401
    con = _read()
    try:
        count = con.execute("SELECT COUNT(*) FROM deliverables").fetchone()[0]
    finally:
        con.close()
    assert count == 0


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
    assert r.status_code == 201
    body = r.json()
    assert body["block_count"] == 0
    assert body["insufficient_evidence"] is True


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
