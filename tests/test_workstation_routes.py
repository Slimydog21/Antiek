"""Workstation + tab-tree route proofs (workstation-tabs SPR-01).

FastAPI TestClient against a REAL DuckDB fixture: CRUD + owner scoping;
optimistic concurrency (409 on stale, never a clobber); refs-only payloads
(422 at the API AND the CHECK at the DB); the CHECK vocabulary at the DB
layer; the corpus tabTree adapter's server contract (load/save/allocate —
expected_version conflicts, never-reused numbers, invariant-refusing
saves); and NO window geometry anywhere in any persisted row (schema
introspection, not review).
"""

from __future__ import annotations

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.graph import ensure_initialized


@pytest.fixture
def api_env(tmp_path, monkeypatch):
    db = tmp_path / "t.duckdb"
    events = tmp_path / "events"
    arts = tmp_path / "artifacts"
    events.mkdir()
    arts.mkdir()
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", str(db))
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", str(events))
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", str(arts))
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    ensure_initialized(str(db))
    return {"db": str(db), "events": str(events), "arts": str(arts)}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


# ── Proof 1: CRUD + owner scoping ───────────────────────────────────────────


def test_create_rename_reorder_round_trip(api_env) -> None:
    client = _client()
    created = client.post("/workstations", json={"name": "Research", "color_token": "sun"})
    assert created.status_code == 201
    ws = created.json()
    assert ws["revision"] == 1
    assert ws["tabs"] == []

    # Rename + set tabs (full-replace at the seen revision).
    replaced = client.put(
        f"/workstations/{ws['workstation_id']}",
        json={
            "name": "The diligence desk",
            "color_token": "aurora",
            "tabs": [
                {"surface_kind": "reader", "surface_payload": {"documentId": "doc-1"}},
                {"surface_kind": "thread", "surface_payload": {"investigationId": "inv-1"}},
            ],
            "revision": 1,
        },
    )
    assert replaced.status_code == 200
    body = replaced.json()
    assert body["name"] == "The diligence desk"
    assert body["color_token"] == "aurora"
    assert body["revision"] == 2
    assert [t["surface_kind"] for t in body["tabs"]] == ["reader", "thread"]
    # Server minted tab ids; payloads round-trip.
    assert all(t["tab_id"].startswith("tab-") for t in body["tabs"])
    assert body["tabs"][0]["surface_payload"] == {"documentId": "doc-1"}

    # GET reflects it.
    listing = client.get("/workstations").json()
    assert listing["count"] == 1
    assert listing["workstations"][0]["name"] == "The diligence desk"
    assert len(listing["workstations"][0]["tabs"]) == 2


def test_a_second_owner_sees_none_of_it(api_env) -> None:
    client = _client()
    created = client.post("/workstations", json={"name": "Research"})
    ws_id = created.json()["workstation_id"]

    # Re-key the workstation at the store layer (the request is always the
    # single test operator; the row's owner is what the API filters on).
    with connect_write(api_env["db"], purpose="test/rekey") as con:
        con.execute(
            "UPDATE workstations SET owner_user_id = 'someone-else' WHERE workstation_id = ?",
            [ws_id],
        )
    assert client.get("/workstations").json()["count"] == 0
    assert client.get(f"/workstations/{ws_id}/tab-tree").status_code == 404
    assert (
        client.put(
            f"/workstations/{ws_id}",
            json={"name": "x", "tabs": [], "revision": 1},
        ).status_code
        == 404
    )
    assert client.delete(f"/workstations/{ws_id}").status_code == 404


# ── Proof 2: optimistic concurrency ─────────────────────────────────────────


def test_stale_revision_409s_and_the_row_is_unchanged(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    assert (
        client.put(
            f"/workstations/{ws['workstation_id']}",
            json={"name": "clobbered", "tabs": [], "revision": 0},
        ).status_code
        == 409
    )
    listing = client.get("/workstations").json()
    assert listing["workstations"][0]["name"] == "Research"
    assert listing["workstations"][0]["revision"] == 1


def test_concurrent_puts_exactly_one_wins(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    first = client.put(
        f"/workstations/{ws['workstation_id']}",
        json={"name": "first write", "tabs": [], "revision": ws["revision"]},
    )
    second = client.put(
        f"/workstations/{ws['workstation_id']}",
        json={"name": "second write", "tabs": [], "revision": ws["revision"]},
    )
    assert first.status_code == 200
    assert second.status_code == 409
    assert client.get("/workstations").json()["workstations"][0]["name"] == "first write"


# ── Proof 3: refs-only payloads (API 422 + the DB CHECK) ────────────────────


def test_a_payload_with_a_long_text_field_is_a_422_and_a_check_violation(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()

    # The API boundary refuses content in a tab payload.
    resp = client.put(
        f"/workstations/{ws['workstation_id']}",
        json={
            "name": "Research",
            "tabs": [
                {
                    "surface_kind": "reader",
                    "surface_payload": {"documentId": "doc-1", "body": "x" * 500},
                }
            ],
            "revision": 1,
        },
    )
    assert resp.status_code == 422
    assert "surface_payload_not_refs" in resp.json()["detail"]

    # The CHECK backstop: a writer skipping the API hits the byte cap.
    import json as _json

    with pytest.raises(duckdb.ConstraintException), connect_write(
        api_env["db"], purpose="test/payload-check"
    ) as con:
        con.execute(
            "INSERT INTO workstation_tabs (tab_id, workstation_id, position, "
            "surface_kind, surface_payload_json) VALUES ('tab-x', ?, 0, 'reader', ?)",
            [ws["workstation_id"], _json.dumps({"blob": "x" * 3000})],
        )


# ── Proof 4: the CHECK vocabulary at the DB layer ───────────────────────────


def test_checks_reject_an_unknown_kind_and_off_palette_color(api_env) -> None:
    from substrate.workstations.schema import init_workstations_schema

    with connect_write(api_env["db"], purpose="test/check-init") as con:
        init_workstations_schema(con)
    ws_id = _seed_ws(api_env["db"])
    with pytest.raises(duckdb.ConstraintException), connect_write(
        api_env["db"], purpose="test/bad-kind"
    ) as con:
        con.execute(
            "INSERT INTO workstation_tabs (tab_id, workstation_id, position, "
            "surface_kind, surface_payload_json) VALUES ('tab-x', ?, 0, 'made_up', '{}')",
            [ws_id],
        )
    with pytest.raises(duckdb.ConstraintException), connect_write(
        api_env["db"], purpose="test/bad-color"
    ) as con:
        con.execute(
            "INSERT INTO workstations (workstation_id, owner_user_id, name, "
            "color_token, position, revision) VALUES ('ws-x', '__operator__', "
            "'the desk', 'mauve', 0, 1)",
        )


def _seed_ws(db: str) -> str:
    with connect_write(db, purpose="test/seed-ws") as con:
        from substrate.workstations.store import WorkstationStore

        return WorkstationStore().create_workstation(
            con, owner_user_id="__operator__", name="the desk", color_token="sun",
            position=0,
        ).workstation_id


# ── Proof 5: the tab-tree adapter's server contract ─────────────────────────

def _snapshot(version: int, number: int | None = 1) -> dict:
    node = {
        "tab_id": "tab-1",
        "hier_number": "1",
        "child_order": [],
        "branch_origin": {"kind": "manual"},
        "public_number": number,
    }
    return {
        "tree": {
            "mothership": "research",
            "nodes": {"tab-1": node},
            "root_order": ["tab-1"],
            "history": {},
            "next_root_index": 2,
            "next_child_index": {},
        },
        "active_tab_id": "tab-1",
        "retired_numbers": [],
        "version": version,
    }


def test_tab_tree_save_load_round_trip_and_version_conflict(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    ws_id = ws["workstation_id"]

    # No tree yet — honestly absent at version 0.
    empty = client.get(f"/workstations/{ws_id}/tab-tree").json()
    assert empty["version"] == 0
    assert empty["snapshot"] == {}

    # Save at 0 → version 1; load round-trips the snapshot.
    saved = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": _snapshot(0), "expected_version": 0},
    )
    assert saved.status_code == 200
    assert saved.json()["version"] == 1
    loaded = client.get(f"/workstations/{ws_id}/tab-tree").json()
    assert loaded["version"] == 1
    assert loaded["snapshot"]["tree"]["nodes"]["tab-1"]["public_number"] == 1

    # A stale save 409s; the tree is unchanged.
    stale = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": _snapshot(0), "expected_version": 0},
    )
    assert stale.status_code == 409
    assert "tab_tree_version_conflict" in stale.json()["detail"]
    assert client.get(f"/workstations/{ws_id}/tab-tree").json()["version"] == 1

    # And the current version saves fine (the rebase path).
    ok = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": _snapshot(1), "expected_version": 1},
    )
    assert ok.status_code == 200
    assert ok.json()["version"] == 2


def test_allocate_is_monotonic_and_never_reused(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    ws_id = ws["workstation_id"]

    first = client.post(f"/workstations/{ws_id}/tab-tree/allocate").json()
    second = client.post(f"/workstations/{ws_id}/tab-tree/allocate").json()
    assert first["public_number"] == 1
    assert second["public_number"] == 2

    # The model's number-reuse refusal, server-enforced: a tab CLOSES (the
    # number retires into the snapshot's history) — the counter never drops.
    closed = _snapshot(1)
    closed["tree"]["history"] = {
        "tab-1": {"node": closed["tree"]["nodes"]["tab-1"], "closed_at": "t"}
    }
    closed["tree"]["nodes"] = {}
    closed["tree"]["root_order"] = []
    closed["retired_numbers"] = [
        {"tab_id": "tab-1", "hier_number": "1", "public_number": 1}
    ]
    closed["active_tab_id"] = None
    # Allocates don't save a tree — the row is still at version 0.
    saved = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": closed, "expected_version": 0},
    )
    assert saved.status_code == 200
    third = client.post(f"/workstations/{ws_id}/tab-tree/allocate").json()
    assert third["public_number"] == 3  # 1 is retired, NEVER re-issued


def test_an_invariant_failing_snapshot_is_a_422(api_env) -> None:
    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    ws_id = ws["workstation_id"]

    # A tree with the same public number held by two tabs — the model's
    # number contract violated.
    bad = _snapshot(0)
    bad["tree"]["nodes"]["tab-2"] = {
        "tab_id": "tab-2",
        "hier_number": "2",
        "child_order": [],
        "branch_origin": {"kind": "manual"},
        "public_number": 1,
    }
    bad["tree"]["root_order"].append("tab-2")
    resp = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": bad, "expected_version": 0},
    )
    assert resp.status_code == 422
    assert "invalid_snapshot" in resp.json()["detail"]
    assert client.get(f"/workstations/{ws_id}/tab-tree").json()["version"] == 0


# ── Proof 6: no window geometry anywhere in any persisted row ───────────────


def test_no_window_geometry_in_any_persisted_row(api_env) -> None:
    """Schema introspection, not review: rects/z/order are session-scoped by
    design (the spec's replay-open rule) — provably absent from the schema."""
    from runtime.db_lock import connect_read

    client = _client()
    ws = client.post("/workstations", json={"name": "Research"}).json()
    client.put(
        f"/workstations/{ws['workstation_id']}",
        json={
            "name": "Research",
            "tabs": [{"surface_kind": "reader", "surface_payload": {"documentId": "doc-1"}}],
            "revision": 1,
        },
    )
    client.put(
        f"/workstations/{ws['workstation_id']}/tab-tree",
        json={"snapshot": _snapshot(0), "expected_version": 0},
    )

    con = connect_read(api_env["db"])
    try:
        for table in ("workstations", "workstation_tabs", "workstation_tab_trees"):
            cols = [
                str(r[1])
                for r in con.execute(f"PRAGMA table_info('{table}')").fetchall()
            ]
            for banned in ("rect", "x", "y", "width", "height", "z_index", "geometry"):
                assert not any(c == banned or c.startswith(banned + "_") for c in cols), (
                    f"{table} carries geometry: {cols}"
                )
        # And no persisted VALUE carries a rect either — the payloads are refs.
        rows = con.execute(
            "SELECT surface_payload_json FROM workstation_tabs"
        ).fetchall()
        for (payload,) in rows:
            assert "rect" not in payload
    finally:
        con.close()


# ── Review hardening W1 (2026-09-25): the server's snapshot contract. A
# tree may not claim one tab_id from two nodes, and the active tab must
# exist — both are 422s, never persisted. ──────────────────────────────────


def test_tab_tree_rejects_duplicate_tab_id_and_dangling_active(api_env) -> None:
    client = _client()
    ws_id = client.post("/workstations", json={"name": "Research"}).json()[
        "workstation_id"
    ]

    dup = _snapshot(0)
    second = dict(dup["tree"]["nodes"]["tab-1"])
    dup["tree"]["nodes"]["tab-2"] = second  # SAME tab_id inside the node
    dup["tree"]["root_order"] = ["tab-1", "tab-2"]
    resp = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": dup, "expected_version": 0},
    )
    assert resp.status_code == 422
    assert "invalid_snapshot" in resp.json()["detail"]
    assert "tab_id" in resp.json()["detail"]

    dangling = _snapshot(0)
    dangling["active_tab_id"] = "tab-ghost"
    resp2 = client.put(
        f"/workstations/{ws_id}/tab-tree",
        json={"snapshot": dangling, "expected_version": 0},
    )
    assert resp2.status_code == 422
    assert "active_tab_id" in resp2.json()["detail"]

    # Nothing persisted by either refusal.
    assert client.get(f"/workstations/{ws_id}/tab-tree").json()["version"] == 0


# ── Review hardening W2 (2026-09-25): the replace invariant must survive
# `python -O`. A store returning None (stale-or-missing despite the route's
# in-transaction pre-check, monkeypatched here) is an honest 409, never a
# silently-skipped check. ─────────────────────────────────────────────────


def test_replace_survives_optimized_python_and_reports_stale(api_env, monkeypatch) -> None:
    from substrate.workstations.store import WorkstationStore

    client = _client()
    created = client.post("/workstations", json={"name": "Research"}).json()
    ws_id, revision = created["workstation_id"], created["revision"]
    monkeypatch.setattr(
        WorkstationStore, "replace_workstation", lambda self, con, **kwargs: None
    )
    stale = client.put(
        f"/workstations/{ws_id}",
        json={
            "name": "Renamed",
            "color_token": "sun",
            "tabs": [],
            "revision": revision,
        },
    )
    assert stale.status_code == 409
    assert "workstation_stale_revision" in stale.json()["detail"]
