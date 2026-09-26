"""Diligence-queue route proofs (autonomous-diligence SPR-01).

FastAPI TestClient against a REAL DuckDB fixture (the api_env shape from
tests/test_book_anchor_routes.py): flag → GET shows it queued; re-flag is
idempotent; dismiss transitions; the owner boundary; write-time ref
grounding (422 on ungroundable refs); the CHECK layer rejecting a bad
kind/status directly at the DB; the note cap at both layers. The auth
middleware's enforcement-disabled default stamps the single-operator
identity ("__operator__") unless a test re-keys a row at the store layer.
"""

from __future__ import annotations

import os
import tempfile

import duckdb
import pytest
from fastapi.testclient import TestClient

from interfaces.research.api.app import create_app
from runtime.db_lock import connect_write
from substrate.diligence.schema import init_diligence_schema
from substrate.graph import ensure_initialized
from substrate.graph.ops import insert_document


@pytest.fixture
def api_env(monkeypatch):
    tmpdir = tempfile.mkdtemp(prefix="diligence-api-")
    db = os.path.join(tmpdir, "t.duckdb")
    events = os.path.join(tmpdir, "events")
    arts = os.path.join(tmpdir, "artifacts")
    os.makedirs(events, exist_ok=True)
    monkeypatch.setenv("ANTIEK_DUCKDB_PATH", db)
    monkeypatch.setenv("ANTIEK_RESEARCH_EVENTS_DIR", events)
    monkeypatch.setenv("ANTIEK_RESEARCH_ARTIFACTS_DIR", arts)
    monkeypatch.setenv("ANTIEK_EMBEDDING_PROVIDER", "hash")
    monkeypatch.setenv("ANTIEK_HOME", tmpdir)
    ensure_initialized(db)
    return {"db": db, "events": events, "arts": arts, "home": tmpdir}


def _client() -> TestClient:
    return TestClient(create_app(register_wrestling=False))


def _seed_graph(db: str) -> None:
    """A document + one question node + one insight node for ref grounding."""
    with connect_write(db, purpose="test/seed-diligence") as con:
        insert_document(
            con,
            document_id="doc-1",
            source_tier=2,
            document_type="book",
            title="Diligence Book",
            raw_text="A book worth flagging.",
            content_class="public_domain",
            on_conflict="ignore",
        )
        con.execute(
            "INSERT INTO nodes (node_id, canonical_label, node_type, graph_scope) "
            "VALUES ('q-1', 'an open question', 'question', 'depth'), "
            "('i-1', 'an insight', 'insight', 'depth')",
        )


def _flag_payload(**over: object) -> dict:
    body = {
        "kind": "open_question",
        "object_ref": "q-1",
        "source_investigation_id": "inv-1",
    }
    body.update(over)
    return body


# ── Proof 1: flag → queue → idempotency → dismiss → owner boundary ─────────


def test_flag_get_reflag_and_dismiss(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    # Flag → 201, queued by default.
    created = client.post("/diligence/flags", json=_flag_payload(note="worth a look"))
    assert created.status_code == 201
    flag = created.json()
    assert flag["status"] == "queued"
    assert flag["object_ref"] == "q-1"
    assert flag["note"] == "worth a look"
    assert flag["spawned_investigation_id"] is None

    # GET shows it queued, newest first.
    queue = client.get("/diligence/queue").json()
    assert queue["count"] == 1
    assert queue["flags"][0]["flag_id"] == flag["flag_id"]
    assert queue["flags"][0]["status"] == "queued"

    # Re-flag the SAME object → 200 with the SAME row, never a duplicate.
    again = client.post("/diligence/flags", json=_flag_payload())
    assert again.status_code == 200
    assert again.json()["flag_id"] == flag["flag_id"]
    assert client.get("/diligence/queue").json()["count"] == 1

    # Dismiss → status dismissed; a second dismiss is idempotent (200).
    dismissed = client.post(f"/diligence/flags/{flag['flag_id']}/dismiss")
    assert dismissed.status_code == 200
    assert dismissed.json()["status"] == "dismissed"
    assert client.post(f"/diligence/flags/{flag['flag_id']}/dismiss").status_code == 200

    # Re-flagging AFTER a dismissal revives the SAME row to queued (the
    # gesture stays safe — still one row per object).
    revived = client.post("/diligence/flags", json=_flag_payload())
    assert revived.status_code == 200
    assert revived.json()["flag_id"] == flag["flag_id"]
    assert revived.json()["status"] == "queued"
    assert client.get("/diligence/queue").json()["count"] == 1


def test_concept_keys_normalize_and_converge(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    first = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "  Dark Matter "}
    )
    assert first.status_code == 201
    assert first.json()["object_ref"] == "dark matter"
    second = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "dark   matter"}
    )
    assert second.status_code == 200
    assert second.json()["flag_id"] == first.json()["flag_id"]
    assert client.get("/diligence/queue").json()["count"] == 1


def test_second_owner_sees_nothing(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    created = client.post("/diligence/flags", json=_flag_payload())
    assert created.status_code == 201
    flag_id = created.json()["flag_id"]

    # Re-key the row to another owner at the store layer (the request is
    # always the single test operator; the row's owner is what filters).
    with connect_write(db, purpose="test/rekey-owner") as con:
        con.execute(
            "UPDATE diligence_queue SET owner_user_id = 'someone-else' WHERE flag_id = ?",
            [flag_id],
        )

    assert client.get("/diligence/queue").json()["count"] == 0
    # And another owner's flag is not dismissable through this identity.
    assert client.post(f"/diligence/flags/{flag_id}/dismiss").status_code == 404


def test_ungroundable_ref_is_a_422(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    # A distilled-node flag must name a real node of the matching type.
    missing = client.post("/diligence/flags", json=_flag_payload(object_ref="no-such-node"))
    assert missing.status_code == 422
    assert "diligence_ref_ungrounded" in missing.json()["detail"]
    # An insight flag pointing at a QUESTION node is equally ungrounded.
    wrong_type = client.post(
        "/diligence/flags", json=_flag_payload(kind="insight", object_ref="q-1")
    )
    assert wrong_type.status_code == 422
    # A lawful insight flag grounds fine.
    ok = client.post("/diligence/flags", json=_flag_payload(kind="insight", object_ref="i-1"))
    assert ok.status_code == 201
    # A source document that does not exist is refused; the real one passes.
    bad_source = client.post(
        "/diligence/flags",
        json={"kind": "concept", "object_ref": "x", "source_document_id": "no-such-doc"},
    )
    assert bad_source.status_code == 422
    assert "diligence_source_ungrounded" in bad_source.json()["detail"]
    good_source = client.post(
        "/diligence/flags",
        json={"kind": "concept", "object_ref": "x", "source_document_id": "doc-1"},
    )
    assert good_source.status_code == 201


# ── Proof 2: the CHECK layer + the note cap ────────────────────────────────


def test_check_constraints_reject_bad_kind_and_status_at_the_db(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    with connect_write(db, purpose="test/check-init") as con:
        init_diligence_schema(con)

    # A kind outside the vocabulary violates the CHECK directly at the DB.
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/bad-kind"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref) "
            "VALUES ('dfl-bad', '__operator__', 'made_up', 'q-1')",
        )
    # A status outside the lifecycle is equally rejected.
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/bad-status"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref, status) "
            "VALUES ('dfl-bad', '__operator__', 'concept', 'x', 'flying')",
        )


def test_note_beyond_the_cap_is_a_422_at_the_api_and_a_check_at_the_db(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    too_long = "x" * 281
    resp = client.post("/diligence/flags", json=_flag_payload(note=too_long))
    assert resp.status_code == 422

    with connect_write(db, purpose="test/note-check-init") as con:
        init_diligence_schema(con)
    with pytest.raises(duckdb.ConstraintException), connect_write(
        db, purpose="test/note-check"
    ) as con:
        con.execute(
            "INSERT INTO diligence_queue (flag_id, owner_user_id, kind, object_ref, note) "
            f"VALUES ('dfl-note', '__operator__', 'concept', 'x', '{too_long}')",
        )

    # The cap itself is lawful.
    ok = client.post("/diligence/flags", json=_flag_payload(note="x" * 280))
    assert ok.status_code == 201


def test_dismiss_of_a_spawned_flag_is_a_409(api_env) -> None:
    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    created = client.post("/diligence/flags", json=_flag_payload())
    flag_id = created.json()["flag_id"]
    with connect_write(db, purpose="test/force-spawned") as con:
        con.execute(
            "UPDATE diligence_queue SET status = 'spawned', "
            "spawned_investigation_id = 'inv-spawned' WHERE flag_id = ?",
            [flag_id],
        )
    resp = client.post(f"/diligence/flags/{flag_id}/dismiss")
    assert resp.status_code == 409
    assert "diligence_not_dismissable" in resp.json()["detail"]


# ── SPR-03 proof 1: the lazy terminal projection on queue read ────────────


def _write_terminal_trajectory(events_dir: str, investigation_id: str, terminal: str | None) -> None:
    """A spawned investigation's trajectory: the start event, plus the
    terminal event when given (the projection's only input)."""
    import json as _json
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from pathlib import Path as _Path

    when = _datetime.now(_UTC)
    rows = [
        {
            "event_id": f"evt-{investigation_id}-start",
            "investigation_id": investigation_id,
            "action_type": "investigation.start_requested",
            "policy_id": "continuous_daemon",
            "emitted_at": when.isoformat(),
            "payload": {"action_type": "investigation.start_requested", "question": "q"},
        }
    ]
    if terminal:
        rows.append(
            {
                "event_id": f"evt-{investigation_id}-terminal",
                "investigation_id": investigation_id,
                "action_type": terminal,
                "emitted_at": when.isoformat(),
                "payload": {"action_type": terminal},
            }
        )
    with open(_Path(events_dir) / f"{investigation_id}.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(_json.dumps(row) + "\n")


def _force_spawned(db: str, flag_id: str, investigation_id: str) -> None:
    from substrate.diligence.store import DiligenceStore

    with connect_write(db, purpose="test/force-spawned-spr3") as con:
        DiligenceStore().mark_spawned(
            con,
            owner_user_id="__operator__",
            flag_id=flag_id,
            spawned_investigation_id=investigation_id,
        )


def test_spawned_flags_project_done_with_the_honest_outcome(api_env) -> None:
    """completed → done/completed; failed → done/failed; chase_halted →
    done/stopped (the terminal-honest rule); a still-running spawn reads
    spawned — and NONE of them reads in-flight forever once terminal."""
    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    cases = [
        ("completed-flag", "inv-t-done", "investigation.completed", "done", "completed"),
        ("failed-flag", "inv-t-failed", "investigation.failed", "done", "failed"),
        ("halted-flag", "inv-t-halted", "investigation.chase_halted", "done", "stopped"),
        ("running-flag", "inv-t-live", None, "spawned", None),
    ]
    for ref, iid, terminal, _status, _outcome in cases:
        created = client.post("/diligence/flags", json={"kind": "concept", "object_ref": ref})
        assert created.status_code == 201
        _force_spawned(db, created.json()["flag_id"], iid)
        _write_terminal_trajectory(api_env["events"], iid, terminal)

    flags = {f["object_ref"]: f for f in client.get("/diligence/queue").json()["flags"]}
    for ref, _iid, _terminal, status, outcome in cases:
        assert flags[ref]["status"] == status, ref
        assert flags[ref]["outcome"] == outcome, ref


# ── SPR-03 proof 4: the summary reconciles the sidecar + the event log ────


def test_summary_line_reconciles_against_sidecar_and_event_log(api_env) -> None:
    """'2 flags diligenced this week · $1.03 of $5.00 daily cap' — the count
    from queue rows + the event-log projection, the dollars from the budget
    sidecar (fabricated). NO new counters."""
    import json as _json
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from pathlib import Path as _Path

    db = api_env["db"]
    _seed_graph(db)
    client = _client()

    # The sidecar: $1.03 of the $5.00 daily cap spent today.
    budgets = _Path(api_env["home"]) / "budgets"
    budgets.mkdir(parents=True)
    stamp = _datetime.now(_UTC).strftime("%Y-%m-%d")
    (budgets / f"daemon_{stamp}.json").write_text(
        _json.dumps(
            {"date_stamp": stamp, "spent_usd": 1.03, "spawn_count": 2, "cap_usd": 5.0}
        )
    )

    # Two flags diligenced this week (spawned → terminal completed).
    for ref, iid in (("done-one", "inv-s-1"), ("done-two", "inv-s-2")):
        created = client.post("/diligence/flags", json={"kind": "concept", "object_ref": ref})
        _force_spawned(db, created.json()["flag_id"], iid)
        _write_terminal_trajectory(api_env["events"], iid, "investigation.completed")
    # One still queued — not counted.
    client.post("/diligence/flags", json={"kind": "concept", "object_ref": "still-queued"})

    summary = client.get("/diligence/queue").json()["summary"]
    assert summary["diligenced_this_week"] == 2
    assert summary["spent_usd"] == 1.03
    assert summary["cap_usd"] == 5.0


def test_no_new_spend_counters_in_the_diligence_surface() -> None:
    """The grep proof (SPR-03 rigor): the diligence store + routes introduce
    NO spend counters of their own — no sidecar writes, no reserves, no
    spawn tally. The summary reads the sidecar through budget.py's public
    read (remaining_today) and the log through the projection."""
    from pathlib import Path as _Path

    root = _Path(__file__).resolve().parent.parent
    sources = [
        root / "substrate" / "diligence" / "store.py",
        root / "substrate" / "diligence" / "schema.py",
        root / "interfaces" / "research" / "api" / "diligence_routes.py",
    ]
    forbidden = ("_write_snapshot", "record_actual(", ".reserve(", "spawn_count")
    for src in sources:
        text = src.read_text()
        for token in forbidden:
            assert token not in text, f"{src.name} carries spend-counter machinery: {token}"
    route_text = sources[2].read_text()
    assert "remaining_today" in route_text  # the sidecar's PUBLIC read


# ── Review hardening D1 (2026-09-25): the source document grounds to the
# CALLER. A flag may never steer the daemon at another owner's document. ──


def test_flag_cannot_reference_another_owners_document(api_env, monkeypatch) -> None:
    from interfaces.research.api import diligence_routes

    _seed_graph(api_env["db"])
    with connect_write(api_env["db"], purpose="test/seed-foreign-doc") as con:
        insert_document(
            con,
            document_id="doc-foreign",
            source_tier=2,
            document_type="book",
            title="Someone Else's Book",
            raw_text="not yours to diligence",
            content_class="personal_reading",
            owner_user_id="owner-b",
            on_conflict="ignore",
        )
    monkeypatch.setattr(
        diligence_routes, "_reader_owner_id", lambda request: "owner-a"
    )
    client = _client()
    denied = client.post(
        "/diligence/flags", json=_flag_payload(source_document_id="doc-foreign")
    )
    assert denied.status_code == 422
    assert "diligence_source_ungrounded" in denied.json()["detail"]

    # The caller's own document still grounds (existence AND ownership).
    with connect_write(api_env["db"], purpose="test/own-doc") as con:
        insert_document(
            con,
            document_id="doc-own",
            source_tier=2,
            document_type="book",
            title="My Book",
            raw_text="mine to diligence",
            content_class="public_domain",
            owner_user_id="owner-a",
            on_conflict="ignore",
        )
    allowed = client.post(
        "/diligence/flags",
        json=_flag_payload(
            object_ref="q-1", source_document_id="doc-own"
        ),
    )
    assert allowed.status_code == 201


# ── Review hardening D2 (2026-09-25): "diligenced this week" counts by the
# TERMINAL EVENT's time — the lazy projection's own truth — never by
# updated_at, which any later write (a receipt rewrite) refreshes. ────────


def test_weekly_count_uses_the_terminal_event_time_not_updated_at(api_env) -> None:
    import json as _json
    from datetime import UTC as _UTC
    from datetime import datetime as _datetime
    from datetime import timedelta as _timedelta
    from pathlib import Path as _Path

    db = api_env["db"]
    _seed_graph(db)
    client = _client()
    created = client.post(
        "/diligence/flags", json={"kind": "concept", "object_ref": "old-done"}
    )
    _force_spawned(db, created.json()["flag_id"], "inv-week-old")
    # The terminal event landed 8 days ago…
    old = _datetime.now(_UTC) - _timedelta(days=8)
    rows = [
        {
            "event_id": "evt-week-old-start",
            "investigation_id": "inv-week-old",
            "action_type": "investigation.start_requested",
            "policy_id": "continuous_daemon",
            "emitted_at": old.isoformat(),
            "payload": {"action_type": "investigation.start_requested", "question": "q"},
        },
        {
            "event_id": "evt-week-old-terminal",
            "investigation_id": "inv-week-old",
            "action_type": "investigation.completed",
            "policy_id": "continuous_daemon",
            "emitted_at": old.isoformat(),
            "payload": {"action_type": "investigation.completed"},
        },
    ]
    path = _Path(api_env["events"]) / f"{ 'inv-week-old' }.jsonl"
    path.write_text("".join(_json.dumps(r) + "\n" for r in rows))
    # …but a later bookkeeping write refreshed updated_at to NOW.
    with connect_write(db, purpose="test/refresh-updated-at") as con:
        con.execute(
            "UPDATE diligence_queue SET updated_at = ? "
            "WHERE spawned_investigation_id = 'inv-week-old'",
            [_datetime.now(_UTC).isoformat()],
        )

    summary = client.get("/diligence/queue").json()["summary"]
    assert summary["diligenced_this_week"] == 0
