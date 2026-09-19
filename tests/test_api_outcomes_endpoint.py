"""Outcomes endpoint tests (POST /outcomes + GET /outcomes/{id}).

Per master-spec §13.8: outcomes feed the Phase 8 skill-growth gate.
The endpoints persist into the existing ``outcomes`` table (schema
defined in substrate/graph/schema.py).
"""

from __future__ import annotations

import os
import shutil
import tempfile
import uuid
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app


@pytest.fixture()
def isolated_db(monkeypatch):
    """Each test gets its own DuckDB file so write locks don't collide."""
    tmpdir = tempfile.mkdtemp(prefix="antiek-outcomes-test-")
    db_path = os.path.join(tmpdir, "antiek.duckdb")
    events_dir = os.path.join(tmpdir, "events")
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db_path)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events_dir)
    try:
        # Ensure schema is materialized before the API touches it.
        from substrate.graph import ensure_initialized
        ensure_initialized(db_path)
        yield db_path
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def _client():
    return TestClient(create_app(register_wrestling=False))


def _seed_synthesis(db_path: str, synthesis_id: str) -> None:
    """Insert a minimal syntheses row so the FK on outcomes resolves."""
    from runtime.db_lock import connect_write
    from substrate.graph.tenancy import (
        GraphTenancyState,
        initialize_graph_authority,
        transition_graph_tenancy_state,
    )
    from substrate.investigation_streams import initialize_composite_stream
    from substrate.investigation_tenancy import InvestigationAuthority

    authority = InvestigationAuthority(
        "__operator__", f"inv-{synthesis_id}", root=Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"])
    )
    initialize_composite_stream(authority)

    with connect_write(db_path, purpose="test:seed_synthesis") as con:
        initialize_graph_authority(con, authority)
        con.execute(
            "INSERT INTO syntheses ("
            "synthesis_id, investigation_id, target_question, synthesis_timestamp, "
            "status, implicit_recommendation, account_digest, investigation_digest"
            ") VALUES (?, ?, ?, CURRENT_TIMESTAMP, 'draft', 'undetermined', ?, ?)",
            [synthesis_id, authority.investigation_id, "test question",
             authority.account_digest, authority.investigation_digest],
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.UNSCOPED,
            desired=GraphTenancyState.COPYING,
        )
        transition_graph_tenancy_state(
            con,
            expected=GraphTenancyState.COPYING,
            desired=GraphTenancyState.SHADOW,
        )


def test_post_outcome_records_validated_grade(isolated_db):
    client = _client()
    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)

    resp = client.post(
        "/outcomes",
        json={
            "synthesis_id": synth_id,
            "observer": "__operator__",
            "thesis_outcomes": [{"kind": "validated", "note": "matches paper"}],
            "notes": "graded after independent review",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["synthesis_id"] == synth_id
    assert body["observer"] == "__operator__"
    assert body["outcome_id"].startswith("out-")


def test_get_outcomes_returns_recorded_grade(isolated_db):
    client = _client()
    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)

    client.post(
        "/outcomes",
        json={
            "synthesis_id": synth_id,
            "thesis_outcomes": [{"kind": "validated", "note": "ok"}],
        },
    )
    resp = client.get(f"/outcomes/{synth_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["synthesis_id"] == synth_id
    assert len(body["outcomes"]) == 1
    o = body["outcomes"][0]
    assert o["thesis_outcomes"] == [{"kind": "validated", "note": "ok"}]
    assert o["falsification_outcomes"] == []


def test_outcomes_persisted_in_chronological_order(isolated_db):
    client = _client()
    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)

    for i in range(3):
        client.post(
            "/outcomes",
            json={
                "synthesis_id": synth_id,
                "thesis_outcomes": [
                    {"kind": "validated", "note": f"grade {i}"}
                ],
            },
        )
    resp = client.get(f"/outcomes/{synth_id}")
    outcomes = resp.json()["outcomes"]
    assert len(outcomes) == 3
    # Oldest first per load_outcomes_for_synthesis contract.
    timestamps = [o["observed_at"] for o in outcomes]
    assert timestamps == sorted(timestamps)


def test_outcome_outbox_recovers_event_store_failure(isolated_db, monkeypatch):
    import substrate.synthesis_event_outbox as outbox
    from runtime.db_lock import connect_write
    from substrate.event_log import trajectory_authorized
    from substrate.investigation_tenancy import InvestigationAuthority
    from substrate.synthesis_event_outbox import reconcile_synthesis_events

    synth_id = f"syn-{uuid.uuid4().hex[:10]}"
    _seed_synthesis(isolated_db, synth_id)
    authority = InvestigationAuthority(
        "__operator__",
        f"inv-{synth_id}",
        root=Path(os.environ["ANTIEK_RESEARCH_EVENTS_DIR"]),
    )
    original_append = outbox.append_event_once_authorized

    def fail_append(*_args, **_kwargs):
        raise RuntimeError("simulated event store outage")

    monkeypatch.setattr(outbox, "append_event_once_authorized", fail_append)
    response = _client().post(
        "/outcomes",
        json={
            "synthesis_id": synth_id,
            "thesis_outcomes": [{"kind": "validated", "note": "durable"}],
        },
    )
    assert response.status_code == 200, response.text
    with connect_write(isolated_db, purpose="test-outcome-outbox-pending") as con:
        assert con.execute(
            "SELECT delivery_state, count(*) FROM synthesis_event_outbox "
            "WHERE synthesis_id = ? GROUP BY delivery_state",
            [synth_id],
        ).fetchall() == [("pending", 1)]

    monkeypatch.setattr(outbox, "append_event_once_authorized", original_append)
    with connect_write(isolated_db, purpose="test-outcome-outbox-reconcile") as con:
        assert reconcile_synthesis_events(con, authority).delivered == 1
        assert reconcile_synthesis_events(con, authority).delivered == 0

    rows = [
        row
        for row in trajectory_authorized(authority)
        if row.get("action_type") == "outcome.recorded"
        and row.get("synthesis_id") == synth_id
    ]
    assert len(rows) == 1
