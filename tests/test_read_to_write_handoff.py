from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import interfaces.research.api.write_routes as write_routes
from interfaces.research.api import create_app
from runtime.db_lock import connect_write
from substrate.event_log import append_event_once, prepare_typed_event
from substrate.graph import default_db_path, ensure_initialized
from substrate.graph.insight_question import insight_node_id
from substrate.graph.ops import insert_deliverable, insert_node, insert_section
from substrate.schemas.events import MarginaliaNotedPayload


@pytest.fixture
def seam(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    db = str(tmp_path / "antiek.duckdb")
    events = tmp_path / "events"
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    ensure_initialized(default_db_path())
    with connect_write(default_db_path(), purpose="test/read_to_write_seed") as con:
        deliverable_id = insert_deliverable(
            con, title="Analysis", deliverable_kind="research_memo"
        )
        section_id = insert_section(
            con, deliverable_id=deliverable_id, section_index=0, title="Argument"
        )
        node_id = insert_node(
            con,
            canonical_label="The reader's own insight",
            node_type="insight",
            graph_scope="cross_domain",
            investigation_id="inv-reader",
            metadata={"origin_note_id": "an-older-note", "source_kind": "user"},
            node_id=insight_node_id("The reader's own insight"),
        )
        # Same note marker, wrong authorship: it must not become eligible.
        insert_node(
            con,
            canonical_label="Model interpretation",
            node_type="insight",
            graph_scope="cross_domain",
            investigation_id="inv-reader",
            metadata={"origin_note_id": "note-1"},
        )
    append_event_once(
        prepare_typed_event(
            "inv-reader",
            MarginaliaNotedPayload(
                note_id="note-1",
                note_text="The reader's own insight",
                excerpt="Source passage",
                chunk_id=None,
            ),
            event_id="evt-marginalia-note-1",
        )
    )
    return TestClient(create_app()), events, deliverable_id, section_id, node_id


def _seam_events(events: Path) -> list[dict]:
    rows: list[dict] = []
    for path in events.rglob("*.jsonl"):
        rows.extend(json.loads(line) for line in path.read_text().splitlines() if line)
    return [row for row in rows if row["payload"]["action_type"] == "seam.read_to_write"]


def test_handoff_reuses_promoted_node_and_converges_on_retry(seam):
    client, events, deliverable_id, section_id, node_id = seam
    command = {
        "note_id": "note-1",
        "target_section_id": section_id,
        "investigation_id": "inv-reader",
    }

    first = client.post("/write/read-handoffs", json=command)
    second = client.post("/write/read-handoffs", json=command)

    assert first.status_code == second.status_code == 201
    assert first.json() == second.json()
    assert first.json()["node_id"] == node_id
    assert first.json()["deliverable_id"] == deliverable_id
    blocks = client.get(f"/write/sections/{section_id}/blocks").json()["blocks"]
    assert len(blocks) == 1
    assert blocks[0]["node_id"] == node_id
    assert blocks[0]["content"] is None
    emitted = _seam_events(events)
    assert len(emitted) == 1
    assert emitted[0]["payload"]["entity_id"] == node_id
    assert emitted[0]["payload"]["provenance_ref"] == "note-1"
    assert emitted[0]["payload"]["target_section_id"] == section_id


def test_handoff_repairs_event_append_from_durable_block_receipt(seam, monkeypatch):
    client, events, _deliverable_id, section_id, _node_id = seam
    original_append = write_routes.append_event_once
    failures = 0

    def fail_once(event):
        nonlocal failures
        failures += 1
        if failures == 1:
            raise OSError("simulated event store fault")
        return original_append(event)

    monkeypatch.setattr(write_routes, "append_event_once", fail_once)
    command = {
        "note_id": "note-1",
        "target_section_id": section_id,
        "investigation_id": "inv-reader",
    }
    with pytest.raises(OSError, match="event store fault"):
        client.post("/write/read-handoffs", json=command)
    assert _seam_events(events) == []

    repaired = client.post("/write/read-handoffs", json=command)
    assert repaired.status_code == 201
    assert len(_seam_events(events)) == 1
    with connect_write(default_db_path(), purpose="test/read_to_write_receipt") as con:
        row = con.execute(
            "SELECT json_extract_string(metadata, '$.seam_event_id'), "
            "json_extract_string(metadata, '$.seam_emitted_at') "
            "FROM outline_blocks"
        ).fetchone()
    assert row[0] == repaired.json()["seam_event_id"]
    assert datetime.fromisoformat(row[1]) == datetime.fromisoformat(
        _seam_events(events)[0]["emitted_at"].replace("Z", "+00:00")
    )


@pytest.mark.parametrize(
    "body",
    [
        {"note_id": "missing", "target_section_id": "{section}", "investigation_id": "inv"},
        {"note_id": "note-1", "target_section_id": "missing", "investigation_id": "inv"},
    ],
)
def test_handoff_refuses_missing_authority_without_side_effects(seam, body):
    client, events, _deliverable_id, section_id, _node_id = seam
    body["target_section_id"] = body["target_section_id"].format(section=section_id)
    assert client.post("/write/read-handoffs", json=body).status_code == 404
    with connect_write(default_db_path(), purpose="test/read_to_write_assert") as con:
        assert con.execute("SELECT count(*) FROM outline_blocks").fetchone()[0] == 0
    assert _seam_events(events) == []


def test_handoff_refuses_before_write_when_event_store_disabled(seam, monkeypatch):
    client, _events, _deliverable_id, section_id, _node_id = seam
    monkeypatch.setenv("ANTIEK_EVENTS_DISABLED", "true")
    with pytest.raises(RuntimeError, match="event persistence is disabled"):
        client.post(
            "/write/read-handoffs",
            json={
                "note_id": "note-1",
                "target_section_id": section_id,
                "investigation_id": "inv-reader",
            },
        )
    with connect_write(default_db_path(), purpose="test/read_to_write_disabled") as con:
        assert con.execute("SELECT count(*) FROM outline_blocks").fetchone()[0] == 0
