from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

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
from substrate.write.outline_block import place_block, place_user_authored_block


@pytest.fixture
def handoff(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = str(tmp_path / "antiek.duckdb")
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    ensure_initialized(default_db_path())
    with connect_write(default_db_path(), purpose="test/write_to_read_seed") as con:
        document_id = insert_document(
            con,
            document_id="doc-source",
            source_tier=2,
            document_type="book",
            title="Source Book",
        )
        con.execute(
            "UPDATE documents SET content_class='public_domain' WHERE document_id=?",
            [document_id],
        )
        chunk_id = insert_chunk(
            con, document_id=document_id, chunk_index=0, text="Source passage"
        )
        node_id = insert_node(
            con,
            canonical_label="Grounded claim",
            node_type="claim",
            graph_scope="cross_domain",
            investigation_id="inv-source",
            metadata={"chunk_id": chunk_id},
        )
        deliverable_id = insert_deliverable(
            con, title="Essay", deliverable_kind="general_essay"
        )
        section_id = insert_section(
            con, deliverable_id=deliverable_id, section_index=0, title="Claim"
        )
        block_id = place_block(
            con,
            section_id=section_id,
            block_kind="claim",
            provenance_kind="graph_node",
            node_id=node_id,
            block_index=0,
            deliverable_id=deliverable_id,
            investigation_id=deliverable_id,
        )
    return {
        "client": TestClient(create_app()),
        "events": events,
        "document": document_id,
        "chunk": chunk_id,
        "deliverable": deliverable_id,
        "section": section_id,
        "block": block_id,
    }


def _seam_events(events: Path) -> list[dict]:
    rows: list[dict] = []
    for path in events.rglob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return [row for row in rows if row["action_type"] == "seam.write_to_read"]


def _post(ctx, command_id="trace-command-1"):
    return ctx["client"].post(
        f"/write/blocks/{ctx['block']}/read-handoffs",
        headers={"Idempotency-Key": command_id},
        json={"deliverable_id": ctx["deliverable"]},
    )


def test_handoff_emits_same_block_and_reconstructs_production_thread(handoff):
    first = _post(handoff)
    second = _post(handoff)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["document_id"] == handoff["document"]
    assert first.json()["chunk_ids"][0] == handoff["chunk"]
    events = _seam_events(handoff["events"])
    assert len(events) == 1
    payload = events[0]["payload"]
    assert payload["entity_id"] == handoff["block"]
    assert payload["provenance_ref"] == handoff["block"]
    assert payload["source_document_id"] == handoff["document"]
    assert payload["source_region_id"] == handoff["chunk"]

    thread = handoff["client"].get(f"/thread/{handoff['block']}")
    assert thread.status_code == 200
    hops = thread.json()["hops"]
    assert [hop["workflow"] for hop in hops] == ["write", "read"]
    assert hops[1]["seam_event_id"] == first.json()["seam_event_id"]


def test_handoff_repairs_failed_append_from_command_receipt(handoff, monkeypatch):
    original = write_routes.append_event_once
    calls = 0

    def fail_once(event):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OSError("simulated append fault")
        return original(event)

    monkeypatch.setattr(write_routes, "append_event_once", fail_once)
    with pytest.raises(OSError, match="append fault"):
        _post(handoff)
    assert _seam_events(handoff["events"]) == []
    repaired = _post(handoff)
    assert repaired.status_code == 201
    assert len(_seam_events(handoff["events"])) == 1


def test_handoff_repairs_accepted_event_after_source_is_taken_down(handoff, monkeypatch):
    original = write_routes.append_event_once
    monkeypatch.setattr(
        write_routes, "append_event_once", lambda _event: (_ for _ in ()).throw(OSError())
    )
    with pytest.raises(OSError):
        _post(handoff)
    monkeypatch.setattr(write_routes, "append_event_once", original)
    with connect_write(default_db_path(), purpose="test/write_to_read_takedown") as con:
        con.execute(
            "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
            [handoff["document"]],
        )
    repaired = _post(handoff)
    assert repaired.status_code == 409
    assert len(_seam_events(handoff["events"])) == 1


def test_blocks_sharing_a_chunk_keep_independent_threads(handoff):
    with connect_write(default_db_path(), purpose="test/write_to_read_shared_chunk") as con:
        other = place_block(
            con,
            section_id=handoff["section"],
            block_kind="claim",
            provenance_kind="graph_node",
            node_id=con.execute("SELECT node_id FROM outline_blocks LIMIT 1").fetchone()[0],
            block_index=1,
            deliverable_id=handoff["deliverable"],
        )
    assert _post(handoff, "first-block").status_code == 201
    handoff["block"] = other
    assert _post(handoff, "second-block").status_code == 201
    assert handoff["client"].get(f"/thread/{other}").status_code == 200


def test_handoff_rejects_reused_command_for_another_block(handoff):
    assert _post(handoff).status_code == 201
    with connect_write(default_db_path(), purpose="test/write_to_read_second") as con:
        other = place_block(
            con,
            section_id=handoff["section"],
            block_kind="claim",
            provenance_kind="graph_node",
            node_id=con.execute("SELECT node_id FROM outline_blocks LIMIT 1").fetchone()[0],
            block_index=1,
            deliverable_id=handoff["deliverable"],
        )
    handoff["block"] = other
    assert _post(handoff).status_code == 409
    assert len(_seam_events(handoff["events"])) == 1


@pytest.mark.parametrize("state", ["gated", "node_only", "user_originated"])
def test_handoff_refuses_non_openable_targets_without_seam(handoff, state):
    with connect_write(default_db_path(), purpose="test/write_to_read_refusal") as con:
        if state == "gated":
            con.execute(
                "INSERT INTO book_assets (document_id, taken_down) VALUES (?, TRUE)",
                [handoff["document"]],
            )
        elif state == "node_only":
            node = insert_node(
                con,
                canonical_label="No source",
                node_type="claim",
                graph_scope="cross_domain",
                investigation_id="inv-source",
            )
            handoff["block"] = place_block(
                con,
                section_id=handoff["section"],
                block_kind="claim",
                provenance_kind="graph_node",
                node_id=node,
                block_index=1,
                deliverable_id=handoff["deliverable"],
            )
        else:
            handoff["block"] = place_user_authored_block(
                con,
                section_id=handoff["section"],
                content="My thought",
                block_index=1,
                deliverable_id=handoff["deliverable"],
            )
    assert _post(handoff).status_code == 409
    assert _seam_events(handoff["events"]) == []


def test_handoff_refuses_wrong_piece_and_disabled_events(handoff, monkeypatch):
    wrong = handoff["client"].post(
        f"/write/blocks/{handoff['block']}/read-handoffs",
        headers={"Idempotency-Key": "wrong-piece"},
        json={"deliverable_id": "another-piece"},
    )
    assert wrong.status_code == 404
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "true")
    with pytest.raises(RuntimeError, match="event persistence is disabled"):
        _post(handoff, "disabled")
    assert _seam_events(handoff["events"]) == []
